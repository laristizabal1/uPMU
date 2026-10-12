#!/bin/bash
# Regenera netlists, corre ngspice (WASM via node), verifica y corre la cadena completa.
set -e
cd "$(dirname "$0")"
python3 make_netlists.py
( cd ../ngspice_runner
  node run.mjs ../sim/uPMU_AFE_ac.cir ../sim/out_ac.json
  node run.mjs ../sim/uPMU_AFE_tran.cir ../sim/out_tran.json
  node run.mjs ../sim/uPMU_AFE_tran_Chile.cir ../sim/out_tran_Chile.json )
python3 verify_spice.py | tee results_spice.txt
python3 simulate_chain.py | tee results_chain.txt
