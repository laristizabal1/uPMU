"""T4.3: prueba de src/estimator.c en la PC (mismo C que el firmware) contra la referencia de data/vectors/*.json.

Para cada vector: codigos -> CIC entero S -> (hi = S >> 2, lo = 2 bits, como en el firmware) -> est_run por canal,
y compara frecuencia (promedio de V e I, como `measure` de ref), modulo y angulo con `ref` (float64).
Compila dos veces: float32 (el del firmware) y double (para separar error numerico de error de algoritmo).

Compilador: gcc/cc, o `ZIGPY=<python con ziglang> python tools/test_est.py`.
"""
import ctypes
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parent.parent
LSB = 3.3 / 4096
TAPS = np.array([1, 3, 6, 10, 12, 12, 10, 6, 3, 1], dtype=np.int64)
FS = 15000.0


def compilar(defs, nombre):
    cc = shutil.which("gcc") or shutil.which("cc")
    cmd = [cc] if cc else [os.environ.get("ZIGPY", sys.executable), "-m", "ziglang", "cc"]
    dll = pathlib.Path(tempfile.mkdtemp()) / nombre
    defs = defs + os.environ.get("EST_DEFS", "").split()   # p. ej. EST_DEFS="-DEST_ITER=2"
    subprocess.run(cmd + ["-shared", "-O2", "-Wall", "-Wextra", "-I", str(RAIZ / "include")] + defs +
                   [str(RAIZ / "src" / "estimator.c"), "-o", str(dll)], check=True)
    return ctypes.CDLL(str(dll))


def estimador(dll, doble):
    t = ctypes.c_double if doble else ctypes.c_float

    class Est(ctypes.Structure):
        _fields_ = [("f_hz", t), ("mag_rms", t), ("ang_rad", t)]

    dll.est_run.argtypes = [ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32,
                            ctypes.c_uint32, ctypes.c_uint32, t, ctypes.c_uint32, ctypes.POINTER(Est)]

    def run(s):
        """s: salida entera S del CIC (int64). Se empaqueta como en el firmware: hi = S >> 2, lo = 2 bits."""
        n = len(s)
        hi = (ctypes.c_uint16 * n)(*(int(x) >> 2 for x in s))
        lo = (ctypes.c_uint8 * ((n + 3) // 4))()
        for i, x in enumerate(s):
            lo[i >> 2] |= (int(x) & 3) << (2 * (i & 3))
        out = Est()
        r = dll.est_run(hi, lo, n, 0, n, FS, 4, ctypes.byref(out))   # buffer lineal; 4 ciclos -> k0 = 4
        assert r == 0
        return out.f_hz, out.mag_rms, out.ang_rad
    return run


def vector(m, binario):
    cod = np.frombuffer(binario, dtype="<u2").reshape(-1, 2).astype(np.int64)
    n = m["n_out"]
    return [np.convolve(cod[:, ch], TAPS)[9::4][:n] for ch in (0, 1)]


def main():
    variantes = [("float32 (firmware)", estimador(compilar([], "est_f.dll"), False)),
                 ("double", estimador(compilar(["-DEST_DOUBLE"], "est_d.dll"), True))]
    vectores = sorted((RAIZ / "data" / "vectors").glob("vec_*.json"))
    for nombre, run in variantes:
        print(f"\n=== {nombre} ===")
        print(f"{'vector':18s} {'df mHz':>8s} {'dMagV %':>9s} {'dMagI %':>9s} {'dAngV deg':>10s} {'dAngI deg':>10s}")
        peor = np.zeros(5)
        for j in vectores:
            m = json.loads(j.read_text())
            yv, yi = vector(m, j.with_suffix(".bin").read_bytes())
            fv, mv, av = run(yv)
            fi, mi, ai = run(yi)
            r = m["ref"]
            mag_v, mag_i = mv * LSB / 64.0, mi * LSB / 64.0          # unidades S (= 64 * codigos) -> volts en el nodo
            e = np.array([
                abs(0.5 * (fv + fi) - r["f_hz"]) * 1e3,
                abs(mag_v / r["node_v_rms"][0] - 1) * 100,
                abs(mag_i / r["node_i_rms"][0] - 1) * 100,
                abs((np.degrees(av) - r["node_v_rms"][1] + 180) % 360 - 180),
                abs((np.degrees(ai) - r["node_i_rms"][1] + 180) % 360 - 180)])
            peor = np.maximum(peor, e)
            print(f"{m['name']:18s} {e[0]:8.4f} {e[1]:9.5f} {e[2]:9.5f} {e[3]:10.5f} {e[4]:10.5f}")
        print(f"{'PEOR':18s} {peor[0]:8.4f} {peor[1]:9.5f} {peor[2]:9.5f} {peor[3]:10.5f} {peor[4]:10.5f}")
        ok = peor[0] < 1 and peor[1] < 0.001 and peor[2] < 0.001 and peor[3] < 0.001 and peor[4] < 0.001
        print("cumple (< 1 mHz, < 0,001 %, < 0,001 deg):", "SI" if ok else "NO")


if __name__ == "__main__":
    main()
