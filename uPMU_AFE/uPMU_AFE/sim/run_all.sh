#!/bin/bash
# Regenera netlists y corre TODO: LTspice (batch), ngspice (WASM via node),
# la comparacion de tres vias y la cadena completa en Python.
set -e
cd "$(dirname "$0")"

python make_netlists.py

# 1) LTspice: AC, transitorios, clamps, muestreo del ADC y Monte Carlo + PNG
python run_ltspice.py | tee results_ltspice.txt

# 2) ngspice sobre los mismos netlists (no soporta mc() ni .step: sin Monte Carlo)
( cd ../ngspice_runner
  node run.mjs ../sim/uPMU_AFE_tran.cir       ../sim/out_tran.json
  node run.mjs ../sim/uPMU_AFE_tran_Chile.cir ../sim/out_tran_Chile.json )

# 3) ngspice contra el modelo, muestra por muestra
python verify_spice.py | tee results_spice.txt

# 4) Cadena completa: con el firmware de hoy y con la compensacion propuesta.
#    Va ANTES de compare_sims.py, que lee results_chain.json.
python simulate_chain.py           | tee results_chain.txt
python simulate_chain.py --ct-nom  | tee results_chain_ctnom.txt

# 5) LTspice vs ngspice vs modelo cerrado de Python
python compare_sims.py | tee results_compare.txt
