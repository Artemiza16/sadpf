"""
Memória dos cálculos pesados, por sessão.

A Curva ABC e os 21 pontos do apoio à decisão dependem só de três coisas: a
versão da base, os filtros e as preferências. O app.py resume as três numa
assinatura a cada clique; enquanto ela não muda, trocar de tela reaproveita o
resultado em vez de recalcular tudo. Mudou um filtro, uma preferência ou a base,
a assinatura muda e o cálculo é refeito.
"""
from __future__ import annotations

import streamlit as st

LIMITE = 24          # combinações guardadas por sessão, das mais recentes


def definir_assinatura(*partes) -> None:
    """Chamada pelo app.py antes de abrir a tela, com tudo de que o recorte depende."""
    st.session_state["_assinatura"] = repr(partes)


def lembrar(nome: str, funcao, *args):
    """Resultado de funcao(*args), calculado uma vez por assinatura."""
    chave = (nome, st.session_state.get("_assinatura"))
    memo = st.session_state.setdefault("_calculos", {})
    if chave not in memo:
        while len(memo) >= LIMITE:
            memo.pop(next(iter(memo)))
        memo[chave] = funcao(*args)
    resultado = memo[chave]
    # listas voltam como cópia: uma tela pode reordená-las sem afetar as outras
    return list(resultado) if isinstance(resultado, list) else resultado
