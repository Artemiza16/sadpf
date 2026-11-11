"""Fornecedores e Medicamentos — análise individual."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import metricas as M
from core.tema import (brl, brl0, cores, data, faixa, linha_cartoes, mes_label,
                       mostrar, num, pct)
from paginas.compras import barras_h


# --------------------------------------------------------------- FORNECEDORES
def _trocar_nomes() -> None:
    """Liga/desliga os nomes originais daqui mesmo, como em Preferências › Privacidade."""
    from core import parametros as PR
    novo = bool(st.session_state["forn_nomes_originais"])
    opcoes = st.session_state.get("_forn_opcoes", [])
    atual = st.session_state.get("forn_sel")
    if atual in opcoes:
        st.session_state["_forn_pos"] = opcoes.index(atual)
    st.session_state["pref_nomes_originais"] = novo
    p = st.session_state.get("params")
    if p is not None:
        p.nomes_originais = novo
        # vale nesta sessão de qualquer jeito; se não gravar, avisa em vez de falhar calado
        st.session_state["_privacidade_nao_salva"] = not PR.salvar(p)


def _privacidade() -> None:
    p = st.session_state.get("params")
    atual = bool(p.nomes_originais) if p is not None else False
    if st.session_state.pop("_privacidade_nao_salva", False):
        st.warning("Não foi possível salvar este ajuste: ele vale só até fechar o painel. "
                   "Confira em Preferências › Privacidade.", icon=":material/warning:")
    st.session_state["forn_nomes_originais"] = atual
    st.toggle("Mostrar os nomes originais dos fornecedores", key="forn_nomes_originais",
              on_change=_trocar_nomes,
              help="Desligado, os fornecedores e representantes aparecem com códigos "
                   "(Fornecedor A = o de maior volume), para apresentações. É o mesmo ajuste de "
                   "Preferências › Privacidade e fica salvo.")


def fornecedores(df: pd.DataFrame, abc: M.ResultadoABC) -> None:
    c = cores()
    resumo = M.por_dimensao(df, "Nome do Fornecedor")
    total = resumo["valor_pedido"].sum() or 1.0

    limite = st.session_state["params"].concentracao_fornecedor if "params" in st.session_state \
        else 0.40

    faixa("Quanto cada <b>distribuidor</b> representa nas compras e como ele se comporta "
          "em volume, entrega e validade. Serve para decidir com quem negociar.",
          "Fornecedores")

    _privacidade()
    st.subheader("Participação dos fornecedores")
    grafico = resumo.copy()
    grafico["participacao"] = grafico["valor_pedido"] / total
    fig = barras_h(grafico, "valor_pedido", "Nome do Fornecedor",
                   "Valor pedido por fornecedor")
    fig.update_traces(customdata=grafico[["participacao"]],
                      hovertemplate="%{y}<br><b>R$ %{x:,.2f}</b><br>"
                                    "%{customdata[0]:.1%} do total<extra></extra>")
    mostrar(fig, 340,
            "**Concentração de compras** é o quanto do valor sai de um único distribuidor."
            f"\n\nAcima de {pct(limite, 0)} em um só fornecedor (régua ajustável em "
            "Preferências), a farmácia perde referência de preço e fica exposta a falha de "
            "entrega.")

    st.subheader("Análise individual do fornecedor")
    opcoes = resumo["Nome do Fornecedor"].tolist()
    # ao trocar os nomes (privacidade), a mesma posição continua escolhida: a ordem é
    # por valor pedido e não muda com o nome
    pos = st.session_state.pop("_forn_pos", None)
    if pos is not None and pos < len(opcoes):
        st.session_state["forn_sel"] = opcoes[pos]
    st.session_state["_forn_opcoes"] = opcoes
    escolhido = st.selectbox("Escolha o fornecedor", opcoes, key="forn_sel")
    sub = df[df["Nome do Fornecedor"] == escolhido]
    ind = M.indicadores(sub)
    curtas = int(sub["validade_curta"].sum())

    st.markdown(f"#### {escolhido}")
    st.caption("Representante: " + ", ".join(sorted(sub["Representante"].astype(str).unique())))
    linha_cartoes([
        ("Período das compras", f"{data(ind.inicio)} a {data(ind.fim)}"),
        ("Participação no total", pct(ind.valor_pedido / total)),
        ("Pedidos", num(ind.pedidos), f"{num(ind.cotacoes)} cotações"),
        ("Valor total pedido", brl(ind.valor_pedido)),
        ("Medicamentos distintos", num(ind.medicamentos)),
        ("Nível de atendimento", pct(ind.nivel_atendimento),
         (f"{brl(ind.nao_faturado)} não faturado" if ind.nao_faturado >= 0
          else f"{brl(-ind.nao_faturado)} faturado além do pedido")),
        ("Valor médio por pedido", brl(ind.ticket_medio)),
        ("Entregas com validade curta", pct(curtas / max(1, len(sub)), 0),
         f"{num(curtas)} de {num(len(sub))} linhas"),
    ], colunas=4)

    # um embaixo do outro, em largura inteira: a série mensal e, logo abaixo, o que se
    # compra do fornecedor (antes lado a lado, apertados)
    s = M.serie_mensal(sub)
    s["mes"] = s["ano_mes"].map(mes_label)
    fig = go.Figure(go.Scatter(x=s["mes"], y=s["valor_pedido"], mode="lines+markers",
                               line=dict(color=c["teal"], width=2.5),
                               fill="tozeroy", fillcolor=c["teal"] + "1F",
                               hovertemplate="%{x}<br><b>R$ %{y:,.2f}</b><extra></extra>"))
    fig.update_layout(title="Valor pedido a este fornecedor por mês", yaxis_tickprefix="R$ ",
                      yaxis_tickformat=",.0f")
    mostrar(fig, 320,
            "Mesma série da Visão Geral, restrita a este distribuidor.\n\nMeses sem ponto "
            "significam que ele não venceu nenhum item naquela cotação — não que a "
            "farmácia deixou de comprar.")

    dims = {"Categoria comercial": "Categoria Comercial",
            "Forma farmacêutica": "Forma Farmacêutica"}
    ver = st.segmented_control("O que se compra dele, por", list(dims),
                               default="Categoria comercial", key="forn_dim") \
        or "Categoria comercial"
    comp = M.por_dimensao(sub, dims[ver])
    geral = M.por_dimensao(df, dims[ver]).set_index(dims[ver])["valor_pedido"]
    comp["part"] = comp["valor_pedido"] / max(ind.valor_pedido, 1)
    comp["part_geral"] = comp[dims[ver]].map(geral / max(total, 1))
    comp = comp.head(10)
    fig = go.Figure(go.Bar(
        y=comp[dims[ver]], x=comp["part"], orientation="h", marker_color=c["purple"],
        name="Este fornecedor",
        customdata=comp[["valor_pedido", "part_geral"]].values,
        hovertemplate="%{y}<br><b>%{x:.0%}</b> deste fornecedor · R$ %{customdata[0]:,.0f}"
                      "<br>%{customdata[1]:.0%} nas compras de todos<extra></extra>"))
    fig.add_trace(go.Scatter(
        y=comp[dims[ver]], x=comp["part_geral"], mode="markers", name="Todos os fornecedores",
        marker=dict(symbol="line-ns", size=18, line=dict(width=2.5, color=c["ink"])),
        hoverinfo="skip"))
    # rótulo depois do que terminar mais à direita (barra ou traço), para não encostar
    fim = comp[["part", "part_geral"]].max(axis=1)
    folga = max(comp["part"].max(), comp["part_geral"].max()) * 0.015
    fig.add_trace(go.Scatter(
        y=comp[dims[ver]], x=fim + folga, mode="text", showlegend=False, hoverinfo="skip",
        text=[f"{pct(v, 0)} · {brl0(r)}" for v, r in zip(comp["part"], comp["valor_pedido"])],
        textposition="middle right", textfont=dict(size=11, color=c["ink2"])))
    fig.update_layout(title=f"O que se compra dele, por {ver.lower()}",
                      xaxis=dict(tickformat=".0%", range=[0, max(comp["part"].max(),
                                 comp["part_geral"].max()) * 1.35]),
                      yaxis=dict(autorange="reversed"), showlegend=True)
    mostrar(fig, 120 + 38 * len(comp),
            f"Participação de cada {ver.lower()} no valor pedido a **este fornecedor**. O "
            "traço preto é a mesma participação nas compras de **todos** os fornecedores: "
            "barra muito acima do traço indica em que o distribuidor é forte (onde vale "
            "negociar com ele); barra abaixo, onde ele quase não é usado.")

    itens = (sub.groupby("sku", as_index=False)
                .agg(Medicamento=("medicamento", "first"),
                     Compras=("Pedido", "nunique"), Quantidade=("Qtde. Ped.", "sum"),
                     Valor=("valor_pedido", "sum"))
                .merge(abc.itens[["sku", "classe"]], on="sku", how="left")
                .rename(columns={"classe": "Classe ABC"})
                .sort_values("Valor", ascending=False).drop(columns="sku"))
    itens["Custo médio"] = itens["Valor"] / itens["Quantidade"].replace(0, pd.NA)
    st.caption(f"{num(len(itens))} medicamentos comprados deste fornecedor, do maior para "
               "o menor valor.")
    st.dataframe(itens, width="stretch", hide_index=True, height=360, column_config={
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "Custo médio": st.column_config.NumberColumn(format="R$ %.2f")})


# --------------------------------------------------------------- MEDICAMENTOS
def medicamentos(df: pd.DataFrame, abc: M.ResultadoABC) -> None:
    c = cores()
    itens = abc.itens

    faixa("A ficha de cada <b>medicamento</b>: onde comprar mais barato, se o custo e a margem "
          "pedem ação, quando comprar de novo e, com a movimentação, quanto repor. Escolha o "
          "produto na lista (dá para digitar o nome ou o código).", "Medicamentos")

    st.subheader("Ficha do medicamento")
    if itens["sku"].nunique() == 1:
        # o filtro global já deixou um só produto: a ficha abre direto nele
        _ficha(df, itens, itens["sku"].iloc[0])
        return
    # todos os medicamentos do recorte, do maior para o menor valor; a lista tem busca
    # própria (digitar filtra por qualquer parte do nome ou do código)
    rotulos = {f"{r['medicamento']} — {r['sku']} (classe {r['classe']})": r["sku"]
               for _, r in itens.iterrows()}
    escolhido = st.selectbox(f"Escolha o medicamento ({num(len(rotulos))} no recorte)",
                             list(rotulos), key="med_sel",
                             placeholder="Digite parte do nome ou o código")
    _ficha(df, itens, rotulos[escolhido])


def _acoes_do_item(sub: pd.DataFrame, ultimo: pd.Series, primeiro: pd.Series, variacao: float,
                   custo_medio: float, margem: float, preco_txt: str,
                   hoje: pd.Timestamp) -> list[tuple]:
    """Os quatro cartões da ficha: cada um diz o valor e o que fazer com ele.

    Mesmas regras do apoio à decisão: menor custo médio ponderado por fornecedor
    (economia por troca), régua de alta de custo, régua de margem apertada e o
    intervalo médio entre compras.
    """
    from core.parametros import Parametros
    p = st.session_state.get("params") or Parametros()
    cartoes = []

    # 1. onde comprar mais barato
    troca = M.melhor_fornecedor_item(sub)
    if troca:
        melhor, menor, maior, economia = (troca["fornecedor"], troca["menor"], troca["maior"],
                                          troca["economia"])
        if menor > 0 and maior / menor > p.razao_preco_suspeita:
            sub_txt = (f"custos de {brl(menor)} a {brl(maior)}: diferença grande demais, "
                       "conferir o cadastro antes de trocar")
        elif economia >= 1:
            sub_txt = (f"custo médio {brl(menor)}, {pct(1 - menor / maior, 0)} abaixo do mais "
                       f"caro · comprar sempre dele teria economizado {brl(economia)}")
        else:
            sub_txt = f"custo médio {brl(menor)} · as compras já saíram no menor custo"
        cartoes.append(("Comprar de", str(melhor), sub_txt, "destaque",
                        "estimado" if economia >= 1 else ""))
    else:
        unico = sub["Nome do Fornecedor"].dropna()
        cartoes.append(("Fornecedor", str(unico.iloc[0]) if len(unico) else "—",
                        "único fornecedor nas compras: cotar outro para ter referência de "
                        "preço", "destaque"))

    # 2. custo: subiu, caiu ou ficou estável
    custo_ult = ultimo["Vl. Custo (R$)"]
    if len(sub) < 2 or primeiro["Vl. Custo (R$)"] <= 0:
        cartoes.append(("Custo da última compra", brl(custo_ult),
                        f"uma compra só: sem histórico de custo · média {brl(custo_medio)}"))
    else:
        regua = pct(p.alta_custo_relevante, 0)
        var_txt = ("+" if variacao >= 0 else "−") + pct(abs(variacao), 0)
        if variacao > p.alta_custo_relevante:
            acao = f"{var_txt} desde a 1ª compra, acima da régua de {regua}: renegociar ou cotar"
        elif variacao < -p.alta_custo_relevante:
            acao = f"{var_txt} desde a 1ª compra: custo caiu, manter a negociação"
        else:
            acao = f"{var_txt} desde a 1ª compra: estável (régua de {regua})"
        cartoes.append(("Custo da última compra", brl(custo_ult), acao))

    # 3. margem contra a régua
    if pd.isna(margem):
        cartoes.append(("Margem bruta", "—", "sem preço de venda registrado: cadastrar o preço "
                                             "para medir a margem"))
    elif margem < p.margem_baixa:
        cartoes.append(("Margem bruta", pct(margem),
                        f"abaixo da régua de {pct(p.margem_baixa, 0)}: rever o preço de venda "
                        f"({preco_txt}) ou o custo"))
    else:
        cartoes.append(("Margem bruta", pct(margem),
                        f"acima da régua de {pct(p.margem_baixa, 0)} · preço de venda {preco_txt}"))

    # 4. quando comprar de novo
    ritmo = M.intervalo_compras(sub)
    if len(ritmo):
        r = ritmo.iloc[0]
        prox = r["proxima_prevista"]
        aviso =" · a data já passou: conferir o estoque" if prox < pd.Timestamp(hoje) else ""
        cartoes.append(("Próxima compra prevista", data(prox),
                        f"a cada {r['intervalo_medio']:.0f} dias, em média, em "
                        f"{num(int(r['compras']))} compras{aviso}", "", "projecao"))
    else:
        cartoes.append(("Próxima compra prevista", "—",
                        "comprado em um único dia: sem ritmo para prever"))
    return cartoes


def _ficha(df: pd.DataFrame, itens: pd.DataFrame, sku: str) -> None:
    """Ficha de um medicamento: compras, custo, fornecedores, reposição e histórico."""
    from paginas import movimentacao as PM
    from core import dados as D
    c = cores()
    sub = df[df["sku"] == sku].sort_values("dt", kind="stable")
    item = itens[itens["sku"] == sku].iloc[0]
    ind = M.indicadores(sub)
    primeiro, ultimo = sub.iloc[0], sub.iloc[-1]
    variacao = ((ultimo["Vl. Custo (R$)"] - primeiro["Vl. Custo (R$)"]) /
                primeiro["Vl. Custo (R$)"]) if len(sub) > 1 and primeiro["Vl. Custo (R$)"] > 0 else 0.0
    custo_medio = ((sub["Vl. Custo (R$)"] * sub["Qtde. Ped."]).sum()
                   / max(1, sub["Qtde. Ped."].sum()))
    # mesma margem ponderada das outras telas; sem preço de venda, não há margem
    margem = M.margem_ponderada(sub)
    margem_txt = "—" if pd.isna(margem) else pct(margem)
    preco_venda = ultimo["Preço de Venda Unitário (R$)"]
    preco_txt = brl(preco_venda) if pd.notna(preco_venda) and preco_venda > 0 else "—"

    st.markdown(f"#### {item['medicamento']}")
    st.caption(f"Código {sku} · classe {item['classe']} · posição #{int(item['posicao'])} · "
               f"{ultimo['Forma Farmacêutica']} · {ultimo['Categoria Comercial']} · "
               f"{ultimo['Fabricante']} — {brl(ind.valor_pedido)} em {num(ind.pedidos)} "
               f"pedidos ({num(ind.qtd_pedida)} unidades) de {data(primeiro['dt'])} a "
               f"{data(ultimo['dt'])}")

    linha_cartoes(_acoes_do_item(sub, ultimo, primeiro, variacao, custo_medio, margem,
                                 preco_txt, df["dt"].max()), colunas=4)

    col1, col2 = st.columns(2)
    with col1:
        mensal = M.custo_ponderado(sub, "ano_mes").reset_index(name="custo")
        mensal["mes"] = mensal["ano_mes"].map(mes_label)
        fig = go.Figure(go.Scatter(x=mensal["mes"], y=mensal["custo"], mode="lines+markers",
                                   line=dict(color=c["purple"], width=2.5)))
        fig.update_traces(hovertemplate="%{x}<br><b>R$ %{y:,.2f}</b><extra></extra>")
        fig.update_layout(title="Custo unitário médio por mês")
        mostrar(fig, 300,
                "**Custo médio ponderado** = soma(custo × quantidade) ÷ soma(quantidade) de "
                "cada mês.\n\nPonderar pela quantidade evita que uma compra pequena e cara "
                "distorça o mês inteiro, o que aconteceria numa média simples.")
    with col2:
        fig = barras_h(M.por_dimensao(sub, "Nome do Fornecedor"), "valor_pedido",
                       "Nome do Fornecedor", "Valor pedido por fornecedor", c["teal"])
        mostrar(fig, 300,
                "Quando o mesmo medicamento aparece com mais de um distribuidor, dá para "
                "comparar o custo que cada um praticou.\n\nEssa comparação é a base do "
                "cálculo de **economia por troca de fornecedor**.")

    p = st.session_state.get("params")
    ean = D.texto_chave(sub["EAN"]).iloc[0] if "EAN" in sub.columns else None
    if p is not None and ean and not PM.dente_serra_produto(ean, p, titulo=True):
        st.caption("Sem movimentação deste produto no recorte: os indicadores de reposição e o "
                   "dente de serra aparecem quando ele estiver no livro de movimentação.")

    st.markdown("**Histórico de compras do item**")
    hist = sub[["dt", "Cotação", "Pedido", "Nome do Fornecedor", "Qtde. Ped.",
                "Qtde. Fat.", "Vl. Custo (R$)", "valor_pedido", "validade",
                "Faixa de Recebimento"]].rename(columns={
        "dt": "Data", "Nome do Fornecedor": "Fornecedor", "Qtde. Ped.": "Qtd. ped.",
        "Qtde. Fat.": "Qtd. fat.", "Vl. Custo (R$)": "Custo unit.",
        "valor_pedido": "Valor", "validade": "Validade",
        "Faixa de Recebimento": "Vida útil na entrega"})
    st.dataframe(hist, width="stretch", hide_index=True, column_config={
        "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Validade": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Custo unit.": st.column_config.NumberColumn(format="R$ %.2f"),
        "Valor": st.column_config.NumberColumn(format="R$ %.2f")})
