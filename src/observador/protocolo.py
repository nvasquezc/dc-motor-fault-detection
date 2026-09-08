"""
Protocolo de telemetria del observador DC.
Trama: k,t_us,ref,w_raw,w_hat,d_hat,e,I,u,duty,i_r,i_l,nf,flags*CRC8
"""

N_CAMPOS = 14

# Banderas de estado del firmware
F_STALL     = 0x01
F_SAT       = 0x02
F_NO_EDGE   = 0x04
F_FALLO_PWM = 0x08
F_GLITCH    = 0x10
F_MANUAL    = 0x20


def crc8(data: bytes) -> int:
    """CRC-8 polinomio 0x07, identico al del firmware."""
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def parsear_trama(raw: bytes) -> dict | None:
    """Valida y desempaqueta una trama. Devuelve None si es invalida."""
    try:
        s = raw.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError:
        return None

    if "*" not in s:
        return None

    cuerpo, _, chk = s.rpartition("*")
    if len(chk) != 2:
        return None

    try:
        if crc8(cuerpo.encode("ascii")) != int(chk, 16):
            return None
    except ValueError:
        return None

    campos = cuerpo.split(",")
    if len(campos) != N_CAMPOS:
        return None

    try:
        return {
            "k": int(campos[0]),
            "t_us": int(campos[1]),
            "ref": float(campos[2]),
            "w_raw": float(campos[3]),
            "w_hat": float(campos[4]),
            "d_hat": float(campos[5]),
            "error": float(campos[6]),
            "integral": float(campos[7]),
            "u": float(campos[8]),
            "duty": float(campos[9]),
            "i_r": float(campos[10]),
            "i_l": float(campos[11]),
            "n_flancos": int(campos[12]),
            "flags": int(campos[13]),
        }
    except ValueError:
        return None