"""T5.1: comprueba el sello UTC de las tramas PMU con la senal del DAC (firmware -DDAC_TEST).

La senoidal del DAC sale del mismo reloj que el muestreo, asi que su fase es lineal en el *numero de muestra*. Si
el sello UTC fuera perfecto, la fase del fasor de corriente seria lineal en el UTC; los residuos de la recta
`fase = a + 360 * f * t` son el error del sello en tiempo (residuo / (360 f)), mas el ruido de fase del estimador
(~0,004 deg = 0,2 us). Tambien compara el segundo UTC con el reloj de la PC y el paso entre tramas.

Uso: python tools/check_stamp.py data/t5_sync_20261011.csv [--png docs/stamp.png]
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
ap.add_argument("--png", default="docs/stamp.png")
args = ap.parse_args()

t_utc, ang, t_pc, dia = [], [], [], None
for pc, linea in csv.reader(open(args.log)):
    c = linea.split(",")
    if c[0] != "PMU" or len(c) != 8 or c[7] != "SYNC":
        continue
    u = c[1]                                   # ddmmyyThhmmss.ffffff
    hh, mm, ss = int(u[7:9]), int(u[9:11]), float(u[11:])
    s = hh * 3600 + mm * 60 + ss
    d = u[:6]
    if dia is None:
        dia = d
    if d != dia:                               # cambio de dia: no se usa
        continue
    t_utc.append(s)
    ang.append(float(c[6]))
    t_pc.append(datetime.datetime.fromisoformat(pc))

n = len(t_utc)
print(f"tramas SYNC: {n}, duracion {t_utc[-1] - t_utc[0]:.1f} s")

# 1) paso entre tramas: debe ser 2000 muestras / tasa real
dt = [b - a for a, b in zip(t_utc, t_utc[1:])]
print(f"paso entre tramas: media {st.mean(dt) * 1e3:.4f} ms, sigma {st.pstdev(dt) * 1e6:.2f} us, "
      f"min {min(dt) * 1e3:.3f}, max {max(dt) * 1e3:.3f} ms")

# 2) segundo UTC contra el reloj de la PC (la PC solo vale a ~+-0,5 s)
dif = []
for s, tp in zip(t_utc, t_pc):
    u = tp.astimezone().astimezone(datetime.timezone.utc)
    dif.append(s - (u.hour * 3600 + u.minute * 60 + u.second + u.microsecond * 1e-6))
print(f"UTC del firmware - UTC de la PC: mediana {st.median(dif):+.2f} s, rango {min(dif):+.2f} .. {max(dif):+.2f} s "
      f"(la PC agrega la latencia USB/serie)")

# 3) error del sello en tiempo. El paso de fase entre tramas consecutivas es regular (la senal esta fija a la
# rejilla de muestreo: 2000 muestras por trama); el paso de los SELLOS no lo es en las fronteras de segundo, donde
# el sello se vuelve a anclar al pulso. Esa discontinuidad es el error acumulado del segundo anterior, que crece
# linealmente de 0 (en el pulso) hasta E_fin al final del segundo (interpolacion causal con la tasa previa).
da = [(b - a + 180.0) % 360.0 - 180.0 for a, b in zip(ang, ang[1:])]
da_med = st.median(da)
dt_med = st.median(dt)
f_fis = (da_med / 360.0 + round(60.0 * dt_med)) / dt_med       # Hz fisicos (ciclos enteros por trama incluidos)
cruce = [i for i in range(len(t_utc) - 1) if int(t_utc[i + 1]) != int(t_utc[i])]
setc = set(cruce)
J = [(dt[i] - dt_med) * 1e6 - (da[i] - da_med) / (360.0 * f_fis) * 1e6 for i in cruce]   # us: salto del sello
dentro = [(dt[i] - dt_med) * 1e6 for i in range(len(dt)) if i not in setc]
print(f"frecuencia fisica de la senal: {f_fis:.4f} Hz")
print(f"paso de sello dentro de un segundo: sigma {st.pstdev(dentro):.2f} us (la tasa es constante)")
print(f"discontinuidad del sello en las fronteras de segundo ({len(J)}): sigma {st.pstdev(J):.1f} us, "
      f"max |J| {max(abs(x) for x in J):.1f} us")
fin = [abs(x) for x in J]
rad = 2 * 3.141592653589793 * f_fis
print(f"  error al final del segundo = |J|: media {st.mean(fin):.1f} us, p95 {sorted(fin)[int(0.95 * len(fin))]:.1f} us")
print(f"  TVE por tiempo al final del segundo: rms {rad * st.pstdev(J) * 1e-6 * 100:.2f} %, "
      f"max {rad * max(fin) * 1e-6 * 100:.2f} % (limite 1 % = {0.01 / rad * 1e6:.1f} us)")
print(f"  fraccion de segundos cuyo error final supera el limite de 1 %: "
      f"{100.0 * sum(1 for x in fin if x > 0.01 / rad * 1e6) / len(fin):.0f} %")
# perfil dentro del segundo: error = u * E_fin (u = fraccion del segundo); rms sobre u uniforme = sigma / sqrt(3)
print(f"  rms sobre todo el segundo (perfil lineal): {st.pstdev(J) / 3 ** 0.5:.1f} us = "
      f"{rad * st.pstdev(J) / 3 ** 0.5 * 1e-6 * 100:.2f} % de TVE")
res_us = [0.0] * len(t_utc)
for i, e in enumerate(J):
    pass

fig, ax = plt.subplots(2, 1, figsize=(10, 6))
ax[0].plot([t_utc[i + 1] - t_utc[0] for i in cruce], J, ".-", lw=0.6)
ax[0].set_ylabel("salto del sello en el pulso (us)")
ax[0].grid(alpha=0.3)
ax[1].hist(J, bins=30)
ax[1].set_xlabel("error del sello al final del segundo (us)")
ax[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(args.png, dpi=110)
print("figura:", args.png)
