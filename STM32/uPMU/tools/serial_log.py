"""Guarda cada linea del puerto serie con la hora de la PC en data/<tarea>_<fecha>.csv.

Uso: python tools/serial_log.py <tarea> [puerto=COM6] [segundos=0 (hasta Ctrl+C)]
"""
import csv
import datetime
import pathlib
import sys
import time

import serial

tarea = sys.argv[1]
puerto = sys.argv[2] if len(sys.argv) > 2 else "COM6"
duracion = float(sys.argv[3]) if len(sys.argv) > 3 else 0

data = pathlib.Path(__file__).resolve().parent.parent / "data"
data.mkdir(exist_ok=True)
ruta = data / f"{tarea}_{datetime.date.today():%Y%m%d}.csv"

with serial.Serial(puerto, 115200, timeout=1) as s, open(ruta, "a", newline="") as f:
    w = csv.writer(f)
    s.reset_input_buffer()
    s.readline()  # descarta la primera linea: puede llegar truncada
    t0 = time.time()
    try:
        while duracion == 0 or time.time() - t0 < duracion:
            linea = s.readline().decode(errors="replace").strip()
            if linea:
                w.writerow([datetime.datetime.now().isoformat(), linea])
                f.flush()
    except KeyboardInterrupt:
        pass
print(ruta)
