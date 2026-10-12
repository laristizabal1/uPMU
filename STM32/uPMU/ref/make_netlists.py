"""Genera los netlists SPICE (compatibles con LTspice y ngspice) desde params.py."""
import sys
from pathlib import Path
import params as P

OUT = Path(__file__).parent


def circuit(grid="Colombia", f=None, vscale=1.0, iscale=1.0, phi_i_deg=-30.0):
    g = P.GRIDS[grid]
    f = f or g["f0"]
    Vpk = 2 ** 0.5 * g["Vrms"] * vscale
    Ipk_sec = 2 ** 0.5 * g["In_rms"] * iscale / P.CT_RATIO
    rp_total = g["Rp"]
    # La fuente de tensión representa la red; el CT del canal V se modela
    # como transformador ideal de corriente 1:1 (F source).
    return f"""* uPMU AFE - {grid} ({f:g} Hz). Valores desde params.py
.param Vpk={Vpk:.6g}
.param Ipk={Ipk_sec:.6g}
.param freq={f:g}
.param phii={phi_i_deg:g}

* --- Alimentacion analogica y punto medio de 1.65 V --------------------
Vdda vdda 0 {P.VDDA}
Rvcm1 vdda vcm {P.R_VCM:g}
Rvcm2 vcm 0 {P.R_VCM:g}
Cvcm1 vcm 0 {P.C_VCM_BULK:g}
Cvcm2 vcm 0 {P.C_VCM_HF:g}

* --- Canal de tension: red -> Rp -> ZMPT101B (1:1) -> burden ---------------
Vmains nL 0 SIN(0 {{Vpk}} {{freq}} 0 0 0) AC 1
Rp nL np {rp_total:g}
Vsp np 0 0
Fv vcm bv Vsp 1
Rbv bv vcm {P.RB_V:g}
Rfv bv nv {P.RF_V:g}
Cfv nv vcm {P.C_F:g}
Rsv nv adcv {P.RS_ADC:g}
Cpv adcv 0 {P.C_ADC_PAR:g}
D1v adcv vdda DCL
D2v 0 adcv DCL

* --- Canal de corriente: SCT013-100 (2000:1) -> burden --------------------
Ict vcm bi SIN(0 {{Ipk}} {{freq}} 0 0 {{phii}}) AC 1
Rbi bi vcm {P.RB_I:g}
Rfi bi ni {P.RF_I:g}
Cfi ni vcm {P.C_F:g}
Rsi ni adci {P.RS_ADC:g}
Cpi adci 0 {P.C_ADC_PAR:g}
D1i adci vdda DCL
D2i 0 adci DCL

.model DCL D(Is=2.5n N=1.75 Rs=0.6 Cjo=4p)
* Tolerancias estrictas: con reltol=1e-3 el solver deja ~2 mV de error numerico (1.2 LSB)
.options reltol=1e-6 vntol=1e-9 abstol=1e-12
"""


def write(name, body):
    (OUT / name).write_text(body)


if __name__ == "__main__":
    base = circuit("Colombia")
    write("uPMU_AFE_ac.cir", base + ".ac dec 40 1 200k\n.end\n")
    write("uPMU_AFE_tran.cir", base +
          ".tran 2u 100m 0 2u\n.end\n")
    # Version para LTspice (contiene ambos analisis comentados)
    write("uPMU_AFE_LTspice.cir", base +
          "\n* Descomenta UNA de las dos lineas:\n.tran 0 100m 0 2u\n*.ac dec 40 1 200k\n.end\n")
    for grid in ("Chile",):
        write(f"uPMU_AFE_tran_{grid}.cir", circuit(grid) + ".tran 2u 120m 0 2u\n.end\n")
    print("netlists escritos en", OUT)
