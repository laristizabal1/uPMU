"""Lector minimo de .raw ASCII de LTspice (-b -ascii).

Devuelve {nombre_variable: np.array}.  Real para .tran/.dc, complejo para .ac.
Con .step devuelve una lista de diccionarios, uno por paso.
"""
import numpy as np


def read(path):
    """Lee un .raw ASCII.  Devuelve lista de dicts (un dict por .step)."""
    with open(path, "r", errors="replace") as fh:
        txt = fh.read()
    head, _, body = txt.partition("Values:\n")
    names, nvar, npts, cplx, offset = [], 0, 0, False, 0.0
    in_vars = False
    for line in head.splitlines():
        s = line.strip()
        if s.startswith("Offset:"):
            # Con .tran ... <Tstart> LTspice guarda el eje relativo y pone el
            # desplazamiento aqui; sin esto los tiempos salen corridos.
            offset = float(s.split(":")[1])
        elif s.startswith("Flags:"):
            cplx = "complex" in s
        elif s.startswith("No. Variables:"):
            nvar = int(s.split(":")[1])
        elif s.startswith("No. Points:"):
            npts = int(s.split(":")[1])
        elif s.startswith("Variables:"):
            in_vars = True
        elif in_vars and s:
            names.append(s.split("\t")[1] if "\t" in s else s.split()[1])

    # Cada punto son nvar lineas: la 1a empieza con el indice del punto.
    toks = [l.strip() for l in body.splitlines() if l.strip()]
    vals = np.empty((npts, nvar), dtype=complex if cplx else float)
    for p in range(npts):
        for v in range(nvar):
            f = toks[p * nvar + v].split("\t")
            s = f[-1]
            vals[p, v] = complex(*map(float, s.split(","))) if cplx else float(s)

    if offset and not cplx:
        vals[:, 0] += offset

    # .step: LTspice concatena los pasos y el eje x se reinicia en cada uno.
    x = vals[:, 0].real
    cuts = [0] + [i for i in range(1, npts) if x[i] < x[i - 1]] + [npts]
    out = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        d = {n: vals[a:b, i] for i, n in enumerate(names)}
        if not cplx:
            d = {k: v.real for k, v in d.items()}
        out.append(d)
    return out


def one(path):
    """Como read() pero exige un solo paso."""
    r = read(path)
    assert len(r) == 1, f"{path}: {len(r)} pasos, se esperaba 1"
    return r[0]


if __name__ == "__main__":   # autocomprobacion: RC de 1er orden conocido
    import subprocess, tempfile, os
    LT = r"C:\Program Files\ADI\LTspice\LTspice.exe"
    d = tempfile.mkdtemp()
    cir = os.path.join(d, "selftest.cir")
    open(cir, "w").write("* selftest\nV1 a 0 SIN(0 1 60) AC 1\nR1 a b 1k\n"
                         "C1 b 0 1u\n.ac list 60\n.save V(b)\n.end\n")
    subprocess.run([LT, "-b", "-ascii", cir], check=True)
    d_ = one(cir[:-4] + ".raw")
    h = d_["V(b)"][0]
    ref = 1 / (1 + 1j * 2 * np.pi * 60 * 1e-6 * 1e3)
    assert abs(h - ref) < 1e-6, (h, ref)
    print("ltspice_raw: OK  (|H|=%.6f, fase=%.4f deg)" % (abs(h), np.degrees(np.angle(h))))
