"""
Formatação de números e datas no padrão brasileiro (R$ 1.234,56 · 12,5% · 08/07/2026).

Módulo neutro, sem dependência da interface: é usado pelo motor de decisão (camada de
modelos), para montar as frases dos pontos, e reexportado por core/tema.py para as
telas. Antes ficava em tema.py, o que fazia a camada de modelos depender do Streamlit.
"""
from __future__ import annotations


def brl(valor, casas: int = 2) -> str:
    if valor is None:
        return "—"
    txt = f"{float(valor):,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {txt}"


def brl0(valor) -> str:
    return brl(valor, 0)


def num(valor) -> str:
    if valor is None:
        return "—"
    return f"{float(valor):,.0f}".replace(",", ".")


def pct(valor, casas: int = 1) -> str:
    if valor is None:
        return "—"
    return f"{float(valor)*100:.{casas}f}".replace(".", ",") + "%"


def data(valor) -> str:
    try:
        return valor.strftime("%d/%m/%Y")
    except Exception:
        return "—"


MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]


def mes_label(ano_mes: str) -> str:
    """'2025-04' vira 'abr/25'."""
    try:
        ano, mes = str(ano_mes).split("-")
        return f"{MESES[int(mes)-1]}/{ano[2:]}"
    except (ValueError, IndexError):
        return str(ano_mes)
