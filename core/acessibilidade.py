"""
Conferência das cores para daltonismo e contraste (usada pelo verificar.py).

- Simulação de daltonismo: matrizes de Machado, Oliveira e Fernandes (2009),
  severidade máxima, para protanopia, deuteranopia e tritanopia.
- Distância entre cores: CIEDE2000 (ΔE00). Acima de ~10 duas cores já são
  distinguíveis com facilidade; abaixo de ~5, quase iguais.
- Contraste: razão de luminância relativa da WCAG 2.1 (texto pequeno ≥ 4,5:1;
  elementos gráficos ≥ 3:1).
"""
from __future__ import annotations

import math

import numpy as np

SIMULACAO = {
    "protanopia": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
                            [-0.003882, -0.048116, 1.051998]]),
    "deuteranopia": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
                              [-0.011820, 0.042940, 0.968881]]),
    "tritanopia": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
                            [0.004733, 0.691367, 0.303900]]),
}


def _linear(hexa: str) -> np.ndarray:
    c = np.array([int(hexa[i:i + 2], 16) for i in (1, 3, 5)]) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lab(rgb_lin: np.ndarray) -> tuple[float, float, float]:
    rgb_lin = np.clip(rgb_lin, 0, 1)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = m @ rgb_lin / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def delta_e2000(lab1, lab2) -> float:
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    cm = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(cm ** 7 / (cm ** 7 + 25 ** 7)))
    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1 = math.degrees(math.atan2(b1, a1p)) % 360
    h2 = math.degrees(math.atan2(b2, a2p)) % 360
    dl, dc = L2 - L1, c2p - c1p
    dh = h2 - h1
    if c1p * c2p == 0:
        dh = 0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dhh = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    lm, cpm = (L1 + L2) / 2, (c1p + c2p) / 2
    hm = h1 + h2
    if c1p * c2p != 0:
        hm = (h1 + h2 + 360) / 2 if abs(h1 - h2) > 180 else (h1 + h2) / 2
    t = (1 - 0.17 * math.cos(math.radians(hm - 30)) + 0.24 * math.cos(math.radians(2 * hm))
         + 0.32 * math.cos(math.radians(3 * hm + 6)) - 0.20 * math.cos(math.radians(4 * hm - 63)))
    sl = 1 + 0.015 * (lm - 50) ** 2 / math.sqrt(20 + (lm - 50) ** 2)
    sc, sh = 1 + 0.045 * cpm, 1 + 0.015 * cpm * t
    rt = (-2 * math.sqrt(cpm ** 7 / (cpm ** 7 + 25 ** 7))
          * math.sin(math.radians(60 * math.exp(-((hm - 275) / 25) ** 2))))
    return math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dhh / sh) ** 2
                     + rt * (dc / sc) * (dhh / sh))


def distancia(cor1: str, cor2: str, tipo: str | None = None) -> float:
    """ΔE00 entre duas cores, vistas normalmente (tipo=None) ou com um tipo de daltonismo."""
    m = SIMULACAO[tipo] if tipo else np.eye(3)
    return delta_e2000(_lab(m @ _linear(cor1)), _lab(m @ _linear(cor2)))


def menor_distancia(cor1: str, cor2: str) -> tuple[float, str]:
    """A pior das três simulações (e a visão normal): onde as cores mais se parecem."""
    casos = {t: distancia(cor1, cor2, t) for t in SIMULACAO}
    casos["normal"] = distancia(cor1, cor2)
    tipo = min(casos, key=casos.get)
    return casos[tipo], tipo


def contraste(cor1: str, cor2: str = "#FFFFFF") -> float:
    def lum(c):
        r, g, b = _linear(c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    a, b = sorted([lum(cor1), lum(cor2)], reverse=True)
    return (a + 0.05) / (b + 0.05)
