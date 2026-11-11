"""
Exportação da Curva ABC em Excel.

Usado pelo botão da tela Curva ABC e pelo script gerar_curva_abc.py, para que
os dois produzam exatamente a mesma planilha: resumo das classes, ranking
completo e os parâmetros usados no cálculo.
"""
from __future__ import annotations

import io

import pandas as pd

from core.metricas import ResultadoABC
from core.parametros import Parametros


def tabelas_curva_abc(df: pd.DataFrame, abc: ResultadoABC,
                      p: Parametros) -> dict[str, pd.DataFrame]:
    """As três abas da planilha, já com nomes de coluna em português."""
    base_txt = "valor faturado" if p.base_abc == "valor_faturado" else "valor pedido"
    resumo = abc.classes.rename(columns={
        "classe": "Classe", "itens": "Medicamentos", "pct_itens": "% dos medicamentos",
        "valor": "Valor (R$)", "pct_valor": "% do valor", "quantidade": "Unidades",
        "valor_medio": "Valor médio por item (R$)"})
    ranking = abc.itens[["posicao", "sku", "medicamento", "categoria", "classe", "valor",
                         "participacao", "acumulado", "acumulado_pct", "quantidade",
                         "compras", "fornecedores"]].rename(columns={
        "posicao": "Posição", "sku": "Código", "medicamento": "Medicamento",
        "categoria": "Categoria", "classe": "Classe", "valor": "Valor (R$)",
        "participacao": "% do total", "acumulado": "Valor acumulado (R$)",
        "acumulado_pct": "% acumulado", "quantidade": "Unidades",
        "compras": "Pedidos", "fornecedores": "Fornecedores"})
    parametros = pd.DataFrame([
        ("Período", f"{df['dt'].min():%d/%m/%Y} a {df['dt'].max():%d/%m/%Y}"),
        ("Base de valor", base_txt),
        ("Corte da classe A", f"acumulado anterior abaixo de {p.corte_a:.0%}"),
        ("Corte da classe B", f"acumulado anterior abaixo de {p.corte_b:.0%}"),
        ("Medicamentos classificados", abc.n),
        ("Valor total classificado (R$)", round(abc.total, 2)),
        ("Valor nos 20% maiores itens", f"{abc.concentracao_20:.1%}"),
    ], columns=["Item", "Valor"])
    return {"Resumo das classes": resumo, "Ranking ABC": ranking, "Parâmetros": parametros}


def curva_abc_excel(df: pd.DataFrame, abc: ResultadoABC, p: Parametros,
                    destino=None):
    """Grava a planilha em `destino` (caminho) ou devolve os bytes, se for None."""
    alvo = destino if destino is not None else io.BytesIO()
    with pd.ExcelWriter(alvo, engine="openpyxl") as excel:
        for nome, tabela in tabelas_curva_abc(df, abc, p).items():
            tabela.to_excel(excel, sheet_name=nome, index=False)
        for aba in excel.sheets.values():          # colunas com largura legível
            for coluna in aba.columns:
                largura = max(len(str(c.value or "")) for c in coluna)
                aba.column_dimensions[coluna[0].column_letter].width = min(60, largura + 2)
    return None if destino is not None else alvo.getvalue()
