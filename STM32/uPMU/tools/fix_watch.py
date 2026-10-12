"""Vigila el fix del GPS a traves del Nucleo (lineas STATE y PPS del firmware normal, por el VCP).

Registra cada linea STATE/PPS/PMU/#NMEA en data/<tarea>_<fecha>.csv y corta cuando el fix (fix > 0 y >= 4
satelites) se sostiene `sostener` segundos, o al cumplirse `max_s`.
Uso: python tools/fix_watch.py [tarea=t1_5_antena] [puerto=COM6] [max_s=420] [sostener_s=300]
"""
import csv
import datetime
import pathlib
import sys
import time

import serial

tarea = sys.argv[1] if len(sys.argv) > 1 else "t1_5_antena"
puerto = sys.argv[2] if len(sys.argv) > 2 else "COM6"
max_s = float(sys.argv[3]) if len(sys.argv) > 3 else 420
sostener = float(sys.argv[4]) if len(sys.argv) > 4 else 300
ruta = pathlib.Path(__file__).resolve().parent.parent / "data" / f"{tarea}_{datetime.date.today():%Y%m%d}.csv"

t0 = time.time()
desde = None
ultimo = None
primer_fix = None
n_state = n_pps = 0
with serial.Serial(puerto, 115200, timeout=0.3) as s, open(ruta, "a", newline="") as f:
    w = csv.writer(f)
    s.reset_input_buffer()
    s.readline()
    while time.time() - t0 < max_s:
        linea = s.readline().decode(errors="replace").strip()
        if not linea:
            continue
        if linea.startswith(("STATE,", "PPS,", "#NMEA", "#LIVE", "#GPSRX")):
            w.writerow([datetime.datetime.now().isoformat(), linea])
            f.flush()
        if linea.startswith("PPS,"):
            n_pps += 1
        if linea.startswith("STATE,"):
            n_state += 1
            c = linea.split(",")
            fix, sats = int(c[2]), int(c[3])
            clave = (fix, sats)
            if clave != ultimo:
                print(f"t={time.time() - t0:5.0f}s  fix={fix} sats={sats}  utc={c[1]}  pps={n_pps}", flush=True)
                ultimo = clave
            ok = fix > 0 and sats >= 4
            if ok and primer_fix is None:
                primer_fix = time.time() - t0
            desde = (desde or time.time()) if ok else None
            if desde and time.time() - desde >= sostener:
                print(f"FIX SOSTENIDO {sostener:.0f} s con >= 4 satelites")
                break
print(f"fin tras {time.time() - t0:.0f} s; STATE={n_state}, PPS={n_pps}, primer fix a los "
      f"{primer_fix if primer_fix is not None else float('nan'):.0f} s; log: {ruta}")
