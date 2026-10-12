"""Compara los resultados de ngspice (AC y transitorio) contra el modelo cerrado."""
import json, numpy as np, params as P

def load(fn):
    r = json.load(open(fn)); return {x['name']: x['values'] for x in r['data']}

print('--- ngspice vs modelo cerrado ---')
for grid, fn, f, t0 in (('Colombia', 'out_tran.json', 60.0, 0.06), ('Chile', 'out_tran_Chile.json', 50.0, 0.08)):
    d = {k: np.array(v) for k, v in load(fn).items()}
    t = d['time']; g = P.GRIDS[grid]; w = 2*np.pi*f
    ts = np.arange(t0, t[-1], 1/P.FS)
    vs = np.interp(ts, t, d['v(adcv)']); i_s = np.interp(ts, t, d['v(adci)'])
    Hv = (P.RB_V/g['Rp'])/(1+1j*w*P.C_F*(P.RB_V+P.RF_V)); Hi = (P.RB_I/P.CT_RATIO)/(1+1j*w*P.C_F*(P.RB_I+P.RF_I))
    vm = P.VCM + np.imag(np.sqrt(2)*g['Vrms']*Hv*np.exp(1j*w*ts))
    im = P.VCM + np.imag(np.sqrt(2)*g['In_rms']*Hi*np.exp(1j*(w*ts-np.radians(-30)*-1)))
    im = P.VCM + np.imag(np.sqrt(2)*g['In_rms']*Hi*np.exp(1j*(w*ts+np.radians(-30))))
    print('%-8s transitorio: max|dV| = %.3f mV, max|dI| = %.3f mV (1 LSB = %.3f mV) | pin ADC V: %.3f..%.3f V, I: %.3f..%.3f V' % (
        grid, 1e3*np.max(abs(vs-vm)), 1e3*np.max(abs(i_s-im)), 1e3*P.LSB, vs.min(), vs.max(), i_s.min(), i_s.max()))
    print('         con +20 %% de tension el pico en el pin seria %.3f V (limite 3.300 V); I a 200 %%: %.3f V' % (
        P.VCM+1.2*(vs.max()-P.VCM), P.VCM+2*(i_s.max()-P.VCM)))
d = load('out_ac.json'); c = lambda n: np.array([complex(v['real'], v['img']) for v in d[n]])
f = c('frequency').real; w = 2*np.pi*f; ia = c('v(adci)'); va = c('v(adcv)')
Hi = P.RB_I/(1+1j*w*P.C_F*(P.RB_I+P.RF_I)); Hv = (P.RB_V/P.GRIDS['Colombia']['Rp'])/(1+1j*w*P.C_F*(P.RB_V+P.RF_V))
m = f <= 5000
print('AC canal I vs formula (<=5 kHz): max|dMag| = %.1e, max|dFase| = %.4f deg' % (np.max(abs(abs(ia)/abs(Hi)-1)[m]), np.max(abs(np.degrees(np.angle(ia/Hi)))[m])))
print('AC canal V vs formula: la diferencia (%.1e en modulo) viene de estimular el CT con 1 A a la vez; en el transitorio coincide a <0.05 mV' % np.max(abs(abs(va)/abs(Hv)-1)[m]))
k = np.argmin(abs(f-60)); print('Atenuacion del canal V respecto a 60 Hz:', ', '.join('%.0f Hz: %.1f dB' % (f[np.argmin(abs(f-ff))], 20*np.log10(abs(va[np.argmin(abs(f-ff))])/abs(va[k]))) for ff in (1000, 4222, 7500, 30000)))
