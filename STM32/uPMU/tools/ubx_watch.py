"""Monitor en vivo de satelites y fix con el GPS conectado directo al PC por USB (equivalente basico a u-center).

Consulta NAV-STATUS y NAV-SVINFO cada 2 s, guarda cada muestra en data/<tarea>_<fecha>.csv y corta al
cumplirse el tiempo maximo o cuando el fix (>= 4 satelites usados) se sostiene `sostener` segundos.
Uso: python tools/ubx_watch.py [puerto=COM7] [max_s=420] [sostener_s=300]
"""
import csv
import datetime
import pathlib
import struct
import sys
import time

import serial

puerto = sys.argv[1] if len(sys.argv) > 1 else "COM7"
max_s = float(sys.argv[2]) if len(sys.argv) > 2 else 420
sostener = float(sys.argv[3]) if len(sys.argv) > 3 else 300
ruta = pathlib.Path(__file__).resolve().parent.parent / "data" / f"t1_5_watch_{datetime.date.today():%Y%m%d}.csv"


def consulta(cls, mid):
    f = bytearray([0xB5, 0x62, cls, mid, 0, 0])
    a = c = 0
    for x in f[2:]:
        a = (a + x) & 0xFF
        c = (c + a) & 0xFF
    return bytes(f) + bytes([a, c])


def tramas(b):
    """Devuelve (tramas validas, bytes sin consumir)."""
    out, i = [], 0
    while i + 8 <= len(b):
        if b[i] == 0xB5 and b[i + 1] == 0x62:
            n = b[i + 4] | b[i + 5] << 8
            if i + 8 + n > len(b):
                break
            a = c = 0
            for x in b[i + 2:i + 6 + n]:
                a = (a + x) & 0xFF
                c = (c + a) & 0xFF
            if (a, c) == (b[i + 6 + n], b[i + 7 + n]):
                out.append((b[i + 2], b[i + 3], bytes(b[i + 6:i + 6 + n])))
                i += 8 + n
                continue
        i += 1
    return out, b[i:]


FIX = {0: "sin fix", 1: "DR", 2: "2D", 3: "3D", 4: "GPS+DR", 5: "tiempo"}
t0 = time.time()
proximo = t0
resto = bytearray()
fix, usados, con_senal, mejores = 0, 0, 0, []
desde = None
ultimo_txt = None
with serial.Serial(puerto, 115200, timeout=0.2) as s, open(ruta, "a", newline="") as f:
    w = csv.writer(f)
    w.writerow(["pc_time", "t_s", "gpsFix", "fixOk", "usados", "con_senal", "cno_top3"])
    while time.time() - t0 < max_s:
        if time.time() >= proximo:
            proximo += 2
            s.write(consulta(0x01, 0x03) + consulta(0x01, 0x30))
        resto += s.read(1024)
        tr, resto = tramas(resto)
        if len(resto) > 4096:
            resto = resto[-512:]
        for cls, mid, p in tr:
            if (cls, mid) == (0x01, 0x03) and len(p) == 16:
                fix, fl = p[4], p[5]
                fix = fix if fl & 1 else 0
            elif (cls, mid) == (0x01, 0x30) and len(p) >= 8:
                nch = p[4]
                sv = [struct.unpack_from("<BBBBBbhi", p, 8 + 12 * k) for k in range(nch)]
                usados = sum(1 for x in sv if x[2] & 1)
                con_senal = sum(1 for x in sv if x[4] > 0)
                mejores = sorted((x[4] for x in sv), reverse=True)[:3]
                t = time.time() - t0
                w.writerow([datetime.datetime.now().isoformat(), f"{t:.0f}", fix, int(fix > 0), usados,
                            con_senal, "/".join(map(str, mejores))])
                f.flush()
                txt = (FIX.get(fix, fix), usados, con_senal)
                if txt != ultimo_txt:
                    print(f"t={t:4.0f}s fix={FIX.get(fix, fix)} usados={usados} con_senal={con_senal} "
                          f"cno_top3={mejores}", flush=True)
                    ultimo_txt = txt
                ok = fix > 0 and usados >= 4
                desde = (desde or time.time()) if ok else None
        if desde and time.time() - desde >= sostener:
            print(f"FIX SOSTENIDO {sostener:.0f} s con >= 4 satelites")
            break
print("fin tras", f"{time.time() - t0:.0f}", "s; log:", ruta)
