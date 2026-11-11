"""Curva ABC e Análises e Indicadores (compras e movimentação)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import metricas as M
from core import movimentacao as MV
from core.exportar import curva_abc_excel
from core.memoria import lembrar
from core.parametros import Parametros
from core.tema import (MESES, brl, brl0, cascata, cores, data, faixa, linha_cartoes,
                       mes_label, mostrar, num, pct)
from paginas.compras import barras_h


# -------------------------------------------------------------------- CURVA ABC
VISOES_ABC = {"Compras": ":material/shopping_cart:",
              "Vendas": ":material/point_of_sale:",
              "Compras × vendas": ":material/compare_arrows:"}


def curva_abc(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    from paginas import movimentacao as PM
    faixa("Quais medicamentos concentram o dinheiro — o <b>principal instrumento de "
          "priorização</b> do sistema. Pelas <b>compras</b>, onde está o gasto; pelas "
          "<b>vendas</b>, o que de fato gira; o cruzamento mostra dinheiro parado e itens que "
          "não podem faltar.", "Curva ABC")
    pos = PM.posicao(p)
    visoes = list(VISOES_ABC) if pos is not None else list(VISOES_ABC)[:1]
    visao = st.segmented_control("Base da curva", visoes, default=visoes[0], key="abc_visao",
                                 format_func=lambda v: f"{VISOES_ABC[v]} {v}")
    visao = visao or visoes[0]
    if visao == "Vendas":
        _abc_vendas(lembrar("abc_vendas", MV.curva_abc_vendas, pos, p), p)
    elif visao == "Compras × vendas":
        _abc_cruzada(abc, lembrar("abc_vendas", MV.curva_abc_vendas, pos, p), p)
    else:
        _abc_compras(df, abc, p)


def _abc_vendas(abc_v: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    classes, itens = abc_v.classes.set_index("classe"), abc_v.itens
    st.subheader("Curva ABC pelo faturamento das vendas")
    st.caption("Mesma regra da curva de compras (cortes em Preferências, classe pelo "
               "acumulado anterior ao item), aplicada ao faturamento de cada medicamento.")
    linha_cartoes(
        [(f"Classe {cl}", f"{num(int(classes.loc[cl,'itens']))} itens",
          f"{pct(classes.loc[cl,'pct_itens'],1)} do mix · {brl0(classes.loc[cl,'valor'])} · "
          f"{pct(classes.loc[cl,'pct_valor'],1)} do faturamento",
          "roxo" if cl == "A" else "") for cl in "ABC"] +
        [("Medicamentos vendidos", num(abc_v.n), f"{brl(abc_v.total)} de faturamento"),
         ("Faturamento nos 20% maiores itens", pct(abc_v.concentracao_20),
          "o princípio de Pareto prevê cerca de 80%"),
         ("Margem da classe A", pct((itens.loc[itens["classe"] == "A", "valor"] *
                                     itens.loc[itens["classe"] == "A", "margem_pct"]).sum()
                                    / max(1.0, classes.loc["A", "valor"]), 1),
          "ponderada pelo faturamento")],
        colunas=3)
    cores_classe = {"A": c["purple"], "B": c["purple_l"], "C": c["gray3"]}
    passo = max(1, abc_v.n // 250)
    amostra = itens.iloc[::passo]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=amostra["posicao"], y=amostra["valor"],
                         marker_color=[cores_classe[cl] for cl in amostra["classe"]],
                         name="Faturamento por item",
                         customdata=amostra[["medicamento", "classe"]],
                         hovertemplate="#%{x} %{customdata[0]}<br><b>R$ %{y:,.2f}</b> · "
                                       "classe %{customdata[1]}<extra></extra>"))
    fig.add_trace(go.Scatter(x=amostra["posicao"], y=amostra["acumulado_pct"], yaxis="y2",
                             mode="lines", line=dict(color=c["amber"], width=2.2),
                             name="% acumulado",
                             hovertemplate="acumulado: <b>%{y:.1%}</b><extra></extra>"))
    for corte in abc_v.corte:
        fig.add_hline(y=corte, yref="y2", line=dict(color=c["amber"], dash="dot", width=1))
    fig.update_layout(title="Curva ABC por vendas: faturamento por item e acumulado",
                      yaxis2=dict(overlaying="y", side="right", tickformat=".0%",
                                  range=[0, 1.02], showgrid=False),
                      xaxis_title="posição do item no ranking")
    mostrar(fig, 380,
            "Pelas vendas, a curva é bem mais concentrada que pelas compras: o que gira "
            "está em poucos itens. É a curva clássica de gestão de estoque, que define o "
            "controle de cada item pela sua saída.")
    tabela = itens[["posicao", "medicamento", "classe", "valor", "participacao",
                    "acumulado_pct", "quantidade", "margem_pct", "giro", "estoque_atual",
                    "cobertura_dias", "situacao"]].rename(columns={
        "posicao": "#", "medicamento": "Medicamento", "classe": "Classe",
        "valor": "Faturamento", "participacao": "% do total", "acumulado_pct": "% acumulado",
        "quantidade": "Unidades vendidas", "margem_pct": "Margem", "giro": "Giro",
        "estoque_atual": "Estoque", "cobertura_dias": "Cobertura (dias)",
        "situacao": "Situação"})
    st.dataframe(tabela, width="stretch", hide_index=True, height=440, column_config={
        "Faturamento": st.column_config.NumberColumn(format="R$ %.2f"),
        "% do total": st.column_config.NumberColumn(format="percent"),
        "% acumulado": st.column_config.ProgressColumn(format="percent", min_value=0,
                                                       max_value=1),
        "Margem": st.column_config.NumberColumn(format="percent"),
        "Giro": st.column_config.NumberColumn(format="%.2fx"),
        "Cobertura (dias)": st.column_config.NumberColumn(format="%.0f")})


def _abc_cruzada(abc: M.ResultadoABC, abc_v: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    cruz = MV.abc_cruzada(abc, abc_v)
    st.subheader("Classe nas compras × classe nas vendas")
    st.caption("Cada medicamento recebe uma classe pela curva de compras (valor comprado) e "
               "outra pela curva de vendas (faturamento). Na diagonal, compra e venda andam "
               "juntas; fora dela está a decisão.")
    linhas = ["A", "B", "C"]
    colunas = ["A", "B", "C", "sem venda"]
    tab = pd.crosstab(cruz["classe_compras"], cruz["classe_vendas"]) \
        .reindex(index=linhas, columns=colunas, fill_value=0)
    valor = cruz.pivot_table(index="classe_compras", columns="classe_vendas",
                             values="valor_compras", aggfunc="sum", fill_value=0) \
        .reindex(index=linhas, columns=colunas, fill_value=0)
    texto = [[f"{tab.loc[r, k]} itens<br>{brl0(valor.loc[r, k])}" for k in colunas]
             for r in linhas]
    fig = go.Figure(go.Heatmap(
        z=tab.values, x=[f"vendas {k}" for k in colunas], y=[f"compras {r}" for r in linhas],
        text=texto, texttemplate="%{text}", colorscale=[[0, c["surface2"]], [1, c["purple"]]],
        showscale=False, hovertemplate="%{y} · %{x}<br>%{text}<extra></extra>"))
    fig.update_layout(title="Medicamentos por classe de compra e de venda "
                            "(rótulo: itens · valor comprado)",
                      yaxis=dict(autorange="reversed"))
    mostrar(fig, 340,
            "**Linha A, colunas C ou sem venda**: muito dinheiro comprado para pouca saída — "
            "capital parado e risco de vencer.\n\n**Coluna A, linhas B ou C**: itens que "
            "custam pouco no total, mas estão entre os que mais vendem — a falta deles "
            "custa venda e cliente.")
    parado = cruz[(cruz["classe_compras"] == "A") &
                  (cruz["classe_vendas"].isin(["C", "sem venda"]))] \
        .sort_values("valor_compras", ascending=False)
    critico = cruz[(cruz["classe_vendas"] == "A") &
                   (cruz["classe_compras"].isin(["B", "C"]))] \
        .sort_values("faturamento", ascending=False)
    esq, dir_ = st.columns(2)
    with esq:
        st.markdown(f"**Compra A, venda C ou sem venda** · {len(parado)} itens · "
                    f"{brl0(parado['valor_compras'].sum())} comprados".replace("$", "\\$"))
        st.dataframe(parado[["medicamento", "valor_compras", "faturamento", "situacao"]]
                     .rename(columns={"medicamento": "Medicamento",
                                      "valor_compras": "Comprado", "faturamento": "Vendido",
                                      "situacao": "Situação"}),
                     hide_index=True, width="stretch", height=300, column_config={
                         "Comprado": st.column_config.NumberColumn(format="R$ %.2f"),
                         "Vendido": st.column_config.NumberColumn(format="R$ %.2f")})
    with dir_:
        st.markdown(f"**Venda A, compra B ou C** · {len(critico)} itens · "
                    f"{brl0(critico['faturamento'].sum())} vendidos".replace("$", "\\$"))
        st.dataframe(critico[["medicamento", "faturamento", "valor_compras", "situacao"]]
                     .rename(columns={"medicamento": "Medicamento", "faturamento": "Vendido",
                                      "valor_compras": "Comprado", "situacao": "Situação"}),
                     hide_index=True, width="stretch", height=300, column_config={
                         "Comprado": st.column_config.NumberColumn(format="R$ %.2f"),
                         "Vendido": st.column_config.NumberColumn(format="R$ %.2f")})


def _abc_compras(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    itens, classes = abc.itens, abc.classes.set_index("classe")
    n = abc.n

    st.subheader("Curva ABC dos medicamentos")
    base_txt = "valor faturado" if p.base_abc == "valor_faturado" else "valor pedido"
    st.caption(f"Medicamentos ordenados pelo {base_txt}, do maior para o menor. O percentual "
               "acumulado define a classe: o item que cruza o corte fecha a classe a que "
               "pertence. Os cortes e a base de valor ficam na tela Preferências.")

    linha_cartoes(
        [(f"Classe {cl}", f"{num(int(classes.loc[cl,'itens']))} itens",
          f"{pct(classes.loc[cl,'pct_itens'],1)} do mix · {brl0(classes.loc[cl,'valor'])} · "
          f"{pct(classes.loc[cl,'pct_valor'],1)} do valor",
          "roxo" if cl == "A" else "") for cl in "ABC"] +
        [("Medicamentos classificados", num(n), f"{brl(abc.total)} em {base_txt}"),
         ("Valor nos 20% maiores itens", pct(abc.concentracao_20),
          "o princípio de Pareto prevê cerca de 80%"),
         (f"Mix necessário para {pct(p.corte_a,0)} do valor",
          pct(classes.loc["A", "pct_itens"], 1) + " dos itens",
          "quanto maior, mais dispersa é a compra")],
        colunas=3)

    cores_classe = {"A": c["purple"], "B": c["purple_l"], "C": c["gray3"]}
    fig = go.Figure()
    for cl in "ABC":
        fig.add_trace(go.Bar(
            y=["Valor comprado", "Medicamentos"],
            x=[classes.loc[cl, "pct_valor"], classes.loc[cl, "pct_itens"]],
            name=f"Classe {cl}", orientation="h", marker_color=cores_classe[cl],
            text=[pct(classes.loc[cl, "pct_valor"], 1), pct(classes.loc[cl, "pct_itens"], 1)],
            textposition="inside", insidetextanchor="middle",
            hovertemplate=f"Classe {cl}<br><b>%{{x:.1%}}</b><extra></extra>"))
    fig.update_layout(barmode="stack", title="Participação de cada classe no mix e no valor",
                      xaxis_tickformat=".0%", xaxis_title=None, yaxis_title=None,
                      legend=dict(traceorder="normal"))
    mostrar(fig, 280,
            "O **princípio de Pareto** prevê que cerca de 20% dos itens concentrem 80% do "
            "valor.\n\nAs duas barras testam isso lado a lado: uma é a fatia do **mix**, a "
            "outra a fatia do **dinheiro**. Quanto mais parecidas, mais achatada é a curva e "
            "menos ela serve para priorizar.")

    passo = max(1, n // 250)
    amostra = itens.iloc[::passo]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=amostra["posicao"], y=amostra["valor"],
                         marker_color=[cores_classe[cl] for cl in amostra["classe"]],
                         name="Valor por item",
                         customdata=amostra[["medicamento", "classe"]],
                         hovertemplate="#%{x} %{customdata[0]}<br><b>R$ %{y:,.2f}</b> · "
                                       "classe %{customdata[1]}<extra></extra>"))
    fig.add_trace(go.Scatter(x=amostra["posicao"], y=amostra["acumulado_pct"], yaxis="y2",
                             mode="lines", line=dict(color=c["amber"], width=2.2),
                             name="% acumulado",
                             hovertemplate="acumulado: <b>%{y:.1%}</b><extra></extra>"))
    for corte in abc.corte:
        fig.add_hline(y=corte, yref="y2", line=dict(color=c["amber"], dash="dot", width=1))
    titulo = ("Curva ABC: valor por item e percentual acumulado" if passo == 1 else
              f"Curva ABC: valor por item e percentual acumulado (1 a cada {passo} itens)")
    fig.update_layout(title=titulo,
                      yaxis2=dict(overlaying="y", side="right", tickformat=".0%",
                                  range=[0, 1.02], showgrid=False),
                      xaxis_title="posição do item no ranking")
    mostrar(fig, 380,
            "A **Curva ABC** ordena os medicamentos pelo valor de consumo, do maior para o "
            "menor.\n\nAs barras são o valor de cada item. A linha âmbar é o **percentual "
            "acumulado**: quanto do valor total já foi somado até ali. Onde ela cruza os "
            "cortes, muda a classe.\n\nA classe usa o acumulado **anterior** ao item, então "
            "quem cruza o corte fecha a classe a que pertence.")

    st.subheader("Distribuição das classes")
    criterios = [f"acumulado até {pct(p.corte_a,0)}",
                 f"de {pct(p.corte_a,0)} até {pct(p.corte_b,0)}",
                 f"acima de {pct(p.corte_b,0)}"]
    dist = abc.classes.copy()
    dist.insert(1, "criterio", criterios)
    dist.loc[len(dist)] = {"classe": "Total", "criterio": "", "itens": n, "pct_itens": 1.0,
                           "valor": abc.total, "pct_valor": 1.0,
                           "quantidade": int(abc.classes["quantidade"].sum()),
                           "valor_medio": abc.total / n if n else 0}
    st.dataframe(dist.rename(columns={
        "classe": "Classe", "criterio": "Critério", "itens": "Medicamentos",
        "pct_itens": "% dos medicamentos", "valor": "Valor", "pct_valor": "% do valor",
        "quantidade": "Unidades", "valor_medio": "Valor médio por item"}),
        width="stretch", hide_index=True, column_config={
            "% dos medicamentos": st.column_config.NumberColumn(format="percent"),
            "% do valor": st.column_config.NumberColumn(format="percent"),
            "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
            "Valor médio por item": st.column_config.NumberColumn(format="R$ %.2f")})

    st.subheader("Ranking dos medicamentos")
    st.caption(f"{num(n)} medicamentos classificados — o ranking completo do período "
               "filtrado.")
    # a mesma planilha do script gerar_curva_abc.py, com os filtros em uso
    planilha = lembrar("abc_excel", curva_abc_excel, df, abc, p)
    st.download_button("Baixar Curva ABC (Excel)", planilha,
                       file_name="curva_abc.xlsx", icon=":material/download:",
                       mime="application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet",
                       help="Resumo das classes, ranking completo e parâmetros usados, "
                            "com os filtros que estão valendo agora.")
    ranking = itens[["posicao", "medicamento", "sku", "classe", "valor", "participacao",
                     "acumulado", "acumulado_pct", "compras", "fornecedores"]].rename(
        columns={"posicao": "#", "medicamento": "Medicamento", "sku": "Código",
                 "classe": "Classe", "valor": "Valor", "participacao": "% do total",
                 "acumulado": "Valor acumulado", "acumulado_pct": "% acumulado",
                 "compras": "Compras", "fornecedores": "Fornecedores"})
    st.dataframe(ranking, width="stretch", hide_index=True, height=460, column_config={
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "Valor acumulado": st.column_config.NumberColumn(format="R$ %.2f"),
        "% do total": st.column_config.NumberColumn(format="percent"),
        "% acumulado": st.column_config.ProgressColumn(format="percent",
                                                       min_value=0, max_value=1)})


# ----------------------------------------------------- ANÁLISES E INDICADORES
ASSUNTOS = {
    "Giro e cobertura": ":material/autorenew:",
    "Entrega e cotação": ":material/local_shipping:",
    "Condições comerciais": ":material/handshake:",
    "Preço e margem": ":material/sell:",
    "Mix e sazonalidade": ":material/donut_large:",
    "ABC × XYZ": ":material/grid_view:",
    "Ritmo de compra": ":material/event_repeat:",
    "Estatística": ":material/query_stats:",
}


def analises(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    faixa("Os indicadores do negócio por assunto: <b>giro e cobertura</b> do estoque, "
          "<b>entrega</b>, <b>condições comerciais</b>, <b>preço e margem</b>, mix e "
          "sazonalidade, regularidade, ritmo de compra e estatística descritiva.",
          "Análises e Indicadores")
    escolha = st.segmented_control(
        "Assunto", list(ASSUNTOS), default=list(ASSUNTOS)[0], key="anal_assunto",
        format_func=lambda a: f"{ASSUNTOS[a]} {a}", label_visibility="collapsed")
    escolha = escolha or list(ASSUNTOS)[0]
    # só o assunto escolhido é calculado e desenhado: a tela continua leve
    {"Giro e cobertura": _giro, "Entrega e cotação": _entrega,
     "Condições comerciais": _condicoes, "Preço e margem": _preco_margem,
     "Mix e sazonalidade": _mix, "ABC × XYZ": _abc_xyz, "Ritmo de compra": _reposicao,
     "Estatística": _estatistica}[escolha](df, abc, p)


# ............................................................. giro e cobertura
def _giro(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    """Giro, cobertura e a ponte do estoque, calculados sobre o livro de movimentação."""
    from paginas import movimentacao as PM
    c = cores()
    rec, _ = PM.recorte()
    if rec is None or rec.mov.empty:
        st.info("Giro e cobertura precisam do livro de movimentação (entradas e saídas). "
                "Carregue-o em Base de Dados.")
        return
    pos = PM.posicao(p)
    pt = lembrar("mov_ponte", MV.ponte_estoque, rec)

    st.subheader("Do estoque de partida ao de chegada")
    st.caption(f"De {data(pt['inicio'])} a {data(pt['fim'])}, a custo. Os indicadores abaixo "
               "saem destes dois pontos e do que entrou e saiu entre eles.")
    linha_cartoes([
        ("Estoque de partida", brl0(pt["valor_inicial"]),
         f"{num(pt['un_inicial'])} un em {data(pt['inicio'])}"),
        ("Estoque de chegada", brl0(pt["valor_final"]),
         f"{num(pt['un_final'])} un em {data(pt['fim'])}", "destaque"),
        ("Variação do estoque", ("+" if pt["variacao"] >= 0 else "") + brl0(pt["variacao"]),
         (pct(pt["variacao_pct"], 0) + " sobre a partida") if pd.notna(pt["variacao_pct"])
         else "sem estoque de partida"),
        ("Giro do período", f"{pt['giro']:.2f}×".replace(".", ",") if pd.notna(pt["giro"])
         else "—", "custo vendido ÷ estoque médio"),
    ], colunas=4)

    # cor pelo efeito no negócio, não pela direção: vender tira do estoque e é
    # benéfico (verde); vencer é prejuízo (laranja); comprar repõe (neutro)
    fig = cascata([
        ("Estoque de partida", pt["valor_inicial"], "total", "total", ""),
        ("Compras recebidas", pt["valor_entradas"], "soma", "neutro", ""),
        ("Custo do que foi vendido", pt["cmv"], "subtrai", "bom", ""),
        ("Perdas por validade", pt["valor_perdas"], "subtrai", "ruim", ""),
        ("Estoque de chegada", pt["valor_final"], "total", "total", ""),
    ], "Ponte do estoque no período (a custo)", horizontal=False)
    mostrar(fig, 380,
            "**estoque de partida + compras − custo do que foi vendido − perdas = estoque de "
            "chegada.** A ponte fecha centavo a centavo porque cada saída é avaliada pelo custo "
            "do lote de onde saiu. O estoque de partida é o saldo da véspera do início do "
            "período; o de chegada, o saldo na data final.\n\n**Cores pelo efeito:** verde é "
            "benéfico (o que saiu vendido), laranja é prejudicial (o que venceu), azul-claro "
            "é neutro (compras, que só repõem) e azul-escuro são os totais.")

    st.subheader("Indicadores do período")
    linhas = [
        ("Giro do estoque", f"{pt['giro']:.2f}×".replace(".", ","),
         "custo vendido ÷ ((partida + chegada) ÷ 2)", "quantas vezes o estoque médio foi vendido"),
        ("Dias de estoque", f"{pt['dias_estoque']:.0f} dias",
         "estoque médio ÷ custo vendido por dia", "quanto tempo, em média, o produto fica parado"),
        ("Cobertura na chegada", f"{pt['cobertura_final']:.0f} dias",
         "estoque de chegada ÷ custo vendido por dia", "quanto o estoque final dura no ritmo do "
                                                         "período (referência: 30 a 60 dias)"),
        ("Escoamento", pct(pt["escoamento"], 0),
         "unidades vendidas ÷ (partida + compras)", "parte do que esteve disponível que foi "
                                                    "vendida"),
        ("Perda sobre o disponível", pct(pt["perda_disponivel"], 1),
         "unidades vencidas ÷ (partida + compras)", "parte do que esteve disponível que venceu"),
        ("Compra ÷ venda", f"{pt['compra_sobre_venda']:.2f}×".replace(".", ","),
         "compras a custo ÷ custo vendido", "acima de 1, o estoque cresce; abaixo, diminui"),
    ]
    st.dataframe(pd.DataFrame(linhas, columns=["Indicador", "Valor", "Fórmula", "Leitura"]),
                 hide_index=True, width="stretch")

    grupos = lembrar("mov_ponte_classe", MV.ponte_por_grupo, rec)
    if len(grupos):
        st.subheader("Por classe terapêutica")
        # valores já formatados no padrão brasileiro (R$ 10.176; 2,96×): o formato
        # numérico da tabela não tem separador de milhar nem vírgula decimal
        tabela = grupos.copy()
        for k in ["inicial", "entradas", "cmv", "perdas", "final"]:
            tabela[k] = tabela[k].map(brl0)
        tabela["variacao"] = tabela["variacao"].map(
            lambda v: ("+" if v >= 0 else "−") + brl0(abs(v)))
        tabela["giro"] = tabela["giro"].map(
            lambda v: f"{v:.2f}×".replace(".", ",") if pd.notna(v) else "—")
        st.dataframe(tabela.rename(columns={
            "grupo": "Classe terapêutica", "inicial": "Partida", "entradas": "Compras",
            "cmv": "Custo vendido", "perdas": "Perdas", "final": "Chegada",
            "variacao": "Variação", "giro": "Giro", "dias_estoque": "Dias de estoque",
            "escoamento": "Escoamento"}), hide_index=True, width="stretch", column_config={
                "Dias de estoque": st.column_config.NumberColumn(format="%.0f"),
                "Escoamento": st.column_config.ProgressColumn(format="percent", min_value=0,
                                                              max_value=1)})

    serie = lembrar("mov_serie", MV.serie_mensal, rec)
    col1, col2 = st.columns(2)
    with col1:
        if len(serie):
            rot = serie["ano_mes"].map(mes_label)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=rot, y=serie["compras"], name="Compras",
                                 marker_color=c["blue_l"],
                                 hovertemplate="%{x}<br>compras <b>R$ %{y:,.0f}</b>"
                                               "<extra></extra>"))
            fig.add_trace(go.Scatter(x=rot, y=serie["cmv"], name="Custo do que foi vendido",
                                     mode="lines", line=dict(color=c["amber"]),
                                     hovertemplate="%{x}<br>custo vendido <b>R$ %{y:,.0f}</b>"
                                                   "<extra></extra>"))
            fig.update_layout(title="Compras × custo do que foi vendido",
                              yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
            mostrar(fig, 340,
                    "Os dois a custo. Meses com a barra acima da linha aumentam o estoque; "
                    "abaixo, reduzem. O primeiro e o último mês podem estar incompletos.")
    with col2:
        fx = MV.faixas_cobertura(pos, p)
        cor_fx = {"Sem estoque": c["red"], "Até 15 dias": c["amber"], "15 a 30 dias": c["amber"],
                  "30 a 60 dias": c["green"], "60 a 120 dias": c["blue_l"],
                  "Mais de 120 dias": c["blue"], "Com estoque, sem venda recente": c["ink3"]}
        rotulos = {"Com estoque, sem venda recente": "Sem venda"}
        fig = go.Figure(go.Bar(
            x=[rotulos.get(f, f) for f in fx["faixa"]], y=fx["produtos"],
            marker_color=[cor_fx[f] for f in fx["faixa"]], customdata=fx["valor"],
            hovertemplate="%{x}<br><b>%{y} produtos</b> · R$ %{customdata:,.0f}"
                          "<extra></extra>"))
        fig.update_layout(title="Produtos por duração do estoque", yaxis_title="produtos")
        mostrar(fig, 340,
                "Cobertura = estoque ÷ venda por dia dos últimos "
                f"{p.mov_janela_demanda} dias. **Verde** é a faixa recomendada (30 a 60 dias; "
                "Slack, Brandon-Jones e Johnston, 2022). À esquerda, risco de faltar; à "
                "direita, dinheiro parado e risco de vencer.")
    PM.atalho("Posição de Estoque", "Ver a situação de cada produto")


def _sazonalidade_vendas(p: Parametros) -> None:
    """Índice sazonal das vendas por classe terapêutica (movimentação)."""
    from paginas import movimentacao as PM
    c = cores()
    rec, _ = PM.recorte()
    if rec is None or rec.mov.empty:
        return
    st.subheader("Sazonalidade das vendas por classe terapêutica")
    saz = lembrar("mov_sazonalidade", MV.sazonalidade, rec)
    rs = MV.resumo_sazonal(saz) if len(saz) else pd.DataFrame()
    if rec.dias < 365 or saz.empty or rs.empty:
        st.info("A sazonalidade compara o mesmo mês entre anos e precisa de pelo menos 12 "
                "meses no período filtrado.")
        return
    legiveis = rs[rs["legivel"]]
    cards = []
    for _, r in legiveis.head(3).iterrows():
        razao = r["inverno_verao"]
        leitura = ("vende mais no inverno" if razao > 1.1 else
                   "vende mais no verão" if razao < 0.9 else "estável no ano")
        cards.append((r["classe"].split(" /")[0], leitura.capitalize(),
                      f"inverno ÷ verão = {razao:.2f} · pico em {MESES[r['mes_pico'] - 1]}"
                      .replace(".", ",")))
    if cards:
        linha_cartoes(cards, colunas=len(cards))
    ordem = rs["classe"].tolist()
    piv = saz.pivot(index="classe", columns="mes", values="indice").reindex(ordem)
    rotulos = [c_ if leg else f"{c_} · pouco volume" for c_, leg in zip(ordem, rs["legivel"])]
    meses_rot = [f"{m} ❄" if i in (5, 6, 7) else m for i, m in enumerate(MESES)]
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=meses_rot, y=rotulos, zmin=40, zmax=160,
        colorscale=[[0, c["blue"]], [0.5, "#F7F9FB"], [1, c["red"]]],
        text=piv.round(0).values, texttemplate="%{text:.0f}", xgap=2, ygap=2,
        hovertemplate="%{y}<br>%{x}: índice <b>%{z:.0f}</b><extra></extra>",
        colorbar=dict(title="índice", thickness=10)))
    fig.update_layout(title="Índice de venda por mês (100 = média da classe; ❄ = inverno)",
                      yaxis=dict(autorange="reversed", showgrid=False),
                      xaxis=dict(showline=False))
    mostrar(fig, 150 + 28 * len(ordem),
            "Acima de 100 (vermelho), o mês vende mais que a média da classe; abaixo (azul), "
            "menos. A literatura do setor espera respiratórios e antibióticos em alta no "
            "inverno e dermatológicos e antiparasitários no verão.\n\nA venda de cada mês é "
            "dividida pelos dias do mês no período e pelos produtos ativos da classe, para que "
            "o catálogo crescendo e os meses repetidos não se passem por estação. Classes com "
            f"menos de {num(MV.VOLUME_MINIMO_SAZONAL)} unidades vendidas aparecem como *pouco "
            "volume*. É este índice que ajusta a demanda da lista de compra.")
    with st.expander("Tabela por classe (pico, vale e razão inverno ÷ verão)"):
        st.dataframe(rs.assign(mes_pico=rs["mes_pico"].map(lambda m: MESES[m - 1]),
                               mes_vale=rs["mes_vale"].map(lambda m: MESES[m - 1]))
                     .drop(columns=["amplitude"]).rename(columns={
                         "classe": "Classe terapêutica", "unidades": "Unidades vendidas",
                         "legivel": "Volume suficiente", "mes_pico": "Pico",
                         "indice_pico": "Índice no pico", "mes_vale": "Vale",
                         "indice_vale": "Índice no vale", "inverno_verao": "Inverno ÷ verão"}),
                     hide_index=True, width="stretch", column_config={
                         "Índice no pico": st.column_config.NumberColumn(format="%.0f"),
                         "Índice no vale": st.column_config.NumberColumn(format="%.0f"),
                         "Inverno ÷ verão": st.column_config.NumberColumn(format="%.2f")})


def _altura_barras(*tabelas, minimo: int = 320) -> int:
    """Altura comum para gráficos lado a lado, conforme o número de categorias."""
    return max(minimo, max((len(t) for t in tabelas), default=0) * 34 + 110)


# ............................................................ entrega e cotação
def _entrega(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    ind = M.indicadores(df)
    serie = M.serie_mensal(df)
    serie["mes"] = serie["ano_mes"].map(mes_label)
    cortadas = int((df["Qtde. Fat."] < df["Qtde. Ped."]).sum())
    falta_un = ind.qtd_pedida - ind.qtd_faturada
    sub_un = (f"{num(falta_un)} unidades não entregues" if falta_un >= 0
              else f"{num(-falta_un)} unidades faturadas além do pedido")
    if ind.nao_faturado >= 0:
        rot_valor, val_valor, sub_valor = ("Valor pedido e não faturado", brl(ind.nao_faturado),
                                           "diferença entre pedido e nota")
    else:
        rot_valor, val_valor, sub_valor = ("Valor faturado além do pedido",
                                           brl(-ind.nao_faturado),
                                           "nota acima do pedido (quantidade ou preço)")
    cotada = pd.to_numeric(df.get("Qtde. Cot", pd.Series(dtype=float)), errors="coerce").sum()
    aderencia = ind.qtd_pedida / cotada if cotada else float("nan")

    st.subheader("Entrega e cotação")
    linha_cartoes([
        ("Nível de atendimento", pct(ind.nivel_atendimento), sub_un, "destaque"),
        ("Linhas com corte", num(cortadas),
         f"{pct(cortadas/max(1,ind.linhas))} das linhas faturadas a menor"),
        (rot_valor, val_valor, sub_valor),
        ("Pedido ÷ cotado", "—" if pd.isna(aderencia) else pct(aderencia),
         "quantidade pedida sobre a quantidade cotada"),
    ], colunas=4)
    if ind.nivel_atendimento >= 0.999:
        st.caption("A base contém apenas pedidos com status Faturado, por isso o atendimento "
                   "fica em 100% por construção. Para medir corte de verdade, a planilha "
                   "precisa trazer também os pedidos faturados parcialmente.")

    atend = M.atendimento_fornecedor(df)
    altura = _altura_barras(atend)
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(atend, x="atendimento", y="fornecedor", orientation="h",
                     title="Nível de atendimento por fornecedor")
        fig.update_traces(marker_color=c["blue"],
                          hovertemplate="%{y}<br><b>%{x:.1%}</b><extra></extra>")
        fig.update_layout(xaxis_tickformat=".0%", xaxis_title=None, yaxis_title=None)
        mostrar(fig, altura,
                "**Nível de atendimento** = quantidade faturada ÷ quantidade pedida.\n\n"
                "Abaixo de 100% significa corte na nota: o item foi cotado, ganhou o pedido "
                "e não chegou.")
    with col2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=serie["mes"], y=serie["valor_pedido"], name="Valor pedido",
                                 mode="lines+markers", line=dict(color=c["blue"], width=2.2)))
        fig.add_trace(go.Scatter(x=serie["mes"], y=serie["valor_faturado"],
                                 name="Valor faturado", mode="lines+markers",
                                 line=dict(color=c["amber"], width=2.2)))
        fig.update_layout(title="Valor pedido × valor faturado por mês")
        mostrar(fig, altura,
                "A distância entre as duas linhas é o que foi pedido e **não faturado** — o "
                "corte que o fornecedor fez ao emitir a nota.")


# ......................................................... condições comerciais
def _condicoes(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    ped = M.pedidos_condicoes(df, p)
    cond = M.condicoes_fornecedor(df, p)
    total = float(ped["valor"].sum()) or 1.0
    com_prazo = ped[ped["prazo_dias"].notna()]
    prazo_medio = ((com_prazo["prazo_dias"] * com_prazo["valor"]).sum()
                   / max(1e-9, com_prazo["valor"].sum())) if len(com_prazo) else float("nan")
    curto = com_prazo[com_prazo["prazo_dias"] < p.prazo_pagamento_minimo]
    abaixo = int((ped["situacao"] == "abaixo do mínimo").sum())
    limite = int((ped["situacao"] == "no limite").sum())
    desconto = pd.to_numeric(df.get("Desc. Com. (%)", pd.Series(dtype=float)),
                             errors="coerce")

    st.subheader("Condições comerciais")
    linha_cartoes([
        ("Prazo médio de pagamento",
         "—" if pd.isna(prazo_medio) else f"{prazo_medio:.0f} dias",
         "ponderado pelo valor do pedido", "destaque"),
        (f"Valor com prazo < {p.prazo_pagamento_minimo} dias", brl0(curto["valor"].sum()),
         f"{pct(curto['valor'].sum()/total)} do valor · {num(len(curto))} pedidos"),
        ("Faturamento mínimo", f"{num(abaixo + limite)} pedidos",
         f"{num(abaixo)} abaixo · {num(limite)} a menos de {pct(p.pedido_minimo_folga,0)} "
         "acima"),
        ("Linhas com desconto comercial", num(int((desconto > 0).sum())),
         (f"desconto médio de {pct(desconto[desconto > 0].mean() / 100)} nessas linhas"
          if (desconto > 0).any() else "nenhuma linha com desconto")),
    ], colunas=4)

    if cond.empty:
        return
    altura = _altura_barras(cond)
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(cond.sort_values("prazo_medio"), x="prazo_medio", y="fornecedor",
                     orientation="h", title="Prazo médio de pagamento por fornecedor")
        fig.update_traces(marker_color=c["teal"],
                          hovertemplate="%{y}<br><b>%{x:.0f} dias</b><extra></extra>")
        fig.add_vline(x=p.prazo_pagamento_minimo, line=dict(color=c["amber"], dash="dot"))
        fig.update_layout(xaxis_title="dias", yaxis_title=None)
        mostrar(fig, altura,
                "Prazo de pagamento de cada pedido, em média ponderada pelo valor. A linha "
                f"pontilhada é o prazo mínimo desejado ({p.prazo_pagamento_minimo} dias, "
                "ajustável em Preferências): à esquerda dela, a farmácia paga antes de vender.")
    with col2:
        dados = cond.sort_values("pedido_medio")
        fig = go.Figure()
        fig.add_trace(go.Bar(y=dados["fornecedor"], x=dados["pedido_medio"], orientation="h",
                             name="Pedido médio", marker_color=c["blue"],
                             hovertemplate="%{y}<br>pedido médio <b>R$ %{x:,.2f}</b>"
                                           "<extra></extra>"))
        fig.add_trace(go.Bar(y=dados["fornecedor"], x=dados["minimo"], orientation="h",
                             name="Faturamento mínimo", marker_color=c["gray3"],
                             hovertemplate="%{y}<br>mínimo <b>R$ %{x:,.2f}</b><extra></extra>"))
        fig.update_layout(barmode="group", title="Pedido médio × faturamento mínimo",
                          xaxis_tickprefix="R$ ", xaxis_tickformat=",.0f", yaxis_title=None)
        mostrar(fig, altura,
                "**Faturamento mínimo** é o menor valor que o distribuidor aceita faturar. "
                "Quanto mais perto o pedido médio fica do mínimo, maior o risco de o pedido "
                "ser recusado ou cobrado com frete depois de um corte na nota.")

    st.markdown("**Condições por fornecedor**")
    tabela = cond[["fornecedor", "pedidos", "valor", "participacao", "prazo_medio", "minimo",
                   "pedido_medio", "abaixo", "no_limite", "desconto", "pedido_vs_cotado",
                   "atendimento", "margem", "representantes"]].rename(columns={
        "fornecedor": "Fornecedor", "pedidos": "Pedidos", "valor": "Valor",
        "participacao": "Participação", "prazo_medio": "Prazo médio (dias)",
        "minimo": "Fat. mínimo", "pedido_medio": "Pedido médio",
        "abaixo": "Abaixo do mín.", "no_limite": "No limite", "desconto": "Desconto (%)",
        "pedido_vs_cotado": "Pedido ÷ cotado", "atendimento": "Atendimento",
        "margem": "Margem", "representantes": "Representantes"})
    st.dataframe(tabela, width="stretch", hide_index=True, column_config={
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "Fat. mínimo": st.column_config.NumberColumn(format="R$ %.0f"),
        "Pedido médio": st.column_config.NumberColumn(format="R$ %.2f"),
        "Participação": st.column_config.NumberColumn(format="percent"),
        "Prazo médio (dias)": st.column_config.NumberColumn(format="%.0f"),
        "Desconto (%)": st.column_config.NumberColumn(format="%.2f"),
        "Pedido ÷ cotado": st.column_config.NumberColumn(format="percent"),
        "Atendimento": st.column_config.NumberColumn(format="percent"),
        "Margem": st.column_config.NumberColumn(format="percent")})

    st.markdown("**Desempenho por representante**")
    rep = M.por_representante(df, p).rename(columns={
        "representante": "Representante", "fornecedor": "Fornecedor", "pedidos": "Pedidos",
        "valor": "Valor", "prazo_medio": "Prazo médio (dias)",
        "abaixo": "Abaixo do mín.", "atendimento": "Atendimento"})
    st.dataframe(rep, width="stretch", hide_index=True, column_config={
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "Prazo médio (dias)": st.column_config.NumberColumn(format="%.0f"),
        "Atendimento": st.column_config.NumberColumn(format="percent")})


# ............................................................... preço e margem
def _preco_margem(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    var = M.variacao_custo(df, p)
    cesta = var[~var["suspeito"]]
    inflacao = ((cesta["valor"] * cesta["variacao"]).sum() / max(1e-9, cesta["valor"].sum())
                if len(cesta) else 0.0)
    disp = M.dispersao_preco(df)
    disp_ok = disp[disp["dispersao"] <= p.razao_preco_suspeita - 1]
    margem_geral = M.margem_ponderada(df)

    st.subheader("Preço e margem")
    linha_cartoes([
        ("Margem bruta média", "—" if pd.isna(margem_geral) else pct(margem_geral),
         "ponderada pela quantidade pedida", "destaque"),
        ("Inflação de custo da cesta", ("+" if inflacao >= 0 else "") + pct(inflacao),
         f"variação média ponderada em {num(len(cesta))} itens"),
        (f"Itens com alta acima de {pct(p.alta_custo_relevante,0)}",
         num(int((cesta["variacao"] > p.alta_custo_relevante).sum())),
         "entre a primeira e a última compra"),
        ("Itens com preços diferentes entre fornecedores", num(len(disp_ok)),
         f"diferença mediana de {pct(disp_ok['dispersao'].median() if len(disp_ok) else 0)}"),
    ], colunas=4)

    margem_cat = (M.margem_ponderada(df, por="Categoria Comercial")
                    .reset_index().sort_values("margem"))
    margem_forn = (M.margem_ponderada(df, por="Nome do Fornecedor")
                     .reset_index().sort_values("margem"))
    altura = _altura_barras(margem_cat, margem_forn)
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(margem_cat, x="margem", y="Categoria Comercial", orientation="h",
                     title="Margem bruta por categoria comercial")
        fig.update_traces(marker_color=c["green_c"],
                          hovertemplate="%{y}<br><b>%{x:.1%}</b><extra></extra>")
        fig.update_layout(xaxis_tickformat=".0%", xaxis_title=None, yaxis_title=None)
        mostrar(fig, altura,
                "**Margem bruta** = 1 − Σ(custo × quantidade) ÷ Σ(preço de venda × "
                "quantidade). Usa o preço registrado na cotação, não o praticado no caixa.")
    with col2:
        fig = px.bar(margem_forn, x="margem", y="Nome do Fornecedor", orientation="h",
                     title="Margem bruta por fornecedor")
        fig.update_traces(marker_color=c["teal"],
                          hovertemplate="%{y}<br><b>%{x:.1%}</b><extra></extra>")
        fig.update_layout(xaxis_tickformat=".0%", xaxis_title=None, yaxis_title=None)
        mostrar(fig, altura,
                "Mesma margem, agrupada por distribuidor. Fornecedor com margem baixa pode "
                "estar vendendo mais caro ou concentrando itens de margem naturalmente baixa.")

    indice = M.indice_custo(df, p)
    if len(indice):
        indice["mes"] = indice["ano_mes"].map(mes_label)
        fig = go.Figure(go.Scatter(x=indice["mes"], y=indice["indice"], mode="lines+markers",
                                   line=dict(color=c["purple"], width=2.4),
                                   hovertemplate="%{x}<br>índice <b>%{y:.1f}</b><extra></extra>"))
        fig.add_hline(y=100, line=dict(color=c["ink3"], dash="dot", width=1))
        fig.update_layout(title="Índice de custo da cesta (base 100 = primeira compra de cada item)")
        mostrar(fig, 320,
                "Cada compra é comparada com o custo da **primeira** compra do mesmo "
                "medicamento; o mês é a média dessas razões, ponderada pelo valor. Acima de "
                "100, os mesmos itens estão custando mais — inflação de custo, separada da "
                "mudança de mix. Razões implausíveis (erro de cadastro) ficam de fora.")

    st.markdown("**Mesmo item, preços diferentes entre fornecedores**")
    st.caption(f"Diferença entre o maior e o menor custo médio pago pelo mesmo medicamento. "
               f"Acima de {pct(p.razao_preco_suspeita-1,0)} é tratada como provável erro de "
               "cadastro (régua em Preferências).")
    disp_tab = disp.assign(erro=disp["dispersao"] > p.razao_preco_suspeita - 1).rename(columns={
        "medicamento": "Medicamento", "fornecedores": "Fornecedores",
        "menor_custo": "Menor custo", "maior_custo": "Maior custo",
        "dispersao": "Diferença", "valor": "Valor comprado", "erro": "Verificar cadastro"})
    st.dataframe(disp_tab.drop(columns="sku"), width="stretch", hide_index=True, height=320,
                 column_config={
                     "Menor custo": st.column_config.NumberColumn(format="R$ %.2f"),
                     "Maior custo": st.column_config.NumberColumn(format="R$ %.2f"),
                     "Valor comprado": st.column_config.NumberColumn(format="R$ %.2f"),
                     "Diferença": st.column_config.NumberColumn(format="percent")})

    st.markdown("**Medicamentos que mudaram de custo**")
    st.caption(f"Primeira × última compra, para itens com mais de uma compra e valor acima de "
               f"{brl0(p.valor_minimo_analise)}. Variações acima de "
               f"{pct(p.variacao_implausivel,0)} são marcadas como provável erro de cadastro.")
    cols = {"medicamento": "Medicamento", "custo_inicial": "Custo inicial",
            "custo_atual": "Custo atual", "variacao": "Variação", "compras": "Compras",
            "suspeito": "Verificar cadastro"}
    conf = {"Custo inicial": st.column_config.NumberColumn(format="R$ %.2f"),
            "Custo atual": st.column_config.NumberColumn(format="R$ %.2f"),
            "Variação": st.column_config.NumberColumn(format="percent")}
    col5, col6 = st.columns(2)
    with col5:
        st.markdown("Ficaram mais caros")
        st.dataframe(var[var["variacao"] > 0].rename(columns=cols)[list(cols.values())],
                     width="stretch", hide_index=True, height=340, column_config=conf)
    with col6:
        st.markdown("Ficaram mais baratos")
        st.dataframe(var[var["variacao"] < 0].sort_values("variacao")
                        .rename(columns=cols)[list(cols.values())],
                     width="stretch", hide_index=True, height=340, column_config=conf)


# ........................................................... mix e sazonalidade
def _mix(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    serie = M.serie_mensal(df)
    media = serie["valor_pedido"].mean()
    acima = serie[serie["valor_pedido"] > media * p.pico_mensal]["ano_mes"].map(mes_label).tolist()
    vezes = f"{p.pico_mensal:.2f}".replace(".", ",")
    total = float(df["valor_pedido"].sum()) or 1.0
    genericos = float(df.loc[df["Categoria Comercial"] == "Genérico", "valor_pedido"].sum())
    fab = M.por_dimensao(df, "Fabricante") if "Fabricante" in df.columns else pd.DataFrame()

    st.subheader("Mix e sazonalidade das compras")
    cartoes = [
        ("Média mensal pedida", brl(media), f"{len(serie)} meses com compra", "destaque"),
        ("Meses de pico", num(len(acima)),
         (", ".join(acima) + f" · acima de {vezes}× a média") if acima
         else f"nenhum mês acima de {vezes}× a média"),
        ("Participação dos genéricos", pct(genericos / total),
         f"{brl0(genericos)} do valor pedido"),
        ("Fabricantes diferentes", num(len(fab)),
         f"o maior concentra {pct(fab.iloc[0]['valor_pedido']/total)}" if len(fab) else "—"),
    ]
    linha_cartoes(cartoes, colunas=4)

    col1, col2 = st.columns(2)
    with col1:
        saz = df.groupby("mes", as_index=False)["valor_pedido"].sum()
        saz["rotulo"] = saz["mes"].map(lambda m: MESES[int(m)-1])
        fig = px.bar(saz, x="rotulo", y="valor_pedido",
                     title="Sazonalidade: valor pedido por mês do ano")
        fig.update_traces(marker_color=c["teal"],
                          hovertemplate="%{x}<br><b>R$ %{y:,.2f}</b><extra></extra>")
        fig.update_layout(xaxis_title=None, yaxis_title=None)
        mostrar(fig, 360,
                "**Sazonalidade** soma o valor pedido por mês do calendário, juntando todos "
                "os anos da base. Meses altos de forma repetida indicam padrão de demanda; "
                "um pico isolado provavelmente foi uma compra grande pontual.")
    with col2:
        if "M/L" in df.columns:
            ml = M.por_dimensao(df, "M/L")
            ml["M/L"] = ml["M/L"].map({"M": "M (preço monitorado)",
                                       "L": "L (preço liberado)"}).fillna(ml["M/L"])
            fig = px.pie(ml, names="M/L", values="valor_pedido", hole=0.58,
                         title="Valor pedido por regime de preço (coluna M/L)")
            fig.update_traces(marker=dict(colors=[c["blue"], c["teal"], c["gray3"]]),
                              textinfo="percent")
            mostrar(fig, 360,
                    "A coluna **M/L** da planilha separa os itens em dois grupos. A leitura "
                    "adotada — M = medicamento com preço monitorado pela CMED, L = preço "
                    "liberado (correlatos, cosméticos, alguns OTC) — é coerente com os "
                    "produtos de cada grupo, mas deve ser confirmada com quem emite a cotação.")
    if len(fab):
        fig = barras_h(fab.head(12), "valor_pedido", "Fabricante",
                       "Valor pedido por fabricante (12 maiores)", c["purple"])
        mostrar(fig, 400,
                "Mostra de quais laboratórios a farmácia mais compra, independentemente do "
                "distribuidor. Concentração alta num fabricante abre espaço para negociar "
                "condições direto com ele ou com o distribuidor que o representa.")
    _sazonalidade_vendas(p)


# ..................................................................... ABC × XYZ
def _abc_xyz(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    from paginas import movimentacao as PM
    pos = PM.posicao(p)
    bases = ["Vendas", "Compras"] if pos is not None else ["Compras"]
    base = st.segmented_control("Regularidade medida pelas", bases, default=bases[0],
                                key="xyz_base") or bases[0]
    if base == "Vendas":
        _abc_xyz_vendas(pos, p)
    else:
        _abc_xyz_compras(df, abc, p)


def _abc_xyz_vendas(pos: pd.DataFrame, p: Parametros) -> None:
    """ABC pelo faturamento × XYZ pela variação das vendas mensais."""
    from paginas import movimentacao as PM
    c = cores()
    rec, _ = PM.recorte()
    xyz = lembrar("mov_xyz", MV.xyz_vendas, rec, p)
    if xyz.empty:
        st.info("Sem vendas no recorte.")
        return
    abc_v = lembrar("abc_vendas", MV.curva_abc_vendas, pos, p)
    mz = abc_v.itens[["ean", "medicamento", "classe", "valor"]].merge(xyz, on="ean")
    cont = xyz["xyz"].value_counts()
    st.subheader("Matriz ABC × XYZ pelas vendas")
    st.caption(f"ABC = peso no faturamento; XYZ = variação das vendas mensais (X: CV ≤ "
               f"{p.cv_x:.2f} · Y: CV ≤ {p.cv_y:.2f} · Z: acima)".replace(".", ",") +
               ". Réguas em Preferências.")
    linha_cartoes([
        ("Regulares (X)", num(int(cont.get("X", 0))), "reposição automática", "destaque"),
        ("Variáveis (Y)", num(int(cont.get("Y", 0))), "estoque de segurança maior"),
        ("Irregulares (Z)", num(int(cont.get("Z", 0))), "acompanhamento ou encomenda"),
        ("Menos de 6 meses", num(int(cont.get("—", 0))), "histórico curto para classificar"),
    ], colunas=4)
    tab = pd.crosstab(mz["classe"], mz["xyz"]).reindex(index=list("ABC"),
                                                       columns=["X", "Y", "Z"], fill_value=0)
    val = mz.pivot_table(index="classe", columns="xyz", values="valor", aggfunc="sum",
                         fill_value=0).reindex(index=list("ABC"), columns=["X", "Y", "Z"],
                                               fill_value=0)
    fig = go.Figure(go.Heatmap(
        z=tab.values, x=["X · regular", "Y · variável", "Z · irregular"],
        y=["A · mais vendidos", "B", "C · menos vendidos"],
        colorscale=[[0, "#F5F8FA"], [1, c["teal"]]], showscale=False, xgap=3, ygap=3,
        text=[[f"{tab.loc[r, k]} produtos<br>{brl0(val.loc[r, k])}" for k in tab.columns]
              for r in tab.index], texttemplate="%{text}",
        hovertemplate="%{y} · %{x}<br>%{text}<extra></extra>"))
    fig.update_layout(title="Produtos e faturamento em cada combinação",
                      yaxis=dict(autorange="reversed", showgrid=False),
                      xaxis=dict(showline=False))
    mostrar(fig, 320,
            "Pontes (2013) combina as duas classificações para definir a política de cada "
            "produto:\n\n- **AX**: muito vendido e regular — reposição pelo ponto de pedido.\n"
            "- **AZ**: muito vendido e irregular — segurança maior e acompanhamento de perto.\n"
            "- **CZ**: pouco vendido e irregular — compra sob encomenda.\n\nCV = desvio ÷ média "
            "das vendas mensais desde a primeira venda do produto. É esta classificação que "
            "define a política *sob encomenda* em Reposição e Lotes.")
    grupo = st.selectbox("Mostrar os produtos da combinação",
                         ["Todas"] + [a + x for a in "ABC" for x in "XYZ"], key="xyz_grupo_v")
    lista = mz if grupo == "Todas" else mz[(mz["classe"] + mz["xyz"]) == grupo]
    st.dataframe(lista.drop(columns="ean").rename(columns={
        "medicamento": "Medicamento", "classe": "ABC", "valor": "Faturamento", "xyz": "XYZ",
        "cv": "CV", "media_mensal": "Venda média por mês", "desvio_mensal": "Desvio mensal",
        "meses": "Meses"}),
        width="stretch", hide_index=True, height=340, column_config={
            "Faturamento": st.column_config.NumberColumn(format="R$ %.2f"),
            "CV": st.column_config.NumberColumn(format="%.2f"),
            "Venda média por mês": st.column_config.NumberColumn(format="%.1f"),
            "Desvio mensal": st.column_config.NumberColumn(format="%.1f")})


def _abc_xyz_compras(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    xyz = M.classificacao_xyz(df, abc, p)
    itens, valor = M.matriz_abc_xyz(xyz)
    total = float(valor.values.sum()) or 1.0
    cv_x, cv_y = (f"{p.cv_x:.2f}".replace(".", ","), f"{p.cv_y:.2f}".replace(".", ","))

    st.subheader("Matriz ABC × XYZ")
    st.caption(f"ABC = peso no valor; XYZ = regularidade da compra trimestre a trimestre "
               f"(X: CV ≤ {cv_x} · Y: CV ≤ {cv_y} · Z: acima). Réguas em Preferências.")
    contagem = xyz["xyz"].value_counts()
    linha_cartoes([
        ("Regulares (X)", num(int(contagem.get("X", 0))), "reposição automática", "destaque"),
        ("Variáveis (Y)", num(int(contagem.get("Y", 0))), "estoque de segurança"),
        ("Irregulares (Z)", num(int(contagem.get("Z", 0))), "compra sob encomenda"),
        ("Classe A irregular (AZ)", num(int(itens.loc["A", "Z"])),
         f"{pct(valor.loc['A','Z']/total)} do valor"),
    ], colunas=4)

    texto = [[f"{num(int(itens.loc[a, x]))} itens<br>{pct(valor.loc[a, x]/total)} do valor"
              for x in "XYZ"] for a in "ABC"]
    fig = go.Figure(go.Heatmap(
        z=(valor / total).values, x=["X (regular)", "Y (variável)", "Z (irregular)"],
        y=["A", "B", "C"], text=texto, texttemplate="%{text}",
        colorscale=[[0, "#F3F0FA"], [1, c["purple"]]], showscale=False,
        hovertemplate="Classe %{y} · %{x}<br>%{text}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(title="Itens e participação no valor em cada combinação")
    mostrar(fig, 340,
            "Cada célula cruza o **peso financeiro** (ABC) com a **regularidade** (XYZ).\n\n"
            "- **AX / AY**: caros e previsíveis — ponto de pedido e estoque mínimo fixos.\n"
            "- **AZ**: caros e esporádicos — compra sob encomenda, decisão a cada cotação.\n"
            "- **CZ**: baratos e esporádicos — candidatos a sair do mix.\n\n"
            "O coeficiente de variação (CV) é o desvio-padrão da quantidade trimestral "
            "dividido pela média. Nesta base a maioria dos itens é Z porque foi comprada em "
            "poucas cotações: é um retrato real da compra, não erro de cálculo.")

    grupo = st.selectbox("Mostrar os itens da combinação",
                         ["Todas"] + [a + x for a in "ABC" for x in "XYZ"], key="xyz_grupo")
    lista = xyz if grupo == "Todas" else xyz[xyz["abc_xyz"] == grupo]
    st.dataframe(lista.drop(columns="sku").rename(columns={
        "medicamento": "Medicamento", "classe": "ABC", "xyz": "XYZ", "abc_xyz": "Combinação",
        "cv": "CV", "trimestres_com_compra": "Trimestres com compra",
        "media_trimestral": "Média por trimestre", "valor": "Valor", "compras": "Pedidos"}),
        width="stretch", hide_index=True, height=360, column_config={
            "CV": st.column_config.NumberColumn(format="%.2f"),
            "Média por trimestre": st.column_config.NumberColumn(format="%.1f"),
            "Valor": st.column_config.NumberColumn(format="R$ %.2f")})


# ............................................................. reposição e lote
def _reposicao(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    intervalo = M.intervalo_compras(df)
    idade = M.idade_na_entrega(df)
    hoje, _ = M.data_referencia(df, p)
    proximas = intervalo[intervalo["proxima_prevista"].between(hoje, hoje + pd.Timedelta(days=30))]

    st.subheader("Ritmo de compra e idade do lote")
    linha_cartoes([
        ("Itens com 2 ou mais compras", num(len(intervalo)),
         "base para medir o ritmo de reposição", "destaque"),
        ("Intervalo mediano entre compras",
         f"{intervalo['intervalo_medio'].median():.0f} dias" if len(intervalo) else "—",
         "metade dos itens volta a ser comprada antes disso"),
        ("Reposição prevista nos próximos 30 dias", num(len(proximas)),
         f"a partir de {data(hoje)}, pelo ritmo de cada item"),
        ("Validade restante na entrega",
         pct(idade["restante_medio"].mean()) if len(idade) else "—",
         "média da fração da validade que restava ao chegar"),
    ], colunas=4)

    altura = _altura_barras(idade)
    col1, col2 = st.columns(2)
    with col1:
        if len(intervalo):
            fig = px.histogram(intervalo, x="intervalo_medio", nbins=24,
                               title="Distribuição do intervalo médio entre compras")
            fig.update_traces(marker_color=c["blue"],
                              hovertemplate="%{x} dias<br><b>%{y} itens</b><extra></extra>")
            fig.update_layout(xaxis_title="dias entre compras", yaxis_title="itens")
            mostrar(fig, altura,
                    "Para cada medicamento comprado em dois dias ou mais, a média de dias "
                    "entre uma compra e a seguinte. Intervalo curto e estável indica item de "
                    "reposição contínua; intervalo longo, compra esporádica.")
    with col2:
        if len(idade):
            fig = px.bar(idade, x="restante_medio", y="fornecedor", orientation="h",
                         title="Validade restante na entrega por fornecedor",
                         custom_data=["idade_mediana", "linhas"])
            fig.update_traces(marker_color=c["amber"],
                              hovertemplate="%{y}<br><b>%{x:.0%}</b> da validade restante"
                                            "<br>lote com %{customdata[0]:.0f} dias de "
                                            "fabricação (mediana)<extra></extra>")
            fig.update_layout(xaxis_tickformat=".0%", xaxis_title=None, yaxis_title=None)
            mostrar(fig, altura,
                    "Fração da validade total (fabricação até vencimento) que ainda restava "
                    "quando o lote chegou. Quanto menor, mais velho o lote enviado pelo "
                    "fornecedor — e menos tempo para vender.")

    st.markdown("**Ritmo de reposição por medicamento**")
    st.caption("Próxima compra prevista = última compra + intervalo médio (estimativa pelo "
               "ritmo de compra; a reposição pela venda está em Reposição e Lotes).")
    tabela = intervalo.merge(abc.itens[["sku", "classe"]], on="sku", how="left")
    st.dataframe(tabela.drop(columns="sku").rename(columns={
        "medicamento": "Medicamento", "compras": "Dias de compra",
        "intervalo_medio": "Intervalo médio (dias)", "ultima_compra": "Última compra",
        "proxima_prevista": "Próxima prevista", "classe": "Classe ABC"}),
        width="stretch", hide_index=True, height=360, column_config={
            "Intervalo médio (dias)": st.column_config.NumberColumn(format="%.0f"),
            "Última compra": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Próxima prevista": st.column_config.DateColumn(format="DD/MM/YYYY")})


# .................................................................. estatística
VARIAVEIS = {
    "Custo unitário (R$)": ("linha", "Vl. Custo (R$)", "R$"),
    "Quantidade pedida por linha": ("linha", "Qtde. Ped.", "un"),
    "Valor da linha de pedido (R$)": ("linha", "valor_pedido", "R$"),
    "Valor por pedido (R$)": ("pedido", "valor", "R$"),
    "Dias entre compras do mesmo item": ("intervalo", "intervalo_medio", "dias"),
    "Margem bruta por item": ("margem", "margem", "%"),
}


def _estatistica(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    st.subheader("Estatística descritiva")
    nome = st.selectbox("Variável", list(VARIAVEIS), key="est_variavel")
    origem, coluna, unidade = VARIAVEIS[nome]
    if origem == "linha":
        serie = df[coluna]
    elif origem == "pedido":
        serie = M.pedidos_condicoes(df, p)[coluna]
    elif origem == "intervalo":
        serie = M.intervalo_compras(df)[coluna]
    else:
        serie = M.margem_ponderada(df, por="sku")
    d = M.descritiva(serie)
    if not d.get("n"):
        st.info("Sem dados para esta variável no recorte.")
        return

    def f(v):
        if pd.isna(v):
            return "—"
        if unidade == "R$":
            return brl(v)
        if unidade == "%":
            return pct(v)
        return f"{v:,.1f} {unidade}".replace(",", "@").replace(".", ",").replace("@", ".")

    linha_cartoes([
        ("Média", f(d["media"]), f"IC 95%: {f(d['ic_inf'])} a {f(d['ic_sup'])}", "destaque"),
        ("Mediana", f(d["mediana"]), "metade dos valores abaixo disso"),
        ("Moda", f(d["moda"]), "valor mais frequente"),
        ("Desvio-padrão", f(d["desvio"]),
         f"CV de {pct(d['cv'])}" if pd.notna(d["cv"]) else ""),
        ("1º quartil (Q1)", f(d["q1"]), "25% dos valores abaixo"),
        ("3º quartil (Q3)", f(d["q3"]), f"amplitude interquartil {f(d['iqr'])}"),
        ("Mínimo e máximo", f"{f(d['minimo'])} a {f(d['maximo'])}", f"{num(d['n'])} observações"),
        ("Valores atípicos", num(d["outliers"]),
         f"{pct(d['outliers']/d['n'])} fora de Q1 − 1,5·IQR e Q3 + 1,5·IQR"),
    ], colunas=4)

    s = pd.to_numeric(serie, errors="coerce").dropna()
    col1, col2 = st.columns([1.4, 1])
    with col1:
        fig = px.histogram(x=s, nbins=40, title=f"Distribuição: {nome}")
        fig.update_traces(marker_color=c["blue"],
                          hovertemplate="%{x}<br><b>%{y}</b> observações<extra></extra>")
        fig.add_vline(x=d["media"], line=dict(color=c["amber"], width=2),
                      annotation_text="média", annotation_position="top")
        fig.add_vline(x=d["mediana"], line=dict(color=c["purple"], dash="dot", width=2),
                      annotation_text="mediana", annotation_position="top left")
        fig.update_layout(xaxis_title=None, yaxis_title="observações", bargap=0.05)
        mostrar(fig, 340,
                "Quando a média fica bem à direita da mediana, a distribuição tem cauda "
                "longa: poucos valores altos puxam a média. Nesse caso a **mediana** "
                "representa melhor o caso típico.")
    with col2:
        fig = go.Figure(go.Box(y=s, name=nome, marker_color=c["purple"], boxpoints="outliers",
                               boxmean=True, hovertemplate="%{y}<extra></extra>"))
        fig.update_layout(title="Box-plot (quartis e atípicos)", showlegend=False)
        mostrar(fig, 340,
                "A caixa vai do 1º ao 3º quartil, com a mediana na linha central e a média "
                "tracejada. Os pontos isolados são valores atípicos pelo critério de 1,5 × "
                "a amplitude interquartil.\n\nO **intervalo de confiança de 95%** da média "
                "usa a aproximação normal (média ± 1,96 × desvio ÷ √n).")
