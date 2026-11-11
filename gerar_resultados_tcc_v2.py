"""
Relatório 2 dos resultados do SADPF (Word), para comparar com o relatório 1.

    python gerar_resultados_tcc_v2.py

Saídas (em relatorio_2/):
    SADPF_Resultados_TCC_v2.docx   diagnóstico de suficiência, resultados detalhados,
                                   limitações e plano para transformar o sistema em produto
    figuras/*.png                  gráficos (os do relatório 1 e os novos desta versão)
    telas/*.png                    capturas do painel (as do relatório 1 e as novas)

Usa as mesmas funções e figuras do relatório 1 (gerar_resultados_tcc.py), para que
as duas versões sejam comparáveis; se as figuras do relatório 1 não existirem, ele
é gerado antes. Requer kaleido/playwright e python-docx (requirements-relatorio.txt).
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import gerar_resultados_tcc as R1
from gerar_resultados_tcc import brl, mes, num, pct
from core import dados as D
from core import decisao as Dc
from core import metricas as M
from core import movimentacao as MV
from core import previsao as PV
from core.parametros import Parametros
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

RAIZ = Path(__file__).parent
SAIDA = RAIZ / "relatorio_2"
FIG, TELAS = SAIDA / "figuras", SAIDA / "telas"
FIG1, TELAS1 = R1.FIG, R1.TELAS
C = R1.C
FONTE_OBS, FONTE_SIM = R1.FONTE_OBS, R1.FONTE_SIM
CAP = "Fonte: captura do sistema (fornecedores codificados)."


def gini(valores) -> float:
    v = np.sort(np.asarray(valores, dtype=float))
    v = v[v > 0]
    n = len(v)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(v) / (n * v.sum())) if n else float("nan")


def preparar_pastas() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    TELAS.mkdir(parents=True, exist_ok=True)
    if not any(FIG1.glob("*.png")):
        R1.main()
    for arq in FIG1.glob("*.png"):
        shutil.copy2(arq, FIG / arq.name)
    for arq in TELAS1.glob("*.png"):
        if not (TELAS / arq.name).exists() or arq.stat().st_mtime > (TELAS / arq.name).stat().st_mtime:
            shutil.copy2(arq, TELAS / arq.name)
    R1.FIG = FIG                     # as figuras novas desta versão vão para relatorio_2/


def main() -> None:
    preparar_pastas()
    p = Parametros()
    base, _ = D.carregar_base()
    mapas = D.apelidos(base)
    df = D.anonimizar(base, mapas)
    mov = MV.anonimizar(MV.carregar(), mapas)
    rec = MV.recortar(mov)
    pos = MV.posicao(rec, p)
    res = MV.resumo(rec, pos)
    ind = M.indicadores(df)
    abc_c = M.curva_abc(df, p)
    abc_v = MV.curva_abc_vendas(pos, p)
    mv = MV.para_decisao(rec, mov, p)
    ins = Dc.gerar(df, abc_c, p, mv)
    ins_antes = Dc.gerar(df, abc_c, p)
    por_id = {i.id: i for i in ins}
    diag = Dc.diagnostico(ins, ind.valor_pedido)
    diag_antes = Dc.diagnostico(ins_antes, ind.valor_pedido)
    cl = abc_c.classes.set_index("classe")
    abc_7090 = M.curva_abc(df, Parametros(corte_a=0.70, corte_b=0.90))
    cl7 = abc_7090.classes.set_index("classe")
    unicas = int((abc_c.itens["compras"] == 1).sum())
    g = gini(abc_c.itens["valor"])
    serie = M.serie_mensal(df)
    cv_mensal = serie["valor_pedido"].std() / serie["valor_pedido"].mean()
    picos = serie.sort_values("valor_pedido", ascending=False).head(3)
    orc = PV.orcamento(df)
    conf = PV.resumo_confiabilidade(PV.confiabilidade(df, p))
    fx_ = conf["faixas"]
    pv = MV.previsao_vendas(rec)
    met = pv["metodos"].sort_values("erro_mediano")
    td = MV.teste_demanda(rec, p)
    pf = MV.projecao_fechamento(rec)
    pt = MV.ponte_estoque(rec)
    prop = MV.propostas_validade(rec, p)
    causas = MV.causas_perdas(rec, df).groupby("causa")["valor"].sum()
    lec = MV.lote_economico(pos, rec, p)
    forn = M.por_dimensao(df, "Nome do Fornecedor")
    funil = df[["Qtde. Cot", "Qtde. Resp", "Qtde. Ped.", "Qtde. Fat."]].sum()
    mapa = __import__("paginas.compras", fromlist=["mapa_financeiro"]).mapa_financeiro(ins, mv)
    ganhos = mapa[mapa["grupo"] == "Ganho possível"]
    fontes = [a.read_text(encoding="utf-8").splitlines()
              for padrao in ("app.py", "core/*.py", "paginas/*.py", "verificar.py")
              for a in RAIZ.glob(padrao)]
    linhas_codigo = sum(len(f) for f in fontes)
    linhas_uteis = sum(1 for f in fontes for linha in f
                       if linha.strip() and not linha.strip().startswith("#"))

    R = R1.Relatorio()
    # ------------------------------------------------------------------ capa
    t = R.doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_ = t.add_run("SADPF — Resultados do projeto (versão 2)")
    r_.bold = True
    r_.font.size = Pt(18)
    r_.font.color.rgb = RGBColor(0x23, 0x5A, 0x80)
    s = R.doc.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s.add_run("Diagnóstico de suficiência, resultados detalhados, limitações e caminho do "
              "protótipo ao produto").font.size = Pt(12.5)
    i_ = R.doc.add_paragraph()
    i_.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_ = i_.add_run(f"Gerado em {date.today():%d/%m/%Y} por gerar_resultados_tcc_v2.py · "
                    "compare com relatorio/resultados_tcc/SADPF_Resultados_TCC.docx (versão 1)")
    r_.font.size = Pt(10)
    r_.italic = True
    R.p("Esta versão parte da primeira (mesmos números, figuras e capturas) e acrescenta "
        "quatro partes: (I) uma verificação de que as informações reunidas bastam para o "
        "capítulo de Resultados do TCC, comparando o texto da versão para a banca com o sistema "
        "atual; (II) a redação detalhada dos resultados, em registro acadêmico, pronta para "
        "adaptar; (III) as limitações, com o efeito de cada uma e o que a resolveria; e (IV) o "
        "que seria preciso para transformar o SADPF em um produto usado por farmácias. Os "
        "números vêm do código do sistema, com fornecedores codificados, e cada resultado é "
        "marcado como observado (cotações reais) ou simulado (vendas do livro de movimentação).",
        "Como ler.")
    R.h2("Sumário")
    R.sumario()
    R.quebra()

    # ================================================================= PARTE I
    R.h1("Parte I — As informações bastam para os resultados?")
    R.p("A verificação comparou três fontes: os objetivos e a questão de pesquisa do TCC "
        "(versão para a banca final), o capítulo de Resultados já escrito e o que o sistema "
        "produz hoje. O critério foi: cada objetivo precisa de pelo menos um número medido, uma "
        "figura ou tabela que o mostre e uma leitura crítica (o que o número significa e até "
        "onde vale).")
    R.h2("1.1 Objetivos específicos × evidências disponíveis")
    obj = [
        ("a) Organizar e estruturar a base de pedidos",
         f"{num(ind.linhas)} linhas válidas de 1.739 (82 removidas por status); chave sem "
         f"duplicidade; histórico de versões; cadastro manual com validações",
         "seções 2.1 e 2.2", "Suficiente"),
        ("b) Aplicar a Curva ABC",
         f"A = {num(cl.loc['A', 'itens'])} itens / {pct(cl.loc['A', 'pct_valor'])} do valor; "
         f"Pareto 20% = {pct(abc_c.concentracao_20)}; Gini {num(g, 3)}; critério 70/90",
         "seção 2.3 (Pareto, classes, cortes)", "Suficiente"),
        ("c) Frequência e regularidade das compras",
         f"{num(unicas)} itens comprados uma única vez ({pct(unicas / abc_c.n)}); XYZ pelas "
         f"compras (935 Z) e pelas vendas (41 X, 200 Y, 526 Z)",
         "seção 2.4 (matriz, exemplo AX × AZ)", "Suficiente (XYZ por vendas é simulado)"),
        ("d) Impacto financeiro de itens, fornecedores e condições",
         f"economia {brl(diag['economia'])} ({pct(diag['economia'] / ind.valor_pedido)}); maior "
         f"fornecedor {pct(forn['valor_pedido'].iloc[0] / ind.valor_pedido)}; prazo, margem, validade",
         "seções 2.5 a 2.7", "Suficiente com ressalva (margem e validade "
         "dependem de campos a confirmar)"),
        ("e) Painel interativo", "16 telas, filtros globais, privacidade, tema escuro, celular",
         "seção 2.1 e apêndice (16 capturas)", "Suficiente"),
        ("f) Recomendações priorizadas pelo impacto",
         f"{len(diag['acionaveis'])} pontos acionáveis no plano de ação, réguas ajustáveis, "
         f"nova leitura comparada", "seção 2.7 (plano de ação, réguas, nova leitura)", "Suficiente"),
        ("Questão de pesquisa",
         "o sistema organiza, prioriza e recomenda; ganhos estimados em reais",
         "Discussão (seção 2.13)", "Suficiente, exceto efeito nas decisões reais (falta "
         "validação com a gestora)"),
    ]
    R.tabela(pd.DataFrame(obj, columns=["Objetivo", "Evidência (número-chave)", "Onde está",
                                        "Situação"]),
             "Objetivos do TCC e as evidências que os sustentam", FONTE_SIM,
             larguras=[3.6, 6.2, 3.2, 3.2])
    R.h2("1.2 O que o texto da banca diz × o que o sistema faz hoje")
    R.p("O capítulo de Resultados do TCC foi escrito antes das últimas versões do sistema. Os "
        "números abaixo estão desatualizados no texto e devem ser substituídos pelos atuais, "
        "senão a banca encontrará diferenças entre o documento e a demonstração.")
    res_ref = MV.referencias(rec, pos, res, abc_v, p)
    diverg = [
        ("Número de telas", "14 telas (inclui \"Gestão de Estoque\")",
         "16 telas; grupo Movimentação com Posição de Estoque, Reposição e Lotes e Validade e "
         "Remarcação", "Atualizar 5.1 e a Figura 10"),
        ("Pontos do motor de decisão", "21 pontos em 6 assuntos",
         f"{len(ins_antes)} só com cotações; {len(ins)} com o livro de movimentação",
         "Citar os dois números e explicar a diferença"),
        ("Diagnóstico", "7 críticos, 6 atenção, 6 saudáveis, 2 informativos",
         " · ".join(f"{diag['contagem'][k]} {Dc.PLURAL[k].lower()}" for k in ("crit", "aten", "ok", "info"))
         + " (com movimentação)", "Manter o de 21 pontos se o texto falar só de cotações"),
        ("Roteiro de verificação", "13 blocos", "16 blocos (cores, coerência entre telas, "
         "movimentação, cadastro manual)", "Atualizar 4.7, 5.10 e o Quadro 5"),
        ("Recortes de filtro testados", "43 recortes", "74 recortes × 21 telas; 545 conferências",
         "Atualizar 4.7 e 5.10"),
        ("Movimentação", "módulo à parte do painel", "integrada ao menu; propostas calculadas "
         "pelo próprio sistema", "Reescrever 5.9 como parte do sistema"),
        ("Giro e cobertura medianos", "2,75 vezes; 98 dias",
         f"{num(res['giro_mediano'], 2)} vezes; {num(res['cobertura_mediana'])} dias (cálculo do "
         f"sistema, por produto)", "Usar os valores do sistema e conferir de onde vieram os do "
         "texto (método ou recorte diferente)"),
        ("Propostas por lote", "188 propostas, 72 remarcações (arquivo do gerador)",
         f"{len(prop)} lotes; " + ", ".join(f"{n} {a.lower()}" for a, n in prop['acao'].value_counts().head(2).items()),
         "Usar as do sistema (calculadas para qualquer recorte)"),
        ("Linhas de código", "cerca de 5.900",
         f"cerca de {num(round(linhas_codigo, -2))} no total; {num(round(linhas_uteis, -2))} sem "
         f"linhas vazias e comentários", "Atualizar 4.6 dizendo qual contagem é usada"),
        ("Visão Geral", "dez indicadores e evolução mensal", "resultado do mês com comparativos, "
         "situação, cascata, prioridades e tendências", "Atualizar 5.1"),
        ("Figuras 13 e 14", "[Inserir aqui a captura…]", "capturas prontas neste relatório "
         "(plano de ação, Preferências, O que mudou)", "Usar as figuras da seção 2.7 deste "
         "documento"),
    ]
    R.tabela(pd.DataFrame(diverg, columns=["Item", "Texto da banca", "Sistema atual", "Ação"]),
             "Divergências entre o TCC e o sistema atual", "Fonte: TCC - Versão Banca Final.docx "
             "(19/10/2026) e execução do SADPF.", larguras=[3, 3.8, 5.2, 4.2])
    R.h2("1.3 O que só a equipe pode completar")
    R.lista([
        ("Autorização da farmácia:", "o texto tem \"[confirmar a forma da autorização]\" (seção "
         "4.3). Sem ela, a banca pode questionar o uso dos dados."),
        ("Origem dos campos de lote, validade e preço de venda:", "\"[Confirmar a origem desses "
         "campos junto à farmácia]\". Enquanto não houver confirmação, validade e margem ficam "
         "como demonstração, como o texto já faz."),
        ("Cronograma:", "\"[conferir os meses]\" na Tabela 2."),
        ("Validação com a gestora:", "nenhuma sessão de uso foi registrada. É a lacuna mais "
         "importante para a questão de pesquisa (efeito nas decisões reais); uma sessão de 1 hora "
         "com tarefas e um questionário SUS já daria uma evidência."),
    ])
    R.h2("1.4 Veredito")
    R.p("Sim: há informação suficiente para um capítulo de Resultados completo. Todos os seis "
        "objetivos específicos têm números medidos, figuras e tabelas, e a questão de pesquisa "
        "tem resposta sustentada. Três condições, porém, precisam ser cumpridas antes da entrega: "
        "(1) atualizar no texto os números da Tabela anterior, para que documento e demonstração "
        "coincidam; (2) manter explícito que os resultados de estoque, giro, perdas e XYZ pelas "
        "vendas vêm de vendas simuladas; e (3) registrar como limitação, ou realizar, a validação "
        "com a gestora. As pendências de autorização e de origem dos campos não impedem a "
        "redação, mas precisam de resposta da equipe.")
    R.quebra()

    # ================================================================= PARTE II
    R.h1("Parte II — Resultados detalhados")
    R.p("Os textos desta parte estão no registro do TCC e podem substituir ou complementar as "
        "seções do capítulo 5. Todos os números foram gerados pelo SADPF sobre a base tratada "
        "(30/10/2024 a 08/07/2026), com as réguas no padrão.", italico=True)

    R.h2("2.1 O sistema desenvolvido")
    R.p(f"O resultado principal é o SADPF, uma aplicação web em Python executada localmente e "
        f"acessada pelo navegador, com cerca de {num(round(linhas_uteis, -2))} linhas de código "
        f"(sem contar linhas vazias e comentários). "
        f"Depois do acesso por empresa, o sistema organiza-se em dezesseis telas, agrupadas em "
        f"Painel (Visão Geral), Compras (Gestão de Compras, Pedidos, Fornecedores, Medicamentos), "
        f"Movimentação (Posição de Estoque, Reposição e Lotes, Validade e Remarcação), Análise e "
        f"decisão (Curva ABC, Análises e Indicadores, Previsão de Compras, Sistema de Apoio à "
        f"Decisão) e Referência (Conceitos e Cálculos, Tutoriais, Preferências, Base de Dados). "
        f"Todas respondem aos mesmos filtros globais de período, fornecedor, categoria, forma "
        f"farmacêutica, medicamento, cotação e status.")
    R.p("A arquitetura segue o paradigma Dados–Modelos–Diálogo de Sprague e Carlson (1982). A "
        "camada de dados lê, trata, valida e versiona a base; a de modelos calcula indicadores, "
        "Curva ABC, XYZ, os pontos do apoio à decisão e as previsões; a de diálogo apresenta os "
        "resultados e recebe os ajustes do gestor. Como a camada de modelos não depende da "
        "interface, ela é testada sem abrir o navegador e pode ser reaproveitada por outra "
        "interface — característica decisiva para a evolução descrita na Parte IV.")
    arq_dmd = FIG / "a02_arquitetura_dmd.png"
    if not arq_dmd.exists():
        import gerar_arquitetura
        gerar_arquitetura.main()
    R.figura(arq_dmd, "Arquitetura do SADPF segundo o paradigma Dados–Modelos–Diálogo",
             "Fonte: elaboração própria, a partir do código do sistema.", 16)
    R.p("Na figura, cada caixa é um módulo do código e cada seta, uma dependência real: a "
        "seta cheia indica o sentido em que os dados seguem; a tracejada, uma gravação ou um "
        "ajuste feito pelo usuário. O núcleo do apoio à decisão (decisao.py) recebe os "
        "indicadores de metricas.py, os resultados de estoque e perdas de movimentacao.py e as "
        "réguas de parametros.py; a previsão (previsao.py) vai direto para as telas. A camada de "
        "modelos não importa o Streamlit — o que o verificar.py confere a cada versão —, de modo "
        "que a interface pode ser trocada sem reescrever os cálculos. A faixa de verificação "
        "atravessa as três camadas: o roteiro testa os modelos sem abrir a interface, e os "
        "testes de navegador testam o diálogo.")
    R.figura(TELAS / "t01_visao_geral.png", "Visão Geral: resultado do mês, situação do período "
             "e composição do resultado", CAP, 15.5)
    R.p("A Visão Geral responde, numa tela, quanto se compra e se vende, onde há dinheiro a "
        "ganhar ou em risco e o que resolver primeiro: compara o último mês fechado com o mês "
        "anterior e com o mesmo mês do ano anterior, mostra a situação do período, decompõe o "
        "resultado em cascata e lista as três prioridades do apoio à decisão.")

    R.h2("2.2 Perfil das compras")
    R.p(f"A base tratada soma {brl(ind.valor_pedido, 2)} em {num(ind.pedidos)} pedidos de "
        f"{num(ind.cotacoes)} cotações, com média de {brl(ind.media_mensal)} por mês em "
        f"{num(ind.meses)} meses com compra. O gasto mensal tem coeficiente de variação de "
        f"{num(cv_mensal, 2)}; os meses de maior desembolso foram "
        + ", ".join(f"{mes(r_['ano_mes'])} ({brl(r_['valor_pedido'])})" for _, r_ in picos.iterrows())
        + f". No outro extremo, {num(unicas)} dos {num(abc_c.n)} medicamentos "
        f"({pct(unicas / abc_c.n)}) foram comprados uma única vez. Essa cauda longa de compras "
        f"pontuais é a característica que mais influencia os resultados seguintes: ela achata a "
        f"Curva ABC, torna a maior parte dos itens irregular e limita a previsão item a item.")
    R.figura(FIG / "b02_classes.png", "Parcela de itens × parcela do valor por classe", FONTE_OBS, 14)

    R.h2("2.3 Curva ABC")
    R.p(f"Com cortes em {pct(p.corte_a, 0)} e {pct(p.corte_b, 0)} do valor acumulado, a classe A "
        f"reuniu {num(cl.loc['A', 'itens'])} dos {num(abc_c.n)} medicamentos "
        f"({pct(cl.loc['A', 'pct_itens'])}), responsáveis por {pct(cl.loc['A', 'pct_valor'])} do "
        f"valor; a classe B, {num(cl.loc['B', 'itens'])} itens e {pct(cl.loc['B', 'pct_valor'])}; "
        f"e a classe C, {num(cl.loc['C', 'itens'])} itens e {pct(cl.loc['C', 'pct_valor'])}.")
    R.figura(FIG / "b01_pareto.png", "Curva ABC (Pareto): compras observadas × vendas simuladas", FONTE_SIM)
    R.p(f"A concentração foi menor que a da literatura hospitalar. Em Nguyen et al. (2022), 5,85% "
        f"dos itens concentraram 79,6% do gasto; aqui, os 20% maiores itens somam "
        f"{pct(abc_c.concentracao_20)} do valor e são necessários {pct(cl.loc['A', 'pct_itens'])} "
        f"dos itens para chegar a 80%. O coeficiente de Gini da distribuição do valor por item é "
        f"{num(g, 3)}: desigualdade alta, mas longe da concentração extrema que o padrão 80/20 "
        f"supõe — resultado próximo ao de Pontes (2013), que precisou de 19% a 27% dos itens. A "
        f"explicação é a cauda longa de compras únicas, que espalha o valor por muitos itens.")
    R.p(f"Por isso a Curva ABC precisa ser lida junto da recorrência. Dos itens A, "
        f"{por_id['a4'].valor if 'a4' in por_id else '—'} são também comprados com frequência e "
        f"formam a prioridade máxima da gestão; outros {por_id['a5'].valor if 'a5' in por_id else '—'} "
        f"estão na classe A pelo valor de uma única compra. O sistema permite testar cortes "
        f"alternativos:")
    R.tabela(pd.DataFrame([
        ("80/95 (padrão)", num(cl.loc["A", "itens"]), pct(cl.loc["A", "pct_itens"]),
         pct(cl.loc["A", "pct_valor"]), num(cl.loc["A", "pct_valor"] / cl.loc["A", "pct_itens"], 2)),
        ("70/90", num(cl7.loc["A", "itens"]), pct(cl7.loc["A", "pct_itens"]),
         pct(cl7.loc["A", "pct_valor"]), num(cl7.loc["A", "pct_valor"] / cl7.loc["A", "pct_itens"], 2)),
    ], columns=["Critério", "Itens A", "% dos itens", "% do valor", "Seletividade"]),
        "Efeito do critério de corte sobre a classe A", FONTE_OBS, larguras=[3.5, 2.5, 3, 3, 3])
    R.p(f"Com o critério 70/90, a classe A cai para {num(cl7.loc['A', 'itens'])} itens, com perda "
        f"de cerca de dez pontos percentuais de valor, e a seletividade (participação no valor ÷ "
        f"participação nos itens) sobe — um foco mais adequado ao acompanhamento item a item numa "
        f"farmácia pequena. Pelas vendas simuladas, a curva tem forma semelhante (Spearman 0,91 "
        f"entre as posições), e o cruzamento compras × vendas aponta itens com dinheiro parado e "
        f"itens que não podem faltar.")
    R.figura(FIG / "b03_matriz_compras_vendas.png", "Classe nas compras × nas vendas", FONTE_SIM, 13)

    R.h2("2.4 Regularidade da demanda (XYZ e matriz ABC × XYZ)")
    R.p("Pelas compras trimestrais, 935 itens foram classificados como Z, 25 como Y e nenhum "
        "como X: a farmácia compra a maior parte do seu valor de forma não programada, padrão de "
        "demanda intermitente descrito por Syntetos, Boylan e Croston (2005). Medida pelas "
        "vendas mensais do livro de movimentação, a regularidade aparece: 41 itens X, 200 Y e 526 "
        "Z. A diferença mostra que o ritmo de compra não revela o ritmo de consumo — e que, com "
        "dados de venda, a política de reposição pode ser diferenciada por quadrante.")
    R.figura(FIG / "c02_matriz_abc_xyz.png", "Matriz ABC × XYZ pelas vendas", FONTE_SIM, 14.5)
    R.figura(FIG / "c03_exemplo_ax_az.png", "Vendas de um item AX e de um AZ em relação à média", FONTE_SIM)
    R.p("Os itens AX (27) podem ter reposição automática com estoque de segurança pequeno; os "
        "AY (114, 40% do faturamento) pedem segurança maior; os AZ (103) exigem acompanhamento "
        "próximo, porque um estoque calculado pela média ficaria ora em falta, ora sobrando; e "
        "os CZ (246) são candidatos a compra sob encomenda.")

    R.h2("2.5 Fornecedores, preços e condições comerciais")
    R.p(f"O maior fornecedor concentrou {pct(forn['valor_pedido'].iloc[0] / ind.valor_pedido)} do "
        f"valor comprado, acima do limite de 40% adotado como crítico, o que coloca "
        f"{brl(por_id['f1'].impacto)} acima desse limite e reduz o poder de negociação. A "
        f"comparação do custo de um mesmo item entre fornecedores indicou economia potencial de "
        f"{brl(por_id['o1'].impacto)} se as compras tivessem sido feitas pelo menor custo "
        f"registrado (sem considerar frete, faturamento mínimo e disponibilidade); itens com "
        f"diferença de preço superior a três vezes foram tratados como indício de erro de cadastro "
        f"e excluídos desse cálculo. O prazo médio de pagamento ponderado foi de "
        f"{por_id['f5'].valor}, e {por_id['m1'].valor} tiveram alta de custo acima da régua, "
        f"embora a inflação da cesta recorrente tenha sido de apenas {por_id['m3'].valor} — altas "
        f"concentradas em poucos produtos.")

    R.h2("2.6 Validade dos lotes")
    R.p(f"Comparando o último lote recebido de cada medicamento com a data de referência, "
        f"{por_id['e1'].valor} estão vencidos ou vencem em até seis meses, somando "
        f"{brl(por_id['e1'].impacto)} em valor comprado. Como a base de cotações não registra "
        f"saídas, o indicador mede o risco associado à validade na entrada, e não o estoque físico "
        f"vencido; com o livro de movimentação, o sistema passa a medir a perda real "
        f"({brl(res['perda_valor'])}, {pct(res['perda_pct'])} do faturamento simulado) e a "
        f"propor, lote a lote, devolver, remarcar ou segregar.")

    R.h2("2.7 Sistema de apoio à decisão")
    R.p(f"O motor de decisão avalia {len(ins_antes)} pontos com a base de cotações e "
        f"{len(ins)} quando o livro de movimentação está disponível. Cada ponto compara um "
        f"indicador a uma régua ajustável, recebe um valor em reais, uma gravidade proporcional "
        f"a esse valor sobre o total comprado e uma ação sugerida. Com a movimentação, o "
        f"diagnóstico resultou em "
        + ", ".join(f"{diag['contagem'][k]} {Dc.PLURAL[k].lower()}" for k in ("crit", "aten", "ok", "info"))
        + f", com economia direta de {brl(diag['economia'])} "
        f"({pct(diag['economia'] / ind.valor_pedido)} do valor comprado).")
    R.figura(FIG / "d02_valor_por_ponto.png", "Valor em reais dos pontos por gravidade", FONTE_SIM)
    R.figura(TELAS / "t08_apoio_pontos.png", "Plano de ação: decisões em ordem de impacto "
             "financeiro (substitui a Figura 13 do TCC)", CAP, 15.5)
    R.p("A reação às réguas e a dados novos foi verificada: cada ajuste em Preferências é salvo, "
        "recalcula todas as telas e gera uma nova leitura, que o sistema compara com a anterior e "
        "explica — por exemplo, ao voltar a janela de validade de 12 para 6 meses, o ponto "
        "\"Validade dos lotes recebidos\" passa de 573 para 329 itens.")
    R.figura(TELAS / "t15_preferencias.png", "Réguas em Preferências, com o valor padrão e o "
             "efeito atual (substitui parte da Figura 14 do TCC)", CAP, 15.5)
    R.figura(TELAS / "t16_o_que_mudou.png", "Leitura do apoio à decisão e o quadro \"O que mudou "
             "desde a leitura anterior\" (substitui parte da Figura 14 do TCC)", CAP, 15.5)
    R.figura(FIG / "d03_cascata_resultado.png", "Composição do resultado com os ganhos estimados", FONTE_SIM)
    R.p(f"As ações sugeridas — trocar de fornecedor, renegociar custos e devolver ou remarcar "
        f"lotes — somam {brl(ganhos['valor'].sum())} estimados, que elevariam o resultado do "
        f"período de {brl(res['margem'] - res['perda_valor'])} para "
        f"{brl(res['margem'] - res['perda_valor'] + ganhos['valor'].sum())}.")

    R.h2("2.8 Previsão de compras e de vendas")
    R.p(f"Todas as previsões foram testadas no histórico antes de entrar no sistema. O valor do "
        f"mês de compras, previsto pela média do histórico, teve erro mediano de "
        f"{pct(orc['erro_mediano'])}, e o gasto real ficou dentro da faixa média ± desvio em "
        f"{pct(orc['acerto_faixa'])} dos {len(orc['teste'])} meses testados; para agosto de 2026 a "
        f"faixa vai de {brl(orc['faixa_min'])} a {brl(orc['faixa_max'])}. A previsão item a item é "
        f"fraca: {pct(conf['itens_novos'])} dos itens de cada mês nunca tinham sido comprados, e a "
        f"faixa de chance alta confirmou-se em {pct(fx_.loc['alta', 'taxa'])} dos casos, contra "
        f"{pct(fx_.loc['baixa', 'taxa'])} na baixa — a ordenação funciona, o nível de acerto não "
        f"basta para gerar pedido automático.")
    R.figura(FIG / "e02_backtest_orcamento.png", "Teste no histórico do orçamento mensal", FONTE_OBS)
    R.p(f"Pelas vendas (simuladas), o faturamento mensal é bem mais previsível: o método "
        f"\"{pv['melhor']}\" teve o menor erro ({pct(met.iloc[0]['erro_mediano'])}), à frente das "
        f"médias móveis e do mesmo mês do ano anterior. A projeção de fechamento de "
        f"{mes(pf['mes'])} é de {brl(pf['curso']['vendas'])} e a de {mes(pf['proximo_mes'])}, "
        f"{brl(pf['proximo']['vendas'])}. Item a item, o erro da demanda de 30 dias (WAPE) é de "
        f"{pct(td['wape'].mean())}, típico de itens de venda baixa e irregular; por isso a "
        f"reposição usa estoque de segurança proporcional à variabilidade. O resultado está de "
        f"acordo com Armstrong e Green (2005): com poucos dados, métodos simples tiveram o melhor "
        f"desempenho medido.")
    R.figura(FIG / "e04_metodos_vendas.png", "Erro de cada método de previsão do faturamento", FONTE_SIM, 14)

    R.h2("2.9 Estoque, reposição e perdas (base simulada)")
    leit = lec["leitura"].value_counts()
    R.p(f"Com o livro de movimentação, o estoque fecha centavo a centavo: partida de "
        f"{brl(pt['valor_inicial'])} + compras de {brl(pt['valor_entradas'])} − custo vendido de "
        f"{brl(pt['cmv'])} − perdas de {brl(pt['valor_perdas'])} = chegada de "
        f"{brl(pt['valor_final'])}. O giro do período foi de {num(pt['giro'], 2)} vezes e a "
        f"cobertura na chegada, de {num(pt['cobertura_final'])} dias — acima da referência de 30 a "
        f"60 dias, o que o sistema traduz como {brl(por_id['v2'].impacto)} de capital parado. "
        f"{num(leit.get('compra acima do lote econômico', 0))} produtos são comprados em lotes "
        f"acima do lote econômico de Harris (limitado pela validade), e as perdas por vencimento "
        f"({brl(res['perda_valor'])}) concentram-se no estoque de abertura "
        f"({brl(causas.get('Estoque de abertura', 0))}) e em fatores ligados à compra, como lote "
        f"maior que a venda até a validade ({brl(causas.get('Lote maior que a venda até a validade', 0))}).")
    R.figura(FIG / "f01_ponte_estoque.png", "Ponte do estoque a custo", FONTE_SIM)
    R.figura(FIG / "e08_dente_serra.png", "Dente de serra de um item com o ponto de pedido e o "
             "lote econômico", FONTE_SIM)
    R.p(f"Para os lotes que vencem nos próximos 180 dias, o sistema propõe a ação que mais recupera "
        f"valor: {len(prop)} lotes, dos quais " + ", ".join(
            f"{n} {a.lower()}" for a, n in prop["acao"].value_counts().items())
        + f", com {brl(prop['perda_evitada'].sum())} recuperáveis. As propostas respeitam o preço "
        f"máximo da CMED, a não divulgação de desconto para medicamentos sob prescrição e a "
        f"exclusão dos controlados. Todos os números desta seção dependem das vendas simuladas e "
        f"mostram como o sistema decide, não a situação da farmácia.")

    R.h2("2.10 Precisão dos pedidos")
    R.p(f"Das {num(funil['Qtde. Cot'])} unidades cotadas, {pct(funil['Qtde. Resp'] / funil['Qtde. Cot'], 2)} "
        f"foram respondidas pelos distribuidores; das pedidas, {pct(ind.nivel_atendimento)} foram "
        f"faturadas, e o valor faturado difere do pedido em "
        f"{pct(ind.valor_faturado / ind.valor_pedido - 1, 2)}. O atendimento de 100% é, porém, "
        f"consequência da regra que mantém só pedidos faturados: considerando os pedidos removidos, "
        f"o TCC registra atendimento de 96,1%, e os pedidos excluídos concentram os cortes de "
        f"entrega (20,9% de atendimento). Medir a precisão real dos pedidos exige uma base de "
        f"análise que inclua os status \"Faturado Parcialmente\" e \"Enviado\".")
    R.figura(FIG / "e01_funil_pedidos.png", "Unidades cotadas, respondidas, pedidas e faturadas", FONTE_OBS, 13)

    R.h2("2.11 Verificação")
    R.p("A correção do sistema foi verificada por quatro meios, todos automatizados e repetidos a "
        "cada mudança: o roteiro verificar.py, com 16 blocos; a execução das 21 telas em 74 "
        "recortes de filtro, com 545 conferências de soma e interseção; a conferência de que telas "
        "diferentes mostram os mesmos números em 14 recortes; e testes no navegador, incluindo "
        "celular, tema escuro e privacidade. Identidades contábeis fecham exatamente: a ponte do "
        "estoque tem diferença de R$ 0,00 e a soma das causas das perdas é igual à perda total.")
    R.p("A verificação também encontrou e permitiu corrigir defeitos reais, o que reforça seu "
        "valor: produtos que sumiam ao combinar categoria e período; erro de sazonalidade com um "
        "único medicamento; a coluna de atendimento que mostrava 1% em vez de 100%; a legenda dos "
        "gráficos encoberta pela barra de ferramentas; cores verde e vermelho indistinguíveis para "
        "daltonismo (distância de cor de 7,6, passada a 17,6); e uma preferência de privacidade "
        "que podia ficar ligada sem aviso quando o arquivo estava travado pela sincronização do "
        "OneDrive, corrigida com gravação em duas etapas, novas tentativas e aviso na tela.")

    R.h2("2.12 Atendimento aos objetivos")
    R.tabela(pd.DataFrame([(o, ev[:70] + ("…" if len(ev) > 70 else ""), sit) for o, ev, _, sit in obj],
                          columns=["Objetivo", "Como foi atendido", "Situação"]),
             "Atendimento aos objetivos específicos", FONTE_SIM, larguras=[4.2, 8, 3.8])

    R.h2("2.13 Discussão")
    R.p("Quatro leituras resumem os resultados. A primeira é sobre priorização: a Curva ABC, que "
        "na literatura hospitalar isola poucos itens de alto valor, mostrou-se achatada numa "
        "farmácia que compra por cotação, e só ganhou poder de decisão quando combinada à "
        "recorrência e à regularidade. A segunda é sobre recomendação: o motor de decisão "
        "transformou indicadores dispersos em uma lista curta de providências com valor em reais, "
        "respondendo à dificuldade dos gestores em interpretar os dados dos sistemas de gestão; a "
        "decisão final continua com o gestor, que pondera fatores ausentes da base, como frete e "
        "relação com o distribuidor.")
    R.p("A terceira é sobre previsão: prever o orçamento do mês é viável e útil para o caixa, "
        "prever quais itens serão comprados não é, e exibir as taxas de acerto ao lado da "
        "previsão evita atribuir-lhe uma precisão que ela não tem. A quarta é sobre dados: os "
        "indicadores clássicos de estoque (giro, cobertura, ruptura, ponto de pedido, lote "
        "econômico) já estão implementados e funcionam sobre o livro de movimentação, mas só "
        "medirão a farmácia quando receberem as vendas reais. Para pequenas farmácias, o ganho "
        "imediato está em organizar e priorizar os dados que já existem; o ganho seguinte depende "
        "mais de dados do que de modelos sofisticados.")
    R.quebra()

    # ================================================================ PARTE III
    R.h1("Parte III — Limitações")
    R.p("As limitações abaixo estão organizadas pelo efeito que têm sobre os resultados e pelo "
        "que as resolveria. Nenhuma invalida o sistema, mas cada uma delimita o que os números "
        "podem afirmar.")
    lim = [
        ("Dados", "A base registra compras, não vendas nem saldo",
         "Giro, cobertura, ruptura, perdas e XYZ por vendas dependem do livro simulado",
         "Livro de movimentação com origem marcada; texto separa observado e simulado",
         "Exportação de vendas do PDV/ERP ou XML das NFC-e"),
        ("Dados", "Origem de lote, validade e preço de venda não confirmada",
         "Validade e margem são demonstração, não medição", "Resultados marcados como tais",
         "Confirmar com a farmácia ou ler do XML da NF-e"),
        ("Dados", "Só pedidos faturados na base", "Atendimento de 100% por construção",
         "Limitação declarada", "Base de análise com todos os status"),
        ("Dados", "22 meses, uma farmácia", "Sem sazonalidade estimável; não generaliza",
         "Métodos simples, testados no histórico", "≥ 36 meses; outras farmácias"),
        ("Método", "Economia pelo menor custo registrado",
         "Ignora frete, faturamento mínimo e disponibilidade", "Valor marcado como estimado",
         "Incluir custos logísticos e mínimos por fornecedor"),
        ("Método", "Causas das perdas por associação", "Não prova causalidade",
         "Um fator por lote, critério explícito", "Registro do motivo na baixa"),
        ("Método", "Réguas com valores de referência", "Gravidade depende das réguas",
         "Réguas ajustáveis e documentadas", "Calibrar com a gestora"),
        ("Validação", "Sem uso pela gestora ao longo do tempo",
         "Efeito nas decisões reais não medido", "—", "Sessões de uso + SUS + piloto de 3 meses"),
        ("Sistema", "Execução local, arquivos CSV/JSON, poucos usuários",
         "Não atende várias lojas nem acesso remoto seguro", "Privacidade por códigos; senha com hash",
         "Banco de dados, HTTPS, login gerenciado (Parte IV)"),
        ("Sistema", "Pasta sincronizada pode travar arquivos",
         "Gravações podiam falhar sem aviso", "Gravação em duas etapas, novas tentativas e aviso",
         "Banco de dados no lugar dos arquivos"),
    ]
    R.tabela(pd.DataFrame(lim, columns=["Tipo", "Limitação", "Efeito nos resultados",
                                        "Como foi tratada", "O que resolveria"]),
             "Limitações do projeto", "Fonte: elaboração própria.",
             larguras=[1.6, 3.6, 3.6, 3.6, 3.8])
    R.p("A limitação mais relevante é a ausência de vendas reais: ela separa o que o TCC pode "
        "afirmar como medição da farmácia (compras, fornecedores, preços, Curva ABC, previsão do "
        "orçamento) do que demonstra como capacidade do sistema (estoque, giro, perdas, reposição "
        "e XYZ por vendas). A segunda é a ausência de validação de campo, que impede afirmar o "
        "efeito do sistema sobre as decisões reais de compra. Ambas têm solução conhecida e "
        "compõem o roteiro da Parte IV.")
    R.quebra()

    # ================================================================= PARTE IV
    R.h1("Parte IV — Do protótipo ao produto")
    R.p("Esta parte descreve o que seria preciso para que o SADPF deixasse de ser um sistema "
        "acadêmico, executado num computador, e passasse a ser um produto usado por farmácias de "
        "pequeno porte. Os valores de hospedagem e os tempos de desenvolvimento vêm do guia do "
        "código (seções 22 a 26 e 29) e são estimativas de ordem de grandeza.")
    R.h2("4.1 O que já está pronto")
    R.lista([
        "Regras de negócio independentes da interface (core/), testadas automaticamente: podem ser "
        "servidas por uma API sem reescrita.",
        "Importação de cotações com validação, chave sem duplicidade e histórico de versões; "
        "cadastro manual com dígitos verificadores de CNPJ e EAN.",
        "Livro de movimentação no layout que as vendas reais ocupariam: a troca de simulado por "
        "real não muda nenhum cálculo.",
        "Privacidade por padrão (fornecedores codificados), senha com hash, preferências por "
        "empresa.",
        "Documentação técnica, guia do código, 68 verbetes de conceitos e 14 roteiros de tutorial.",
    ])
    R.h2("4.2 O que falta para ser produto")
    falta = [
        ("Dados", "Planilhas enviadas à mão", "Entrada automática por XML de NF-e e vendas do PDV/NFC-e", "médio a alto"),
        ("Armazenamento", "CSV e JSON locais", "PostgreSQL, uma base por farmácia (multiempresa)", "médio"),
        ("Acesso", "Senha local, sem HTTPS", "Login gerenciado (OIDC), perfis, HTTPS, auditoria", "médio"),
        ("Hospedagem", "Computador da farmácia", "Servidor sempre ligado, backups, monitoramento", "baixo a médio"),
        ("Interface", "Streamlit (bom para poucos usuários)", "Manter na fase 1; avaliar Django ou React na escala", "baixo → alto"),
        ("Operação", "Uso assistido", "Implantação guiada, suporte, atualizações, termos de uso", "médio"),
        ("Validação", "Sem usuários reais", "Piloto com métricas e ajuste das réguas", "médio"),
    ]
    R.tabela(pd.DataFrame(falta, columns=["Área", "Hoje", "Necessário para produto", "Esforço"]),
             "Lacunas entre o protótipo e um produto", "Fonte: elaboração própria; esforço "
             "segundo o guia do código, seções 25 e 29.", larguras=[2.6, 4, 7, 2.4])

    R.h2("4.3 Arquitetura-alvo")
    fig = go.Figure()
    caixas = [
        (0.00, 0.60, 0.18, 0.98, "Entradas", "XML NF-e (SEFAZ)<br>Vendas PDV / NFC-e<br>Cotações<br>Cadastro manual", C["ink3"]),
        (0.23, 0.60, 0.43, 0.98, "Integração", "fila de importação<br>validação e<br>deduplicação<br>(regras atuais)", C["teal"]),
        (0.48, 0.60, 0.68, 0.98, "API (FastAPI)", "core/ atual:<br>ABC, XYZ, reposição,<br>26 pontos, previsão<br>tarefas agendadas", C["blue"]),
        (0.73, 0.60, 1.00, 0.98, "Aplicação", "telas (Streamlit na fase 1)<br>login OIDC · perfis<br>HTTPS · alertas<br>por e-mail", C["blue_d"]),
        (0.23, 0.08, 0.68, 0.45, "Dados e segurança", "PostgreSQL (uma base por farmácia) · backups diários<br>criptografia em repouso · registro de auditoria · LGPD", C["purple"]),
        (0.73, 0.08, 1.00, 0.45, "Operação", "monitoramento · testes automáticos<br>(verificar.py) a cada versão<br>suporte e implantação", C["green"]),
    ]
    for x0, y0, x1, y1, tit_, txt, cor in caixas:
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1, line=dict(color=cor, width=2),
                      fillcolor=cor + "18", layer="below")
        fig.add_annotation(x=(x0 + x1) / 2, y=y1 - 0.06, text=f"<b>{tit_}</b>", showarrow=False,
                           font=dict(size=14, color=cor))
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2 - 0.04, text=txt, showarrow=False,
                           font=dict(size=11.5, color=C["ink"]))
    for xa, xb in ((0.18, 0.23), (0.43, 0.48), (0.68, 0.73)):
        fig.add_annotation(x=xb, y=0.79, ax=xa, ay=0.79, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowsize=1.4, arrowwidth=2,
                           arrowcolor=C["ink2"], text="")
    for x in (0.33, 0.58):
        fig.add_annotation(x=x, y=0.45, ax=x, ay=0.60, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=C["purple"], text="")
    fig.update_layout(xaxis=dict(visible=False, range=[-0.01, 1.01]),
                      yaxis=dict(visible=False, range=[0, 1]), showlegend=False)
    R.figura(R1.salvar(fig, "h01_arquitetura_produto", altura=520, largura=1200),
             "Arquitetura-alvo do SADPF como produto", "Fonte: elaboração própria.")
    R.p("A proposta preserva o que existe: as regras do core/ passam a ser servidas por uma API "
        "(FastAPI), os arquivos dão lugar a um banco PostgreSQL com uma base por farmácia, e a "
        "interface em Streamlit continua na primeira fase — o guia estima de 3 a 5 semanas para "
        "esse modelo híbrido. A troca da interface por Django ou React (8 semanas a 4 meses) só "
        "se justifica quando houver muitas farmácias e usuários simultâneos.")

    R.h2("4.4 Integração de dados")
    R.tabela(pd.DataFrame([
        ("XML da NF-e de compra", "o que chegou, lote, validade, prazo de entrega, duplicatas",
         "importação de arquivo; depois, download automático pela SEFAZ com certificado digital"),
        ("Vendas (PDV, ERP ou XML da NFC-e)", "saídas reais: giro, cobertura, ruptura, XYZ, previsão",
         "exportação periódica no layout do livro de movimentação"),
        ("Inventário inicial", "saldo de partida por lote", "contagem física; depois, contagens "
         "cíclicas dos itens A"),
        ("Cotações dos portais", "preço, fornecedor e condições", "importação atual; depois, "
         "integração com o portal"),
    ], columns=["Fonte", "O que traz", "Como entra"]), "Fontes de dados de um SADPF em produção",
        "Fonte: guia do código, seção 29.", larguras=[4, 6, 6])

    R.h2("4.5 Segurança e LGPD")
    R.lista([
        ("Papéis:", "a farmácia é a controladora dos dados; o fornecedor do SADPF atua como "
         "operador, com contrato que defina finalidade, segurança e eliminação ao fim do uso."),
        ("Dados pessoais:", "nomes de representantes e, numa fase futura, de funcionários e "
         "clientes de receitas — minimizar, codificar por padrão (como já é feito) e restringir "
         "por perfil."),
        ("Proteção:", "HTTPS, senhas com hash e login gerenciado, criptografia em repouso, "
         "backups diários testados e registro de quem acessou e alterou o quê."),
        ("Incidentes e direitos:", "procedimento de comunicação de incidentes e de atendimento a "
         "pedidos de titulares, com um encarregado definido."),
    ])

    R.h2("4.6 Hospedagem e custo de infraestrutura")
    opcoes = [("Streamlit Community Cloud", 0), ("Render Starter / Railway Hobby", 7),
              ("Híbrido FastAPI + PostgreSQL", 15), ("Hugging Face Spaces (PRO)", 9)]
    fig = go.Figure(go.Bar(x=[o for o, _ in opcoes], y=[v for _, v in opcoes],
                           marker_color=[C["green"], C["blue"], C["purple"], C["blue_l"]],
                           text=[f"US$ {v}" if v else "grátis" for _, v in opcoes],
                           textposition="outside"))
    fig.update_layout(yaxis=dict(title="US$ por mês (teto da faixa)", range=[0, 19]))
    R.figura(R1.salvar(fig, "h02_custos_hospedagem", altura=380, largura=900),
             "Custo mensal de hospedagem por opção (valores publicados em 30/09/2026)",
             "Fonte: guia do código, seções 22, 24 e 25.", 14)
    R.p("O custo de infraestrutura é baixo frente ao valor em jogo: a opção gratuita serve para "
        "demonstração, mas apaga os arquivos ao reiniciar; para uso real, um servidor sempre "
        "ligado com banco custa da ordem de US$ 5 a 15 por mês e pode atender várias farmácias. "
        "O custo dominante de um produto não é o servidor, e sim implantação, suporte e evolução.")

    R.h2("4.7 Modelo de negócio (hipóteses a validar)")
    R.lista([
        ("Público:", "farmácias independentes que compram por cotação eletrônica e não têm "
         "analista de compras."),
        ("Proposta de valor:", "transformar as cotações que a farmácia já tem em economia e "
         "prioridades em reais, sem trocar o ERP."),
        ("Receita:", "assinatura mensal por loja, com implantação assistida; o preço deve ser "
         "testado em entrevistas e no piloto, comparado com a economia medida por loja."),
        ("Viabilidade:", "o produto se paga para a farmácia quando a economia realizada por mês "
         "supera a assinatura; para o fornecedor, quando o número de lojas cobre suporte e "
         "evolução. Os dois lados dependem de medir a economia realizada, não só a estimada."),
    ])

    R.h2("4.8 Roteiro e piloto")
    fases = [("1. Piloto assistido na farmácia estudada", 0, 12),
             ("2. Base de dados e API (híbrido)", 4, 5),
             ("3. Entradas por XML da NF-e", 9, 6),
             ("4. Vendas reais (PDV/NFC-e)", 15, 8),
             ("5. Hospedagem segura e multiempresa", 9, 6),
             ("6. Beta com 3 a 5 farmácias", 23, 12)]
    fig = go.Figure()
    for nome_, ini, dur in fases:
        fig.add_trace(go.Bar(y=[nome_], x=[dur], base=[ini], orientation="h",
                             marker_color=C["blue"] if "Piloto" not in nome_ and "Beta" not in nome_ else C["green"],
                             text=[f"{dur} sem."], textposition="inside", showlegend=False))
    fig.update_layout(yaxis=dict(autorange="reversed"),
                      xaxis=dict(title="semanas a partir do início", dtick=4), barmode="overlay")
    R.figura(R1.salvar(fig, "h03_roteiro", altura=380, largura=1000),
             "Roteiro estimado do protótipo ao beta (verde = uso com farmácias)",
             "Fonte: elaboração própria; durações segundo o guia do código.")
    R.tabela(pd.DataFrame([
        ("Economia realizada", "R$ por mês efetivamente economizados nas compras",
         "comparar preço pago × menor preço cotado, antes e depois"),
        ("Perdas por validade", "perda ÷ faturamento", "cair em relação ao período anterior"),
        ("Cobertura do estoque", "dias de estoque dos itens A", "aproximar-se de 30 a 60 dias"),
        ("Tempo de preparo da cotação", "minutos por cotação", "reduzir"),
        ("Uso", "sessões por semana e ações do plano marcadas como feitas", "uso semanal contínuo"),
        ("Usabilidade", "questionário SUS (0 a 100)", "acima de 68"),
    ], columns=["Indicador", "Medida", "Meta do piloto"]), "Métricas de sucesso do piloto",
        "Fonte: elaboração própria.", larguras=[4, 6, 6])

    R.h2("4.9 Riscos")
    R.tabela(pd.DataFrame([
        ("Qualidade dos dados de venda", "alto", "validação na importação; contagens cíclicas"),
        ("Adesão do usuário", "alto", "implantação assistida; plano de ação curto; tutoriais"),
        ("Recomendação errada levar a prejuízo", "médio", "valores marcados como estimados; "
         "decisão sempre do gestor; regras auditáveis"),
        ("Vazamento de dados comerciais", "médio", "HTTPS, perfis, auditoria, codificação por padrão"),
        ("Regulação (preço máximo, controlados, prescrição)", "médio", "regras já aplicadas na "
         "remarcação; revisão por farmacêutico"),
        ("Dependência de formatos dos portais e do PDV", "médio", "importadores separados e testados"),
    ], columns=["Risco", "Impacto", "Mitigação"]), "Riscos para o produto e mitigação",
        "Fonte: elaboração própria.", larguras=[5.5, 2, 8.5])
    R.p("Um cuidado de enquadramento: o SADPF apoia decisões comerciais e de estoque e não toma "
        "decisões clínicas; ainda assim, qualquer recomendação que toque a dispensação (como o "
        "prazo mínimo de validade por classe terapêutica) deve passar pela revisão do farmacêutico "
        "responsável.")
    R.quebra()

    # ================================================================== PARTE V
    R.h1("Parte V — Síntese e próximos passos para o TCC")
    R.lista([
        "Atualizar no capítulo 5 os números da Tabela de divergências (Parte I) e inserir as "
        "capturas que faltavam (Figuras do plano de ação, de Preferências e do quadro \"O que "
        "mudou\").",
        "Acrescentar ao capítulo 5 a seção de precisão (2.8 e 2.10) e a de verificação com os "
        "defeitos encontrados (2.11), que mostram rigor.",
        "Usar a tabela de limitações (Parte III) para reescrever a seção 6.1.",
        "Resumir a Parte IV em trabalhos futuros (6.2), com o roteiro e as métricas do piloto.",
        "Resolver com a equipe as pendências da seção 1.3 — autorização, origem dos campos, "
        "cronograma e, se possível, uma sessão de validação com a gestora.",
    ], numerada=True)

    R.h1("Apêndice — Telas do sistema")
    for arq, tit_ in (("t02_movimentacoes.png", "Visão Geral › Movimentações do período"),
                      ("t05_curva_abc.png", "Curva ABC"),
                      ("t06_abc_xyz.png", "Análises e Indicadores › ABC × XYZ"),
                      ("t07_apoio_decisao.png", "Sistema de Apoio à Decisão"),
                      ("t09_previsao_fechamento.png", "Previsão de Compras › Pelas vendas"),
                      ("t10_dente_serra.png", "Reposição e Lotes"),
                      ("t11_ficha_medicamento.png", "Ficha do medicamento"),
                      ("t12_posicao_estoque.png", "Posição de Estoque"),
                      ("t13_causas_perdas.png", "Validade e Remarcação")):
        if (TELAS / arq).exists():
            R.figura(TELAS / arq, tit_, CAP, 15.5)

    arq = R.salvar(SAIDA / "SADPF_Resultados_TCC_v2.docx")
    print(f"documento: {arq} · {R.n_fig} figuras · {R.n_tab} tabelas")


if __name__ == "__main__":
    try:
        main()
    finally:
        R1._fechar_navegador()
