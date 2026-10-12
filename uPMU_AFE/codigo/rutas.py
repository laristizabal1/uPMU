# -*- coding: utf-8 -*-
"""Carpetas del proyecto, para que cada script escriba donde corresponde."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CODIGO = RAIZ / "codigo"
NETLISTS = RAIZ / "netlists"
FIGURAS = RAIZ / "figuras"
RESULTADOS = RAIZ / "resultados"
DOCS = RAIZ / "docs"

for _d in (NETLISTS, FIGURAS, RESULTADOS, DOCS):
    _d.mkdir(exist_ok=True)
