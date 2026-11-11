"""
SADPF — Sistema de Apoio à Decisão para Pequenas Farmácias
==========================================================

Versão Python (Streamlit + Plotly + pandas) do painel de gestão de compras,
estoque e apoio à decisão, construída sobre a base de cotações eletrônicas.

Como rodar:
    pip install -r requirements.txt
    python verificar.py          # confere ambiente e cálculos, sem abrir nada
    streamlit run app.py

A base consolidada fica em dados/base_consolidada.csv e é criada na primeira
execução a partir de dados/cotacao_06_09.xlsx. Cotações novas entram pela aba
Base de Dados.
"""
from __future__ import annotations

import sys
import unicodedata
from dataclasses import asdict
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from core import dados as D              # noqa: E402
from core import memoria                 # noqa: E402
from core import metricas as M           # noqa: E402
from core import movimentacao as MV       # noqa: E402
from core import parametros as PR        # noqa: E402
from core import tema as T               # noqa: E402
from paginas import (acesso, analitico, apoio_decisao,  # noqa: E402
                     cadastros, compras, gestao, movimentacao, previsao,
                     tutoriais)

SECOES = [
    "Visão Geral",
    "Gestão de Compras", "Pedidos", "Fornecedores", "Medicamentos",
    *movimentacao.TELAS,
    "Curva ABC",
    "Análises e Indicadores", "Previsão de Compras", "Sistema de Apoio à Decisão",
    "Conceitos e Cálculos", "Tutoriais", "Preferências", "Base de Dados",
]

GRUPOS = {
    "Compras": ["Gestão de Compras", "Pedidos", "Fornecedores", "Medicamentos"],
    "Movimentação": movimentacao.TELAS,
    "Análise e decisão": ["Curva ABC", "Análises e Indicadores", "Previsão de Compras",
                          "Sistema de Apoio à Decisão"],
    "Referência": ["Conceitos e Cálculos", "Tutoriais", "Preferências", "Base de Dados"],
}

# ícones do menu lateral (Material Symbols, já incluídos no Streamlit)
ICONES = {
    "Visão Geral": ":material/home:",
    "Gestão de Compras": ":material/shopping_cart:",
    "Pedidos": ":material/receipt_long:",
    "Fornecedores": ":material/local_shipping:",
    "Medicamentos": ":material/medication:",
    **movimentacao.ICONES,
    "Curva ABC": ":material/bar_chart:",
    "Análises e Indicadores": ":material/monitoring:",
    "Previsão de Compras": ":material/event_upcoming:",
    "Sistema de Apoio à Decisão": ":material/lightbulb:",
    "Conceitos e Cálculos": ":material/menu_book:",
    "Tutoriais": ":material/school:",
    "Preferências": ":material/settings:",
    "Base de Dados": ":material/database:",
}


def _slug(texto: str) -> str:
    """'Gestão de Compras' vira 'gestao-de-compras', para o endereço da página."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode()
    return "-".join(sem_acento.lower().split())


def grupo_de(secao: str) -> str:
    for grupo, itens in GRUPOS.items():
        if secao in itens:
            return grupo
    return secao


def iniciar_estado() -> None:
    # o tema sai do próprio controle da barra lateral, lido já no início: assim o
    # CSS é aplicado uma única vez por clique, com a cor certa
    st.session_state.setdefault("tema_escuro", False)
    st.session_state["tema"] = "escuro" if st.session_state["tema_escuro"] else "claro"
    st.session_state.setdefault("secao", "Visão Geral")
    st.session_state.setdefault("params", PR.carregar())
    st.session_state.setdefault("f_periodo", None)
    for chave in ("categorias", "cotacoes", "formas", "fornecedores",
                  "medicamentos", "status"):
        st.session_state.setdefault(f"f_{chave}", [])


FILTROS = {"categorias": "Categoria Comercial", "cotacoes": "Cotação",
           "formas": "Forma Farmacêutica", "fornecedores": "Nome do Fornecedor",
           "medicamentos": "Descrição do Produto", "status": "Status do Pedido"}


def carregar(forcar: bool = False) -> pd.DataFrame:
    """Base da sessão, relida sempre que o arquivo em disco mudar.

    Assim uma inclusão ou restauração feita em outra aba do navegador também
    chega aqui, em vez de a sessão seguir com a base antiga na memória.
    """
    versao = D.versao_base()
    if forcar or "base" not in st.session_state or \
            st.session_state.get("versao_base") != versao:
        try:
            base, origem = D.carregar_base()
        except FileNotFoundError:
            st.error("Nenhuma base de dados encontrada.")
            st.info(f"Coloque a planilha de cotações em `dados/{D.BASE_ORIGINAL.name}` e recarregue "
                    "a página. O modelo com as colunas e as instruções está em "
                    "`dados/modelo_cotacao.xlsx` (repositório do GitHub) ou no botão *Baixar o "
                    "modelo de importação* da tela Base de Dados.")
            st.stop()
        except ValueError as erro:
            st.error(f"Não foi possível carregar a base: {erro}")
            st.stop()
        st.session_state["base"] = base
        st.session_state["origem"] = origem
        st.session_state["versao_base"] = D.versao_base()
    return st.session_state["base"]


def sincronizar_filtros(df: pd.DataFrame) -> None:
    """Ajusta os filtros guardados à base atual, antes de desenhá-los.

    Depois de incluir ou restaurar cotações, uma seleção pode apontar para um
    valor que não existe mais, e o período guardado pode deixar de fora as
    datas novas. Um período que cobria a base inteira passa a cobrir a nova.
    """
    for chave, coluna in FILTROS.items():
        atual = st.session_state.get(f"f_{chave}") or []
        if atual:
            validos = set(df[coluna].dropna().unique().tolist())
            st.session_state[f"f_{chave}"] = [v for v in atual if v in validos]

    limites = (df["dt"].min().date(), df["dt"].max().date())
    anteriores = st.session_state.get("f_limites")
    periodo = st.session_state.get("f_periodo")
    mudou = anteriores is not None and tuple(anteriores) != limites
    if periodo and mudou:
        if tuple(periodo) == tuple(anteriores):
            periodo = None
        else:
            inicio, fim = max(periodo[0], limites[0]), min(periodo[1], limites[1])
            periodo = (inicio, fim) if inicio <= fim else None
    st.session_state["f_periodo"] = periodo
    st.session_state["f_limites"] = limites
    # o campo de período guarda o próprio valor; só é reposto na primeira
    # abertura, depois de "Limpar filtros" ou quando a base muda de tamanho
    if "f_periodo_w" not in st.session_state or mudou:
        st.session_state["f_periodo_w"] = periodo or limites


def limpar_filtros() -> None:
    """Chamada pelo botão antes do script rodar de novo.

    O Streamlit não deixa alterar o valor de um filtro depois que ele já foi
    desenhado na tela; por isso a limpeza acontece aqui, no clique, e não no
    corpo do script (que era a causa do erro ao limpar os filtros).
    """
    for chave in FILTROS:
        st.session_state[f"f_{chave}"] = []
    st.session_state["f_periodo"] = None
    st.session_state.pop("f_periodo_w", None)


def sair() -> None:
    """Encerra o acesso: a sessão volta ao estado de quem acabou de abrir o painel."""
    for chave in list(st.session_state.keys()):
        del st.session_state[chave]


def traduzir_selecoes(mapas: dict, originais: bool) -> None:
    """Mantém os fornecedores escolhidos no filtro ao ligar ou desligar os nomes originais."""
    ida = mapas.get("Nome do Fornecedor", {})
    conversao = {v: k for k, v in ida.items()} if originais else ida
    atual = st.session_state.get("f_fornecedores") or []
    st.session_state["f_fornecedores"] = [conversao.get(v, v) for v in atual]


def base_para_exibir(df_original: pd.DataFrame) -> pd.DataFrame:
    """Base com os nomes originais ou codificados, conforme a Preferência."""
    p = st.session_state["params"]
    # o controle da tela Preferências vale já neste clique, sem esperar o próximo
    p.nomes_originais = bool(st.session_state.get("pref_nomes_originais", p.nomes_originais))
    mapas = D.apelidos(df_original)
    traduzir_selecoes(mapas, p.nomes_originais)
    return df_original if p.nomes_originais else D.anonimizar(df_original, mapas)


ROTULOS_FILTRO = {"categorias": "Categoria", "cotacoes": "Cotação", "formas": "Forma",
                  "fornecedores": "Fornecedor", "medicamentos": "Medicamento",
                  "status": "Status"}


def descrever_filtros(filtros: dict, periodo_ativo: bool) -> list[tuple[str, str]]:
    """Filtros em uso, como pares (rótulo, valores), para o resumo e os chips."""
    ativos = []
    if periodo_ativo:
        inicio, fim = filtros["periodo"]
        ativos.append(("Período", f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"))
    for chave, rotulo in ROTULOS_FILTRO.items():
        valores = [str(v) for v in filtros.get(chave) or []]
        if valores:
            texto = ", ".join(valores[:2]) + (f" +{len(valores) - 2}" if len(valores) > 2 else "")
            ativos.append((rotulo, texto))
    return ativos


def barra_lateral(df: pd.DataFrame) -> dict:
    """Empresa no topo, filtros globais abaixo do menu e Sair fixo no rodapé.

    A ordem visual (empresa acima do menu, Sair no fim) é feita no CSS de
    core/tema.py, a partir das chaves dos contêineres criados aqui.
    """
    sincronizar_filtros(df)
    with st.sidebar:
        with st.container(key="lateral_empresa"):
            st.markdown(
                "<div class='empresa-cartao'><span class='empresa-icone'>"
                "<span class='material-symbols-rounded' aria-hidden='true'>storefront</span></span>"
                "<span><small>Empresa conectada</small>"
                f"<b>{escape(st.session_state['usuario'])}</b></span></div>",
                unsafe_allow_html=True)

        st.toggle(":material/dark_mode: Tema escuro", key="tema_escuro")
        st.markdown("<div class='lateral-tit filtros-tit'>Filtros globais</div>",
                    unsafe_allow_html=True)
        resumo = st.empty()      # preenchido depois de ler os filtros

        minimo, maximo = df["dt"].min().date(), df["dt"].max().date()
        # campos e opções em ordem alfabética, como no painel HTML
        todos = "Todos"
        categorias = st.multiselect("Categoria comercial",
                                    D.opcoes(df, "Categoria Comercial"), key="f_categorias",
                                    placeholder=todos)
        cotacoes = st.multiselect("Cotação", sorted(df["Cotação"].unique().tolist()),
                                  key="f_cotacoes", placeholder=todos)
        formas = st.multiselect("Forma farmacêutica",
                                D.opcoes(df, "Forma Farmacêutica"), key="f_formas",
                                placeholder=todos)
        fornecedores = st.multiselect("Fornecedor",
                                      D.opcoes(df, "Nome do Fornecedor"), key="f_fornecedores",
                                      placeholder=todos)
        medicamentos = st.multiselect("Medicamento",
                                      D.opcoes(df, "Descrição do Produto"),
                                      key="f_medicamentos", placeholder="Todos — digite para buscar",
                                      help="Digite para buscar entre os medicamentos.")
        periodo = st.date_input("Período", min_value=minimo, max_value=maximo,
                                format="DD/MM/YYYY", key="f_periodo_w",
                                help="Clique na data inicial e depois na final.")
        status = st.multiselect("Status do pedido",
                                D.opcoes(df, "Status do Pedido"), key="f_status",
                                placeholder=todos)

        if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
            inicio, fim = periodo
            # período inteiro = sem filtro: acompanha a base se ela crescer
            st.session_state["f_periodo"] = (None if (inicio, fim) == (minimo, maximo)
                                             else (inicio, fim))
        else:
            # só a data inicial foi escolhida: mantém o último período completo
            inicio, fim = st.session_state.get("f_periodo") or (minimo, maximo)

        filtros = {"periodo": (inicio, fim), "categorias": categorias, "cotacoes": cotacoes,
                   "formas": formas, "fornecedores": fornecedores,
                   "medicamentos": medicamentos, "status": status}
        ativos = descrever_filtros(filtros, st.session_state["f_periodo"] is not None)
        st.session_state["filtros_ativos"] = ativos

        # confirmação visual: quantos filtros estão valendo, e o período em destaque
        if ativos:
            resumo.markdown(
                f"<div class='filtros-resumo ativo'><b>{len(ativos)}</b> "
                f"{'filtro ativo' if len(ativos) == 1 else 'filtros ativos'} em todas as "
                "telas</div>", unsafe_allow_html=True)
        else:
            resumo.markdown("<div class='filtros-resumo'>Nenhum filtro ativo: as telas "
                            "mostram a base inteira. Sem seleção = todos.</div>",
                            unsafe_allow_html=True)
        if st.session_state["f_periodo"] is not None:
            st.markdown("<style>.st-key-f_periodo_w [data-testid='stDateInputField']"
                        "{border-color:#7FBEE3 !important;box-shadow:inset 3px 0 0 #7FBEE3}"
                        ".st-key-f_periodo_w label p{color:#fff !important}</style>",
                        unsafe_allow_html=True)

        st.button(f"Limpar filtros ({len(ativos)})" if ativos else "Limpar filtros",
                  width="stretch", on_click=limpar_filtros, disabled=not ativos,
                  icon=":material/filter_alt_off:", key="limpar_filtros")
        st.caption(f"Base: {df['Cotação'].nunique()} cotações · {len(df):,} linhas"
                   .replace(",", "."))

        with st.container(key="lateral_sair"):
            st.button("Sair", icon=":material/logout:", width="stretch", on_click=sair,
                      key="botao_sair")

    return filtros


def preparar_movimentacao(df_original: pd.DataFrame, recorte: pd.DataFrame,
                          filtros: dict) -> None:
    """Livro de movimentação limitado aos mesmos filtros das outras telas.

    O período vale como está; os demais filtros (fornecedor, categoria, forma,
    medicamento, cotação, status) escolhem produtos, e o livro fica com os
    produtos que sobraram no recorte de compras.
    """
    mov = MV.carregar()
    if mov is None:
        st.session_state["mov_rec"] = st.session_state["mov_full"] = None
        return
    p = st.session_state["params"]
    chave = (MV.versao(), p.nomes_originais)
    if st.session_state.get("_mov_chave") != chave:
        # fornecedores com os mesmos códigos das outras telas, salvo a Preferência
        st.session_state["_mov_exibir"] = (mov if p.nomes_originais else
                                            MV.anonimizar(mov, D.apelidos(df_original)))
        st.session_state["_mov_chave"] = chave
    exibir = st.session_state["_mov_exibir"]
    produtos = any(filtros.get(k) for k in FILTROS)
    # os produtos saem dos filtros de produto SEM o período: o período já limita os
    # fluxos do livro. Com o período aqui, "categoria + período" perdia os itens que
    # venderam no período mas foram comprados antes dele, e as categorias deixavam de
    # somar o período (achado da revisão de 21/10/2026)
    if produtos:
        df_total = st.session_state.get("_df_total_filtros")
        sem_periodo = {k: v for k, v in filtros.items() if k != "periodo"}
        fonte = df_total if df_total is not None else recorte
        eans = MV.eans_do_recorte(D.aplicar_filtros(fonte, sem_periodo))
    else:
        eans = None
    periodo = st.session_state.get("f_periodo")
    inicio, fim = periodo if periodo else (None, None)
    st.session_state["mov_rec"] = MV.recortar(exibir, eans, inicio, fim)
    st.session_state["mov_full"] = exibir


def _pagina(secao: str, df_original: pd.DataFrame, recorte: pd.DataFrame):
    """Cria a função que o menu chama ao abrir a seção."""
    def abrir() -> None:
        renderizar(secao, df_original, recorte)
    return abrir


def montar_menu(df_original: pd.DataFrame, recorte: pd.DataFrame):
    """Menu lateral nativo, agrupado por categoria e com ícones."""
    def pagina(secao: str) -> st.Page:
        return st.Page(_pagina(secao, df_original, recorte), title=secao,
                       icon=ICONES[secao], url_path=_slug(secao),
                       default=secao == SECOES[0])

    paginas = {s: pagina(s) for s in SECOES}
    # as telas usam estas páginas para links internos (st.page_link)
    st.session_state["paginas_menu"] = paginas
    estrutura = {"": [paginas[SECOES[0]]]}
    for grupo, itens in GRUPOS.items():
        estrutura[grupo] = [paginas[s] for s in itens]
    return st.navigation(estrutura, position="sidebar", expanded=True)


def main() -> None:
    st.set_page_config(page_title="SADPF — Apoio à Decisão para Pequenas Farmácias",
                       page_icon=":material/local_pharmacy:", layout="wide",
                       initial_sidebar_state="auto")
    iniciar_estado()
    T.traduzir_interface()

    # sem login, só a tela de entrada existe: nada da base é lido nem mostrado.
    # O menu é registrado oculto, com os mesmos endereços, e todos levam à
    # entrada; assim quem abriu /curva-abc cai na Curva ABC depois de entrar
    if not st.session_state.get("usuario"):
        st.navigation([st.Page(acesso.tela_entrada, title=s, url_path=_slug(s),
                               default=s == SECOES[0]) for s in SECOES],
                      position="hidden").run()
        return

    st.logo(str(T.LOGO), size="large", icon_image=str(T.ICONE))
    T.aplicar_css()

    df_original = carregar()
    # fornecedores e representantes codificados, salvo se a Preferência pedir os originais
    df_total = base_para_exibir(df_original)

    filtros = barra_lateral(df_total)
    recorte = D.aplicar_filtros(df_total, filtros)
    st.session_state["_df_total_filtros"] = df_total
    # tudo de que o recorte e os cálculos dependem: enquanto não mudar, a Curva
    # ABC e o apoio à decisão são reaproveitados ao trocar de tela
    preparar_movimentacao(df_original, recorte, filtros)
    memoria.definir_assinatura(st.session_state.get("versao_base"), MV.versao(), filtros,
                               asdict(st.session_state["params"]))

    pagina = montar_menu(df_original, recorte)
    st.session_state["secao"] = pagina.title
    T.cabecalho(pagina.title, grupo_de(pagina.title))
    # tutoriais e base de dados não dependem dos filtros: ali a faixa confundiria
    if pagina.title not in ("Tutoriais", "Base de Dados"):
        T.filtros_aplicados(st.session_state.get("filtros_ativos", []))
    pagina.run()


def renderizar(secao: str, df_original: pd.DataFrame, recorte: pd.DataFrame) -> None:
    p = st.session_state["params"]

    if secao == "Tutoriais":
        tutoriais.tutoriais()
        return

    # telas da movimentação: usam o livro recortado pelos mesmos filtros (app.py
    # prepara em preparar_movimentacao). Validade e Remarcação usa também as
    # compras, e por isso é aberta mais abaixo, junto com as demais
    telas_mov = {movimentacao.POSICAO: movimentacao.posicao_estoque,
                 movimentacao.REPOSICAO: movimentacao.reposicao_lotes}
    if secao in telas_mov:
        telas_mov[secao](p)
        return

    # a aba de base não depende do recorte e trabalha sempre com os nomes
    # originais: é ela que grava, exporta e compara cotações novas
    if secao == "Base de Dados":
        nova = gestao.base_dados(df_original)
        if nova is not None:
            # relê do disco: a sessão passa a usar exatamente o que foi gravado
            carregar(forcar=True)
            st.rerun()
        return

    if recorte.empty:
        st.warning("Nenhuma linha atende aos filtros. Ajuste a seleção no menu lateral.")
        st.stop()

    abc = memoria.lembrar("abc", M.curva_abc, recorte, p)

    if secao == "Visão Geral":
        compras.visao_geral(recorte, abc, p)
    elif secao == "Gestão de Compras":
        compras.gestao_compras(recorte, abc, p)
    elif secao == "Pedidos":
        compras.pedidos(recorte, abc)
    elif secao == "Fornecedores":
        cadastros.fornecedores(recorte, abc)
    elif secao == "Medicamentos":
        cadastros.medicamentos(recorte, abc)
    elif secao == movimentacao.VALIDADE:
        movimentacao.validade_remarcacao(recorte, abc, p)
    elif secao == "Curva ABC":
        analitico.curva_abc(recorte, abc, p)
    elif secao == "Análises e Indicadores":
        analitico.analises(recorte, abc, p)
    elif secao == "Previsão de Compras":
        previsao.previsao(recorte, abc, p)
    elif secao == "Sistema de Apoio à Decisão":
        apoio_decisao.apoio_decisao(recorte, abc, p)
    elif secao == "Conceitos e Cálculos":
        gestao.conceitos(recorte, abc, p)
    elif secao == "Preferências":
        st.session_state["params"] = gestao.preferencias(recorte, abc, p)


if __name__ == "__main__":
    main()
