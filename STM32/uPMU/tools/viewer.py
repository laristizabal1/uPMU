"""T5.5: visor en vivo de la trama PMU (frecuencia, modulo de V e I, desfase V-I y estado de sincronia).

Lee las lineas `PMU,<utc>,<f_Hz>,<V_rms>,<V_ang_deg>,<I_rms>,<I_ang_deg>,<bandera>` (docs/FORMATO_TRAMA.md) del
puerto serie, o de un log de data/ con --replay.

Uso:
  python tools/viewer.py [--port COM6] [--window 30]                 ventana en vivo (30 s visibles)
  python tools/viewer.py --port COM6 --duration 300 --save out.png   sin ventana: corre 5 min y guarda la figura
  python tools/viewer.py --replay data/t5_dac_loop_20261011.csv --save out.png

Al terminar (o con Ctrl+C) imprime: tramas, tasa, huecos mayores a 2 periodos y recuento por bandera.
"""
import argparse
import collections
import csv
import datetime
import sys
import time

import matplotlib

ap = argparse.ArgumentParser()
ap.add_argument("--port", default="COM6")
ap.add_argument("--baud", type=int, default=115200)
ap.add_argument("--window", type=float, default=30.0, help="segundos visibles")
ap.add_argument("--duration", type=float, default=0.0, help="segundos a correr (0 = hasta cerrar la ventana)")
ap.add_argument("--replay", help="log CSV de data/ (pc_time,linea) en vez del puerto serie")
ap.add_argument("--save", help="guarda la figura final en este PNG")
args = ap.parse_args()
headless = bool(args.save and (args.duration or args.replay))
if headless:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLOR = {"SYNC": "tab:green", "HOLD": "tab:orange", "NOSYNC": "tab:red"}
t_s, f_hz, v_rms, i_rms, dphi, flags = ([] for _ in range(6))
conteo = collections.Counter()
huecos = 0


def parse(linea, t):
    c = linea.strip().split(",")
    if len(c) != 8 or c[0] != "PMU":
        return False
    try:
        f, v, va, i, ia = (float(x) for x in c[2:7])
    except ValueError:
        return False
    d = (va - ia + 180.0) % 360.0 - 180.0
    t_s.append(t); f_hz.append(f); v_rms.append(v); i_rms.append(i); dphi.append(d); flags.append(c[7])
    conteo[c[7]] += 1
    return True


def fuente():
    """Genera (tiempo_s, linea): del log o del puerto serie."""
    if args.replay:
        t0 = None
        for pc, linea in csv.reader(open(args.replay)):
            t = datetime.datetime.fromisoformat(pc).timestamp()
            t0 = t if t0 is None else t0
            yield t - t0, linea
        return
    import serial
    with serial.Serial(args.port, args.baud, timeout=0.05) as s:
        t0, buf = time.time(), b""
        while True:
            buf += s.read(4096)
            while b"\n" in buf:
                linea, buf = buf.split(b"\n", 1)
                yield time.time() - t0, linea.decode(errors="replace")
            yield None, None


fig, ax = plt.subplots(4, 1, sharex=True, figsize=(10, 8))
etiquetas = ["f (Hz)", "V rms (V)", "I rms (A)", "V - I (deg)"]
lineas = []
for a, e in zip(ax, etiquetas):
    a.set_ylabel(e)
    a.grid(alpha=0.3)
    lineas.append(a.plot([], [], lw=1)[0])
ax[3].set_xlabel("t (s)")
txt = fig.text(0.01, 0.985, "", va="top", fontsize=10, family="monospace")


def refresca():
    if not t_s:
        return
    t1 = t_s[-1]
    ini = next((k for k, t in enumerate(t_s) if t >= t1 - args.window), 0)
    for ln, y in zip(lineas, (f_hz, v_rms, i_rms, dphi)):
        ln.set_data(t_s[ini:], y[ini:])
    for a in ax:
        a.set_xlim(max(0, t1 - args.window), max(args.window, t1))
        a.relim()
        a.autoscale_view(scaley=True, scalex=False)
    fl = flags[-1]
    txt.set_text(f"bandera: {fl}   f = {f_hz[-1]:.4f} Hz   V = {v_rms[-1]:.3f} V   I = {i_rms[-1]:.4f} A   "
                 f"tramas = {len(t_s)}")
    txt.set_color(COLOR.get(fl, "black"))


def resumen():
    if len(t_s) < 2:
        print("sin tramas PMU")
        return
    dt = [b - a for a, b in zip(t_s, t_s[1:])]
    periodo = sorted(dt)[len(dt) // 2]
    grandes = sum(1 for d in dt if d > 2.5 * periodo)
    print(f"tramas: {len(t_s)} en {t_s[-1] - t_s[0]:.1f} s -> {len(t_s) / (t_s[-1] - t_s[0]):.1f}/s "
          f"(periodo mediano {periodo * 1e3:.1f} ms); huecos > 2,5 periodos: {grandes}; "
          f"mayor intervalo {max(dt) * 1e3:.0f} ms; banderas: {dict(conteo)}")


def main():
    t_fin = time.time() + args.duration if args.duration and not args.replay else None
    ultimo = 0.0
    try:
        for t, linea in fuente():
            if linea is not None and parse(linea, t):
                pass
            ahora = time.time()
            if ahora - ultimo > 0.2 and not (args.replay or headless):
                refresca()
                plt.pause(0.001)
                ultimo = ahora
                if not plt.fignum_exists(fig.number):
                    break
            if t_fin and ahora > t_fin:
                break
    except KeyboardInterrupt:
        pass
    refresca()
    resumen()
    if args.save:
        fig.savefig(args.save, dpi=110)
        print("figura:", args.save)


if __name__ == "__main__":
    if not headless:
        plt.ion()
        plt.show(block=False)
    main()
