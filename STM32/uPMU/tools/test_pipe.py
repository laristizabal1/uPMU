"""T5: prueba de src/pipeline.c (+ cic.c + estimator.c) en la PC, mismo C que el firmware.

1) Alimenta una senal larga (varias ventanas) por pipe_push y, en cada disparo, estima sobre la ventana circular;
   compara con el estimador sobre la misma ventana construida aparte con numpy (S = convolucion entera).
   Verifica: instantes de disparo (cada `period` salidas desde que se llena N), ventana mas reciente, envoltura del
   buffer circular y deteccion de ventana pisada.
2) Que la frecuencia y el modulo salgan donde deben (la senal sintetica tiene f y amplitud conocidas).

Compilador: gcc/cc o `ZIGPY=<python con ziglang>`.
"""
import ctypes
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TAPS = np.array([1, 3, 6, 10, 12, 12, 10, 6, 3, 1], dtype=np.int64)
FS = 15000.0
SLACK = 600

cc = shutil.which("gcc") or shutil.which("cc")
cmd = [cc] if cc else [os.environ.get("ZIGPY", sys.executable), "-m", "ziglang", "cc"]
dll = pathlib.Path(tempfile.mkdtemp()) / "pipe.dll"
subprocess.run(cmd + ["-shared", "-O2", "-Wall", "-Wextra", "-I", str(RAIZ / "include")] +
               [str(RAIZ / "src" / n) for n in ("pipeline.c", "cic.c", "estimator.c")] + ["-o", str(dll)], check=True)
lib = ctypes.CDLL(str(dll))


class Cic(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint32) for n in ("i1", "i2", "i3", "c1", "c2", "c3", "n")]


class Pipe(ctypes.Structure):
    _fields_ = [("n", ctypes.c_uint32), ("period", ctypes.c_uint32), ("len", ctypes.c_uint32),
                ("hi_v", ctypes.c_void_p), ("hi_i", ctypes.c_void_p), ("lo_v", ctypes.c_void_p),
                ("lo_i", ctypes.c_void_p), ("cic_v", Cic), ("cic_i", Cic), ("wp", ctypes.c_uint32),
                ("n_out", ctypes.c_uint32), ("next_due", ctypes.c_uint32), ("rep_seq", ctypes.c_uint32),
                ("rep_start", ctypes.c_uint32), ("rep_n_out", ctypes.c_uint32),
                ("n_in", ctypes.c_uint32), ("base_m", ctypes.c_uint32)]


class Est(ctypes.Structure):
    _fields_ = [("f_hz", ctypes.c_float), ("mag_rms", ctypes.c_float), ("ang_rad", ctypes.c_float)]


u16p, u8p = ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint8)
lib.pipe_init.argtypes = [ctypes.POINTER(Pipe), ctypes.c_uint32, u16p, u8p, u16p, u8p]
lib.pipe_push.argtypes = [ctypes.POINTER(Pipe), ctypes.c_uint32, ctypes.c_uint32]
lib.pipe_take.argtypes = [ctypes.POINTER(Pipe)] + [ctypes.POINTER(ctypes.c_uint32)] * 4
lib.pipe_window_valid.argtypes = [ctypes.POINTER(Pipe), ctypes.c_uint32]
lib.est_run.argtypes = [u16p, u8p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float,
                        ctypes.c_uint32, ctypes.POINTER(Est)]


def sintetica(f, n_in, amp_v=1500.0, amp_i=700.0, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n_in) / 60000.0
    v = 2048 + amp_v * np.sin(2 * np.pi * f * t + 0.3) + rng.normal(0, 1.5, n_in)
    i = 2048 + amp_i * np.sin(2 * np.pi * f * t - 0.5) + rng.normal(0, 1.5, n_in)
    return np.clip(np.round(v), 0, 4095).astype(np.uint32), np.clip(np.round(i), 0, 4095).astype(np.uint32)


def prueba(f0, f):
    n = 60000 // f0
    period = n // 2
    n_in = 4 * (n + 4 * period + 700) + 40           # ventana llena + 4 reportes + sobrante
    v, i = sintetica(f, n_in)
    Sv = np.convolve(v.astype(np.int64), TAPS)[9::4]
    Si = np.convolve(i.astype(np.int64), TAPS)[9::4]

    length = n + SLACK
    hi_v = (ctypes.c_uint16 * length)(); hi_i = (ctypes.c_uint16 * length)()
    lo_v = (ctypes.c_uint8 * ((length + 3) // 4))(); lo_i = (ctypes.c_uint8 * ((length + 3) // 4))()
    p = Pipe()
    assert lib.pipe_init(ctypes.byref(p), f0, hi_v, lo_v, hi_i, lo_i) == 0
    assert (p.n, p.period, p.len) == (n, period, length)

    seen = ctypes.c_uint32(0)
    start, n_at, skipped = ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint32()
    reportes = []
    for k in range(len(v)):
        lib.pipe_push(ctypes.byref(p), int(v[k]), int(i[k]))
        if lib.pipe_take(ctypes.byref(p), ctypes.byref(seen), ctypes.byref(start), ctypes.byref(n_at),
                         ctypes.byref(skipped)):
            ev, ei = Est(), Est()
            assert lib.est_run(hi_v, lo_v, length, start.value, n, FS, 4, ctypes.byref(ev)) == 0
            assert lib.est_run(hi_i, lo_i, length, start.value, n, FS, 4, ctypes.byref(ei)) == 0
            reportes.append((n_at.value, start.value, ev, ei, skipped.value))

    assert len(reportes) >= 4, len(reportes)
    for r, (n_out_at, st, ev, ei, sk) in enumerate(reportes):
        assert n_out_at == n + r * period, (r, n_out_at)          # primer reporte al llenar la ventana, luego cada period
        assert sk == 0
        # ventana de referencia: las n salidas que terminan en n_out_at (numpy), estimada con el mismo C lineal
        w = slice(n_out_at - n, n_out_at)
        hv = (ctypes.c_uint16 * n)(*(int(x) >> 2 for x in Sv[w]))
        lv = (ctypes.c_uint8 * ((n + 3) // 4))()
        for q, x in enumerate(Sv[w]):
            lv[q >> 2] |= (int(x) & 3) << (2 * (q & 3))
        e0 = Est()
        assert lib.est_run(hv, lv, n, 0, n, FS, 4, ctypes.byref(e0)) == 0
        assert (e0.f_hz, e0.mag_rms, e0.ang_rad) == (ev.f_hz, ev.mag_rms, ev.ang_rad), (r, e0.f_hz, ev.f_hz)
        assert abs(ev.f_hz - f) < 0.01, (r, ev.f_hz, f)
        # modulo esperado: amp * ganancia CIC / sqrt2 en unidades S (= 64 * codigos)
        x = np.pi * f / 60000.0
        g = (np.sin(4 * x) / (4 * np.sin(x))) ** 3
        esperado = 1500.0 * g / np.sqrt(2) * 64
        assert abs(ev.mag_rms / esperado - 1) < 2e-3, (r, ev.mag_rms, esperado)
    assert lib.pipe_window_valid(ctypes.byref(p), reportes[-1][0]) in (0, 1)
    # ventana pisada: si llegan mas de SLACK salidas tras el disparo, pipe_window_valid debe decir 0
    assert lib.pipe_window_valid(ctypes.byref(p), (p.n_out - SLACK) & 0xFFFFFFFF) == 1
    assert lib.pipe_window_valid(ctypes.byref(p), (p.n_out - SLACK - 1) & 0xFFFFFFFF) == 0
    print(f"OK f0={f0} f={f}: {len(reportes)} reportes, ventana circular (len {length}) == ventana lineal, "
          f"f_est = {reportes[-1][2].f_hz:.4f} Hz")


prueba(60, 60.0)
prueba(60, 61.3)
prueba(50, 50.0)
prueba(50, 47.2)
print("TODO OK")
