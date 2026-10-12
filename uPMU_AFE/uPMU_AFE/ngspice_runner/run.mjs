// Corre un netlist con ngspice (WASM, eecircuit-engine) y guarda el resultado en JSON.
import { Simulation } from 'eecircuit-engine';
import fs from 'fs';

const [, , netlistPath, outPath] = process.argv;
const sim = new Simulation();
await sim.start();
sim.setNetList(fs.readFileSync(netlistPath, 'utf8'));
const res = await sim.runSim();
fs.writeFileSync(outPath, JSON.stringify(res));
console.log('ok', res.header ?? '', 'vars:', res.variableNames?.length, 'points:', res.numPoints);
