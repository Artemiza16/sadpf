"""Previsão de Compras: orçamento provável e itens candidatos para a próxima cotação."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import metricas as M
from core import previsao as PV
from core.memoria import lembrar
from core.parametros import Parametros
from core.tema import (MESES, brl, brl0, cores, data, faixa, linha_cartoes, mes_label,
                       mostrar, num, pct)


def _nome_mes(periodo: pd.Period) -> str:
    return f"{MESES[periodo.month - 1]}/{periodo.year}"


VISOES = {"Pelas compras": ":material/shopping_cart:",
          "Pelas vendas": ":material/point_of_sale:"}


def previsao(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    from paginas import movimentacao as PM
    pos = PM.posicao(p)
    visoes = list(VISOES) if pos is not None else list(VISOES)[:1]
    visao = st.segmented_control("Base da previsão", visoes, default=visoes[0],
                                 key="prev_visao", format_func=lambda v: f"{VISOES[v]} {v}")
    if (visao or visoes[0]) == visoes[0]:
        _por_compras(df, abc, p)
    else:
        _por_movimentacao(pos, p, df)


def _fechamento(rec, df: pd.DataFrame | None, pv: dict) -> None:
    """Realizado do mês em curso, fechamento projetado e o mês seguinte."""
    from core import movimentacao as MV
    from core.tema import selo_natureza
    c = cores()
    compras_prev = PV.orcamento(df)["media"] if df is not None and len(df) else None
    erro = pv.get("erro_mediano") if pv.get("melhor") else None
    f = lembrar("mov_fechamento", MV.projecao_fechamento, rec, compras_prev, erro)
    if not f:
        st.info("Sem movimentação no recorte para projetar o fechamento.")
        return
    mes, prox = f["mes"], f["proximo_mes"]
    st.subheader("Fechamento projetado")
    if f["fechado"]:
        st.caption(f"O recorte termina no fim de {_nome_mes(mes)}: o mês já está fechado e a "
                   f"projeção é para {_nome_mes(prox)}.")
    else:
        st.caption(f"{_nome_mes(mes)} está em curso: {f['dias_feitos']} de {f['dias_mes']} dias "
                   f"realizados (até {data(f['fim'])}). O fechamento soma o realizado à projeção "
                   f"dos {f['faltam']} dias que faltam; {_nome_mes(prox)} é projetado inteiro.")
    st.markdown("<div class='nat-legenda'><span><b>Realizado</b> observado nos movimentos</span>"
                f"<span>{selo_natureza('estimado')} cálculo com premissa</span>"
                f"<span>{selo_natureza('projecao')} valor futuro</span></div>",
                unsafe_allow_html=True)
    real, curso, proximo = f["realizado"], f["curso"], f["proximo"]
    faixa_v = (f" (± {pct(erro, 0)}: {brl0(proximo['vendas'] * (1 - erro))} a "
               f"{brl0(proximo['vendas'] * (1 + erro))})") if erro else ""
    linha_cartoes(
        ([] if f["fechado"] else [
            (f"Vendas realizadas em {_nome_mes(mes)}", brl0(real["vendas"]),
             f"até {data(f['fim'])} · margem de {brl0(real['margem'])}"),
            (f"Fechamento de {_nome_mes(mes)}", brl0(curso["vendas"]),
             f"realizado + {f['faltam']} dias × {brl0(f['ritmo_diario'])}/dia", "destaque",
             "projecao")]) +
        [(f"Vendas em {_nome_mes(prox)}", brl0(proximo["vendas"]),
          f"{prox.days_in_month} dias × {brl0(f['ritmo_diario'])}/dia{faixa_v}", "",
          "projecao"),
         (f"Estoque ao fim de {_nome_mes(prox)}", brl0(proximo["estoque_fim"]),
          f"hoje: {brl0(f['estoque_atual'])} · com compras de {brl0(f['compras_prev'])}/mês",
          "", "projecao")], colunas=4)

    linhas = [
        ("Vendas", real["vendas"], curso["vendas"], proximo["vendas"],
         "ritmo diário de venda dos últimos 30 dias × dias"),
        ("Custo do que foi vendido", real["cmv"], curso["cmv"], proximo["cmv"],
         f"vendas × (1 − margem média de {pct(f['margem_pct'], 1)} dos 3 últimos meses fechados)"),
        ("Margem bruta", real["margem"], curso["margem"], proximo["margem"],
         "vendas − custo do que foi vendido"),
        ("Compras", real["compras"], curso["compras"], proximo["compras"],
         "orçamento pelas compras: média mensal do histórico"),
        ("Perdas por validade", real["perdas"], curso["perdas"], proximo["perdas"],
         f"média mensal dos 6 últimos meses fechados ({brl0(f['perdas_mes'])})"),
        ("Estoque ao fim do mês (a custo)", f["estoque_atual"], curso["estoque_fim"],
         proximo["estoque_fim"], "estoque + compras − custo vendido − perdas"),
    ]
    tabela = pd.DataFrame(linhas, columns=["Indicador", f"Realizado até {data(f['fim'])}",
                                           f"Fechamento de {_nome_mes(mes)} (projeção)",
                                           f"{_nome_mes(prox)} (projeção)", "Premissa"])
    if f["fechado"]:
        tabela = tabela.drop(columns=[f"Fechamento de {_nome_mes(mes)} (projeção)"])
    for col in tabela.columns[1:-1]:
        tabela[col] = tabela[col].map(brl0)
    st.dataframe(tabela, hide_index=True, width="stretch",
                 column_config={"Premissa": st.column_config.TextColumn(width="large")})

    s = MV.serie_mensal(rec).set_index("ano_mes")
    hist = [x for x in s.index if pd.Period(x, "M") < mes][-12:]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[mes_label(x) for x in hist], y=s.loc[hist, "faturamento"],
                         name="Realizado", marker_color=c["teal"],
                         hovertemplate="%{x}<br>realizado <b>R$ %{y:,.0f}</b><extra></extra>"))
    if not f["fechado"]:
        fig.add_trace(go.Bar(x=[mes_label(str(mes))], y=[real["vendas"]], name="Realizado no mês",
                             marker_color=c["teal"], showlegend=False,
                             hovertemplate="%{x}<br>realizado <b>R$ %{y:,.0f}</b><extra></extra>"))
        fig.add_trace(go.Bar(x=[mes_label(str(mes))], y=[curso["vendas"] - real["vendas"]],
                             name="Projeção", marker_color=c["teal_l"], opacity=0.75,
                             hovertemplate="%{x}<br>projeção do restante <b>R$ %{y:,.0f}</b>"
                                           "<extra></extra>"))
    fig.add_trace(go.Bar(x=[mes_label(str(prox))], y=[proximo["vendas"]], name="Projeção do mês",
                         marker_color=c["teal_l"], opacity=0.75, showlegend=f["fechado"],
                         error_y=dict(type="data", array=[proximo["vendas"] * erro],
                                      color=c["ink3"]) if erro else None,
                         hovertemplate="%{x}<br>projeção <b>R$ %{y:,.0f}</b><extra></extra>"))
    fig.update_layout(title="Vendas por mês: realizado e projeção", barmode="stack",
                      yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
    mostrar(fig, 360,
            "**Barras cheias**: vendas realizadas. **Barras claras**: projeção — no mês em curso, "
            "só a parte que falta; no mês seguinte, o mês inteiro, com a faixa de ± erro mediano "
            "do teste no histórico.\n\nA projeção repete o ritmo de venda recente, o mesmo "
            "princípio do método *último mês*, que teve o menor erro no teste abaixo. Margem, "
            "perdas e compras usam as médias indicadas na tabela; são premissas, não "
            "resultados.")


def _por_movimentacao(pos: pd.DataFrame, p: Parametros, df: pd.DataFrame | None = None) -> None:
    from core import movimentacao as MV
    from paginas import movimentacao as PM
    c = cores()
    rec, _ = PM.recorte()
    faixa("Pelas vendas, a previsão projeta o <b>fechamento do mês</b> e do mês seguinte e, "
          "item a item, <b>quanto comprar</b> para não faltar nem sobrar, com o acerto medido no "
          "próprio histórico.", "Previsão de Compras")

    pv = lembrar("mov_prev_vendas", MV.previsao_vendas, rec)
    _fechamento(rec, df, pv)

    # ------------------------------------------- como a projeção foi testada
    st.subheader("Como a projeção foi testada")
    if pv["melhor"] is None:
        st.info("O período filtrado tem poucos meses completos para testar um método.")
    else:
        linha_cartoes([
            ("Método de menor erro", pv["melhor"], "escolhido no teste no histórico", "destaque"),
            ("Erro mediano no teste", pct(pv["erro_mediano"], 0),
             "do faturamento de cada mês testado"),
            ("Meses completos", num(len(pv["serie"])), "o mês de abertura e o mês em curso "
                                                        "ficam de fora"),
        ], colunas=3)
        s = pv["serie"]
        teste = pv["teste"][pv["teste"]["metodo"] == pv["melhor"]]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=s["ano_mes"].map(mes_label), y=s["faturamento"],
                             name="Faturamento realizado", marker_color=c["blue_l"],
                             hovertemplate="%{x}<br><b>R$ %{y:,.2f}</b><extra></extra>"))
        fig.add_trace(go.Scatter(x=teste["mes"].map(mes_label), y=teste["previsto"],
                                 mode="lines+markers", name=f"Previsto ({pv['melhor'].lower()})",
                                 line=dict(color=c["purple"], dash="dot"),
                                 hovertemplate="%{x}<br>previsto <b>R$ %{y:,.2f}</b>"
                                               "<extra></extra>"))
        fig.update_layout(title="Faturamento realizado × previsto no teste",
                          yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
        mostrar(fig, 340,
                "Quatro métodos simples foram testados: para cada mês, a previsão usa só os "
                "meses anteriores. Vence o de menor erro mediano.\n\nCuidado de leitura: o "
                "número de produtos ativos cresce ao longo do período (cada item só entra no "
                "estoque na primeira compra), o que puxa o faturamento para cima. Por isso "
                "métodos de memória curta tendem a ganhar.")
        met = pv["metodos"].rename(columns={"metodo": "Método", "meses": "Meses testados",
                                            "erro_mediano": "Erro mediano",
                                            "erro_medio": "Erro médio"})
        st.dataframe(met, hide_index=True, width="stretch", column_config={
            "Erro mediano": st.column_config.NumberColumn(format="percent"),
            "Erro médio": st.column_config.NumberColumn(format="percent")})

    # ------------------------------------------------------- lista de compra
    st.subheader("O que comprar")
    agora = pos[pos["repor_agora"]]
    linha_cartoes([
        ("Produtos no ponto de pedido", num(len(agora)),
         f"{num(agora['qtd_sugerida'].sum())} unidades · {brl0(agora['valor_sugerido'].sum())}",
         "roxo", "estimado"),
        ("Na próxima cotação", num(int(((pos["qtd_sugerida"] > 0) & ~pos["repor_agora"]).sum())),
         "abaixo da cobertura desejada", "", "estimado"),
        ("Total sugerido", brl0(pos["valor_sugerido"].sum()),
         f"{num(pos['qtd_sugerida'].sum())} unidades", "", "estimado"),
    ], colunas=3)
    paginas = st.session_state.get("paginas_menu", {})
    if "Reposição e Lotes" in paginas:
        st.page_link(paginas["Reposição e Lotes"], icon=":material/add_shopping_cart:",
                     label="Ver a lista completa, o lote econômico e o acerto da demanda")


def _por_compras(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    orc = lembrar("prev_orcamento", PV.orcamento, df)
    alvo = orc["alvo"]
    faixa(f"Planejamento da <b>próxima cotação ({_nome_mes(alvo)})</b> pela rotina de compras: "
          "quanto deve ser gasto e quais itens recorrentes conferir antes de cotar. É uma "
          "projeção, não um pedido pronto.", "Previsão de Compras")

    # -------------------------------------------------------- 1. orçamento
    st.subheader(f"Orçamento provável para {_nome_mes(alvo)}")
    st.caption(f"Próximo mês depois da última compra registrada ({data(df['dt'].max())}). "
               "Com cotações novas na base, a previsão avança sozinha.")
    linha_cartoes([
        ("Faixa provável de gasto", f"{brl0(orc['faixa_min'])} a {brl0(orc['faixa_max'])}",
         "média mensal ± 1 desvio-padrão", "destaque", "projecao"),
        ("Gasto médio mensal", brl(orc["media"]), f"{len(orc['serie'])} meses de histórico"),
        ("Média dos últimos 3 meses", brl(orc["media_3m"]),
         "acima da média" if orc["media_3m"] > orc["media"] else "abaixo da média"),
        ("Acerto da faixa no histórico", pct(orc["acerto_faixa"], 0),
         f"dos {len(orc['teste'])} meses testados; erro mediano de "
         f"{pct(orc['erro_mediano'], 0)}"),
    ], colunas=4)

    serie = orc["serie"].assign(rotulo=lambda d: d["mes"].astype(str).map(mes_label))
    fig = go.Figure()
    fig.add_trace(go.Bar(x=serie["rotulo"], y=serie["valor"], name="Gasto realizado",
                         marker_color=c["blue_l"],
                         hovertemplate="%{x}<br><b>R$ %{y:,.2f}</b><extra></extra>"))
    rot_alvo = mes_label(str(alvo))
    fig.add_trace(go.Scatter(
        x=[rot_alvo], y=[orc["media"]], mode="markers", name="Previsão (faixa)",
        marker=dict(color=c["purple"], size=12, symbol="diamond"),
        error_y=dict(type="data", symmetric=False, color=c["purple"], thickness=2, width=10,
                     array=[orc["faixa_max"] - orc["media"]],
                     arrayminus=[orc["media"] - orc["faixa_min"]]),
        hovertemplate=f"{rot_alvo} (previsão)<br>média <b>R$ %{{y:,.2f}}</b><br>faixa "
                      f"{brl0(orc['faixa_min'])} a {brl0(orc['faixa_max'])}<extra></extra>"))
    fig.add_hline(y=orc["media"], line=dict(color=c["purple"], dash="dot", width=1))
    fig.update_layout(title=f"Gasto mensal e faixa prevista para {_nome_mes(alvo)}", yaxis_tickprefix="R$ ",
                      yaxis_tickformat=",.0f")
    mostrar(fig, 360,
            "As barras são o valor pedido em cada mês. O losango é a previsão para o próximo "
            "mês: a média de todo o histórico, com a faixa de **± 1 desvio-padrão**.\n\n"
            "Por que a média de todo o histórico? No teste com os meses passados, ela errou "
            "menos que a média dos últimos 3 ou 6 meses e que o último mês: as cotações desta "
            "farmácia variam muito de um mês para o outro, e a média longa amortece isso.")

    # ------------------------------------------------------- 2. candidatos
    cand = lembrar("prev_candidatos", PV.candidatos, df, abc, p)
    st.subheader("Itens candidatos para a próxima cotação")
    st.caption("Medicamentos comprados em pelo menos dois meses. A **chance** é a fração dos "
               "meses em que o item foi comprado; o **ritmo** compara a última compra com o "
               "intervalo de costume.")
    if cand.empty:
        st.info("Nenhum item recorrente com chance suficiente no período filtrado.")
    else:
        contagem = cand["chance"].value_counts()
        prev_mes = cand[cand["ritmo"].isin(["prevista para o mês", "atrasada"])]
        linha_cartoes([
            ("Chance alta", num(int(contagem.get("alta", 0))),
             f"comprados em {pct(p.previsao_chance_alta, 0)}+ dos meses · "
             + brl0(cand.loc[cand["chance"] == "alta", "valor_estimado"].sum()),
             "roxo", "projecao"),
            ("Chance média", num(int(contagem.get("média", 0))),
             brl0(cand.loc[cand["chance"] == "média", "valor_estimado"].sum()) + " estimados"),
            ("Chance baixa", num(int(contagem.get("baixa", 0))),
             f"a partir de {pct(p.previsao_chance_minima, 0)} dos meses · "
             + brl0(cand.loc[cand["chance"] == "baixa", "valor_estimado"].sum())),
            ("No ritmo para o mês", num(len(prev_mes)),
             "compra prevista para o mês ou atrasada"),
        ], colunas=4)

        with st.container(border=True):
            st.markdown("<div class='barra-filtros'>Filtrar a lista</div>",
                        unsafe_allow_html=True)
            f1, f2, f3 = st.columns([1.2, 2.2, 0.9], vertical_alignment="bottom")
            chances = f1.pills("Chance", ["alta", "média", "baixa"], selection_mode="multi",
                               default=["alta", "média"], key="prev_chance")
            ritmos = f2.pills("Ritmo", ["prevista para o mês", "atrasada", "mais adiante",
                                        "parada"], selection_mode="multi", default=[],
                              key="prev_ritmo",
                              help="Sem seleção, todos os ritmos entram na lista.")
            so_a = f3.toggle("Só classe A", key="prev_so_a")
        lista = cand[cand["chance"].isin(chances or ["alta", "média", "baixa"])]
        if ritmos:
            lista = lista[lista["ritmo"].isin(ritmos)]
        if so_a:
            lista = lista[lista["classe"] == "A"]
        st.caption(f"**{num(len(lista))} itens · {brl(lista['valor_estimado'].sum())}** "
                   "(projeção). Quantidade = mediana das quantidades pedidas por compra; valor "
                   "= quantidade × último custo pago.")
        tabela = lista.drop(columns="sku").rename(columns={
            "medicamento": "Medicamento", "classe": "ABC", "chance": "Chance",
            "prob": "Meses com compra (%)", "ritmo": "Ritmo",
            "meses_com_compra": "Meses com compra", "intervalo_medio": "Intervalo (dias)",
            "ultima": "Última compra", "qtd_estimada": "Qtd. estimada",
            "custo_ultimo": "Último custo", "valor_estimado": "Valor estimado",
            "ultimo_fornecedor": "Último fornecedor",
            "fornecedor_menor_custo": "Fornecedor de menor custo", "menor_custo": "Menor custo"})
        st.dataframe(tabela, width="stretch", hide_index=True, height=420, column_config={
            "Meses com compra (%)": st.column_config.ProgressColumn(
                format="percent", min_value=0, max_value=1),
            "Intervalo (dias)": st.column_config.NumberColumn(format="%.0f"),
            "Última compra": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Qtd. estimada": st.column_config.NumberColumn(format="%.0f"),
            "Último custo": st.column_config.NumberColumn(format="R$ %.2f"),
            "Valor estimado": st.column_config.NumberColumn(format="R$ %.2f"),
            "Menor custo": st.column_config.NumberColumn(format="R$ %.2f")})
        st.download_button(
            "Baixar lista de candidatos (CSV)",
            tabela.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            file_name=f"candidatos_{alvo}.csv", mime="text/csv",
            icon=":material/download:")

    # --------------------------------------------------- 3. confiabilidade
    teste = lembrar("prev_confiabilidade", PV.confiabilidade, df, p)
    conf = PV.resumo_confiabilidade(teste)
    st.subheader("Quão confiável é a previsão")
    st.caption(f"Teste com os meses passados ({conf['meses']} meses): para cada mês, a "
               "previsão foi refeita só com os dados anteriores a ele e comparada com o que de "
               "fato foi comprado.")
    faixas = conf["faixas"]
    taxa = lambda ch: (pct(faixas.loc[ch, "taxa"], 0)  # noqa: E731
                       if ch in faixas.index and pd.notna(faixas.loc[ch, "taxa"]) else "—")
    linha_cartoes([
        ("Confirmação — chance alta", taxa("alta"),
         "dos itens previstos foram comprados no mês", "destaque"),
        ("Confirmação — chance média", taxa("média"), "dos itens previstos"),
        ("Valor coberto pela lista", pct(conf["cobertura_valor"], 0),
         "do valor comprado no mês estava entre os candidatos"),
        ("Itens novos a cada mês", pct(conf["itens_novos"], 0),
         "nunca tinham sido comprados — impossíveis de prever"),
    ], colunas=4)

    t = orc["teste"]
    if len(t):
        t = t.assign(rotulo=t["mes"].map(mes_label))
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t["rotulo"], y=t["faixa_max"], mode="lines",
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=t["rotulo"], y=t["faixa_min"], mode="lines",
                                 line=dict(width=0), fill="tonexty",
                                 fillcolor=c["purple"] + "26", name="Faixa prevista",
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=t["rotulo"], y=t["previsto"], mode="lines",
                                 line=dict(color=c["purple"], dash="dot"), name="Previsto",
                                 hovertemplate="%{x}<br>previsto <b>R$ %{y:,.2f}</b>"
                                               "<extra></extra>"))
        fig.add_trace(go.Scatter(x=t["rotulo"], y=t["real"], mode="lines+markers",
                                 line=dict(color=c["blue"], width=2.4), name="Realizado",
                                 hovertemplate="%{x}<br>realizado <b>R$ %{y:,.2f}</b>"
                                               "<extra></extra>"))
        fig.update_layout(title="Teste no histórico: gasto previsto × realizado", yaxis_tickprefix="R$ ",
                          yaxis_tickformat=",.0f")
        mostrar(fig, 340,
                "Para cada mês, a faixa roxa é o que o método teria previsto usando só os "
                "meses anteriores. Quando a linha azul fica dentro da faixa, a previsão "
                f"acertou — o que aconteceu em {pct(orc['acerto_faixa'], 0)} dos meses.")

    with st.expander("Como ler e usar esta previsão"):
        st.markdown(
            "**O que ela é:** um ponto de partida para montar a próxima cotação — um "
            "orçamento de referência e uma lista de itens recorrentes para conferir.\n\n"
            "**O que ela não é:** um pedido pronto. Ela segue o ritmo de compra, e "
            f"cerca de {pct(conf['itens_novos'], 0)} dos itens de cada mês são compras novas, "
            "que nenhum histórico antecipa. Por isso mesmo a faixa de chance alta se confirma "
            f"em {taxa('alta')} dos casos.\n\n"
            "**Como usar:** conferir no balcão os itens de chance alta e os que estão "
            "*atrasados* no ritmo; para os de classe A, cotar com o fornecedor de menor custo "
            "já registrado; usar a faixa de gasto para não comprometer o caixa do mês.\n\n"
            "**Pelas vendas:** a visão *Pelas vendas*, no topo da tela, usa a demanda medida "
            "na movimentação (giro, cobertura e ponto de pedido) em vez do ritmo de compra.")
