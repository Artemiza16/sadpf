"""
Grupo Movimentação: três telas sobre o estoque e o que fazer com ele.

    Posição de Estoque      o que pede atenção, situação de cada produto e saldo
    Reposição e Lotes       quando e quanto comprar, lote econômico e dente de serra
    Validade e Remarcação   perdas, lotes que vão vencer, o que fazer com cada um e
                            a validade do que chega dos fornecedores

As análises de giro, cobertura, ponte do estoque e sazonalidade das vendas ficam
em Análises e Indicadores; as verificações do livro e a carga de um livro novo,
em Base de Dados. Cada tela abre com uma frase, uma leitura automática do
resultado e seções curtas, com a explicação de cada gráfico recolhida.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import metricas as M
from core import movimentacao as MV
from core.memoria import lembrar
from core.parametros import Parametros
from core.tema import (brl, brl0, cores, data, faixa, linha_cartoes, mes_label, mostrar,
                       num, pct)

# nomes das telas no menu (usados pelo app.py e pelos atalhos entre telas)
POSICAO = "Posição de Estoque"
REPOSICAO = "Reposição e Lotes"
VALIDADE = "Validade e Remarcação"
TELAS = [POSICAO, REPOSICAO, VALIDADE]
ICONES = {POSICAO: ":material/inventory:", REPOSICAO: ":material/add_shopping_cart:",
          VALIDADE: ":material/event_busy:"}
ANALISES = "Análises e Indicadores"

COR_SITUACAO = {"Ruptura": "red", "Descontinuado": "ink3", "Estoque crítico": "amber",
                "Validade próxima": "purple", "Excesso": "blue", "Sem giro recente": "blue_l",
                "Normal": "green"}
O_QUE_FAZER = {
    "Ruptura": "repor na próxima cotação",
    "Descontinuado": "decidir se volta ao mix ou sai do cadastro",
    "Estoque crítico": "pedir agora, antes de zerar",
    "Validade próxima": "dar saída ao lote mais antigo ou remarcar",
    "Excesso": "suspender a compra até a cobertura baixar",
    "Sem giro recente": "rever se o item deve continuar no mix",
    "Normal": "nenhuma ação",
}


# ---------------------------------------------------------------------------
#                 ACESSO AO RECORTE (usado também por outras telas)
# ---------------------------------------------------------------------------
def recorte() -> tuple[MV.Recorte | None, pd.DataFrame | None]:
    """Livro do recorte e livro completo, preparados pelo app.py a cada clique."""
    return st.session_state.get("mov_rec"), st.session_state.get("mov_full")


def posicao(p: Parametros) -> pd.DataFrame | None:
    rec, _ = recorte()
    if rec is None or rec.mov.empty:
        return None
    return lembrar("mov_posicao", MV.posicao, rec, p)


def para_decisao(p: Parametros) -> dict | None:
    """Pacote da movimentação para o motor de decisão, ou None sem livro."""
    rec, completo = recorte()
    if rec is None or rec.mov.empty:
        return None
    return lembrar("mov_decisao", MV.para_decisao, rec, completo, p)


def propostas(p: Parametros) -> pd.DataFrame:
    """Propostas por lote (devolver, remarcar, segregar) do recorte em uso."""
    pacote = para_decisao(p)
    return pacote["remarc"] if pacote else pd.DataFrame()


def sem_livro() -> None:
    st.info("Nenhum livro de movimentação encontrado. Coloque o arquivo "
            "**movimentacao_estoque.csv** na pasta `movimentacao/` do projeto ou envie-o na "
            "tela *Base de Dados*.")


# ---------------------------------------------------------------------------
#                              PEÇAS DE LAYOUT
# ---------------------------------------------------------------------------
def _abertura(tela: str, texto: str) -> bool:
    """Frase de abertura. False se não houver livro ou produto no recorte."""
    faixa(texto, tela)
    rec, _ = recorte()
    if rec is None:
        sem_livro()
        return False
    if rec.mov.empty:
        st.warning("Nenhum produto da movimentação atende aos filtros em uso. Ajuste a seleção "
                   "no menu lateral.")
        return False
    return True


def leitura(frases: list[str]) -> None:
    """Leitura automática do resultado, em frases curtas."""
    frases = [f for f in frases if f]
    if not frases:
        return
    itens = "".join(f"<li>{f}</li>" for f in frases)
    st.markdown(f"<div class='leitura-auto'><b>Leitura do sistema</b><ul>{itens}</ul></div>",
                unsafe_allow_html=True)


def secao(titulo: str, legenda: str = "", ajuda: str = "") -> None:
    """Título de bloco; `ajuda` vira o (?) ao lado do título (fórmulas, critérios)."""
    st.subheader(titulo, help=ajuda or None)
    if legenda:
        st.caption(legenda)


def atalho(tela: str, rotulo: str, icone: str | None = None) -> None:
    paginas = st.session_state.get("paginas_menu", {})
    if tela in paginas:
        st.page_link(paginas[tela], label=rotulo, icon=icone or ICONES.get(tela))


def _situacoes(pos: pd.DataFrame) -> pd.DataFrame:
    return (pos.groupby("situacao")
               .agg(produtos=("ean", "size"), valor=("valor_estoque", "sum"),
                    unidades=("estoque_atual", "sum"))
               .reindex(MV.SITUACOES).fillna(0).reset_index())


def _comparativos_mes(rec: MV.Recorte, indicadores: list[tuple[str, str, bool | None, bool]],
                      titulo: bool = True) -> None:
    """Cartões do último mês fechado contra o anterior e o mesmo mês do ano anterior.

    indicador = (rótulo, coluna de serie_mensal, maior_e_melhor, em_reais).
    """
    from core.tema import cartao_comparativo, linha_comparativos
    serie = lembrar("mov_serie", MV.serie_mensal, rec)
    if serie.empty:
        return
    ref = M.mes_referencia(rec.fim)
    s = serie.set_index("ano_mes")
    inicio = rec.inicio.to_period("M")
    nome = lambda per: mes_label(str(per))   # noqa: E731
    if titulo:
        st.caption(f"**{nome(ref)}** (último mês fechado) comparado com {nome(ref - 1)} e "
                   f"{nome(ref - 12)}.")
    else:
        st.caption(f"{nome(ref)} comparado com {nome(ref - 1)} e {nome(ref - 12)}.")
    cartoes = []
    for rotulo, coluna, melhor, reais in indicadores:
        cmp = M.comparar_mes(s[coluna], ref, inicio=inicio)
        valor = (brl0(cmp["valor"]) if reais else f"{num(cmp['valor'])} un") \
            if cmp["valor"] is not None else "—"
        cartoes.append(cartao_comparativo(rotulo, valor, cmp, melhor))
    linha_comparativos(cartoes, colunas=max(3, len(cartoes)))


def dente_serra_produto(ean: str, p: Parametros, titulo: bool = False) -> bool:
    """Indicadores de reposição e o dente de serra de UM produto.

    Usado em Reposição e Lotes, na ficha de Medicamentos e na Gestão de Compras
    quando o filtro deixa um só produto. Devolve False se o produto não estiver
    no livro de movimentação do recorte.
    """
    c = cores()
    rec, _ = recorte()
    pos = posicao(p)
    if pos is None or ean not in set(pos["ean"]):
        return False
    lec = lembrar("mov_lote", MV.lote_economico, pos, rec, p)
    if ean not in set(lec["ean"]):
        return False
    ln = lec.set_index("ean").loc[ean]
    linha = pos.set_index("ean").loc[ean]
    nome = str(linha["medicamento"])
    if titulo:
        st.subheader("Reposição e lote econômico")
        st.caption("Quando e quanto comprar deste produto, com o estoque que aconteceu ao lado "
                   "do comportamento ideal.")
    d = float(ln["demanda_prevista"])
    ciclo = ln["lec"] / d if d > 0 else float("nan")
    politica = str(linha["politica"])
    linha_cartoes([
        ("Estoque na data final", f"{num(linha['estoque_atual'])} un",
         f"{linha['situacao'].lower()} · " + (f"dura {linha['cobertura_dias']:.0f} dias"
                                             if pd.notna(linha["cobertura_dias"])
                                             else "sem venda recente")),
        ("Venda prevista por dia", f"{d:.2f} un".replace(".", ","),
         f"política: {politica}", "", "estimado"),
        ("Ponto de pedido", f"{num(ln['ponto_pedido'])} un",
         ("comprar agora: " + num(linha["qtd_sugerida"]) + " un") if linha["repor_agora"]
         else "pedir quando o estoque chegar aqui", "", "estimado"),
        ("Lote econômico (LEC)", f"{num(ln['lec'])} un",
         f"Harris: {num(ln['lec_teorico'])} un" + (" · limitado pela validade"
                                                   if ln["limitado_validade"] else ""),
         "destaque", "estimado"),
        ("Estoque mínimo · máximo",
         f"{num(ln['estoque_minimo'])} · {num(ln['estoque_maximo'])} un",
         "segurança · segurança + lote", "", "estimado"),
        ("Ciclo de compra", f"{ciclo:.0f} dias" if pd.notna(ciclo) else "—",
         f"lote praticado: {num(ln['lote_praticado'])} un"
         if pd.notna(ln["lote_praticado"]) else "lote ÷ venda diária", "", "estimado"),
    ], colunas=3)
    traj = MV.trajetoria(rec, ean)
    inicio = rec.fim - pd.Timedelta(days=180)
    traj = traj[traj["data"] >= inicio]
    modelo = (MV.dente_serra_modelo(d, float(ln["lec"]), float(ln["estoque_minimo"]),
                                    float(ln["ponto_pedido"]), int(p.mov_lead_time), inicio, 181)
              if politica == "ponto de pedido" else pd.DataFrame())
    fig = go.Figure()
    if len(modelo):
        fig.add_trace(go.Scatter(x=modelo["data"], y=modelo["saldo"], mode="lines",
                                 line=dict(color=c["purple"], width=1.8, dash="dot"),
                                 name="Política recomendada",
                                 hovertemplate="%{x|%d/%m}<br>modelo <b>%{y:.0f} un</b>"
                                               "<extra></extra>"))
        ped = modelo[modelo["pedido"]]
        fig.add_trace(go.Scatter(x=ped["data"], y=ped["saldo"], mode="markers",
                                 marker=dict(symbol="triangle-down", size=9, color=c["purple"]),
                                 name="Pedido (modelo)",
                                 hovertemplate="%{x|%d/%m}<br>pedir "
                                               f"<b>{int(ln['lec'])} un</b><extra></extra>"))
    if len(traj):
        fig.add_trace(go.Scatter(x=traj["data"], y=traj["saldo"], mode="lines",
                                 line=dict(shape="hv", color=c["blue"], width=2),
                                 name="Saldo que aconteceu",
                                 hovertemplate="%{x|%d/%m}<br>saldo <b>%{y} un</b>"
                                               "<extra></extra>"))
        ent = traj[traj["entrada"].notna()]
        fig.add_trace(go.Scatter(x=ent["data"], y=ent["saldo"], mode="markers",
                                 marker=dict(size=8, color=c["teal"]),
                                 name="Compra recebida", customdata=ent["entrada"],
                                 hovertemplate="%{x|%d/%m}<br>chegou <b>%{customdata} un"
                                               "</b><extra></extra>"))
    if politica == "ponto de pedido":
        for y, rotulo, cor, traco in [
                (ln["estoque_maximo"], "máximo", c["ink3"], "dash"),
                (ln["ponto_pedido"], "ponto de pedido", c["amber"], "dash"),
                (ln["estoque_minimo"], "mínimo", c["red"], "dot")]:
            fig.add_hline(y=y, line=dict(color=cor, dash=traco, width=1.1),
                          annotation_text=f"{rotulo} · {int(y)}", annotation_position="right",
                          annotation_xanchor="left")
    fig.update_layout(title=f"Dente de serra — {nome} (últimos 180 dias)",
                      yaxis_title="unidades", yaxis=dict(rangemode="tozero"), margin=dict(r=120),
                      xaxis=dict(tickformat="%d/%m/%y"))
    mostrar(fig, 400,
            "**Linha azul**: o saldo que aconteceu. **Pontilhado roxo**: como o estoque se "
            "comportaria seguindo a política recomendada — começa no máximo, cai com a venda "
            "prevista e, ao tocar o **ponto de pedido**, um lote do tamanho do **lote econômico** "
            f"é pedido e chega {p.mov_lead_time} dias depois. A altura de cada dente é o lote; o "
            "vale não deveria passar do **mínimo** (estoque de segurança).\n\nAzul muito acima "
            "do roxo: compra maior que o necessário. Azul encostando no zero: compra tardia. "
            "Produtos sob encomenda, fora de linha ou sem venda recente não têm política de "
            "ponto de pedido: aparece só o saldo.")
    return True


# ===========================================================================
#                            1. POSIÇÃO DE ESTOQUE
# ===========================================================================
def posicao_estoque(p: Parametros) -> None:
    if not _abertura(POSICAO, "Quanto existe de cada produto na data final do período e em "
                              "que <b>situação</b> ele está, com o que pede atenção primeiro."):
        return
    c = cores()
    rec, _ = recorte()
    pos = posicao(p)
    res = lembrar("mov_resumo", MV.resumo, rec, pos)
    sit = _situacoes(pos)
    cont = sit.set_index("situacao")

    linha_cartoes([
        ("Estoque na data final", f"{num(res['estoque_unidades'])} un",
         f"{brl0(res['estoque_valor'])} a custo · {data(res['fim'])}", "destaque"),
        ("Produtos normais", num(cont.loc["Normal", "produtos"]),
         f"de {num(len(pos))} produtos"),
        ("Zerados ou críticos",
         num(cont.loc["Ruptura", "produtos"] + cont.loc["Estoque crítico", "produtos"]),
         f"{num(cont.loc['Ruptura', 'produtos'])} em ruptura · "
         f"{num(cont.loc['Estoque crítico', 'produtos'])} vão zerar em até "
         f"{p.mov_cobertura_critica} dias"),
        ("Parado", brl0(cont.loc["Excesso", "valor"] + cont.loc["Sem giro recente", "valor"]),
         "em excesso ou sem venda recente"),
    ], colunas=4)

    _comparativos_mes(rec, [("Unidades vendidas", "un_vendas", True, False),
                            ("Unidades recebidas", "un_entradas", None, False),
                            ("Estoque ao fim do mês (un)", "estoque_fim", None, False)])

    secao("O que pede atenção", "Em ordem de urgência, com a tela onde se resolve.")
    repor = pos[pos["repor_agora"]]
    prop = propostas(p)
    recuperavel = float(prop["perda_evitada"].sum()) if len(prop) else 0.0
    # ícones de traço, monocromáticos (Material Symbols, a mesma família do menu), no
    # lugar dos emojis coloridos
    pontos = [
        ("block",
         f"<b>{num(cont.loc['Ruptura', 'produtos'])} produtos em linha estão zerados</b> "
         "— costumam vender e não há saldo.", REPOSICAO, "Ver o que comprar"),
        ("shopping_cart_checkout",
         f"<b>{num(len(repor))} produtos chegaram ao ponto de pedido</b> — compra "
         f"sugerida de {brl0(repor['valor_sugerido'].sum())}.", REPOSICAO,
         "Ver o que comprar"),
        ("event_busy",
         f"<b>{num(len(prop))} lotes vão vencer antes de serem vendidos</b> — "
         f"{brl0(recuperavel)} recuperáveis devolvendo ou remarcando.", VALIDADE,
         "Ver validade e remarcação"),
        ("hourglass_empty",
         f"<b>Cobertura mediana de {res['cobertura_mediana']:.0f} dias</b> — a "
         "referência é de 30 a 60." if pd.notna(res["cobertura_mediana"]) else
         "<b>Sem venda recente para medir a cobertura.</b>", ANALISES,
         "Ver giro e cobertura"),
    ]
    for icone, texto, tela, rotulo in pontos:
        with st.container(border=True):
            a, b = st.columns([3.2, 1.3], vertical_alignment="center")
            a.markdown(f"<div class='ponto-atencao'><span class='pa-ico material-symbols-rounded' "
                       f"aria-hidden='true'>{icone}</span><p>{texto}</p></div>",
                       unsafe_allow_html=True)
            with b:
                atalho(tela, rotulo, ":material/monitoring:" if tela == ANALISES else None)

    secao("Situação dos produtos", "Cada produto recebe a primeira situação da lista que se "
                                   "aplicar.")
    fig = go.Figure(go.Bar(
        y=sit["situacao"], x=sit["produtos"], orientation="h",
        marker_color=[c[COR_SITUACAO[s]] for s in sit["situacao"]],
        text=[f"{int(n)} · {brl0(v)}" for n, v in zip(sit["produtos"], sit["valor"])],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br><b>%{x} produtos</b><extra></extra>"))
    fig.update_layout(title="Produtos por situação (quantidade · valor em estoque)",
                      yaxis=dict(autorange="reversed"), xaxis_title="produtos",
                      margin=dict(r=110))
    mostrar(fig, 320, "Valor em estoque = saldo de cada lote × custo residual do lote.")
    criterios = {
        "Ruptura": f"saldo zero em item em linha (reposto mais de uma vez ou comprado há "
                   f"menos de {p.mov_dias_descontinuado} dias)",
        "Descontinuado": f"saldo zero e sem reposição há mais de {p.mov_dias_descontinuado} dias",
        "Estoque crítico": f"cobertura abaixo de {p.mov_cobertura_critica} dias",
        "Validade próxima": f"lote mais antigo vencendo em menos de {p.mov_validade_proxima} dias",
        "Excesso": f"cobertura acima de {p.mov_cobertura_excesso} dias",
        "Sem giro recente": f"saldo positivo sem venda nos últimos {p.mov_janela_demanda} dias",
        "Normal": "nenhuma das anteriores",
    }
    with st.expander("Critério de cada situação e o que fazer"):
        st.dataframe(pd.DataFrame({
            "Situação": list(criterios), "Critério": list(criterios.values()),
            "Produtos": [int(cont.loc[s, "produtos"]) for s in criterios],
            "O que fazer": [O_QUE_FAZER[s] for s in criterios]}),
            hide_index=True, width="stretch")
        st.caption("Os limites ficam em Preferências › Movimentação de estoque.")

    secao("Produtos", "Ordenados pelo valor vendido no período.")
    f1, f2 = st.columns([2, 1.4])
    situacoes = f1.multiselect("Situação", MV.SITUACOES, key="mov_sit", placeholder="Todas")
    busca = f2.text_input("Buscar medicamento", key="mov_busca", placeholder="Nome")
    lista = pos
    if situacoes:
        lista = lista[lista["situacao"].isin(situacoes)]
    if busca:
        lista = lista[lista["medicamento"].str.contains(busca, case=False, na=False)]
    lista = lista.sort_values("faturamento", ascending=False)
    st.caption(f"{num(len(lista))} produtos · {brl0(lista['valor_estoque'].sum())} em estoque")
    tabela = lista[["medicamento", "situacao", "estoque_atual", "valor_estoque",
                    "demanda_diaria", "cobertura_dias", "giro", "dias_para_vencer",
                    "fornecedor_principal", "ultima_compra", "ultima_venda", "ean"]].rename(
        columns={"medicamento": "Medicamento", "situacao": "Situação",
                 "estoque_atual": "Estoque (un)", "valor_estoque": "Valor em estoque",
                 "demanda_diaria": "Venda por dia", "cobertura_dias": "Dura (dias)",
                 "giro": "Giro", "dias_para_vencer": "Lote mais antigo vence em (dias)",
                 "fornecedor_principal": "Fornecedor principal",
                 "ultima_compra": "Última compra", "ultima_venda": "Última venda", "ean": "EAN"})
    st.dataframe(tabela, width="stretch", hide_index=True, height=420, column_config={
        "Valor em estoque": st.column_config.NumberColumn(format="R$ %.2f"),
        "Venda por dia": st.column_config.NumberColumn(format="%.2f"),
        "Dura (dias)": st.column_config.NumberColumn(format="%.0f"),
        "Giro": st.column_config.NumberColumn(format="%.2fx"),
        "Lote mais antigo vence em (dias)": st.column_config.NumberColumn(format="%.0f"),
        "Última compra": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Última venda": st.column_config.DateColumn(format="DD/MM/YYYY")})
    st.download_button("Baixar a lista (CSV)",
                       tabela.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="posicao_estoque.csv", mime="text/csv",
                       icon=":material/download:")

    secao("Saldo de um produto ao longo do tempo",
          "Como o estoque subiu com as compras e desceu com as vendas.")
    ordem = pos.sort_values("faturamento", ascending=False)
    nomes = dict(zip(ordem["ean"], ordem["medicamento"]))
    ean = st.selectbox("Medicamento", ordem["ean"].tolist(), key="mov_produto",
                       format_func=lambda e: nomes.get(e, e),
                       help="Ordenados pelo valor vendido. Digite para buscar.")
    if not ean:
        return
    linha = pos.set_index("ean").loc[ean]
    traj = MV.trajetoria(rec, ean)
    linha_cartoes([
        ("Situação", str(linha["situacao"]), O_QUE_FAZER[linha["situacao"]]),
        ("Estoque", f"{num(linha['estoque_atual'])} un",
         (f"dura {linha['cobertura_dias']:.0f} dias" if pd.notna(linha["cobertura_dias"])
          else "sem venda recente")),
        ("Vende por dia", f"{linha['demanda_diaria']:.2f} un".replace(".", ","),
         f"{num(linha['vendas'])} un no período"),
        ("Compras recebidas", num(linha["n_compras"]),
         f"última em {data(linha['ultima_compra'])}"),
    ], colunas=4)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=traj["data"], y=traj["saldo"], mode="lines",
                             line=dict(shape="hv", color=c["blue"], width=2),
                             fill="tozeroy", fillcolor="rgba(58,124,168,0.10)", name="Saldo",
                             hovertemplate="%{x|%d/%m/%Y}<br>saldo <b>%{y} un</b><extra></extra>"))
    ent = traj[traj["entrada"].notna()]
    fig.add_trace(go.Scatter(x=ent["data"], y=ent["saldo"], mode="markers+text",
                             marker=dict(size=8, color=c["teal"],
                                         line=dict(width=1.5, color="#FFFFFF")),
                             text=[f"+{int(q)}" for q in ent["entrada"]],
                             textposition="top center", textfont=dict(size=10, color=c["ink2"]),
                             name="Chegada de compra",
                             hovertemplate="%{x|%d/%m/%Y}<br>chegou <b>%{text} un</b>"
                                           "<extra></extra>"))
    per = traj[traj["perda"].notna()]
    if len(per):
        fig.add_trace(go.Scatter(x=per["data"], y=per["saldo"], mode="markers",
                                 marker=dict(size=9, color=c["red"], symbol="x"),
                                 name="Perda por validade", customdata=per["perda"],
                                 hovertemplate="%{x|%d/%m/%Y}<br>vencido <b>%{customdata} un"
                                               "</b><extra></extra>"))
    if linha["ponto_pedido"] > 0:
        fig.add_hline(y=linha["ponto_pedido"], line=dict(color=c["amber"], dash="dash"),
                      annotation_text=f"ponto de pedido · {int(linha['ponto_pedido'])} un",
                      annotation_position="top right")
    fig.update_layout(title=f"Saldo de {nomes.get(ean, ean)}", yaxis_title="unidades",
                      xaxis=dict(tickformat="%d/%m/%y"))
    mostrar(fig, 380,
            "O desenho esperado é um **dente de serra**: o saldo cai com as vendas, sobe quando "
            "a compra chega e volta a cair. O ideal é a compra chegar quando o saldo está perto "
            "do **ponto de pedido**. Chegar com a prateleira cheia é excesso; ficar muito tempo "
            "no zero é ruptura. A comparação com a política recomendada está em Reposição e "
            "Lotes.")


# ===========================================================================
#                            2. REPOSIÇÃO E LOTES
# ===========================================================================
def reposicao_lotes(p: Parametros) -> None:
    if not _abertura(REPOSICAO, "Quando pedir e quanto pedir de cada produto, qual o tamanho de "
                                "compra mais econômico e como o estoque se comporta com essa "
                                "política."):
        return
    c = cores()
    rec, _ = recorte()
    pos = posicao(p)
    agora = pos[pos["repor_agora"]]
    proxima = pos[(pos["qtd_sugerida"] > 0) & ~pos["repor_agora"]]
    lec = lembrar("mov_lote", MV.lote_economico, pos, rec, p)
    vc = lec["leitura"].value_counts()
    pol = pos["politica"].value_counts()
    ajustadas = pos.loc[(pos["fator_sazonal"] - 1).abs() > 0.02, "classe_terapeutica"].unique()
    leitura([
        f"<b>{num(len(agora))} produtos</b> já estão no ponto de pedido: comprar "
        f"<b>{num(agora['qtd_sugerida'].sum())} unidades</b> ({brl0(agora['valor_sugerido'].sum())}).",
        (f"Outros <b>{num(len(proxima))}</b> podem entrar na próxima cotação "
         f"({brl0(proxima['valor_sugerido'].sum())})." if len(proxima) else ""),
        (f"A demanda de <b>{len(ajustadas)}</b> classe(s) foi ajustada pela estação "
         f"({', '.join(a.split(' /')[0].lower() for a in ajustadas)})." if len(ajustadas) else ""),
        f"<b>{num(int(vc.get('compra acima do lote econômico', 0)))}</b> produtos são comprados "
        "em lotes maiores que o recomendado.",
    ])

    secao("Como o sistema decide", ajuda=(
        f"- **Demanda prevista por dia** = vendas dos últimos {p.mov_janela_demanda} dias ÷ "
        f"{p.mov_janela_demanda} × fator sazonal\n"
        "- **Fator sazonal** = índice da classe nos dias que a compra vai cobrir ÷ índice "
        "nos dias usados para medir a demanda (1 com pouco volume ou menos de 12 meses; "
        "entre 0,6 e 1,6)\n"
        "- **Sob encomenda** = classe Z de regularidade e menos de 1 unidade vendida por mês\n"
        f"- **Estoque de segurança** = z ({pct(p.mov_nivel_servico, 0)} de nível de serviço) "
        "× desvio da venda diária × fator × √prazo\n"
        "- **Ponto de pedido** = demanda prevista × prazo + segurança\n"
        "- **Quantidade** = demanda prevista × (prazo + cobertura desejada) + segurança − "
        f"estoque, limitada a {p.mov_cobertura_excesso} dias de estoque\n\n"
        "As réguas ficam em Preferências › Movimentação de estoque."))
    passos = st.columns(4)
    for col, (titulo, texto) in zip(passos, [
        ("① Quanto vende",
         f"Média dos últimos {p.mov_janela_demanda} dias, ajustada pela estação da classe."),
        ("② Que política",
         "Venda rara e irregular fica sob encomenda; o resto segue o ponto de pedido."),
        ("③ Quando pedir",
         f"Quando o estoque só cobre {p.mov_lead_time} dias de entrega mais a segurança."),
        ("④ Quanto pedir",
         f"O que falta para {p.mov_lead_time} + {p.mov_cobertura_alvo} dias, até "
         f"{p.mov_cobertura_excesso} dias de estoque."),
    ]):
        with col.container(border=True):
            st.markdown(f"**{titulo}**\n\n<small>{texto}</small>", unsafe_allow_html=True)

    secao("Política de cada produto")
    linha_cartoes([
        ("Ponto de pedido", num(int(pol.get("ponto de pedido", 0))),
         "reposição pela regra acima", "destaque"),
        ("Sob encomenda", num(int(pol.get("sob encomenda", 0))),
         "venda irregular e menor que 1 un/mês"),
        ("Sem venda recente", num(int(pol.get("sem venda recente", 0))),
         f"em linha, sem venda em {p.mov_janela_demanda} dias"),
        ("Fora de linha", num(int(pol.get("fora de linha", 0))),
         f"sem reposição há {p.mov_dias_descontinuado}+ dias"),
    ], colunas=4)

    secao("O que comprar", "Primeiro o que já está no ponto de pedido.")
    so_agora = st.toggle("Mostrar só os que precisam ser pedidos agora", key="rep_agora",
                         value=True)
    lista = agora if so_agora else pos[pos["qtd_sugerida"] > 0]
    lista = lista.sort_values(["repor_agora", "valor_sugerido"], ascending=[False, False])
    tabela = lista[["medicamento", "estoque_atual", "demanda_diaria", "fator_sazonal",
                    "demanda_prevista", "ponto_pedido", "estoque_seguranca", "qtd_sugerida",
                    "custo_ultimo", "valor_sugerido", "xyz", "fornecedor_principal"]].rename(
        columns={"medicamento": "Medicamento", "estoque_atual": "Estoque",
                 "demanda_diaria": f"Venda/dia ({p.mov_janela_demanda} d)",
                 "fator_sazonal": "Ajuste sazonal",
                 "demanda_prevista": "Venda/dia prevista", "ponto_pedido": "Ponto de pedido",
                 "estoque_seguranca": "Segurança", "qtd_sugerida": "Comprar (un)",
                 "custo_ultimo": "Último custo", "valor_sugerido": "Valor",
                 "xyz": "Regularidade", "fornecedor_principal": "Fornecedor principal"})
    st.caption(f"{num(len(tabela))} produtos · {num(tabela['Comprar (un)'].sum())} unidades · "
               f"{brl0(tabela['Valor'].sum())} (estimado)")
    st.dataframe(tabela, width="stretch", hide_index=True, height=380, column_config={
        f"Venda/dia ({p.mov_janela_demanda} d)": st.column_config.NumberColumn(format="%.2f"),
        "Ajuste sazonal": st.column_config.NumberColumn(format="×%.2f"),
        "Venda/dia prevista": st.column_config.NumberColumn(format="%.2f"),
        "Último custo": st.column_config.NumberColumn(format="R$ %.2f"),
        "Valor": st.column_config.NumberColumn(format="R$ %.2f")})
    st.download_button("Baixar a lista de compra (CSV)",
                       tabela.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="lista_compra.csv", mime="text/csv",
                       icon=":material/download:")

    secao("Dente de serra e lote econômico",
          "O saldo que aconteceu ao lado do comportamento ideal com o lote econômico, o ponto "
          "de pedido e os estoques mínimo e máximo.")
    candidatos = (lec[lec["politica"] == "ponto de pedido"]
                  .sort_values("demanda_anual", ascending=False))
    if candidatos.empty:
        st.info("Nenhum produto com reposição pelo ponto de pedido no recorte.")
    else:
        nomes = dict(zip(candidatos["ean"], candidatos["medicamento"]))
        ean = st.selectbox("Medicamento", candidatos["ean"].tolist(), key="rep_produto",
                           format_func=lambda e: nomes.get(e, e),
                           help="Produtos com reposição pelo ponto de pedido, do que mais vende "
                                "para o que menos vende.")
        dente_serra_produto(ean, p)

    comvenda = lec[lec["demanda_anual"] > 0]
    secao("Tamanho do lote", "O lote que a farmácia compra comparado ao recomendado.", ajuda=(
        "1. **Lote econômico (Harris, 1913)** = √(2 × venda anual × custo de pedir ÷ custo "
        f"de manter), com custo de pedir de {brl(p.mov_custo_pedido)} por item e custo de "
        f"manter de {pct(p.mov_taxa_manutencao, 0)} do valor ao ano.\n"
        "2. A fórmula supõe produto que não vence; por isso o lote é **limitado a "
        f"{p.mov_cobertura_excesso} dias de venda** — o limite valeu para "
        f"{num(int(comvenda['limitado_validade'].sum()))} de {num(len(comvenda))} produtos.\n"
        "3. **Estoque mínimo** = estoque de segurança; **máximo** = mínimo + lote.\n"
        "4. **Lote praticado** = mediana das quantidades compradas.\n\n"
        "Custos de pedir e de manter são premissas ajustáveis em Preferências."))
    linha_cartoes([
        ("Lote maior que o recomendado", num(int(vc.get("compra acima do lote econômico", 0))),
         "mais de 1,5 vez o lote recomendado", "roxo"),
        ("Lote adequado", num(int(vc.get("compra próxima do lote econômico", 0))),
         "entre 0,67 e 1,5 vez"),
        ("Lote menor que o recomendado", num(int(vc.get("compra abaixo do lote econômico", 0))),
         "pedidos mais frequentes que o necessário"),
    ], colunas=3)
    filtro = st.multiselect("Mostrar", sorted(lec["leitura"].unique()), key="mov_lote_filtro",
                            placeholder="Todos os produtos")
    lista = lec[lec["leitura"].isin(filtro)] if filtro else lec
    lista = lista.sort_values("demanda_anual", ascending=False)
    st.dataframe(lista[["medicamento", "leitura", "politica", "demanda_anual", "lote_praticado",
                        "lec", "estoque_minimo", "ponto_pedido", "estoque_maximo",
                        "estoque_atual"]].rename(columns={
        "medicamento": "Medicamento", "leitura": "Leitura", "politica": "Política",
        "demanda_anual": "Venda por ano", "lote_praticado": "Lote comprado",
        "lec": "Lote recomendado", "estoque_minimo": "Estoque mínimo",
        "ponto_pedido": "Ponto de pedido", "estoque_maximo": "Estoque máximo",
        "estoque_atual": "Estoque atual"}),
        hide_index=True, width="stretch", height=360, column_config={
            "Venda por ano": st.column_config.NumberColumn(format="%.0f")})

    secao("Quão confiável é a demanda",
          "Em cada data de corte, a demanda de 30 dias foi prevista só com os dados anteriores "
          "e comparada com o que foi vendido depois.")
    td = lembrar("mov_teste_demanda", MV.teste_demanda, rec, p)
    if td.empty:
        st.info("Período curto demais para testar a demanda.")
        return
    vies = td["previsto"].sum() / max(1.0, td["real"].sum()) - 1
    vies_media = td["previsto_media"].sum() / max(1.0, td["real"].sum()) - 1
    linha_cartoes([
        ("Erro por produto — método do sistema", pct(td["wape"].mean(), 0),
         "média com ajuste sazonal (WAPE)", "destaque"),
        ("Erro por produto — média simples", pct(td["wape_media"].mean(), 0),
         "sem ajuste sazonal"),
        ("Erro por produto — repetir o último mês", pct(td["wape_ingenuo"].mean(), 0),
         "referência ingênua"),
        ("Volume total previsto × vendido", f"{pct(vies, 0)} com ajuste",
         f"{pct(vies_media, 0)} sem ajuste (negativo = previu menos)"),
    ], colunas=4)
    fig = go.Figure()
    rot = td["corte"].dt.strftime("%d/%m/%y")
    fig.add_trace(go.Bar(x=rot, y=td["real"], name="Vendido nos 30 dias seguintes",
                         marker_color=c["blue_l"]))
    fig.add_trace(go.Scatter(x=rot, y=td["previsto"], name="Previsto com ajuste sazonal",
                             mode="lines+markers", line=dict(color=c["purple"])))
    fig.add_trace(go.Scatter(x=rot, y=td["previsto_media"], name="Previsto pela média simples",
                             mode="lines+markers", line=dict(color=c["ink3"], dash="dot")))
    fig.update_layout(title="Unidades previstas × vendidas em cada data de corte",
                      yaxis_title="unidades")
    mostrar(fig, 340,
            "O **WAPE** soma o erro absoluto de todos os produtos e divide pelo total vendido; "
            "evita que itens pequenos dominem a média.\n\nO ajuste sazonal aproxima o **volume "
            "total** nos meses de alta, mas o erro **produto a produto** quase não muda, porque "
            "a maioria vende poucas unidades por mês. Por isso a lista usa estoque de segurança "
            "e deve ser revisada antes de cotar.")


# ===========================================================================
#                          3. VALIDADE E REMARCAÇÃO
# ===========================================================================
def validade_remarcacao(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    faixa("Quanto já se perdeu por vencimento, que lotes vão vencer antes de serem vendidos, o "
          "que fazer com cada um e a <b>validade com que os produtos chegam</b> dos "
          "fornecedores.", VALIDADE)
    rec, _ = recorte()
    if rec is None:
        sem_livro()
    elif rec.mov.empty:
        st.warning("Nenhum produto da movimentação atende aos filtros em uso.")
    else:
        _validade_estoque(p)
    validade_recebimento(df, abc, p)


def _validade_estoque(p: Parametros) -> None:
    c = cores()
    rec, _ = recorte()
    pos = posicao(p)
    res = lembrar("mov_resumo", MV.resumo, rec, pos)
    vencer = lembrar("mov_lotes_vencer", MV.lotes_a_vencer, rec, p.mov_validade_proxima)
    prop = propostas(p)
    leitura([
        f"No período, <b>{brl0(res['perda_valor'])}</b> venceram em estoque "
        f"({pct(res['perda_pct'], 1)} do faturamento; a referência do setor é de 1% a 3%).",
        f"<b>{num(len(vencer))} lotes</b> vencem nos próximos {p.mov_validade_proxima} dias; "
        f"em <b>{num(len(prop))}</b> deles parte do saldo não sai a tempo no ritmo atual.",
        (f"Devolver ou remarcar recupera até <b>{brl0(prop['perda_evitada'].sum())}</b> a custo."
         if len(prop) else ""),
    ])

    secao("Perdas por vencimento")
    _comparativos_mes(rec, [("Perdas por validade (a custo)", "perdas", False, True),
                            ("Unidades vencidas", "un_perdas", False, False)], titulo=False)
    serie = lembrar("mov_serie", MV.serie_mensal, rec)
    if len(serie):
        fig = go.Figure(go.Bar(x=serie["ano_mes"].map(mes_label), y=serie["perdas"],
                               marker_color=c["red"],
                               hovertemplate="%{x}<br><b>R$ %{y:,.2f}</b> vencidos"
                                             "<extra></extra>"))
        media = serie["perdas"].mean()
        fig.add_hline(y=media, line=dict(color=c["ink3"], dash="dot"),
                      annotation_text=f"média · {brl0(media)}", annotation_position="top left")
        fig.update_layout(title="Valor vencido em estoque por mês (a custo)",
                          yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
        mostrar(fig, 300,
                "Custo dos lotes que venceram na prateleira em cada mês. Um lote vence quando a "
                "compra foi maior do que a venda conseguiu escoar até a validade.")
    perdidos = pos[pos["valor_perdas"] > 0].sort_values("valor_perdas", ascending=False)
    with st.expander(f"Produtos que mais perderam ({num(len(perdidos))})"):
        st.dataframe(perdidos[["medicamento", "perdas", "valor_perdas", "vendas", "situacao"]]
                     .rename(columns={"medicamento": "Medicamento", "perdas": "Vencido (un)",
                                      "valor_perdas": "Valor vencido", "vendas": "Vendido (un)",
                                      "situacao": "Situação"}),
                     hide_index=True, width="stretch", height=300, column_config={
                         "Valor vencido": st.column_config.NumberColumn(format="R$ %.2f")})

    _causas_perdas(rec)

    secao("O que fazer com cada lote",
          f"Lotes em estoque que vencem nos próximos {p.mov_validade_proxima} dias e não serão "
          "vendidos a tempo. Nenhum preço muda sem aprovação.")
    if prop.empty:
        st.success("Nenhum lote em risco de vencer na prateleira neste recorte.")
    else:
        etapas = st.columns(4)
        for col, (titulo, texto) in zip(etapas, [
            ("① Devolver", f"{MV.JANELA_DEVOLUCAO} dias ou mais até vencer: o distribuidor "
                           "aceita a troca e o custo volta inteiro."),
            ("② Remarcar", "Desconto pela faixa de prazo, sem vender abaixo do custo + 8% e "
                           "com até 60% de desconto."),
            ("③ Segregar", "Prazo menor que o necessário para o paciente concluir o "
                           "tratamento: não dispensar."),
            ("④ Controlados", "Devolução ou baixa com escrituração."),
        ]):
            with col.container(border=True):
                st.markdown(f"**{titulo}**\n\n<small>{texto}</small>", unsafe_allow_html=True)
        resumo = (prop.groupby("acao")
                      .agg(lotes=("Lote", "size"), unidades=("excedente", "sum"),
                           valor=("valor_excedente", "sum"),
                           recupera=("perda_evitada", "sum"))
                      .reindex([a for a in MV.ACOES if a in set(prop["acao"])]).reset_index())
        st.dataframe(resumo.rename(columns={"acao": "Ação proposta", "lotes": "Lotes",
                                            "unidades": "Unidades que não saem a tempo",
                                            "valor": "Valor a custo",
                                            "recupera": "Perda evitada (estimado)"}),
                     hide_index=True, width="stretch", column_config={
                         "Valor a custo": st.column_config.NumberColumn(format="R$ %.2f"),
                         "Perda evitada (estimado)": st.column_config.NumberColumn(
                             format="R$ %.2f")})
        filtro = st.multiselect("Ação", [a for a in MV.ACOES if a in set(prop["acao"])],
                                key="mov_acao", placeholder="Todas")
        lista = prop[prop["acao"].isin(filtro)] if filtro else prop
        tabela = lista[["medicamento", "Lote", "validade", "dias_para_vencer", "saldo",
                        "excedente", "valor_excedente", "acao", "preco_vigente",
                        "preco_proposto", "desconto_pct", "justificativa", "status"]].rename(
            columns={"medicamento": "Medicamento", "validade": "Validade",
                     "dias_para_vencer": "Vence em (dias)", "saldo": "Saldo do lote",
                     "excedente": "Não sai a tempo (un)", "valor_excedente": "Valor a custo",
                     "acao": "Ação", "preco_vigente": "Preço atual",
                     "preco_proposto": "Preço proposto", "desconto_pct": "Desconto",
                     "justificativa": "Por quê", "status": "Status"})
        st.dataframe(tabela, width="stretch", hide_index=True, height=380, column_config={
            "Validade": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Valor a custo": st.column_config.NumberColumn(format="R$ %.2f"),
            "Preço atual": st.column_config.NumberColumn(format="R$ %.2f"),
            "Preço proposto": st.column_config.NumberColumn(format="R$ %.2f"),
            "Desconto": st.column_config.NumberColumn(format="percent"),
            "Por quê": st.column_config.TextColumn(width="large")})
        st.download_button("Baixar as propostas (CSV)",
                           tabela.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           file_name="propostas_validade.csv", mime="text/csv",
                           icon=":material/download:")


def _causas_perdas(rec: MV.Recorte) -> None:
    """Fatores associados às perdas, lote a lote, com o critério de cada um."""
    c = cores()
    causas = lembrar("mov_causas_perdas", MV.causas_perdas, rec, st.session_state.get("base"))
    secao("Por que as perdas acontecem",
          "Cada lote vencido recebe um fator, o primeiro da lista que os movimentos comprovam. "
          "São fatores associados, medidos nos dados, não prova de causa.")
    if causas.empty:
        st.success("Nenhuma perda por validade no período.")
        return
    por = (causas.groupby("causa").agg(lotes=("Lote", "size"), unidades=("unidades", "sum"),
                                       valor=("valor", "sum"))
                 .reindex(MV.CAUSAS_PERDA).dropna().reset_index())
    total = por["valor"].sum()
    maior = por.sort_values("valor").iloc[-1]
    leitura([
        f"<b>{maior['causa']}</b> responde pela maior parte: {brl0(maior['valor'])} "
        f"({pct(maior['valor'] / total, 0)} das perdas, {num(maior['lotes'])} lotes).",
        f"Em mediana, <b>{pct((causas['unidades'] / causas['qtd_lote']).median(), 0)}</b> de "
        "cada lote perdido venceu na prateleira.",
    ])
    cor = {"Estoque de abertura": c["ink3"], "Chegou com validade curta": c["amber"],
           "Lote maior que a venda até a validade": c["red"],
           "Comprado sem histórico de venda": c["purple"],
           "Venda caiu depois da compra": c["blue"], "Outros fatores": c["gray3"]}
    ordem = por.sort_values("valor")
    fig = go.Figure(go.Bar(
        y=ordem["causa"], x=ordem["valor"], orientation="h",
        marker_color=[cor[k] for k in ordem["causa"]],
        text=[f"{brl0(v)} · {int(n)} lotes" for v, n in zip(ordem["valor"], ordem["lotes"])],
        textposition="outside", cliponaxis=False,
        customdata=[MV.CRITERIO_CAUSA[k] for k in ordem["causa"]],
        hovertemplate="%{y}<br><b>R$ %{x:,.0f}</b><br>%{customdata}<extra></extra>"))
    fig.update_layout(title="Perdas por fator associado (a custo)", xaxis_tickprefix="R$ ",
                      xaxis_tickformat=",.0f", margin=dict(r=120))
    mostrar(fig, 340,
            "Para cada lote vencido, o sistema localiza a entrada que o trouxe e mede: a validade "
            "restante na chegada (faixa da cotação), o tamanho do lote, a venda diária do produto "
            "nos 180 dias antes da compra e a venda entre a chegada e o vencimento. O fator é o "
            "primeiro critério que se confirma, nesta ordem:\n\n" +
            "\n".join(f"{i}. **{k}** — {v}" for i, (k, v) in
                      enumerate(MV.CRITERIO_CAUSA.items(), 1)))
    col1, col2 = st.columns(2)
    with col1:
        cl = (causas.groupby("Classe Terapêutica")["valor"].sum().sort_values().tail(8))
        fig = go.Figure(go.Bar(y=cl.index, x=cl.values, orientation="h", marker_color=c["red"],
                               text=[brl0(v) for v in cl.values], textposition="outside",
                               cliponaxis=False,
                               hovertemplate="%{y}<br><b>R$ %{x:,.0f}</b><extra></extra>"))
        fig.update_layout(title="Perdas por classe terapêutica (8 maiores)",
                          xaxis_tickprefix="R$ ", xaxis_tickformat=",.0f", margin=dict(r=80))
        mostrar(fig, 340, "Soma do custo dos lotes vencidos de cada classe no período.")
    with col2:
        compradas = causas[causas["origem_lote"] == "ENTRADA"]
        fx = (compradas.groupby(compradas["faixa_recebimento"].fillna("sem faixa"))["valor"]
                       .sum().reindex(["Fresco (≥70%)", "Normal (50-70%)", "Curto (30-50%)",
                                       "Crítico (<30%)"]).fillna(0))
        fig = go.Figure(go.Bar(x=fx.index, y=fx.values,
                               marker_color=[c["green"], c["blue"], c["amber"], c["red"]],
                               text=[brl0(v) for v in fx.values], textposition="outside",
                               cliponaxis=False,
                               hovertemplate="%{x}<br><b>R$ %{y:,.0f}</b><extra></extra>"))
        fig.update_layout(title="Perdas dos lotes comprados, pela validade na entrega",
                          yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
        mostrar(fig, 340,
                "Só os lotes que vieram de compras (o estoque de abertura não tem faixa). A faixa "
                "é quanto restava da validade quando o lote chegou.")
    with st.expander(f"Lotes perdidos e o fator de cada um ({num(len(causas))})"):
        st.dataframe(causas[["medicamento", "Lote", "data", "unidades", "valor", "causa",
                             "chegada", "qtd_lote", "vida_na_chegada", "faixa_recebimento",
                             "venda_dia_antes", "venda_ate_validade"]].rename(columns={
            "medicamento": "Medicamento", "data": "Venceu em", "unidades": "Unidades",
            "valor": "Valor", "causa": "Fator", "chegada": "Chegou em",
            "qtd_lote": "Lote recebido (un)", "vida_na_chegada": "Validade na chegada (dias)",
            "faixa_recebimento": "Faixa na entrega", "venda_dia_antes": "Venda/dia antes",
            "venda_ate_validade": "Venda esperada até vencer (un)"}),
            hide_index=True, width="stretch", height=320, column_config={
                "Venceu em": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Chegou em": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
                "Venda/dia antes": st.column_config.NumberColumn(format="%.3f"),
                "Venda esperada até vencer (un)": st.column_config.NumberColumn(format="%.0f")})


def validade_recebimento(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    """Validade do que entrou: vida útil na entrega e último lote de cada item.

    Vem só da base de compras, então funciona também sem o livro de movimentação.
    """
    c = cores()
    secao("Validade no recebimento",
          "Quanto da validade restava quando cada compra chegou, por faixa e por fornecedor.")
    hoje, ajustada = M.data_referencia(df, p)
    jan = p.validade_risco_meses
    todos_lotes = M.posicao_lotes(df, abc, hoje)
    lotes = todos_lotes[todos_lotes["validade"].notna()]
    vencidos = lotes[lotes["meses_restantes"] < 0]
    na_janela = lotes[(lotes["meses_restantes"] >= 0) & (lotes["meses_restantes"] < jan)]
    meses_txt = "mês" if jan == 1 else "meses"
    linha_cartoes([
        ("Linhas com vida útil curta", pct(df["validade_curta"].mean()),
         "chegaram com menos de 50% da validade", "destaque"),
        ("Último lote já vencido", num(len(vencidos)),
         f"{brl0(vencidos['valor_lote'].sum())} · data de referência {data(hoje)}",
         "", "estimado"),
        (f"Último lote vence em até {jan} {meses_txt}", num(len(na_janela)),
         f"{brl0(na_janela['valor_lote'].sum())} em risco", "", "estimado"),
    ], colunas=3)
    if ajustada:
        st.caption(f"A data de Preferências ({data(pd.Timestamp(p.data_referencia))}) é anterior "
                   "à última compra; vale a data da última compra.")

    qual = M.qualidade_entrega(df, p)
    col1, col2 = st.columns(2)
    with col1:
        from core.dados import ORDEM_FAIXAS
        fx = df.groupby("Faixa de Recebimento", as_index=False)["valor_faturado"].sum()
        fx["ordem"] = fx["Faixa de Recebimento"].map({f: i for i, f in enumerate(ORDEM_FAIXAS)})
        fx = fx.sort_values("ordem", na_position="last")
        cor_faixa = dict(zip(ORDEM_FAIXAS, [c["green"], c["blue"], c["amber"], c["red"]]))
        fig = go.Figure(go.Pie(labels=fx["Faixa de Recebimento"], values=fx["valor_faturado"],
                               hole=0.6, sort=False, textinfo="percent",
                               marker=dict(colors=[cor_faixa.get(f, c["gray3"])
                                                   for f in fx["Faixa de Recebimento"]],
                                           line=dict(color="#FFFFFF", width=2)),
                               hovertemplate="%{label}<br><b>R$ %{value:,.2f}</b>"
                                             "<extra></extra>"))
        fig.update_layout(title="Valor faturado por vida útil na entrega")
        mostrar(fig, 320,
                "Quanto sobrava da validade quando o lote chegou, em % do prazo total: "
                "**fresco** 70% ou mais, **normal** 50% a 70%, **curto** 30% a 50%, "
                "**crítico** menos de 30%. Curto e crítico exigem giro rápido.")
    with col2:
        if not qual.empty:
            altura = max(320, len(qual) * 34 + 110)
            fig = go.Figure(go.Bar(x=qual.sort_values("pct")["pct"],
                                   y=qual.sort_values("pct")["fornecedor"], orientation="h",
                                   marker_color=c["amber"],
                                   hovertemplate="%{y}<br><b>%{x:.1%}</b><extra></extra>"))
            fig.update_layout(title="Linhas com validade curta por fornecedor",
                              xaxis_tickformat=".0%")
            mostrar(fig, altura,
                    "Linhas recebidas nas faixas **curto** ou **crítico**. Só entram "
                    f"fornecedores com {p.linhas_minimas} ou mais linhas.")
        else:
            st.info("Nenhum fornecedor com linhas suficientes para avaliar no recorte.")

    with st.expander("Último lote recebido de cada medicamento"):
        escopos = {
            "Todos": lambda d: d,
            "Já vencidos": lambda d: d[d["meses_restantes"] < 0],
            f"Vencem em até {jan} {meses_txt}": lambda d: d[(d["meses_restantes"] >= 0) &
                                                            (d["meses_restantes"] < jan)],
            "Somente classe A": lambda d: d[d["classe"] == "A"],
            f"Recorrentes ({p.recorrencia_minima}+ compras)":
                lambda d: d[d["compras"] >= p.recorrencia_minima],
        }
        escopo = st.radio("Escopo", list(escopos), horizontal=True, key="escopo_estoque",
                          label_visibility="collapsed")
        visiveis = escopos[escopo](lotes)
        cols = ["medicamento", "classe", "fornecedor", "compras", "quantidade", "valor_lote",
                "gasto_acumulado", "recebido_em", "validade", "meses_restantes",
                "vida_util_entrega"]
        st.dataframe(visiveis[cols].rename(columns={
            "medicamento": "Medicamento", "classe": "Curva ABC", "fornecedor": "Fornecedor",
            "compras": "Compras", "quantidade": "Quantidade", "valor_lote": "Valor do lote",
            "gasto_acumulado": "Gasto acumulado", "recebido_em": "Recebido em",
            "validade": "Validade", "meses_restantes": "Meses restantes",
            "vida_util_entrega": "Vida útil na entrega"}),
            width="stretch", hide_index=True, height=380, column_config={
                "Recebido em": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Validade": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Valor do lote": st.column_config.NumberColumn(format="R$ %.2f"),
                "Gasto acumulado": st.column_config.NumberColumn(format="R$ %.2f"),
                "Meses restantes": st.column_config.NumberColumn(format="%.1f")})
        st.caption(f"{num(len(visiveis))} de {num(len(lotes))} medicamentos com validade "
                   "registrada. Prazo contado a partir da data de referência.")
