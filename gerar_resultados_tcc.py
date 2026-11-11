"""
Gera o documento de resultados do SADPF para o TCC (Word, com figuras e tabelas).

    python gerar_resultados_tcc.py

Saídas (em relatorio/resultados_tcc/):
    SADPF_Resultados_TCC.docx   o documento, com sumário, figuras e tabelas numeradas
    figuras/*.png               os gráficos, gerados com o código do próprio sistema
    telas/*.png                 capturas do painel (geradas à parte, pelo teste de navegador)

Todos os números saem dos mesmos módulos que o painel usa (core/), com os nomes de
fornecedores codificados. O texto separa sempre o que é OBSERVADO (cotações) do que
depende das vendas SIMULADAS do livro de movimentação. Requer kaleido e python-docx
(pip install -r requirements-relatorio.txt).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from docx import Document                                   # noqa: E402
from docx.enum.section import WD_ORIENT                     # noqa: E402,F401
from docx.enum.table import WD_TABLE_ALIGNMENT              # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH               # noqa: E402
from docx.oxml import OxmlElement                           # noqa: E402
from docx.oxml.ns import qn                                 # noqa: E402
from docx.shared import Cm, Pt, RGBColor                    # noqa: E402

from core import acessibilidade as AC                       # noqa: E402
from core import dados as D                                 # noqa: E402
from core import decisao as Dc                              # noqa: E402
from core import metricas as M                              # noqa: E402
from core import movimentacao as MV                         # noqa: E402
from core import previsao as PV                             # noqa: E402
from core import tema as T                                  # noqa: E402
from core.parametros import Parametros                      # noqa: E402

SAIDA = RAIZ / "relatorio" / "resultados_tcc"
FIG, TELAS = SAIDA / "figuras", SAIDA / "telas"
C = T.PALETA["claro"]
COR_OBS, COR_SIM = C["blue"], C["purple"]          # observado × simulado, em todas as figuras
COR_NIVEL = {"crit": C["red"], "aten": C["amber"], "ok": C["green"], "info": C["blue_l"]}
FONTE_OBS = "Fonte: elaboração própria (SADPF), base de cotações de 30/10/2024 a 08/07/2026."
FONTE_SIM = ("Fonte: elaboração própria (SADPF), base de cotações e livro de movimentação "
             "(entradas observadas; estoque inicial, vendas e perdas simulados).")


# --------------------------------------------------------------------------- formatos
def brl(v, casas=0):
    s = f"{abs(v):,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    negativo = round(v, casas) < 0          # sem "−R$ 0,00" para um zero arredondado
    return ("−" if negativo else "") + "R$ " + s


def pct(v, casas=1):
    s = f"{abs(v) * 100:.{casas}f}%".replace(".", ",")
    return ("−" if round(v * 100, casas) < 0 else "") + s


def num(v, casas=0):
    return f"{v:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def mes(p_):
    return T.mes_label(str(p_))


# --------------------------------------------------------------------------- figuras
# As figuras são exportadas pelo próprio Plotly.js numa página do Chrome instalado,
# aberta pelo Playwright (Plotly.toImage). O kaleido, que faria o mesmo, pode travar
# ao abrir o navegador depois de uma atualização do Chrome.
_NAVEGADOR: dict = {}


def _pagina():
    if "pagina" not in _NAVEGADOR:
        from playwright.sync_api import sync_playwright
        import plotly.offline as po
        pw = sync_playwright().start()
        nav = pw.chromium.launch(channel="chrome", headless=True)
        pg = nav.new_page()
        pg.set_content("<html><body style='margin:0'><div id='g'></div>"
                       f"<script>{po.get_plotlyjs()}</script></body></html>")
        _NAVEGADOR.update(pw=pw, nav=nav, pagina=pg)
    return _NAVEGADOR["pagina"]


def _fechar_navegador():
    if _NAVEGADOR:
        _NAVEGADOR["nav"].close()
        _NAVEGADOR["pw"].stop()
        _NAVEGADOR.clear()


def salvar(fig: go.Figure, nome: str, altura=440, largura=1000) -> Path:
    import base64
    import json
    fig.update_layout(template="sadpf_branco_claro", height=altura, width=largura,
                      paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", separators=",.",
                      margin=dict(l=20, r=30, t=60, b=40), font=dict(size=13),
                      title=dict(text=None))
    arq = FIG / f"{nome}.png"
    url = _pagina().evaluate(
        """async ([fig, w, h]) => {
             const g = document.getElementById('g');
             await Plotly.newPlot(g, fig.data, fig.layout, {staticPlot: true});
             const png = await Plotly.toImage(g, {format: 'png', width: w, height: h, scale: 2});
             Plotly.purge(g);
             return png;
           }""", [json.loads(fig.to_json()), largura, altura])
    arq.write_bytes(base64.b64decode(url.split(",", 1)[1]))
    print(f"  figura {nome}", flush=True)
    return arq


def _hex_simulado(hexa: str, tipo: str | None) -> str:
    lin = AC._linear(hexa)
    if tipo:
        lin = np.clip(AC.SIMULACAO[tipo] @ lin, 0, 1)
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    return "#" + "".join(f"{int(round(v * 255)):02X}" for v in np.clip(srgb, 0, 1))


# --------------------------------------------------------------------------- documento
class Relatorio:
    def __init__(self):
        self.doc = Document()
        self.n_fig = 0
        self.n_tab = 0
        sec = self.doc.sections[0]
        sec.top_margin, sec.left_margin = Cm(3), Cm(3)
        sec.bottom_margin, sec.right_margin = Cm(2), Cm(2)
        normal = self.doc.styles["Normal"]
        normal.font.name = "Arial"
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
        normal.font.size = Pt(11)
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.25
        for nome, tam in (("Heading 1", 15), ("Heading 2", 12.5), ("Heading 3", 11.5)):
            st_ = self.doc.styles[nome]
            st_.font.name = "Arial"
            st_.font.size = Pt(tam)
            st_.font.color.rgb = RGBColor(0x23, 0x5A, 0x80)
        # pede ao Word para atualizar o sumário ao abrir
        upd = OxmlElement("w:updateFields")
        upd.set(qn("w:val"), "true")
        self.doc.settings.element.append(upd)

    # texto
    def h1(self, t):
        self.doc.add_heading(t, level=1)

    def h2(self, t):
        self.doc.add_heading(t, level=2)

    def h3(self, t):
        self.doc.add_heading(t, level=3)

    def p(self, texto, negrito_inicio: str | None = None, italico=False):
        par = self.doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if negrito_inicio:
            r_ = par.add_run(negrito_inicio + " ")
            r_.bold = True
        r_ = par.add_run(texto)
        r_.italic = italico
        return par

    def lista(self, itens, numerada=False):
        estilo = "List Number" if numerada else "List Bullet"
        for it in itens:
            par = self.doc.add_paragraph(style=estilo)
            if isinstance(it, tuple):
                r_ = par.add_run(it[0] + " ")
                r_.bold = True
                par.add_run(it[1])
            else:
                par.add_run(it)

    def _legenda(self, texto):
        par = self.doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_before = Pt(8)
        par.paragraph_format.keep_with_next = True
        r_ = par.add_run(texto)
        r_.bold = True
        r_.font.size = Pt(10)

    def _fonte(self, texto):
        par = self.doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_ = par.add_run(texto)
        r_.font.size = Pt(9)
        r_.italic = True

    def figura(self, arq: Path, titulo: str, fonte: str, largura_cm=16.0):
        self.n_fig += 1
        self._legenda(f"Figura {self.n_fig} — {titulo}")
        par = self.doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.keep_with_next = True
        par.add_run().add_picture(str(arq), width=Cm(largura_cm))
        self._fonte(fonte)
        return self.n_fig

    def tabela(self, df: pd.DataFrame, titulo: str, fonte: str, larguras=None):
        self.n_tab += 1
        self._legenda(f"Tabela {self.n_tab} — {titulo}")
        tab = self.doc.add_table(rows=1, cols=len(df.columns))
        try:
            tab.style = self.doc.styles["Light List Accent 1"]
        except KeyError:
            tab.style = self.doc.styles["Table Grid"]
        tab.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, col in enumerate(df.columns):
            cel = tab.rows[0].cells[i]
            cel.text = str(col)
            for r_ in cel.paragraphs[0].runs:
                r_.bold = True
                r_.font.size = Pt(9)
        for _, linha in df.iterrows():
            cels = tab.add_row().cells
            for i, v in enumerate(linha):
                cels[i].text = str(v)
                for r_ in cels[i].paragraphs[0].runs:
                    r_.font.size = Pt(9)
        if larguras:
            for linha in tab.rows:
                for i, w in enumerate(larguras):
                    linha.cells[i].width = Cm(w)
        self._fonte(fonte)
        return self.n_tab

    def sumario(self):
        par = self.doc.add_paragraph()
        r_ = par.add_run()
        ini = OxmlElement("w:fldChar"); ini.set(qn("w:fldCharType"), "begin")
        ins = OxmlElement("w:instrText"); ins.set(qn("xml:space"), "preserve")
        ins.text = 'TOC \\o "1-2" \\h \\z \\u'
        sep = OxmlElement("w:fldChar"); sep.set(qn("w:fldCharType"), "separate")
        txt = OxmlElement("w:t"); txt.text = "Clique com o botão direito e escolha Atualizar campo."
        fim = OxmlElement("w:fldChar"); fim.set(qn("w:fldCharType"), "end")
        for el in (ini, ins, sep, txt, fim):
            r_._r.append(el)

    def quebra(self):
        self.doc.add_page_break()

    def salvar(self, arq: Path) -> Path:
        """Grava o .docx; se o arquivo estiver aberto no Word, grava ao lado com '_novo'."""
        try:
            self.doc.save(arq)
            return arq
        except PermissionError:
            alternativo = arq.with_name(arq.stem + "_novo" + arq.suffix)
            self.doc.save(alternativo)
            print(f"  aviso: {arq.name} está aberto (provavelmente no Word); "
                  f"gravado como {alternativo.name}")
            return alternativo


# =========================================================================== cálculo
def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    TELAS.mkdir(parents=True, exist_ok=True)
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
    diag = Dc.diagnostico(ins, ind.valor_pedido)
    diag_antes = Dc.diagnostico(ins_antes, ind.valor_pedido)
    R = Relatorio()

    # ------------------------------------------------------------------ capa
    tit = R.doc.add_paragraph()
    tit.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_ = tit.add_run("SADPF — Sistema de Apoio à Decisão para Pequenas Farmácias")
    r_.bold = True
    r_.font.size = Pt(18)
    r_.font.color.rgb = RGBColor(0x23, 0x5A, 0x80)
    sub = R.doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_ = sub.add_run("Resultados do projeto: Curva ABC e XYZ, apoio à decisão, arquitetura, "
                     "precisão das previsões e dos pedidos, e validação do sistema")
    r_.font.size = Pt(12.5)
    info = R.doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_ = info.add_run(f"Material de apoio ao capítulo de Resultados do TCC · gerado em "
                      f"{date.today():%d/%m/%Y} por gerar_resultados_tcc.py")
    r_.font.size = Pt(10)
    r_.italic = True
    R.p("Todos os números, tabelas e gráficos deste documento foram calculados com o código do "
        "próprio sistema, sobre a base de cotações da farmácia e o livro de movimentação de "
        "estoque. Os nomes de fornecedores e representantes aparecem codificados "
        "(Fornecedor A = o de maior volume). Ao longo do texto, cada resultado é identificado "
        "como observado (medido nas cotações reais) ou simulado (dependente das vendas "
        "geradas para o livro de movimentação), condição necessária para a leitura correta "
        "dos achados.", "Sobre este documento.")
    R.h2("Sumário")
    R.sumario()
    R.quebra()

    # ================================================================== 1. base
    R.h1("1. Apresentação e base de dados")
    tipos = mov["tipo"].value_counts()
    R.p(f"O SADPF transforma o histórico de cotações eletrônicas de uma farmácia de pequeno "
        f"porte em indicadores de compras, estoque e apoio à decisão. A base analisada reúne "
        f"{num(ind.linhas)} linhas de pedido em {num(ind.cotacoes)} cotações e "
        f"{num(ind.pedidos)} pedidos, de {ind.inicio:%d/%m/%Y} a {ind.fim:%d/%m/%Y}, somando "
        f"{brl(ind.valor_pedido)} em compras de {num(ind.medicamentos)} medicamentos junto a "
        f"{num(ind.fornecedores)} distribuidores. O livro de movimentação acrescenta "
        f"{num(len(mov))} movimentos de estoque, lote a lote.")
    R.tabela(pd.DataFrame([
        ("Linhas de pedido (cotações)", num(ind.linhas), "observado"),
        ("Cotações / pedidos", f"{num(ind.cotacoes)} / {num(ind.pedidos)}", "observado"),
        ("Medicamentos distintos", num(ind.medicamentos), "observado"),
        ("Fornecedores", num(ind.fornecedores), "observado"),
        ("Valor pedido", brl(ind.valor_pedido), "observado"),
        ("Média mensal de compras", brl(ind.media_mensal), "observado"),
        ("Entradas no livro de movimentação", num(tipos.get("ENTRADA", 0)),
         "observado (uma por linha faturada)"),
        ("Estoque inicial (lotes)", num(tipos.get("ESTOQUE_INICIAL", 0)), "simulado"),
        ("Saídas por venda", num(tipos.get("SAIDA_VENDA", 0)), "simulado"),
        ("Perdas por validade", num(tipos.get("PERDA_VALIDADE", 0)), "simulado"),
    ], columns=["Item", "Valor", "Natureza"]), "Composição da base analisada", FONTE_SIM,
        larguras=[7, 4, 5])
    R.p("A base de cotações registra apenas o que entrou na farmácia. Para medir giro, "
        "cobertura, ruptura, perdas e Curva ABC por vendas, o projeto construiu um livro de "
        "movimentação: as entradas são as compras reais; o estoque inicial, as vendas e as "
        "perdas foram simulados a partir do ritmo real de reposição de cada produto (gerador "
        "com semente fixa, documentado na seção 9.10 da documentação técnica). O sistema "
        "trata o livro como trataria as vendas do caixa: ao carregar dados reais no mesmo "
        "layout, nenhum cálculo muda.", "Observado e simulado.")

    # ================================================================== 2. arquitetura
    R.h1("2. Arquitetura do sistema")
    R.p("O sistema é uma aplicação web local em Python, organizada em três camadas: dados "
        "(leitura, limpeza, validação e importação), cálculo (indicadores, classificações, "
        "previsões e motor de decisão) e apresentação (16 telas em Streamlit). A separação "
        "permite testar os cálculos sem a interface (verificar.py) e trocar a interface sem "
        "mexer nas regras.")
    fig = go.Figure()
    caixas = [
        (0.00, 0.62, 0.17, 0.95, "Fontes de dados", "Cotações (.xlsx/.csv)<br>Livro de movimentação<br>(.csv)<br>Cadastro manual", C["ink3"]),
        (0.21, 0.55, 0.40, 0.95, "Camada de dados", "core/dados.py<br>leitura, limpeza, regras<br>validação e importação<br>core/cadastro.py", C["teal"]),
        (0.44, 0.55, 0.63, 0.95, "Camada de cálculo", "core/metricas.py (ABC, XYZ)<br>core/movimentacao.py<br>core/previsao.py<br>core/parametros.py (réguas)", C["blue"]),
        (0.67, 0.55, 0.83, 0.95, "Motor de decisão", "core/decisao.py<br>26 pontos · gravidade<br>impacto em R$ · ação<br>core/leituras.py", C["purple"]),
        (0.87, 0.55, 1.00, 0.95, "Interface", "app.py + paginas/<br>16 telas Streamlit<br>core/tema.py<br>(gráficos Plotly)", C["blue_d"]),
        (0.21, 0.05, 0.63, 0.40, "Verificação", "verificar.py (16 blocos) · testes de filtros (74 recortes)<br>testes de navegador · simulação de daltonismo", C["green"]),
        (0.67, 0.05, 1.00, 0.40, "Usuário", "gestor da farmácia: filtros, réguas em<br>Preferências, leitura do plano de ação", C["amber"]),
    ]
    for x0, y0, x1, y1, tit_, txt, cor in caixas:
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1, line=dict(color=cor, width=2),
                      fillcolor=cor + "18", layer="below")
        fig.add_annotation(x=(x0 + x1) / 2, y=y1 - 0.06, text=f"<b>{tit_}</b>", showarrow=False,
                           font=dict(size=14, color=cor), bgcolor="rgba(0,0,0,0)")
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2 - 0.04, text=txt, showarrow=False,
                           font=dict(size=11.5, color=C["ink"]), bgcolor="rgba(0,0,0,0)")
    for xa, xb in ((0.17, 0.21), (0.40, 0.44), (0.63, 0.67), (0.83, 0.87)):
        fig.add_annotation(x=xb, y=0.75, ax=xa, ay=0.75, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowsize=1.4, arrowwidth=2,
                           arrowcolor=C["ink2"], text="")
    fig.add_annotation(x=0.42, y=0.40, ax=0.42, ay=0.55, xref="x", yref="y", axref="x", ayref="y",
                       showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=C["green"], text="")
    fig.add_annotation(x=0.93, y=0.40, ax=0.93, ay=0.55, xref="x", yref="y", axref="x", ayref="y",
                       showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=C["amber"], text="")
    fig.update_layout(xaxis=dict(visible=False, range=[-0.01, 1.01]),
                      yaxis=dict(visible=False, range=[0, 1]), showlegend=False)
    R.figura(salvar(fig, "a01_arquitetura", altura=520, largura=1200),
             "Arquitetura do SADPF em camadas", "Fonte: elaboração própria.")
    modulos = []
    for arq, papel in [("app.py", "entrada, login, menu, filtros globais"),
                       ("core/dados.py", "leitura, limpeza, regras de status, importação"),
                       ("core/cadastro.py", "cadastro manual com validações (CNPJ, EAN, datas)"),
                       ("core/metricas.py", "indicadores, Curva ABC, XYZ, comparativos"),
                       ("core/movimentacao.py", "estoque, giro, reposição, LEC, perdas, previsão de vendas"),
                       ("core/previsao.py", "orçamento e itens da próxima cotação"),
                       ("core/decisao.py", "motor de decisão: 26 pontos, gravidade, plano de ação"),
                       ("core/parametros.py", "réguas ajustáveis e preferências salvas"),
                       ("core/tema.py", "identidade visual, gráficos, cores acessíveis"),
                       ("core/acessibilidade.py", "simulação de daltonismo e contraste"),
                       ("paginas/*.py", "as 16 telas"), ("verificar.py", "verificação automática")]:
        caminho = list(RAIZ.glob(arq))
        linhas = sum(len(c.read_text(encoding="utf-8").splitlines()) for c in caminho)
        modulos.append((arq, papel, num(linhas)))
    R.tabela(pd.DataFrame(modulos, columns=["Módulo", "Responsabilidade", "Linhas"]),
             "Módulos do sistema e responsabilidades", "Fonte: código-fonte do SADPF.",
             larguras=[4.2, 9.5, 2])
    R.tabela(pd.DataFrame([
        ("Python 3.12", "linguagem; todo o cálculo"), ("pandas / NumPy", "tratamento e agregação dos dados"),
        ("Streamlit", "interface web local (16 telas, filtros, sessões)"),
        ("Plotly", "gráficos interativos (e as figuras deste documento)"),
        ("openpyxl", "leitura e exportação de planilhas Excel"),
        ("Playwright (testes)", "testes automáticos no navegador"),
    ], columns=["Biblioteca", "Papel"]), "Bibliotecas principais", "Fonte: requirements.txt.",
        larguras=[5, 11])
    R.p("Do dado à recomendação, o fluxo tem cinco passos:", "Fluxo de decisão.")
    R.lista([
        ("Dado:", "linha de pedido ou movimento de estoque, já limpo e filtrado pelo recorte."),
        ("Indicador:", "cálculo sobre o recorte (ex.: participação do maior fornecedor)."),
        ("Ponto:", "o indicador comparado a uma régua de Preferências (ex.: concentração acima de 40%)."),
        ("Gravidade e impacto:", "crítico, atenção, saudável ou informativo, com o valor em reais."),
        ("Ação:", "o que fazer e em que tela; o plano de ação ordena os pontos por impacto."),
    ], numerada=True)
    if (TELAS / "t01_visao_geral.png").exists():
        R.figura(TELAS / "t01_visao_geral.png", "Tela Visão Geral do SADPF",
                 "Fonte: captura do sistema (nomes de fornecedores codificados).", 15.5)

    # ================================================================== 3. curva ABC
    R.quebra()
    R.h1("3. Curva ABC")
    cl_c = abc_c.classes.set_index("classe")
    cl_v = abc_v.classes.set_index("classe")
    R.p(f"A Curva ABC ordena os medicamentos pelo valor e classifica como A os que somam até "
        f"{pct(p.corte_a, 0)} do valor acumulado, B até {pct(p.corte_b, 0)} e C o restante. "
        f"Pelas compras (observado), {num(cl_c.loc['A', 'itens'])} medicamentos "
        f"({pct(cl_c.loc['A', 'pct_itens'])} do mix) concentram {pct(cl_c.loc['A', 'pct_valor'])} "
        f"do valor; a cauda C, com {pct(cl_c.loc['C', 'pct_itens'])} dos itens, responde por "
        f"apenas {pct(cl_c.loc['C', 'pct_valor'])}.")
    fig = go.Figure()
    for a, nome, cor, traco in ((abc_c, "Compras (observado)", COR_OBS, "solid"),
                                (abc_v, "Vendas (simulado)", COR_SIM, "dash")):
        fig.add_trace(go.Scatter(x=a.itens["posicao"] / a.n, y=a.itens["acumulado_pct"], name=nome,
                                 mode="lines", line=dict(color=cor, width=2.8, dash=traco)))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], name="Distribuição uniforme", mode="lines",
                             line=dict(color=C["ink3"], width=1, dash="dot")))
    for corte in (p.corte_a, p.corte_b):
        fig.add_hline(y=corte, line=dict(color=C["ink3"], width=1, dash="dot"),
                      annotation_text=f"corte {pct(corte, 0)}", annotation_position="bottom right")
    fig.add_vline(x=0.2, line=dict(color=C["ink3"], width=1, dash="dot"),
                  annotation_text="20% dos itens", annotation_position="top right")
    fig.update_layout(xaxis=dict(title="fração dos medicamentos (do maior para o menor valor)",
                                 tickformat=".0%"),
                      yaxis=dict(title="fração acumulada do valor", tickformat=".0%"))
    R.figura(salvar(fig, "b01_pareto"), "Curva ABC (Pareto): compras observadas × vendas simuladas",
             FONTE_SIM)
    R.tabela(pd.DataFrame([
        (f"Classe {k}", num(cl_c.loc[k, "itens"]), pct(cl_c.loc[k, "pct_itens"]),
         brl(cl_c.loc[k, "valor"]), pct(cl_c.loc[k, "pct_valor"]),
         num(cl_v.loc[k, "itens"]), pct(cl_v.loc[k, "pct_itens"]), pct(cl_v.loc[k, "pct_valor"]))
        for k in "ABC"], columns=["Classe", "Itens (compras)", "% itens", "Valor comprado",
                                  "% valor", "Itens (vendas)", "% itens", "% faturamento"]),
        "Classes ABC pelas compras (observado) e pelas vendas (simulado)", FONTE_SIM)
    R.p(f"Os 20% maiores itens somam {pct(abc_c.concentracao_20)} do valor comprado, abaixo dos "
        f"cerca de 80% do princípio de Pareto. A curva é mais achatada do que a referência: o "
        f"gasto está espalhado por muitos itens, o que o sistema sinaliza no ponto "
        f"\"Curva achatada\" do apoio à decisão. Pelas vendas simuladas, a concentração é de "
        f"{pct(abc_v.concentracao_20)}.", "Leitura à luz da literatura.")
    fig = go.Figure()
    for nome_, col_, cor in (("% dos itens", "pct_itens", C["blue_l"]), ("% do valor", "pct_valor", COR_OBS)):
        fig.add_trace(go.Bar(x=[f"Classe {k}" for k in "ABC"], y=cl_c.loc[list("ABC"), col_],
                             name=nome_, marker_color=cor,
                             text=[pct(v) for v in cl_c.loc[list("ABC"), col_]], textposition="outside"))
    fig.update_layout(barmode="group", yaxis=dict(tickformat=".0%", range=[0, 0.95]))
    R.figura(salvar(fig, "b02_classes", altura=380, largura=900),
             "Parcela de itens × parcela do valor em cada classe (compras, observado)", FONTE_OBS, 14)
    top = abc_c.itens.head(10)
    R.tabela(pd.DataFrame([(int(r_["posicao"]), r_["medicamento"][:42], brl(r_["valor"]),
                            pct(r_["participacao"]), pct(r_["acumulado_pct"]))
                           for _, r_ in top.iterrows()],
                          columns=["#", "Medicamento", "Valor comprado", "Participação", "Acumulado"]),
             "Os dez medicamentos de maior valor comprado (classe A)", FONTE_OBS, larguras=[1, 8, 3, 2.3, 2.3])
    cruz = MV.abc_cruzada(abc_c, abc_v)
    matriz = pd.crosstab(cruz["classe_compras"], cruz["classe_vendas"]) \
        .reindex(index=["A", "B", "C"], columns=["A", "B", "C", "sem venda"], fill_value=0)
    comuns = cruz[(cruz["classe_compras"] != "—") & (cruz["classe_vendas"] != "sem venda")]
    rho = comuns["valor_compras"].rank().corr(comuns["faturamento"].rank())
    mesma = (comuns["classe_compras"] == comuns["classe_vendas"]).mean()
    parado = cruz[(cruz["classe_compras"] == "A") & cruz["classe_vendas"].isin(["C", "sem venda"])]
    critico = cruz[(cruz["classe_vendas"] == "A") & cruz["classe_compras"].isin(["B", "C"])]
    fig = go.Figure(go.Heatmap(z=matriz.values, x=[f"vendas {j}" for j in matriz.columns],
                               y=[f"compras {i}" for i in matriz.index], text=matriz.values,
                               texttemplate="%{text}", textfont=dict(size=17),
                               colorscale=[[0, "#F5F8FA"], [1, C["blue"]]], showscale=False,
                               xgap=3, ygap=3))
    fig.update_layout(yaxis=dict(autorange="reversed", showgrid=False), xaxis=dict(showline=False))
    R.figura(salvar(fig, "b03_matriz_compras_vendas", altura=380, largura=820),
             "Classe de cada medicamento nas compras × nas vendas", FONTE_SIM, 13)
    R.p(f"{pct(mesma)} dos medicamentos ficam na mesma classe nas duas curvas e a correlação de "
        f"Spearman entre as posições é {num(rho, 2)}. O cruzamento gera duas listas acionáveis: "
        f"{num(len(parado))} itens A nas compras e C (ou sem venda) nas vendas — dinheiro parado, "
        f"{brl(parado['valor_compras'].sum())} — e {num(len(critico))} itens A nas vendas que não "
        f"são A nas compras, que não podem faltar ({brl(critico['faturamento'].sum())} de "
        f"faturamento). Parte da semelhança entre as curvas vem de as vendas simuladas terem "
        f"sido calibradas pelo ritmo de compra.", "Compras × vendas.")
    if (TELAS / "t05_curva_abc.png").exists():
        R.figura(TELAS / "t05_curva_abc.png", "Tela Curva ABC", "Fonte: captura do sistema.", 15.5)

    # ================================================================== 4. XYZ
    R.quebra()
    R.h1("4. Classificação XYZ e matriz ABC × XYZ")
    xyz_c = M.classificacao_xyz(df, abc_c, p)["xyz"].value_counts()
    xyz_v = pos["xyz"].value_counts()
    R.p("A classificação XYZ mede a regularidade da demanda pelo coeficiente de variação "
        "(CV = desvio-padrão ÷ média) das vendas mensais: X é regular (CV ≤ 0,50), Y variável "
        "(CV ≤ 1,00) e Z irregular. Itens com menos de seis meses de histórico não são "
        "classificados. Cruzada com a Curva ABC, ela define a política de reposição de cada "
        "item (Pontes, 2013).")
    fig = go.Figure()
    for nome_, cont, cor in (("Pelas compras trimestrais (observado)", xyz_c, COR_OBS),
                             ("Pelas vendas mensais (simulado)", xyz_v, COR_SIM)):
        tot = sum(int(cont.get(k, 0)) for k in "XYZ") or 1
        fig.add_trace(go.Bar(x=["X — regular", "Y — variável", "Z — irregular"],
                             y=[int(cont.get(k, 0)) / tot for k in "XYZ"], name=nome_, marker_color=cor,
                             text=[num(int(cont.get(k, 0))) for k in "XYZ"], textposition="outside"))
    fig.update_layout(barmode="group", yaxis=dict(tickformat=".0%", range=[0, 1.12],
                                                  title="parcela dos classificados"))
    R.figura(salvar(fig, "c01_xyz", altura=380, largura=900),
             "Regularidade dos medicamentos (XYZ): compras × vendas", FONTE_SIM, 14)
    R.p(f"Pelas compras, quase todos os itens são Z ({num(int(xyz_c.get('Z', 0)))} de "
        f"{num(int(sum(xyz_c.get(k, 0) for k in 'XYZ')))}): a farmácia compra em lotes "
        f"esporádicos, e o ritmo de compra não revela a regularidade do consumo. Pelas vendas, "
        f"{num(int(xyz_v.get('X', 0)))} itens são X, {num(int(xyz_v.get('Y', 0)))} Y e "
        f"{num(int(xyz_v.get('Z', 0)))} Z. Por isso a classificação pelas vendas é a usada na "
        f"reposição sempre que há livro de movimentação.", "Compras não medem regularidade.")
    mx = pos[["sku", "ean", "xyz", "faturamento"]].merge(abc_v.itens[["sku", "classe"]], on="sku")
    mx = mx[mx["xyz"].isin(list("XYZ"))]
    cont = pd.crosstab(mx["classe"], mx["xyz"]).reindex(index=list("ABC"), columns=list("XYZ"), fill_value=0)
    fat = mx.groupby(["classe", "xyz"])["faturamento"].sum().unstack().reindex(
        index=list("ABC"), columns=list("XYZ")).fillna(0)
    texto = [[f"{cont.loc[i, j]} {'item' if cont.loc[i, j] == 1 else 'itens'}<br>"
              f"{brl(fat.loc[i, j])}" for j in "XYZ"] for i in "ABC"]
    fig = go.Figure(go.Heatmap(z=fat.values, x=["X — regular", "Y — variável", "Z — irregular"],
                               y=["A", "B", "C"], text=texto, texttemplate="%{text}",
                               textfont=dict(size=14), colorscale=[[0, "#F3F6FA"], [1, C["teal"]]],
                               showscale=False, xgap=3, ygap=3))
    fig.update_layout(yaxis=dict(autorange="reversed", showgrid=False, title="classe ABC (vendas)"),
                      xaxis=dict(showline=False))
    R.figura(salvar(fig, "c02_matriz_abc_xyz", altura=420, largura=900),
             "Matriz ABC × XYZ pelas vendas: itens e faturamento de cada combinação", FONTE_SIM, 14.5)
    politica = {"AX": "reposição automática, estoque baixo", "AY": "reposição com segurança maior",
                "AZ": "acompanhamento próximo; comprar sob demanda confirmada",
                "BX": "reposição automática", "BY": "revisão periódica", "BZ": "revisão periódica, lotes menores",
                "CX": "reposição automática simples", "CY": "lotes econômicos, revisão espaçada",
                "CZ": "sob encomenda (não manter estoque)"}
    R.tabela(pd.DataFrame([(f"{a}{x}", num(cont.loc[a, x]), brl(fat.loc[a, x]),
                            pct(fat.loc[a, x] / fat.values.sum()), politica[f"{a}{x}"])
                           for a in "ABC" for x in "XYZ"],
                          columns=["Quadrante", "Itens", "Faturamento", "% fat.", "Política sugerida"]),
             "Matriz ABC × XYZ e política de reposição por quadrante", FONTE_SIM,
             larguras=[2.2, 1.6, 3, 1.8, 7.5])
    ax_ = mx[(mx["classe"] == "A") & (mx["xyz"] == "X")].sort_values("faturamento", ascending=False)
    az_ = mx[(mx["classe"] == "A") & (mx["xyz"] == "Z")].sort_values("faturamento", ascending=False)
    vendas = rec.periodo[rec.periodo["tipo"] == "SAIDA_VENDA"]
    meses_c = [m_ for m_ in sorted(vendas["ano_mes"].unique())][1:-1]          # só meses completos
    fig = go.Figure()
    exemplos = []
    for lin, cor, rot in ((ax_.iloc[0] if len(ax_) else None, C["green"], "AX"),
                          (az_.iloc[0] if len(az_) else None, C["red"], "AZ")):
        if lin is None:
            continue
        s = (-vendas[vendas["ean"] == lin["ean"]].groupby("ano_mes")["quantidade"].sum()) \
            .reindex(meses_c).fillna(0)
        cv = s.std() / s.mean() if s.mean() else float("nan")
        nome_ = pos.set_index("ean").loc[lin["ean"], "medicamento"][:34]
        exemplos.append((rot, nome_, num(s.mean(), 1), num(cv, 2)))
        # cada item em relação à própria média: com escalas tão diferentes, o item de
        # venda baixa pareceria uma linha reta, escondendo justamente a irregularidade
        fig.add_trace(go.Scatter(x=[mes(m_) for m_ in meses_c], y=(s / s.mean()).values,
                                 mode="lines+markers",
                                 name=f"{rot}: {nome_} (média {num(s.mean(), 1)} un/mês · CV {num(cv, 2)})",
                                 line=dict(color=cor, width=2.4)))
    fig.add_hline(y=1, line=dict(color=C["ink3"], dash="dot"), annotation_text="mês médio",
                  annotation_position="top left")
    fig.update_layout(yaxis=dict(title="vendas do mês ÷ média do item", rangemode="tozero"))
    R.figura(salvar(fig, "c03_exemplo_ax_az", altura=420),
             "Exemplo: vendas mensais de um item AX (regular) e de um AZ (irregular), em relação "
             "à média de cada um", FONTE_SIM)
    R.p("Cada linha mostra as vendas do mês divididas pela média do próprio item (1 = mês "
        "médio). O item AX oscila perto da média, e o ponto de pedido com estoque de segurança "
        "pequeno basta. O item AZ vai de quase zero a várias vezes a média: um estoque calculado "
        "pela média ficaria ora em falta, ora sobrando. Por isso o sistema o marca para "
        "acompanhamento.", "Exemplo.")
    if (TELAS / "t06_abc_xyz.png").exists():
        R.figura(TELAS / "t06_abc_xyz.png", "Tela Análises e Indicadores › ABC × XYZ",
                 "Fonte: captura do sistema.", 15.5)

    # ================================================================== 5. apoio à decisão
    R.quebra()
    R.h1("5. Sistema de Apoio à Decisão")
    R.p(f"O motor de decisão (core/decisao.py) avalia {len(ins)} pontos agrupados em categorias "
        f"(Curva ABC, alertas, fornecedores, medicamentos, compras, estoque e movimentação). "
        f"Cada ponto compara um indicador a uma régua ajustável em Preferências, recebe uma "
        f"gravidade e um impacto em reais, e traz a decisão sugerida e a tela onde agir. Sem "
        f"o livro de movimentação, são {len(ins_antes)} pontos; com ele, entram mais "
        f"{len(ins) - len(ins_antes)}, de estoque e validade.")
    fig = go.Figure()
    for nivel in ("crit", "aten", "info", "ok"):
        v = [diag_antes["contagem"][nivel], diag["contagem"][nivel]]
        fig.add_trace(go.Bar(x=["Só cotações", "Cotações + movimentação"], y=v, name=Dc.PLURAL[nivel],
                             marker_color=COR_NIVEL[nivel], text=v, textposition="inside"))
    fig.update_layout(barmode="stack", yaxis_title="pontos avaliados")
    R.figura(salvar(fig, "d01_gravidade", altura=380, largura=820),
             "Pontos do apoio à decisão por gravidade", FONTE_SIM, 13)
    nat = {"real": "observado", "estimado": "estimado"}
    ordem = {"crit": 0, "aten": 1, "info": 2, "ok": 3}
    R.tabela(pd.DataFrame([(i.id, i.titulo, Dc.NIVEIS[i.nivel], i.valor,
                            brl(i.impacto) if i.impacto else "—",
                            "simulado" if i.simulado else nat.get(i.natureza, i.natureza))
                           for i in sorted(ins, key=lambda x: (ordem[x.nivel], -x.impacto))],
                          columns=["Id", "Ponto", "Gravidade", "Leitura", "Impacto", "Natureza"]),
             "Os pontos avaliados pelo motor de decisão, por gravidade e impacto", FONTE_SIM,
             larguras=[1.1, 5.6, 2, 3.2, 2.4, 2])
    top_i = sorted([i for i in ins if i.impacto > 0], key=lambda x: -x.impacto)[:14]
    fig = go.Figure(go.Bar(y=[f"{i.titulo} ({i.id})" for i in top_i], x=[i.impacto for i in top_i],
                           orientation="h", marker_color=[COR_NIVEL[i.nivel] for i in top_i],
                           text=[brl(i.impacto) for i in top_i], textposition="outside", cliponaxis=False))
    fig.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(tickprefix="R$ ", tickformat=",.0f",
                      range=[0, max(i.impacto for i in top_i) * 1.22]))
    R.figura(salvar(fig, "d02_valor_por_ponto", altura=560),
             "Valor em reais dos pontos (laranja = crítico, âmbar = atenção, verde = saudável)",
             FONTE_SIM)
    acion = diag["acionaveis"][:3]
    R.p("O plano de ação ordena os pontos críticos e em atenção pelo impacto. As três primeiras "
        "prioridades da base atual são:", "Exemplo de leitura.")
    R.tabela(pd.DataFrame([(n + 1, i.titulo, i.valor, brl(i.impacto), i.acao)
                           for n, i in enumerate(acion)],
                          columns=["#", "Ponto", "Leitura", "Valor", "O que fazer"]),
             "As três prioridades do plano de ação", FONTE_SIM, larguras=[0.8, 3.6, 2.6, 2.2, 7.3])
    # cascata do resultado
    mapa = __import__("paginas.compras", fromlist=["mapa_financeiro"]).mapa_financeiro(ins, mv)
    ganhos = mapa[mapa["grupo"] == "Ganho possível"]
    passos = [("Vendas", res["faturamento"], "total", "total", ""),
              ("Custo do que foi vendido", res["cmv"], "subtrai", "neutro", ""),
              ("Margem bruta", res["margem"], "total", "total", ""),
              ("Perdas por validade", res["perda_valor"], "subtrai", "ruim", ""),
              ("Margem após perdas", res["margem"] - res["perda_valor"], "total", "total", "")]
    pot = res["margem"] - res["perda_valor"]
    curto = {"Comprar do fornecedor mais barato": "Troca de fornecedor",
             "Renegociar custos que subiram": "Renegociação de custos",
             "Devolver ou remarcar lotes antes de vencer": "Lotes devolvidos ou remarcados"}
    for _, g in ganhos.iterrows():
        passos.append((g["item"], g["valor"], "soma", "bom", "estimado"))
        pot += g["valor"]
    passos.append(("Resultado com os ganhos", pot, "total", "total", ""))
    fig = T.cascata(passos, None, rotulos_curtos=curto)
    R.figura(salvar(fig, "d03_cascata_resultado", altura=520),
             "Composição do resultado do período, com os ganhos possíveis (estimados)", FONTE_SIM)
    R.p(f"Das vendas de {brl(res['faturamento'])}, a margem bruta é de {brl(res['margem'])} "
        f"({pct(res['margem_pct'])}); as perdas por validade levam {brl(res['perda_valor'])}. As "
        f"ações sugeridas pelo sistema — trocar de fornecedor, renegociar custos e devolver ou "
        f"remarcar lotes — somam {brl(ganhos['valor'].sum())} estimados, elevando o resultado "
        f"para {brl(pot)}.")
    # sensibilidade às réguas
    def pontos(params):
        return {i.id: i for i in Dc.gerar(df, M.curva_abc(df, params), params,
                                          MV.para_decisao(rec, mov, params))}
    padrao = pontos(p)
    sens = []
    for campo, novo, rot in (("validade_risco_meses", 12, "Risco de validade: 6 → 12 meses"),
                             ("concentracao_fornecedor", 0.30, "Concentração crítica: 40% → 30%"),
                             ("margem_baixa", 0.30, "Margem apertada: 25% → 30%"),
                             ("alta_custo_relevante", 0.10, "Alta de custo relevante: 15% → 10%")):
        alt = pontos(Parametros(**{campo: novo}))
        for pid, i in alt.items():
            a = padrao.get(pid)
            if a and (a.nivel != i.nivel or abs(a.impacto - i.impacto) > 0.5 or a.valor != i.valor):
                def leitura(x):
                    return (f"{Dc.NIVEIS[x.nivel]} · {x.valor}"
                            + (f" · {brl(x.impacto)}" if x.impacto else ""))
                sens.append((rot, i.titulo, leitura(a), leitura(i)))
    if sens:
        R.p("Cada régua de Preferências muda os pontos que dependem dela, o que permite ao gestor "
            "calibrar o sistema ao porte e ao perfil da farmácia:", "Reação às réguas.")
        R.tabela(pd.DataFrame(sens[:12], columns=["Régua alterada", "Ponto", "Antes", "Depois"]),
                 "Efeito de mudanças de régua sobre os pontos", FONTE_SIM, larguras=[4.5, 4.5, 3.6, 3.6])
    for arq, tit_ in (("t07_apoio_decisao.png", "Tela Sistema de Apoio à Decisão"),
                      ("t08_apoio_pontos.png", "Plano de ação: decisões em ordem de impacto financeiro")):
        if (TELAS / arq).exists():
            R.figura(TELAS / arq, tit_, "Fonte: captura do sistema.", 15.5)

    # ================================================================== 6. precisão
    R.quebra()
    R.h1("6. Precisão das previsões e dos pedidos")
    R.p("A precisão foi medida por teste no histórico (backtesting): para cada mês, a previsão "
        "é refeita usando só os meses anteriores e comparada ao que aconteceu. O erro relativo "
        "mediano é a métrica principal das previsões mensais; para a demanda por item usa-se o "
        "WAPE (erro absoluto ponderado pelo volume).")
    # 6.1 atendimento
    R.h2("6.1 Atendimento dos pedidos: cotado, pedido e faturado")
    funil = df[["Qtde. Cot", "Qtde. Resp", "Qtde. Ped.", "Qtde. Fat."]].sum()
    fig = go.Figure(go.Bar(x=["Cotado", "Respondido", "Pedido", "Faturado"], y=funil.values,
                           marker_color=[C["blue_l"], C["blue_l"], COR_OBS, C["green"]],
                           text=[num(v) for v in funil.values], textposition="outside"))
    fig.update_layout(yaxis=dict(title="unidades", range=[0, funil.max() * 1.15]))
    R.figura(salvar(fig, "e01_funil_pedidos", altura=360, largura=820),
             "Unidades cotadas, respondidas, pedidas e faturadas", FONTE_OBS, 13)
    R.p(f"Das unidades pedidas, {pct(ind.nivel_atendimento)} foram faturadas; o valor faturado "
        f"({brl(ind.valor_faturado)}) difere do pedido ({brl(ind.valor_pedido)}) em "
        f"{pct(ind.valor_faturado / ind.valor_pedido - 1, 2)}. A resposta das cotações foi de "
        f"{pct(funil['Qtde. Resp'] / funil['Qtde. Cot'], 2)} das unidades cotadas. Atenção: a "
        f"regra de limpeza mantém só pedidos com status Faturado, e por isso o atendimento "
        f"fica em 100% por construção. Para medir cortes de entrega, os status Faturado "
        f"Parcialmente e Enviado precisam entrar na base (limitação registrada).",
        "Precisão dos pedidos.")
    # 6.2 orçamento
    R.h2("6.2 Orçamento do próximo mês (pelas compras)")
    orc = PV.orcamento(df)
    t = orc["teste"]
    fig = go.Figure()
    x = [mes(m_) for m_ in t["mes"].astype(str)]
    fig.add_trace(go.Scatter(x=x + x[::-1], y=list(t["faixa_max"]) + list(t["faixa_min"])[::-1],
                             fill="toself", fillcolor=COR_OBS + "22", line=dict(width=0),
                             name="Faixa prevista", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=t["previsto"], name="Previsto", mode="lines",
                             line=dict(color=COR_OBS, dash="dot")))
    fig.add_trace(go.Scatter(x=x, y=t["real"], name="Realizado", mode="lines+markers",
                             line=dict(color=C["ink"], width=2)))
    fig.update_layout(yaxis=dict(tickprefix="R$ ", tickformat=",.0f"))
    R.figura(salvar(fig, "e02_backtest_orcamento"),
             "Teste no histórico do orçamento mensal de compras (faixa = média ± desvio)", FONTE_OBS)
    R.p(f"Em {len(t)} meses de teste, o gasto real caiu dentro da faixa prevista em "
        f"{pct(orc['acerto_faixa'])} dos meses, com erro mediano de {pct(orc['erro_mediano'])}. "
        f"Para agosto de 2026, o orçamento de referência é {brl(orc['media'])} (faixa de "
        f"{brl(orc['faixa_min'])} a {brl(orc['faixa_max'])}). O erro alto reflete compras em "
        f"lotes e meses de pico; serve como teto de caixa, não como valor exato.")
    # 6.3 itens candidatos
    R.h2("6.3 Itens sugeridos para a próxima cotação")
    conf = PV.resumo_confiabilidade(PV.confiabilidade(df, p))
    fx_ = conf["faixas"]
    base_rate = fx_["confirmados"].sum() / fx_["previstos"].sum()
    fig = go.Figure(go.Bar(x=["Chance alta", "Chance média", "Chance baixa"],
                           y=[fx_.loc[k, "taxa"] for k in ("alta", "média", "baixa")],
                           marker_color=[C["green"], C["blue"], C["blue_l"]],
                           text=[pct(fx_.loc[k, "taxa"]) for k in ("alta", "média", "baixa")],
                           textposition="outside"))
    fig.add_hline(y=base_rate, line=dict(color=C["ink3"], dash="dot"),
                  annotation_text=f"média geral {pct(base_rate)}", annotation_position="top right")
    fig.update_layout(yaxis=dict(tickformat=".0%", title="itens confirmados no mês seguinte",
                                 range=[0, fx_["taxa"].max() * 1.35]))
    R.figura(salvar(fig, "e03_confirmacao_candidatos", altura=380, largura=820),
             "Itens recomendados que foram de fato comprados no mês seguinte, por faixa de chance",
             FONTE_OBS, 13)
    R.p(f"A faixa de chance alta se confirma em {pct(fx_.loc['alta', 'taxa'])} dos casos, "
        f"{num(fx_.loc['alta', 'taxa'] / fx_.loc['baixa', 'taxa'], 1)} vezes a faixa baixa "
        f"({pct(fx_.loc['baixa', 'taxa'])}): a ordenação funciona. Ainda assim, "
        f"{pct(conf['itens_novos'])} dos itens de cada mês são compras novas, que nenhum "
        f"histórico antecipa — por isso a lista é um ponto de partida para a cotação, não um "
        f"pedido pronto.")
    # 6.4 vendas
    R.h2("6.4 Faturamento do mês (pelas vendas)")
    pv = MV.previsao_vendas(rec)
    met = pv["metodos"].sort_values("erro_mediano")
    fig = go.Figure(go.Bar(y=met["metodo"], x=met["erro_mediano"], orientation="h",
                           marker_color=[C["green"] if m_ == pv["melhor"] else C["blue_l"] for m_ in met["metodo"]],
                           text=[pct(v) for v in met["erro_mediano"]], textposition="outside"))
    fig.update_layout(yaxis=dict(autorange="reversed"),
                      xaxis=dict(tickformat=".0%", range=[0, met["erro_mediano"].max() * 1.3],
                                 title="erro relativo mediano (menor é melhor)"))
    R.figura(salvar(fig, "e04_metodos_vendas", altura=340, largura=900),
             "Erro de cada método de previsão do faturamento mensal", FONTE_SIM, 14)
    tv = pv["teste"][pv["teste"]["metodo"] == pv["melhor"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[mes(m_) for m_ in tv["mes"]], y=tv["real"], name="Realizado",
                             mode="lines+markers", line=dict(color=C["ink"])))
    fig.add_trace(go.Scatter(x=[mes(m_) for m_ in tv["mes"]], y=tv["previsto"],
                             name=f"Previsto ({pv['melhor'].lower()})", mode="lines",
                             line=dict(color=COR_SIM, dash="dot", width=2.4)))
    fig.update_layout(yaxis=dict(tickprefix="R$ ", tickformat=",.0f"))
    R.figura(salvar(fig, "e05_backtest_vendas"), "Teste no histórico da previsão de faturamento",
             FONTE_SIM)
    pf = MV.projecao_fechamento(rec)
    R.p(f"O método escolhido pelo teste foi \"{pv['melhor']}\", com erro mediano de "
        f"{pct(met.iloc[0]['erro_mediano'])}. A projeção de fechamento de {mes(pf['mes'])} "
        f"soma o realizado ({brl(pf['realizado']['vendas'])} em {pf['dias_feitos']} dias) ao "
        f"ritmo dos últimos 30 dias: {brl(pf['curso']['vendas'])}. Para {mes(pf['proximo_mes'])}, "
        f"{brl(pf['proximo']['vendas'])}, com faixa de ± {pct(met.iloc[0]['erro_mediano'], 0)}.")
    # 6.5 demanda por item
    R.h2("6.5 Demanda por item (WAPE)")
    td = MV.teste_demanda(rec, p)
    w = [("Sazonal (usado no sistema)", td["wape"].mean()), ("Média simples", td["wape_media"].mean()),
         ("Ingênuo (repete o último mês)", td["wape_ingenuo"].mean())]
    fig = go.Figure(go.Bar(x=[a for a, _ in w], y=[b for _, b in w],
                           marker_color=[C["green"], C["blue_l"], C["blue_l"]],
                           text=[pct(b) for _, b in w], textposition="outside"))
    fig.update_layout(yaxis=dict(tickformat=".0%", range=[0, max(b for _, b in w) * 1.2],
                                 title="WAPE da demanda de 30 dias"))
    R.figura(salvar(fig, "e06_wape", altura=360, largura=820),
             "Erro da previsão de demanda por item em 30 dias (WAPE)", FONTE_SIM, 13)
    vies = td["previsto"].sum() / td["real"].sum() - 1
    R.p(f"Item a item, o erro é alto (WAPE de {pct(td['wape'].mean())}), como é típico em itens "
        f"de venda baixa e irregular: a maioria dos medicamentos é Z. O método sazonal "
        f"supera o ingênuo e tem viés de {pct(vies)} no total. Por isso a reposição usa estoque "
        f"de segurança proporcional à variabilidade, e não só a média.")
    # 6.6 reposição e lote
    R.h2("6.6 Reposição, lote econômico e dente de serra")
    lec = MV.lote_economico(pos, rec, p)
    pol = pos["politica"].value_counts()
    leit = lec["leitura"].value_counts()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=list(pol.index), y=list(pol.values), marker_color=COR_SIM,
                         text=[num(v) for v in pol.values], textposition="outside", name="Política"))
    fig.update_layout(yaxis=dict(title="produtos", range=[0, pol.max() * 1.18]), showlegend=False)
    R.figura(salvar(fig, "e07_politicas", altura=340, largura=820),
             "Política de reposição atribuída a cada produto", FONTE_SIM, 13)
    repor = pos[pos["repor_agora"]]
    R.p(f"{num(pol.get('ponto de pedido', 0))} produtos seguem o ponto de pedido; "
        f"{num(len(repor))} já estão nele, com compra sugerida de "
        f"{brl(repor['valor_sugerido'].sum())}. Comparando o lote que a farmácia compra com o "
        f"lote econômico de Harris (limitado a {p.mov_cobertura_excesso} dias de venda por causa "
        f"da validade): {num(leit.get('compra acima do lote econômico', 0))} produtos compram "
        f"acima do recomendado, {num(leit.get('compra próxima do lote econômico', 0))} próximo e "
        f"{num(leit.get('compra abaixo do lote econômico', 0))} abaixo — lotes grandes explicam "
        f"parte do capital parado e das perdas.")
    cand = lec[lec["politica"] == "ponto de pedido"].sort_values("demanda_anual", ascending=False)
    if len(cand):
        l0 = cand.iloc[0]
        tr = MV.trajetoria(rec, l0["ean"])
        tr = tr[tr["data"] >= tr["data"].max() - pd.Timedelta(days=180)]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=tr["data"], y=tr["saldo"], mode="lines", line_shape="hv",
                                 name="Saldo que aconteceu", line=dict(color=COR_SIM, width=2.2)))
        ent = tr[tr["entrada"].notna()]
        fig.add_trace(go.Scatter(x=ent["data"], y=ent["saldo"], mode="markers", name="Compra recebida",
                                 marker=dict(color=C["teal"], size=9)))
        for val, rot, cor, traco in ((l0["estoque_maximo"], "máximo", C["blue"], "dot"),
                                     (l0["ponto_pedido"], "ponto de pedido", C["amber"], "dash"),
                                     (l0["estoque_minimo"], "mínimo", C["red"], "dot")):
            fig.add_hline(y=val, line=dict(color=cor, dash=traco, width=1.6),
                          annotation_text=f"{rot}: {num(val)} un", annotation_position="top left")
        fig.update_layout(yaxis_title="unidades", xaxis=dict(tickformat="%d/%m/%y"))
        R.figura(salvar(fig, "e08_dente_serra", altura=420),
                 f"Dente de serra de {l0['medicamento'][:40]} (últimos 180 dias)", FONTE_SIM)
        R.p(f"LEC de {num(l0['lec'])} un, lote praticado de {num(l0['lote_praticado'])} un, ponto "
            f"de pedido de {num(l0['ponto_pedido'])} un. O gráfico mostra quando o saldo real "
            f"ficou acima do máximo recomendado — estoque que imobiliza caixa e se aproxima do "
            f"vencimento.", "Exemplo.")
    for arq, tit_ in (("t09_previsao_fechamento.png", "Tela Previsão de Compras › Pelas vendas"),
                      ("t10_dente_serra.png", "Tela Reposição e Lotes: dente de serra e lote econômico")):
        if (TELAS / arq).exists():
            R.figura(TELAS / arq, tit_, "Fonte: captura do sistema.", 15.5)

    # ================================================================== 7. estoque
    R.quebra()
    R.h1("7. Estoque, giro e perdas por validade")
    pt = MV.ponte_estoque(rec)
    fig = T.cascata([("Estoque de partida", pt["valor_inicial"], "total", "total", ""),
                     ("Compras recebidas", pt["valor_entradas"], "soma", "neutro", ""),
                     ("Custo do que foi vendido", pt["cmv"], "subtrai", "bom", ""),
                     ("Perdas por validade", pt["valor_perdas"], "subtrai", "ruim", ""),
                     ("Estoque de chegada", pt["valor_final"], "total", "total", "")], None,
                    horizontal=False)
    R.figura(salvar(fig, "f01_ponte_estoque", altura=440),
             "Ponte do estoque a custo: partida + compras − custo vendido − perdas = chegada", FONTE_SIM)
    R.tabela(pd.DataFrame([
        ("Giro do estoque", f"{num(pt['giro'], 2)}×", "custo vendido ÷ estoque médio"),
        ("Dias de estoque", f"{num(pt['dias_estoque'])} dias", "estoque médio ÷ custo vendido por dia"),
        ("Cobertura na chegada", f"{num(pt['cobertura_final'])} dias", "estoque final ÷ custo vendido por dia"),
        ("Escoamento", pct(pt["escoamento"]), "unidades vendidas ÷ (partida + compras)"),
        ("Perda sobre o disponível", pct(pt["perda_disponivel"]), "unidades vencidas ÷ (partida + compras)"),
        ("Margem bruta", pct(res["margem_pct"]), "(vendas − custo vendido) ÷ vendas"),
        ("Perda ÷ faturamento", pct(res["perda_pct"]), "perdas a custo ÷ faturamento"),
        ("Diferença da ponte", brl(pt["diferenca"], 2), "deve ser zero (fecha centavo a centavo)"),
    ], columns=["Indicador", "Valor", "Fórmula"]), "Indicadores de estoque do período", FONTE_SIM,
        larguras=[4.5, 3, 8.5])
    causas = MV.causas_perdas(rec, df)
    cs = causas.groupby("causa")["valor"].sum().reindex(MV.CAUSAS_PERDA).fillna(0)
    fig = go.Figure(go.Bar(y=cs.index, x=cs.values, orientation="h",
                           marker_color=[C["blue_l"], C["red"], C["red"], C["red"], C["amber"], C["ink3"]],
                           text=[f"{brl(v)} ({pct(v / cs.sum(), 0)})" for v in cs.values],
                           textposition="outside", cliponaxis=False))
    fig.update_layout(yaxis=dict(autorange="reversed"),
                      xaxis=dict(tickprefix="R$ ", tickformat=",.0f", range=[0, cs.max() * 1.35]))
    R.figura(salvar(fig, "f02_causas_perdas", altura=380),
             "Perdas por validade por fator associado (um fator por lote)", FONTE_SIM)
    R.p(f"Das perdas de {brl(cs.sum())}, {brl(cs.get('Estoque de abertura', 0))} vêm do estoque "
        f"que já existia no início do livro. Entre as perdas de lotes comprados, os fatores "
        f"ligados à decisão de compra — lote maior que a venda até a validade, validade curta na "
        f"chegada e compra sem histórico — somam "
        f"{brl(cs[['Lote maior que a venda até a validade', 'Chegou com validade curta', 'Comprado sem histórico de venda']].sum())}. "
        f"São associações medidas nos dados, não prova de causa.")
    ref = MV.referencias(rec, pos, res, abc_v, p)
    def valor_ref(r_):
        if r_["unidade"] == "pct":
            return pct(r_["valor"])
        if r_["unidade"] == "dias":
            return f"{num(r_['valor'])} dias"
        return f"{num(r_['valor'], 2)}×"
    R.tabela(pd.DataFrame([(r_["indicador"], valor_ref(r_), r_["referencia"], r_["leitura"],
                            r_["fonte"])
                           for _, r_ in ref.iterrows()],
                          columns=["Indicador", "Valor", "Referência", "Leitura", "Fonte"]),
             "Indicadores comparados com a literatura", FONTE_SIM, larguras=[3.8, 1.9, 3.4, 1.6, 5.3])
    for arq, tit_ in (("t12_posicao_estoque.png", "Tela Posição de Estoque: o que pede atenção"),
                      ("t13_causas_perdas.png", "Tela Validade e Remarcação: causas das perdas")):
        if (TELAS / arq).exists():
            R.figura(TELAS / arq, tit_, "Fonte: captura do sistema.", 15.5)

    # ================================================================== 8. validação
    R.quebra()
    R.h1("8. Validação do sistema")
    R.p("A confiabilidade dos resultados foi verificada por testes automatizados, repetidos a "
        "cada mudança do código: dos cálculos isolados (verificar.py) às telas no navegador, "
        "passando por identidades contábeis que precisam fechar exatamente:")
    R.tabela(pd.DataFrame([
        ("verificar.py (16 blocos)", "cálculos contra valores esperados, filtros, importação, "
         "privacidade, login, exportação, réguas, movimentação, cadastro, cores", "aprovado"),
        ("Filtros combinados", "74 recortes (cada filtro, pares, trios, vazio) × 21 telas; "
         "545 conferências de soma e interseção", "545 de 545"),
        ("Consistência entre telas", "Visão Geral, Curva ABC, movimentação e apoio à decisão "
         "mostram os mesmos números em 14 recortes", "aprovado"),
        ("Testes de navegador", "16 telas, filtros, celular, tema escuro, botão de privacidade, "
         "cadastro manual numa cópia da base", "aprovado"),
        ("Ponte do estoque", "partida + compras − custo vendido − perdas = chegada",
         f"diferença {brl(pt['diferenca'], 2)}"),
        ("Causas das perdas", "soma dos fatores = perda total do período",
         f"{brl(cs.sum(), 2)} = {brl(res['perda_valor'], 2)}"),
        ("Coerência ficha × apoio", "economia por troca de fornecedor igual nas duas telas", "25 de 25 itens"),
        ("Acessibilidade", "cores distinguíveis em 3 tipos de daltonismo; contraste ≥ 4,5:1",
         f"ΔE00 = {num(AC.menor_distancia(C['green'], C['red'])[0], 1)}"),
    ], columns=["Teste", "O que confere", "Resultado"]), "Testes de validação do sistema",
        "Fonte: execução dos testes em 25/10/2026.", larguras=[4, 9, 3])
    visoes = [(None, "Visão comum"), ("protanopia", "Protanopia"), ("deuteranopia", "Deuteranopia"),
              ("tritanopia", "Tritanopia")]
    fig = go.Figure()
    pares = [("Antes: verde × vermelho", "#4D8A70", "#B5625B"),
             ("Agora: verde × laranja", C["green"], C["red"])]
    for linha, (rot, c1, c2) in enumerate(pares):
        for col, (tipo, nome_v) in enumerate(visoes):
            x0 = col * 1.0
            for k, cor in enumerate((c1, c2)):
                fig.add_shape(type="rect", x0=x0 + k * 0.42, x1=x0 + k * 0.42 + 0.4,
                              y0=-linha - 0.42, y1=-linha + 0.0,
                              fillcolor=_hex_simulado(cor, tipo), line=dict(width=0))
            d = AC.distancia(c1, c2, tipo)
            fig.add_annotation(x=x0 + 0.41, y=-linha - 0.55, text=f"ΔE00 = {num(d, 1)}", showarrow=False,
                               font=dict(size=12, color=C["ink"]))
            if linha == 0:
                fig.add_annotation(x=x0 + 0.41, y=0.18, text=f"<b>{nome_v}</b>", showarrow=False,
                                   font=dict(size=13))
        fig.add_annotation(x=-0.08, y=-linha - 0.21, text=f"<b>{rot}</b>", showarrow=False,
                           xanchor="right", font=dict(size=12.5))
    fig.update_layout(xaxis=dict(visible=False, range=[-1.25, 4.0]),
                      yaxis=dict(visible=False, range=[-1.75, 0.35]), showlegend=False)
    R.figura(salvar(fig, "g01_daltonismo", altura=330, largura=1100),
             "Cores de benefício × prejuízo vistas em cada tipo de daltonismo (simulação)",
             "Fonte: elaboração própria; simulação de Machado, Oliveira e Fernandes (2009).")
    R.p("A paleta anterior ficava quase igual para quem tem protanopia (ΔE00 7,6); a atual "
        "separa as duas cores em todos os tipos simulados, e a cor vem sempre acompanhada de "
        "seta, sinal ou rótulo.")

    # ================================================================== 9. discussão
    R.quebra()
    R.h1("9. Discussão: o que levar para o TCC")
    R.h2("9.1 Principais achados")
    R.lista([
        ("Concentração do gasto:", f"{num(cl_c.loc['A', 'itens'])} medicamentos (classe A) "
         f"concentram {pct(cl_c.loc['A', 'pct_valor'])} das compras, mas os 20% maiores somam "
         f"{pct(abc_c.concentracao_20)} — curva mais achatada que a regra 80/20, típica de mix amplo."),
        ("Regularidade:", "as compras não revelam a regularidade do consumo (quase tudo Z); pelas "
         f"vendas, só {num(int(xyz_v.get('X', 0)))} itens são regulares, e {num(cont.loc['A', 'Z'])} "
         "itens A são irregulares e exigem acompanhamento."),
        ("Dependência de fornecedor:", f"o maior distribuidor responde por "
         f"{pct(M.por_dimensao(df, 'Nome do Fornecedor')['valor_pedido'].iloc[0] / ind.valor_pedido)} "
         "das compras, acima da régua de 40%."),
        ("Dinheiro em jogo:", f"o plano de ação lista {len(diag['acionaveis'])} pontos acionáveis; o "
         f"maior é o capital parado em estoque ({brl(padrao['v2'].impacto) if 'v2' in padrao else '—'}). "
         f"Os ganhos estimados somam {brl(ganhos['valor'].sum())}."),
        ("Precisão:", f"faturamento mensal previsto com erro mediano de {pct(met.iloc[0]['erro_mediano'])}; "
         f"orçamento de compras com {pct(orc['erro_mediano'])} — compras em lotes são menos "
         "previsíveis que vendas."),
        ("Perdas:", f"{pct(res['perda_pct'])} do faturamento, dentro da faixa de 1% a 3%, com "
         "fatores ligados ao tamanho do lote e à validade na chegada."),
    ])
    R.h2("9.2 Contribuições do projeto")
    R.lista([
        "Um sistema de apoio à decisão funcional, de baixo custo e instalação local, que usa dados "
        "que a farmácia já possui (as cotações eletrônicas).",
        "Integração entre a Curva ABC, a classificação XYZ e regras de reposição (ponto de pedido, "
        "estoque de segurança e lote econômico) num mesmo fluxo de decisão.",
        "Recomendações com impacto em reais, gravidade e ação, ajustáveis pelo gestor (réguas) e "
        "explicadas na própria tela (Conceitos e Cálculos).",
        "Medição explícita da precisão (teste no histórico) e separação entre valores observados, "
        "estimados e projetados.",
        "Verificação automatizada e cuidado com acessibilidade (daltonismo e contraste).",
    ])
    R.h2("9.3 Limitações")
    R.lista([
        ("Vendas simuladas:", "giro, cobertura, perdas, XYZ pelas vendas e previsão de faturamento "
         "dependem do livro de movimentação simulado; os resultados mostram como o sistema decide "
         "e passam a medir a farmácia quando as vendas do caixa forem carregadas."),
        ("Status dos pedidos:", "a base mantém só pedidos faturados, o que deixa o atendimento em "
         "100% por construção."),
        ("Preço de venda:", "a margem usa o preço registrado na cotação; reprecificações "
         "posteriores não entram."),
        ("Erros de cadastro:", "itens com custos muito diferentes entre fornecedores são separados "
         "e ficam fora da economia estimada."),
        ("Associação, não causa:", "os fatores das perdas são associações medidas nos dados."),
    ])
    R.h2("9.4 Trabalhos futuros")
    R.lista([
        "Carregar as vendas reais do sistema de caixa no layout do livro de movimentação.",
        "Incluir os pedidos parcialmente faturados para medir cortes de entrega.",
        "Hospedagem com acesso seguro (HTTPS e login gerenciado) para uso em mais de um computador.",
        "Integração com a nota fiscal eletrônica para atualizar a base sem importação manual.",
    ])

    # ================================================================== apêndice
    R.quebra()
    R.h1("Apêndice A — Fórmulas principais")
    R.tabela(pd.DataFrame([
        ("Valor pedido", "Qtde. pedida × custo unitário"),
        ("Curva ABC", f"classe A até {pct(p.corte_a, 0)} do valor acumulado; B até {pct(p.corte_b, 0)}; C o restante"),
        ("Concentração de Pareto", "valor dos 20% maiores itens ÷ valor total"),
        ("Coeficiente de variação (XYZ)", "desvio-padrão ÷ média das vendas mensais; X ≤ 0,50; Y ≤ 1,00; Z acima"),
        ("Margem bruta", "(vendas − custo do que foi vendido) ÷ vendas"),
        ("Giro do estoque", "custo vendido ÷ ((estoque de partida + de chegada) ÷ 2)"),
        ("Estoque de segurança", "z × desvio da venda diária × √prazo de entrega"),
        ("Ponto de pedido", "demanda prevista × prazo + estoque de segurança"),
        ("Lote econômico (Harris)", "√(2 × demanda anual × custo de pedir ÷ custo de manter), limitado pela validade"),
        ("Economia por troca", "Σ máx(0, custo pago − menor custo médio do item) × quantidade"),
        ("Erro relativo mediano", "mediana de |previsto − real| ÷ real nos meses de teste"),
        ("WAPE", "Σ |previsto − real| ÷ Σ real, por item"),
        ("ΔE00 (CIEDE2000)", "distância perceptual entre duas cores; < 10 = fáceis de confundir"),
    ], columns=["Conceito", "Fórmula"]), "Fórmulas usadas nos resultados",
        "Fonte: Conceitos e Cálculos do SADPF e documentação técnica.", larguras=[5, 11])
    R.h1("Apêndice B — Telas do sistema")
    for arq, tit_ in (("t02_movimentacoes.png", "Visão Geral › Movimentações do período"),
                      ("t03_prioridades.png", "Visão Geral › Prioridades"),
                      ("t04_tendencias.png", "Visão Geral › Tendências"),
                      ("t11_ficha_medicamento.png", "Ficha do medicamento com cartões de ação"),
                      ("t14_conceitos.png", "Conceitos e Cálculos")):
        if (TELAS / arq).exists():
            R.figura(TELAS / arq, tit_, "Fonte: captura do sistema.", 15.5)

    arq = R.salvar(SAIDA / "SADPF_Resultados_TCC.docx")
    print(f"documento: {arq} · {R.n_fig} figuras · {R.n_tab} tabelas · "
          f"{len(list(FIG.glob('*.png')))} gráficos gerados")


if __name__ == "__main__":
    try:
        main()
    finally:
        _fechar_navegador()
