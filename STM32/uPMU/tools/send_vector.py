"""T4.1: envia un vector de data/vectors/ al Nucleo por el puerto serie y recibe el resultado del firmware.

Trama (ver include/vecrx.h): 55 56 | n_in u16 | f0 u8 | flags u8 | n_in*{V u16, I u16} | CRC32 u32.
El firmware responde con una linea `VEC,<estado>,<n_in>,<f0>,<crc>,<sumV>,<sumI>,<minV>,<maxV>,<minI>,<maxI>,...`
que aqui se compara con la estadistica calculada en la PC (data/vectors/<nombre>.json).

Uso: python tools/send_vector.py <nombre|ruta .bin> [puerto=COM6] [--corrupt]
  --corrupt  cambia un byte del payload sin recalcular el CRC (el firmware debe responder CRC).
"""
import json
import pathlib
import struct
import sys
import time
import zlib

import serial

RAIZ = pathlib.Path(__file__).resolve().parent.parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
corromper = "--corrupt" in sys.argv
nombre = args[0]
puerto = args[1] if len(args) > 1 else "COM6"
ruta = pathlib.Path(nombre)
if not ruta.suffix:
    ruta = RAIZ / "data" / "vectors" / f"{nombre}.bin"
meta = json.loads(ruta.with_suffix(".json").read_text())
payload = bytearray(ruta.read_bytes())
n_in = meta["n_in"]
assert len(payload) == 4 * n_in
crc = zlib.crc32(bytes(payload)) & 0xFFFFFFFF
if corromper:
    payload[len(payload) // 2] ^= 0x10   # CRC calculado antes: el firmware debe detectarlo
trama = b"\x55\x56" + struct.pack("<HBB", n_in, meta["f0_nominal"], 0) + bytes(payload) + struct.pack("<I", crc)

esperado = meta["stats"]
with serial.Serial(puerto, 115200, timeout=0.2) as s:
    s.reset_input_buffer()
    t0 = time.time()
    for i in range(0, len(trama), 64):          # trozos pequenos: no satura el buffer del driver
        s.write(trama[i:i + 64])
        s.flush()
    t_tx = time.time() - t0
    respuesta, cic, est, mem, t1 = None, None, None, None, time.time()
    while time.time() - t1 < 15:
        linea = s.readline().decode(errors="replace").strip()
        if linea.startswith("VEC,"):
            respuesta = linea
            if ",OK," not in linea:
                break
        elif linea.startswith("CIC,") and respuesta:
            cic = linea
        elif linea.startswith("EST,") and respuesta:
            est = linea
        elif linea.startswith("MEM,") and est:
            mem = linea
            break

print(f"enviados {len(trama)} bytes en {t_tx:.2f} s")
if respuesta is None:
    print("FALLO: sin respuesta VEC del firmware")
    sys.exit(2)
print("firmware:", respuesta)
c = respuesta.split(",")
estado = c[1]
if corromper:
    ok = estado == "CRC"
    print("PASS (CRC detectado)" if ok else "FALLO: se esperaba CRC")
    sys.exit(0 if ok else 1)
obtenido = {"n_in": int(c[2]), "f0": int(c[3]), "crc32": int(c[4], 16), "sum_v": int(c[5]), "sum_i": int(c[6]),
            "min_v": int(c[7]), "max_v": int(c[8]), "min_i": int(c[9]), "max_i": int(c[10])}
quiero = dict(esperado, n_in=n_in, f0=meta["f0_nominal"])
dif = {k: (obtenido[k], quiero[k]) for k in obtenido if obtenido[k] != quiero[k]}
if estado == "OK" and cic is None:
    print("FALLO: falta la linea CIC")
    sys.exit(2)
if estado == "OK":
    print("firmware:", cic)
    x = cic.split(",")
    claves = ("n_out", "crc32", "sum_sv", "sum_si", "first_sv", "first_si", "last_sv", "last_si")
    valores = [int(x[1]), int(x[2], 16)] + [int(v) for v in x[3:9]]
    for k, v in zip(claves, valores):
        if v != meta["cic"][k]:
            dif["cic." + k] = (v, meta["cic"][k])
if estado == "OK" and not dif:
    print(f"PASS: {meta['name']} coincide (CRC {esperado['crc32']:08x}; CIC entero identico, "
          f"CRC {meta['cic']['crc32']:08x} sobre {meta['cic']['n_out']} salidas x 2)")
else:
    print("FALLO:", estado, dif)
    sys.exit(1)

# T4.3: estimador en el firmware contra la referencia (float64) en el dominio del nodo del ADC
if est is None or est.startswith("EST,ERROR"):
    print("FALLO: sin salida del estimador:", est)
    sys.exit(2)
print("firmware:", est)
e = est.split(",")
fv, fi, mv, av, mi, ai, ciclos = (int(x) for x in e[1:8])
r = meta["ref"]
f_est = 0.5 * (fv + fi) * 1e-6
err = {
    "df_mHz": abs(f_est - r["f_hz"]) * 1e3,
    "dMagV_%": abs(mv * 1e-9 / r["node_v_rms"][0] - 1) * 100,
    "dMagI_%": abs(mi * 1e-9 / r["node_i_rms"][0] - 1) * 100,
    "dAngV_deg": abs((av * 1e-6 - r["node_v_rms"][1] + 180) % 360 - 180),
    "dAngI_deg": abs((ai * 1e-6 - r["node_i_rms"][1] + 180) % 360 - 180),
}
lim = {"df_mHz": 1.0, "dMagV_%": 0.001, "dMagI_%": 0.001, "dAngV_deg": 0.001, "dAngI_deg": 0.001}
print("error vs referencia:", ", ".join(f"{k}={v:.5f}" for k, v in err.items()), f"| {ciclos} ciclos",
      f"| {mem}" if mem else "")
if all(err[k] < lim[k] for k in lim):
    print("PASS estimador (< 1 mHz, < 0,001 %, < 0,001 deg)")
else:
    print("FALLO estimador:", {k: v for k, v in err.items() if v >= lim[k]})
    sys.exit(1)
