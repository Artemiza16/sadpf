"""
Desenha a arquitetura do SADPF no paradigma Dados–Modelos–Diálogo (Sprague; Carlson, 1982).

    python gerar_arquitetura.py

Saída: relatorio_2/figuras/a02_arquitetura_dmd.png (também usada pelo relatório 2).

O desenho segue o código: cada caixa é um módulo que existe, cada seta é uma importação
ou uma leitura/gravação de arquivo que acontece. Seta cheia = os dados seguem nesse
sentido; seta tracejada = gravação ou ajuste feito pelo usuário. Ao mudar o código,
confira as setas com `Select-String "from core"` (ou grep) e rode de novo.
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

import gerar_resultados_tcc as R1

C = R1.C
SAIDA = Path(__file__).parent / "relatorio_2" / "figuras"
CINZA, TINTA = "#9AA6B2", C["ink"]


def caixa(fig, x0, y0, x1, y1, titulo, texto="", cor=CINZA, destaque=False, tracejada=False,
          tam=13.5):
    fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1, layer="below",
                  line=dict(color=C["blue_d"] if destaque else cor, width=2.6 if destaque else 1.4,
                            dash="dash" if tracejada else "solid"),
                  fillcolor="#E4EEF8" if destaque else "#FFFFFF")
    # título e texto num bloco só, centrado: em caixas baixas, posições separadas se
    # sobrepunham
    corpo = (f"<b>{titulo}</b>" + (f"<br><span style='font-size:{tam - 2}px;color:{C['ink2']}'>"
                                   f"{texto}</span>" if texto else ""))
    fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=corpo, showarrow=False,
                       font=dict(size=tam + 1, color=TINTA), bgcolor="rgba(0,0,0,0)",
                       align="center")


def seta(fig, de, para, rotulo="", tracejada=False, duas=False, cor=None, pos=0.5, desloc=(0, 0)):
    cor = cor or C["ink2"]
    if tracejada:
        # o Plotly não traceja a seta da anotação: linha tracejada + ponta
        fig.add_shape(type="line", x0=de[0], y0=de[1], x1=para[0], y1=para[1],
                      line=dict(color=cor, width=1.6, dash="dash"))
        fig.add_annotation(x=para[0], y=para[1], ax=de[0] + (para[0] - de[0]) * 0.92,
                           ay=de[1] + (para[1] - de[1]) * 0.92, xref="x", yref="y", axref="x",
                           ayref="y", showarrow=True, arrowhead=2, arrowsize=1.3, arrowwidth=1.6,
                           arrowcolor=cor, text="")
        if duas:
            fig.add_annotation(x=de[0], y=de[1], ax=de[0] + (para[0] - de[0]) * 0.08,
                               ay=de[1] + (para[1] - de[1]) * 0.08, xref="x", yref="y",
                               axref="x", ayref="y", showarrow=True, arrowhead=2, arrowsize=1.3,
                               arrowwidth=1.6, arrowcolor=cor, text="")
    else:
        fig.add_annotation(x=para[0], y=para[1], ax=de[0], ay=de[1], xref="x", yref="y",
                           axref="x", ayref="y", showarrow=True, arrowhead=2, arrowsize=1.3,
                           arrowwidth=1.8, arrowcolor=cor, text="",
                           arrowside="end+start" if duas else "end")
    if rotulo:
        fig.add_annotation(x=de[0] + (para[0] - de[0]) * pos + desloc[0],
                           y=de[1] + (para[1] - de[1]) * pos + desloc[1], text=f"<i>{rotulo}</i>",
                           showarrow=False, font=dict(size=11, color=C["ink2"]),
                           bgcolor="rgba(255,255,255,0.92)")


def faixa(fig, y0, y1, nome, sub):
    fig.add_shape(type="rect", x0=0.0, y0=y0, x1=0.845, y1=y1, layer="below",
                  line=dict(color="#D5DBE1", width=1), fillcolor="#F3F4F0")
    fig.add_annotation(x=0.018, y=(y0 + y1) / 2, text=f"<b>{nome}</b>", textangle=-90,
                       showarrow=False, font=dict(size=18, color=TINTA))
    fig.add_annotation(x=0.040, y=(y0 + y1) / 2, text=sub, textangle=-90, showarrow=False,
                       font=dict(size=11.5, color=C["ink2"]))


def desenhar() -> go.Figure:
    fig = go.Figure()
    faixa(fig, 0.755, 0.985, "Diálogo", "Streamlit · Plotly")
    faixa(fig, 0.345, 0.735, "Modelos", "core/ · pandas · NumPy · sem Streamlit")
    faixa(fig, 0.015, 0.325, "Dados", "arquivos locais")

    # ---------------------------------------------------------------- diálogo
    caixa(fig, 0.065, 0.80, 0.165, 0.95, "Gestor", "navegador<br>ou celular")
    caixa(fig, 0.195, 0.80, 0.335, 0.95, "app.py", "login, menu,<br>filtros globais<br>e recorte")
    caixa(fig, 0.365, 0.80, 0.655, 0.95, "paginas/ · 16 telas",
          "Painel · Compras · Movimentação · Análise e decisão · Referência<br>"
          "(Base de Dados recebe cotações, livro e cadastro manual;<br>"
          "Preferências ajusta as réguas)", destaque=True)
    caixa(fig, 0.685, 0.875, 0.835, 0.965, "tema.py", "visual, gráficos,<br>cores acessíveis", tam=12.5)
    caixa(fig, 0.685, 0.775, 0.835, 0.865, "memoria.py", "cache por versão<br>da base", tam=12.5)
    seta(fig, (0.165, 0.875), (0.195, 0.875), duas=True)
    seta(fig, (0.335, 0.875), (0.365, 0.875))
    seta(fig, (0.655, 0.905), (0.685, 0.92))
    seta(fig, (0.655, 0.845), (0.685, 0.82))

    # ---------------------------------------------------------------- modelos
    caixa(fig, 0.065, 0.625, 0.215, 0.715, "cadastro.py", "cadastro manual:<br>CNPJ, EAN, datas", tam=12.5)
    caixa(fig, 0.065, 0.38, 0.215, 0.605, "dados.py",
          "leitura, limpeza,<br>regras de status,<br>chave sem duplicidade,<br>recorte filtrado,<br>"
          "nomes codificados")
    caixa(fig, 0.25, 0.615, 0.43, 0.705, "metricas.py", "indicadores, Curva ABC,<br>XYZ, comparativos")
    caixa(fig, 0.25, 0.505, 0.43, 0.595, "previsao.py", "orçamento e itens,<br>teste no histórico")
    caixa(fig, 0.25, 0.375, 0.43, 0.485, "movimentacao.py",
          "posição, giro, reposição,<br>lote econômico, perdas,<br>previsão de vendas")
    caixa(fig, 0.47, 0.615, 0.65, 0.705, "parametros.py", "33 réguas em<br>8 categorias")
    caixa(fig, 0.47, 0.465, 0.65, 0.585, "decisao.py", "26 pontos (21 sem o livro),<br>gravidade, "
          "impacto em R$<br>e plano de ação", destaque=True)
    caixa(fig, 0.47, 0.37, 0.65, 0.44, "leituras.py", "leitura atual × anterior", tam=12.5)
    caixa(fig, 0.685, 0.625, 0.835, 0.715, "formato.py", "R$, %, datas<br>(modelos e telas)", tam=12.5)
    caixa(fig, 0.685, 0.515, 0.835, 0.605, "exportar.py", "Curva ABC<br>em Excel", tam=12.5)
    caixa(fig, 0.685, 0.395, 0.835, 0.495, "usuarios.py", "acesso por empresa,<br>senha com hash", tam=12.5)

    seta(fig, (0.50, 0.80), (0.38, 0.705), "recorte ↓ · tabelas, gráficos e pontos ↑", duas=True,
         pos=0.45, desloc=(0.07, 0.0))
    seta(fig, (0.40, 0.80), (0.14, 0.715), "Base de Dados", tracejada=True, pos=0.55,
         desloc=(-0.02, 0.012))
    seta(fig, (0.60, 0.80), (0.58, 0.705), "Preferências", tracejada=True, pos=0.45,
         desloc=(0.045, 0.0))
    seta(fig, (0.14, 0.625), (0.14, 0.605))
    seta(fig, (0.215, 0.585), (0.25, 0.64))           # dados → metricas
    seta(fig, (0.215, 0.43), (0.25, 0.43))            # dados → movimentacao
    seta(fig, (0.34, 0.615), (0.34, 0.595))
    seta(fig, (0.43, 0.66), (0.47, 0.545))
    seta(fig, (0.43, 0.43), (0.47, 0.49), "estoque e perdas", pos=0.5, desloc=(0.0, -0.02))
    seta(fig, (0.56, 0.615), (0.56, 0.585), "réguas", pos=0.5, desloc=(0.03, 0.0))
    seta(fig, (0.56, 0.465), (0.56, 0.44))

    # ---------------------------------------------------------------- dados
    caixa(fig, 0.065, 0.05, 0.195, 0.27, "Cotações", "planilhas do<br>portal (.xlsx/.csv)")
    caixa(fig, 0.22, 0.05, 0.36, 0.27, "base_consolidada.csv", "base tratada<br>e historico/<br>de versões")
    caixa(fig, 0.385, 0.05, 0.525, 0.27, "Livro de<br>movimentação", "movimentacao_<br>estoque.csv<br>"
          "entradas reais,<br>saídas simuladas", tam=12.5)
    caixa(fig, 0.55, 0.05, 0.66, 0.27, "Gerador", "pipeline à parte,<br>semente 42", tracejada=True)
    caixa(fig, 0.685, 0.035, 0.835, 0.30, "Arquivos JSON",
          "preferencias.json ↔ parametros<br>leituras.json ↔ leituras<br>"
          "usuarios.json ↔ usuarios<br>apelidos.json → dados", tam=12.5)
    seta(fig, (0.13, 0.27), (0.13, 0.38), "importação validada", pos=0.5, desloc=(0.0, 0.0))
    seta(fig, (0.20, 0.38), (0.29, 0.27), "grava versão / lê", tracejada=True, duas=True,
         pos=0.5, desloc=(0.035, 0.0))
    seta(fig, (0.55, 0.16), (0.525, 0.16), tracejada=True)
    seta(fig, (0.44, 0.27), (0.36, 0.375), "lê", pos=0.5, desloc=(0.02, 0.0))
    seta(fig, (0.76, 0.30), (0.76, 0.395), "lê e grava", tracejada=True, duas=True, pos=0.5,
         desloc=(0.04, 0.0))

    # ---------------------------------------------------------------- verificação
    fig.add_shape(type="rect", x0=0.86, y0=0.015, x1=0.995, y1=0.985, layer="below",
                  line=dict(color=C["green"], width=1.4, dash="dash"), fillcolor="#EEF5F2")
    fig.add_annotation(x=0.9275, y=0.965, text="<b>Verificação</b>", showarrow=False,
                       font=dict(size=16, color=C["green"]))
    itens = [("navegador", "16 telas, celular,<br>tema escuro,<br>privacidade", 0.80, 0.94),
             ("verificar.py", "16 blocos: testa<br>core/ sem abrir<br>a interface", 0.50, 0.70),
             ("filtros", "74 recortes ×<br>21 telas, 545<br>conferências", 0.36, 0.48),
             ("acessibilidade.py", "cores para<br>daltonismo e<br>contraste", 0.05, 0.27)]
    for tit_, txt, y0, y1 in itens:
        caixa(fig, 0.87, y0, 0.985, y1, tit_, txt, cor=C["green"], tam=12)

    fig.add_annotation(x=0.42, y=0.0, yanchor="top", showarrow=False,
                       text="seta cheia: os dados seguem nesse sentido   ·   seta tracejada: "
                            "gravação ou ajuste feito pelo usuário   ·   caixa azul: núcleo do "
                            "apoio à decisão   ·   faixa verde: verificação, que testa todas as "
                            "camadas",
                       font=dict(size=11.5, color=C["ink2"]))
    fig.update_layout(xaxis=dict(visible=False, range=[-0.005, 1.0]),
                      yaxis=dict(visible=False, range=[-0.03, 1.0]), showlegend=False,
                      margin=dict(l=10, r=10, t=10, b=10))
    return fig


def main() -> Path:
    SAIDA.mkdir(parents=True, exist_ok=True)
    R1.FIG = SAIDA
    try:
        return R1.salvar(desenhar(), "a02_arquitetura_dmd", altura=1000, largura=1700)
    finally:
        R1._fechar_navegador()


if __name__ == "__main__":
    print("figura:", main())
