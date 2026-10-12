"""Prueba de src/nmea.c en la PC: compila el mismo C como DLL y le pasa sentencias reales de data/*.csv
mas casos construidos a mano. Referencia independiente: parser en Python.

Compilador: gcc/cc si existen; si no, `python -m ziglang cc` (pip install ziglang).
Uso: python tools/test_nmea.py
"""
import csv
import ctypes
import glob
import pathlib
import shutil
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def compilar(salida):
    cc = shutil.which("gcc") or shutil.which("cc")
    cmd = [cc] if cc else [sys.executable, "-m", "ziglang", "cc"]
    subprocess.run(cmd + ["-shared", "-O1", "-Wall", "-Wextra", "-I", str(RAIZ / "include"),
                          str(RAIZ / "src" / "nmea.c"), "-o", str(salida)], check=True)


class Nmea(ctypes.Structure):  # espejo de nmea_t (include/nmea.h)
    _fields_ = [("line", ctypes.c_char * 96), ("len", ctypes.c_uint8), ("in_sentence", ctypes.c_uint8),
                ("dirty", ctypes.c_uint8), ("time", ctypes.c_char * 11), ("date", ctypes.c_char * 7),
                ("rmc_status", ctypes.c_char), ("fix", ctypes.c_uint8), ("sats", ctypes.c_uint8),
                ("n_ok", ctypes.c_uint32), ("n_bad", ctypes.c_uint32), ("type", ctypes.c_char * 4)]


tmp = pathlib.Path(tempfile.mkdtemp()) / "nmea.dll"
compilar(tmp)
lib = ctypes.CDLL(str(tmp))
lib.nmea_feed.argtypes = [ctypes.POINTER(Nmea), ctypes.c_uint8]
lib.nmea_state_line.argtypes = [ctypes.POINTER(Nmea), ctypes.c_char_p, ctypes.c_size_t]
GGA, RMC, BAD = 2, 3, -1


def nuevo():
    n = Nmea()
    lib.nmea_init(ctypes.byref(n))
    return n


def alimentar(n, datos):
    """Devuelve la lista de resultados distintos de NONE."""
    return [r for r in (lib.nmea_feed(ctypes.byref(n), b) for b in datos) if r != 0]


def estado(n):
    buf = ctypes.create_string_buffer(64)
    lib.nmea_state_line(ctypes.byref(n), buf, 64)
    return buf.value.decode()


def cs(cuerpo):
    x = 0
    for c in cuerpo:
        x ^= ord(c)
    return f"{x:02X}"


def sent(cuerpo):
    return f"${cuerpo}*{cs(cuerpo)}\r\n".encode()


# 1) Sentencias reales de los logs: mismo conteo que la referencia en Python
total_ok = 0
for ruta in sorted(glob.glob(str(RAIZ / "data" / "t1_3_*.csv"))):
    lineas = [fila[1] for fila in csv.reader(open(ruta)) if len(fila) == 2]
    esperadas = sum(1 for l in lineas if l.startswith("$") and "*" in l and
                    cs(l[1:].rsplit("*", 1)[0]) == l.rsplit("*", 1)[1].upper())
    n = nuevo()
    res = alimentar(n, "".join(l + "\r\n" for l in lineas).encode())
    assert n.n_ok == esperadas and n.n_bad == 0, (ruta, n.n_ok, esperadas, n.n_bad)
    ggas = sum(1 for l in lineas if l[3:6] == "GGA")
    assert res.count(GGA) == ggas, (ruta, res.count(GGA), ggas)
    assert estado(n) == "STATE,,0,0", estado(n)  # logs sin fix: hora vacia
    total_ok += n.n_ok
    print(f"OK {pathlib.Path(ruta).name}: {n.n_ok} sentencias, {res.count(GGA)} GGA, estado={estado(n)}")

# 2) Casos construidos a mano (sinteticos, no son mediciones)
n = nuevo()
r = alimentar(n, sent("GPRMC,083559.00,A,4717.11437,N,00833.91522,E,0.004,77.52,091202,,,A") +
              sent("GPGGA,083559.00,4717.11437,N,00833.91522,E,1,08,0.94,499.7,M,47.4,M,,"))
assert r == [RMC, GGA], r
assert estado(n) == "STATE,091202T083559.00,1,8", estado(n)
assert n.rmc_status == b"A"

n = nuevo()  # talker GN y fix 4
alimentar(n, sent("GNGGA,120000.00,4717.11,N,00833.91,E,4,12,0.8,1.0,M,1.0,M,,"))
assert (n.fix, n.sats) == (4, 12) and estado(n) == "STATE,------T120000.00,4,12", estado(n)

n = nuevo()  # checksum malo: se descarta y se cuenta, el estado no cambia
cuerpo = "GPGGA,083559.00,4717.11,N,00833.91,E,1,08,0.94,499.7,M,47.4,M,,"
assert cs(cuerpo) != "00"
mala = f"${cuerpo}*00\r\n".encode()  # checksum 00: no coincide
assert alimentar(n, mala) == [BAD] and n.n_bad == 1 and n.n_ok == 0 and estado(n) == "STATE,,0,0"

n = nuevo()  # sin '*', demasiado larga, basura antes y '$' a mitad de linea
assert alimentar(n, b"$GPGGA,sin,checksum\r\n") == [BAD]
assert alimentar(n, b"\xff\x00ruido$GPGGA," + b"9" * 200 + b"\r\n") == [BAD]
assert alimentar(n, b"$GPGGA,0835" + sent("GPRMC,083559.00,A,,,,,,,091202,,,A")) == [RMC]
assert n.n_bad == 3 and n.n_ok == 1, (n.n_bad, n.n_ok)  # la sentencia cortada por '$' cuenta como mala

n = nuevo()  # byte a byte con trozos partidos y '\n' solo
s = sent("GPGGA,235959.99,,,,,2,07,1.0,,M,,M,,").replace(b"\r\n", b"\n")
assert alimentar(n, s) == [GGA] and estado(n) == "STATE,------T235959.99,2,7"

print(f"TODO OK ({total_ok} sentencias reales validadas)")
