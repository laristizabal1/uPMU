# -*- coding: utf-8 -*-
"""Genera los netlists de LTspice desde params.py.

Correcciones frente a la versión anterior (ver sim/RESULTADOS_LTspice.md):
  * .ac excitaba las dos fuentes a la vez y con AC 1 = 1 A en el secundario del
    CT (= 2000 A primarios): contaminaba el canal V un 0,39 % en módulo.  Ahora
    cada canal se excita por separado y con su unidad física correcta.
  * Los transformadores eran ideales: no había error de fase del sensor.  Ahora
    llevan magnetizante Lm + devanado Rw (Lm derivada de la hoja de datos).
  * El 1N4148 era un .model de 4 parámetros hecho a mano.  Ahora es el modelo
    estándar (Philips) con Bv, Isr/Nr, Vj, M y Tt.
  * Faltaba la red de muestreo del ADC: se agrega interruptor + C_SH.
  * Se agregan .meas y una corrida Monte Carlo con mc() (solo LTspice).
"""
import params as P
from rutas import NETLISTS as OUT

# Modelo estándar del 1N4148 (Philips/NXP), el mismo que distribuye LTspice.
D_MODEL = (".model D1N4148 D(Is=4.352n N=1.906 Rs=.6458 Ikf=44.17m Xti=3 Eg=1.11 "
           "Cjo=4p M=.3333 Vj=.5 Fc=.5 Isr=1.21n Nr=2 Bv=110 Ibv=1u Tt=11.54n)")


def _r(val, mc):
    """Resistencia: nominal, o mc(val, 1 %) para Monte Carlo (solo LTspice)."""
    return "{mc(%.6g,0.01)}" % val if mc else "%.6g" % val


def _c(val, mc):
    """Condensador: nominal, o mc(val, 5 %)."""
    return "{mc(%.6g,0.05)}" % val if mc else "%.6g" % val


def body(grid="Colombia", f=None, vscale=1.0, iscale=1.0, phi_i_deg=-30.0,
         ideal_ct=False, ac_v=0.0, ac_i=0.0, mc=False, adc_sh=False):
    """Cuerpo del netlist.

    ac_v      magnitud AC de la fuente de red [V].  1 -> V(adcv) = H en V/V.
    ac_i      magnitud AC de la corriente PRIMARIA [A].  La fuente inyecta
              ac_i/CT_RATIO en el secundario, así que V(adci) sale en V/A
              primario, igual que la Hi() de simulate_chain.py.
    ideal_ct  True reproduce el modelo viejo (CT ideal, sin error de fase).
    """
    g = P.GRIDS[grid]
    f = f or g["f0"]
    Vpk = 2 ** 0.5 * g["Vrms"] * vscale
    Ipk_sec = 2 ** 0.5 * g["In_rms"] * iscale / P.CT_RATIO
    rp_total = g["Rp"] + P.R_PRI_ZMPT        # el devanado primario suma a Rp
    ac_i_sec = ac_i / P.CT_RATIO
    ideal_txt = " - CT ideal" if ideal_ct else ""

    s = f"""* uPMU AFE - {grid} ({f:g} Hz){ideal_txt}. Valores desde params.py
.param Vpk={Vpk:.6g}
.param Ipk={Ipk_sec:.6g}
.param freq={f:g}
.param phii={phi_i_deg:g}

* --- Alimentacion analogica y punto medio de 1.65 V ----------------------
Vdda vdda 0 {P.VDDA}
Rvcm1 vdda vcm {_r(P.R_VCM, mc)}
Rvcm2 vcm 0 {_r(P.R_VCM, mc)}
Cvcm1 vcm 0 {P.C_VCM_BULK:g}
Cvcm2 vcm 0 {P.C_VCM_HF:g}

* --- Canal de tension: red -> Rp -> ZMPT101B -> burden -------------------
Vmains nL 0 SIN(0 {{Vpk}} {{freq}} 0 0 0) AC {ac_v:g}
Rp nL np {_r(rp_total, mc)}
Vsp np 0 0
"""
    # Secundario del ZMPT101B: fuente ideal 1:1, magnetizante Lm, devanado Rw.
    if ideal_ct:
        s += "Fv vcm bv Vsp 1\n"
    else:
        s += f"Fv vcm nsv Vsp 1\nLmv nsv vcm {P.LM_V:.6g}\nRwv nsv bv {P.RW_V:.6g}\n"

    s += f"""Rbv bv vcm {_r(P.RB_V, mc)}
Rfv bv nv {_r(P.RF_V, mc)}
Cfv nv vcm {_c(P.C_F, mc)}
Rsv nv adcv {_r(P.RS_ADC, mc)}
Cpv adcv 0 {P.C_ADC_PAR:g}
D1v adcv vdda D1N4148
D2v 0 adcv D1N4148

* --- Canal de corriente: SCT-013 (2000:1) -> burden ----------------------
Ict vcm {'bi' if ideal_ct else 'nsi'} SIN(0 {{Ipk}} {{freq}} 0 0 {{phii}}) AC {ac_i_sec:.6g}
"""
    if not ideal_ct:
        s += f"Lmi nsi vcm {P.LM_I:.6g}\nRwi nsi bi {P.RW_I:.6g}\n"

    s += f"""Rbi bi vcm {_r(P.RB_I, mc)}
Rfi bi ni {_r(P.RF_I, mc)}
Cfi ni vcm {_c(P.C_F, mc)}
Rsi ni adci {_r(P.RS_ADC, mc)}
Cpi adci 0 {P.C_ADC_PAR:g}
D1i adci vdda D1N4148
D2i 0 adci D1N4148

{D_MODEL}
"""
    if adc_sh:
        # Muestreo y retencion del ADC: Ron = R_ADC, ventana = T_SAMPLE a FS.
        s += f"""
* --- Red de muestreo del ADC (STM32F303: 61,5 ciclos a 15 MHz) -----------
.model SWADC SW(Ron={P.R_ADC:g} Roff=1G Vt=0.5 Vh=0)
Vsmp nsmp 0 PULSE(0 1 {0.5 / P.FS:g} 1n 1n {P.T_SAMPLE:g} {1 / P.FS:g})
Ssv adcv shv nsmp 0 SWADC
Cshv shv 0 {P.C_ADC_SH:g}
Ssi adci shi nsmp 0 SWADC
Cshi shi 0 {P.C_ADC_SH:g}
"""
    # reltol/vntol/abstol: con el reltol de fabrica el solver deja ~2 mV
    # (2,5 LSB) de error numerico.
    s += ".options reltol=1e-6 vntol=1e-9 abstol=1e-12\n"
    return s


AC_SWEEP = ".ac dec 100 10 100k\n"          # el enunciado pide 10 Hz .. 100 kHz
SAVE_AC = ".save V(adcv) V(adci) V(vcm)\n"
SAVE_TR = ".save V(adcv) V(adci) V(vcm) I(D1v) I(D2v) I(D1i) I(D2i)\n"
# Asentamiento antes de la ventana guardada.  Hay DOS transitorios lentos:
#   1) la continua del magnetizante, tau = Lm/(Rw+Rb) = 221 ms (V) y 182 ms (I);
#   2) la resonancia de Lm con los 10 uF de VCM: 4,3 Hz en el canal V y
#      16,7 Hz en el canal I, que decae con tau = 2L/R = 0,44 s y 0,37 s.
# Con 2 s quedaban 1,7 mV (2 LSB) de offset en el canal I a 50 Hz; con 5 s
# baja a 0,008 mV.  Comprobado tambien al quitar Cvcm1, que elimina el modo.
SETTLE = 5.0
TRAN_MEAS = (".meas tran vmax MAX V(adcv)\n.meas tran vmin MIN V(adcv)\n"
             ".meas tran imax MAX V(adci)\n.meas tran imin MIN V(adci)\n"
             ".meas tran id1v MAX abs(I(D1v))\n.meas tran id2v MAX abs(I(D2v))\n"
             ".meas tran id1i MAX abs(I(D1i))\n.meas tran id2i MAX abs(I(D2i))\n")


def ac_meas(node, tag):
    """.meas de modulo y fase a 50 y 60 Hz."""
    return "".join(
        ".meas ac mag{t}{f} FIND mag(V({n})) AT {f}\n"
        ".meas ac ph{t}{f} FIND ph(V({n})) AT {f}\n".format(t=tag, n=node, f=fr)
        for fr in (50, 60))


def write(name, text):
    (OUT / name).write_text(text, encoding="utf-8")
    return name


if __name__ == "__main__":
    n = []
    # --- AC: un canal a la vez, con su unidad fisica ----------------------
    for tag, kw in (("V", dict(ac_v=1.0)), ("I", dict(ac_i=1.0))):
        node = "adcv" if tag == "V" else "adci"
        n.append(write("uPMU_AFE_ac_%s.cir" % tag,
                       body(**kw) + SAVE_AC + AC_SWEEP + ac_meas(node, tag) + ".end\n"))
        # misma corrida con el CT ideal, para el antes/despues
        n.append(write("uPMU_AFE_ac_ideal_%s.cir" % tag,
                       body(ideal_ct=True, **kw) + SAVE_AC + AC_SWEEP + ".end\n"))

    # --- Transitorio: nominal y sobrecarga (V 120 %, I 200 %) -------------
    # El magnetizante del CT trae un transitorio de continua con
    # tau = Lm/(Rw+Rb) = 221 ms (canal V) y 182 ms (canal I): hay que simular
    # ~1 s y guardar solo el final, o los picos salen falseados.
    for grid, win in (("Colombia", 0.100), ("Chile", 0.120)):
        suf = "" if grid == "Colombia" else "_" + grid
        tr = ".tran 2u %g %g 2u\n" % (SETTLE + win, SETTLE)
        n.append(write("uPMU_AFE_tran%s.cir" % suf,
                       body(grid) + SAVE_TR + tr + TRAN_MEAS + ".end\n"))
        n.append(write("uPMU_AFE_tran%s_ovl.cir" % suf,
                       body(grid, vscale=1.2, iscale=2.0) + SAVE_TR
                       + tr + TRAN_MEAS + ".end\n"))

    # --- Clamps: sobretension grande, los 1N4148 deben limitar ------------
    n.append(write("uPMU_AFE_clamp.cir",
                   body("Colombia", vscale=4.0, iscale=6.0) + SAVE_TR
                   + ".tran 2u %g %g 2u\n" % (SETTLE + 0.05, SETTLE)
                   + TRAN_MEAS + ".end\n"))

    # --- Muestreo del ADC: asentamiento a 12 bits -------------------------
    n.append(write("uPMU_AFE_adcsh.cir",
                   body("Colombia", adc_sh=True)
                   + ".save V(adcv) V(shv) V(adci) V(shi) V(nsmp)\n"
                   # Sin asentar: el error de muestreo es V(shv) - V(adcv),
                   # un efecto local de ns; el transitorio de continua del
                   # magnetizante lo desplaza a los dos por igual y no influye.
                   # Con paso de 2 ns no se puede simular 1 s.
                   + ".tran 2n 2m 1m 2n\n.end\n"))

    # --- Monte Carlo con mc(): R al 1 %, C al 5 % -------------------------
    # Las dos fuentes activas con su nivel nominal: el acoplamiento por el
    # nodo vcm queda a escala real.  200 corridas.
    for grid in P.GRIDS:
        g = P.GRIDS[grid]
        f0 = g["f0"]
        n.append(write("uPMU_AFE_mc_%s.cir" % grid,
                       body(grid, ac_v=g["Vrms"], ac_i=g["In_rms"], mc=True)
                       + ".param run=1\n.step param run 1 200 1\n" + SAVE_AC
                       # dos frecuencias: ademas de medir en 50 y 60, el salto
                       # 60 -> 50 es lo que permite separar los .step al leer
                       # el .raw (con un solo punto no hay como cortarlos).
                       + ".ac list 50 60\n"
                       + ".meas ac magv FIND mag(V(adcv)) AT %g\n" % f0
                       + ".meas ac phv FIND ph(V(adcv)) AT %g\n" % f0
                       + ".meas ac magi FIND mag(V(adci)) AT %g\n" % f0
                       + ".meas ac phi FIND ph(V(adci)) AT %g\n" % f0 + ".end\n"))

    # --- Netlist para abrir a mano en LTspice -----------------------------
    gc = P.GRIDS["Colombia"]
    n.append(write("uPMU_AFE_LTspice.cir",
                   body("Colombia", ac_v=gc["Vrms"], ac_i=gc["In_rms"])
                   + "\n* Descomenta UNA de las dos lineas:\n"
                   + ".tran 2u 100m 0 2u\n*" + AC_SWEEP + ".end\n"))

    print("netlists escritos en", OUT)
    for x in n:
        print("  ", x)
