"""
Motor do Sistema de Apoio à Decisão.

Transforma o recorte filtrado em uma lista de insights. Cada um tem um resumo
curto para o cartão e um detalhamento que só aparece quando o painel é aberto.

Duas ideias sustentam o módulo:

1. Nenhum número fica escrito no texto. Tudo é calculado sobre o recorte ativo,
   e a gravidade sai do impacto medido, não de um rótulo fixo. Com outra base,
   um ponto hoje crítico pode nascer saudável — e a cor, a ordem e a frase
   acompanham sem edição.

2. Economia e exposição são coisas diferentes. Economia é dinheiro recuperável
   e pode ser somada. Exposição é valor sob risco e NÃO pode: o mesmo
   medicamento aparece em mais de um ponto, e somar contaria o mesmo dinheiro
   duas vezes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core import metricas as M
from core.movimentacao import JANELA_DEVOLUCAO as MV_JANELA
from core.parametros import Parametros
from core.formato import brl, brl0, data, mes_label, num, pct

CATEGORIAS = [
    ("abc", "Curva ABC", "📊"),
    ("alertas", "Oportunidades e Alertas", "⚠️"),
    ("fornecedores", "Fornecedores", "🚚"),
    ("medicamentos", "Medicamentos", "💊"),
    ("compras", "Compras", "🛒"),
    ("estoque", "Estoque", "📦"),
    ("movimentacao", "Movimentação", "🔄"),
]

NIVEIS = {"crit": "Crítico", "aten": "Atenção", "ok": "Saudável", "info": "Informativo"}
PLURAL = {"crit": "Críticos", "aten": "Em atenção", "ok": "Saudáveis",
          "info": "Informativos"}
PESO = {"crit": 0, "aten": 1, "info": 2, "ok": 3}


@dataclass
class Insight:
    id: str
    categoria: str
    nivel: str
    icone: str
    titulo: str
    valor: str
    frase: str
    periodo: str
    indicador: tuple[str, str]
    resumo: str
    impacto: float = 0.0
    tipo: str = "exposicao"            # "economia" = dinheiro recuperável
    valores: list[tuple[str, str]] = field(default_factory=list)
    medicamentos: list[tuple[str, str]] = field(default_factory=list)
    fornecedores: list[tuple[str, str]] = field(default_factory=list)
    explicacao: str = ""
    acao: str = ""
    grafico: object | None = None
    reguas: list[str] = field(default_factory=list)   # campos de Parametros usados
    # depende das saídas da movimentação (hoje simuladas; ver DOCUMENTACAO, seção 9).
    # Não aparece na tela: só impede que o ponto dispute o destaque de maior
    # exposição com os medidos sobre as compras
    simulado: bool = False
    natureza: str = "real"              # real · estimado (só "estimado" vira selo na tela)


def gerar(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros,
          mov: dict | None = None) -> list[Insight]:
    """Os 21 pontos da base de compras e, com `mov`, os 5 da movimentação.

    `mov` é o resultado de movimentacao.para_decisao(): posição, resumo e
    propostas de remarcação do recorte em uso.
    """
    if df.empty or abc.itens.empty:
        return []
    ins = _gerar_compras(df, abc, p)
    if mov:
        ins += pontos_movimentacao(mov, p, M.indicadores(df).valor_pedido or 1.0)
    for i in ins:
        i.reguas = REGUAS.get(i.id, [])
        i.natureza = NATUREZA.get(i.id, "real")
    return ins


# pontos que dependem de uma premissa (os demais são medição direta dos dados)
NATUREZA = {
    "o1": "estimado",   # supõe comprar todo o volume pelo menor custo registrado
    "m1": "estimado",   # sobrecusto = valor × variação entre a 1ª e a última compra
    "e1": "estimado",   # risco de validade do último lote, não posição física
    "v4": "estimado",   # perda evitada supõe o ritmo atual de venda até a validade
    "v5": "estimado",   # sugestão de compra: demanda prevista, prazo e nível de serviço
}


def _gerar_compras(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> list[Insight]:

    hoje, _ = M.data_referencia(df, p)
    ind = M.indicadores(df)
    total = ind.valor_pedido or 1.0
    periodo = f"{data(ind.inicio)} a {data(ind.fim)}"

    mensal = M.serie_mensal(df)
    media_mes = mensal["valor_pedido"].mean() if not mensal.empty else 0.0
    picos = mensal.nlargest(3, "valor_pedido")

    cot = (df.groupby("Cotação", as_index=False)["valor_pedido"].sum()
             .sort_values("valor_pedido", ascending=False))
    top_cot = cot.head(3)
    conc_cot = top_cot["valor_pedido"].sum() / total

    fornecedores = M.por_dimensao(df, "Nome do Fornecedor")
    lider = fornecedores.iloc[0]
    part_lider = lider["valor_pedido"] / total

    itens = abc.itens
    classes = abc.classes.set_index("classe")
    unicos = itens[itens["compras"] == 1]
    a_unica = itens[(itens["classe"] == "A") & (itens["compras"] == 1)]
    a_recorrente = itens[(itens["classe"] == "A") &
                         (itens["compras"] >= p.recorrencia_minima)]
    a_um_forn = itens[(itens["classe"] == "A") & (itens["fornecedores"] == 1) &
                      (itens["compras"] >= 2)]
    forn_de = df.groupby("sku")["Nome do Fornecedor"].first()
    migrou = M.migracao_classe(df, p)

    oport = M.oportunidades_fornecedor(df, p)
    confiaveis = oport[~oport["suspeito"]]
    suspeitos = oport[oport["suspeito"]]
    economia_troca = float(confiaveis["economia"].sum())

    variacao = M.variacao_custo(df, p)
    altas = variacao[(variacao["variacao"] > p.alta_custo_relevante) &
                     (~variacao["suspeito"])]
    # itens que já estão na economia por troca de fornecedor não entram de novo
    # aqui: o mesmo dinheiro seria contado duas vezes na economia somada
    altas_sem_troca = altas[~altas["sku"].isin(confiaveis["sku"])]
    sobrecusto = float((altas_sem_troca["valor"] * altas_sem_troca["variacao"]).sum())
    # a gravidade mede o fenômeno inteiro; só a soma da economia exclui a sobreposição
    sobrecusto_total = float((altas["valor"] * altas["variacao"]).sum())

    margens = M.margem_classe_a(df, abc)
    marg_baixa = margens[margens["margem"] < p.margem_baixa]
    margem_media = M.margem_ponderada(df)

    lotes = M.posicao_lotes(df, abc, hoje)
    risco = lotes[lotes["meses_restantes"] < p.validade_risco_meses] \
        .sort_values("valor_lote", ascending=False)
    vencidos = lotes[lotes["meses_restantes"] < 0]

    curtas = M.qualidade_entrega(df, p)
    atend = M.atendimento_fornecedor(df)
    fracos = atend[(atend["pedidos"] >= p.pedidos_minimos) &
                   (atend["atendimento"] < p.atendimento_minimo)]

    ins: list[Insight] = []

    def novo(**kw):
        ins.append(Insight(periodo=periodo, **kw))

    def lista_med(d, coluna_txt):
        return [(str(r["medicamento"]), coluna_txt(r)) for _, r in d.head(8).iterrows()]

    # ------------------------------------------------------------- CURVA ABC
    novo(id="a1", categoria="abc", nivel="info", icone="📊", impacto=0.0,
         titulo="Concentração da classe A",
         valor=pct(classes.loc["A", "pct_valor"], 0),
         frase=f"do valor está em {num(int(classes.loc['A','itens']))} medicamentos "
               f"({pct(classes.loc['A','pct_itens'],1)} do mix)",
         indicador=(f"{num(int(classes.loc['A','itens']))} itens",
                    f"concentram {pct(classes.loc['A','pct_valor'],1)} do valor comprado"),
         resumo="Itens que justificam controle individual e negociação item a item.",
         valores=[(f"Classe {c}",
                   f"{num(int(classes.loc[c,'itens']))} itens · {pct(classes.loc[c,'pct_valor'],1)}")
                  for c in "ABC"] + [("Valor classificado", brl(abc.total))],
         medicamentos=[(r["medicamento"], f"{brl(r['valor'])} · {pct(r['participacao'],2)}")
                       for _, r in itens.head(8).iterrows()],
         explicacao="A classificação usa o valor de consumo (quantidade × custo unitário) "
                    "somado por SKU, ordenado do maior para o menor, com corte no percentual "
                    "acumulado. A classe sai do acumulado anterior ao item, então quem cruza "
                    "o corte fecha a classe a que pertence.",
         acao="Revisar preço e fornecedor dos itens de classe A a cada cotação.")

    # diagnóstico estrutural: descreve a forma da curva, não um valor sob risco,
    # por isso não carrega impacto em reais
    novo(id="a2", categoria="abc",
         nivel="aten" if abc.concentracao_20 < 0.75 else "ok",
         icone="🧩", impacto=0.0,
         titulo="Curva achatada" if abc.concentracao_20 < 0.75 else "Curva concentrada",
         valor=pct(abc.concentracao_20),
         frase="do valor está nos 20% maiores itens — o padrão de Pareto seria 80%",
         indicador=(pct(abc.concentracao_20),
                    "é o valor concentrado nos 20% maiores medicamentos"),
         resumo="O padrão clássico de Pareto não se confirma nesta base."
                if abc.concentracao_20 < 0.75
                else "A concentração está próxima do padrão de Pareto.",
         valores=[(f"Itens até {pct(p.corte_a,0)} do valor",
                   pct(classes.loc["A", "pct_itens"], 1) + " do mix"),
                  ("Nos 20% maiores", pct(abc.concentracao_20)),
                  ("Itens comprados 1x", num(len(unicos))),
                  ("Valor desses itens", pct(unicos["valor"].sum() / abc.total, 1))],
         explicacao=f"São necessários {pct(classes.loc['A','pct_itens'],1)} dos itens para "
                    f"chegar a {pct(p.corte_a,0)} do valor, contra os 20% do padrão de Pareto. "
                    "Uma classe A grande é característica da base, não erro de "
                    "classificação: quanto mais medicamentos comprados uma única vez, mais "
                    "longa a cauda e mais achatada a curva.",
         acao="Padronizar o mix reduz a cauda e devolve à curva o poder de priorização.")

    novo(id="a3", categoria="abc", nivel="ok", icone="📉", impacto=0.0,
         titulo="Cauda de baixo valor", valor=pct(classes.loc["C", "pct_itens"], 1),
         frase=f"dos itens representam só {pct(classes.loc['C','pct_valor'],1)} do valor",
         indicador=(f"{num(int(classes.loc['C','itens']))} itens",
                    f"somam apenas {pct(classes.loc['C','pct_valor'],1)} do valor comprado"),
         resumo="Classe C admite controle simplificado e compra agrupada.",
         valores=[("Itens classe C", num(int(classes.loc["C", "itens"]))),
                  ("Valor", brl(classes.loc["C", "valor"])),
                  ("Valor médio por item", brl(classes.loc["C", "valor_medio"]))],
         explicacao="Controlar item a item a classe C custa mais em tempo de gestão do que "
                    "o valor que ela representa no orçamento.",
         acao="Agrupar em pedidos maiores para reduzir frete e esforço de cotação.")

    novo(id="a4", categoria="abc", nivel="info", icone="🎯", impacto=0.0,
         titulo="Prioridade máxima da gestão", valor=f"{num(len(a_recorrente))} itens",
         frase=f"classe A com {p.recorrencia_minima} ou mais compras no período",
         indicador=(f"{num(len(a_recorrente))} itens",
                    "concentram valor e frequência ao mesmo tempo"),
         resumo="Cruzamento entre peso financeiro e recorrência — onde o controle rende mais.",
         valores=[("Valor desses itens", brl(a_recorrente["valor"].sum())),
                  ("Participação no total", pct(a_recorrente["valor"].sum() / abc.total, 1)),
                  ("Total da classe A", f"{num(int(classes.loc['A','itens']))} itens"),
                  ("Compras somadas", num(int(a_recorrente["compras"].sum())))],
         medicamentos=lista_med(a_recorrente,
                                lambda r: f"{brl0(r['valor'])} · {int(r['compras'])} compras"),
         explicacao="Um item pode ser caro e comprado uma vez, ou barato e comprado sempre. "
                    "Os que são as duas coisas concentram valor e esforço operacional. Sem "
                    "registro de saída de estoque, a frequência de compra é a melhor "
                    "aproximação disponível do giro real.",
         acao="Fechar acordo de volume trimestral e definir ponto de reposição fixo.")

    novo(id="a5", categoria="abc",
         nivel=p.nivel_por_impacto(a_unica["valor"].sum(), abc.total, len(a_unica) > 0),
         icone="🧩", impacto=float(a_unica["valor"].sum()),
         titulo="Classe A sem recorrência", valor=f"{num(len(a_unica))} itens",
         frase=f"de alto valor comprados uma única vez, somando {brl0(a_unica['valor'].sum())}",
         indicador=(pct(a_unica["valor"].sum() / abc.total, 1),
                    "do valor está em classe A comprada uma só vez"),
         resumo="Medicamentos caros que entraram na cotação sem fazer parte de um plano.",
         valores=[("Itens", num(len(a_unica))), ("Valor", brl(a_unica["valor"].sum())),
                  ("Participação na classe A",
                   pct(len(a_unica) / max(1, int(classes.loc["A", "itens"])), 1)),
                  ("Classe A recorrente", f"{num(len(a_recorrente))} itens")],
         medicamentos=lista_med(a_unica, lambda r: f"{brl(r['valor'])} · 1 compra"),
         explicacao="É o ponto mais delicado da curva nesta base. Um item de classe A "
                    "deveria justificar controle individual, mas comprado uma única vez ele "
                    "pode ser tanto uma compra pontual legítima quanto uma falha de "
                    "planejamento cara. Sem registro de saída de estoque, a base não "
                    "distingue os dois casos.",
         acao="Revisar esta lista com o balconista: encomenda pontual sai do radar, "
              "falta recorrente entra na lista fixa.")

    novo(id="a6", categoria="abc",
         nivel=p.nivel_por_impacto(migrou["valor"].sum() if len(migrou) else 0,
                                   abc.total, len(migrou) > 0),
         icone="📈", impacto=float(migrou["valor"].sum()) if len(migrou) else 0.0,
         titulo="Itens que subiram de classe", valor=f"{num(len(migrou))} itens",
         frase="ganharam peso da primeira para a segunda metade do período"
               if len(migrou) else "sem migração relevante no recorte",
         indicador=(f"{num(len(migrou))} itens",
                    "mudaram para uma classe superior ao longo do período"),
         resumo="Compara a Curva ABC da primeira metade do período com a da segunda.",
         valores=[("Itens que subiram", num(len(migrou))),
                  ("Valor na 2ª metade", brl(migrou["valor"].sum()) if len(migrou) else "—"),
                  ("Passaram a classe A",
                   num(int((migrou["classe"] == "A").sum())) if len(migrou) else "0")],
         medicamentos=[(r["medicamento"], f"de {r['de']} para {r['classe']} · {brl0(r['valor'])}")
                       for _, r in migrou.head(8).iterrows()],
         explicacao="A Curva ABC é uma fotografia do período inteiro e esconde movimento. "
                    "Dividindo o recorte ao meio e classificando as duas metades, aparecem os "
                    "medicamentos que estão ganhando importância — e que provavelmente ainda "
                    "são tratados com o cuidado da classe antiga.",
         acao="Trazer esses itens para o controle de classe A antes da próxima cotação.")

    # -------------------------------------------------- OPORTUNIDADES E ALERTAS
    novo(id="o1", categoria="alertas", tipo="economia",
         nivel=p.nivel_por_impacto(economia_troca, total, len(confiaveis) > 0, "economia"),
         icone="💸", impacto=economia_troca,
         titulo="Economia na troca de fornecedor", valor=brl0(economia_troca),
         frase=f"{pct(economia_troca/total)} do valor comprado, em {num(len(confiaveis))} itens",
         indicador=(brl(economia_troca), "de economia possível no período"),
         resumo="Comparação entre o que foi pago e o menor custo que o próprio histórico "
                "já registrou.",
         valores=[("Itens com mais de um fornecedor", num(len(oport))),
                  ("Economia estimada", brl(economia_troca)),
                  ("Sobre o total comprado", pct(economia_troca / total)),
                  ("Excluídos por erro de cadastro", num(len(suspeitos)))],
         medicamentos=[(r["medicamento"],
                        f"{brl(r['economia'])} · melhor preço com {r['melhor_fornecedor']}")
                       for _, r in confiaveis.head(8).iterrows()],
         explicacao="A estimativa usa o custo unitário médio ponderado de cada fornecedor "
                    "para o mesmo SKU. Não considera frete, prazo de pagamento nem "
                    "faturamento mínimo — serve como ponto de partida da negociação. Itens "
                    f"com diferença acima de {pct(p.razao_preco_suspeita-1,0)} ficaram fora "
                    "por indício de erro de cadastro.",
         acao="Levar esses itens à próxima cotação com o preço de referência em mãos.")

    novo(id="o2", categoria="alertas",
         nivel="crit" if len(suspeitos) else "ok", icone="🗄️", impacto=0.0,
         titulo="Indício de erro de cadastro", valor=f"{num(len(suspeitos))} itens",
         frase=f"com custo que varia mais de {pct(p.razao_preco_suspeita-1,0)} entre fornecedores",
         indicador=(f"{num(len(suspeitos))} itens",
                    "com diferença de preço grande demais para ser negociação"),
         resumo="Provável erro de digitação ou de unidade na cotação de origem.",
         valores=[("Itens suspeitos", num(len(suspeitos)))],
         medicamentos=[(r["medicamento"], f"de {brl(r['melhor_custo'])} a {brl(r['pior_custo'])}")
                       for _, r in suspeitos.head(8).iterrows()],
         explicacao="Um mesmo medicamento registrado com preços muito distantes não "
                    "representa oportunidade de compra: representa dado errado, que "
                    "contamina qualquer análise de preço feita sobre a base.",
         acao="Conferir o cadastro antes de usar esses preços como referência.")

    # ------------------------------------------------------------ FORNECEDORES
    # crítico acima do limite; atenção a partir de 3/4 dele; abaixo disso, saudável
    nivel_lider = ("crit" if part_lider > p.concentracao_fornecedor
                   else "aten" if part_lider >= p.concentracao_fornecedor * 0.75 else "ok")
    novo(id="f1", categoria="fornecedores", nivel=nivel_lider,
         icone="🚚", impacto=max(0.0, lider["valor_pedido"] - total * p.concentracao_fornecedor),
         titulo="Dependência de um fornecedor", valor=pct(part_lider),
         frase=f"do valor comprado está com {str(lider['Nome do Fornecedor']).split(' - ')[0]}",
         indicador=(pct(part_lider), "do valor comprado em um único distribuidor"),
         resumo=f"Concentração acima de {pct(p.concentracao_fornecedor,0)} deixa preço e "
                "prazo sem contrapeso na negociação.",
         valores=[("Valor com o líder", brl(lider["valor_pedido"])),
                  ("Pedidos com o líder", num(int(lider["pedidos"]))),
                  ("Fornecedores ativos", num(len(fornecedores)))],
         fornecedores=[(r["Nome do Fornecedor"],
                        f"{brl0(r['valor_pedido'])} · {pct(r['valor_pedido']/total)}")
                       for _, r in fornecedores.head(8).iterrows()],
         explicacao="Com boa parte do volume em um só distribuidor, a farmácia perde "
                    "referência de preço e fica exposta a uma eventual falha de entrega. "
                    f"O ponto fica crítico acima de {pct(p.concentracao_fornecedor,0)}, em "
                    f"atenção a partir de {pct(p.concentracao_fornecedor*0.75,0)} e saudável "
                    "abaixo disso; o valor exposto é apenas o que passa do limite.",
         acao="Distribuir os itens de classe A entre pelo menos dois distribuidores.")

    novo(id="f2", categoria="fornecedores",
         nivel=p.nivel_por_impacto(fracos["perda"].sum() if len(fracos) else 0,
                                   total, len(fracos) > 0),
         icone="🛡️", impacto=float(fracos["perda"].sum()) if len(fracos) else 0.0,
         titulo="Confiabilidade de entrega",
         valor=pct(fracos.iloc[0]["atendimento"], 0) if len(fracos)
               else pct(ind.nivel_atendimento, 0),
         frase=f"pior nível: {str(fracos.iloc[0]['fornecedor']).split(' - ')[0]}"
               if len(fracos) else
               f"nenhum fornecedor abaixo de {pct(p.atendimento_minimo,0)} de atendimento",
         indicador=(pct(fracos.iloc[0]["atendimento"]) if len(fracos)
                    else pct(ind.nivel_atendimento),
                    "atendido pelo fornecedor mais fraco" if len(fracos)
                    else "de nível de atendimento geral"),
         resumo="Distribuidores que cortam quantidade ao faturar geram ruptura na loja.",
         valores=[("Nível geral", pct(ind.nivel_atendimento)),
                  (f"Abaixo de {pct(p.atendimento_minimo,0)}", num(len(fracos))),
                  ("Valor não faturado",
                   brl(fracos["perda"].sum()) if len(fracos) else brl(0))],
         fornecedores=[(r["fornecedor"], f"{pct(r['atendimento'])} · {brl0(r['perda'])} não faturados")
                       for _, r in fracos.head(8).iterrows()],
         explicacao="O menor preço perde valor quando o fornecedor entrega parcialmente: o "
                    "item falta na gôndola e a compra precisa ser refeita com urgência. "
                    "Quando a base contém apenas pedidos faturados, este indicador tende a "
                    "100% por construção — a informação de corte está nos outros status.",
         acao="Considerar o corte histórico ao decidir o vencedor da cotação.")

    novo(id="f3", categoria="fornecedores",
         nivel=p.nivel_por_impacto(a_um_forn["valor"].sum(), total, len(a_um_forn) > 0),
         icone="🔗", impacto=float(a_um_forn["valor"].sum()),
         titulo="Classe A com fornecedor único", valor=f"{num(len(a_um_forn))} itens",
         frase=f"somam {brl0(a_um_forn['valor'].sum())} sem alternativa cotada",
         indicador=(f"{num(len(a_um_forn))} itens",
                    "de maior peso dependem de um só distribuidor"),
         resumo="Risco de ruptura nos medicamentos que mais pesam no orçamento.",
         valores=[("Valor envolvido", brl(a_um_forn["valor"].sum())),
                  ("Total classe A", num(int(classes.loc["A", "itens"])))],
         medicamentos=[(r["medicamento"], f"{brl0(r['valor'])} · {forn_de.get(r['sku'],'—')}")
                       for _, r in a_um_forn.head(8).iterrows()],
         explicacao="Se o único fornecedor desses itens falhar ou aumentar o preço, não "
                    "existe base de comparação nem canal alternativo já testado.",
         acao="Cotar esses itens com um segundo fornecedor mesmo sem trocar de imediato.")

    # ------------------------------------------------------------ MEDICAMENTOS
    novo(id="m1", categoria="medicamentos", tipo="economia",
         nivel=p.nivel_por_impacto(sobrecusto_total, total, len(altas) > 0, "economia"),
         icone="📈", impacto=sobrecusto,
         titulo="Custos em alta", valor=f"{num(len(altas))} itens",
         frase=f"subiram mais de {pct(p.alta_custo_relevante,0)} entre a primeira e a "
               "última compra",
         indicador=("+" + pct(altas.iloc[0]["variacao"], 0) if len(altas) else "—",
                    "no item de maior alta"),
         resumo="Comparação do custo unitário da primeira e da última compra de cada item.",
         valores=[("Itens com alta", num(len(altas))),
                  ("Valor envolvido", brl(altas["valor"].sum())),
                  ("Sobrecusto total", brl(sobrecusto_total)),
                  ("Fora da troca de fornecedor", brl(sobrecusto)),
                  ("Itens já contados na troca", num(len(altas) - len(altas_sem_troca)))],
         medicamentos=[(r["medicamento"],
                        f"{brl(r['custo_inicial'])} → {brl(r['custo_atual'])} (+{pct(r['variacao'],0)})")
                       for _, r in altas.head(8).iterrows()],
         explicacao="Quando o custo sobe e o preço de venda não acompanha, a margem cai sem "
                    "que ninguém perceba — o item continua vendendo bem e parece saudável. "
                    "O sobrecusto é o valor comprado vezes a alta de custo, e a gravidade "
                    "considera o total. Na economia somada do painel entram só os itens que "
                    "não aparecem em 'Economia na troca de fornecedor', para que o mesmo "
                    "dinheiro não seja contado duas vezes.",
         acao="Revisar o preço de venda desses itens e cotar um fornecedor alternativo.")

    novo(id="m2", categoria="medicamentos",
         nivel=p.nivel_por_impacto(marg_baixa["valor"].sum(), total, len(marg_baixa) > 0),
         icone="⚖️", impacto=float(marg_baixa["valor"].sum()),
         titulo="Margem apertada em itens de peso",
         valor=pct(margens.iloc[0]["margem"]) if len(margens) else "—",
         frase="é a menor margem entre os medicamentos de classe A",
         indicador=(pct(margens.iloc[0]["margem"]) if len(margens) else "—",
                    "no item de classe A com pior margem"),
         resumo="Itens de alto valor com margem baixa consomem caixa e devolvem pouco.",
         valores=[("Margem média ponderada", pct(margem_media)),
                  (f"Itens A abaixo de {pct(p.margem_baixa,0)}", num(len(marg_baixa))),
                  ("Valor desses itens", brl0(marg_baixa["valor"].sum()))],
         medicamentos=[(r["medicamento"], f"margem {pct(r['margem'],0)} · {brl0(r['valor'])}")
                       for _, r in margens.head(8).iterrows()],
         explicacao="A margem usa o preço de venda registrado na própria cotação, então "
                    "reflete a intenção de precificação no momento da compra. É ponderada "
                    "pela quantidade pedida, e itens sem preço de venda ficam de fora. Em "
                    "classe A, cada ponto percentual representa um valor absoluto relevante.",
         acao="Renegociar o custo antes de mexer no preço de venda.")

    # ---------------------------------------------------------------- COMPRAS
    novo(id="c1", categoria="compras",
         nivel=p.nivel_por_impacto(picos.iloc[0]["valor_pedido"] - media_mes, total,
                                   picos.iloc[0]["valor_pedido"] > media_mes * p.pico_mensal),
         icone="📅", impacto=float(picos.iloc[0]["valor_pedido"] - media_mes),
         titulo="Meses de maior desembolso",
         valor=" · ".join(mes_label(m) for m in picos["ano_mes"]),
         frase=f"pico de {brl0(picos.iloc[0]['valor_pedido'])}, "
               f"{pct(picos.iloc[0]['valor_pedido']/max(1e-9,media_mes)-1,0)} acima da média",
         indicador=(brl(picos.iloc[0]["valor_pedido"]),
                    f"no mês mais pesado ({mes_label(picos.iloc[0]['ano_mes'])})"),
         resumo="Concentração de desembolso em poucos meses pressiona o caixa da farmácia.",
         valores=[("Média mensal", brl(media_mes)),
                  ("Maior mês", brl(picos.iloc[0]["valor_pedido"])),
                  ("Menor mês", brl(mensal["valor_pedido"].min())),
                  ("Meses no recorte", num(ind.meses))],
         explicacao="Cotações grandes agrupadas no mesmo mês criam picos de pagamento que "
                    "não acompanham a entrada de caixa da farmácia, que é diária e "
                    "relativamente estável.",
         acao="Dividir a cotação dos meses de pico em duas rodadas ou negociar prazo maior.")

    # como na dependência de fornecedor, o valor exposto é só o que passa do limite
    novo(id="c2", categoria="compras",
         nivel="aten" if conc_cot > p.concentracao_cotacao else "ok",
         icone="🗓️",
         impacto=max(0.0, float(top_cot["valor_pedido"].sum()) - total * p.concentracao_cotacao),
         titulo="Peso das maiores cotações", valor=pct(conc_cot),
         frase=f"do valor saiu das 3 maiores cotações, de {num(ind.cotacoes)} no total "
               f"(limite: {pct(p.concentracao_cotacao,0)})",
         indicador=(pct(conc_cot), "do valor comprado está em apenas três cotações"),
         resumo="Mede se a compra está fracionada ao longo do tempo ou concentrada em "
                "poucas rodadas grandes.",
         valores=[("Cotações no recorte", num(ind.cotacoes)),
                  ("Valor das 3 maiores", brl(top_cot["valor_pedido"].sum())),
                  ("Cotação média", brl(total / max(1, ind.cotacoes))),
                  ("Maior cotação", brl(top_cot.iloc[0]["valor_pedido"]))],
         explicacao="Cotação concentrada significa comprar muito de uma vez: melhora o poder "
                    "de negociação por volume, mas prende capital e aumenta o risco de "
                    "validade, porque o lote inteiro chega junto e precisa girar junto.",
         acao="Para itens de classe A, avaliar se vale fracionar a cotação grande em duas "
              "entregas com o mesmo preço negociado.")

    # ---------------------------------------------------------------- ESTOQUE
    novo(id="e1", categoria="estoque",
         nivel=p.nivel_por_impacto(risco["valor_lote"].sum(), total, len(risco) > 0),
         icone="⏳", impacto=float(risco["valor_lote"].sum()),
         titulo="Validade dos lotes recebidos", valor=f"{num(len(risco))} itens",
         frase=f"vencidos ou vencendo em menos de {p.validade_risco_meses} meses, "
               f"somando {brl0(risco['valor_lote'].sum())}",
         indicador=(brl(risco["valor_lote"].sum()),
                    f"em lotes vencidos ou a vencer até {data(hoje + pd.DateOffset(months=p.validade_risco_meses))}"),
         resumo=f"Último lote recebido de cada medicamento, comparado a {data(hoje)}. "
                "É indicativo de risco, não posição de estoque.",
         valores=[("Já vencidos", num(len(vencidos))),
                  (f"Até {p.validade_risco_meses} meses", num(len(risco) - len(vencidos))),
                  ("Valor em risco", brl(risco["valor_lote"].sum())),
                  ("Sendo classe A", num(int((risco["classe"] == "A").sum())))],
         medicamentos=[(r["medicamento"],
                        f"{brl(r['valor_lote'])} · " +
                        ("vencido" if r["meses_restantes"] < 0
                         else f"{r['meses_restantes']:.1f} meses".replace(".", ",")))
                       for _, r in risco.head(8).iterrows()],
         explicacao="Este indicador tem um limite que precisa ser dito: a base registra "
                    "compras, não saídas. Não é possível saber se o lote ainda está na "
                    "prateleira ou já foi vendido. O número mostra quanta mercadoria entrou "
                    "com prazo curto — um risco real — mas não é um inventário. É por isso "
                    "que a priorização do sistema se apoia na Curva ABC.",
         acao="Conferir fisicamente os itens de classe A desta lista.")

    pior_curta = curtas.iloc[0] if not curtas.empty else None
    novo(id="e2", categoria="estoque",
         nivel=p.nivel_por_impacto(pior_curta["valor"] if pior_curta is not None else 0,
                                   total, pior_curta is not None),
         icone="⚠️", impacto=float(pior_curta["valor"]) if pior_curta is not None else 0.0,
         titulo="Validade curta na entrega",
         valor=pct(pior_curta["pct"], 0) if pior_curta is not None else "—",
         frase=(f"das entregas de {str(pior_curta['fornecedor']).split(' - ')[0]} chegam "
                "com menos de metade do prazo") if pior_curta is not None
               else "sem desvio relevante",
         indicador=(pct(pior_curta["pct"], 0) if pior_curta is not None else "—",
                    "das entregas do fornecedor mais crítico"),
         resumo="Percentual de linhas recebidas com menos de 50% da vida útil do produto.",
         valores=[("Linhas em faixa curta", num(int(df["validade_curta"].sum()))),
                  ("Valor envolvido",
                   brl(df.loc[df["validade_curta"], "valor_faturado"].sum())),
                  ("Fornecedores avaliados", num(len(curtas)))],
         fornecedores=[(r["fornecedor"],
                        f"{pct(r['pct'],0)} ({int(r['curtas'])} de {int(r['linhas'])})")
                       for _, r in curtas.head(8).iterrows()],
         explicacao="Alguns distribuidores usam a cotação para escoar lote perto do "
                    "vencimento. O preço parece bom, mas o risco de perda é transferido "
                    "para a farmácia. Só entram distribuidores com "
                    f"{p.linhas_minimas} ou mais linhas, para que um caso isolado não vire "
                    "percentual alto sem significado.",
         acao="Exigir validade mínima em contrato para os itens de classe A.")

    # -------------------------------------------- REGULARIDADE (ABC × XYZ)
    xyz = M.classificacao_xyz(df, abc, p)
    a_xyz = xyz[xyz["classe"] == "A"]
    az = a_xyz[a_xyz["xyz"] == "Z"]
    a_regular = a_xyz[a_xyz["xyz"].isin(["X", "Y"])]
    pct_az = az["valor"].sum() / max(1e-9, a_xyz["valor"].sum()) if len(a_xyz) else 0.0
    novo(id="a7", categoria="abc",
         nivel="aten" if pct_az > 0.5 else ("info" if len(az) else "ok"),
         icone="🔀", impacto=0.0,
         titulo="Classe A sem ritmo de compra", valor=pct(pct_az, 0),
         frase=f"do valor da classe A está em itens de compra irregular (Z), "
               f"{num(len(az))} de {num(len(a_xyz))}",
         indicador=(f"{num(len(az))} itens", "de classe A comprados sem regularidade"),
         resumo="Cruza o peso financeiro (ABC) com a regularidade da compra trimestre a "
                "trimestre (XYZ).",
         valores=[("A regulares (AX + AY)", num(len(a_regular))),
                  ("A irregulares (AZ)", num(len(az))),
                  ("Valor AZ", brl0(az["valor"].sum())),
                  ("Régua X / Y", f"CV ≤ {p.cv_x:.2f} / ≤ {p.cv_y:.2f}".replace(".", ","))],
         medicamentos=[(r["medicamento"],
                        f"{brl0(r['valor'])} · {int(r['trimestres_com_compra'])} trimestre(s) "
                        "com compra") for _, r in az.head(8).iterrows()],
         explicacao="O coeficiente de variação (desvio-padrão ÷ média) da quantidade "
                    "comprada por trimestre mede a regularidade: X é previsível, Y varia e "
                    "Z é esporádico. Item caro e esporádico (AZ) não aceita reposição "
                    "automática nem estoque de segurança fixo — cada compra precisa de "
                    "decisão. Já AX e AY são os candidatos ideais a ponto de pedido.",
         acao="Ponto de pedido fixo para AX/AY; compra sob encomenda e revisão a cada "
              "cotação para AZ.")

    # ------------------------------------- FATURAMENTO MÍNIMO E PRAZO DE PAGAMENTO
    ped = M.pedidos_condicoes(df, p)
    abaixo = ped[ped["situacao"] == "abaixo do mínimo"]
    limite = ped[ped["situacao"] == "no limite"]
    valor_risco_min = float(abaixo["valor"].sum() + limite["valor"].sum())
    nivel_min = p.nivel_por_impacto(valor_risco_min, total, len(abaixo) + len(limite) > 0)
    if len(abaixo) and nivel_min == "ok":
        nivel_min = "aten"          # pedido abaixo do mínimo nunca é saudável
    novo(id="f4", categoria="fornecedores", nivel=nivel_min,
         icone="🧾", impacto=valor_risco_min,
         titulo="Faturamento mínimo", valor=f"{num(len(abaixo) + len(limite))} pedidos",
         frase=f"{num(len(abaixo))} abaixo do mínimo e {num(len(limite))} a menos de "
               f"{pct(p.pedido_minimo_folga,0)} acima dele",
         indicador=(f"{num(len(abaixo) + len(limite))} de {num(len(ped))}",
                    "pedidos abaixo ou no limite do faturamento mínimo"),
         resumo="Compara o valor de cada pedido com o faturamento mínimo exigido pelo "
                "fornecedor na cotação.",
         valores=[("Pedidos avaliados", num(len(ped))),
                  ("Abaixo do mínimo", num(len(abaixo))),
                  ("No limite", num(len(limite))),
                  ("Valor desses pedidos", brl0(valor_risco_min))],
         fornecedores=[(r["fornecedor"],
                        f"pedido {r['Pedido']}: {brl0(r['valor'])} para mínimo de "
                        f"{brl0(r['minimo'])}")
                       for _, r in pd.concat([abaixo, limite]).head(8).iterrows()],
         explicacao="Pedido abaixo do faturamento mínimo pode ser recusado ou gerar frete. "
                    "Pedido que passa por pouco também é frágil: um corte na nota o derruba "
                    "para baixo do mínimo. Juntar itens do mesmo fornecedor evita os dois "
                    "casos.",
         acao="Concentrar os itens de baixo valor desses fornecedores em menos pedidos, "
              "acima do mínimo com folga.")

    com_prazo = ped[ped["prazo_dias"].notna()]
    curto = com_prazo[com_prazo["prazo_dias"] < p.prazo_pagamento_minimo]
    prazo_medio = ((com_prazo["prazo_dias"] * com_prazo["valor"]).sum()
                   / max(1e-9, com_prazo["valor"].sum())) if len(com_prazo) else float("nan")
    prazo_forn = (curto.groupby("fornecedor")
                       .agg(valor=("valor", "sum"), prazo=("prazo_dias", "median"),
                            pedidos=("Pedido", "size"))
                       .sort_values("valor", ascending=False))
    novo(id="f5", categoria="compras",
         nivel=p.nivel_por_impacto(curto["valor"].sum(), total, len(curto) > 0),
         icone="💳", impacto=float(curto["valor"].sum()),
         titulo="Prazo de pagamento curto",
         valor=(f"{prazo_medio:.0f} dias" if pd.notna(prazo_medio) else "—"),
         frase=f"de prazo médio ponderado; {pct(curto['valor'].sum()/total,0)} do valor "
               f"paga em menos de {p.prazo_pagamento_minimo} dias",
         indicador=(brl(curto["valor"].sum()),
                    f"comprados com prazo menor que {p.prazo_pagamento_minimo} dias"),
         resumo="Prazo curto faz o pagamento vencer antes de o produto girar, e a farmácia "
                "financia o próprio estoque.",
         valores=[("Prazo médio ponderado",
                   f"{prazo_medio:.0f} dias" if pd.notna(prazo_medio) else "—"),
                  (f"Pedidos com menos de {p.prazo_pagamento_minimo} dias", num(len(curto))),
                  ("Valor desses pedidos", brl0(curto["valor"].sum()))],
         fornecedores=[(f, f"{int(r['prazo'])} dias · {brl0(r['valor'])} em "
                           f"{int(r['pedidos'])} pedido(s)")
                       for f, r in prazo_forn.head(8).iterrows()],
         explicacao="O prazo médio é ponderado pelo valor de cada pedido, porque um pedido "
                    "grande pesa mais no caixa. O ideal é que o prazo de pagamento cubra o "
                    "tempo até o produto ser vendido; sem dados de venda, a régua de prazo "
                    "mínimo fica em Preferências.",
         acao="Negociar prazo maior com os fornecedores listados ou deslocar para eles "
              "apenas itens de giro rápido.")

    # ---------------------------------------------- INFLAÇÃO DE CUSTO DA CESTA
    cesta = variacao[~variacao["suspeito"]]
    inflacao = ((cesta["valor"] * cesta["variacao"]).sum() / max(1e-9, cesta["valor"].sum())
                if len(cesta) else 0.0)
    indice = M.indice_custo(df, p)
    novo(id="m3", categoria="medicamentos",
         nivel=("crit" if inflacao > p.alta_custo_relevante
                else "aten" if inflacao > p.alta_custo_relevante / 2 else "ok"),
         icone="🌡️", impacto=0.0,
         titulo="Inflação de custo da cesta",
         valor=("+" if inflacao >= 0 else "") + pct(inflacao, 1),
         frase=f"de variação média ponderada no custo de {num(len(cesta))} itens recorrentes",
         indicador=(("+" if inflacao >= 0 else "") + pct(inflacao, 1),
                    "de variação de custo, ponderada pelo valor comprado"),
         resumo="Mede quanto o custo dos mesmos medicamentos mudou entre a primeira e a "
                "última compra, separando inflação de mudança de mix.",
         valores=[("Itens na cesta", num(len(cesta))),
                  ("Índice no último mês",
                   f"{indice['indice'].iloc[-1]:.1f}".replace(".", ",") if len(indice) else "—"),
                  ("Subiram", num(int((cesta["variacao"] > 0).sum()))),
                  ("Caíram", num(int((cesta["variacao"] < 0).sum())))],
         explicacao="Cada medicamento comprado mais de uma vez contribui com a variação "
                    "entre o primeiro e o último custo, ponderada pelo valor comprado. "
                    "Variações implausíveis (erro de cadastro) ficam de fora. O ponto fica "
                    f"crítico acima de {pct(p.alta_custo_relevante,0)} e em atenção acima "
                    f"de {pct(p.alta_custo_relevante/2,0)}.",
         acao="Comparar com o reajuste de preço de venda praticado no período.")
    return ins


def pontos_movimentacao(mv: dict, p: Parametros, total: float) -> list[Insight]:
    """Cinco pontos que só existem com entradas e saídas: ruptura, capital
    parado, perda por validade, remarcação e reposição.

    A gravidade usa a mesma régua de exposição dos demais pontos, contra o valor
    comprado no recorte, para que todos fiquem na mesma escala.
    """
    pos, res, prop = mv["pos"], mv["resumo"], mv["remarc"]
    if pos is None or pos.empty:
        return []
    periodo = f"{data(res['inicio'])} a {data(res['fim'])}"
    ins: list[Insight] = []

    def novo(**kw):
        ins.append(Insight(periodo=periodo, simulado=True, **kw))

    def itens(d, texto):
        return [(str(r["medicamento"]), texto(r)) for _, r in d.head(8).iterrows()]

    dias = max(1, res["dias"])
    # ------------------------------------------------------------ ruptura
    rup = pos[pos["situacao"] == "Ruptura"].copy()
    rup["venda_mes"] = rup["faturamento"] / dias * 30
    rup = rup.sort_values("venda_mes", ascending=False)
    risco = float(rup["venda_mes"].sum())
    novo(id="v1", categoria="movimentacao", icone="🚫",
         nivel=p.nivel_por_impacto(risco, total, len(rup) > 0),
         impacto=risco, titulo="Ruptura de itens em linha",
         valor=f"{num(len(rup))} itens",
         frase=f"em linha estão com saldo zero; {brl0(risco)} de venda por mês em risco",
         indicador=(f"{num(len(rup))} itens", "sem estoque, mas repostos com regularidade"),
         resumo="Item que a farmácia costuma repor e que está zerado é venda perdida e "
                "cliente que vai para o concorrente.",
         valores=[("Itens em ruptura", num(len(rup))),
                  ("Venda média mensal desses itens", brl0(risco)),
                  ("Descontinuados (fora de linha)",
                   num(res["situacao"].get("Descontinuado", 0)))],
         medicamentos=itens(rup, lambda r: f"{brl0(r['venda_mes'])}/mês · última compra "
                                           f"{data(r['ultima_compra'])}"),
         explicacao="Ruptura é saldo zero em item reposto mais de uma vez ou comprado há "
                    f"menos de {p.mov_dias_descontinuado} dias. Saldo zero em item comprado "
                    "uma vez e sem reposição recente é descontinuação, não ruptura. A venda "
                    "em risco é o faturamento médio diário do item no período × 30.",
         acao="Incluir esses itens na próxima cotação, começando pelos de maior venda.")

    # ------------------------------------------------------ capital parado
    parado = pos[pos["situacao"].isin(["Excesso", "Sem giro recente"])] \
        .sort_values("valor_estoque", ascending=False)
    valor_parado = float(parado["valor_estoque"].sum())
    novo(id="v2", categoria="movimentacao", icone="🧊",
         nivel=p.nivel_por_impacto(valor_parado, total, len(parado) > 0),
         impacto=valor_parado, titulo="Capital parado em estoque",
         valor=brl0(valor_parado),
         frase=f"em {num(len(parado))} itens com excesso ou sem venda recente "
               f"({pct(valor_parado / max(1.0, res['estoque_valor']), 0)} do estoque)",
         indicador=(brl0(valor_parado), "a custo, em itens que giram devagar"),
         resumo="Estoque acima do necessário prende caixa e aumenta a chance de o lote "
                "vencer na prateleira.",
         valores=[("Excesso", num(res["situacao"].get("Excesso", 0))),
                  ("Sem giro recente", num(res["situacao"].get("Sem giro recente", 0))),
                  ("Valor total do estoque", brl0(res["estoque_valor"])),
                  ("Cobertura mediana", f"{res['cobertura_mediana']:.0f} dias"
                   if pd.notna(res["cobertura_mediana"]) else "—")],
         medicamentos=itens(parado, lambda r: f"{brl0(r['valor_estoque'])} · "
                            + (f"{r['cobertura_dias']:.0f} dias de cobertura"
                               if pd.notna(r["cobertura_dias"]) else "sem venda recente")),
         explicacao=f"Excesso é cobertura acima de {p.mov_cobertura_excesso} dias (estoque ÷ "
                    f"demanda diária dos últimos {p.mov_janela_demanda} dias); sem giro é "
                    "saldo positivo sem venda na janela. O valor é o saldo de cada lote pelo "
                    "seu custo.",
         acao="Suspender a compra desses itens até a cobertura voltar ao alvo e priorizar a "
              "saída dos lotes mais antigos.")

    # -------------------------------------------------- perda por validade
    perda = res["perda_valor"]
    perda_pct = res["perda_pct"] if pd.notna(res["perda_pct"]) else 0.0
    perdidos = pos[pos["valor_perdas"] > 0].sort_values("valor_perdas", ascending=False)
    novo(id="v3", categoria="movimentacao", icone="🗑️",
         nivel="crit" if perda_pct > 0.03 else "aten" if perda_pct > 0.01 else "ok",
         impacto=perda, titulo="Perda por vencimento",
         valor=brl0(perda),
         frase=f"baixados por validade ({pct(perda_pct, 2)} do faturamento, "
               f"{num(res['perda_unidades'])} unidades)",
         indicador=(brl0(perda), "de mercadoria vencida em estoque, a custo"),
         resumo="Cada lote que vence é o custo inteiro perdido. A referência do varejo "
                "farmacêutico pequeno fica entre 1% e 3% do faturamento.",
         valores=[("Perda no período", brl0(perda)), ("Sobre o faturamento", pct(perda_pct, 2)),
                  ("Itens com perda", num(len(perdidos)))],
         medicamentos=itens(perdidos, lambda r: f"{brl0(r['valor_perdas'])} · "
                                                f"{num(r['perdas'])} un"),
         explicacao="Soma das baixas por vencimento do período, avaliadas pelo custo do lote. "
                    "Fica crítico acima de 3% do faturamento e em atenção acima de 1%.",
         acao="Usar a remarcação por validade e reduzir a quantidade comprada dos itens "
              "listados.")

    # ------------------------------------------------- remarcação por validade
    if prop is not None and len(prop):
        valor = prop["valor_excedente"]
        por_acao = valor.groupby(prop["acao"]).sum().sort_values(ascending=False)
        evitada = float(prop["perda_evitada"].sum())
        lista = prop.sort_values("valor_excedente", ascending=False)
        novo(id="v4", categoria="movimentacao", icone="🏷️",
             nivel=p.nivel_por_impacto(float(valor.sum()), total, len(prop) > 0),
             impacto=float(valor.sum()), titulo="Lotes que vão vencer na prateleira",
             valor=f"{num(len(prop))} lotes",
             frase=f"não serão vendidos a tempo; {brl0(valor.sum())} a custo, dos quais "
                   f"{brl0(evitada)} recuperáveis",
             indicador=(brl0(valor.sum()), "em unidades que vencem antes de serem vendidas"),
             resumo="Devolver ao fornecedor, remarcar ou segregar antes de vencer recupera "
                    "parte do custo que viraria perda.",
             valores=[(a, brl0(v)) for a, v in por_acao.items()] +
                     [("Perda evitável (devolver ou remarcar)", brl0(evitada))],
             medicamentos=[(str(r["medicamento"]),
                            f"{r['acao'].lower()} · {int(r['dias_para_vencer'])} dias · "
                            f"{num(r['excedente'])} un")
                           for _, r in lista.head(8).iterrows()],
             explicacao="Para cada lote em estoque, o excedente é o que não sai até a validade "
                        "no ritmo atual de venda. Cascata: controlado → devolver ou baixa "
                        f"controlada; {MV_JANELA} dias ou mais → devolver ao fornecedor; menos "
                        "que o prazo mínimo de tratamento da classe → segregar; nos demais, "
                        "remarcar pela faixa de prazo, sem vender abaixo do custo + 8% e com "
                        "desconto de até 60%. Nenhum preço muda sem aprovação.",
             acao="Revisar as propostas na tela Validade e Remarcação e aprovar as "
                  "remarcações.")

    # ---------------------------------------------------------- reposição
    repor = pos[pos["repor_agora"]].sort_values("valor_sugerido", ascending=False)
    novo(id="v5", categoria="movimentacao", icone="📥",
         nivel="aten" if len(repor) else "ok", impacto=0.0,
         titulo="Itens no ponto de pedido",
         valor=f"{num(len(repor))} itens",
         frase=f"com estoque no ponto de pedido; compra sugerida de {brl0(repor['valor_sugerido'].sum())}",
         indicador=(f"{num(len(repor))} itens", "a repor agora para não faltar"),
         resumo="O ponto de pedido avisa a hora de comprar: o estoque que resta cobre só o "
                "prazo de reposição e a margem de segurança.",
         valores=[("Prazo de reposição", f"{p.mov_lead_time} dias"),
                  ("Cobertura desejada", f"{p.mov_cobertura_alvo} dias"),
                  ("Nível de serviço", pct(p.mov_nivel_servico, 0)),
                  ("Unidades sugeridas", num(repor["qtd_sugerida"].sum()))],
         medicamentos=itens(repor, lambda r: f"{num(r['qtd_sugerida'])} un · "
                                             f"{brl0(r['valor_sugerido'])}"),
         explicacao="Ponto de pedido = demanda prevista × prazo de reposição + estoque de "
                    "segurança, com demanda prevista = média dos últimos dias × fator sazonal "
                    "da classe e segurança = z × desvio da venda diária × √prazo. A "
                    "quantidade cobre o prazo mais a cobertura desejada, sem passar do "
                    "limite de excesso.",
         acao="Levar a lista da tela Reposição e Lotes à próxima cotação.")
    return ins


GRAVIDADE_EXPOSICAO = ["exposicao_critica", "exposicao_atencao"]
GRAVIDADE_ECONOMIA = ["economia_critica", "economia_atencao"]
REGUAS = {
    "a1": ["corte_a", "corte_b", "base_abc"],
    "a2": ["corte_a", "base_abc"],
    "a3": ["corte_b", "base_abc"],
    "a4": ["recorrencia_minima", "corte_a"],
    "a5": ["corte_a"] + GRAVIDADE_EXPOSICAO,
    "a6": ["corte_a", "corte_b"] + GRAVIDADE_EXPOSICAO,
    "a7": ["cv_x", "cv_y", "corte_a"],
    "o1": ["razao_preco_suspeita"] + GRAVIDADE_ECONOMIA,
    "o2": ["razao_preco_suspeita"],
    "f1": ["concentracao_fornecedor"],
    "f2": ["atendimento_minimo", "pedidos_minimos"] + GRAVIDADE_EXPOSICAO,
    "f3": ["corte_a"] + GRAVIDADE_EXPOSICAO,
    "f4": ["pedido_minimo_folga"] + GRAVIDADE_EXPOSICAO,
    "f5": ["prazo_pagamento_minimo"] + GRAVIDADE_EXPOSICAO,
    "m1": ["alta_custo_relevante", "variacao_implausivel", "valor_minimo_analise"]
          + GRAVIDADE_ECONOMIA,
    "m2": ["margem_baixa", "corte_a"] + GRAVIDADE_EXPOSICAO,
    "m3": ["alta_custo_relevante", "variacao_implausivel", "valor_minimo_analise"],
    "c1": ["pico_mensal"] + GRAVIDADE_EXPOSICAO,
    "c2": ["concentracao_cotacao"],
    "e1": ["validade_risco_meses", "data_referencia"] + GRAVIDADE_EXPOSICAO,
    "e2": ["linhas_minimas"] + GRAVIDADE_EXPOSICAO,
    "v1": ["mov_dias_descontinuado"] + GRAVIDADE_EXPOSICAO,
    "v2": ["mov_cobertura_excesso", "mov_janela_demanda"] + GRAVIDADE_EXPOSICAO,
    "v3": [],
    "v4": GRAVIDADE_EXPOSICAO,
    "v5": ["mov_lead_time", "mov_cobertura_alvo", "mov_nivel_servico", "mov_janela_demanda"],
}


def diagnostico(insights: list[Insight], total: float) -> dict:
    """Resumo do painel: contagem por gravidade, economia e maior exposição.

    O plano de ação traz todo ponto crítico ou em atenção: primeiro os que têm
    valor em reais, do maior para o menor; depois os que não têm (como erro de
    cadastro), críticos antes dos em atenção.
    """
    acionaveis = sorted([i for i in insights if i.nivel in ("crit", "aten")],
                        key=lambda i: (i.impacto <= 0, -i.impacto, PESO[i.nivel]))
    economia = sum(i.impacto for i in acionaveis if i.tipo == "economia" and i.impacto > 0)
    # pontos de venda simulada entram no plano de ação, mas não disputam o destaque
    # de maior exposição com os pontos medidos sobre dado real
    exposicao = [i for i in acionaveis
                 if i.tipo != "economia" and i.impacto > 0 and not i.simulado]
    return {
        "contagem": {nv: sum(1 for i in insights if i.nivel == nv)
                     for nv in ("crit", "aten", "info", "ok")},
        "acionaveis": acionaveis,
        "economia": economia,
        "economia_pct": economia / max(1.0, total),
        "maior_exposicao": exposicao[0] if exposicao else None,
    }
