"""T4.5: corre todos los vectores por el Nucleo y compara el TVE del firmware con el de la simulacion de ref.

Para cada vector (tools/send_vector.py -> linea EST del firmware):
  c = mag * e^{j ang}                       fasor rms en el nodo del ADC, en el centro de la ventana
  f_est = (f_V + f_I) / 2                   como measure() de ref
  x = c / (H_nom(f_est) * G_cic(f_est)) * kappa   (cadena fisica de ref, con kappa del JSON)
  TVE = |x - x_verdadero| / |x_verdadero| * 100
y lo compara con el TVE que la simulacion de referencia dio para ese mismo vector (JSON, "ref.tve_*").
Guarda data/t4_5_tve_<fecha>.csv y imprime la tabla.

Uso: python tools/verify_all.py [puerto=COM6]     (numpy lo pide ref/params.py; el envio por serie usa el
python de PlatformIO (pyserial), o el indicado en la variable SERIALPY)
"""
import cmath
import csv
import datetime
import json
import math
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ref"))
import params as P  # noqa: E402

puerto = sys.argv[1] if len(sys.argv) > 1 else "COM6"
LSB = P.LSB


def cic_gain(f):
    x = math.pi * f / P.FS
    return (math.sin(P.DECIM * x) / (P.DECIM * math.sin(x))) ** 3


def h_nom(grid, canal, f):
    w = 2 * math.pi * f
    if canal == "v":
        return (P.RB_V / P.GRIDS[grid]["Rp"]) / (1 + 1j * w * P.C_F * (P.RB_V + P.RF_V))
    return (P.RB_I / P.CT_RATIO) / (1 + 1j * w * P.C_F * (P.RB_I + P.RF_I))


def fasor(mag, ang_deg):
    return mag * cmath.exp(1j * math.radians(ang_deg))


def main():
    py = os.environ.get("SERIALPY", str(pathlib.Path.home() / ".platformio" / "penv" / "Scripts" / "python.exe"))
    filas, peor = [], {"dTVE_V": 0.0, "dTVE_I": 0.0, "f_err_mHz": 0.0, "TVE_V": 0.0, "TVE_I": 0.0}
    print(f"{'vector':18s} {'f ver Hz':>8s} {'f fw Hz':>9s} | {'TVE_V sim':>9s} {'TVE_V fw':>9s} | "
          f"{'TVE_I sim':>9s} {'TVE_I fw':>9s} | {'dTVE_V':>8s} {'dTVE_I':>8s}")
    for j in sorted((RAIZ / "data" / "vectors").glob("vec_*.json")):
        m = json.loads(j.read_text())
        r = subprocess.run([py, str(RAIZ / "tools" / "send_vector.py"), m["name"], puerto],
                           capture_output=True, text=True, timeout=60)
        est = next((l for l in r.stdout.splitlines() if l.startswith("firmware: EST,")), None)
        if r.returncode != 0 or est is None:
            print(f"{m['name']:18s} FALLO del envio:\n{r.stdout}{r.stderr}")
            sys.exit(1)
        fv, fi, mv, av, mi, ai, ciclos = (int(x) for x in est.split(",")[1:8])
        f_est = 0.5 * (fv + fi) * 1e-6
        cv, ci = fasor(mv * 1e-9, av * 1e-6), fasor(mi * 1e-9, ai * 1e-6)
        kv = complex(*m["kappa_v"])
        ki = complex(*m["kappa_i"])
        xv = cv / (h_nom(m["grid"], "v", f_est) * cic_gain(f_est)) * kv
        xi = ci / (h_nom(m["grid"], "i", f_est) * cic_gain(f_est)) * ki
        verd_v = fasor(*m["ref"]["true_v"])
        verd_i = fasor(*m["ref"]["true_i"])
        tve_v = abs(xv - verd_v) / abs(verd_v) * 100
        tve_i = abs(xi - verd_i) / abs(verd_i) * 100
        sv, si = m["ref"]["tve_v_pct"], m["ref"]["tve_i_pct"]
        f_true = m["f_true_hz"]
        e = {"dTVE_V": abs(tve_v - sv), "dTVE_I": abs(tve_i - si), "f_err_mHz": abs(f_est - f_true) * 1e3,
             "TVE_V": tve_v, "TVE_I": tve_i}
        for k, v in e.items():
            peor[k] = max(peor[k], v)
        filas.append([m["name"], m["grid"], f_true, round(f_est, 6), round(m["ref"]["f_hz"], 6), round(sv, 5),
                      round(tve_v, 5), round(si, 5), round(tve_i, 5), round(e["dTVE_V"], 5), round(e["dTVE_I"], 5),
                      ciclos])
        print(f"{m['name']:18s} {f_true:8.1f} {f_est:9.4f} | {sv:9.4f} {tve_v:9.4f} | {si:9.4f} {tve_i:9.4f} | "
              f"{e['dTVE_V']:8.5f} {e['dTVE_I']:8.5f}")
    ruta = RAIZ / "data" / f"t4_5_tve_{datetime.date.today():%Y%m%d}.csv"
    with open(ruta, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vector", "red", "f_verdadera_Hz", "f_firmware_Hz", "f_referencia_Hz", "TVE_V_sim_pct",
                    "TVE_V_fw_pct", "TVE_I_sim_pct", "TVE_I_fw_pct", "dTVE_V_pct", "dTVE_I_pct", "ciclos"])
        w.writerows(filas)
    print(f"\nPEOR: TVE_V fw = {peor['TVE_V']:.4f} %, TVE_I fw = {peor['TVE_I']:.4f} %; "
          f"|TVE fw - TVE sim|: V {peor['dTVE_V']:.5f} %, I {peor['dTVE_I']:.5f} %; "
          f"error de frecuencia vs verdadera {peor['f_err_mHz']:.2f} mHz")
    ok = peor["dTVE_V"] < 0.001 and peor["dTVE_I"] < 0.001
    print("coincide con la simulacion (|dTVE| < 0,001 %):", "SI" if ok else "NO")
    print("log:", ruta)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
