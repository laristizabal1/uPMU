"""T2.2: estadistica del intervalo entre PPS medido con el contador del Nucleo.

Lee un log de data/ (lineas `PPS,<n>,<fase>,<k>,<n_dma>` y `STATE,...`) y, para cada par de pulsos consecutivos,
T = k * 1000 + fase (ticks de 60 MHz nominales, k = disparos de muestreo exactos) y delta = T[i+1] - T[i].
Calcula media, desviacion estandar, deriva en ppm, jitter segundo a segundo (que separa ruido de reloj del
PPS) y guarda histograma y serie temporal en PNG.

Uso: python tools/analyze_pps.py data/t2_2_pps_20261011.csv [--out docs/pps]
Solo cuentan los pulsos con fix (los PPS sin fix, ver T2.3, se separan por la linea STATE previa).
"""
import argparse
import csv
import datetime
import statistics as st

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("log")
ap.add_argument("--out", default="docs/pps")
ap.add_argument("--nominal", type=float, default=0, help="frecuencia nominal del timer (Hz); 0 = la del log")
ap.add_argument("--ticks", type=int, default=0, help="ticks por muestra; 0 = el del log (1000 HSI, 1200 HSE)")
args = ap.parse_args()

# el firmware informa `clk=`, `hz=` y `ticks=` en la linea #LIVE (cada 10 s)
_ticks, _hz = 1000, 60e6
for _pc, _l in csv.reader(open(args.log)):
    if _l.startswith("#LIVE") and "ticks=" in _l:
        _kv = dict(x.split("=") for x in _l.split(",")[1:] if "=" in x)
        _ticks, _hz = int(_kv["ticks"]), float(_kv["hz"])
if not args.ticks:
    args.ticks = _ticks
if not args.nominal:
    args.nominal = _hz
print(f"ticks por muestra: {args.ticks}, reloj nominal del timer: {args.nominal:.0f} Hz")

pulsos = []  # (t_pc, T_ticks, fix)
fix = 0
for pc, linea in csv.reader(open(args.log)):
    c = linea.split(",")
    if c[0] == "STATE":
        fix = int(c[2])
    elif c[0] == "PPS" and len(c) == 5:
        pulsos.append((datetime.datetime.fromisoformat(pc).timestamp(), int(c[3]) * args.ticks + int(c[2]), fix))

if len(pulsos) < 10:
    raise SystemExit(f"pocos pulsos: {len(pulsos)}")
t0 = pulsos[0][0]
tt, dd = [], []
for (ta, Ta, fa), (tb, Tb, fb) in zip(pulsos, pulsos[1:]):
    d = Tb - Ta
    if fa > 0 and fb > 0:
        tt.append(tb - t0)
        dd.append(d)
nom = st.median(dd)
buenos = [(t, d) for t, d in zip(tt, dd) if abs(d - nom) < 0.01 * nom]
perdidos = len(dd) - len(buenos)
t_b = [t for t, _ in buenos]
d_b = [d for _, d in buenos]
n = len(d_b)
m, s = st.mean(d_b), st.pstdev(d_b)
ppm = [(d - args.nominal) / args.nominal * 1e6 for d in d_b]
dif = [b - a for a, b in zip(d_b, d_b[1:])]
jit = st.pstdev(dif) / 2 ** 0.5
tau = [b - a for a, b in zip(t_b, t_b[1:])]
print(f"pulsos con fix: {len(pulsos)}, intervalos validos: {n}, descartados (saltos): {perdidos}")
print(f"duracion: {t_b[-1] - t_b[0]:.0f} s")
print(f"delta medio: {m:.1f} ticks  (frecuencia efectiva del timer {m:.1f} Hz)")
print(f"  desviacion del reloj respecto a {args.nominal:.0f} Hz: {(m - args.nominal) / args.nominal * 1e6:+.1f} ppm")
print(f"  sigma del delta: {s:.1f} ticks = {s / args.nominal * 1e9:.0f} ns ({s / args.nominal * 1e6:.1f} ppm)")
print(f"  min {min(d_b)}  max {max(d_b)}  (rango {max(d_b) - min(d_b)} ticks)")
print(f"  jitter segundo a segundo: {jit:.0f} ticks = {jit / args.nominal * 1e6:.1f} us "
      f"({jit / args.nominal * 1e6:.1f} ppm)")
bloque = max(10, n // 10)
trozos = [round(st.mean(ppm[i:i + bloque]), 1) for i in range(0, n - bloque + 1, bloque)]
print(f"  deriva por bloques de {bloque} s (ppm): {trozos}")
print(f"  tendencia: {trozos[-1] - trozos[0]:+.1f} ppm entre el primer y el ultimo bloque")

fig, ax = plt.subplots(2, 1, figsize=(10, 7))
ax[0].plot([t / 60 for t in t_b], ppm, lw=0.6)
ax[0].set_xlabel("t (min)")
ax[0].set_ylabel("error del reloj (ppm)")
ax[0].grid(alpha=0.3)
ax[1].hist(d_b, bins=60)
ax[1].set_xlabel("delta entre PPS (ticks de 60 MHz)")
ax[1].set_ylabel("cuentas")
ax[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(args.out + ".png", dpi=110)
print("figura:", args.out + ".png")
