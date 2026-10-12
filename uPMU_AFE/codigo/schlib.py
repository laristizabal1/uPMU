"""Mini libreria de dibujo de esquematicos sobre matplotlib (coordenadas libres)."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Circle, Rectangle, Arc

LW = 1.7
INK = "#111111"
NET = "#0b57a4"      # color de etiquetas de red
NOTE = "#444444"


class Sheet:
    def __init__(self, w, h, scale=0.5):
        self.fig = plt.figure(figsize=(w * scale, h * scale))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(0, h)
        self.ax.set_aspect("equal")
        self.ax.axis("off")
        self.w, self.h = w, h

    # -- basicos ---------------------------------------------------------
    def wire(self, *pts, lw=LW, color=INK):
        p = np.array(pts, float)
        self.ax.plot(p[:, 0], p[:, 1], color=color, lw=lw, solid_capstyle="round", zorder=2)

    def dot(self, x, y, r=0.16):
        self.ax.add_patch(Circle((x, y), r, color=INK, zorder=5))

    def text(self, x, y, s, size=9, ha="center", va="center", color=INK, weight="normal", rot=0, style="normal"):
        self.ax.text(x, y, s, fontsize=size, ha=ha, va=va, color=color, weight=weight, rotation=rot,
                     fontstyle=style, zorder=6, linespacing=1.25)

    def box(self, x, y, w, h, fc="none", ec=INK, lw=1.6, ls="-", z=1):
        self.ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, ls=ls, zorder=z))

    # -- geometria de componentes con dos terminales ---------------------
    def _axis(self, p0, p1):
        p0, p1 = np.array(p0, float), np.array(p1, float)
        d = p1 - p0
        L = np.hypot(*d)
        u = d / L
        n = np.array([-u[1], u[0]])
        return p0, p1, L, u, n

    def _label(self, c, n, lines, side, off, size=9, ha="center"):
        pos = c + n * side * off
        va = "center"
        if abs(n[0]) > 0.5:
            ha = "left" if n[0] * side > 0 else "right"
        self.text(pos[0], pos[1], lines, size=size, ha=ha, va=va)

    def res(self, p0, p1, label="", side=1, off=0.95, body=2.0, w=0.75, size=9):
        p0, p1, L, u, n = self._axis(p0, p1)
        c = (p0 + p1) / 2
        a, b = c - u * body / 2, c + u * body / 2
        self.wire(p0, a)
        self.wire(b, p1)
        poly = [a + n * w / 2, b + n * w / 2, b - n * w / 2, a - n * w / 2]
        self.ax.add_patch(Polygon(poly, closed=True, fc="white", ec=INK, lw=LW, zorder=3))
        if label:
            self._label(c, n, label, side, off if abs(n[0]) < 0.5 else off + 0.1, size)

    def cap(self, p0, p1, label="", side=1, off=0.95, gap=0.42, plate=1.3, size=9):
        p0, p1, L, u, n = self._axis(p0, p1)
        c = (p0 + p1) / 2
        a, b = c - u * gap / 2, c + u * gap / 2
        self.wire(p0, a)
        self.wire(b, p1)
        for q in (a, b):
            self.wire(q + n * plate / 2, q - n * plate / 2, lw=LW + 0.6)
        if label:
            self._label(c, n, label, side, off, size)

    def diode(self, p0, p1, label="", side=1, off=0.95, size=0.9, fsize=9):
        """Anodo en p0, catodo en p1."""
        p0, p1, L, u, n = self._axis(p0, p1)
        c = (p0 + p1) / 2
        tip, base = c + u * size / 2, c - u * size / 2
        self.wire(p0, base)
        self.wire(tip, p1)
        self.ax.add_patch(Polygon([base + n * size / 2, base - n * size / 2, tip], closed=True, fc="white", ec=INK, lw=LW, zorder=3))
        self.wire(tip + n * size / 2, tip - n * size / 2)
        if label:
            self._label(c, n, label, side, off, fsize)

    def fuse(self, p0, p1, label="", side=1, off=0.95, body=2.2, w=0.7, size=9):
        p0, p1, L, u, n = self._axis(p0, p1)
        c = (p0 + p1) / 2
        a, b = c - u * body / 2, c + u * body / 2
        self.wire(p0, p1)
        poly = [a + n * w / 2, b + n * w / 2, b - n * w / 2, a - n * w / 2]
        self.ax.add_patch(Polygon(poly, closed=True, fc="white", ec=INK, lw=LW, zorder=3))
        self.wire(a, b, lw=1.0)
        if label:
            self._label(c, n, label, side, off, size)

    def coil(self, x, y_top, loops=4, d=1.0, bulge=+1, lw=LW):
        """Bobina vertical: arcos que abultan a la derecha (+1) o izquierda (-1). Devuelve (y_top, y_bot)."""
        for k in range(loops):
            yc = y_top - d / 2 - k * d
            th = (270, 90) if bulge > 0 else (90, 270)
            self.ax.add_patch(Arc((x, yc), d, d, theta1=th[0], theta2=th[1], lw=lw, ec=INK, zorder=3))
        return y_top, y_top - loops * d

    def ground(self, x, y, label=None):
        self.wire((x, y), (x, y - 0.5))
        for i, w in enumerate((1.2, 0.8, 0.4)):
            self.wire((x - w / 2, y - 0.5 - i * 0.22), (x + w / 2, y - 0.5 - i * 0.22), lw=1.5)
        if label:
            self.text(x, y - 1.5, label, size=8, color=NET)

    def rail_flag(self, x, y, label):
        """Bandera de alimentacion hacia arriba (termina en y)."""
        self.wire((x, y - 0.5), (x, y))
        self.wire((x - 0.6, y), (x + 0.6, y), lw=2.2)
        self.text(x, y + 0.45, label, size=9, color="#b00020", weight="bold")

    def netlabel(self, x, y, s, ha="left", size=9, dx=0.3, dy=0.0):
        self.text(x + (dx if ha == "left" else -dx), y + dy, s, size=size, ha=ha, color=NET, weight="bold")

    def terminal(self, x, y, label="", ha="right", dx=0.35):
        self.ax.add_patch(Circle((x, y), 0.26, fc="white", ec=INK, lw=LW, zorder=4))
        if label:
            self.text(x + (dx if ha == "left" else -dx) * 1.0, y, label, size=9, ha=ha, weight="bold")

    def save(self, nombre, dpi=170):
        """PNG a figuras/ y PDF a docs/."""
        from rutas import DOCS, FIGURAS
        self.fig.savefig(FIGURAS / (nombre + ".png"), dpi=dpi, facecolor="white")
        self.fig.savefig(DOCS / (nombre + ".pdf"), facecolor="white")
        plt.close(self.fig)
