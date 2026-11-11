"""Visão Geral, Gestão de Compras e Pedidos."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import decisao as Dc
from core import metricas as M
from core.memoria import lembrar
from core.parametros import Parametros
from core.tema import (brl, brl0, cascata, cores, data, faixa, linha_cartoes, mes_label,
                       mostrar, num, pct, selo_natureza)


def _serie(df: pd.DataFrame) -> pd.DataFrame:
    s = M.serie_mensal(df)
    if not s.empty:
        s["mes"] = s["ano_mes"].map(mes_label)
    return s


def barras_h(dados: pd.DataFrame, x: str, y: str, titulo: str,
             cor: str | None = None) -> go.Figure:
    c = cores()
    fig = px.bar(dados.sort_values(x), x=x, y=y, orientation="h", title=titulo)
    fig.update_traces(marker_color=cor or c["blue"],
                      hovertemplate="%{y}<br><b>R$ %{x:,.2f}</b><extra></extra>")
    # eixo em reais com ponto de milhar (R$ 9.000), em vez da abreviação "9k"
    fig.update_layout(xaxis_title=None, yaxis_title=None,
                      xaxis_tickprefix="R$ ", xaxis_tickformat=",.0f")
    return fig


# --------------------------------------------------------------- VISÃO GERAL
def mapa_financeiro(insights: list, mv: dict | None) -> pd.DataFrame:
    """Ganhos possíveis, perdas e riscos do período numa tabela só.

    Os valores vêm dos mesmos pontos do apoio à decisão (mesmas réguas e
    filtros), para que a Visão Geral e o painel de decisão nunca discordem.
    Cada linha diz se o valor é observado ou estimado e a tela onde agir.
    """
    por_id = {i.id: i for i in insights}
    linhas = []

    def add(grupo, nome, valor, natureza, tela, explicacao):
        if valor and valor > 0:
            linhas.append({"grupo": grupo, "item": nome, "valor": float(valor),
                           "natureza": natureza, "tela": tela, "explicacao": explicacao})

    if "o1" in por_id:
        add("Ganho possível", "Comprar do fornecedor mais barato", por_id["o1"].impacto,
            "estimado", "Fornecedores",
            "diferença entre o custo pago e o menor custo registrado do mesmo item")
    if "m1" in por_id:
        add("Ganho possível", "Renegociar custos que subiram", por_id["m1"].impacto,
            "estimado", "Análises e Indicadores",
            "valor comprado × alta de custo dos itens que subiram acima da régua")
    if mv and mv.get("remarc") is not None and len(mv["remarc"]):
        add("Ganho possível", "Devolver ou remarcar lotes antes de vencer",
            float(mv["remarc"]["perda_evitada"].sum()), "estimado", "Validade e Remarcação",
            "custo das unidades que venceriam na prateleira e podem ser devolvidas ou vendidas "
            "com desconto")
    if mv:
        add("Perda realizada", "Mercadoria vencida em estoque", mv["resumo"]["perda_valor"],
            "real", "Validade e Remarcação", "custo dos lotes baixados por vencimento no período")
    if "e1" in por_id:
        add("Risco", "Último lote recebido vencido ou perto de vencer", por_id["e1"].impacto,
            "estimado", "Validade e Remarcação",
            "valor do último lote de cada item comparado à data de referência")
    if mv:
        for pid, nome, tela, natureza, expl in [
                ("v2", "Dinheiro parado em estoque", "Análises e Indicadores", "real",
                 "estoque, a custo, de itens com excesso ou sem venda recente"),
                ("v1", "Venda em risco por ruptura (por mês)", "Posição de Estoque", "estimado",
                 "venda média mensal dos itens em linha que estão zerados")]:
            if pid in por_id:
                add("Risco", nome, por_id[pid].impacto, natureza, tela, expl)
    if "f5" in por_id:
        add("Risco", "Compras com prazo de pagamento curto", por_id["f5"].impacto, "real",
            "Análises e Indicadores", "valor pago em prazo menor que o desejado")
    return pd.DataFrame(linhas, columns=["grupo", "item", "valor", "natureza", "tela",
                                         "explicacao"])


def _nome_mes(per: pd.Period) -> str:
    return mes_label(str(per))


def resultado_do_mes(df: pd.DataFrame, rec, mv: dict | None) -> tuple[pd.Period, list[str]]:
    """Cartões do último mês fechado contra o mês anterior e o mesmo mês do ano anterior.

    Usado na Visão Geral; as outras telas mostram só o comparativo do assunto delas.
    """
    from core import movimentacao as MV
    from core.tema import cartao_comparativo
    fim = df["dt"].max() if rec is None else max(df["dt"].max(), rec.fim)
    ref = M.mes_referencia(fim)
    inicio = df["dt"].min().to_period("M")
    compras = M.serie_mensal(df).set_index("ano_mes")["valor_pedido"]
    cmp_c = M.comparar_mes(compras, ref, inicio=inicio)
    cartoes = [cartao_comparativo("Compras", brl0(cmp_c["valor"] or 0), cmp_c, None,
                                  estilo="destaque")]
    if mv:
        s = lembrar("mov_serie", MV.serie_mensal, rec).set_index("ano_mes")
        ini_mov = rec.inicio.to_period("M")
        cmp_v = M.comparar_mes(s["faturamento"], ref, inicio=ini_mov)
        taxa = (s["margem"] / s["faturamento"].replace(0, float("nan")))
        cmp_m = M.comparar_mes(taxa, ref, relativo=False, inicio=ini_mov, zero_se_vazio=False)
        cmp_p = M.comparar_mes(s["perdas"], ref, inicio=ini_mov)
        margem_rs = s["margem"].get(str(ref), 0.0)
        cartoes += [
            cartao_comparativo("Vendas", brl0(cmp_v["valor"] or 0), cmp_v, True),
            cartao_comparativo(f"Margem bruta · {brl0(margem_rs)}",
                               pct(cmp_m["valor"], 1) if cmp_m["valor"] is not None else "—",
                               cmp_m, True, formato="pp"),
            cartao_comparativo("Perdas por validade", brl0(cmp_p["valor"] or 0), cmp_p, False),
        ]
    else:
        pedidos = M.serie_mensal(df).set_index("ano_mes")["pedidos"]
        cmp_n = M.comparar_mes(pedidos, ref, inicio=inicio)
        cartoes.append(cartao_comparativo("Pedidos", num(cmp_n["valor"] or 0), cmp_n, None))
    return ref, cartoes


CURTO = {"Comprar do fornecedor mais barato": "Troca de fornecedor",
         "Renegociar custos que subiram": "Renegociação de custos",
         "Devolver ou remarcar lotes antes de vencer": "Lotes devolvidos ou remarcados"}


def _tendencia(serie: pd.Series, meses: list[str], percentual: bool) -> tuple[float, str]:
    """Média dos 3 últimos meses contra a dos 3 anteriores: variação e direção."""
    v = serie.reindex(meses)
    recente, anterior = v.iloc[-3:].mean(), v.iloc[-6:-3].mean()
    if pd.isna(recente) or pd.isna(anterior) or (not percentual and anterior == 0):
        return float("nan"), "sem base"
    var = recente - anterior if percentual else recente / anterior - 1
    limite = 0.005 if percentual else 0.05
    return var, ("estável" if abs(var) < limite else "subindo" if var > 0 else "caindo")


def _mini_tendencias(itens: list[tuple], ref: pd.Period) -> None:
    """Pequenos múltiplos: um mini-gráfico por indicador, 12 meses até o mês de referência.

    item = (nome, série mensal indexada por 'AAAA-MM', maior_e_melhor, formato), com
    formato 'brl' (reais), 'pct' (percentual, variação em p.p.) ou 'num' (contagem).
    A linha é verde quando o último trimestre melhorou, laranja quando piorou e
    azul quando a direção não é boa nem ruim por si (compras). Grade de duas
    colunas, para cada gráfico ter tamanho de leitura (com eixo de valores e os
    meses a cada trimestre).
    """
    from core.tema import PALETA, figura
    c = PALETA["claro"]
    meses = [str(m) for m in pd.period_range(ref - 11, ref, freq="M")]
    rot = [mes_label(m) for m in meses]
    colunas = []
    for inicio in range(0, len(itens), 2):
        colunas += list(st.columns(2, gap="medium"))
    for col, (nome, serie, maior_e_melhor, formato) in zip(colunas, itens):
        percentual = formato == "pct"
        v = serie.reindex(meses)
        var, direcao = _tendencia(serie, meses, percentual)
        if direcao in ("subindo", "caindo") and maior_e_melhor is not None:
            efeito = "bom" if (direcao == "subindo") == maior_e_melhor else "ruim"
        else:
            efeito = "neutro"
        cor = {"bom": c["green"], "ruim": c["red"], "neutro": c["blue"]}[efeito]
        seta = {"subindo": "▲", "caindo": "▼", "estável": "●"}.get(direcao, "–")
        if var == var:
            mud = (f"{abs(var) * 100:.1f} p.p.".replace(".", ",") if percentual
                   else f"{abs(var) * 100:.0f}%")
            frase = f"{seta} {direcao}" + ("" if direcao == "estável" else f" {mud}")
        else:
            frase = "– sem meses suficientes"
        ultimo = v.dropna()
        # a média dos 12 meses, não o último mês: esse já está nos cartões do topo
        media = ("—" if ultimo.empty else
                 pct(ultimo.mean(), 1) if percentual else
                 f"{num(round(ultimo.mean()))}/mês" if formato == "num" else
                 f"{brl0(ultimo.mean())}/mês")
        fig = go.Figure(go.Scatter(
            # linha reta entre os meses: a curva suavizada criava vales que não existem
            x=rot, y=v.values, mode="lines", line=dict(color=cor, width=2.4),
            fill="tozeroy", fillcolor=cor + "1F", connectgaps=False,
            hovertemplate="%{x}<br><b>" + {"pct": "%{y:.1%}", "num": "%{y:,.0f}"}.get(
                formato, "R$ %{y:,.0f}")
                          + "</b><extra></extra>"))
        if not ultimo.empty:
            fig.add_trace(go.Scatter(x=[mes_label(ultimo.index[-1])], y=[ultimo.iloc[-1]],
                                     mode="markers", hoverinfo="skip",
                                     marker=dict(size=8, color=cor,
                                                 line=dict(color="#FFFFFF", width=2))))
        # trimestre comparado: faixa clara cobrindo os 3 últimos meses inteiros
        fig.add_vrect(x0=len(rot) - 3.5, x1=len(rot) - 0.5, fillcolor=c["grid"], opacity=0.7,
                      line_width=0, layer="below")
        mini = figura(fig, 230)
        eixo_y = ({"tickformat": ".0%"} if percentual else
                  {"tickformat": ",.0f"} if formato == "num" else
                  {"tickprefix": "R$ ", "tickformat": ",.0f"})
        mini.update_layout(margin=dict(l=10, r=16, t=8, b=10), showlegend=False,
                           xaxis=dict(showline=False, tickvals=rot[::3] + ([rot[-1]] if
                                      (len(rot) - 1) % 3 else []),
                                      tickfont=dict(size=10.5), range=[-0.5, len(rot) - 0.5]),
                           yaxis=dict(rangemode="tozero", nticks=4, tickfont=dict(size=10),
                                      **eixo_y))
        with col, st.container(border=True, key=f"mini_{nome}".replace(" ", "_")):
            st.markdown(
                f"<div class='mini-tend {efeito}'><span class='mt-nome'>{nome}</span>"
                f"<b>{frase}</b><small>média de 12 meses: {media}</small></div>",
                unsafe_allow_html=True)
            st.plotly_chart(mini, width="stretch", theme=None,
                            config={"displayModeBar": False, "responsive": True})

def visao_geral(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    from paginas.apoio_decisao import insights_da_sessao
    from paginas.movimentacao import para_decisao, recorte as recorte_mov
    from core import movimentacao as MV
    from core.tema import linha_comparativos
    ind = M.indicadores(df)
    insights = insights_da_sessao(df, abc, p)
    mv = para_decisao(p)
    rec, _ = recorte_mov()
    # o significado de "Estimado" e "Projeção" fica em Conceitos e Cálculos; aqui cada
    # selo traz a definição ao passar o mouse

    # ------------------------------------------------- resultado do mês
    ref, cartoes = resultado_do_mes(df, rec if mv else None, mv)
    st.subheader(f"Resultado de {_nome_mes(ref)}")
    st.caption(f"Último mês fechado do recorte, comparado com {_nome_mes(ref - 1)} e com "
               f"{_nome_mes(ref - 12)}. Verde = melhor; laranja = pior; cinza = nem bom nem "
               "ruim por si (compras).")
    linha_comparativos(cartoes, colunas=len(cartoes))

    # ------------------------------------------------- situação no período
    st.subheader("Situação no período")
    st.caption(f"{data(ind.inicio)} a {data(ind.fim)}.")
    fornecedores = M.por_dimensao(df, "Nome do Fornecedor")
    lider = fornecedores.iloc[0]
    if mv:
        res, pt = mv["resumo"], mv["ponte"]
        linha_cartoes([
            ("Compras no período", brl0(ind.valor_pedido),
             f"média de {brl0(ind.media_mensal)} por mês · {num(ind.pedidos)} pedidos"),
            ("Estoque na data final", brl0(pt["valor_final"]),
             ("+" if pt["variacao"] >= 0 else "−") + f"{brl0(abs(pt['variacao']))} desde "
             f"{data(pt['inicio'])}"),
            ("Giro do estoque", f"{pt['giro']:.1f}×".replace(".", ",")
             if pd.notna(pt["giro"]) else "—",
             (f"{pt['dias_estoque']:.0f} dias de estoque · cobertura típica de "
              f"{res['cobertura_mediana']:.0f} dias") if pd.notna(pt["dias_estoque"])
             else "sem venda no período"),
            ("Maior fornecedor", str(lider["Nome do Fornecedor"]),
             f"{pct(lider['valor_pedido'] / ind.valor_pedido)} das compras · "
             f"{num(ind.fornecedores)} fornecedores"),
        ], colunas=4)
    else:
        a_classe = abc.classes.set_index("classe")
        linha_cartoes([
            ("Compras no período", brl0(ind.valor_pedido),
             f"{num(ind.pedidos)} pedidos em {num(ind.cotacoes)} cotações"),
            ("Média mensal", brl0(ind.media_mensal), f"{ind.meses} meses com compra"),
            ("Maior fornecedor", str(lider["Nome do Fornecedor"]),
             f"{pct(lider['valor_pedido'] / ind.valor_pedido)} das compras"),
            ("Curva ABC", f"{num(int(a_classe.loc['A', 'itens']))} itens A",
             f"concentram {pct(a_classe.loc['A', 'pct_valor'], 0)} do valor"),
        ], colunas=4)

    # ------------------------------------------------------ movimentações
    st.subheader("Movimentações do período")
    mapa = mapa_financeiro(insights, mv)
    ganhos = mapa[mapa["grupo"] == "Ganho possível"]
    if mv:
        res = mv["resumo"]
        st.caption("Da venda ao resultado: o que sobra das vendas depois do custo da mercadoria e "
                   "das perdas, e quanto ainda pode ser ganho (estimado).")
        # efeito no negócio: o custo vendido é o custo normal da venda (neutro); a
        # perda é prejuízo (laranja); os ganhos possíveis são benefício (verde)
        passos = [("Vendas", res["faturamento"], "total", "total", ""),
                  ("Custo do que foi vendido", res["cmv"], "subtrai", "neutro", ""),
                  ("Margem bruta", res["margem"], "total", "total", ""),
                  ("Perdas por validade", res["perda_valor"], "subtrai", "ruim", ""),
                  ("Margem após perdas", res["margem"] - res["perda_valor"], "total", "total",
                   "")]
        potencial = res["margem"] - res["perda_valor"]
    else:
        st.caption("Compras do período e quanto delas pode ser economizado (estimado).")
        passos = [("Compras", ind.valor_pedido, "total", "total", "")]
        potencial = ind.valor_pedido
    for _, g in ganhos.iterrows():
        passos.append((g["item"], g["valor"], "soma" if mv else "subtrai", "bom", "estimado"))
        potencial += g["valor"] if mv else -g["valor"]
    if len(ganhos):
        passos.append(("Resultado com os ganhos" if mv else "Compras com a economia",
                       potencial, "total", "total", ""))
    mostrar(cascata(passos, "Composição do resultado do período" if mv
                    else "Compras e economia possível", rotulos_curtos=CURTO),
            110 + 42 * len(passos),
            "Cada barra parte de onde a anterior terminou. **Verde**: o que é benéfico (ganhos "
            "possíveis). **Laranja**: o que é prejudicial (perdas por validade). **Azul-claro**: "
            "o custo normal do que foi vendido. **Azul-escuro**: totais. As barras com *(estimado)* "
            "no rótulo, em verde mais suave com contorno, são ganhos que dependem de uma ação (trocar de fornecedor, "
            "renegociar, devolver ou remarcar lotes). O sinal + ou − no rótulo repete o que a "
            "cor indica.\n\nOs riscos (dinheiro parado, lotes perto de vencer) não entram na "
            "conta, porque não são entradas nem saídas do período: estão em Prioridades.")
    with st.expander("Como cada valor é calculado e onde agir"):
        tabela = mapa[["grupo", "item", "valor", "natureza", "explicacao", "tela"]].assign(
            natureza=mapa["natureza"].map({"estimado": "estimado"}).fillna("observado"))
        st.dataframe(tabela.rename(columns={"grupo": "Tipo", "item": "O quê", "valor": "Valor",
                                            "natureza": "Natureza", "explicacao": "Cálculo",
                                            "tela": "Onde agir"}),
                     hide_index=True, width="stretch",
                     column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f"),
                                    "Cálculo": st.column_config.TextColumn(width="large")})

    _prioridades(df, abc, p, ind.valor_pedido, insights)

    # --------------------------------------------------------- tendências
    st.subheader("Tendências")
    st.caption(f"Últimos 12 meses até {_nome_mes(ref)}. A direção compara a média do último "
               "trimestre (faixa cinza) com a do trimestre anterior.")
    # mês sem compra vale zero; antes da primeira compra do recorte, sem dado
    s_comp = M.serie_mensal(df).set_index("ano_mes")
    meses_tudo = [str(m) for m in pd.period_range(df["dt"].min().to_period("M"), ref, freq="M")]
    compras_mes = s_comp["valor_pedido"].reindex(meses_tudo).fillna(0.0)
    if mv:
        s = lembrar("mov_serie", MV.serie_mensal, rec).set_index("ano_mes")
        itens = [("Vendas", s["faturamento"], True, "brl"),
                 ("Margem bruta", s["margem"] / s["faturamento"].replace(0, float("nan")),
                  True, "pct"),
                 ("Perdas por validade", s["perdas"], False, "brl"),
                 ("Compras", compras_mes, None, "brl")]
    else:
        itens = [("Compras", compras_mes, None, "brl"),
                 ("Pedidos", s_comp["pedidos"].reindex(meses_tudo).fillna(0.0), None, "num")]
    _mini_tendencias(itens, ref)

    _aprofundar()


def _prioridades(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros, total: float,
                 insights: list | None = None) -> None:
    """Os três pontos que o motor de decisão manda olhar primeiro.

    Usa o mesmo diagnóstico da tela Sistema de Apoio à Decisão, então a
    gravidade e a ordem aqui são sempre as mesmas de lá.
    """
    c = cores()
    if insights is None:
        from paginas.apoio_decisao import insights_da_sessao
        insights = insights_da_sessao(df, abc, p)
    diag = Dc.diagnostico(insights, total)

    st.subheader("Prioridades")
    top = diag["acionaveis"][:3]
    if not top:
        st.success("Nenhum ponto crítico ou em atenção neste recorte.")
    for ins in top:
        cor = c["red"] if ins.nivel == "crit" else c["amber"]
        impacto = (f"{brl0(ins.impacto)} {'recuperável' if ins.tipo == 'economia' else 'exposto'}"
                   if ins.impacto > 0 else "")
        with st.container(border=True):
            a, b = st.columns([1.35, 1], vertical_alignment="center", gap="medium")
            a.markdown(
                f"<div class='prioridade-linha' style='border-left:4px solid {cor}'>"
                f"<div class='pl-topo'><span class='selo {ins.nivel}'>{Dc.NIVEIS[ins.nivel]}"
                f"</span><b>{ins.titulo}</b>{selo_natureza(ins.natureza)}</div>"
                f"<div class='pl-valor'>{ins.valor}"
                + (f" <small>· {impacto}</small>" if impacto else "") +
                f"</div><div class='pl-frase'>{ins.frase}</div></div>",
                unsafe_allow_html=True)
            b.markdown(f"<div class='pl-acao'><b>O que fazer</b>{ins.acao}</div>",
                       unsafe_allow_html=True)
    paginas = st.session_state.get("paginas_menu", {})
    if "Sistema de Apoio à Decisão" in paginas:
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        st.page_link(paginas["Sistema de Apoio à Decisão"],
                     label="Ver todos os pontos e o plano de ação",
                     icon=":material/arrow_forward:")
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)


def _aprofundar() -> None:
    """Atalhos por pergunta: cada uma leva à tela que a responde."""
    paginas = st.session_state.get("paginas_menu", {})
    atalhos = [
        ("O que preciso comprar agora?", "Reposição e Lotes", ":material/add_shopping_cart:"),
        ("O que pode vencer na prateleira?", "Validade e Remarcação", ":material/event_busy:"),
        ("Quais itens pesam mais?", "Curva ABC", ":material/bar_chart:"),
        ("Quanto tempo o estoque dura?", "Análises e Indicadores", ":material/monitoring:"),
        ("Com quem e em que condições compro?", "Fornecedores", ":material/local_shipping:"),
        ("O que conferir na próxima cotação?", "Previsão de Compras",
         ":material/event_upcoming:"),
    ]
    atalhos = [a for a in atalhos if a[1] in paginas]
    if not atalhos:
        return
    st.subheader("Onde aprofundar")
    for inicio in range(0, len(atalhos), 3):
        for col, (pergunta, secao, icone) in zip(st.columns(3), atalhos[inicio:inicio + 3]):
            with col:
                st.page_link(paginas[secao], label=pergunta, icon=icone,
                             help=f"Abre {secao}")


# --------------------------------------------------------- GESTÃO DE COMPRAS
def gestao_compras(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    ind = M.indicadores(df)
    serie = _serie(df)

    faixa("Para onde vai o dinheiro das compras: o <b>mês</b> comparado com os anteriores, a "
          "<b>concentração</b> do gasto e a composição por <b>categoria</b>, <b>forma</b>, "
          "<b>medicamento</b> e <b>fabricante</b>. A lista linha a linha fica em Pedidos.",
          "Gestão de Compras")

    from core.tema import cartao_comparativo, linha_comparativos
    ref = M.mes_referencia(df["dt"].max())
    inicio = df["dt"].min().to_period("M")
    s = M.serie_mensal(df).set_index("ano_mes")
    ticket = s["valor_pedido"] / s["pedidos"].replace(0, float("nan"))
    skus_mes = df.groupby("ano_mes")["sku"].nunique()
    cmp_v = M.comparar_mes(s["valor_pedido"], ref, inicio=inicio)
    cmp_p = M.comparar_mes(s["pedidos"], ref, inicio=inicio)
    cmp_t = M.comparar_mes(ticket, ref, inicio=inicio, zero_se_vazio=False)
    cmp_i = M.comparar_mes(skus_mes, ref, inicio=inicio)
    st.subheader(f"Compras de {_nome_mes(ref)}")
    st.caption(f"Último mês fechado, comparado com {_nome_mes(ref - 1)} e {_nome_mes(ref - 12)}.")
    linha_comparativos([
        cartao_comparativo("Valor pedido", brl0(cmp_v["valor"] or 0), cmp_v, None, estilo="destaque"),
        cartao_comparativo("Pedidos", num(cmp_p["valor"] or 0), cmp_p, None),
        cartao_comparativo("Valor médio por pedido",
                           brl0(cmp_t["valor"]) if cmp_t["valor"] is not None else "—", cmp_t, None),
        cartao_comparativo("Medicamentos comprados", num(cmp_i["valor"] or 0), cmp_i, None),
    ], colunas=4)

    if df["sku"].nunique() == 1:
        # filtro de um só produto: os indicadores de reposição dele vêm direto aqui
        from paginas import movimentacao as PM
        from core import dados as D
        PM.dente_serra_produto(D.texto_chave(df["EAN"]).iloc[0], p, titulo=True)

    # ------------------------------------------- onde o gasto se concentra
    st.subheader("Onde o gasto se concentra")
    st.caption(f"Período inteiro: {brl0(ind.valor_pedido)} em {num(ind.pedidos)} pedidos, "
               f"{num(ind.medicamentos)} medicamentos e {num(ind.fornecedores)} fornecedores.")
    linha_cartoes(_destaques_compras(df, abc, serie, ind), colunas=4)

    col1, col2 = st.columns([1.5, 1])
    with col1:
        media = serie["valor_pedido"].mean()
        limite = media * p.pico_mensal
        fig = go.Figure(go.Bar(
            x=serie["mes"], y=serie["valor_pedido"], customdata=serie[["pedidos"]],
            marker_color=[c["amber"] if v > limite else c["blue"] for v in serie["valor_pedido"]],
            hovertemplate="%{x}<br><b>R$ %{y:,.0f}</b> · %{customdata[0]} pedidos"
                          "<extra></extra>"))
        fig.add_hline(y=media, line=dict(color=c["ink3"], dash="dot"),
                      annotation_text=f"média {brl0(media)}", annotation_position="top left")
        fig.update_layout(title="Valor pedido por mês", yaxis_tickprefix="R$ ",
                          yaxis_tickformat=",.0f")
        mostrar(fig, 320,
                "Valor pedido (quantidade × custo) em cada mês, com a **média** do período. "
                "Em **âmbar**, os meses acima de "
                f"{str(round(p.pico_mensal, 2)).replace('.', ',')}× a média (régua de pico em "
                "Preferências): neles o desembolso pesa mais no caixa.\n\nO número "
                "de pedidos aparece ao passar o mouse.")
    with col2:
        cat = M.por_dimensao(df, "Categoria Comercial")
        fig = px.pie(cat, names="Categoria Comercial", values="valor_pedido", hole=0.58,
                     title="Por categoria comercial")
        fig.update_traces(marker=dict(colors=[c["blue"], c["teal"], c["purple"],
                                              c["green_c"], c["blue_l"]]),
                          textinfo="percent", sort=True)
        mostrar(fig, 320,
                "**Categoria comercial** é como o medicamento é classificado no mercado: "
                "referência (o original, com patente), genérico (mesma substância sem marca), "
                "similar (mesma substância com marca própria) e correlato (não medicamento, "
                "como curativo e seringa).")

    # ------------------------------------------------- composição (um gráfico só)
    dimensoes = {"Medicamento": "medicamento", "Forma farmacêutica": "Forma Farmacêutica",
                 "Fabricante": "Fabricante"}
    ver = st.segmented_control("Composição do gasto por", list(dimensoes), default="Medicamento",
                               key="gc_composicao") or "Medicamento"
    coluna = dimensoes[ver]
    comp = M.por_dimensao(df, coluna)
    topo = comp.head(12).copy()
    topo["participacao"] = topo["valor_pedido"] / max(ind.valor_pedido, 1)
    fig = barras_h(topo, "valor_pedido", coluna, f"{ver}: os 12 de maior valor pedido",
                   {"Medicamento": c["green_c"], "Forma farmacêutica": c["purple"],
                    "Fabricante": c["teal"]}[ver])
    fig.update_traces(customdata=topo[["participacao"]].values,
                      hovertemplate="%{y}<br><b>R$ %{x:,.0f}</b> · %{customdata[0]:.1%} do "
                                    "total<extra></extra>")
    mostrar(fig, 120 + 30 * len(topo),
            f"Os 12 maiores de {num(len(comp))} ({pct(topo['valor_pedido'].sum() / max(ind.valor_pedido, 1), 0)} "
            "do valor pedido). Ordenado por **valor pedido** (quantidade × custo), não por "
            "quantidade de caixas: um item caro comprado poucas vezes pode pesar mais que um "
            "barato comprado sempre.\n\n**Forma farmacêutica** é a apresentação (sólido oral, "
            "xarope, injetável…) e mostra se o gasto está em tipos que exigem armazenagem "
            "especial. **Fabricante** mostra a dependência de um laboratório.")
    paginas = st.session_state.get("paginas_menu", {})
    if "Pedidos" in paginas:
        st.page_link(paginas["Pedidos"], label="Ver as compras linha a linha em Pedidos",
                     icon=":material/receipt_long:")


def _destaques_compras(df: pd.DataFrame, abc: M.ResultadoABC, serie: pd.DataFrame,
                       ind: M.Indicadores) -> list[tuple]:
    """Quatro leituras do gasto que apontam onde agir (cartões de Gestão de Compras)."""
    total = max(ind.valor_pedido, 1.0)
    # concentração: a classe A da própria Curva ABC (mesmo corte de Preferências), o
    # grupo a negociar primeiro
    classes = abc.classes.set_index("classe")
    n_a = int(classes.loc["A", "itens"]) if "A" in classes.index else 0
    pct_a = float(classes.loc["A", "pct_valor"]) if "A" in classes.index else 0.0
    # genéricos: participação no valor
    gen = df.loc[df["Categoria Comercial"] == "Genérico", "valor_pedido"].sum() / total
    # mês de pico
    pico = serie.loc[serie["valor_pedido"].idxmax()] if len(serie) else None
    acima = (pico["valor_pedido"] / serie["valor_pedido"].mean() - 1) if pico is not None else 0
    # fabricante de maior peso
    fab = M.por_dimensao(df, "Fabricante").head(1)
    cartoes = [
        (f"{pct(pct_a, 0)} do gasto em", f"{num(n_a)} medicamentos",
         f"classe A, de {num(ind.medicamentos)} comprados · negociar estes primeiro"),
        ("Genéricos no valor", pct(gen, 0),
         "parcela que já é genérico; os demais itens são referência, similar ou outros"),
    ]
    if pico is not None:
        cartoes.append(("Mês de maior gasto", mes_label(pico["ano_mes"]),
                        f"{brl0(pico['valor_pedido'])} · {pct(acima, 0)} acima da média — "
                        "planejar o caixa"))
    if len(fab):
        cartoes.append(("Fabricante de maior peso", str(fab["Fabricante"].iloc[0]),
                        f"{pct(fab['valor_pedido'].iloc[0] / total, 0)} do valor pedido"))
    return cartoes


# ----------------------------------------------------------------- PEDIDOS
def pedidos(df: pd.DataFrame, abc: M.ResultadoABC | None = None) -> None:
    faixa("Cada <b>pedido</b> de cada cotação, com o que foi pedido e o que a nota "
          "realmente trouxe.", "Pedidos")
    por_pedido, por_item = st.tabs(["Por pedido", "Itens comprados"])
    with por_pedido:
        _pedidos_resumo(df)
    with por_item:
        _itens_comprados(df, abc)


def _itens_comprados(df: pd.DataFrame, abc: M.ResultadoABC | None) -> None:
    """Todas as linhas de pedido do recorte (antes ficava em Gestão de Compras)."""
    st.caption("Clique no cabeçalho de uma coluna para reordenar.")
    base = df if abc is None else df.merge(abc.itens[["sku", "classe"]], on="sku", how="left")
    colunas = ["dt", "Cotação", "Pedido", "medicamento", "Nome do Fornecedor",
               "Categoria Comercial", "Qtde. Ped.", "Qtde. Fat.", "Vl. Custo (R$)",
               "valor_pedido"] + (["classe"] if abc is not None else [])
    tabela = (base.sort_values("dt", ascending=False)[colunas]
                  .rename(columns={"dt": "Data", "medicamento": "Medicamento",
                                   "Nome do Fornecedor": "Fornecedor",
                                   "Categoria Comercial": "Categoria",
                                   "Qtde. Ped.": "Qtd. ped.", "Qtde. Fat.": "Qtd. fat.",
                                   "Vl. Custo (R$)": "Custo unit.",
                                   "valor_pedido": "Valor pedido", "classe": "Classe ABC"}))
    st.dataframe(tabela, width="stretch", hide_index=True, height=480,
                 column_config={
                     "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                     "Custo unit.": st.column_config.NumberColumn(format="R$ %.2f"),
                     "Valor pedido": st.column_config.NumberColumn(format="R$ %.2f")})


def _pedidos_resumo(df: pd.DataFrame) -> None:
    resumo = M.resumo_pedidos(df)
    por_status = (df.groupby("Status do Pedido", as_index=False)
                    .agg(pedidos=("Pedido", "nunique"), valor=("valor_pedido", "sum"))
                    .sort_values("pedidos", ascending=False))

    st.subheader("Pedidos do período")
    linha_cartoes(
        [("Pedidos", num(len(resumo)), "no período filtrado", "destaque"),
         ("Itens por pedido", f"{resumo['itens'].mean():.1f}".replace(".", ","),
          "média de linhas por pedido")] +
        [(f"Status: {r['Status do Pedido']}", f"{num(r['pedidos'])} pedidos",
          f"{brl0(r['valor'])} em valor pedido") for _, r in por_status.iterrows()],
        colunas=4)

    visao = resumo.rename(columns={
        "cotacao": "Cotação", "data": "Data", "fornecedor": "Fornecedor",
        "representante": "Representante", "status": "Status", "itens": "Itens",
        "qtd_pedida": "Qtd. pedida", "valor_pedido": "Valor pedido",
        "valor_faturado": "Valor faturado", "atendimento": "Atendimento",
    })[["Pedido", "Cotação", "Data", "Fornecedor", "Representante", "Status",
        "Itens", "Qtd. pedida", "Valor pedido", "Valor faturado", "Atendimento"]]

    st.markdown("Selecione uma linha da tabela para ver os itens do pedido.")
    evento = st.dataframe(
        visao, width="stretch", hide_index=True, height=430,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Valor pedido": st.column_config.NumberColumn(format="R$ %.2f"),
            "Valor faturado": st.column_config.NumberColumn(format="R$ %.2f"),
            # o valor é a fração (1 = 100%): "percent" multiplica por 100; o formato
            # "%.0f%%" mostrava "1%" com a barra cheia
            "Atendimento": st.column_config.ProgressColumn(
                format="percent", min_value=0, max_value=1)})

    escolha = evento.selection.rows if evento and evento.selection else []
    if escolha:
        pedido = visao.iloc[escolha[0]]["Pedido"]
        itens = df[df["Pedido"] == pedido][
            ["medicamento", "Fabricante", "Forma Farmacêutica", "Qtde. Ped.",
             "Qtde. Fat.", "Vl. Custo (R$)", "valor_pedido", "validade",
             "Faixa de Recebimento"]].rename(columns={
                "medicamento": "Medicamento", "Forma Farmacêutica": "Forma",
                "Qtde. Ped.": "Qtd. ped.", "Qtde. Fat.": "Qtd. fat.",
                "Vl. Custo (R$)": "Custo", "valor_pedido": "Total",
                "validade": "Validade", "Faixa de Recebimento": "Vida útil na entrega"})
        st.markdown(f"**Itens do pedido {pedido}**")
        st.dataframe(itens, width="stretch", hide_index=True, column_config={
            "Validade": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Custo": st.column_config.NumberColumn(format="R$ %.2f"),
            "Total": st.column_config.NumberColumn(format="R$ %.2f")})
