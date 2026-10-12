"""Decodifica el diagnostico RF del GPS (firmware compilado con -DUBX_DIAG).

Lee COM6 N segundos, guarda los bytes crudos en data/<tarea>_<fecha>.bin y decodifica las tramas UBX
(MON-VER, MON-HW, NAV-SVINFO, NAV-STATUS) segun u-blox 7 Receiver Description V14 (GPS.G7-SW-12001-B).
Uso: python tools/ubx_diag.py [segundos=20] [puerto=COM6] [poll]
  Con "poll" el script mismo envia las consultas (modulo conectado directo al PC por USB);
  sin "poll" las envia el firmware del Nucleo (-DUBX_DIAG).
"""
import datetime
import pathlib
import struct
import sys
import time

import serial

dur = float(sys.argv[1]) if len(sys.argv) > 1 else 20
puerto = sys.argv[2] if len(sys.argv) > 2 else "COM6"
data = pathlib.Path(__file__).resolve().parent.parent / "data"
data.mkdir(exist_ok=True)
stem = f"t1_5_ubx_diag_{datetime.date.today():%Y%m%d}"

def consulta(cls, mid):
    f = bytearray([0xB5, 0x62, cls, mid, 0, 0])
    a = c = 0
    for x in f[2:]:
        a = (a + x) & 0xFF
        c = (c + a) & 0xFF
    return bytes(f) + bytes([a, c])


buf = bytearray()
with serial.Serial(puerto, 115200, timeout=0.2) as s:
    s.reset_input_buffer()
    t0 = time.time()
    proximo = t0 + 1
    while time.time() - t0 < dur:
        if "poll" in sys.argv[3:] and time.time() >= proximo:
            proximo += 3
            for cm in ((0x0A, 0x04), (0x0A, 0x09), (0x01, 0x30), (0x01, 0x03)):
                s.write(consulta(*cm))
        buf += s.read(512)
(data / f"{stem}.bin").write_bytes(buf)


def tramas(b):
    """Recorre b buscando B5 62 con checksum Fletcher valido (el NMEA intercalado se ignora)."""
    i = 0
    while i + 8 <= len(b):
        if b[i] == 0xB5 and b[i + 1] == 0x62:
            n = b[i + 4] | b[i + 5] << 8
            if i + 8 + n <= len(b):
                a = c = 0
                for x in b[i + 2:i + 6 + n]:
                    a = (a + x) & 0xFF
                    c = (c + a) & 0xFF
                if (a, c) == (b[i + 6 + n], b[i + 7 + n]):
                    yield b[i + 2], b[i + 3], bytes(b[i + 6:i + 6 + n])
                    i += 8 + n
                    continue
        i += 1


A_STATUS = {0: "INIT", 1: "DONTKNOW", 2: "OK", 3: "SHORT", 4: "OPEN"}
A_POWER = {0: "OFF", 1: "ON", 2: "DONTKNOW"}
JAM = {0: "desconocido/desactivado", 1: "ok", 2: "aviso", 3: "critico"}
FIX = {0: "sin fix", 1: "DR", 2: "2D", 3: "3D", 4: "GPS+DR", 5: "solo tiempo"}
QUAL = {0: "idle", 1: "buscando", 2: "adquirida", 3: "detectada/inutil", 4: "code lock", 5: "code+carrier",
        6: "code+carrier", 7: "code+carrier"}

salida = []
cuenta = {}
ult = {}
for cls, mid, p in tramas(buf):
    cuenta[(cls, mid)] = cuenta.get((cls, mid), 0) + 1
    ult[(cls, mid)] = p
    if (cls, mid) == (0x0A, 0x09) and len(p) == 60:
        noise, agc, ast, apw, fl = struct.unpack_from("<HHBBB", p, 16)
        jam = p[45]
        salida.append(f"MON-HW   noisePerMS={noise} agcCnt={agc}/8191 antena={A_STATUS.get(ast, ast)} "
                      f"alim_antena={A_POWER.get(apw, apw)} jamInd={jam}/255 "
                      f"jammingState={JAM[(fl >> 2) & 3]} rtcCalib={fl & 1}")
    elif (cls, mid) == (0x01, 0x30) and len(p) >= 8:
        itow, nch = struct.unpack_from("<IB", p, 0)
        chans = []
        for k in range(nch):
            ch, sv, fl, q, cno, el, az, pr = struct.unpack_from("<BBBBBbhi", p, 8 + 12 * k)
            if sv != 0 or cno:
                chans.append((sv, cno, q & 7, el, fl & 1, (fl >> 2) & 1))
        txt = ", ".join(f"SV{sv}:{cno}dBHz q={QUAL[q]} el={el}{' USADO' if used else ''}"
                        f"{' orbita' if orb else ''}" for sv, cno, q, el, used, orb in chans)
        salida.append(f"NAV-SVINFO canales={nch} con_senal={sum(1 for c in chans if c[1] > 0)} "
                      f"[{txt or 'ninguno'}]")
    elif (cls, mid) == (0x01, 0x03) and len(p) == 16:
        _, fix, fl, _, _, ttff, msss = struct.unpack("<IBBBBII", p)
        salida.append(f"NAV-STATUS gpsFix={FIX.get(fix, fix)} gpsFixOk={fl & 1} ttff={ttff} ms "
                      f"desde_arranque={msss / 1000:.0f} s")
    elif (cls, mid) == (0x0A, 0x04):
        ext = [p[40 + 30 * k:70 + 30 * k].split(b"\0")[0].decode(errors="replace") for k in range((len(p) - 40) // 30)]
        salida.append(f"MON-VER  sw={p[:30].split(chr(0).encode())[0].decode(errors='replace')} "
                      f"hw={p[30:40].split(chr(0).encode())[0].decode(errors='replace')} ext={ext}")

resumen = f"{len(buf)} bytes, tramas UBX validas: " + \
          ", ".join(f"{c:02X}-{i:02X}x{n}" for (c, i), n in sorted(cuenta.items()))
(data / f"{stem}.txt").write_text(resumen + "\n" + "\n".join(salida) + "\n", encoding="utf-8")
print(resumen)
print("\n".join(salida))
