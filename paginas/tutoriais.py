"""Tutoriais em vídeo, organizados em trilhas do básico ao avançado.

Cada tutorial tem um roteiro sugerido para a gravação. Quando o vídeo existir,
preencha o campo `video` com:
  - o nome de um arquivo salvo em assets/videos/ (ex.: "01-conhecendo.mp4"), ou
  - um endereço do YouTube ou de outro serviço de vídeo.
Enquanto o campo estiver vazio, a tela mostra o roteiro e o aviso "vídeo em produção".
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.tema import faixa

PASTA_VIDEOS = Path(__file__).parent.parent / "assets" / "videos"

TRILHAS = [
    ("Primeiros passos", "Para quem abre o sistema pela primeira vez.", [
        {"titulo": "Conhecendo o SADPF em 3 minutos", "duracao": "3 min", "video": "",
         "objetivo": "Mostrar para que serve o sistema e como ele está organizado.",
         "roteiro": ["O problema: decidir compras sem olhar o histórico",
                     "O menu lateral e seus quatro grupos (Compras, Movimentação, Análise e decisão, Referência)",
                     "De onde vêm os dados: as cotações e o livro de movimentação do estoque",
                     "Os selos Estimado e Projeção: o que não é valor observado",
                     "O caminho sugerido: Visão Geral → Apoio à Decisão → telas de detalhe"]},
        {"titulo": "Usando os filtros globais", "duracao": "3 min", "video": "",
         "objetivo": "Ensinar a recortar a análise por período, fornecedor, categoria e medicamento.",
         "roteiro": ["Os filtros valem para todas as telas ao mesmo tempo",
                     "Escolher um período: data inicial e depois a final",
                     "Combinar filtros (ex.: genéricos de um fornecedor)",
                     "Botão Limpar filtros e o rodapé com o tamanho da base"]},
        {"titulo": "Lendo a Visão Geral na ordem certa", "duracao": "4 min", "video": "",
         "objetivo": "Apresentar a hierarquia de leitura da tela principal.",
         "roteiro": ["Resumo do período: compras, vendas, estoque e perdas",
                     "Ganhos, perdas e riscos: onde está o dinheiro",
                     "Prioridades: o que o apoio à decisão recomenda olhar primeiro",
                     "Tendências e onde aprofundar"]},
    ]),
    ("Telas de compras", "Quanto, de quem e o que foi comprado.", [
        {"titulo": "Gestão de Compras e Pedidos", "duracao": "4 min", "video": "",
         "objetivo": "Mostrar a composição das compras e como consultar um pedido.",
         "roteiro": ["Composição por categoria, forma farmacêutica e fornecedor",
                     "Tabela de itens comprados: ordenar e buscar",
                     "Tela Pedidos: clicar num pedido para ver os itens"]},
        {"titulo": "Comparando fornecedores", "duracao": "4 min", "video": "",
         "objetivo": "Ensinar a avaliar um distribuidor antes de negociar.",
         "roteiro": ["Participação de cada fornecedor no total",
                     "Ficha individual: pedidos, atendimento, validade curta",
                     "Por que concentração acima de 40% é um risco"]},
        {"titulo": "Histórico de um medicamento", "duracao": "3 min", "video": "",
         "objetivo": "Mostrar como acompanhar preço e frequência de compra de um item.",
         "roteiro": ["Buscar por nome ou código",
                     "Evolução do custo e fornecedores que venderam o item",
                     "Margem e classe ABC do medicamento"]},
    ]),
    ("Estoque e indicadores", "Como cada número é calculado e como interpretá-lo.", [
        {"titulo": "Curva ABC: do conceito à tela", "duracao": "5 min", "video": "",
         "objetivo": "Explicar a classificação A, B e C e como usá-la para priorizar.",
         "roteiro": ["O princípio de Pareto e por que ele não se confirma nesta base",
                     "Como o sistema calcula o valor e o acumulado",
                     "Ler o gráfico de Pareto e o ranking",
                     "Mudar o critério de corte em Preferências e ver o efeito"]},
        {"titulo": "Posição, reposição e validade do estoque", "duracao": "6 min", "video": "",
         "objetivo": "Mostrar como acompanhar o estoque e decidir o que comprar e remarcar.",
         "roteiro": ["Posição de Estoque: o que pede atenção e a situação de cada produto",
                     "Reposição e Lotes: ponto de pedido, lista de compra e dente de serra",
                     "Validade e Remarcação: lotes que vão vencer e a ação de cada um",
                     "Validade no recebimento: com quanto prazo os produtos chegam"]},
        {"titulo": "Análises e Indicadores", "duracao": "5 min", "video": "",
         "objetivo": "Explicar giro, atendimento, margem, sazonalidade e variação de preço.",
         "roteiro": ["Giro e cobertura: a ponte do estoque de partida ao de chegada",
                     "Nível de atendimento e linhas com corte",
                     "Margem bruta ponderada por categoria",
                     "Sazonalidade das compras e das vendas por classe terapêutica"]},
    ]),
    ("Apoio à decisão", "Do diagnóstico ao plano de ação.", [
        {"titulo": "Como o sistema de apoio à decisão pensa", "duracao": "5 min", "video": "",
         "objetivo": "Explicar gravidade, economia e exposição.",
         "roteiro": ["Os 26 pontos em sete assuntos",
                     "Crítico, atenção e saudável: a gravidade vem do valor em reais",
                     "Economia (pode somar) × exposição (não soma)",
                     "Abrir um ponto: valores, itens envolvidos e ação sugerida"]},
        {"titulo": "Do diagnóstico ao plano de ação: um caso completo", "duracao": "6 min",
         "video": "",
         "objetivo": "Percorrer uma decisão real do começo ao fim.",
         "roteiro": ["Partir de um ponto crítico da Visão Geral",
                     "Conferir o detalhe na tela correspondente",
                     "Usar os filtros para isolar o problema",
                     "Registrar a ação e acompanhar na próxima cotação"]},
    ]),
    ("Configuração e dados", "Ajustar o sistema e manter a base atualizada.", [
        {"titulo": "Preferências: ajustando as réguas", "duracao": "4 min", "video": "",
         "objetivo": "Mostrar como mudar limites e ver o efeito na hora.",
         "roteiro": ["Nomes originais ou codificados dos fornecedores",
                     "Janela de validade, margem apertada e concentração",
                     "O quadro verde com o efeito de cada valor",
                     "Salvar e restaurar os padrões"]},
        {"titulo": "Incluindo uma nova cotação", "duracao": "4 min", "video": "",
         "objetivo": "Ensinar a atualizar a base sem duplicar dados.",
         "roteiro": ["Enviar a planilha na tela Base de Dados",
                     "Ler a prévia: linhas novas, já existentes e regras de limpeza",
                     "Confirmar e ver todas as telas atualizadas",
                     "Desfazer uma inclusão pelas versões anteriores",
                     "Cadastro manual: digitar um pedido, revisar os erros e gravar",
                     "Aba Movimentação de estoque: verificações e carga de um livro novo"]},
        {"titulo": "Conceitos e Cálculos: onde conferir cada fórmula", "duracao": "3 min",
         "video": "",
         "objetivo": "Mostrar onde está a explicação de cada indicador.",
         "roteiro": ["Grupos de conceitos e como navegar",
                     "Fórmula e valor calculado no recorte atual",
                     "Limitações da base registradas no sistema"]},
    ]),
]

DICAS = [
    "Um assunto por vídeo, entre 3 e 6 minutos.",
    "Grave a tela inteira em 1080p, com o zoom do navegador em 100%.",
    "Deixe os nomes de fornecedores codificados (padrão) para não expor os dados.",
    "Comece dizendo qual pergunta o vídeo responde e termine com o que fazer depois.",
    "Mostre um exemplo real da base em vez de explicar só a tela.",
]


def _video(origem: str) -> None:
    if origem.startswith(("http://", "https://")):
        st.video(origem)
        return
    arquivo = PASTA_VIDEOS / origem
    if arquivo.exists():
        st.video(str(arquivo))
    else:
        st.warning(f"Arquivo de vídeo não encontrado: assets/videos/{origem}")


def tutoriais() -> None:
    faixa("Vídeos curtos para aprender a usar o sistema, do <b>primeiro acesso</b> até a "
          "<b>leitura dos indicadores</b> e a <b>atualização da base</b>. Siga as trilhas na "
          "ordem ou vá direto ao assunto que precisa.", "Tutoriais")

    todos = [t for _, _, lista in TRILHAS for t in lista]
    prontos = sum(1 for t in todos if t["video"])
    st.caption(f"{prontos} de {len(todos)} vídeos disponíveis · "
               f"{len(TRILHAS)} trilhas, do básico ao avançado")

    abas = st.tabs([f"{i}. {nome}" for i, (nome, _, _) in enumerate(TRILHAS, 1)])
    numero = 0
    for aba, (nome, descricao, lista) in zip(abas, TRILHAS):
        with aba:
            st.caption(descricao)
            for tut in lista:
                numero += 1
                situacao = "disponível" if tut["video"] else "vídeo em produção"
                with st.expander(f"{numero:02d} · {tut['titulo']}  —  {tut['duracao']} · "
                                 f"{situacao}", expanded=False):
                    st.markdown(f"**Objetivo:** {tut['objetivo']}")
                    if tut["video"]:
                        _video(tut["video"])
                    else:
                        st.info("Vídeo em produção. Abaixo, o roteiro sugerido para a gravação.",
                                icon=":material/videocam:")
                    st.markdown("**Roteiro**")
                    st.markdown("\n".join(f"{i}. {passo}"
                                          for i, passo in enumerate(tut["roteiro"], 1)))

    with st.expander("Dicas para gravar os vídeos"):
        st.markdown("\n".join(f"- {d}" for d in DICAS))
