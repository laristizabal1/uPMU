"""T2.4: retardo entre el PPS y el primer byte ('$') de cada sentencia NMEA, por tipo.

Entrada: log con lineas `PPS,<n>,<fase>,<k>,<n_dma>` y `NMEA,<tipo>,<k>,<cnt>,<hora>` (firmware con -DNMEA_TS).
Cada sentencia se asocia al ultimo PPS anterior; el retardo es
    ((k_nmea - k_pps) * 1000 + (cnt_nmea - fase_pps)) ticks / f_timer
con f_timer = 59,93 MHz (la medida del propio log: delta medio entre PPS), no 60 MHz nominales.
Ademas comprueba la hipotesis del md: la RMC posterior al pulso trae la hora de ESE pulso. La referencia
independiente es el reloj de la PC (UTC): el segundo UTC del instante de llegada de la linea, menos el retardo.

Uso: python tools/analyze_nmea_delay.py data/t2_4_nmea_20261011.csv [--png docs/nmea_delay.png]
"""
import argparse
import collections
import csv
import datetime
import statistics as st

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("log")
ap.add_argument("--png", default="docs/nmea_delay.png")
ap.add_argument("--ticks", type=int, default=0, help="ticks por muestra; 0 = el del log (1000 HSI, 1200 HSE)")
args = ap.parse_args()
TICKS = args.ticks
if not TICKS:
    TICKS = 1000
    for _pc, _l in csv.reader(open(args.log)):
        if _l.startswith("#LIVE") and "ticks=" in _l:
            TICKS = int(dict(x.split("=") for x in _l.split(",")[1:] if "=" in x)["ticks"])

pps = []     # (k, fase, t_pc)
nmea = []    # (tipo, k, cnt, hora, t_pc)
for pc, linea in csv.reader(open(args.log)):
    c = linea.split(",")
    t = datetime.datetime.fromisoformat(pc)
    if c[0] == "PPS" and len(c) == 5:
        pps.append((int(c[3]), int(c[2]), t))
    elif c[0] == "NMEA" and len(c) == 5:
        nmea.append((c[1], int(c[2]), int(c[3]), c[4], t))

# frecuencia efectiva del timer, del propio log
T = [k * TICKS + f for k, f, _ in pps]
d = [b - a for a, b in zip(T, T[1:])]
nom = st.median(d)
ftim = st.mean([x for x in d if abs(x - nom) < 0.01 * nom])
print(f"PPS: {len(pps)}, NMEA: {len(nmea)}, f_timer efectiva = {ftim / 1.0:.0f} Hz")

por_tipo = collections.defaultdict(list)
horas = []   # (hora_nmea, segundo UTC de la PC en el pulso)
for tipo, k, cnt, hora, t_pc in nmea:
    prev = [p for p in pps if (k - p[0]) * TICKS + (cnt - p[1]) >= 0]
    if not prev:
        continue
    kp, fp, tp = prev[-1]
    ticks = (k - kp) * TICKS + (cnt - fp)
    ms = ticks / ftim * 1e3
    if 0 <= ms < 1000:
        por_tipo[tipo].append(ms)
        if tipo == "RMC" and hora:
            # UTC de la PC en el instante del pulso: llegada de la linea - retardo - latencia de transmision (~USB)
            utc = t_pc.astimezone(datetime.timezone.utc) if t_pc.tzinfo else t_pc.astimezone().astimezone(datetime.timezone.utc)
            seg_pulso = (utc - datetime.timedelta(milliseconds=ms + 100)).replace(microsecond=0)
            horas.append((hora, seg_pulso))

print(f"\n{'tipo':6s} {'n':>5s} {'media ms':>9s} {'sigma ms':>9s} {'min ms':>8s} {'max ms':>8s}")
for tipo, v in sorted(por_tipo.items(), key=lambda kv: st.mean(kv[1])):
    print(f"{tipo:6s} {len(v):5d} {st.mean(v):9.2f} {st.pstdev(v):9.2f} {min(v):8.2f} {max(v):8.2f}")

if horas:
    cuenta = collections.Counter()
    for hora, seg in horas:
        hhmmss = int(hora.split(".")[0])
        h, m, s = hhmmss // 10000, (hhmmss // 100) % 100, hhmmss % 100
        d_s = (h * 3600 + m * 60 + s) - (seg.hour * 3600 + seg.minute * 60 + seg.second)
        cuenta[d_s] += 1
    print("\nHora de la RMC menos segundo UTC del pulso (reloj de la PC), en segundos -> numero de RMC:")
    for d_s, n in sorted(cuenta.items()):
        print(f"  {d_s:+d} s : {n}")

fig, ax = plt.subplots(figsize=(9, 4.5))
for tipo, v in sorted(por_tipo.items(), key=lambda kv: st.mean(kv[1])):
    ax.hist(v, bins=40, alpha=0.6, label=f"{tipo} (n={len(v)})")
ax.set_xlabel("retardo PPS -> '$' (ms)")
ax.set_ylabel("sentencias")
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(args.png, dpi=110)
print("figura:", args.png)
