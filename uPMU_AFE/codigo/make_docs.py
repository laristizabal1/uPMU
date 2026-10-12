# -*- coding: utf-8 -*-
"""Convierte los informes en Markdown a PDF (docs/*.pdf).

    python make_docs.py informe.md [otro.md ...]

Markdown -> HTML con la libreria `markdown`, y HTML -> PDF con Chrome o Edge en
modo headless (los dos vienen con Windows; no hace falta instalar LaTeX ni
pandoc).  Las imagenes referenciadas se resuelven respecto a la raiz del
proyecto, asi que en el .md se pueden citar como figuras/loquesea.png
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

from rutas import DOCS, RAIZ

NAVEGADORES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
       font-size: 9.6pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 19pt; border-bottom: 2px solid #333; padding-bottom: 4px;
     margin: 0 0 14px; }
h2 { font-size: 13.5pt; margin: 20px 0 7px; padding-top: 6px;
     border-top: 1px solid #ccc; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 14px 0 5px; page-break-after: avoid; }
p, li { orphans: 3; widows: 3; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.8pt;
       background: #f3f3f3; padding: 1px 3px; border-radius: 3px; }
pre { background: #f6f6f6; border-left: 3px solid #bbb; padding: 7px 10px;
      overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 9px 0;
        font-size: 8.6pt; page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 3.5px 6px; text-align: left;
         vertical-align: top; }
th { background: #eef2f7; font-weight: 600; }
tr:nth-child(even) td { background: #fafafa; }
blockquote { border-left: 3px solid #d9b36c; background: #fffaf0;
             margin: 9px 0; padding: 6px 12px; }
img { max-width: 100%; }
hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
a { color: #0b57a4; text-decoration: none; }
"""


def navegador():
    for p in NAVEGADORES:
        if Path(p).exists():
            return p
    sys.exit("No encuentro Chrome ni Edge para generar el PDF.")


def a_pdf(md_path, pdf_path=None):
    md_path = Path(md_path)
    pdf_path = Path(pdf_path) if pdf_path else DOCS / (md_path.stem + ".pdf")
    html = markdown.markdown(
        md_path.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc", "sane_lists"])
    doc = ("<!doctype html><html><head><meta charset='utf-8'>"
           "<base href='%s/'><style>%s</style></head><body>%s</body></html>"
           % (RAIZ.as_uri(), CSS, html))

    tmp = Path(tempfile.mkdtemp()) / (md_path.stem + ".html")
    tmp.write_text(doc, encoding="utf-8")
    subprocess.run([navegador(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--print-to-pdf=%s" % pdf_path, tmp.as_uri()],
                   capture_output=True, text=True, timeout=180)
    if not pdf_path.exists():
        sys.exit("No se genero %s" % pdf_path)
    print("  %s  ->  %s (%.0f kB)" % (md_path.name, pdf_path.name,
                                      pdf_path.stat().st_size / 1024))
    return pdf_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for a in sys.argv[1:]:
        a_pdf(a)
