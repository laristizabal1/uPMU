"""T4.1: genera los vectores de prueba en data/vectors/ a partir de ref/simulate_chain.py (solo lectura).

Por cada red (Colombia 60 Hz / Chile 50 Hz) y cada escenario de ref (nominal, V 80 %/I 10 %, V 120 %/I 200 %,
f0 +-2 Hz, f0 +-5 Hz) escribe:
  vec_<red>_<escenario>.bin   codigos del ADC a 60 kS/s, uint16 LE intercalados (V, I), n_in muestras
  vec_<red>_<escenario>.json  metadatos, estadistica y salida esperada de la referencia
Los codigos replican las lineas de `acquire()` (ruido de 1,5 LSB rms incluido) y se verifica que, con la misma
semilla, el CIC de ref los reproduce exactamente. La salida esperada sale de `measure()` de ref.

Uso: python tools/gen_vectors.py
"""
import json
import pathlib
import sys
import zlib

import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ref"))
import params as P            # noqa: E402
import simulate_chain as S    # noqa: E402

SALIDA = RAIZ / "data" / "vectors"
SALIDA.mkdir(parents=True, exist_ok=True)
SEMILLA = 20261011
ESCENARIOS = {"nominal": "nominal", "V 80 %, I 10 %": "v80i10", "V 120 %, I 200 %": "v120i200",
              "f0 - 2 Hz": "fm2", "f0 + 2 Hz": "fp2", "f0 - 5 Hz": "fm5", "f0 + 5 Hz": "fp5"}
RED = {"Colombia": "col", "Chile": "chi"}


def codigos(chain, f, Xv, Xi, t0, n_dec):
    """Replica de la generacion de codigos de S.acquire (mismas llamadas al RNG, mismo orden)."""
    n_in = n_dec * P.DECIM + len(S.H_CIC) + 8
    t = t0 + np.arange(n_in) / P.FS
    out = []
    for H, X in ((chain.Hv, Xv), (chain.Hi, Xi)):
        y = np.real(np.sqrt(2) * X * H(f) * np.exp(2j * np.pi * f * t))
        v = P.VCM + y + S.rng.normal(0, 0.002)
        c = v / P.LSB + S.rng.normal(0, S.NOISE_LSB, n_in)
        out.append(np.clip(np.round(c), 0, 2 ** P.NBITS - 1))
    return np.column_stack(out).astype("<u2")


def fasor(z):
    return [float(abs(z)), float(np.degrees(np.angle(z)))]


def main():
    indice = []
    for gi, (grid, g) in enumerate(P.GRIDS.items()):
        S.rng = np.random.default_rng(SEMILLA + gi)
        chain = S.Chain(grid)
        Xv0 = g["Vrms"] * np.exp(1j * np.radians(20.0))
        Xi0 = g["In_rms"] * np.exp(1j * np.radians(20.0 - 30.0))
        S.calibrate(chain, Xv0, Xi0)
        n_dec = int(round(P.CYCLES / chain.f0 * P.FS / P.DECIM))
        for nombre, f, vs, is_ in S.scenarios(grid):
            Xv, Xi = vs * Xv0, is_ * Xi0
            t0 = S.rng.uniform(0.0, 1.0 / f)
            estado = S.rng.bit_generator.state

            # referencia: acquire + measure con el mismo estado del RNG
            t_ref, yv_ref, yi_ref = S.acquire(chain, f, Xv, Xi, t0, n_dec, noise=True)
            S.rng.bit_generator.state = estado
            f_est, xv, xi, tc = S.measure(chain, f, Xv, Xi, t0, noise=True)
            S.rng.bit_generator.state = estado
            cod = codigos(chain, f, Xv, Xi, t0, n_dec)

            # comprobacion: el CIC de ref sobre mis codigos reproduce exactamente a acquire
            for ch, y_ref in ((0, yv_ref), (1, yi_ref)):
                yf = np.convolve(cod[:, ch].astype(float), S.H_CIC)
                ks = np.arange(len(S.H_CIC) - 1, len(yf) - len(S.H_CIC), P.DECIM)[:n_dec]
                assert np.array_equal(yf[ks] * P.LSB, y_ref), (grid, nombre, ch)

            # salida esperada en el dominio del nodo del ADC (antes de H_nominal, CIC y kappa)
            _, cv, _ = S.ipdft_ls(t_ref, yv_ref, chain.f0)
            _, ci, _ = S.ipdft_ls(t_ref, yi_ref, chain.f0)
            verdad_v, verdad_i = S.true_phasor(Xv, f, tc), S.true_phasor(Xi, f, tc)

            # T4.2: salida entera del CIC S = 64 * (H_CIC * c), V e I intercalados, int32 LE
            taps = np.array([1, 3, 6, 10, 12, 12, 10, 6, 3, 1], dtype=np.int64)
            assert np.array_equal(taps, np.rint(S.H_CIC * 64).astype(np.int64))
            Sv, Si = (np.convolve(cod[:, ch].astype(np.int64), taps)[9::4][:n_dec] for ch in (0, 1))
            assert len(Sv) == n_dec
            cic = {"n_out": int(n_dec),
                   "crc32": zlib.crc32(np.column_stack([Sv, Si]).astype("<i4").tobytes()) & 0xFFFFFFFF,
                   "sum_sv": int(Sv.sum()), "sum_si": int(Si.sum()),
                   "first_sv": int(Sv[0]), "first_si": int(Si[0]), "last_sv": int(Sv[-1]), "last_si": int(Si[-1])}
            # y coincide con la referencia (codigos filtrados en volts)
            assert np.array_equal(Sv / 64.0 * P.LSB, yv_ref) and np.array_equal(Si / 64.0 * P.LSB, yi_ref)

            slug = f"vec_{RED[grid]}_{ESCENARIOS[nombre]}"
            payload = cod.tobytes()
            (SALIDA / f"{slug}.bin").write_bytes(payload)
            meta = {
                "name": slug, "grid": grid, "scenario": nombre, "f0_nominal": int(chain.f0),
                "f_true_hz": f, "v_scale": vs, "i_scale": is_, "t0_s": t0, "n_in": int(len(cod)),
                "n_out": int(n_dec), "fs_hz": P.FS, "decim": P.DECIM, "noise_lsb": S.NOISE_LSB,
                "seed": SEMILLA + gi,
                "stats": {"sum_v": int(cod[:, 0].sum()), "sum_i": int(cod[:, 1].sum()),
                          "min_v": int(cod[:, 0].min()), "max_v": int(cod[:, 0].max()),
                          "min_i": int(cod[:, 1].min()), "max_i": int(cod[:, 1].max()),
                          "crc32": zlib.crc32(payload) & 0xFFFFFFFF},
                "ref": {
                    "f_hz": float(f_est), "t_center_s": float(tc),
                    "node_v_rms": fasor(cv), "node_i_rms": fasor(ci),      # [modulo V rms, angulo deg] en el nodo
                    "phys_v": fasor(xv), "phys_i": fasor(xi),              # fisicos (H_nominal, CIC y kappa aplicados)
                    "true_v": fasor(verdad_v), "true_i": fasor(verdad_i),
                    "tve_v_pct": S.tve(xv, verdad_v), "tve_i_pct": S.tve(xi, verdad_i),
                },
                "cic": cic,
                "kappa_v": [chain.kappa_v.real, chain.kappa_v.imag],
                "kappa_i": [chain.kappa_i.real, chain.kappa_i.imag],
            }
            (SALIDA / f"{slug}.json").write_text(json.dumps(meta, indent=1))
            indice.append(slug)
            print(f"{slug:20s} f0={chain.f0:g} f={f:5.1f} n_in={len(cod)} f_est={f_est:8.4f} "
                  f"TVE_V={meta['ref']['tve_v_pct']:.4f} % TVE_I={meta['ref']['tve_i_pct']:.4f} %")
    (SALIDA / "index.json").write_text(json.dumps(indice, indent=1))
    print(f"{len(indice)} vectores en {SALIDA}")


if __name__ == "__main__":
    main()
