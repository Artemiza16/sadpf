"""
Gera as figuras, tabelas e números do relatório de resultados (relatorio/).

    python gerar_relatorio.py

Saídas:
    relatorio/figuras/*.png     gráficos usados no RELATORIO_RESULTADOS.md
    relatorio/tabelas/*.csv     tabelas de apoio (separador ;, decimal ,)
    relatorio/numeros.json      os números citados no texto

Compara o sistema ANTES (só a base de cotações, dados observados) e DEPOIS da
inclusão do livro de movimentação (entradas observadas, saídas simuladas), para a
Curva ABC, as previsões de compra e o apoio à decisão. Os nomes de fornecedores
saem codificados, como no painel. As figuras em PNG precisam do pacote kaleido
(pip install -r requirements-relatorio.txt); sem ele, o script grava só as
tabelas e os números e avisa.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from core import dados as D                 # noqa: E402
from core import decisao as Dc              # noqa: E402
from core import metricas as M              # noqa: E402
from core import movimentacao as MV         # noqa: E402
from core import previsao as PV             # noqa: E402
from core import tema as T                  # noqa: E402
from core.parametros import Parametros      # noqa: E402

SAIDA = RAIZ / "relatorio"
FIG, TAB = SAIDA / "figuras", SAIDA / "tabelas"
C = T.PALETA["claro"]
COR_OBS, COR_SIM = C["blue"], C["amber"]      # observado × simulado, em todas as figuras
NUM: dict = {}
PNG_OK = True


def salvar(fig: go.Figure, nome: str, altura: int = 460, largura: int = 1000) -> None:
    global PNG_OK
    fig.update_layout(template="sadpf_branco_claro", height=altura, width=largura,
                      paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", separators=",.",
                      margin=dict(l=20, r=30, t=70, b=40), font=dict(size=13))
    if not PNG_OK:
        return
    try:
        fig.write_image(FIG / f"{nome}.png", scale=2)
    except Exception as erro:                              # noqa: BLE001
        PNG_OK = False
        print(f"  (figuras não geradas: {erro.__class__.__name__}; instale o kaleido)")


def tabela(df: pd.DataFrame, nome: str) -> None:
    df.to_csv(TAB / f"{nome}.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")


def r(x, casas=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), casas)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    p = Parametros()
    base, _ = D.carregar_base()
    df = D.anonimizar(base, D.apelidos(base))
    mov = MV.anonimizar(MV.carregar(), D.apelidos(base))
    rec = MV.recortar(mov)
    pos = MV.posicao(rec, p)
    res = MV.resumo(rec, pos)
    ind = M.indicadores(df)

    # ------------------------------------------------------------ a base
    NUM["base"] = {"linhas": int(ind.linhas), "cotacoes": int(ind.cotacoes),
                   "pedidos": int(ind.pedidos), "fornecedores": int(ind.fornecedores),
                   "medicamentos": int(ind.medicamentos), "valor_pedido": r(ind.valor_pedido, 2),
                   "valor_faturado": r(ind.valor_faturado, 2), "inicio": str(ind.inicio.date()),
                   "fim": str(ind.fim.date()), "media_mensal": r(ind.media_mensal, 2),
                   "movimentos": int(len(mov)),
                   "mov_tipos": {k: int(v) for k, v in mov["tipo"].value_counts().items()}}

    # ------------------------------------------------- 1. Curva ABC antes × depois
    abc_c = M.curva_abc(df, p)
    abc_v = MV.curva_abc_vendas(pos, p)
    cruz = MV.abc_cruzada(abc_c, abc_v)
    classes = []
    for nome, a in (("Compras (observado)", abc_c), ("Vendas (simulado)", abc_v)):
        for _, cl in a.classes.iterrows():
            classes.append({"curva": nome, "classe": cl["classe"], "itens": int(cl["itens"]),
                            "pct_itens": cl["pct_itens"], "valor": cl["valor"],
                            "pct_valor": cl["pct_valor"]})
    tabela(pd.DataFrame(classes), "abc_classes_antes_depois")
    comuns = cruz[(cruz["classe_compras"] != "—") & (cruz["classe_vendas"] != "sem venda")]
    rho = comuns["valor_compras"].rank().corr(comuns["faturamento"].rank())
    mesma = (comuns["classe_compras"] == comuns["classe_vendas"]).mean()
    matriz = pd.crosstab(cruz["classe_compras"], cruz["classe_vendas"]) \
        .reindex(index=["A", "B", "C"], columns=["A", "B", "C", "sem venda"], fill_value=0)
    tabela(matriz.reset_index().rename(columns={"classe_compras": "compras \\ vendas"}),
           "abc_matriz_compras_vendas")
    parado = cruz[(cruz["classe_compras"] == "A") & cruz["classe_vendas"].isin(["C", "sem venda"])]
    critico = cruz[(cruz["classe_vendas"] == "A") & cruz["classe_compras"].isin(["B", "C"])]
    NUM["abc"] = {
        "compras": {"itens": int(abc_c.n), "conc20": r(abc_c.concentracao_20),
                    **{f"{k}_itens": int(v) for k, v in abc_c.classes.set_index("classe")["itens"].items()},
                    **{f"{k}_pct_itens": r(v) for k, v in abc_c.classes.set_index("classe")["pct_itens"].items()},
                    **{f"{k}_pct_valor": r(v) for k, v in abc_c.classes.set_index("classe")["pct_valor"].items()},
                    "base": p.base_abc, "total": r(abc_c.total, 2)},
        "vendas": {"itens": int(abc_v.n), "conc20": r(abc_v.concentracao_20),
                   **{f"{k}_itens": int(v) for k, v in abc_v.classes.set_index("classe")["itens"].items()},
                   **{f"{k}_pct_itens": r(v) for k, v in abc_v.classes.set_index("classe")["pct_itens"].items()},
                   **{f"{k}_pct_valor": r(v) for k, v in abc_v.classes.set_index("classe")["pct_valor"].items()},
                   "total": r(abc_v.total, 2)},
        "spearman": r(rho), "mesma_classe": r(mesma), "comuns": int(len(comuns)),
        "matriz": {f"{i}->{j}": int(matriz.loc[i, j]) for i in matriz.index for j in matriz.columns},
        "parado_itens": int(len(parado)), "parado_valor": r(parado["valor_compras"].sum(), 2),
        "critico_itens": int(len(critico)), "critico_fat": r(critico["faturamento"].sum(), 2),
    }

    # figura 1: curvas de Pareto sobrepostas
    fig = go.Figure()
    for a, nome, cor, traco in ((abc_c, "Compras — observado", COR_OBS, "solid"),
                                (abc_v, "Vendas — simulado", COR_SIM, "dash")):
        x = a.itens["posicao"] / a.n
        fig.add_trace(go.Scatter(x=x, y=a.itens["acumulado_pct"], name=nome, mode="lines",
                                 line=dict(color=cor, width=2.6, dash=traco)))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], name="Distribuição uniforme", mode="lines",
                             line=dict(color=C["ink3"], width=1, dash="dot")))
    for corte in (p.corte_a, p.corte_b):
        fig.add_hline(y=corte, line=dict(color=C["ink3"], width=1, dash="dot"),
                      annotation_text=f"corte {corte:.0%}", annotation_position="bottom right")
    fig.add_vline(x=0.2, line=dict(color=C["ink3"], width=1, dash="dot"),
                  annotation_text="20% dos itens", annotation_position="top right")
    fig.update_layout(title="Figura 1 — Curva ABC (Pareto): compras observadas × vendas simuladas",
                      xaxis=dict(title="fração dos medicamentos (do maior para o menor)",
                                 tickformat=".0%"),
                      yaxis=dict(title="fração acumulada do valor", tickformat=".0%"))
    salvar(fig, "fig01_pareto_compras_vendas")

    # figura 2: matriz compras × vendas
    texto = [[f"{matriz.loc[i, j]}" for j in matriz.columns] for i in matriz.index]
    fig = go.Figure(go.Heatmap(z=matriz.values, x=[f"vendas {j}" for j in matriz.columns],
                               y=[f"compras {i}" for i in matriz.index], text=texto,
                               texttemplate="%{text}", textfont=dict(size=16),
                               colorscale=[[0, "#F5F8FA"], [1, C["purple"]]], showscale=False,
                               xgap=3, ygap=3))
    fig.update_layout(title="Figura 2 — Classe de cada medicamento nas compras × nas vendas",
                      yaxis=dict(autorange="reversed", showgrid=False),
                      xaxis=dict(showline=False))
    salvar(fig, "fig02_matriz_abc", altura=420, largura=820)

    # figura 3: tamanho das classes
    fig = go.Figure()
    for nome, a, cor in (("Compras — observado", abc_c, COR_OBS), ("Vendas — simulado", abc_v, COR_SIM)):
        cl = a.classes.set_index("classe")
        fig.add_trace(go.Bar(x=[f"Classe {k}" for k in "ABC"], y=cl.loc[list("ABC"), "pct_itens"],
                             name=nome, marker_color=cor, text=[f"{v:.1%}".replace(".", ",")
                                                                for v in cl.loc[list("ABC"), "pct_itens"]],
                             textposition="outside"))
    fig.update_layout(title="Figura 3 — Parcela do mix em cada classe",
                      yaxis=dict(tickformat=".0%", title="medicamentos da classe ÷ total",
                                 range=[0, 0.55]), barmode="group")
    salvar(fig, "fig03_classes_abc", altura=420, largura=820)

    # ------------------------------------------------- 2. Previsões antes × depois
    orc = PV.orcamento(df)
    cand = PV.candidatos(df, abc_c, p)
    conf = PV.resumo_confiabilidade(PV.confiabilidade(df, p))
    pv = MV.previsao_vendas(rec)
    td = MV.teste_demanda(rec, p)
    repor = pos[pos["repor_agora"]]
    lista_v = pos[pos["qtd_sugerida"] > 0]
    cand_am = cand[cand["chance"].isin(["alta", "média"])]
    sku_c, sku_v = set(cand_am["sku"]), set(lista_v["sku"])
    faixas = conf["faixas"]
    NUM["previsao"] = {
        "compras": {"alvo": str(orc["alvo"]), "media": r(orc["media"], 2),
                    "faixa_min": r(orc["faixa_min"], 2), "faixa_max": r(orc["faixa_max"], 2),
                    "acerto_faixa": r(orc["acerto_faixa"]), "erro_mediano": r(orc["erro_mediano"]),
                    "meses_teste": int(len(orc["teste"])),
                    "candidatos": int(len(cand)),
                    "por_chance": {k: int(v) for k, v in cand["chance"].value_counts().items()},
                    "lista_alta_media_itens": int(len(cand_am)),
                    "lista_alta_media_valor": r(cand_am["valor_estimado"].sum(), 2),
                    "confirmacao": {k: r(faixas.loc[k, "taxa"]) for k in faixas.index},
                    "cobertura_valor": r(conf["cobertura_valor"]),
                    "itens_novos": r(conf["itens_novos"]), "meses_conf": int(conf["meses"])},
        "vendas": {"alvo": str(pv["alvo"]), "metodo": pv["melhor"], "previsao": r(pv["previsao"], 2),
                   "erro_mediano": r(pv["metodos"].set_index("metodo").loc[pv["melhor"], "erro_mediano"]),
                   "metodos": {m: r(e) for m, e in zip(pv["metodos"]["metodo"], pv["metodos"]["erro_mediano"])},
                   "wape_sazonal": r(td["wape"].mean()), "wape_media": r(td["wape_media"].mean()),
                   "wape_ingenuo": r(td["wape_ingenuo"].mean()),
                   "vies_sazonal": r(td["previsto"].sum() / td["real"].sum() - 1),
                   "vies_media": r(td["previsto_media"].sum() / td["real"].sum() - 1),
                   "repor_agora_itens": int(len(repor)), "repor_agora_valor": r(repor["valor_sugerido"].sum(), 2),
                   "lista_total_itens": int(len(lista_v)), "lista_total_valor": r(lista_v["valor_sugerido"].sum(), 2),
                   "politicas": {k: int(v) for k, v in pos["politica"].value_counts().items()}},
        "sobreposicao": {"so_compras": len(sku_c - sku_v), "ambas": len(sku_c & sku_v),
                         "so_vendas": len(sku_v - sku_c)},
    }

    # figura 4: backtests lado a lado (gasto mensal × faturamento mensal)
    t = orc["teste"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t["mes"].astype(str).map(T.mes_label), y=t["real"], name="Gasto realizado (observado)",
                             mode="lines+markers", line=dict(color=COR_OBS)))
    fig.add_trace(go.Scatter(x=t["mes"].astype(str).map(T.mes_label), y=t["previsto"], name="Gasto previsto (média)",
                             mode="lines", line=dict(color=COR_OBS, dash="dot")))
    tv = pv["teste"][pv["teste"]["metodo"] == pv["melhor"]]
    fig.add_trace(go.Scatter(x=tv["mes"].map(T.mes_label), y=tv["real"], name="Faturamento (simulado)",
                             mode="lines+markers", line=dict(color=COR_SIM)))
    fig.add_trace(go.Scatter(x=tv["mes"].map(T.mes_label), y=tv["previsto"], name=f"Faturamento previsto ({pv['melhor'].lower()})",
                             mode="lines", line=dict(color=COR_SIM, dash="dot")))
    fig.update_layout(title="Figura 4 — Teste no histórico: previsão pelas compras × pelas vendas",
                      yaxis=dict(title="R$ por mês", tickprefix="R$ ", tickformat=",.0f"),
                      legend=dict(orientation="h", y=1.0, yanchor="bottom", x=1, xanchor="right"))
    salvar(fig, "fig04_backtests")

    # figura 5: erros comparados
    erros = pd.DataFrame([
        ("Gasto do mês (compras, média ± desvio)", orc["erro_mediano"], "observado"),
        (f"Faturamento do mês (vendas, {pv['melhor'].lower()})",
         NUM["previsao"]["vendas"]["erro_mediano"], "simulado"),
        ("Demanda de 30 dias por item — sazonal (WAPE)", td["wape"].mean(), "simulado"),
        ("Demanda de 30 dias por item — média simples", td["wape_media"].mean(), "simulado"),
        ("Demanda de 30 dias por item — último mês", td["wape_ingenuo"].mean(), "simulado"),
    ], columns=["previsao", "erro", "natureza"])
    tabela(erros, "previsao_erros")
    fig = go.Figure(go.Bar(y=erros["previsao"], x=erros["erro"], orientation="h",
                           marker_color=[COR_OBS if n == "observado" else COR_SIM for n in erros["natureza"]],
                           text=[f"{e:.0%}" for e in erros["erro"]], textposition="outside"))
    fig.update_layout(title="Figura 5 — Erro das previsões (menor é melhor)",
                      xaxis=dict(tickformat=".0%", range=[0, max(erros["erro"]) * 1.2]),
                      yaxis=dict(autorange="reversed"))
    salvar(fig, "fig05_erros_previsao", altura=400)

    # figura 6: o que cada lista recomenda comprar
    sob = NUM["previsao"]["sobreposicao"]
    fig = go.Figure(go.Bar(x=["Só na lista pelas compras", "Nas duas listas", "Só na lista pelas vendas"],
                           y=[sob["so_compras"], sob["ambas"], sob["so_vendas"]],
                           marker_color=[COR_OBS, C["teal"], COR_SIM],
                           text=[sob["so_compras"], sob["ambas"], sob["so_vendas"]], textposition="outside"))
    fig.update_layout(title="Figura 6 — Medicamentos recomendados para a próxima compra",
                      yaxis_title="medicamentos")
    salvar(fig, "fig06_listas_compra", altura=400, largura=820)

    # ------------------------------------------------- 3. Apoio à decisão antes × depois
    ins_antes = Dc.gerar(df, abc_c, p)
    ins_depois = Dc.gerar(df, abc_c, p, MV.para_decisao(rec, mov, p))
    d_a, d_d = (Dc.diagnostico(i, ind.valor_pedido) for i in (ins_antes, ins_depois))
    NUM["apoio"] = {
        "antes": {"pontos": len(ins_antes), **{k: int(v) for k, v in d_a["contagem"].items()},
                  "economia": r(d_a["economia"], 2), "acionaveis": len(d_a["acionaveis"])},
        "depois": {"pontos": len(ins_depois), **{k: int(v) for k, v in d_d["contagem"].items()},
                   "economia": r(d_d["economia"], 2), "acionaveis": len(d_d["acionaveis"]),
                   "novos": [(i.id, i.titulo, i.nivel, r(i.impacto, 2)) for i in ins_depois
                             if i.categoria == "movimentacao"]},
    }
    fig = go.Figure()
    for nivel, cor in (("crit", C["red"]), ("aten", C["amber"]), ("info", C["blue"]), ("ok", C["green"])):
        fig.add_trace(go.Bar(x=["Antes (só compras)", "Depois (com movimentação)"],
                             y=[d_a["contagem"][nivel], d_d["contagem"][nivel]],
                             name=Dc.PLURAL[nivel], marker_color=cor,
                             text=[d_a["contagem"][nivel], d_d["contagem"][nivel]],
                             textposition="inside"))
    fig.update_layout(title="Figura 7 — Pontos do apoio à decisão por gravidade",
                      barmode="stack", yaxis_title="pontos avaliados")
    salvar(fig, "fig07_apoio_gravidade", altura=420, largura=820)

    # ------------------------------------------------- 4. Regularidade (XYZ) antes × depois
    xyz_c = M.classificacao_xyz(df, abc_c, p)["xyz"].value_counts()
    xyz_v = MV.xyz_vendas(rec, p)["xyz"].value_counts()
    NUM["xyz"] = {"compras": {k: int(xyz_c.get(k, 0)) for k in "XYZ"},
                  "vendas": {k: int(xyz_v.get(k, 0)) for k in ["X", "Y", "Z", "—"]}}
    fig = go.Figure()
    for nome, cont, cor in (("Pelas compras trimestrais — observado", xyz_c, COR_OBS),
                            ("Pelas vendas mensais — simulado", xyz_v, COR_SIM)):
        tot = sum(int(cont.get(k, 0)) for k in "XYZ") or 1
        fig.add_trace(go.Bar(x=["X — regular", "Y — variável", "Z — irregular"],
                             y=[int(cont.get(k, 0)) / tot for k in "XYZ"], name=nome, marker_color=cor,
                             text=[int(cont.get(k, 0)) for k in "XYZ"], textposition="outside"))
    fig.update_layout(title="Figura 8 — Regularidade dos medicamentos (classificação XYZ)",
                      yaxis=dict(tickformat=".0%", title="parcela dos classificados", range=[0, 1.1]),
                      barmode="group")
    salvar(fig, "fig08_xyz", altura=420, largura=820)

    # ------------------------------------------------- 5. Resultados da movimentação
    pt = MV.ponte_estoque(rec)
    prop = MV.propostas_validade(rec, p)
    fx = MV.faixas_cobertura(pos, p)
    NUM["movimentacao"] = {"ponte": {k: r(v, 4) for k, v in pt.items() if isinstance(v, float)},
                           "un": {k: int(v) for k, v in pt.items() if isinstance(v, int)},
                           "faturamento": r(res["faturamento"], 2), "margem_pct": r(res["margem_pct"]),
                           "perda_valor": r(res["perda_valor"], 2), "perda_pct": r(res["perda_pct"]),
                           "estoque_valor": r(res["estoque_valor"], 2), "giro_mediano": r(res["giro_mediano"]),
                           "cobertura_mediana": r(res["cobertura_mediana"]), "situacao": res["situacao"],
                           "propostas": {k: int(v) for k, v in prop["acao"].value_counts().items()},
                           "propostas_valor": r(prop["valor_excedente"].sum(), 2),
                           "propostas_recupera": r(prop["perda_evitada"].sum(), 2),
                           "faixas_cobertura": {f: int(n) for f, n in zip(fx["faixa"], fx["produtos"])}}
    fig = go.Figure(go.Waterfall(
        x=["Estoque de partida (simulado)", "Compras (observado)", "Custo vendido (simulado)",
           "Perdas (simulado)", "Estoque de chegada (simulado)"],
        y=[pt["valor_inicial"], pt["valor_entradas"], -pt["cmv"], -pt["valor_perdas"], pt["valor_final"]],
        measure=["absolute", "relative", "relative", "relative", "total"],
        text=[f"R$ {abs(v):,.0f}".replace(",", ".") for v in
              (pt["valor_inicial"], pt["valor_entradas"], pt["cmv"], pt["valor_perdas"], pt["valor_final"])],
        textposition="outside", increasing=dict(marker=dict(color=COR_OBS)),
        decreasing=dict(marker=dict(color=COR_SIM)), totals=dict(marker=dict(color=C["teal"])),
        connector=dict(line=dict(color=C["line"]))))
    fig.update_layout(title="Figura 9 — Ponte do estoque (a custo), 30/09/2024 a 08/07/2026",
                      yaxis=dict(tickprefix="R$ ", tickformat=",.0f"), showlegend=False)
    salvar(fig, "fig09_ponte_estoque")
    serie = MV.serie_mensal(rec)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=serie["ano_mes"].map(T.mes_label), y=serie["compras"], name="Compras (observado)",
                         marker_color=COR_OBS))
    fig.add_trace(go.Scatter(x=serie["ano_mes"].map(T.mes_label), y=serie["cmv"], name="Custo vendido (simulado)",
                             mode="lines+markers", line=dict(color=COR_SIM)))
    fig.update_layout(title="Figura 10 — Compras × custo do que foi vendido, por mês",
                      yaxis=dict(tickprefix="R$ ", tickformat=",.0f"),
                      legend=dict(orientation="h", y=1.0, yanchor="bottom", x=1, xanchor="right"))
    salvar(fig, "fig10_compras_cmv")
    fig = go.Figure(go.Bar(x=fx["faixa"].replace({"Com estoque, sem venda recente": "Sem venda recente"}),
                           y=fx["produtos"], marker_color=[C["red"], C["amber"], C["amber"], C["green"],
                                                           C["blue_l"], C["blue"], C["ink3"]],
                           text=fx["produtos"], textposition="outside"))
    fig.update_layout(title="Figura 11 — Produtos por duração do estoque (cobertura) — simulado",
                      yaxis_title="produtos")
    salvar(fig, "fig11_cobertura", altura=420)

    # ------------------------------------------------- 6. Indicadores observados das compras
    forn = M.por_dimensao(df, "Nome do Fornecedor")
    NUM["compras_observadas"] = {
        "maior_fornecedor_pct": r(forn["valor_pedido"].iloc[0] / ind.valor_pedido),
        "margem_cotacao": r(M.margem_ponderada(df)),
        "validade_curta_pct": r(df["validade_curta"].mean()),
        "economia_o1": r(next((i.impacto for i in ins_antes if i.id == "o1"), 0), 2),
    }
    s = M.serie_mensal(df)
    media = s["valor_pedido"].mean()
    fig = go.Figure(go.Bar(x=s["ano_mes"].map(T.mes_label), y=s["valor_pedido"],
                           marker_color=[C["amber"] if v > media * p.pico_mensal else COR_OBS
                                         for v in s["valor_pedido"]]))
    fig.add_hline(y=media, line=dict(color=C["ink3"], dash="dot"),
                  annotation_text=f"média R$ {media:,.0f}".replace(",", "."),
                  annotation_position="top left")
    fig.update_layout(title="Figura 12 — Valor comprado por mês (observado; âmbar = pico)",
                      yaxis=dict(tickprefix="R$ ", tickformat=",.0f"), showlegend=False)
    salvar(fig, "fig12_compras_mes")

    (SAIDA / "numeros.json").write_text(json.dumps(NUM, ensure_ascii=False, indent=2, default=str),
                                        encoding="utf-8")
    print(f"relatório: {len(list(FIG.glob('*.png')))} figuras, {len(list(TAB.glob('*.csv')))} "
          f"tabelas e numeros.json em {SAIDA}")


if __name__ == "__main__":
    main()
