# -*- coding: utf-8 -*-
"""Genera uPMU_AFE.asc: el mismo circuito, pero dibujado para abrirlo en LTspice.

    python make_asc.py          # genera y verifica contra el netlist de referencia

La verificacion no es opcional: se le pide a LTspice que extraiga el netlist del
esquematico (-netlist) y se compara con uPMU_AFE_tran.cir.  Si una coordenada de
pin esta mal, el nodo sale distinto y la comprobacion falla.
"""
import os
import re
import subprocess
import sys

import params as P
from rutas import NETLISTS

# Pines de cada simbolo, leidos de lib/sym/*.asy de LTspice.
PINES = {
    "res":     [(16, 16), (16, 96)],
    "cap":     [(16, 0), (16, 64)],
    "ind":     [(16, 16), (16, 96)],
    "voltage": [(0, 16), (0, 96)],
    "current": [(0, 0), (0, 80)],
    "diode":   [(16, 0), (16, 64)],   # pin 1 = anodo
    "f":       [(0, 0), (0, 80)],
}


def _rot(px, py, r):
    return {"R0": (px, py), "R90": (-py, px),
            "R180": (-px, -py), "R270": (py, -px)}[r]


class Asc:
    def __init__(self, ancho=2048, alto=1400):
        self.L = ["Version 4", "SHEET 1 %d %d" % (ancho, alto)]

    def sym(self, kind, x, y, name, value=None, rot="R0", extra=()):
        """Coloca un simbolo y devuelve las coordenadas absolutas de sus pines."""
        self.L.append("SYMBOL %s %d %d %s" % (kind, x, y, rot))
        self.L.append("SYMATTR InstName %s" % name)
        if value is not None:
            self.L.append("SYMATTR Value %s" % value)
        for a, v in extra:
            self.L.append("SYMATTR %s %s" % (a, v))
        out = []
        for px, py in PINES[kind]:
            rx, ry = _rot(px, py, rot)
            out.append((x + rx, y + ry))
        return out

    def wire(self, x1, y1, x2, y2):
        self.L.append("WIRE %d %d %d %d" % (x1, y1, x2, y2))

    def flag(self, x, y, name):
        self.L.append("FLAG %d %d %s" % (x, y, name))

    def stub(self, x, y, name, dy=-32):
        """Etiqueta de red colgada de un punto del cable."""
        self.wire(x, y, x, y + dy)
        self.flag(x, y + dy, name)

    def directive(self, x, y, txt):
        self.L.append("TEXT %d %d Left 2 !%s" % (x, y, txt))

    def comment(self, x, y, txt):
        self.L.append("TEXT %d %d Left 2 ;%s" % (x, y, txt))

    def write(self, path):
        path.write_text("\n".join(self.L) + "\n", encoding="utf-8")


def construir(grid="Colombia"):
    g = P.GRIDS[grid]
    f0 = g["f0"]
    Vpk = 2 ** 0.5 * g["Vrms"]
    Ipk = 2 ** 0.5 * g["In_rms"] / P.CT_RATIO
    a = Asc()

    def canal(y, pre, rb, rf, rw, lm, fuente):
        """Dibuja un canal completo en la fila y.  Devuelve nada."""
        # --- nodo del secundario: fuente ideal -> Lm -> Rw -> burden -> RC -> pin
        if fuente == "F":
            # Fv vcm nsv Vsp 1 : pin1 = vcm (arriba), pin2 = nsv (abajo)
            p = a.sym("f", 256, y - 80, "F" + pre, "Vsp 1")
            a.wire(256, p[0][1], 256, p[0][1] - 32)
            a.flag(256, p[0][1] - 32, "vcm")
        else:
            # Ict vcm nsi : pin1 = vcm, pin2 = nsi
            p = a.sym("current", 256, y - 80, "Ict",
                      "SIN(0 %.6g %g 0 0 -30)" % (Ipk, f0),
                      extra=[("Value2", "AC %.6g" % (g["In_rms"] / P.CT_RATIO))])
            a.wire(256, p[0][1], 256, p[0][1] - 32)
            a.flag(256, p[0][1] - 32, "vcm")
        a.wire(256, y, 352, y)
        a.wire(352, y, 400, y)
        a.stub(352, y, "ns" + pre)

        # Lm: del nodo del secundario al riel vcm (hacia abajo)
        pl = a.sym("ind", 384, y - 16, "Lm" + pre, "%.6g" % lm)
        a.wire(pl[1][0], pl[1][1], pl[1][0], pl[1][1] + 32)
        a.flag(pl[1][0], pl[1][1] + 32, "vcm")

        # Rw en serie (horizontal, R90: pin1 a la derecha, pin2 a la izquierda)
        a.sym("res", 496, y - 16, "Rw" + pre, "%.6g" % rw, rot="R90")
        a.wire(480, y, 560, y)
        a.wire(560, y, 608, y)
        a.wire(608, y, 640, y)
        a.stub(608, y, "b" + pre)

        # burden al riel vcm
        pb = a.sym("res", 544, y - 16, "Rb" + pre, "%.6g" % rb)
        a.wire(pb[1][0], pb[1][1], pb[1][0], pb[1][1] + 32)
        a.flag(pb[1][0], pb[1][1] + 32, "vcm")

        # Rf en serie
        a.sym("res", 736, y - 16, "Rf" + pre, "%.6g" % rf, rot="R90")
        a.wire(720, y, 800, y)
        a.wire(800, y, 848, y)
        a.wire(848, y, 880, y)
        a.stub(848, y, "n" + pre)

        # Cf al riel vcm
        pc = a.sym("cap", 784, y, "Cf" + pre, "%.6g" % P.C_F)
        a.wire(pc[1][0], pc[1][1], pc[1][0], pc[1][1] + 32)
        a.flag(pc[1][0], pc[1][1] + 32, "vcm")

        # Rs hasta el pin
        a.sym("res", 976, y - 16, "Rs" + pre, "%.6g" % P.RS_ADC, rot="R90")
        a.wire(960, y, 1040, y)
        a.wire(1040, y, 1120, y)
        a.wire(1120, y, 1200, y)
        a.wire(1200, y, 1280, y)
        a.stub(1120, y, "adc" + pre)

        # parasita del pin a masa
        pp = a.sym("cap", 1024, y, "Cp" + pre, "%.6g" % P.C_ADC_PAR)
        a.wire(pp[1][0], pp[1][1], pp[1][0], pp[1][1] + 32)
        a.flag(pp[1][0], pp[1][1] + 32, "0")

        # D1: anodo = pin del ADC, catodo = vdda  (R180 deja el catodo arriba)
        pd = a.sym("diode", 1216, y - 64, "D1" + pre, "D1N4148", rot="R180")
        a.wire(1200, pd[0][1], 1200, y)
        a.wire(1200, pd[1][1], 1200, pd[1][1] - 32)
        a.flag(1200, pd[1][1] - 32, "vdda")

        # D2: anodo = masa, catodo = pin del ADC
        pe = a.sym("diode", 1296, y + 144, "D2" + pre, "D1N4148", rot="R180")
        a.wire(1280, pe[1][1], 1280, y)
        a.wire(1280, pe[0][1], 1280, pe[0][1] + 32)
        a.flag(1280, pe[0][1] + 32, "0")

    YV, YI = 320, 880

    # ---- primario del canal de tension: red -> Rp -> amperimetro ------------
    pv = a.sym("voltage", 48, 544, "Vmains",
               "SIN(0 %.6g %g 0 0 0)" % (Vpk, f0),
               extra=[("Value2", "AC %g" % g["Vrms"])])
    a.wire(48, pv[0][1], 48, 528)
    a.wire(48, 528, 48, 528)
    a.wire(48, pv[1][1], 48, 672)
    a.flag(48, 672, "0")
    a.sym("res", 144, 512, "Rp", "%.6g" % (g["Rp"] + P.R_PRI_ZMPT), rot="R90")
    a.wire(48, 528, 48, pv[0][1])
    a.flag(48, 528, "nL")
    ps = a.sym("voltage", 128, 544, "Vsp", "0")
    a.wire(128, 528, 128, ps[0][1])
    a.wire(128, ps[1][1], 128, 672)
    a.wire(48, 672, 128, 672)
    a.stub(128, 560, "np", dy=0)

    canal(YV, "v", P.RB_V, P.RF_V, P.RW_V, P.LM_V, "F")
    canal(YI, "i", P.RB_I, P.RF_I, P.RW_I, P.LM_I, "I")

    # ---- alimentacion y punto medio ----------------------------------------
    pd = a.sym("voltage", 1552, 112, "Vdda", "%g" % P.VDDA)
    a.wire(1552, pd[0][1], 1552, 96)
    a.flag(1552, 96, "vdda")
    a.wire(1552, pd[1][1], 1552, 240)
    a.flag(1552, 240, "0")

    p1 = a.sym("res", 1680, 96, "Rvcm1", "%.6g" % P.R_VCM)
    a.wire(1696, p1[0][1], 1696, 96)
    a.flag(1696, 96, "vdda")
    p2 = a.sym("res", 1680, 272, "Rvcm2", "%.6g" % P.R_VCM)
    a.wire(1696, p1[1][1], 1696, p2[0][1])
    a.wire(1696, p2[1][1], 1696, 416)
    a.flag(1696, 416, "0")
    a.stub(1696, 240, "vcm", dy=0)

    for i, (cx, val, nom) in enumerate(((1808, P.C_VCM_BULK, "Cvcm1"),
                                        (1904, P.C_VCM_HF, "Cvcm2"))):
        pc = a.sym("cap", cx - 16, 240, nom, "%.6g" % val)
        a.wire(pc[0][0], pc[0][1], 1696, 240)
        a.wire(pc[1][0], pc[1][1], pc[1][0], pc[1][1] + 32)
        a.flag(pc[1][0], pc[1][1] + 32, "0")

    # ---- directivas ---------------------------------------------------------
    a.directive(48, 1180, ".model D1N4148 D(Is=4.352n N=1.906 Rs=.6458 Ikf=44.17m "
                          "Xti=3 Eg=1.11 Cjo=4p M=.3333 Vj=.5 Fc=.5 Isr=1.21n Nr=2 "
                          "Bv=110 Ibv=1u Tt=11.54n)")
    a.directive(48, 1220, ".options reltol=1e-6 vntol=1e-9 abstol=1e-12")
    a.directive(48, 1260, ".tran 2u 5.1 5 2u")
    a.comment(48, 1100,
              "uPMU AFE - " + grid + " (%g Hz). Generado por codigo/make_asc.py desde params.py." % f0)
    a.comment(48, 1130,
              "OJO: el .tran simula 5 s y guarda los ultimos 100 ms. El magnetizante de los "
              "transformadores tarda segundos en asentarse (ver docs/RESULTADOS_LTspice.pdf).")
    return a


def componentes(texto):
    """{nombre: (nodo1, nodo2)} de un netlist SPICE, en minusculas."""
    out = {}
    for ln in texto.splitlines():
        ln = ln.strip()
        if not ln or ln[0] in "*.;":
            continue
        t = ln.split()
        if len(t) >= 3 and t[0][0].lower() in "rcldfiv":
            out[t[0].lower()] = (t[1].lower(), t[2].lower())
    return out


def verificar(asc_path, ref_path):
    """Pide a LTspice el netlist del .asc y lo compara con el .cir de referencia."""
    lt = os.environ.get("LTSPICE", r"C:\Program Files\ADI\LTspice\LTspice.exe")
    if not os.path.exists(lt):
        print("  (sin LTspice: no se pudo verificar el .asc)")
        return True
    subprocess.run([lt, "-netlist", str(asc_path)], capture_output=True, text=True)
    net = asc_path.with_suffix(".net")
    if not net.exists():
        sys.exit("LTspice no genero el netlist de %s" % asc_path.name)
    a = componentes(net.read_text(errors="replace"))
    b = componentes(ref_path.read_text(encoding="utf-8"))
    # LTspice renombra los nodos sin etiqueta como N00x: solo se comparan los
    # componentes y la relacion entre ellos a traves de los nodos con nombre.
    fallos = []
    for nombre, nodos in sorted(b.items()):
        if nombre not in a:
            fallos.append("falta %s en el .asc" % nombre)
            continue
        # R, C y L son simetricos: el orden de los nodos da igual.  En V, I, D
        # y F la polaridad SI importa, asi que ahi se compara en orden.
        igual = (set(a[nombre]) == set(nodos) if nombre[0] in "rcl"
                 else a[nombre] == nodos)
        if not igual:
            fallos.append("%s: .asc %s  vs  .cir %s" % (nombre, a[nombre], nodos))
    for nombre in sorted(set(a) - set(b)):
        fallos.append("sobra %s en el .asc" % nombre)
    if fallos:
        print("  VERIFICACION FALLIDA (%d):" % len(fallos))
        for f in fallos:
            print("   -", f)
        return False
    print("  verificado: los %d componentes del .asc tienen los mismos nodos que %s"
          % (len(b), ref_path.name))
    return True


if __name__ == "__main__":
    p = NETLISTS / "uPMU_AFE.asc"
    construir("Colombia").write(p)
    print("esquematico de LTspice escrito en", p)
    # Solo se sale con error si falla: este modulo tambien se ejecuta desde
    # run_ltspice.py con runpy, y un sys.exit(0) ahi abortaria la corrida.
    if not verificar(p, NETLISTS / "uPMU_AFE_tran.cir"):
        sys.exit(1)
