"""Conceitos e Cálculos, Preferências e Base de Dados."""
from __future__ import annotations

import re
from dataclasses import asdict, fields

import pandas as pd
import streamlit as st

from core import dados as D
from core import metricas as M
from core import parametros as PR
from core.memoria import lembrar
from core import previsao as PV
from core.parametros import Parametros
from core.tema import brl, brl0, data, faixa, num, pct


# ===========================================================================
#                          CONCEITOS E CÁLCULOS
# ===========================================================================
# Cada verbete vira uma dúvida, do jeito que alguém perguntaria, com as
# palavras-chave que a busca também aceita (sinônimos e termos do dia a dia).
DUVIDAS = {
    "Cotação": ("O que é uma cotação?",
                ["cotação", "rodada de compra", "distribuidor", "orçamento"]),
    "Pedido": ("O que é um pedido e por que há mais pedidos que cotações?",
               ["pedido", "fornecedor vencedor", "compra"]),
    "Linha de pedido": ("O que é uma linha de pedido?",
                        ["linha", "registro", "item do pedido", "planilha"]),
    "SKU": ("O que é SKU e por que os itens são agrupados por ele?",
            ["sku", "código do produto", "descrição", "agrupamento"]),
    "Cadastro manual e validações": ("Como cadastrar uma compra sem planilha?",
                                     ["cadastro", "manual", "digitar", "pedido", "validação",
                                      "duplicidade", "modelo", "importação"]),
    "Valor pedido": ("Como é calculado o valor pedido (o gasto)?",
                     ["valor pedido", "gasto", "custo", "quantidade", "total comprado"]),
    "Valor faturado": ("Qual a diferença entre valor pedido e valor faturado?",
                       ["valor faturado", "nota fiscal", "corte", "faturamento"]),
    "Nível de atendimento": ("Como é medido o nível de atendimento do fornecedor?",
                             ["atendimento", "entrega", "corte", "falta", "ruptura"]),
    "Margem bruta": ("Como é calculada a margem bruta?",
                     ["margem", "lucro", "preço de venda", "precificação"]),
    "Valor médio por pedido (ticket)": ("O que é o ticket médio (valor médio por pedido)?",
                                        ["ticket", "valor médio", "tamanho da compra"]),
    "Custo médio ponderado": ("Por que o custo médio é ponderado pela quantidade?",
                              ["custo médio", "média ponderada", "média simples"]),
    "Curva ABC": ("O que é a Curva ABC e para que ela serve?",
                  ["curva abc", "classificação", "prioridade", "classe a"]),
    "Valor de consumo": ("Qual valor é usado para montar a Curva ABC?",
                         ["valor de consumo", "base de valor", "faturado", "pedido"]),
    "Percentual acumulado": ("O que é o percentual acumulado da curva?",
                             ["acumulado", "gráfico de pareto", "linha âmbar"]),
    "Regra de corte das classes": ("Como o sistema decide se um item é classe A, B ou C?",
                                   ["classe", "corte", "80%", "95%", "critério"]),
    "Princípio de Pareto": ("O que é o princípio de Pareto (regra 80/20)?",
                            ["pareto", "80/20", "concentração", "curva achatada"]),
    "Faixa de recebimento": ("O que significam as faixas fresco, normal, curto e crítico?",
                             ["vida útil", "validade", "fresco", "curto", "crítico",
                              "recebimento"]),
    "Meses restantes": ("Como são contados os meses até o vencimento?",
                        ["vencimento", "validade", "meses restantes", "data de referência",
                         "lote"]),
    "Concentração de compras": ("Quando a dependência de um fornecedor vira problema?",
                                ["concentração", "dependência", "fornecedor", "risco"]),
    "Economia por troca de fornecedor": ("Como é estimada a economia ao trocar de fornecedor?",
                                         ["economia", "menor custo", "negociação", "troca"]),
    "Impacto financeiro": ("Como o sistema define a gravidade (crítico ou atenção) de cada "
                           "alerta?",
                           ["impacto", "gravidade", "exposição", "crítico", "atenção",
                            "alerta"]),
    "Classificação XYZ": ("O que é a classificação XYZ e a matriz ABC × XYZ?",
                          ["xyz", "regularidade", "coeficiente de variação", "cv",
                           "reposição automática", "matriz"]),
    "Índice de custo da cesta": ("Como saber se os medicamentos estão ficando mais caros?",
                                 ["inflação", "índice", "custo", "cesta", "reajuste"]),
    "Estatística descritiva": ("Quais estatísticas o sistema calcula (média, mediana, quartis)?",
                               ["média", "mediana", "moda", "quartil", "desvio-padrão",
                                "outlier", "intervalo de confiança", "estatística"]),
    "Previsão de compras": ("Como o sistema prevê a próxima cotação e quanto confiar nela?",
                            ["previsão", "próximo mês", "orçamento", "candidatos", "chance",
                             "backtest", "reposição"]),
    "Movimentação de estoque": ("O que é a base de movimentação?",
                                ["movimentação", "entrada", "saída", "venda", "base",
                                 "livro-razão", "saldo", "fefo"]),
    "Giro e cobertura": ("Como são calculados o giro e a cobertura do estoque?",
                         ["giro", "cobertura", "estoque médio", "dias de estoque", "excesso",
                          "ruptura"]),
    "Ponto de pedido e lista de compra": ("Quando comprar e quanto comprar de cada item?",
                                          ["ponto de pedido", "estoque de segurança",
                                           "reposição", "lead time", "nível de serviço",
                                           "quanto comprar"]),
    "Valores estimados e projeções": ("O que significam os selos Estimado e Projeção?",
                                      ["estimado", "projeção", "selo", "premissa",
                                       "observado", "confiável"]),
    "Ponte do estoque": ("Como o estoque de partida chega ao de chegada?",
                         ["ponte", "estoque inicial", "estoque final", "partida",
                          "chegada", "giro", "dias de estoque", "escoamento"]),
    "Custo do lote": ("Como o estoque é avaliado em reais?",
                      ["custo", "lote", "valor em estoque", "custo residual"]),
    "Situação do produto": ("O que é ruptura, excesso ou estoque crítico?",
                            ["situação", "ruptura", "excesso", "crítico",
                             "descontinuado", "em linha"]),
    "Sazonalidade das vendas": ("Em que meses cada classe vende mais?",
                                ["sazonalidade", "estação", "inverno", "índice",
                                 "fator sazonal"]),
    "Lote econômico e dente de serra": ("Qual o tamanho certo de compra?",
                                        ["lote econômico", "lec", "harris",
                                         "dente de serra", "mínimo", "máximo"]),
    "Teste da demanda (WAPE)": ("Quanto a demanda da lista de compra acerta?",
                                ["wape", "erro", "teste", "backtest", "demanda"]),
    "Remarcação por validade": ("O que fazer com lotes perto de vencer?",
                                ["remarcação", "desconto", "validade", "devolução",
                                 "vencimento", "promoção"]),
    "Faturamento mínimo": ("O que é o faturamento mínimo do fornecedor?",
                           ["faturamento mínimo", "pedido mínimo", "frete", "condição comercial"]),
    "Prazo médio de pagamento": ("Como é calculado o prazo médio de pagamento?",
                                 ["prazo", "pagamento", "caixa", "dias", "condição comercial"]),
    "A base de cotações registra só compras": ("De onde vêm as saídas e o saldo?",
                                             ["estoque", "saída", "venda", "inventário",
                                              "giro", "limitação"]),
    "Preços com erro de cadastro": ("Por que alguns itens ficam fora do cálculo de economia?",
                                    ["erro de cadastro", "preço suspeito", "digitação",
                                     "limitação"]),
    "Preço de venda é o da cotação": ("A margem considera o preço praticado no caixa?",
                                      ["preço de venda", "reprecificação", "caixa",
                                       "limitação"]),
    "Frequência como proxy de giro": ("Como o sistema estima o giro sem dados de venda?",
                                      ["giro", "frequência", "recorrência", "reposição",
                                       "limitação"]),
}

ICONE_GRUPO = {"A base": ":material/table_view:", "Valores": ":material/payments:",
               "Curva ABC": ":material/bar_chart:", "Validade": ":material/event_busy:",
               "Fornecedores": ":material/local_shipping:",
               "Estoque": ":material/inventory:", "Limitações": ":material/report:",
               "Premissas": ":material/rule:", "Telas do sistema": ":material/dashboard:"}

# perguntas das telas: "O que a tela X mostra?"
TELAS_DOC = ["Visão Geral", "Gestão de Compras", "Pedidos", "Fornecedores", "Medicamentos",
             "Posição de Estoque", "Reposição e Lotes", "Validade e Remarcação", "Curva ABC",
             "Análises e Indicadores", "Previsão de Compras", "Sistema de Apoio à Decisão",
             "Conceitos e Cálculos", "Tutoriais", "Preferências", "Base de Dados"]
DUVIDAS.update({f"Tela {t}": (f"O que a tela {t} mostra?",
                    ["tela", "aba", t.lower(), "funcionalidade", "indicadores"])
                for t in TELAS_DOC})
DUVIDAS.update({
    "Comparativos mensais": ("Como funcionam as setas de mês anterior e ano anterior?",
                             ["comparativo", "seta", "mês anterior", "ano anterior", "variação",
                              "aumento", "redução"]),
    "Movimentações do período": ("Como se lê a cascata de movimentações da Visão Geral?",
                                 ["movimentações", "cascata", "waterfall", "resultado",
                                  "margem", "ganhos", "perdas"]),
    "Causas das perdas": ("Por que as perdas por validade acontecem?",
                          ["perda", "causa", "fator", "vencimento", "validade", "lote"]),
    "Projeção de fechamento": ("Como o sistema projeta o fechamento do mês?",
                               ["fechamento", "projeção", "mês em curso", "próximo mês",
                                "realizado", "ritmo"]),
    "Réguas ajustáveis em Preferências": ("Quais limites posso ajustar e quais estão em uso?",
                                          ["régua", "premissa", "parâmetro", "limite",
                                           "preferências", "padrão"]),
    "Premissas fixas do cálculo": ("Quais premissas o sistema usa e não dá para mudar?",
                                   ["premissa", "constante", "regra", "convenção", "método"]),
    "Referências usadas para ler os indicadores": ("Com que referências os indicadores são "
                                                   "comparados?",
                                                   ["referência", "literatura", "faixa",
                                                    "benchmark", "pareto", "cobertura"]),
    "Como a base de movimentação foi construída": ("Como a base de movimentação foi "
                                                   "construída e o que nela é simulado?",
                                                   ["simulado", "real", "gerador", "premissa",
                                                    "movimentação", "vendas"]),
})


def _tabela_reguas(p: Parametros) -> str:
    """Tabela em Markdown com todas as réguas de Preferências: valor em uso e padrão."""
    linhas = ["| Categoria | Régua | Em uso | Padrão | O que define |", "|---|---|---|---|---|"]
    for categoria, controles in PR.CONTROLES:
        for campo, rotulo, descricao, *_ in controles:
            linhas.append(f"| {categoria} | {rotulo} | {PR.formatar(campo, getattr(p, campo))} | "
                          f"{PR.formatar(campo, getattr(PR.PADRAO, campo))} | "
                          f"{descricao.split('. ')[0].rstrip('.')} |")
    for campo, (rotulo, _) in PR._FORA_DOS_CONTROLES.items():
        if campo == "nomes_originais":
            continue
        linhas.append(f"| Curva ABC e referência | {rotulo} | {PR.formatar(campo, getattr(p, campo))} | "
                      f"{PR.formatar(campo, getattr(PR.PADRAO, campo))} | ver Curva ABC e "
                      "Meses restantes |")
    return "\n".join(linhas)


def _tabela_fixas(p: Parametros) -> str:
    """Constantes de método que não ficam em Preferências."""
    from core import movimentacao as MV
    prazos = "; ".join(f"{k.split(' /')[0]} {v}" for k, v in MV.PRAZO_MINIMO_CLASSE.items())
    linhas = [
        ("Base", "status que entram na análise", ", ".join(D.STATUS_MANTIDOS) or "todos"),
        ("Base", "identidade de uma linha", "cotação + pedido + código do produto"),
        ("Validade", "dias por mês na contagem de meses restantes", "30,44"),
        ("Validade", "faixas de recebimento (validade restante na entrega)",
         "fresco ≥ 70% · normal 50–70% · curto 30–50% · crítico < 30%"),
        ("Estoque", "avaliação do estoque", "custo residual de cada lote"),
        ("Estoque", "item em linha", f"reposto 2+ vezes ou comprado há menos de "
                                     f"{p.mov_dias_descontinuado} dias"),
        ("Estoque", "estoque de segurança", "z do nível de serviço × desvio diário × √prazo"),
        ("Estoque", "fator sazonal", "entre 0,6 e 1,6; classes com 3.000+ unidades vendidas e "
                                     "12+ meses de histórico"),
        ("Estoque", "regularidade (XYZ) pelas vendas", "6+ meses desde a primeira venda"),
        ("Estoque", "sob encomenda", "classe Z e menos de 1 unidade vendida por mês"),
        ("Estoque", "teto da compra e do lote econômico",
         f"{p.mov_cobertura_excesso} dias de venda (régua de excesso)"),
        ("Remarcação", "janela de devolução ao distribuidor", f"{MV.JANELA_DEVOLUCAO} dias"),
        ("Remarcação", "preço mínimo", f"custo do lote + {MV.MARGEM_PISO:.0%}"),
        ("Remarcação", "desconto máximo", f"{MV.DESCONTO_MAXIMO:.0%}"),
        ("Remarcação", "desconto por prazo até vencer",
         "10% (91–119 dias) · 20% (61–90) · 30% (31–60) · 40% (até 30)"),
        ("Remarcação", "prazo mínimo de tratamento por classe (dias)",
         f"{prazos}; demais {MV.PRAZO_MINIMO_PADRAO}"),
        ("Perdas", "janela de venda antes da compra", "180 dias"),
        ("Perdas", "queda de venda depois da compra", "abaixo de 50% da venda anterior"),
        ("Comparativos", "mês de referência", "último mês fechado do recorte"),
        ("Previsão", "orçamento pelas compras", "média mensal ± 1 desvio-padrão"),
        ("Previsão", "candidatos", "itens comprados em 2+ meses"),
        ("Previsão", "teste no histórico", "6+ meses antes do mês testado; métodos com 4+ "
                                           "meses testados concorrem"),
        ("Previsão", "fechamento projetado", "ritmo de venda dos últimos 30 dias; margem dos 3 "
                                             "últimos meses fechados; perdas dos 6 últimos"),
        ("Gravidade", "maior exposição do painel", "não pode vir de ponto que dependa das "
                                                   "saídas simuladas"),
    ]
    return "| Assunto | Premissa | Valor |\n|---|---|---|\n" + \
        "\n".join(f"| {a} | {b} | {c} |" for a, b, c in linhas)


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acento, para a busca achar 'calculo' em 'Cálculo'."""
    return D._sem_acento(texto)


def _combina(termo: str, texto: str) -> bool:
    """O termo aparece no texto, aceitando variações de final de palavra.

    'cálculo' acha 'calculada' e 'margens' acha 'margem': para palavras de
    cinco letras ou mais, basta o radical (sem as duas últimas letras).
    """
    return termo in texto or (len(termo) >= 5 and termo[:-2] in texto)


def conceitos(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> None:
    faixa("Dúvidas frequentes sobre o sistema: o que cada termo significa, <b>como cada "
          "número é calculado</b> e quais são os limites da base. Pesquise por uma "
          "palavra-chave ou escolha um assunto. Os números citados acompanham os filtros "
          "em uso.", "Conceitos e Cálculos")

    ind = M.indicadores(df)
    base_lab = ("quantidade faturada × custo unitário" if p.base_abc == "valor_faturado"
                else "quantidade pedida × custo unitário")
    cls = abc.classes.set_index("classe") if abc.n else None
    curtas = int(df["validade_curta"].sum())

    V = [
        ("A base", "Cotação", "Base",
         "Uma rodada de compra: a farmácia lança a lista de medicamentos e os "
         "distribuidores respondem com preço e quantidade disponível.",
         f"No recorte há **{num(ind.cotacoes)}** cotações.", "Coluna **Cotação**"),
        ("A base", "Pedido", "Base",
         "O conjunto de itens que um mesmo fornecedor ganhou dentro de uma cotação. "
         "Uma cotação gera vários pedidos, um por distribuidor vencedor.",
         f"Por isso há **{num(ind.pedidos)}** pedidos para {num(ind.cotacoes)} cotações.",
         "Coluna **Pedido**"),
        ("A base", "Linha de pedido", "Base",
         "A unidade mínima da base: um medicamento dentro de um pedido. Quase todo "
         "cálculo parte da soma de linhas.",
         f"**{num(ind.linhas)}** linhas no recorte.", "Cada registro da planilha"),
        ("A base", "SKU", "Base",
         "Código único do produto. É por ele que os itens são agrupados, e não pela "
         "descrição: duas descrições diferentes podem ser o mesmo produto.",
         f"**{num(ind.medicamentos)}** medicamentos distintos.",
         "Coluna **Código do Produto**"),
        ("A base", "Cadastro manual e validações", "Método",
         "Um pedido pode ser digitado na tela Base de Dados, com as mesmas colunas do modelo de "
         "importação. Antes de gravar, cada linha (digitada ou importada) é conferida: campos "
         "obrigatórios, números e datas válidos, CNPJ e EAN com dígito verificador, uma data "
         "por cotação, um fornecedor por pedido, um EAN por código de produto e nenhuma linha "
         "repetida. Erro impede a gravação; aviso só pede atenção.",
         "`chave = cotação + pedido + código do produto` · `faixa de recebimento = (validade − "
         "data da compra) ÷ (validade − fabricação)` · `valor pedido = Qtde. Ped. × Vl. Custo`",
         "Base de Dados → Cadastro manual e Cotações"),

        ("Valores", "Valor pedido", "Fórmula",
         "O que a farmácia solicitou. Somado por mês, fornecedor ou categoria, é a base "
         "de quase todos os gráficos de gasto.",
         f"`valor pedido = Qtde. Ped. × Vl. Custo`\n\nTotal: **{brl(ind.valor_pedido)}**.",
         "Colunas **Qtde. Ped.** e **Vl. Custo**"),
        ("Valores", "Valor faturado", "Fórmula",
         "O que a nota fiscal realmente trouxe. A diferença para o valor pedido é o "
         "corte feito pelo fornecedor.",
         f"`valor faturado = Qtde. Fat. × Vl. Faturado`\n\nTotal: "
         f"**{brl(ind.valor_faturado)}**.", "Colunas **Qtde. Fat.** e **Vl. Faturado**"),
        ("Valores", "Nível de atendimento", "Fórmula",
         "Quanto do que foi pedido chegou. Abaixo de 100%, parte do pedido não foi "
         "entregue — risco de falta na prateleira, não desconto.",
         f"`atendimento = Σ Qtde. Fat. ÷ Σ Qtde. Ped.`\n\nNo recorte: "
         f"**{pct(ind.nivel_atendimento)}**.", "Tela Análises e Indicadores"),
        ("Valores", "Margem bruta", "Fórmula",
         "Ponderada pela quantidade. Usa o preço de venda registrado na cotação, então "
         "reflete a intenção de precificação no momento da compra. Linhas sem preço de "
         "venda ficam de fora.",
         "`margem = 1 − Σ(custo × qtde) ÷ Σ(preço de venda × qtde)`\n\nNo recorte: "
         f"**{pct(M.margem_ponderada(df))}**.",
         "Coluna **Preço de Venda Unitário**"),
        ("Valores", "Valor médio por pedido (ticket)", "Fórmula",
         "Tamanho típico de uma compra. Serve de referência ao aprovar uma nova cotação.",
         f"`ticket = valor pedido ÷ nº de pedidos`\n\nNo recorte: "
         f"**{brl(ind.ticket_medio)}**.", "Telas Visão Geral, Gestão de Compras e Fornecedores"),
        ("Valores", "Custo médio ponderado", "Fórmula",
         "Ponderar pela quantidade evita que uma compra pequena e cara distorça o "
         "período. Uma média simples trataria uma caixa e mil caixas com o mesmo peso.",
         "`custo médio = Σ(custo × qtd) ÷ Σ qtd`",
         "Ficha do medicamento e cálculo de economia"),

        ("Curva ABC", "Curva ABC", "Método",
         "Classifica os medicamentos pela participação no valor de consumo, para separar "
         "o que exige controle individual do que pode ser tratado em bloco. **É o "
         "instrumento central deste sistema**: pelas compras, mostra onde está o gasto; "
         "pelas vendas, o que de fato gira.",
         "", "Tela Curva ABC e todo o apoio à decisão"),
        ("Curva ABC", "Valor de consumo", "Fórmula",
         "É o eixo da classificação. A base pode ser o valor faturado (padrão) ou o "
         "pedido, alternável em Preferências.",
         f"`valor de consumo = {base_lab}, somado por SKU`" +
         (f"\n\nTotal classificado: **{brl(abc.total)}** em {num(abc.n)} medicamentos."
          if abc.n else ""), "Seletor **Base de valor**"),
        ("Curva ABC", "Percentual acumulado", "Fórmula",
         "Depois de ordenar do maior para o menor, é quanto do dinheiro já foi somado até "
         "aquele item. É a linha âmbar do gráfico de Pareto.",
         "`acumulado(i) = Σ valor dos itens 1..i ÷ valor total`",
         "Gráfico da Curva ABC"),
        ("Curva ABC", "Regra de corte das classes", "Método",
         "A classe usa o acumulado **anterior** ao item, de modo que o item que cruza o "
         "corte fecha a classe a que pertence — convenção usual da curva. Usar o "
         "acumulado do próprio item empurraria essa fronteira para a classe seguinte.",
         f"`A se acumulado anterior < {pct(p.corte_a,0)}`\n\n"
         f"`B se acumulado anterior < {pct(p.corte_b,0)}`\n\n`C caso contrário`" +
         (f"\n\nResultado: **A** {num(int(cls.loc['A','itens']))} · "
          f"**B** {num(int(cls.loc['B','itens']))} · "
          f"**C** {num(int(cls.loc['C','itens']))} itens." if cls is not None else ""),
         "Seletor **Critério de classificação**"),
        ("Curva ABC", "Princípio de Pareto", "Conceito",
         "A expectativa clássica é que 20% dos itens concentrem 80% do valor. É a "
         "referência contra a qual a curva desta base é lida.",
         f"Aqui os 20% maiores concentram **{pct(abc.concentracao_20)}**" +
         (" — a curva é mais achatada que o padrão, efeito da cauda de compras pontuais."
          if abc.concentracao_20 < 0.8 else "."), "Tela Curva ABC"),

        ("Validade", "Faixa de recebimento", "Conceito",
         "Quanto restava da validade quando o lote chegou, em percentual do prazo total: "
         "**fresco** 70% ou mais, **normal** 50 a 70%, **curto** 30 a 50%, **crítico** "
         "menos de 30%.",
         f"Curto e crítico somam **{pct(curtas/max(1,len(df)))}** das linhas.",
         "Coluna **Faixa de Recebimento**"),
        ("Validade", "Meses restantes", "Fórmula",
         "Calculado sobre o **último lote recebido** de cada medicamento. 30,44 é a média "
         "de dias por mês no ano. Se a base tiver compras depois da data configurada, "
         "vale a data da última compra.",
         f"`meses = (validade − data de referência) ÷ 30,44`\n\nReferência atual: "
         f"**{data(M.data_referencia(df, p)[0])}**.", "Validade e Remarcação › Validade no recebimento"),

        ("Fornecedores", "Concentração de compras", "Fórmula",
         f"Mede dependência. Acima de {pct(p.concentracao_fornecedor,0)} a farmácia perde "
         "referência de preço e fica exposta a uma falha de entrega.",
         "`concentração = valor do maior fornecedor ÷ valor total`",
         "Tela Fornecedores e apoio à decisão"),
        ("Fornecedores", "Economia por troca de fornecedor", "Fórmula",
         "Para cada medicamento comprado de mais de um distribuidor, compara o custo médio "
         "ponderado de cada um e adota o menor como referência. Não considera frete, prazo "
         "nem faturamento mínimo — é ponto de partida de negociação.",
         "`economia = Σ (custo pago − menor custo do SKU) × qtd`",
         "Apoio à decisão, categoria Oportunidades"),
        ("Fornecedores", "Impacto financeiro", "Método",
         "Cada ponto do apoio à decisão carrega um valor em reais que está em jogo. É ele "
         "que define a gravidade e a ordem do plano de ação. **Economia** é dinheiro "
         "recuperável e pode ser somada. **Exposição** é valor sob risco e não pode: o "
         "mesmo medicamento aparece em mais de um ponto, e somar contaria o mesmo dinheiro "
         "duas vezes — por isso o painel mostra o maior ponto exposto, não o total.",
         f"`economia: crítico ≥ {pct(p.economia_critica,0)} · atenção ≥ "
         f"{pct(p.economia_atencao,0)}`\n\n"
         f"`exposição: crítico ≥ {pct(p.exposicao_critica,0)} · atenção ≥ "
         f"{pct(p.exposicao_atencao,0)}`", "Tela Sistema de Apoio à Decisão"),

        ("Curva ABC", "Classificação XYZ", "Método",
         "Mede a regularidade de cada medicamento. **Pelas vendas**, a variação das vendas "
         "mensais (é a que define a política sob encomenda); **pelas compras**, a quantidade "
         "comprada por trimestre. X é regular, Y varia e Z é esporádico. Cruzada com a ABC, "
         "separa o que aceita reposição automática (AX, AY) do que pede decisão (AZ, CZ).",
         f"`CV = desvio-padrão ÷ média (vendas mensais ou compras trimestrais)`\n\n"
         f"`X se CV ≤ {p.cv_x:.2f} · Y se CV ≤ {p.cv_y:.2f} · Z acima`".replace(".", ","),
         "Análises e Indicadores → ABC × XYZ e apoio à decisão"),
        ("Valores", "Índice de custo da cesta", "Fórmula",
         "Mostra se os mesmos medicamentos estão ficando mais caros, separando inflação de "
         "mudança de mix. Cada compra é comparada com a primeira compra do mesmo item.",
         "`índice do mês = 100 × Σ(custo ÷ custo inicial × peso) ÷ Σ peso`\n\n"
         "`peso = quantidade × custo inicial`",
         "Análises e Indicadores → Preço e margem e apoio à decisão"),
        ("Valores", "Estatística descritiva", "Método",
         "Resume uma variável (custo, quantidade, valor por pedido, dias entre compras) por "
         "posição (média, mediana, moda, quartis) e dispersão (desvio-padrão, coeficiente de "
         "variação, amplitude interquartil). Valores atípicos ficam fora de Q1 − 1,5·IQR e "
         "Q3 + 1,5·IQR.",
         "`IC 95% da média = média ± 1,96 × desvio ÷ √n`",
         "Análises e Indicadores → Estatística"),
        ("Valores", "Previsão de compras", "Método",
         "Estimativa para a próxima cotação: uma faixa de gasto (média mensal ± 1 desvio) e "
         "uma lista de itens recorrentes com chance de voltar a ser comprados. A chance é a "
         "fração dos meses em que o item foi comprado; o ritmo compara a última compra com "
         "o intervalo de costume. O acerto é medido refazendo a previsão para cada mês "
         "passado só com os dados anteriores a ele (backtest).",
         f"`chance = meses com compra ÷ meses observados` · candidato a partir de "
         f"{pct(p.previsao_chance_minima, 0)}, alta a partir de {pct(p.previsao_chance_alta, 0)}"
         "\n\n`faixa = média mensal ± desvio-padrão`",
         "Tela Previsão de Compras"),
        ("Estoque", "Movimentação de estoque", "Conceito",
         "Livro-razão do estoque: estoque inicial, cada entrada (compra), venda e perda por "
         "validade, lote a lote, com o saldo após cada movimento. Cada entrada aponta para a "
         "linha da cotação que a originou. Ao ser carregado, o livro tem as colunas "
         "padronizadas, os fornecedores codificados como no resto do sistema e passa por "
         f"{num(40)} verificações (tela Base de Dados). A construção da base atual está "
         "descrita na documentação técnica.",
         "`saldo = estoque inicial + entradas − vendas − perdas por validade`",
         "Grupo Movimentação, Análises e Indicadores, Curva ABC (vendas), Previsão e apoio à "
         "decisão"),
        ("Estoque", "Ponte do estoque", "Fórmula",
         "Liga o estoque de **partida** (véspera do início do período) ao de **chegada** "
         "(data final) pelo que entrou e saiu entre os dois, a custo. Dela saem os "
         "indicadores clássicos do período. Fecha centavo a centavo porque cada saída é "
         "avaliada pelo custo do lote de onde saiu.",
         "`partida + compras − custo do que foi vendido − perdas = chegada`\n\n"
         "`giro = custo vendido ÷ ((partida + chegada) ÷ 2)` · `dias de estoque = estoque "
         "médio ÷ custo vendido por dia` · `escoamento = unidades vendidas ÷ (partida + "
         "compras)` · `perda sobre o disponível = unidades vencidas ÷ (partida + compras)`",
         "Análises e Indicadores → Giro e cobertura; Visão Geral"),
        ("Estoque", "Custo do lote", "Fórmula",
         "O estoque é avaliado lote a lote. Um mesmo código de lote pode chegar em duas "
         "compras com custos diferentes; por isso o custo do saldo é o **residual**: o que "
         "entrou a custo menos o que saiu a custo.",
         "`custo do lote = (Σ entradas a custo − Σ saídas a custo) ÷ saldo do lote`\n\n"
         "`valor em estoque = Σ saldo do lote × custo do lote`",
         "Posição de Estoque, Visão Geral e todos os valores de estoque"),
        ("Estoque", "Giro e cobertura", "Fórmula",
         "**Giro do estoque** é quantas vezes o estoque médio foi vendido e reposto no "
         "período. Giro 3× num ano quer dizer que, em média, cada real em estoque virou venda "
         "três vezes: o produto fica cerca de 120 dias parado (365 ÷ 3). Giro **alto** = "
         "estoque enxuto, menos capital parado e menos risco de vencer, mas mais risco de "
         "faltar; giro **baixo** = dinheiro parado e lotes envelhecendo. O giro é medido a "
         "custo, para comparar a mesma grandeza dos dois lados (custo do que foi vendido ÷ "
         "estoque a custo).\n\nNo **período**, o estoque médio é a média entre o estoque de "
         "partida e o de chegada (Ponte do estoque). **Por produto**, é ponderado pelo tempo "
         "em que cada saldo ficou na prateleira, porque um produto pode passar meses zerado e "
         "dias cheio. **Dias de estoque** = estoque médio ÷ custo vendido por dia: é o mesmo "
         "giro dito em dias. **Cobertura** olha para a frente: quantos dias o estoque de hoje "
         "dura no ritmo de venda recente.",
         f"`giro do produto = unidades vendidas ÷ estoque médio no tempo` · `cobertura = "
         f"estoque ÷ demanda diária ({p.mov_janela_demanda} dias)` · crítico abaixo de "
         f"{p.mov_cobertura_critica} dias, excesso acima de {p.mov_cobertura_excesso}, "
         "referência de 30 a 60 dias",
         "Análises e Indicadores → Giro e cobertura; Posição de Estoque; apoio à decisão"),
        ("Estoque", "Situação do produto", "Método",
         "Cada produto recebe a primeira situação que se aplicar, nesta ordem: ruptura, "
         "descontinuado, estoque crítico, validade próxima, excesso, sem giro recente, "
         "normal. Item **em linha** é o reposto mais de uma vez ou comprado há pouco tempo.",
         f"`ruptura = saldo 0 e em linha` · `descontinuado = saldo 0 e sem reposição há "
         f"{p.mov_dias_descontinuado}+ dias` · `crítico = cobertura < {p.mov_cobertura_critica}` "
         f"· `validade próxima = lote mais antigo vence em < {p.mov_validade_proxima} dias` · "
         f"`excesso = cobertura > {p.mov_cobertura_excesso}`",
         "Posição de Estoque e apoio à decisão"),
        ("Estoque", "Sazonalidade das vendas", "Fórmula",
         "Índice de venda de cada classe terapêutica por mês do ano (100 = média da classe). "
         "A venda do mês é dividida pelos dias do mês no período e pelos produtos ativos, "
         "para o catálogo que cresce não se passar por estação. O índice ajusta a demanda "
         "da lista de compra.",
         "`índice(mês) = 100 × taxa do mês ÷ taxa média da classe` · `fator sazonal = índice "
         "dos dias que a compra cobre ÷ índice da janela de demanda`, entre 0,6 e 1,6, só "
         f"com {num(3000)}+ unidades e 12 meses de histórico",
         "Análises e Indicadores → Mix e sazonalidade; Reposição e Lotes"),
        ("Estoque", "Lote econômico e dente de serra", "Fórmula",
         "O lote econômico (Harris) equilibra o custo de pedir com o custo de manter. Como "
         "a fórmula supõe produto que não vence, o lote é limitado pela cobertura máxima. O "
         "dente de serra mostra o estoque subindo com cada lote e caindo com a venda, entre "
         "o mínimo e o máximo.",
         f"`LEC = √(2 × venda anual × custo de pedir ÷ custo de manter)`, limitado a "
         f"{p.mov_cobertura_excesso} dias de venda · `mínimo = estoque de segurança` · "
         "`máximo = mínimo + lote` · `ciclo = lote ÷ venda diária`",
         "Reposição e Lotes"),
        ("Estoque", "Teste da demanda (WAPE)", "Método",
         "Mede quanto a demanda usada na lista de compra acerta. Em várias datas passadas, a "
         "demanda de 30 dias é prevista só com os dados anteriores e comparada com o que foi "
         "vendido depois. É comparada com a média simples e com repetir o último mês.",
         "`WAPE = Σ |previsto − vendido| ÷ Σ vendido` · `viés = Σ previsto ÷ Σ vendido − 1`",
         "Reposição e Lotes"),
        ("Valores", "Ponto de pedido e lista de compra", "Fórmula",
         "Hora de comprar: quando o estoque só cobre o prazo de reposição mais uma margem de "
         "segurança. A demanda é a média dos últimos dias ajustada pela estação da classe "
         "terapêutica (fator de 0,6 a 1,6). Itens que vendem menos de uma unidade por mês, de "
         "forma irregular, ficam sob encomenda. A quantidade sugerida leva o estoque até a "
         "cobertura desejada, sem passar do limite de excesso. O gráfico de dente de serra "
         "compara o saldo real com esta política.",
         f"`demanda prevista = demanda/dia × fator sazonal` · `ponto de pedido = demanda "
         f"prevista × {p.mov_lead_time} + segurança` · `segurança = z × desvio diário × √prazo` "
         f"(z do nível de serviço de {pct(p.mov_nivel_servico, 0)}) · `comprar = mín(demanda "
         f"prevista × (prazo + {p.mov_cobertura_alvo}) + segurança, demanda prevista × "
         f"{p.mov_cobertura_excesso}) − estoque`",
         "Movimentação → Reposição e Lotes"),
        ("Valores", "Valores estimados e projeções", "Conceito",
         "Três tipos de número aparecem no painel:\n\n"
         "- **Realizado (sem selo)**: aconteceu e está registrado — compras, entradas, vendas, "
         "saldo, perdas. Só muda se os dados mudarem.\n"
         "- **Estimado**: um valor do **presente ou do passado** que depende de uma premissa "
         "declarada. Ex.: economia na troca de fornecedor (supõe comprar tudo pelo menor custo "
         "já pago), lote econômico (supõe custo de pedir e de manter), perda evitável de um "
         "lote (supõe o ritmo atual de venda até a validade), ponto de pedido. Se a premissa "
         "mudar, o número muda, mesmo sem dado novo.\n"
         "- **Projeção**: um valor do **futuro** calculado a partir do histórico. Ex.: "
         "fechamento do mês em curso, vendas do próximo mês, orçamento da próxima cotação, "
         "itens candidatos. Só se confirma ou não depois que o período acontece, e o sistema "
         "mostra o erro que esse método teve no passado.\n\n"
         "Resumindo: estimado responde *quanto vale isso, se a premissa valer*; projeção "
         "responde *quanto vai ser*.",
         "`sem selo = realizado` · `Estimado = hoje, com premissa` · `Projeção = futuro, com "
         "erro medido no histórico`",
         "Visão Geral, Sistema de Apoio à Decisão, Previsão e telas de Movimentação"),
        ("Estoque", "Remarcação por validade", "Método",
         "Para cada lote em estoque que vence nos próximos dias, o sistema calcula o "
         "**excedente** — o que não sai até a validade no ritmo atual — e propõe uma ação, "
         "da que mais recupera para a que menos recupera: controlado → devolver ou baixa "
         "com escrituração; 120 dias ou mais → devolver ao fornecedor; menos que o prazo "
         "mínimo de tratamento da classe (20 a 60 dias) → segregar; nos demais → remarcar. "
         "Nenhum preço muda sem aprovação.",
         "`excedente = saldo − venda diária × dias até vencer` · `desconto: 10% (91–119 dias),"
         " 20% (61–90), 30% (31–60), 40% (até 30)` · `preço proposto ≥ custo × 1,08`, "
         "desconto até 60% · `perda evitada = excedente × custo do lote`",
         "Validade e Remarcação, Visão Geral e apoio à decisão"),
        ("Fornecedores", "Faturamento mínimo", "Conceito",
         "Menor valor de pedido que o distribuidor aceita faturar, informado na cotação. "
         "Pedido abaixo dele pode ser recusado ou cobrado com frete; pedido que passa por "
         "pouco fica 'no limite', porque qualquer corte na nota o derruba.",
         f"`no limite se valor do pedido < mínimo × (1 + {pct(p.pedido_minimo_folga,0)})`",
         "Análises e Indicadores → Condições comerciais e apoio à decisão"),
        ("Fornecedores", "Prazo médio de pagamento", "Fórmula",
         "Dias entre a compra e o vencimento do pagamento. Ponderado pelo valor, porque um "
         "pedido grande pesa mais no caixa. Prazo menor que o tempo de venda faz a farmácia "
         "financiar o próprio estoque.",
         "`prazo médio = Σ(prazo × valor do pedido) ÷ Σ valor`",
         "Análises e Indicadores → Condições comerciais e apoio à decisão"),

        ("Limitações", "A base de cotações registra só compras", "Limitação",
         "A planilha de cotação traz o que foi **comprado**: não tem venda, baixa nem "
         "inventário. Saídas, saldo, giro e cobertura vêm do **livro de movimentação**. "
         "Sem ele, a Validade no recebimento aponta **risco de perda** pelo último lote "
         "comprado, não a posição física, e a Curva ABC por compras é o critério de "
         "prioridade.",
         "", "Validade e Remarcação, Curva ABC e apoio à decisão"),
        ("Limitações", "Preços com erro de cadastro", "Limitação",
         f"Alguns medicamentos aparecem com custos que variam mais de "
         f"{pct(p.razao_preco_suspeita-1,0)} entre fornecedores. Diferença dessa ordem não "
         "é negociação, é erro de digitação ou de unidade na origem. Esses itens ficam "
         "fora do cálculo de economia e viram um alerta próprio.",
         "", "Apoio à decisão, categoria Oportunidades"),
        ("Limitações", "Preço de venda é o da cotação", "Limitação",
         "A margem usa o preço de venda registrado no momento da compra. Se a farmácia "
         "reprecificou depois, a margem real difere da calculada aqui.",
         "", "Tela Análises e Indicadores"),
        ("Limitações", "Frequência como proxy de giro", "Limitação",
         "Nas análises feitas só com as compras (ritmo de compra, previsão pelas compras, "
         "XYZ pelas compras), o número de vezes que um item foi comprado substitui o giro. "
         "Um item comprado em grande volume uma vez pode girar mais que outro comprado toda "
         "semana; com o livro de movimentação, prefira as visões pelas vendas.",
         "", "Análises e Indicadores → Ritmo de compra; Previsão pelas compras"),
        # ------------------------------------------------ métodos novos
        ("Valores", "Comparativos mensais", "Método",
         "Os cartões com setas comparam o **último mês fechado** do recorte com o mês anterior "
         "e com o mesmo mês do ano anterior. O mês em curso não entra: comparar 8 dias de um "
         "mês com meses inteiros faria tudo parecer queda. Mês sem movimento dentro do "
         "histórico vale zero; mês anterior ao início dos dados aparece como *sem dado*.\n\n"
         "**Verde** = variação favorável; **laranja** = desfavorável; **cinza** = sem juízo. "
         "Vendas e margem que sobem são favoráveis; perdas que sobem, desfavoráveis; compras, "
         "pedidos e estoque ficam em cinza, porque subir ou cair depende do contexto. As cores "
         "são seguras para daltonismo (ver *Cores e acessibilidade*), e ao passar o mouse a "
         "seta diz se a variação é favorável ou não.",
         "`variação = (mês − mês comparado) ÷ |mês comparado|` · margem em **pontos "
         "percentuais**: `margem do mês − margem do mês comparado` · `base zero` quando o mês "
         "comparado é zero",
         "Visão Geral, Gestão de Compras, Posição de Estoque, Validade e Remarcação"),
        ("Valores", "Movimentações do período", "Fórmula",
         "A cascata da Visão Geral mostra a composição do resultado: das vendas sai o custo do "
         "que foi vendido (sobra a margem bruta), saem as perdas por validade (sobra a margem "
         "após perdas) e entram os ganhos **estimados** que dependem de uma ação. Os riscos "
         "(dinheiro parado, lotes perto de vencer) não entram: não são entradas nem saídas do "
         "período. Sem livro de movimentação, a cascata parte das compras e desconta a economia "
         "possível.\n\n**Cores pelo efeito no negócio**, não pela direção da barra: verde = "
         "benéfico (ganhos possíveis), laranja = prejudicial (perdas), azul-claro = neutro (o "
         "custo normal do que foi vendido), azul-escuro = totais; as estimadas têm verde mais "
         "suave, contorno e *(estimado)* no rótulo. A ponte do estoque (Análises) segue a mesma "
         "regra: o que sai vendido é verde, o que vence é laranja e as compras, que só repõem, "
         "são azul-claro.",
         "`margem bruta = vendas − custo do que foi vendido` · `margem após perdas = margem "
         "bruta − perdas por validade` · `resultado com os ganhos = margem após perdas + troca "
         "de fornecedor + renegociação + lotes devolvidos ou remarcados (estimados)`",
         "Visão Geral"),
        ("Estoque", "Causas das perdas", "Método",
         "Para cada lote vencido, o sistema localiza a entrada que o trouxe e atribui **um** "
         "fator, o primeiro que os movimentos comprovam, nesta ordem: (1) **estoque de "
         "abertura** — o lote já estava no estoque no início do livro, sem compra registrada "
         "para medir; (2) **chegou com validade curta** — menos de 50% da validade na entrega; "
         "(3) **lote maior que a venda até a validade** — a quantidade recebida passava da "
         "venda diária dos 180 dias anteriores × dias de validade; (4) **comprado sem "
         "histórico de venda** — nenhuma venda nos 180 dias antes; (5) **venda caiu depois da "
         "compra** — a venda diária até o vencimento ficou abaixo da metade da anterior; (6) "
         "**outros fatores**. São associações medidas nos dados, não prova de causa.",
         "`venda esperada até vencer = venda/dia dos 180 dias anteriores × dias de validade na "
         "chegada` · `lote grande se recebido > venda esperada`",
         "Validade e Remarcação → Por que as perdas acontecem"),
        ("Valores", "Projeção de fechamento", "Método",
         "Projeta o fechamento do mês em curso e o mês seguinte, separando **realizado** "
         "(movimentos até a data final), **estimado** (premissas: margem, perdas, compras) e "
         "**projeção** (o futuro). A venda futura repete o ritmo dos últimos 30 dias — o mesmo "
         "princípio do método *último mês*, que teve o menor erro no teste com o histórico. A "
         "faixa do mês seguinte é ± o erro mediano desse teste.",
         "`fechamento do mês = vendas realizadas + venda/dia (30 dias) × dias que faltam` · "
         "`mês seguinte = venda/dia × dias do mês` · `custo vendido = vendas × (1 − margem "
         "média dos 3 últimos meses fechados)` · `perdas = média dos 6 últimos meses` · "
         "`compras = orçamento pelas compras` · `estoque ao fim = estoque + compras − custo "
         "vendido − perdas`",
         "Previsão de Compras → Pelas vendas"),
        ("Valores", "Cores e acessibilidade", "Método",
         "Três cores têm significado fixo em todo o painel: **verde** = benéfico ou saudável, "
         "**laranja** = prejudicial ou crítico, **âmbar** = atenção. O par verde × laranja "
         "segue a paleta de Okabe e Ito, feita para daltonismo: o verde puxa para o azul e o "
         "laranja para o amarelo, eixo que quem tem protanopia ou deuteranopia continua "
         "enxergando. A cor vem acompanhada de setas, sinais + e −, *(estimado)* no rótulo das "
         "barras estimadas e, nos comparativos, da explicação ao passar o mouse.\n\n"
         "O `verificar.py` simula os três tipos de daltonismo (matrizes de Machado, Oliveira e "
         "Fernandes, 2009) e mede a distância entre as cores (CIEDE2000): verde × laranja fica "
         "acima de 17 em todos — antes, com verde e vermelho, ficava em 8 a 10, quase iguais. "
         "Os textos coloridos têm contraste de pelo menos 4,5:1 (WCAG 2.1).",
         "`ΔE00(verde, laranja) ≥ 15 em protanopia, deuteranopia e tritanopia` · `contraste do "
         "texto ≥ 4,5:1`",
         "Todas as telas; teste no bloco 16 do verificar.py"),
        ("Valores", "Tendências (mini-gráficos)", "Método",
         "Na Visão Geral, cada indicador tem um gráfico dos 12 meses até o mês de referência, "
         "em grade de duas colunas. A frase acima diz a **direção**: a média do último trimestre (faixa "
         "cinza) contra a do trimestre anterior. Variação abaixo de 5% (ou 0,5 p.p. na margem) "
         "é *estável*. A linha fica verde quando a direção é favorável, laranja quando é "
         "desfavorável e azul quando não é boa nem ruim por si (compras). Embaixo, a média dos "
         "12 meses — o valor do último mês já está nos cartões do topo.",
         "`direção = média(últimos 3 meses) ÷ média(3 meses anteriores) − 1` · margem: "
         "`diferença em p.p.`",
         "Visão Geral → Tendências"),

        # ------------------------------------------------------ premissas
        ("Premissas", "Réguas ajustáveis em Preferências", "Premissa",
         "Os limites que o usuário pode mudar em Preferências. Cada um muda os cálculos na "
         "hora e é salvo para a próxima abertura. A tabela mostra o valor em uso e o padrão.",
         _tabela_reguas(p), "Preferências"),
        ("Premissas", "Premissas fixas do cálculo", "Premissa",
         "Regras e constantes que não estão em Preferências, por serem convenções da "
         "literatura ou decisões de método. Ficam no código e são citadas em cada resposta.",
         _tabela_fixas(p), "core/dados.py, core/metricas.py, core/movimentacao.py, "
                           "core/previsao.py"),
        ("Premissas", "Referências usadas para ler os indicadores", "Premissa",
         "Faixas da literatura que o sistema usa para dizer se um indicador está dentro, "
         "acima ou abaixo do esperado. Fora da faixa não é erro de cálculo: é um achado.",
         "| Indicador | Referência | Fonte |\n|---|---|---|\n"
         "| Valor nos 20% maiores itens (Pareto) | cerca de 80% (70% a 90%) | Princípio de "
         "Pareto; Nguyen et al. (2022) |\n"
         "| Cobertura do estoque | 30 a 60 dias | Slack, Brandon-Jones e Johnston (2022) |\n"
         "| Perda por validade ÷ vendas | 1% a 3% | varejo farmacêutico pequeno |\n"
         "| Margem bruta | 25% a 50% | varejo farmacêutico |\n"
         "| Itens em linha zerados (ruptura) | abaixo de 2% | TCC, seção 2.6.3 |\n"
         "| Sazonalidade de respiratórios | inverno acima do verão | TCC, seção 2.5.3 |\n"
         "| Classificação XYZ e política por item | AX automático, AZ acompanhado, CZ sob "
         "encomenda | Pontes (2013) |\n"
         "| Lote econômico | √(2DS ÷ H) | Harris (1913) |",
         "Base de Dados → Movimentação de estoque (Indicadores × literatura)"),
        ("Premissas", "Como a base de movimentação foi construída", "Premissa",
         "O livro de movimentação da base atual combina dados **reais** e **simulados**. As "
         "entradas são as compras faturadas da cotação, uma por linha. O estoque inicial, as "
         "vendas e as perdas foram **simulados** a partir do ritmo real de compra de cada "
         "produto, por um gerador em Python com semente fixa. Os números de venda mostram "
         "como o sistema decide; ao carregar as vendas do caixa no mesmo layout, todo o "
         "cálculo continua igual.",
         "| Etapa | Regra |\n|---|---|\n"
         "| Estoque inicial | 30 dias antes do 1º pedido; produtos comprados 2+ vezes, ou 1 vez "
         "nos 6 primeiros meses (probabilidade 0,70); quantidade = média comprada × fator "
         "entre 0,50 e 1,40 |\n"
         "| Demanda | por ciclo de reposição: quantidade recebida × 1,03 ÷ dias até a compra "
         "seguinte, com teto de 2,8× a taxa típica; trecho final até 1,2× a última compra; "
         "abertura até 0,8× o estoque inicial; itens comprados uma vez vendem 70% do recebido |\n"
         "| Vendas diárias | sorteio de Poisson com essa taxa × fator sazonal da classe "
         "terapêutica; só com saldo; consumo pelo lote que vence primeiro (FEFO) |\n"
         "| Preço | preço da cotação com reajuste de 0,37% ao mês e margem mínima de 18% sobre o "
         "custo do lote |\n"
         "| Perdas | lote que chega à validade com saldo é baixado |\n"
         "| Reprodutibilidade | semente 42: o mesmo arquivo é gerado sempre |",
         "Documentação técnica, seção 9.10"),

        # ------------------------------------------------- telas do sistema
        ("Telas do sistema", "Tela Visão Geral", "Tela",
         "O resumo do negócio. **Resultado do mês**: compras, vendas, margem bruta e perdas "
         "do último mês fechado, com setas contra o mês anterior e o ano anterior. "
         "**Situação no período**: compras, estoque na data final e quanto variou, giro e o "
         "maior fornecedor. **Movimentações**: cascata das vendas até o resultado, com os "
         "ganhos estimados. **Prioridades**: os três pontos de maior impacto do apoio à "
         "decisão, com o que fazer. **Tendências**: um mini-gráfico por indicador (vendas, "
         "margem, perdas e compras) com a direção do último trimestre. Atalhos levam à tela de "
         "cada pergunta. O significado dos selos *Estimado* e *Projeção* está em *Valores "
         "estimados e projeções*; na tela, aparece ao passar o mouse no selo, e a explicação "
         "de cada gráfico, no (?) ao lado do título.",
         "Critérios: mês de referência = último mês fechado · prioridades = pontos críticos e "
         "em atenção, ordenados por gravidade e valor (ver *Impacto financeiro*)",
         "Menu → Visão Geral"),
        ("Telas do sistema", "Tela Gestão de Compras", "Tela",
         "Para onde vai o dinheiro das compras. **Compras do mês**: valor pedido, pedidos, "
         "valor médio por pedido e medicamentos comprados no último mês fechado, com "
         "comparativos. **Onde o gasto se concentra**: quantos itens (classe A) fazem a maior "
         "parte do gasto, a participação dos genéricos, o mês de maior gasto e o fabricante de "
         "maior peso. **Valor pedido por mês** (picos em âmbar) e **por categoria comercial**. "
         "**Composição** num gráfico só, escolhendo medicamento, forma farmacêutica ou "
         "fabricante. A lista linha a linha está em Pedidos › Itens comprados. Com o filtro de "
         "um só medicamento, mostra também a reposição e o dente de serra dele.",
         "`valor pedido = Qtde. Ped. × Vl. Custo` · `valor médio por pedido = valor ÷ pedidos` · "
         "`pico = mês acima de " + str(round(p.pico_mensal, 2)).replace(".", ",") + "× a média`",
         "Menu → Compras → Gestão de Compras"),
        ("Telas do sistema", "Tela Pedidos", "Tela",
         "Duas abas. **Por pedido**: cada pedido com cotação, data, fornecedor, representante, "
         "status, itens, valor pedido, valor faturado e nível de atendimento; clicar numa "
         "linha abre os itens. **Itens comprados**: todas as linhas de pedido do recorte, com a "
         "classe ABC de cada medicamento.",
         "`atendimento = Σ Qtde. Fat. ÷ Σ Qtde. Ped.`", "Menu → Compras → Pedidos"),
        ("Telas do sistema", "Tela Fornecedores", "Tela",
         "Participação de cada distribuidor no valor comprado e ficha individual: período, "
         "participação, pedidos, valor, medicamentos, nível de atendimento, valor médio por "
         "pedido, entregas com validade curta, valor por mês e, ao lado, **o que se compra "
         "dele** por categoria comercial ou forma farmacêutica, com um traço marcando a mesma "
         "participação nas compras de todos (barra acima do traço = onde ele é forte). O botão "
         "no topo mostra ou esconde os nomes originais, como em Preferências › Privacidade.",
         f"`concentração = valor do fornecedor ÷ valor total` · crítica acima de "
         f"{pct(p.concentracao_fornecedor, 0)}", "Menu → Compras → Fornecedores"),
        ("Telas do sistema", "Tela Medicamentos", "Tela",
         "A ficha de um medicamento, escolhido entre **todos** os do recorte (a lista aceita "
         "digitar o nome ou o código). Quatro cartões dizem o que fazer: **comprar de** qual "
         "fornecedor (o de menor custo médio, com a economia que teria dado — a mesma do apoio "
         "à decisão), o **custo da última compra** contra a régua de alta, a **margem** contra "
         "a régua de margem apertada e a **próxima compra prevista** pelo ritmo. Depois, custo "
         "por mês, valor por fornecedor, **reposição e lote econômico com o dente de serra** e "
         "o histórico de compras. Com o filtro de um só medicamento no menu, a ficha abre "
         "direto nele.",
         "`custo médio = Σ(custo × qtd) ÷ Σ qtd` · `economia = Σ máx(0, custo pago − menor custo "
         "médio) × qtd` · `variação = (último custo − primeiro) ÷ primeiro`, alta acima de "
         f"{pct(p.alta_custo_relevante, 0)} · margem apertada abaixo de "
         f"{pct(p.margem_baixa, 0)} · `próxima compra = última + intervalo médio`",
         "Menu → Compras → Medicamentos"),
        ("Telas do sistema", "Tela Posição de Estoque", "Tela",
         "Estoque na data final, produtos normais, zerados ou críticos e valor parado; "
         "unidades vendidas, recebidas e estoque ao fim do último mês fechado com "
         "comparativos; o que pede atenção, com atalho para a tela que resolve; situação de "
         "cada produto; lista filtrável e o saldo de um produto ao longo do tempo.",
         "Critérios de situação: ver *Situação do produto*", "Menu → Movimentação → Posição "
         "de Estoque"),
        ("Telas do sistema", "Tela Reposição e Lotes", "Tela",
         "Quando e quanto comprar: os quatro passos da decisão, a política de cada produto "
         "(ponto de pedido, sob encomenda, sem venda recente, fora de linha), a lista de "
         "compra, o dente de serra com o lote econômico, o tamanho do lote comprado × "
         "recomendado e o teste da demanda (WAPE).",
         "Ver *Ponto de pedido e lista de compra*, *Lote econômico e dente de serra* e *Teste "
         "da demanda*", "Menu → Movimentação → Reposição e Lotes"),
        ("Telas do sistema", "Tela Validade e Remarcação", "Tela",
         "Perdas por vencimento por mês, com comparativo; **por que as perdas acontecem** "
         "(fator de cada lote, por classe terapêutica e pela validade na entrega); a proposta "
         "para cada lote que vai vencer (devolver, remarcar, segregar); e a validade com que "
         "as compras chegam, por faixa e por fornecedor.",
         "Ver *Causas das perdas* e *Remarcação por validade*",
         "Menu → Movimentação → Validade e Remarcação"),
        ("Telas do sistema", "Tela Curva ABC", "Tela",
         "A classificação A, B e C pelas compras, pelas vendas e o cruzamento das duas: "
         "tamanho de cada classe, curva de Pareto, distribuição, ranking completo e a "
         "planilha em Excel.",
         "Ver *Curva ABC*, *Regra de corte das classes* e *Princípio de Pareto*",
         "Menu → Análise e decisão → Curva ABC"),
        ("Telas do sistema", "Tela Análises e Indicadores", "Tela",
         "Oito assuntos: giro e cobertura (ponte do estoque), entrega e cotação, condições "
         "comerciais, preço e margem, mix e sazonalidade, ABC × XYZ, ritmo de compra e "
         "estatística descritiva. Só o assunto aberto é calculado.",
         "Ver *Ponte do estoque*, *Giro e cobertura*, *Classificação XYZ* e *Estatística "
         "descritiva*", "Menu → Análise e decisão → Análises e Indicadores"),
        ("Telas do sistema", "Tela Previsão de Compras", "Tela",
         "Pelas compras: orçamento provável da próxima cotação, itens candidatos com chance e "
         "ritmo, e a confiabilidade medida no histórico. Pelas vendas: **fechamento "
         "projetado** do mês em curso e do seguinte (realizado × estimado × projeção), o teste "
         "do método de previsão e o resumo do que comprar.",
         "Ver *Previsão de compras* e *Projeção de fechamento*",
         "Menu → Análise e decisão → Previsão de Compras"),
        ("Telas do sistema", "Tela Sistema de Apoio à Decisão", "Tela",
         "As leituras que viram ação: 26 pontos em sete assuntos, cada um com valor em reais, "
         "gravidade, detalhe, réguas e o que fazer; os gráficos que fundamentam o diagnóstico; "
         "o plano de ação; e o que mudou desde a leitura anterior.",
         "Ver *Impacto financeiro*", "Menu → Análise e decisão → Sistema de Apoio à Decisão"),
        ("Telas do sistema", "Tela Conceitos e Cálculos", "Tela",
         "Esta tela: o que cada termo significa, como cada número é calculado, as premissas, "
         "o que cada tela mostra e os limites da base. A busca aceita palavras sem acento.",
         "", "Menu → Referência → Conceitos e Cálculos"),
        ("Telas do sistema", "Tela Tutoriais", "Tela",
         "Roteiros de vídeo em trilhas, do primeiro acesso à atualização da base.", "",
         "Menu → Referência → Tutoriais"),
        ("Telas do sistema", "Tela Preferências", "Tela",
         "As réguas de decisão por categoria, com o valor padrão, a marca de alterado e o "
         "efeito do valor atual sobre os dados. Os ajustes são salvos automaticamente.",
         "Ver *Réguas ajustáveis em Preferências*", "Menu → Referência → Preferências"),
        ("Telas do sistema", "Tela Base de Dados", "Tela",
         "Três abas. **Cotações**: base atual, importação de planilha com prévia e "
         "validações, modelo de importação, versões anteriores e exportação. **Cadastro "
         "manual**: um pedido digitado item a item. **Movimentação de estoque**: livro atual, "
         "verificações, indicadores × literatura e carga de um livro novo.",
         "Ver *Cadastro manual e validações*", "Menu → Referência → Base de Dados"),
    ]

    # ---------------- busca e assunto ----------------
    busca = st.text_input("Pesquisar dúvida", key="conc_busca",
                          placeholder="Digite uma palavra-chave: margem, validade, "
                                      "curva abc, economia, fornecedor…",
                          icon=":material/search:")
    grupos = ["Tudo"] + list(dict.fromkeys(v[0] for v in V))
    escolha = st.pills("Assunto", grupos, default="Tudo", key="conc_grupo") or "Tudo"

    termos = _normalizar(busca).split()
    encontrados = []
    for grupo, titulo, tag, corpo, formula, onde in V:
        pergunta, chaves = DUVIDAS.get(titulo, (titulo, []))
        if escolha != "Tudo" and grupo != escolha:
            continue
        extra = "calculo formula conta" if tag == "Fórmula" else ""
        texto = _normalizar(" ".join([grupo, titulo, pergunta, corpo, formula, onde,
                                      " ".join(chaves), extra]))
        if all(_combina(t, texto) for t in termos):
            # relevância: termo no título ou na pergunta pesa mais que nas palavras-chave,
            # que pesam mais que no corpo da resposta
            cabeca = _normalizar(f"{titulo} {pergunta}")
            chaves_txt = _normalizar(" ".join(chaves))
            nota = sum(3 * _combina(t, cabeca) + 2 * _combina(t, chaves_txt) for t in termos)
            encontrados.append((grupo, titulo, tag, corpo, formula, onde, pergunta, chaves, nota))
    if termos:
        encontrados.sort(key=lambda e: -e[8])
    encontrados = [e[:8] for e in encontrados]
    abertos = {e[1] for e in encontrados[:3]} if termos else set()

    if busca.strip():
        st.caption(f"{len(encontrados)} dúvida(s) encontrada(s) para “{busca.strip()}”.")
    else:
        st.caption(f"{len(encontrados)} dúvidas. Clique em uma pergunta para ver a "
                   "resposta.")
    if not encontrados:
        st.info("Nenhuma dúvida com essa palavra-chave. Tente um termo mais curto, como "
                "“margem”, “validade” ou “abc”.")
        return

    # ---------------- lista de dúvidas, agrupada por assunto ----------------
    n = 0
    for grupo in dict.fromkeys(e[0] for e in encontrados):
        do_grupo = [e for e in encontrados if e[0] == grupo]
        st.markdown(f"#### {ICONE_GRUPO.get(grupo, '')} {grupo} "
                    f"<span class='selo'>{len(do_grupo)}</span>", unsafe_allow_html=True)
        for _, titulo, tag, corpo, formula, onde, pergunta, chaves in do_grupo:
            n += 1
            # com busca ativa, as três respostas mais relevantes já aparecem abertas
            # "1\." escapado: sem a barra, o rótulo viraria uma lista numerada
            with st.expander(f"{n}\\. {pergunta}", expanded=titulo in abertos):
                st.markdown(f"<span class='selo'>{tag}</span> &nbsp;**{titulo}**",
                            unsafe_allow_html=True)
                st.markdown(corpo)
                if formula:
                    st.markdown(formula)
                onde_html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", onde)
                st.markdown(f"<p class='onde'>Onde aparece: {onde_html}</p>"
                            "<div class='palavras-chave'>" +
                            "".join(f"<span>{c}</span>" for c in chaves) + "</div>",
                            unsafe_allow_html=True)


# ===========================================================================
#                              PREFERÊNCIAS
# ===========================================================================
def _restaurar_padroes() -> None:
    """Chamada no clique de 'Restaurar padrões', antes de a tela ser redesenhada.

    Apagar o estado dos controles não basta: o navegador devolve o valor que
    estava na régua e ela continuaria com o ajuste antigo. Por isso cada
    controle recebe aqui o valor padrão, na mesma unidade em que é exibido.
    """
    padrao = PR.restaurar()
    st.session_state["params"] = padrao
    for _, controles in PR.CONTROLES:
        for campo, _, _, _, _, _, fmt in controles:
            valor = getattr(padrao, campo)
            st.session_state[f"pref_{campo}"] = (float(round(valor * 100, 2)) if fmt == "pct"
                                                 else float(valor)
                                                 if fmt in ("moeda", "vezes", "decimal")
                                                 else int(valor))
    st.session_state["pref_nomes_originais"] = padrao.nomes_originais
    st.session_state["_restaurado"] = True


def preferencias(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> Parametros:
    """Controles dos parâmetros. Devolve os parâmetros já atualizados."""
    faixa("Aqui você define as réguas do sistema. Cada ajuste <b>recalcula a análise "
          "inteira</b> — gráficos, tabelas, gravidade dos alertas e o texto das mensagens. "
          "O quadro colorido abaixo de cada controle mostra o efeito do valor atual sobre "
          "os dados filtrados. <b>Os ajustes são salvos automaticamente</b> e já valem no "
          "Sistema de Apoio à Decisão, que mostra o que mudou.", "Preferências")

    mudados = PR.alterados(p)
    st.subheader("Preferências de análise")
    st.caption((f"{len(mudados)} ajuste fora do padrão" if len(mudados) == 1
                else f"{len(mudados)} ajustes fora do padrão") if mudados
               else "Todos os parâmetros estão no valor padrão.")

    c1, c2, c3 = st.columns([1.2, 1.6, 2.2])
    c1.button("Restaurar padrões", width="stretch", icon=":material/restart_alt:",
              on_click=_restaurar_padroes)
    paginas = st.session_state.get("paginas_menu", {})
    if "Sistema de Apoio à Decisão" in paginas:
        with c2:
            st.page_link(paginas["Sistema de Apoio à Decisão"],
                         label="Ver o efeito no Apoio à Decisão", icon=":material/lightbulb:")
    if st.session_state.pop("_restaurado", False):
        st.toast("Réguas de volta ao padrão.", icon=":material/restart_alt:")

    # contexto para os indicadores de efeito
    hoje, _ = M.data_referencia(df, p)
    lotes = M.posicao_lotes(df, abc, hoje) if not df.empty else pd.DataFrame()
    total = float(df["valor_pedido"].sum()) if not df.empty else 1.0
    forn = M.por_dimensao(df, "Nome do Fornecedor")
    part_lider = forn.iloc[0]["valor_pedido"] / total if len(forn) else 0.0
    atend = M.atendimento_fornecedor(df)
    var = M.variacao_custo(df, p)
    margens = M.margem_classe_a(df, abc)
    serie = M.serie_mensal(df)
    media = serie["valor_pedido"].mean() if not serie.empty else 0.0

    def efeito(campo: str) -> str:
        if campo == "validade_risco_meses" and len(lotes):
            risco = lotes[lotes["meses_restantes"] < p.validade_risco_meses]
            venc = int((lotes["meses_restantes"] < 0).sum())
            return (f"**{num(len(risco))}** em risco — {num(venc)} já vencidos e "
                    f"**{num(len(risco)-venc)}** vencendo na janela · "
                    f"**{brl0(risco['valor_lote'].sum())}**")
        if campo == "recorrencia_minima" and abc.n:
            r = abc.itens[abc.itens["compras"] >= p.recorrencia_minima]
            a = r[r["classe"] == "A"]
            return f"**{num(len(r))}** itens recorrentes · **{num(len(a))}** deles na classe A"
        if campo == "concentracao_fornecedor":
            estado = "**crítico**" if part_lider > p.concentracao_fornecedor else "atenção"
            return f"líder tem **{pct(part_lider)}** → {estado}"
        if campo == "atendimento_minimo" and len(atend):
            n = int(((atend["pedidos"] >= p.pedidos_minimos) &
                     (atend["atendimento"] < p.atendimento_minimo)).sum())
            return f"**{num(n)}** fornecedores abaixo do limite"
        if campo == "pedidos_minimos" and len(atend):
            n = int((atend["pedidos"] >= p.pedidos_minimos).sum())
            return f"**{num(n)}** de {num(len(atend))} fornecedores avaliados"
        if campo == "linhas_minimas" and len(atend):
            n = int((atend["linhas"] >= p.linhas_minimas).sum())
            return f"**{num(n)}** fornecedores entram no gráfico de validade"
        if campo == "alta_custo_relevante" and len(var):
            n = int(((var["variacao"] > p.alta_custo_relevante) & (~var["suspeito"])).sum())
            return f"**{num(n)}** medicamentos entram na lista de custo em alta"
        if campo == "variacao_implausivel" and len(var):
            return f"**{num(int(var['suspeito'].sum()))}** variações marcadas como erro"
        if campo == "razao_preco_suspeita":
            op = M.oportunidades_fornecedor(df, p)
            return (f"**{num(int(op['suspeito'].sum()))}** itens fora do cálculo de economia"
                    if len(op) else "sem itens multi-fornecedor no recorte")
        if campo == "valor_minimo_analise" and len(var):
            return f"**{num(len(var))}** medicamentos com valor suficiente para análise"
        if campo == "margem_baixa" and len(margens):
            n = int((margens["margem"] < p.margem_baixa).sum())
            return f"**{num(n)}** itens de classe A abaixo do limite"
        if campo == "pico_mensal" and not serie.empty:
            n = int((serie["valor_pedido"] > media * p.pico_mensal).sum())
            return f"**{num(n)}** meses acima do limite, de {num(len(serie))}"
        if campo == "concentracao_cotacao" and not df.empty:
            cot = df.groupby("Cotação")["valor_pedido"].sum().nlargest(3).sum() / total
            estado = "**atenção**" if cot > p.concentracao_cotacao else "saudável"
            return f"as 3 maiores somam **{pct(cot)}** → {estado}"
        if campo == "pedido_minimo_folga" and not df.empty:
            ped = M.pedidos_condicoes(df, p)
            n_ab = int((ped["situacao"] == "abaixo do mínimo").sum())
            n_li = int((ped["situacao"] == "no limite").sum())
            return f"**{num(n_ab)}** pedidos abaixo do mínimo e **{num(n_li)}** no limite"
        if campo == "prazo_pagamento_minimo" and not df.empty:
            ped = M.pedidos_condicoes(df, p)
            curto = ped[ped["prazo_dias"] < p.prazo_pagamento_minimo]
            return (f"**{num(len(curto))}** pedidos com prazo menor, somando "
                    f"**{brl0(curto['valor'].sum())}** ({pct(curto['valor'].sum()/total)})")
        if campo in ("previsao_chance_minima", "previsao_chance_alta") and not df.empty:
            cand = PV.candidatos(df, abc, p)
            n_alta = int((cand["chance"] == "alta").sum()) if len(cand) else 0
            return (f"**{num(len(cand))}** candidatos para a próxima cotação · "
                    f"**{num(n_alta)}** com chance alta")
        if campo.startswith("mov_"):
            from paginas import movimentacao as PMov
            pos = PMov.posicao(p)
            if pos is None:
                return "sem livro de movimentação carregado"
            sit = pos["situacao"].value_counts()
            if campo in ("mov_cobertura_critica", "mov_cobertura_excesso",
                         "mov_validade_proxima", "mov_dias_descontinuado",
                         "mov_janela_demanda"):
                return (f"**{num(int(sit.get('Estoque crítico', 0)))}** em estoque crítico · "
                        f"**{num(int(sit.get('Excesso', 0)))}** em excesso · "
                        f"**{num(int(sit.get('Validade próxima', 0)))}** com validade próxima · "
                        f"**{num(int(sit.get('Ruptura', 0)))}** em ruptura")
            if campo in ("mov_custo_pedido", "mov_taxa_manutencao"):
                from core import movimentacao as MVm
                rec, _ = PMov.recorte()
                lec = MVm.lote_economico(pos, rec, p)
                vc = lec["leitura"].value_counts()
                return (f"lote recomendado mediano de **{num(lec['lec'].median())} un** · "
                        f"**{num(int(vc.get('compra acima do lote econômico', 0)))}** itens "
                        "comprados acima do lote econômico")
            rep = pos[pos["repor_agora"]]
            return (f"**{num(len(rep))}** itens no ponto de pedido · compra sugerida de "
                    f"**{brl0(pos['valor_sugerido'].sum())}**")
        if campo in ("cv_x", "cv_y") and abc.n:
            x = M.classificacao_xyz(df, abc, p)["xyz"].value_counts()
            return (f"**{num(int(x.get('X', 0)))}** itens regulares (X) · "
                    f"**{num(int(x.get('Y', 0)))}** variáveis (Y) · "
                    f"**{num(int(x.get('Z', 0)))}** irregulares (Z)")
        if campo in ("economia_critica", "economia_atencao",
                     "exposicao_critica", "exposicao_atencao"):
            return f"equivale a **{brl0(total * getattr(p, campo))}** nesta base"
        return ""

    # ---------------- organização: uma categoria por bloco, um ajuste por linha
    def categoria(ancora: str, icone: str, titulo: str, descricao: str) -> None:
        st.subheader(titulo, anchor=ancora)
        st.markdown(f"<div class='pref-cat'><span class='ico'><span aria-hidden='true'>"
                    f"{icone}</span></span><small>{descricao}</small></div>",
                    unsafe_allow_html=True)

    def cabeca(rotulo: str, padrao: str, alterado: bool, descricao: str) -> None:
        marca = "<span class='alterado'>alterado</span>" if alterado else ""
        st.markdown(f"<div class='pref-item'><b>{rotulo}</b><span>{marca} "
                    f"<span class='padrao'>padrão: {padrao}</span></span></div>"
                    f"<p class='pref-desc'>{descricao}</p>", unsafe_allow_html=True)

    def separador() -> None:
        st.markdown("<hr class='pref-sep'>", unsafe_allow_html=True)

    def mostrar_efeito(txt: str) -> None:
        if txt:
            # **negrito** do Markdown não vale dentro de HTML: vira <b>
            txt = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)
            st.markdown(f"<div class='efeito'><b>Efeito agora:</b> {txt}</div>",
                        unsafe_allow_html=True)

    def formatar(valor, fmt: str) -> str:
        if fmt == "pct":
            return pct(valor, 1)
        if fmt == "moeda":
            return brl0(valor)
        if fmt == "vezes":
            return f"{valor:.2f}×".replace(".", ",")
        if fmt == "decimal":
            return f"{valor:.2f}".replace(".", ",")
        return f"{int(valor)} {fmt}"

    # descrição e ícone de cada categoria de PR.CONTROLES
    SOBRE = {
        "Validade e estoque": ("pref-validade", "event_busy",
                               "Quando um lote passa a ser risco de vencimento e quando um "
                               "medicamento é tratado como item de reposição."),
        "Fornecedores": ("pref-fornecedores", "local_shipping",
                         "Quanto depender de um distribuidor é aceitável e quantos dados "
                         "são necessários antes de julgar a entrega de cada um."),
        "Preço e margem": ("pref-preco", "sell",
                           "O que conta como alta de custo, o que é erro de cadastro e "
                           "qual margem é considerada apertada."),
        "Compras e caixa": ("pref-compras", "account_balance_wallet",
                            "Quando um mês vira pico de desembolso, quando a compra está "
                            "concentrada em poucas cotações e qual prazo de pagamento é "
                            "aceitável para o caixa."),
        "Previsão de compras": ("pref-previsao", "event_upcoming",
                                "Quais itens entram na lista de candidatos da próxima cotação "
                                "e a partir de quando a chance de compra é tratada como alta."),
        "Movimentação de estoque": ("pref-movimentacao", "swap_vert",
                                    "Como o sistema lê entradas e saídas: a janela da demanda, "
                                    "os limites de cobertura que definem estoque crítico e "
                                    "excesso, e o prazo e o nível de serviço que definem o "
                                    "ponto de pedido."),
        "Regularidade (XYZ)": ("pref-xyz", "timeline",
                               "Como o sistema separa a compra regular (X), variável (Y) e "
                               "irregular (Z), pelo coeficiente de variação da quantidade "
                               "comprada a cada trimestre."),
        "Régua de gravidade": ("pref-gravidade", "crisis_alert",
                               "A partir de quanto dinheiro, em proporção do valor comprado, "
                               "um alerta do apoio à decisão vira crítico ou atenção."),
    }
    indice = [("pref-privacidade", "Privacidade"), ("pref-abc", "Curva ABC")] + \
        [(SOBRE[t][0], t) for t, _ in PR.CONTROLES]
    st.markdown("<div class='pref-indice'>" + "".join(
        f"<a href='#{a}'>{t}</a>" for a, t in indice) + "</div>", unsafe_allow_html=True)

    # ---------------- Privacidade ----------------
    with st.container(border=True):
        categoria("pref-privacidade", "visibility", "Privacidade",
                  "Como fornecedores e representantes aparecem nas telas, filtros e "
                  "mensagens.")
        cabeca("Nomes originais", "desligado", p.nomes_originais != PR.PADRAO.nomes_originais,
               "Desligado, o sistema mostra códigos (Fornecedor A, Representante 01) para "
               "que a origem dos dados não seja identificada em apresentações. A tela Base "
               "de Dados e a exportação mantêm sempre os nomes originais.")
        valor = ({} if "pref_nomes_originais" in st.session_state
                 else {"value": p.nomes_originais})
        p.nomes_originais = st.toggle(
            "Mostrar os nomes originais de fornecedores e representantes",
            key="pref_nomes_originais", **valor)
        mostrar_efeito("nomes <b>originais</b> visíveis em todas as telas."
                       if p.nomes_originais else
                       "nomes <b>codificados</b>; o Fornecedor A é o de maior volume de "
                       "compra. Os códigos ficam fixos em <code>dados/apelidos.json</code>.")

    # ---------------- Curva ABC ----------------
    with st.container(border=True):
        categoria("pref-abc", "bar_chart", "Curva ABC",
                  "Como os medicamentos são classificados em A, B e C. A classificação "
                  "orienta todo o apoio à decisão.")
        atual = next((k for k, v in PR.CORTES_ABC.items() if v == p.corte),
                     list(PR.CORTES_ABC)[0])
        cabeca("Critério de classificação", list(PR.CORTES_ABC)[0].replace(" (padrão)", ""),
               p.corte != PR.PADRAO.corte,
               "Até qual percentual acumulado do valor um item é classe A, e até qual é "
               "classe B. O restante é classe C.")
        escolha = st.selectbox("Critério de classificação", list(PR.CORTES_ABC),
                               index=list(PR.CORTES_ABC).index(atual),
                               label_visibility="collapsed")
        p.corte_a, p.corte_b = PR.CORTES_ABC[escolha]
        if abc.n:
            cA = abc.classes.iloc[0]
            mostrar_efeito(f"<b>{num(int(cA['itens']))}</b> itens na classe A — "
                           f"<b>{pct(cA['pct_itens'],1)}</b> do mix carregam "
                           f"<b>{pct(cA['pct_valor'],1)}</b> do valor.")
        separador()
        atual_b = next((k for k, v in PR.BASES_ABC.items() if v[0] == p.base_abc),
                       list(PR.BASES_ABC)[0])
        cabeca("Base de valor", "valor faturado", p.base_abc != PR.PADRAO.base_abc,
               "Qual valor ordena a curva: o faturado (o que a nota trouxe) ou o pedido "
               "(o que foi solicitado ao fornecedor).")
        escolha_b = st.selectbox("Base de valor", list(PR.BASES_ABC),
                                 index=list(PR.BASES_ABC).index(atual_b),
                                 label_visibility="collapsed")
        p.base_abc = PR.BASES_ABC[escolha_b][0]
        mostrar_efeito(f"total classificado de <b>{brl(abc.total)}</b>.")

    # ---------------- categorias de réguas ----------------
    for titulo, controles in PR.CONTROLES:
        ancora, icone, descricao = SOBRE.get(titulo, (f"pref-{titulo}", "tune", ""))
        with st.container(border=True):
            categoria(ancora, icone, titulo, descricao)
            if titulo == "Validade e estoque":
                padrao_data = pd.Timestamp(PR.PADRAO.data_referencia)
                cabeca("Data de referência", data(padrao_data),
                       p.data_referencia != PR.PADRAO.data_referencia,
                       "Data a partir da qual são contados os meses até o vencimento. Se "
                       "a base tiver compras depois dela, vale a data da última compra.")
                nova_data = st.date_input("Data de referência",
                                          value=pd.Timestamp(p.data_referencia).date(),
                                          format="DD/MM/YYYY", label_visibility="collapsed")
                p.data_referencia = str(nova_data)
                vencidos = int((lotes["meses_restantes"] < 0).sum()) if len(lotes) else 0
                mostrar_efeito(f"<b>{num(vencidos)}</b> medicamentos com o último lote já "
                               "vencido nesta data.")
                separador()
            for i, (campo, rot, desc, mn, mx, passo, fmt) in enumerate(controles):
                if i:
                    separador()
                atual_v = getattr(p, campo)
                padrao_v = getattr(PR.PADRAO, campo)
                cabeca(rot, formatar(padrao_v, fmt), atual_v != padrao_v, desc)
                # o valor salvo entra como 'value' só enquanto o controle não tem
                # estado próprio; depois vale o estado (que 'Restaurar padrões'
                # reposiciona). Sem 'value', a régua cairia no mínimo da escala.
                chave = f"pref_{campo}"
                if fmt == "pct":
                    inicial = float(round(atual_v * 100, 2))
                elif fmt in ("moeda", "vezes", "decimal"):
                    inicial = float(atual_v)
                else:
                    inicial = int(atual_v)
                valor = {} if chave in st.session_state else {"value": inicial}
                if fmt == "pct":
                    novo = st.slider(rot, float(mn * 100), float(mx * 100),
                                     step=float(passo * 100), format="%.1f%%",
                                     key=chave, label_visibility="collapsed", **valor)
                    novo = round(novo / 100, 6)       # sem resíduo de ponto flutuante
                elif fmt in ("moeda", "vezes", "decimal"):
                    novo = st.slider(rot, float(mn), float(mx), step=float(passo),
                                     format={"moeda": "R$ %.0f", "vezes": "%.2fx",
                                             "decimal": "%.2f"}[fmt],
                                     key=chave, label_visibility="collapsed", **valor)
                    novo = round(novo, 6)
                else:
                    novo = st.slider(rot, int(mn), int(mx), step=int(passo),
                                     format=f"%d {fmt}", key=chave,
                                     label_visibility="collapsed", **valor)
                setattr(p, campo, novo)
                mostrar_efeito(efeito(campo))

    with st.expander("O que não se ajusta nesta tela"):
        st.markdown(
            "**Filtro de status do pedido.** A base consolidada já contém apenas os pedidos "
            f"com status {', '.join(D.STATUS_MANTIDOS) or 'todos'}. O recorte é aplicado na "
            "entrada dos dados. Para mudar, edite `STATUS_MANTIDOS` em `core/dados.py`, "
            "apague `dados/base_consolidada.csv` e abra o sistema de novo: a base é "
            "reprocessada a partir da planilha original com as regras novas.\n\n"
            "**Correções de cadastro.** Trocas de nome de produto e remoção de prefixos são "
            "aplicadas na entrada, no bloco `CORRECOES` do mesmo arquivo.\n\n"
            "**Faixas de vida útil na entrega.** Fresco, normal, curto e crítico vêm "
            "classificados da própria cotação. O sistema lê, não recalcula. Para trabalhar com "
            "outra régua, use a data de referência e os meses até o vencimento.")

    # salvamento automático: o ajuste vale já, inclusive depois de recarregar a página
    if asdict(p) != asdict(PR.carregar()):
        if PR.salvar(p):
            st.toast("Preferência salva e aplicada em todas as telas.",
                     icon=":material/check_circle:")
        else:
            st.error("Não foi possível gravar dados/preferencias.json; o ajuste vale só "
                     "nesta sessão.")
    return p


# ===========================================================================
#                              BASE DE DADOS
# ===========================================================================
def base_dados(df: pd.DataFrame) -> pd.DataFrame | None:
    """Os dados que alimentam o sistema: cotações e movimentação de estoque.

    Devolve a base de cotações nova se houve inclusão ou restauração.
    """
    faixa("Os dados que alimentam o sistema: as <b>cotações</b> (compras) e o <b>livro de "
          "movimentação</b> (entradas e saídas do estoque). Cada arquivo novo passa pelas "
          "verificações antes de ser gravado, e a versão anterior fica guardada.",
          "Base de Dados")

    # mensagem da inclusão ou restauração anterior, que vem de antes do rerun
    aviso = st.session_state.pop("aviso_base", None)
    if aviso:
        st.success(aviso)
        paginas = st.session_state.get("paginas_menu", {})
        if "Sistema de Apoio à Decisão" in paginas:
            st.page_link(paginas["Sistema de Apoio à Decisão"],
                         label="Ver a nova leitura no Sistema de Apoio à Decisão — o que "
                               "mudou com os dados novos", icon=":material/radar:")

    aba_cot, aba_man, aba_mov = st.tabs([":material/receipt_long: Cotações",
                                         ":material/edit_note: Cadastro manual",
                                         ":material/swap_vert: Movimentação de estoque"])
    with aba_mov:
        _base_movimentacao(df)
    with aba_man:
        nova_manual = _cadastro_manual(df)
    with aba_cot:
        nova_arquivo = _base_cotacoes(df)
    return nova_manual if nova_manual is not None else nova_arquivo


def _base_movimentacao(df: pd.DataFrame) -> None:
    """Origem, verificações e carga do livro de movimentação (antiga tela de Qualidade)."""
    from core import movimentacao as MV
    from core.memoria import lembrar
    from core.tema import linha_cartoes
    from paginas import movimentacao as PM
    p = st.session_state["params"]
    rec, completo = PM.recorte()
    if completo is None:
        PM.sem_livro()
    else:
        arquivo = MV.arquivo_livro()
        tipos = completo.groupby("tipo").agg(linhas=("quantidade", "size"),
                                             unidades=("quantidade", "sum"))
        st.subheader("Livro atual")
        cols = st.columns(4)
        for col, (rot, val) in zip(cols, [
            ("Movimentos", num(len(completo))), ("Produtos", num(completo["ean"].nunique())),
            ("Início", data(completo["data"].min())), ("Fim", data(completo["data"].max())),
        ]):
            col.metric(rot, val)
        st.dataframe(pd.DataFrame({
            "Movimento": [MV.TIPOS[t] for t in MV.TIPOS],
            "Linhas": [int(tipos.loc[t, "linhas"]) if t in tipos.index else 0 for t in MV.TIPOS],
            "Unidades": [abs(int(tipos.loc[t, "unidades"])) if t in tipos.index else 0
                         for t in MV.TIPOS]}), hide_index=True, width="stretch")
        st.caption(f"Arquivo em uso: **{arquivo.name if arquivo else '—'}**. Cada entrada aponta "
                   "para a linha da cotação que a originou. A construção da base atual está "
                   "descrita na documentação técnica (DOCUMENTACAO.md, seção 9).")

        st.subheader("Verificações do livro")
        st.caption("Executadas sobre o livro inteiro, sem filtros. Falha impede o uso; atenção "
                   "é uma diferença explicada.")
        resultado = lembrar("mov_validacao", MV.validar, completo, df, p)
        cont = resultado["resultado"].value_counts()
        linha_cartoes([
            ("Aprovadas", num(cont.get("PASSOU", 0)), f"de {num(len(resultado))} verificações",
             "destaque"),
            ("Atenção", num(cont.get("ATENÇÃO", 0)), "diferenças explicadas"),
            ("Falhas", num(cont.get("FALHOU", 0)), "impediriam o uso do livro"),
        ], colunas=3)
        sobre_bloco = {
            "Estrutura": "tipos de movimento, sinais das quantidades e campos obrigatórios",
            "Saldo": "saldo = soma dos movimentos anteriores; ponte do estoque fecha",
            "Lotes": "saída pelo lote que vence primeiro, nenhum lote vendido vencido",
            "Financeiro": "valores = quantidade × custo ou preço, sem venda abaixo do custo",
            "Integração": "cada entrada confere com a sua linha da base de cotação",
            "Arquivos": "os resultados do sistema contra os arquivos que vieram com o livro",
            "Remarcação": "propostas por lote coerentes com o livro e com as regras de preço",
            "Plausibilidade": "perdas, margem e reposições na ordem de grandeza do setor",
        }
        for bloco, g in resultado.groupby("bloco", sort=False):
            n_ok = int((g["resultado"] == "PASSOU").sum())
            marca = "✅" if n_ok == len(g) else ("⚠️" if (g["resultado"] != "FALHOU").all()
                                                 else "❌")
            with st.expander(f"{marca} {bloco} — {n_ok} de {len(g)} aprovadas · "
                             f"{sobre_bloco.get(bloco, '')}"):
                st.dataframe(g[["verificacao", "resultado", "detalhe"]].rename(columns={
                    "verificacao": "Verificação", "resultado": "Resultado",
                    "detalhe": "Detalhe"}), hide_index=True, width="stretch",
                    column_config={"Detalhe": st.column_config.TextColumn(width="large")})

        if rec is not None and not rec.mov.empty:
            st.subheader("Indicadores × literatura")
            st.caption("Cada indicador do recorte ao lado da faixa de referência citada no TCC "
                       "(seção 2.6). Fora da faixa não é erro de cálculo: é um achado.")
            pos = PM.posicao(p)
            res = lembrar("mov_resumo", MV.resumo, rec, pos)
            abc_v = lembrar("abc_vendas", MV.curva_abc_vendas, pos, p)
            ref = lembrar("mov_referencias", MV.referencias, rec, pos, res, abc_v, p)

            def mostrar_valor(v, u):
                if pd.isna(v):
                    return "—"
                return (pct(v, 1) if u == "pct" else f"{v:.0f} dias" if u == "dias"
                        else f"{v:.2f}×".replace(".", ","))
            marca = {"dentro": "✅ dentro", "acima": "⬆ acima", "abaixo": "⬇ abaixo",
                     "sem dado": "—"}
            st.dataframe(ref.assign(valor=[mostrar_valor(v, u) for v, u in
                                           zip(ref["valor"], ref["unidade"])],
                                    leitura=ref["leitura"].map(marca))
                         [["indicador", "valor", "referencia", "leitura", "fonte"]]
                         .rename(columns={"indicador": "Indicador", "valor": "Valor",
                                          "referencia": "Referência", "leitura": "Leitura",
                                          "fonte": "Fonte"}),
                         hide_index=True, width="stretch",
                         column_config={"Fonte": st.column_config.TextColumn(width="large")})

        gerador = MV.validacao_do_gerador()
        if len(gerador):
            with st.expander(f"Verificações feitas na geração da base ({len(gerador)})"):
                st.dataframe(gerador, width="stretch", hide_index=True, height=360)

    st.subheader("Carregar um livro novo")
    st.caption("Por exemplo, com as vendas exportadas do caixa no mesmo layout. O arquivo só "
               "substitui o atual se passar nas verificações; o anterior fica em "
               "movimentacao/historico/.")
    arquivo = st.file_uploader("Livro de movimentação (movimentacao_estoque.csv ou .xlsx)",
                               type=["csv", "xlsx"], key="mov_upload")
    if arquivo is not None and st.button("Verificar e substituir", icon=":material/upload:",
                                         key="mov_substituir"):
        with st.spinner("Lendo e verificando..."):
            ok, resultado = MV.substituir_livro(arquivo.getvalue(), df, arquivo.name)
        if ok:
            st.success("Livro substituído. Todas as telas já usam a versão nova.")
            st.rerun()
        else:
            st.error("O arquivo não passou nas verificações e nada foi alterado.")
            st.dataframe(resultado[resultado["resultado"] == "FALHOU"], hide_index=True,
                         width="stretch")


def _base_cotacoes(df: pd.DataFrame) -> pd.DataFrame | None:
    """Base atual de cotações, inclusão, versões anteriores e exportação."""
    ind = M.indicadores(df)
    st.subheader("Base atual")
    cols = st.columns(5)
    for col, (rot, val) in zip(cols, [
        ("Linhas", num(ind.linhas)), ("Pedidos", num(ind.pedidos)),
        ("Cotações", num(ind.cotacoes)), ("Medicamentos", num(ind.medicamentos)),
        ("Fornecedores", num(ind.fornecedores)),
    ]):
        col.metric(rot, val)
    st.caption(f"Período coberto: {data(ind.inicio)} a {data(ind.fim)}")

    st.subheader("Incluir novas cotações")
    st.caption("Envie uma planilha (.xlsx) ou CSV com as mesmas colunas da base. "
               "Linhas já existentes, identificadas por cotação + pedido + produto, "
               "são ignoradas automaticamente; as novas passam pelas mesmas validações do "
               "cadastro manual.")
    from core import cadastro as CD
    st.download_button("Baixar o modelo de importação (Excel)",
                       lembrar("modelo_importacao", CD.modelo_excel, df),
                       file_name="modelo_importacao_cotacao.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/download:",
                       help="Colunas na ordem da base, uma linha de exemplo e a aba "
                            "Instruções com o que preencher em cada campo.")
    # a chave muda a cada inclusão para esvaziar o campo de envio
    envio = st.session_state.setdefault("envio_n", 0)
    arquivo = st.file_uploader("Arquivo de cotações", type=["xlsx", "csv"],
                               key=f"upload_cotacoes_{envio}")

    if arquivo is not None:
        previa = D.analisar_entrada(arquivo, df)
        if previa.erro:
            st.error(previa.erro)
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Linhas novas", num(len(previa.novas)))
            c2.metric("Já existentes", num(len(previa.duplicadas)))
            c3.metric("Cotações novas", num(len(previa.cotacoes_novas)))

            if previa.log_limpeza:
                with st.expander("O que as regras de limpeza fizeram neste arquivo"):
                    for linha in previa.log_limpeza:
                        st.write("- " + linha)

            if previa.cotacoes_novas:
                st.caption("Cotações novas: " +
                           ", ".join(str(x) for x in previa.cotacoes_novas))
            if previa.cotacoes_existentes:
                st.caption("Cotações que já existem na base: " +
                           ", ".join(str(x) for x in previa.cotacoes_existentes))

            if previa.ok:
                # as mesmas validações do cadastro manual: um arquivo com pedido de
                # outro fornecedor, código com outro EAN ou datas trocadas não entra
                from core import cadastro as CD
                validacao = CD.validar(previa.novas, df)
                if validacao.erros or validacao.avisos:
                    (st.error if validacao.erros else st.warning)(
                        f"{len(validacao.erros)} erro(s) e {len(validacao.avisos)} aviso(s) "
                        "nas linhas novas." + (" Corrija o arquivo: com erro, nada é gravado."
                                               if validacao.erros else ""))
                    st.dataframe(validacao.tabela(), hide_index=True, width="stretch",
                                 height=min(320, 40 + 35 * (len(validacao.erros) +
                                                            len(validacao.avisos))))
                st.markdown("**Prévia das linhas que serão incluídas**")
                st.dataframe(previa.novas.head(200), width="stretch", hide_index=True)
                if st.button("Confirmar inclusão", type="primary",
                             disabled=not validacao.ok):
                    nova = D.mesclar(df, previa.novas)
                    st.session_state["aviso_base"] = (
                        f"{num(len(nova) - len(df))} linhas incluídas. A base agora tem "
                        f"{num(len(nova))} linhas, e todas as telas já usam os dados novos.")
                    st.session_state["envio_n"] = envio + 1
                    return nova
            else:
                st.info("Nenhuma linha nova: todas as do arquivo já estão na base.")

    st.subheader("Versões anteriores")
    versoes = D.versoes_anteriores()
    if not versoes:
        st.caption("Nenhuma inclusão feita ainda. A cada inclusão, uma cópia da base "
                   "anterior é guardada aqui.")
    else:
        escolha = st.selectbox("Cópia guardada", [v.name for v in versoes])
        if st.button("Restaurar esta versão"):
            alvo = next(v for v in versoes if v.name == escolha)
            nova = D.restaurar_versao(alvo)
            st.session_state["aviso_base"] = (f"Base restaurada para {escolha} — "
                                              f"{num(len(nova))} linhas.")
            return nova

    st.subheader("Exportar")
    bruto = df.drop(columns=[c for c in D.COLUNAS_DERIVADAS if c in df.columns])
    st.download_button("Baixar base consolidada (CSV)",
                       bruto.to_csv(index=False, sep=";", decimal=",")
                            .encode("utf-8-sig"),
                       file_name="base_consolidada.csv", mime="text/csv")
    return None

# ===========================================================================
#                             CADASTRO MANUAL
# ===========================================================================
NOVO_FORNECEDOR = "➕ Novo fornecedor"
NOVO_PRODUTO = "➕ Novo produto"
NOVA_COTACAO = "➕ Nova cotação"


def _ultimo(df: pd.DataFrame, coluna: str, valor) -> pd.Series | None:
    """Última linha comprada com aquele valor (fornecedor ou produto), para sugerir dados."""
    linhas = df[df[coluna].astype(str) == str(valor)]
    return linhas.sort_values("dt").iloc[-1] if len(linhas) else None


def _cadastro_manual(df: pd.DataFrame) -> pd.DataFrame | None:
    """Inclusão de um pedido digitado na tela, com as colunas do modelo de importação.

    Os campos do pedido valem para todos os itens; cada item é acrescentado a um
    rascunho; a gravação só é liberada sem erros e segue o mesmo caminho da
    importação (cópia da base anterior em dados/historico/).
    """
    from core import cadastro as CD
    from core.tema import linha_cartoes
    st.caption("Para registrar uma compra sem planilha: os campos seguem o modelo de importação, "
               "os dados conhecidos de fornecedor e produto vêm preenchidos da última compra, e "
               "o pedido só é gravado depois de passar pelas validações.")
    itens: list[dict] = st.session_state.setdefault("man_itens", [])

    # -------------------------------------------------------- 1. pedido
    st.subheader("1. Pedido")
    c1, c2, c3 = st.columns(3)
    cotacoes = sorted(D.texto_chave(df["Cotação"]).unique(), key=lambda x: -int(x))
    escolha_cot = c1.selectbox("Cotação", [NOVA_COTACAO] + cotacoes, key="man_cot_sel")
    if escolha_cot == NOVA_COTACAO:
        numero_cot = c1.number_input("Número da nova cotação", min_value=1, step=1, value=None,
                                     key="man_cot_num", placeholder="ex.: 12200999")
        data_cot = c2.date_input("Data da cotação", format="DD/MM/YYYY", key="man_cot_data")
        serial_cot = CD.para_serial(data_cot)
    else:
        numero_cot = int(escolha_cot)
        serial_cot = float(df.loc[D.texto_chave(df["Cotação"]) == escolha_cot,
                                  "Data de Criação"].iloc[0])
        c2.date_input("Data da cotação", value=D._para_data(pd.Series([serial_cot])).iloc[0],
                      format="DD/MM/YYYY", disabled=True, key=f"man_cot_data_{escolha_cot}")
    numero_ped = c3.number_input("Número do pedido", min_value=1, step=1, value=None,
                                 key="man_ped", placeholder="ex.: 52499999")

    f1, f2, f3 = st.columns(3)
    fornecedores = D.opcoes(df, "Nome do Fornecedor")
    escolha_forn = f1.selectbox("Fornecedor", fornecedores + [NOVO_FORNECEDOR], key="man_forn")
    ult = _ultimo(df, "Nome do Fornecedor", escolha_forn)
    if escolha_forn == NOVO_FORNECEDOR:
        nome_forn = f1.text_input("Nome do novo fornecedor", key="man_forn_nome").strip()
        cnpj = f2.text_input("CNPJ", key="man_cnpj_novo", placeholder="00.000.000/0000-00")
    else:
        nome_forn = escolha_forn
        cnpj = f2.text_input("CNPJ", key=f"man_cnpj_{escolha_forn}",
                             value=str(int(ult["CNPJ Fornecedor"])).zfill(14))
    representante = f3.text_input("Representante", key=f"man_rep_{escolha_forn}",
                                  value="" if ult is None else str(ult["Representante"]))
    g1, g2, g3 = st.columns(3)
    prazo_padrao = 30 if ult is None else int(re.sub(r"\D", "", str(ult["Prazo de Pagamento"])) or 30)
    prazo = g1.number_input("Prazo de pagamento (dias)", min_value=0, max_value=365, step=1,
                            value=prazo_padrao, key=f"man_prazo_{escolha_forn}")
    fat_min = g2.number_input("Faturamento mínimo (R$)", min_value=0.0, step=50.0,
                              value=0.0 if ult is None else float(ult["Faturamento Mínimo"]),
                              key=f"man_fmin_{escolha_forn}")
    status = g3.selectbox("Status do pedido", CD.STATUS_CONHECIDOS, key="man_status",
                          help="Só pedidos 'Faturado' entram na análise.")
    pedido = {"Cotação": numero_cot, "Pedido": numero_ped, "Status do Pedido": status,
              "Data de Criação": serial_cot,
              "CNPJ Fornecedor": int(re.sub(r"\D", "", cnpj)) if re.sub(r"\D", "", cnpj) else None,
              "Nome do Fornecedor": nome_forn or None, "Representante": representante.strip(),
              "Prazo de Pagamento": prazo, "Faturamento Mínimo": fat_min}

    # --------------------------------------------------------- 2. itens
    st.subheader("2. Itens")
    produtos = (df.sort_values("dt").drop_duplicates("sku", keep="last")
                  .sort_values("Descrição do Produto"))
    nomes = dict(zip(produtos["sku"], produtos["Descrição do Produto"]))
    escolha_prod = st.selectbox("Medicamento", [NOVO_PRODUTO] + produtos["sku"].tolist(),
                                key="man_prod",
                                format_func=lambda s: s if s == NOVO_PRODUTO
                                else f"{nomes[s]} · código {s}",
                                help="Digite para buscar. Os dados do produto vêm do cadastro.")
    up = None if escolha_prod == NOVO_PRODUTO else produtos.set_index("sku").loc[escolha_prod]
    with st.form("man_item", clear_on_submit=True, border=True):
        if up is None:
            n1, n2, n3 = st.columns(3)
            codigo = n1.text_input("Código do produto")
            ean = n2.text_input("EAN (código de barras)")
            descricao = n3.text_input("Descrição do produto")
            n4, n5, n6, n7 = st.columns([1.3, 1.3, 1.3, 0.6])
            fabricante = n4.text_input("Fabricante")
            forma = n5.selectbox("Forma farmacêutica", D.opcoes(df, "Forma Farmacêutica"))
            categoria = n6.selectbox("Categoria comercial", D.opcoes(df, "Categoria Comercial"))
            ml = n7.selectbox("M/L", ["M", "L"])
        else:
            codigo, ean = escolha_prod, str(int(up["EAN"]))
            descricao, fabricante = up["Descrição do Produto"], up["Fabricante"]
            forma, categoria, ml = up["Forma Farmacêutica"], up["Categoria Comercial"], up["M/L"]
            st.caption(f"**{descricao}** · EAN {ean} · {fabricante} · {forma} · {categoria} · "
                       f"última compra a {brl(up['Vl. Custo (R$)'])}")
        q1, q2, q3, q4, q5 = st.columns(5)
        qtd_cot = q1.number_input("Qtde. cotada", min_value=0, step=1, value=1)
        qtd_resp = q2.number_input("Qtde. respondida", min_value=0, step=1, value=1)
        qtd_ped = q3.number_input("Qtde. pedida", min_value=0, step=1, value=1)
        qtd_fat = q4.number_input("Qtde. faturada", min_value=0, step=1, value=1)
        desconto = q5.number_input("Desconto (%)", min_value=0.0, max_value=100.0, step=5.0)
        v1, v2, v3 = st.columns(3)
        custo = v1.number_input("Custo unitário (R$)", min_value=0.0, step=0.01, format="%.2f",
                                value=0.0 if up is None else float(up["Vl. Custo (R$)"]))
        faturado = v2.number_input("Valor faturado unitário (R$)", min_value=0.0, step=0.01,
                                   format="%.2f", value=0.0,
                                   help="Deixe 0 para usar o custo (como em toda a base atual).")
        preco = v3.number_input("Preço de venda (R$)", min_value=0.0, step=0.01, format="%.2f",
                                value=0.0 if up is None
                                else float(up["Preço de Venda Unitário (R$)"]))
        l1, l2, l3 = st.columns(3)
        lote = l1.text_input("Lote")
        fabricacao = l2.date_input("Fabricação", value=None, format="DD/MM/YYYY")
        validade = l3.date_input("Validade", value=None, format="DD/MM/YYYY")
        if st.form_submit_button("Adicionar item ao pedido", icon=":material/add:"):
            itens.append({
                "Código do Produto": str(codigo).strip(),
                "EAN": int(re.sub(r"\D", "", ean)) if re.sub(r"\D", "", str(ean)) else None,
                "Descrição do Produto": str(descricao).strip(), "Fabricante": str(fabricante).strip(),
                "Forma Farmacêutica": forma, "Categoria Comercial": categoria, "M/L": ml,
                "Qtde. Cot": int(qtd_cot), "Qtde. Resp": int(qtd_resp), "Qtde. Ped.": int(qtd_ped),
                "Qtde. Fat.": int(qtd_fat), "Desc. Com. (%)": float(desconto),
                "Vl. Custo (R$)": float(custo) or None,
                "Vl. Faturado (R$)": float(faturado) or None,
                "Preço de Venda Unitário (R$)": float(preco) or None,
                "Lote": lote.strip(), "Data de Fabricação": fabricacao, "Data de Validade": validade})
            st.rerun()

    if not itens:
        st.info("Nenhum item no rascunho. Escolha o medicamento, preencha os campos e clique em "
                "*Adicionar item ao pedido*.")
        return None

    # ----------------------------------------------- 3. revisar e gravar
    linhas = CD.montar_linhas(pedido, itens)
    validacao = CD.validar(linhas, df)
    st.subheader("3. Revisar e gravar")
    linha_cartoes([
        ("Itens no rascunho", num(len(linhas)), f"pedido {numero_ped or '—'}", "destaque"),
        ("Valor pedido", brl(pd.to_numeric(linhas["Qtde. Ped. x Vl. Custo (R$)"]).sum()),
         "quantidade pedida × custo"),
        ("Erros", num(len(validacao.erros)), "impedem a gravação"),
        ("Avisos", num(len(validacao.avisos)), "não impedem, mas confira"),
    ], colunas=4)
    if validacao.erros or validacao.avisos:
        st.dataframe(validacao.tabela(), hide_index=True, width="stretch")
    previa = linhas.assign(**{"Data de Criação": D._para_data(linhas["Data de Criação"]),
                              "Data de Fabricação": D._para_data(linhas["Data de Fabricação"]),
                              "Data de Validade": D._para_data(linhas["Data de Validade"])})
    st.dataframe(previa[["linha_origem", "Descrição do Produto", "Código do Produto", "Lote",
                         "Qtde. Ped.", "Qtde. Fat.", "Vl. Custo (R$)",
                         "Qtde. Ped. x Vl. Custo (R$)", "Data de Validade",
                         "Faixa de Recebimento"]].rename(columns={"linha_origem": "Linha"}),
                 hide_index=True, width="stretch", column_config={
                     "Data de Validade": st.column_config.DateColumn(format="DD/MM/YYYY"),
                     "Vl. Custo (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                     "Qtde. Ped. x Vl. Custo (R$)": st.column_config.NumberColumn(
                         format="R$ %.2f")})
    b1, b2, b3 = st.columns([1.2, 1.2, 2])
    remover = b1.selectbox("Remover a linha", [None] + list(range(1, len(itens) + 1)),
                           key="man_remover", format_func=lambda x: "—" if x is None else str(x))
    if b1.button("Remover", disabled=remover is None, key="man_btn_remover"):
        itens.pop(remover - 1)
        st.rerun()
    if b2.button("Limpar o rascunho", key="man_limpar", icon=":material/delete:"):
        itens.clear()
        st.rerun()
    if b3.button("Gravar na base", type="primary", disabled=not validacao.ok,
                 icon=":material/save:", key="man_gravar"):
        nova = D.mesclar(df, linhas)
        st.session_state["aviso_base"] = (
            f"Pedido {numero_ped} gravado: {num(len(nova) - len(df))} linha(s) incluída(s). "
            "Todas as telas já usam os dados novos; a base anterior foi guardada em Versões "
            "anteriores.")
        itens.clear()
        return nova
    if not validacao.ok:
        st.caption("Corrija os erros acima (no pedido ou removendo e incluindo o item de novo) "
                   "para liberar a gravação.")
    return None
