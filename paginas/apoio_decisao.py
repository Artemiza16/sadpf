"""
Sistema de Apoio à Decisão.

Abre com um diagnóstico do recorte, lista os pontos em cartões ordenáveis por
prioridade ou por assunto, e fecha com um plano de ação em ordem de impacto.
O detalhe de cada ponto só aparece quando o painel é aberto.
"""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from core import decisao as Dc
from core import leituras as L
from core import metricas as M
from core import parametros as PR
from core.memoria import lembrar
from core.parametros import Parametros
from core.tema import (brl, brl0, cores, faixa, legenda_natureza, mes_label, mostrar, num,
                       pct, selo_natureza)


def insights_da_sessao(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> list:
    """Os pontos do recorte: 21 da base de compras e, havendo livro de
    movimentação, os 5 de entradas e saídas."""
    from paginas.movimentacao import para_decisao
    return lembrar("insights", Dc.gerar, df, abc, p, para_decisao(p))


def _cartao(ins: Dc.Insight, alterados: set[str], p: Parametros) -> str:
    c = cores()
    borda = {"crit": c["red"], "aten": c["amber"], "ok": c["green"], "info": c["blue"]}[ins.nivel]
    tam = "16px" if len(ins.valor) > 14 else "25px"
    impacto = ""
    if ins.impacto > 0:
        rotulo = "Economia possível" if ins.tipo == "economia" else "Valor exposto"
        impacto = (f"<div style='font-size:10.5px;color:{c['ink3']};margin-top:8px;"
                   f"padding-top:7px;border-top:1px dashed {c['line']}'>{rotulo} "
                   f"<b style='color:{c['blue_d']}'>{brl0(ins.impacto)}</b></div>")
    # aviso de que uma régua deste ponto foi mudada em Preferências
    mudadas = [r for r in ins.reguas if r in alterados]
    regua = ""
    if mudadas:
        nomes = " · ".join(f"{PR.descrever(r)[0]}: {PR.formatar(r, getattr(p, r))}"
                           for r in mudadas[:2])
        regua = f"<div class='regua-alterada'>⚙ Régua ajustada — {escape(nomes)}</div>"
    return f"""<div class="cartao" style="border-left:4px solid {borda}">
      <div class="rot" style="display:flex;align-items:center;gap:8px">
        <span style="font-size:16px">{ins.icone}</span>{ins.titulo}{selo_natureza(ins.natureza)}</div>
      <div class="val" style="font-size:{tam}">{ins.valor}</div>
      <div class="sub">{ins.frase}</div>
      {impacto}{regua}
      <div style="margin-top:10px"><span class="selo {ins.nivel}">
        {Dc.NIVEIS[ins.nivel]}</span></div></div>"""


def _reguas(ins: Dc.Insight, p: Parametros) -> str:
    """Réguas de Preferências que definem o ponto, com o valor atual e o padrão."""
    if not ins.reguas:
        return ""
    itens = []
    for r in ins.reguas:
        atual, padrao = getattr(p, r), getattr(PR.PADRAO, r)
        marca = " <span class='alterado'>alterada</span>" if atual != padrao else ""
        itens.append(f"<li><span class='det-nome'>{escape(PR.descrever(r)[0])}{marca}</span>"
                     f"<span class='det-info'>{escape(PR.formatar(r, atual))} · padrão "
                     f"{escape(PR.formatar(r, padrao))}</span></li>")
    return ("<div class='bloco-rot'>RÉGUAS QUE DEFINEM ESTE PONTO</div>"
            f"<ul class='det-lista reguas'>{''.join(itens)}</ul>")


def _lista(titulo: str, itens: list[tuple[str, str]]) -> str:
    """Lista nome + indicador que quebra linha, em vez de cortar como a tabela."""
    linhas = "".join(f"<li><span class='det-nome'>{escape(str(nome))}</span>"
                     f"<span class='det-info'>{escape(str(info))}</span></li>"
                     for nome, info in itens)
    return f"<div class='bloco-rot'>{titulo}</div><ul class='det-lista'>{linhas}</ul>"


def _detalhe(ins: Dc.Insight, p: Parametros) -> None:
    # cabeçalho em HTML simples: um título Markdown ganharia o ícone de âncora
    st.markdown(
        f"<div class='det-topo'><div><span class='det-num'>{ins.indicador[0]}</span>"
        f"<span class='det-txt'>{ins.indicador[1]}</span></div>"
        f"<span class='selo {ins.nivel}'>{Dc.NIVEIS[ins.nivel]}</span></div>",
        unsafe_allow_html=True)

    st.markdown(f"**Resumo da situação** — {ins.resumo}")
    st.caption(f"Período analisado: {ins.periodo}")

    blocos = []
    if ins.valores:
        caixas = "".join(f"<div class='det-valor'><span>{rot}</span><b>{val}</b></div>"
                         for rot, val in ins.valores)
        blocos.append(f"<div class='bloco-rot'>VALORES</div>"
                      f"<div class='det-valores'>{caixas}</div>")
    if ins.medicamentos:
        blocos.append(_lista("MEDICAMENTOS ENVOLVIDOS", ins.medicamentos))
    if ins.fornecedores:
        blocos.append(_lista("FORNECEDORES ENVOLVIDOS", ins.fornecedores))
    blocos.append(f"<div class='bloco-rot'>EXPLICAÇÃO</div>"
                  f"<p class='det-expl'>{ins.explicacao}</p>"
                  f"<div class='acao'><b>Ação sugerida:</b> {ins.acao}</div>")
    blocos.append(_reguas(ins, p))
    st.markdown("".join(blocos), unsafe_allow_html=True)
    paginas = st.session_state.get("paginas_menu", {})
    if ins.reguas and "Preferências" in paginas:
        st.page_link(paginas["Preferências"], label="Ajustar estas réguas em Preferências",
                     icon=":material/tune:")


def _leitura(insights: list[Dc.Insight], diag: dict, df: pd.DataFrame,
             p: Parametros) -> None:
    """Quadro da leitura atual e do que mudou desde a anterior.

    A comparação pega tanto réguas ajustadas em Preferências quanto cotações
    novas incluídas na Base de Dados: os dois disparam uma nova leitura.
    """
    c = cores()
    atual = L.retrato(insights, diag, df, p, st.session_state.get("versao_base"))
    chave = repr(st.session_state.get("filtros_ativos", []))
    mudanca = L.comparar(L.registrar(chave, atual), atual)
    alterados = PR.alterados(p)
    reguas_txt = (f"{len(alterados)} régua(s) ajustada(s) em Preferências"
                  if [a for a in alterados if a != "nomes_originais"]
                  else "réguas no padrão")
    st.markdown(
        f"<div class='leitura'><span class='material-symbols-rounded' aria-hidden='true'>"
        f"radar</span><span><b>Leitura de {atual['quando']}</b> · {num(atual['linhas'])} "
        f"linhas · {atual['cotacoes']} cotações · última compra em {atual['ultima_compra']} "
        f"· {reguas_txt}</span></div>", unsafe_allow_html=True)
    if not mudanca or not (mudanca["motivos"] or mudanca["reguas"] or mudanca["pontos"]):
        return
    with st.expander(f"O que mudou desde a leitura anterior ({mudanca['quando']}) — "
                     f"{len(mudanca['pontos'])} ponto(s) alterado(s)", expanded=True):
        motivos = list(mudanca["motivos"]) + [f"{rot}: {de} → {para}"
                                              for rot, de, para in mudanca["reguas"]]
        # "$" escapado: dois "R$" na mesma linha viram fórmula matemática no Markdown
        if motivos:
            st.markdown(("**Por quê:** " + " · ".join(motivos)).replace("$", "\\$"))
        if mudanca["economia_de"] != mudanca["economia_para"]:
            st.markdown(f"**Economia direta:** {brl0(mudanca['economia_de'])} → "
                        f"{brl0(mudanca['economia_para'])}".replace("$", "\\$"))
        if not mudanca["pontos"]:
            st.caption("Nenhum ponto mudou de valor ou de gravidade com esta mudança.")
            return
        linhas = []
        for pt in mudanca["pontos"]:
            if pt["novo"]:
                nivel = f"<span class='selo {pt['para']}'>novo · {Dc.NIVEIS[pt['para']]}</span>"
            elif pt["de"] != pt["para"]:
                piorou = Dc.PESO[pt["para"]] < Dc.PESO[pt["de"]]
                seta = (f"<b style='color:{c['red'] if piorou else c['green']}'>"
                        f"{'▲ piorou' if piorou else '▼ melhorou'}</b>")
                nivel = (f"<span class='selo {pt['de']}'>{Dc.NIVEIS[pt['de']]}</span> → "
                         f"<span class='selo {pt['para']}'>{Dc.NIVEIS[pt['para']]}</span> {seta}")
            else:
                nivel = f"<span class='selo {pt['para']}'>{Dc.NIVEIS[pt['para']]}</span>"
            linhas.append(f"<li><span class='det-nome'>{escape(pt['titulo'])}</span>"
                          f"<span class='det-info'>{escape(str(pt['valor_de']))} → "
                          f"<b>{escape(str(pt['valor_para']))}</b> &nbsp; {nivel}</span></li>")
        st.markdown(f"<ul class='det-lista mudancas'>{''.join(linhas)}</ul>",
                    unsafe_allow_html=True)


def _graficos(insights: list[Dc.Insight], diag: dict, df: pd.DataFrame,
              p: Parametros) -> None:
    """Os gráficos que sustentam o diagnóstico.

    Cada aba mostra a tendência por trás de um grupo de pontos, com a régua de
    Preferências desenhada como linha: o gestor vê o número cruzar o limite em
    vez de só ler que ele cruzou.
    """
    import plotly.graph_objects as go
    from core import movimentacao as MV
    from paginas.movimentacao import recorte as recorte_mov
    c = cores()
    st.subheader("Os gráficos por trás do diagnóstico")
    st.caption("Cada aba mostra a evolução que fundamenta um grupo de pontos, com o limite "
               "de Preferências desenhado no gráfico.")
    rec, _ = recorte_mov()
    nomes = ["Valor por ponto", "Compras mês a mês", "Custo dos medicamentos",
             "Dependência de fornecedor"]
    if rec is not None and not rec.mov.empty:
        nomes.append("Estoque e vendas")
    abas = st.tabs(nomes)
    cor_nivel = {"crit": c["red"], "aten": c["amber"], "ok": c["green"], "info": c["blue"]}

    with abas[0]:
        com_valor = sorted([i for i in insights if i.impacto > 0], key=lambda i: i.impacto)
        if not com_valor:
            st.info("Nenhum ponto com valor em reais neste recorte.")
        else:
            rotulos = [i.titulo + (" (estimado)" if i.natureza == "estimado" else "")
                       for i in com_valor]
            fig = go.Figure(go.Bar(
                y=rotulos, x=[i.impacto for i in com_valor], orientation="h",
                marker_color=[cor_nivel[i.nivel] for i in com_valor],
                text=[f"{brl0(i.impacto)} · {'recuperável' if i.tipo == 'economia' else 'exposto'}"
                      for i in com_valor], textposition="outside", cliponaxis=False,
                hovertemplate="%{y}<br><b>R$ %{x:,.0f}</b><extra></extra>"))
            fig.update_layout(title="Valor em reais de cada ponto (cor = gravidade)",
                              xaxis_tickprefix="R$ ", xaxis_tickformat=",.0f",
                              margin=dict(r=120))
            mostrar(fig, 120 + 34 * len(com_valor),
                    "**Recuperável** (economia) é dinheiro que dá para trazer de volta e pode ser "
                    "somado; **exposto** é valor sob risco e não se soma, porque o mesmo "
                    "medicamento aparece em mais de um ponto. Pontos marcados como *estimado* "
                    "dependem de uma premissa declarada no detalhe do ponto.")

    with abas[1]:
        s = M.serie_mensal(df)
        if len(s) > 1:
            media = s["valor_pedido"].mean()
            limite = media * p.pico_mensal
            fig = go.Figure(go.Bar(
                x=s["ano_mes"].map(mes_label), y=s["valor_pedido"],
                marker_color=[c["amber"] if v > limite else c["blue_l"] for v in s["valor_pedido"]],
                hovertemplate="%{x}<br><b>R$ %{y:,.2f}</b><extra></extra>", name="Gasto"))
            fig.add_hline(y=media, line=dict(color=c["ink3"], dash="dot"),
                          annotation_text=f"média {brl0(media)}", annotation_position="top left")
            fig.add_hline(y=limite, line=dict(color=c["amber"], dash="dash"),
                          annotation_text=f"pico: acima de {brl0(limite)}",
                          annotation_position="top right")
            fig.update_layout(title="Compras por mês (em âmbar, os meses de pico)",
                              yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f", showlegend=False)
            mostrar(fig, 340,
                    "Fundamenta o ponto **Meses de maior desembolso**. Um mês é pico quando "
                    f"passa de {str(round(p.pico_mensal, 2)).replace('.', ',')}× a média "
                    "mensal (régua em Preferências).")

    with abas[2]:
        ind = M.indice_custo(df, p)
        if len(ind) > 1:
            fig = go.Figure(go.Scatter(
                x=ind["ano_mes"].map(mes_label), y=ind["indice"], mode="lines+markers",
                line=dict(color=c["purple"], width=2.4),
                hovertemplate="%{x}<br>índice <b>%{y:.1f}</b><extra></extra>"))
            fig.add_hline(y=100, line=dict(color=c["ink3"], dash="dot"),
                          annotation_text="custo da 1ª compra = 100")
            fig.add_hline(y=100 * (1 + p.alta_custo_relevante), line=dict(color=c["red"],
                                                                           dash="dash"),
                          annotation_text=f"alta relevante (+{pct(p.alta_custo_relevante, 0)})",
                          annotation_position="top right")
            fig.update_layout(title="Índice de custo dos mesmos medicamentos (100 = 1ª compra)",
                              showlegend=False)
            mostrar(fig, 340,
                    "Fundamenta **Custos em alta** e **Inflação de custo da cesta**. Cada compra "
                    "é comparada com o custo da primeira compra do mesmo medicamento, então a "
                    "linha mede reajuste de preço e não mudança de mix.")

    with abas[3]:
        forn = M.por_dimensao(df, "Nome do Fornecedor")
        total = forn["valor_pedido"].sum() or 1.0
        forn = forn.assign(part=forn["valor_pedido"] / total).sort_values("part")
        fig = go.Figure(go.Bar(
            y=forn["Nome do Fornecedor"], x=forn["part"], orientation="h",
            marker_color=[c["red"] if v > p.concentracao_fornecedor else c["blue"]
                          for v in forn["part"]],
            text=[pct(v, 1) for v in forn["part"]], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}<br><b>%{x:.1%}</b> do valor<extra></extra>"))
        fig.add_vline(x=p.concentracao_fornecedor, line=dict(color=c["red"], dash="dash"),
                      annotation_text=f"limite {pct(p.concentracao_fornecedor, 0)}")
        fig.update_layout(title="Participação de cada fornecedor no valor comprado",
                          xaxis_tickformat=".0%")
        mostrar(fig, 120 + 30 * len(forn),
                "Fundamenta **Dependência de um fornecedor**. Acima do limite, um atraso ou "
                "reajuste desse distribuidor atinge boa parte das compras.")

    if len(abas) > 4:
        with abas[4]:
            s = lembrar("mov_serie", MV.serie_mensal, rec)
            if len(s):
                rot = s["ano_mes"].map(mes_label)
                fig = go.Figure()
                fig.add_trace(go.Bar(x=rot, y=s["faturamento"], name="Vendas",
                                     marker_color=c["teal_l"],
                                     hovertemplate="%{x}<br>vendas <b>R$ %{y:,.0f}</b>"
                                                   "<extra></extra>"))
                fig.add_trace(go.Bar(x=rot, y=s["compras"], name="Compras",
                                     marker_color=c["blue"],
                                     hovertemplate="%{x}<br>compras <b>R$ %{y:,.0f}</b>"
                                                   "<extra></extra>"))
                fig.add_trace(go.Scatter(x=rot, y=s["perdas"], name="Perdas por validade",
                                         mode="lines+markers", yaxis="y2",
                                         line=dict(color=c["red"]),
                                         hovertemplate="%{x}<br>perdas <b>R$ %{y:,.0f}</b>"
                                                       "<extra></extra>"))
                fig.update_layout(title="Compras, vendas e perdas por mês", barmode="group",
                                  yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f",
                                  yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                              tickprefix="R$ ", rangemode="tozero"))
                mostrar(fig, 360,
                        "Fundamenta os pontos de **Movimentação**. Compras acima das vendas por "
                        "meses seguidos acumulam capital parado e, depois, perda por validade.")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)


def apoio_decisao(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    c = cores()
    insights = insights_da_sessao(df, abc, p)
    if not insights:
        st.info("Nenhuma linha no recorte para gerar recomendações.")
        return

    total = M.indicadores(df).valor_pedido or 1.0
    diag = Dc.diagnostico(insights, total)
    contagem = diag["contagem"]

    faixa("As leituras que viram <b>ação</b>, ancoradas na Curva ABC. O painel mede o "
          "impacto financeiro de cada ponto e ordena por prioridade — abra qualquer cartão "
          "para ver o detalhe, a decisão sugerida e as réguas que o definem. Cotações novas "
          "e ajustes em Preferências geram uma <b>nova leitura</b>, comparada com a "
          "anterior.", "Sistema de Apoio à Decisão")
    _leitura(insights, diag, df, p)
    alterados = set(PR.alterados(p))

    st.subheader("Diagnóstico do recorte")
    st.caption(f"{insights[0].periodo} · {num(len(df))} linhas analisadas")

    esq, dir_ = st.columns([1.15, 1])
    with esq:
        st.markdown("**Como está a gestão de compras**")
        cols = st.columns(4)
        for col, nv in zip(cols, ("crit", "aten", "info", "ok")):
            rotulo = Dc.NIVEIS[nv] if contagem[nv] == 1 else Dc.PLURAL[nv]
            cor = c[{"crit": "red", "aten": "amber", "info": "blue", "ok": "green"}[nv]]
            col.markdown(
                f"<div class='cartao' style='padding:11px 13px'>"
                f"<b style='display:block;font-size:22px;color:{cor};line-height:1'>"
                f"{contagem[nv]}</b>"
                f"<span style='font-size:10.5px'>{rotulo}</span></div>",
                unsafe_allow_html=True)
        # barra de gravidade
        partes = "".join(
            f"<i style='display:block;width:{contagem[nv]/len(insights)*100:.1f}%;"
            f"background:{c[{'crit':'red','aten':'amber','info':'blue','ok':'green'}[nv]]}'></i>"
            for nv in ("crit", "aten", "info", "ok"))
        st.markdown(f"<div style='display:flex;height:9px;border-radius:5px;overflow:hidden;"
                    f"margin-top:12px;background:{c['line']}'>{partes}</div>",
                    unsafe_allow_html=True)
    with dir_:
        maior = diag["maior_exposicao"]
        extra = ""
        if maior is not None:
            extra = (f" Há valor <b>exposto</b> a risco, sendo o maior ponto "
                     f"{brl0(maior.impacto)} em {maior.titulo.lower()}; esses montantes se "
                     "sobrepõem e por isso não são somados.")
        if diag["economia"] > 0:
            texto = (f"{pct(diag['economia_pct'])} do valor comprado — dinheiro que o próprio "
                     "histórico mostra ser recuperável, em preço de fornecedor e em custo "
                     "que subiu.")
            valor = brl0(diag["economia"])
        else:
            texto = ("Neste recorte não há economia direta a capturar: ela depende de "
                     "comparar o mesmo medicamento entre fornecedores diferentes.")
            valor = "Nenhuma"
        st.markdown(f"<div class='impactobox'><span>Economia direta identificada</span>"
                    f"<b class='big'>{valor}</b><small>{texto}{extra}</small></div>",
                    unsafe_allow_html=True)

    _graficos(insights, diag, df, p)

    st.subheader("Os pontos, um a um")
    legenda_natureza()
    col_ord, col_niv = st.columns([1, 1])
    ordem = col_ord.radio("Ordenar por", ["Prioridade", "Assunto"], horizontal=True,
                          key="sad_ordem")
    filtro_nivel = col_niv.selectbox(
        "Mostrar", ["Todas as gravidades"] +
        [Dc.PLURAL[nv] for nv in ("crit", "aten", "info", "ok")], key="sad_nivel")

    ordem_cat = {chave: i for i, (chave, _, _) in enumerate(Dc.CATEGORIAS)}
    if ordem == "Prioridade":
        insights.sort(key=lambda i: (Dc.PESO[i.nivel], -i.impacto))
    else:
        insights.sort(key=lambda i: ordem_cat.get(i.categoria, 9))

    if filtro_nivel != "Todas as gravidades":
        alvo = next(nv for nv in Dc.NIVEIS if Dc.PLURAL[nv] == filtro_nivel)
        insights = [i for i in insights if i.nivel == alvo]

    abas = st.tabs(["Tudo"] + [f"{ico} {nome}" for _, nome, ico in Dc.CATEGORIAS])

    def render(lista: list[Dc.Insight]) -> None:
        if not lista:
            st.info("Nenhum ponto nesta combinação de assunto e gravidade.")
            return
        for inicio in range(0, len(lista), 3):
            for col, ins in zip(st.columns(3, gap="small"), lista[inicio:inicio + 3]):
                with col:
                    st.markdown(_cartao(ins, alterados, p), unsafe_allow_html=True)
                    with st.expander("Ver detalhes"):
                        _detalhe(ins, p)
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    with abas[0]:
        render(insights)
    for aba, (chave, _, _) in zip(abas[1:], Dc.CATEGORIAS):
        with aba:
            render([i for i in insights if i.categoria == chave])

    if diag["acionaveis"]:
        st.subheader("Plano de ação")
        st.caption("As decisões em ordem de impacto financeiro.")
        for i, ins in enumerate(diag["acionaveis"], start=1):
            borda = c["red"] if ins.nivel == "crit" else c["amber"]
            if ins.impacto > 0:
                valor = brl0(ins.impacto)
                unidade = "recuperável" if ins.tipo == "economia" else "exposto"
            else:
                valor, unidade = Dc.NIVEIS[ins.nivel], "sem valor em reais"
            st.markdown(
                f"<div class='cartao' style='border-left:4px solid {borda};"
                f"display:flex;gap:14px;align-items:flex-start;margin-bottom:10px'>"
                f"<span style='flex:0 0 26px;height:26px;border-radius:50%;"
                f"background:{c['wash']};color:{c['blue_d']};display:flex;"
                f"align-items:center;justify-content:center;font-size:12px;"
                f"font-weight:700'>{i}</span>"
                f"<span style='flex:1'><b style='display:block;font-size:13px;"
                f"color:{c['ink']}'>{ins.titulo}</b>"
                f"<span style='font-size:12.5px;color:{c['ink2']}'>{ins.acao}</span></span>"
                f"<span style='text-align:right;flex:0 0 auto'><b style='display:block;"
                f"font-size:14px;color:{c['ink']};white-space:nowrap'>{valor}</b>"
                f"<span style='font-size:10px;color:{c['ink3']}'>{unidade}</span></span>"
                f"</div>", unsafe_allow_html=True)
