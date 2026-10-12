"""Prueba de src/vecrx.c en la PC con los vectores de data/vectors/ (mismo C que el firmware).

Compilador: gcc/cc o `python -m ziglang cc` (pip install ziglang).  Uso: python tools/test_vecrx.py
"""
import ctypes
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
dll = pathlib.Path(tempfile.mkdtemp()) / "vecrx.dll"
cc = shutil.which("gcc") or shutil.which("cc")
cmd = [cc] if cc else [sys.executable, "-m", "ziglang", "cc"]
subprocess.run(cmd + ["-shared", "-O1", "-Wall", "-Wextra", "-I", str(RAIZ / "include"),
                      str(RAIZ / "src" / "vecrx.c"), str(RAIZ / "src" / "cic.c"), "-o", str(dll)], check=True)
lib = ctypes.CDLL(str(dll))


class Cic(ctypes.Structure):  # espejo de cic_t (include/cic.h)
    _fields_ = [(n, ctypes.c_uint32) for n in ("i1", "i2", "i3", "c1", "c2", "c3", "n")]


class Vecrx(ctypes.Structure):  # espejo de vecrx_t (include/vecrx.h)
    _fields_ = [("state", ctypes.c_uint8), ("idx", ctypes.c_uint8), ("buf", ctypes.c_uint8 * 4),
                ("t_last", ctypes.c_uint32), ("got", ctypes.c_uint32), ("crc", ctypes.c_uint32),
                ("crc_rx", ctypes.c_uint32), ("n_in", ctypes.c_uint16), ("f0", ctypes.c_uint8),
                ("flags", ctypes.c_uint8), ("crc_calc", ctypes.c_uint32), ("sum_v", ctypes.c_uint32),
                ("sum_i", ctypes.c_uint32), ("min_v", ctypes.c_uint16), ("max_v", ctypes.c_uint16),
                ("min_i", ctypes.c_uint16), ("max_i", ctypes.c_uint16),
                ("cic_v", Cic), ("cic_i", Cic), ("n_out_max", ctypes.c_uint32), ("n_out", ctypes.c_uint32),
                ("crc_s", ctypes.c_uint32), ("sum_sv", ctypes.c_uint32), ("sum_si", ctypes.c_uint32),
                ("first_sv", ctypes.c_int32), ("first_si", ctypes.c_int32), ("last_sv", ctypes.c_int32),
                ("last_si", ctypes.c_int32), ("hi_v", ctypes.c_void_p), ("hi_i", ctypes.c_void_p),
                ("lo_v", ctypes.c_void_p), ("lo_i", ctypes.c_void_p)]


lib.vecrx_feed.argtypes = [ctypes.POINTER(Vecrx), ctypes.c_uint8, ctypes.c_uint32]
lib.vecrx_poll.argtypes = [ctypes.POINTER(Vecrx), ctypes.c_uint32]
OK, CRC, HDR, TIMEOUT = 1, 2, 3, 4


def nuevo():
    r = Vecrx()
    lib.vecrx_init(ctypes.byref(r))
    return r


def alimentar(r, datos, t=0):
    res = []
    for b in datos:
        x = lib.vecrx_feed(ctypes.byref(r), b, t)
        if x:
            res.append(x)
    return res


def trama(payload, n_in, f0=60, crc=None):
    crc = zlib.crc32(payload) & 0xFFFFFFFF if crc is None else crc
    return b"\x55\x56" + struct.pack("<HBB", n_in, f0, 0) + payload + struct.pack("<I", crc)


# 1) todos los vectores reales: estadistica y CRC iguales a los del JSON
total = 0
for j in sorted((RAIZ / "data" / "vectors").glob("vec_*.json")):
    m = json.loads(j.read_text())
    payload = j.with_suffix(".bin").read_bytes()
    r = nuevo()
    res = alimentar(r, b"\xaa\x55" + trama(payload, m["n_in"], m["f0_nominal"]))  # basura antes: debe resincronizar
    s = m["stats"]
    assert res == [OK], (m["name"], res)
    got = dict(sum_v=r.sum_v, sum_i=r.sum_i, min_v=r.min_v, max_v=r.max_v, min_i=r.min_i, max_i=r.max_i,
               crc32=r.crc_calc)
    assert got == {k: s[k] for k in got}, (m["name"], got, s)
    assert r.n_in == m["n_in"] and r.f0 == m["f0_nominal"]
    c = m["cic"]  # T4.2: salida del CIC entero identica a la de Python (CRC32 de las 2*n salidas)
    got = dict(n_out=r.n_out, crc32=r.crc_s, sum_sv=r.sum_sv, sum_si=r.sum_si, first_sv=r.first_sv,
               first_si=r.first_si, last_sv=r.last_sv, last_si=r.last_si)
    assert got == c, (m["name"], got, c)
    total += 1
print(f"OK: {total} vectores reales con estadistica, CRC y salida del CIC identicos")

# 2) casos de error
payload = j.with_suffix(".bin").read_bytes()
n_in = m["n_in"]
r = nuevo()
mal = bytearray(payload); mal[100] ^= 1
assert alimentar(r, trama(bytes(mal), n_in, 60, zlib.crc32(payload) & 0xFFFFFFFF)) == [CRC]
assert alimentar(r, trama(payload, n_in, 60)) == [OK]                    # y se recupera para la siguiente
assert alimentar(r, b"\x55\x56" + struct.pack("<HBB", 0, 60, 0)) == [HDR]        # n_in = 0
assert alimentar(r, b"\x55\x56" + struct.pack("<HBB", 7000, 60, 0)) == [HDR]     # demasiado grande
assert alimentar(r, b"\x55\x56" + struct.pack("<HBB", 100, 55, 0)) == [HDR]      # f0 invalido
assert alimentar(r, trama(payload, n_in, 50)) == [OK] and r.f0 == 50
# trama a medias + timeout, y luego una trama buena
r = nuevo()
assert alimentar(r, trama(payload, n_in)[:500], t=1000) == []
assert lib.vecrx_poll(ctypes.byref(r), 1100) == 0                      # aun dentro del plazo
assert lib.vecrx_poll(ctypes.byref(r), 1600) == TIMEOUT
assert alimentar(r, trama(payload, n_in), t=2000) == [OK]
print("OK: CRC malo, cabeceras invalidas, resincronizacion y timeout")
