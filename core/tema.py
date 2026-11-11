"""
Identidade visual do SADPF.

Tons de cinza e azul-claro como base, com verde-azulado, roxo e verde de apoio.
Três cores ficam reservadas e não devem virar decoração: verde é benéfico ou
saudável, laranja-avermelhado ("red") é prejudicial ou crítico e âmbar é atenção.
A Curva ABC usa roxo em toda parte, para ser reconhecível de imediato.

Acessível a daltonismo: o par verde × laranja segue a paleta de Okabe e Ito
(verde puxado para o azul, vermelho puxado para o laranja), que continua
distinguível em protanopia, deuteranopia e tritanopia — a distância de cor
simulada (CIEDE2000) entre os dois fica acima de 17 nos três tipos; o verde e o
vermelho anteriores ficavam em 8 a 10, quase iguais. Setas, sinais (+/−), o
"(estimado)" no rótulo e a dica ao passar o mouse acompanham a cor.
"""
from __future__ import annotations

import numbers
import textwrap
from functools import lru_cache
from html import escape
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

PALETA = {
    "claro": {
        "bg": "#EDF1F6", "surface": "#FFFFFF", "surface2": "#F6F9FC", "wash": "#E6F0F8",
        "line": "#DCE4EC", "ink": "#1A2733", "ink2": "#5B6B7B", "ink3": "#8697A6",
        "blue": "#3A7CA8", "blue_d": "#235A80", "blue_l": "#8FBBDA", "blue_xl": "#C9DFEE",
        "teal": "#4A958F", "teal_l": "#8EC6C1", "teal_w": "#E4F1F0",
        "purple": "#7368A6", "purple_l": "#ADA4D3", "purple_w": "#EEECF6",
        "green_c": "#558F70", "green_l": "#9CC7AE", "green_w": "#E7F1EB",
        "slate": "#243342", "amber": "#D29B30", "red": "#C4501F", "green": "#0E7563",
        "amber_t": "#8A5D0F", "neutro": "#B9CAD8", "total": "#235A80",
        "gray3": "#D3DEE7", "grid": "#E6ECF1",
    },
    "escuro": {
        "bg": "#111820", "surface": "#1A232D", "surface2": "#212C38", "wash": "#1D3345",
        "line": "#2C3A48", "ink": "#E7EEF5", "ink2": "#A2B4C4", "ink3": "#7C8D9D",
        "blue": "#5F9CC6", "blue_d": "#9CC8E6", "blue_l": "#4A80A8", "blue_xl": "#2C557A",
        "teal": "#62ABA5", "teal_l": "#3A7C77", "teal_w": "#17302F",
        "purple": "#9A90CC", "purple_l": "#675D9C", "purple_w": "#221E36",
        "green_c": "#6FAA88", "green_l": "#44795B", "green_w": "#16281E",
        "slate": "#0E151C", "amber": "#E0B04F", "red": "#F08A4B", "green": "#4DB6A6",
        "amber_t": "#E0B04F", "neutro": "#B9CAD8", "total": "#235A80",
        "gray3": "#3A4956", "grid": "#2C3A48",
    },
}

# cor de destaque de cada seção, usada na faixa de abertura
COR_SECAO = {
    "Visão Geral": "blue", "Gestão de Compras": "teal", "Pedidos": "blue_d",
    "Fornecedores": "purple", "Medicamentos": "green_c",
    "Posição de Estoque": "teal", "Reposição e Lotes": "teal", "Validade e Remarcação": "teal",
    "Curva ABC": "purple", "Análises e Indicadores": "green_c", "Previsão de Compras": "purple",
    "Sistema de Apoio à Decisão": "blue", "Conceitos e Cálculos": "ink3", "Tutoriais": "teal",
    "Preferências": "purple", "Base de Dados": "teal",
}

COR_NIVEL = {"crit": "red", "aten": "amber", "ok": "green", "info": "blue"}

PASTA_ASSETS = Path(__file__).parent.parent / "assets"
PASTA_STATIC = Path(__file__).parent.parent / "static"
LOGO = PASTA_ASSETS / "logo.svg"
ICONE = PASTA_ASSETS / "icone.svg"      # usado com o menu recolhido

# foto do banner de cada grupo do menu (arquivos em static/)
IMAGEM_GRUPO = {
    "Visão Geral": "farmacia.jpg", "Compras": "capsulas.jpg",
    "Movimentação": "estoque.jpg", "Análise e decisão": "estoque.jpg", "Referência": "referencia.jpg",
}


def cores() -> dict:
    return PALETA[st.session_state.get("tema", "claro")]


def escuro() -> bool:
    return st.session_state.get("tema") == "escuro"


# ---------------------------------------------------------------------------
#                               FORMATAÇÃO
# ---------------------------------------------------------------------------
# As funções ficam em core/formato.py (sem Streamlit), para que a camada de modelos
# possa usá-las; aqui são reexportadas para as telas continuarem importando de tema.
from core.formato import MESES, brl, brl0, data, mes_label, num, pct  # noqa: E402,F401


# ---------------------------------------------------------------------------
#                                   CSS
# ---------------------------------------------------------------------------
def aplicar_css() -> None:
    c = cores()
    st.markdown(f"""
    <style>
    .stApp {{ background:{c['bg']}; color:{c['ink']}; transition:background-color .3s ease }}
    header[data-testid="stHeader"] {{ background:{c['bg']} }}
    /* botões principais (Salvar, Entrar, Confirmar): texto branco sobre o azul */
    .stApp [data-testid="stBaseButton-primary"] *,
    .stApp [data-testid="stBaseButton-primaryFormSubmit"] * {{ color:#fff !important }}
    section[data-testid="stSidebar"] {{ background:{c['slate']} }}
    section[data-testid="stSidebar"] * {{ color:#C3D2DE }}
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{ color:#fff }}

    /* ---------------------------------------------------- menu lateral */
    [data-testid="stSidebarHeader"] {{ padding:18px 12px 14px 20px;
      border-bottom:1px solid rgba(255,255,255,.07); margin-bottom:6px }}
    [data-testid="stSidebarHeader"] div:has(> [data-testid="stSidebarLogo"]) {{
      flex:1 1 auto !important; height:auto !important }}
    [data-testid="stSidebarLogo"] {{ height:auto !important; max-height:none !important;
      width:100% !important; max-width:200px !important }}
    [data-testid="stSidebarNav"] {{ padding:2px 0 8px }}
    [data-testid="stSidebarNavItems"] {{ padding:0 10px }}
    [data-testid="stNavSectionHeader"] {{ margin:16px 0 4px 12px; padding:0 }}
    [data-testid="stNavSectionHeader"],
    [data-testid="stNavSectionHeader"] * {{ font-size:12.5px; font-weight:600;
      color:#7E93A6 !important; letter-spacing:.02em }}
    [data-testid="stSidebarNavLink"] {{ border-radius:10px; padding:7px 12px;
      margin:1px 0; transition:background-color .15s ease }}
    [data-testid="stSidebarNavLink"] p {{ font-size:15px; color:#D5E0E9 !important;
      white-space:normal; line-height:1.3 }}
    [data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] {{ color:#9FB4C6 !important }}
    [data-testid="stSidebarNavLink"]:hover {{ background:rgba(255,255,255,.06) }}
    [data-testid="stSidebarNavLink"][aria-current="page"] {{
      background:rgba(127,190,227,.16);
      box-shadow:inset 0 0 0 1px rgba(127,190,227,.12) }}
    [data-testid="stSidebarNavLink"][aria-current="page"] p {{ color:#fff !important;
      font-weight:600 }}
    [data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] {{
      color:#fff !important }}
    /* textos da barra lateral: a regra geral de parágrafo (cinza) não vale aqui */
    .stApp section[data-testid="stSidebar"] p,
    .stApp section[data-testid="stSidebar"] label,
    .stApp section[data-testid="stSidebar"] span {{ color:#C3D2DE }}
    .stApp section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
      color:#8FA3B5 }}
    [data-testid="stSidebarNavSeparator"] {{ border-color:rgba(255,255,255,.07) }}
    [data-testid="stSidebarUserContent"] {{ padding-top:10px }}
    .lateral-tit {{ font-size:12.5px; font-weight:600; color:#7E93A6 !important;
      letter-spacing:.02em; margin:2px 0 2px }}
    section[data-testid="stSidebar"] hr {{ border-color:rgba(255,255,255,.08); margin:14px 0 }}

    /* ------------------------------------- ordem da barra lateral
       logo → empresa → menu → tema e filtros → Sair fixo no rodapé.
       O conteúdo do usuário vem depois do menu no HTML do Streamlit; com
       display:contents os blocos dele viram itens da coluna da barra e podem
       ser reordenados com "order" sem mexer no menu nativo. */
    [data-testid="stSidebarContent"] {{ display:flex; flex-direction:column }}
    [data-testid="stSidebarHeader"] {{ order:0 }}
    [data-testid="stSidebarNav"] {{ order:2 }}
    [data-testid="stSidebarUserContent"],
    [data-testid="stSidebarUserContent"] > div,
    [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {{
      display:contents }}
    [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] > * {{
      order:3; margin:0 20px 12px; width:auto !important }}
    [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]
      > :is(.st-key-lateral_empresa, :has(> .st-key-lateral_empresa)) {{
      order:1; margin:6px 10px 14px }}
    [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]
      > :is(.st-key-lateral_sair, :has(> .st-key-lateral_sair)) {{
      order:9; margin:auto 0 0; position:sticky; bottom:0; z-index:5;
      padding:12px 20px 14px; background:{c['slate']};
      border-top:1px solid rgba(255,255,255,.09);
      box-shadow:0 -10px 18px -10px rgba(0,0,0,.45) }}

    .empresa-cartao {{ display:flex; align-items:center; gap:11px; padding:10px 12px;
      border-radius:12px; background:rgba(127,190,227,.10);
      border:1px solid rgba(127,190,227,.22) }}
    .empresa-icone {{ flex:0 0 34px; height:34px; border-radius:10px; display:flex;
      align-items:center; justify-content:center; background:#2E80B9 }}
    .stApp section[data-testid="stSidebar"] .empresa-icone span {{
      font-family:'Material Symbols Rounded'; font-size:20px; color:#fff !important }}
    .stApp section[data-testid="stSidebar"] .empresa-cartao small {{ display:block;
      font-size:11px; color:#9FB4C6 !important; letter-spacing:.02em }}
    .empresa-cartao b {{ display:block; font-size:15px; font-weight:700; color:#fff !important;
      line-height:1.25; overflow-wrap:anywhere }}

    /* ------------------------------------------------ filtros globais */
    .filtros-tit {{ margin-top:4px; padding-top:14px;
      border-top:1px solid rgba(255,255,255,.08); font-size:13px !important;
      color:#DCE6EF !important; text-transform:uppercase; letter-spacing:.06em }}
    .stApp section[data-testid="stSidebar"] .filtros-resumo {{ font-size:12px;
      line-height:1.45; color:#B5C6D5 !important; padding:7px 10px; border-radius:9px;
      margin:2px 0 8px;
      background:rgba(255,255,255,.04); border:1px dashed rgba(255,255,255,.14) }}
    .stApp section[data-testid="stSidebar"] .filtros-resumo.ativo {{ color:#fff !important;
      background:rgba(46,128,185,.28); border:1px solid #7FBEE3 }}
    .filtros-resumo b {{ display:inline-flex; min-width:20px; height:20px; padding:0 6px;
      border-radius:999px; align-items:center; justify-content:center;
      background:#7FBEE3; color:#13202C !important; font-size:12px; margin-right:2px }}
    /* rótulos legíveis */
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
      color:#E6EEF5 !important; font-size:13px !important; font-weight:600 }}
    /* campos: fundo mais claro que a barra e borda visível */
    section[data-testid="stSidebar"] .react-aria-ComboBox > [role="group"],
    section[data-testid="stSidebar"] [data-testid="stDateInputField"] {{
      background:#34495E !important; border:1px solid #5A7590 !important;
      border-radius:10px !important; transition:border-color .15s, box-shadow .15s }}
    section[data-testid="stSidebar"] .react-aria-ComboBox > [role="group"]:hover,
    section[data-testid="stSidebar"] [data-testid="stDateInputField"]:hover {{
      border-color:#8FB3CF !important }}
    section[data-testid="stSidebar"] .react-aria-ComboBox > [role="group"][data-focus-within],
    section[data-testid="stSidebar"] [data-testid="stDateInputField"]:focus-within {{
      border-color:#7FBEE3 !important; box-shadow:0 0 0 3px rgba(127,190,227,.25) }}
    section[data-testid="stSidebar"] input::placeholder {{ color:#AFC2D2 !important;
      opacity:1 }}
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] [data-testid="stDateInputField"] [role="spinbutton"],
    section[data-testid="stSidebar"] [data-testid="stDateInputField"] span {{
      color:#F2F6FA !important }}
    section[data-testid="stSidebar"] .react-aria-ComboBox button svg {{ color:#C9D8E4 }}
    /* opções escolhidas: chip azul com texto branco */
    section[data-testid="stSidebar"] [data-tag] {{ background:#2E80B9 !important;
      border:1px solid #7FBEE3; border-radius:7px !important }}
    section[data-testid="stSidebar"] [data-tag] span,
    section[data-testid="stSidebar"] [data-tag] button {{ color:#fff !important;
      font-weight:600 }}
    /* filtro em uso: borda e marca à esquerda, rótulo em branco */
    section[data-testid="stSidebar"] [data-testid="stMultiSelect"]:has([data-tag])
      .react-aria-ComboBox > [role="group"] {{ border-color:#7FBEE3 !important;
      box-shadow:inset 3px 0 0 #7FBEE3 }}
    section[data-testid="stSidebar"] [data-testid="stMultiSelect"]:has([data-tag])
      [data-testid="stWidgetLabel"] p {{ color:#fff !important }}
    section[data-testid="stSidebar"] [data-testid="stMultiSelect"]:has([data-tag])
      [data-testid="stWidgetLabel"] p::after {{ content:"  •"; color:#7FBEE3 }}
    /* botões da barra */
    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
      background:#2E80B9 !important; border:1px solid #2E80B9 !important;
      border-radius:10px; min-height:40px }}
    .stApp section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] * {{
      color:#fff !important; font-weight:600 }}
    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {{
      background:#3B90CB !important; border-color:#7FBEE3 !important }}
    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:disabled {{
      background:transparent !important; border:1px solid rgba(255,255,255,.16) !important }}
    .stApp section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:disabled * {{
      color:#8FA3B5 !important; font-weight:500 }}
    section[data-testid="stSidebar"] .st-key-lateral_sair [data-testid="stBaseButton-secondary"] {{
      background:transparent !important; border:1px solid rgba(222,128,120,.6) !important }}
    .stApp section[data-testid="stSidebar"] .st-key-lateral_sair
      [data-testid="stBaseButton-secondary"] * {{ color:#F5CFCA !important }}
    section[data-testid="stSidebar"] .st-key-lateral_sair
      [data-testid="stBaseButton-secondary"]:hover {{
      background:rgba(179,72,64,.35) !important; border-color:#DE8078 !important }}

    /* faixa "Filtros aplicados" na área principal */
    .filtros-aplicados {{ display:flex; flex-wrap:wrap; align-items:center; gap:7px;
      margin:-6px 0 16px; padding:9px 12px; border-radius:12px;
      background:{c['surface']}; border:1px solid {c['blue_l']} }}
    .stApp .fa-tit {{ display:inline-flex; align-items:center; gap:5px; font-size:12px;
      font-weight:700; color:{c['blue_d']}; margin-right:4px }}
    .stApp .fa-tit .material-symbols-rounded {{ font-family:'Material Symbols Rounded';
      font-size:18px; color:{c['blue']} }}
    .stApp .chip-filtro {{ font-size:12px; color:{c['ink']}; background:{c['wash']};
      border:1px solid {c['blue_xl']}; border-radius:999px; padding:3px 10px;
      overflow-wrap:anywhere }}
    .chip-filtro b {{ color:{c['blue_d']}; font-weight:600 }}

    /* ----------------------------------------------------- conteúdo */
    .block-container {{ max-width:1480px; padding:1.4rem 2.2rem 3rem }}

    .banner {{ position:relative; overflow:hidden; border-radius:18px;
      margin:0 0 20px; min-height:clamp(118px, 13vw, 176px);
      display:flex; align-items:center;
      padding:clamp(18px, 2.4vw, 30px) clamp(18px, 3vw, 38px);
      background:linear-gradient(90deg, #1B2835 0%, #1B2835F2 34%, #1B283599 58%,
                 #1B283500 86%), var(--img) center/cover no-repeat, #1B2835;
      box-shadow:0 1px 2px rgba(26,39,51,.08), 0 10px 26px rgba(26,39,51,.10) }}
    .banner::after {{ content:""; position:absolute; left:0; top:0; bottom:0;
      width:4px; background:var(--ac) }}
    .banner-txt {{ position:relative; max-width:min(620px, 100%) }}
    .banner-grupo {{ display:inline-flex; align-items:center; gap:6px;
      font-size:11.5px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
      color:#BFDDF1 !important; background:rgba(255,255,255,.10);
      border:1px solid rgba(255,255,255,.14); border-radius:999px; padding:3px 11px }}
    .banner-tit {{ font-size:clamp(22px, 2.5vw, 32px); font-weight:700; color:#fff;
      letter-spacing:-.02em; line-height:1.15; margin:10px 0 6px }}
    .banner-sub {{ font-size:clamp(12.5px, 1vw, 14px); color:#D5E2EC !important;
      line-height:1.55; margin:0 }}
    .banner-sub b {{ color:#FFFFFF; font-weight:600 }}

    /* gráficos: fundo branco, dentro de um cartão. Sem overflow:hidden: ele
       cortava o último botão da barra de ferramentas (zoom, mover, tela cheia) */
    [data-testid="stPlotlyChart"] {{ background:#FFFFFF; border:1px solid {c['line']};
      border-radius:14px; padding:8px 10px 6px;
      box-shadow:0 1px 2px rgba(26,39,51,.04), 0 4px 14px rgba(26,39,51,.04) }}
    [data-testid="stPlotlyChart"] .modebar-container {{ right:10px !important;
      top:6px !important }}
    /* fundo da barra só ao passar o mouse: parado, ele cobria o rótulo da barra mais
       alta no canto superior direito */
    [data-testid="stPlotlyChart"] .modebar {{ background:transparent !important;
      border-radius:8px; padding:2px 4px }}
    [data-testid="stPlotlyChart"]:hover .modebar {{
      background:rgba(255,255,255,.92) !important }}
    [data-testid="stPlotlyChart"] .modebar-btn path {{ fill:{c['ink3']} !important }}
    [data-testid="stPlotlyChart"] .modebar-btn:hover path,
    [data-testid="stPlotlyChart"] .modebar-btn.active path {{ fill:{c['blue']} !important }}
    /* barra do Streamlit (tela cheia, baixar): acima do cartão, sempre inteira */
    [data-testid="stElementToolbar"] {{ z-index:20 }}
    h1,h2,h3,h4 {{ color:{c['ink']}; letter-spacing:-.015em }}
    .stApp h3 {{ margin-top:.9rem; margin-bottom:.15rem; font-size:1.35rem }}
    .stApp p, .stApp li, .stApp label, .stApp span {{ color:{c['ink2']} }}
    /* opções escolhidas nos campos da área principal: texto escuro sobre azul claro
       (a regra geral de span acima deixava o texto cinza sobre o azul do tema) */
    [data-testid="stMain"] [data-tag] {{ background:{c['wash']} !important;
      border:1px solid {c['blue_l']} !important; border-radius:7px !important }}
    .stApp [data-testid="stMain"] [data-tag] span,
    .stApp [data-testid="stMain"] [data-tag] button {{ color:{c['blue_d']} !important;
      font-weight:600 }}
    /* botões de escolha (pílulas e controle segmentado): o escolhido fica azul
       com texto branco; os demais, brancos com borda e texto escuro */
    [data-testid="stMain"] [data-testid="stButtonGroup"] button {{
      background:{c['surface']}; border:1px solid {c['line']}; transition:all .15s ease }}
    [data-testid="stMain"] [data-testid="stButtonGroup"] button:hover {{
      border-color:{c['blue_l']}; background:{c['wash']} }}
    .stApp [data-testid="stMain"] [data-testid="stButtonGroup"] button * {{
      color:{c['ink']} !important }}
    [data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-pressed="true"],
    [data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"] {{
      background:{c['blue_d'] if not escuro() else c['blue_l']} !important;
      border-color:{c['blue_d'] if not escuro() else c['blue_l']} !important }}
    .stApp [data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-pressed="true"] *,
    .stApp [data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"] * {{
      color:#FFFFFF !important; font-weight:600 }}
    /* filtros de uma lista: um bloco só, separado do conteúdo */
    .barra-filtros {{ font-size:11px; font-weight:700; letter-spacing:.06em;
      text-transform:uppercase; color:{c['ink3']}; margin:4px 0 2px }}

    .cartao {{
      background:{c['surface']}; border:1px solid {c['line']}; border-radius:14px;
      padding:15px 17px; height:100%;
      box-shadow:0 1px 2px rgba(26,39,51,.05), 0 6px 18px rgba(26,39,51,.05);
      transition:transform .2s ease, box-shadow .2s ease;
    }}
    .cartao:hover {{ transform:translateY(-2px) }}
    .cartao .rot {{ font-size:11.5px; color:{c['ink2']}; font-weight:500 }}
    .cartao .val {{ font-size:25px; font-weight:600; color:{c['ink']};
                    letter-spacing:-.03em; margin-top:6px; line-height:1.1 }}
    .cartao .val.sm {{ font-size:16px; line-height:1.25 }}
    .cartao .sub {{ font-size:11.5px; color:{c['ink3']}; margin-top:5px }}
    .cartao.destaque {{ background:linear-gradient(135deg,{c['blue_d']},{c['blue']});
                        border-color:transparent }}
    .cartao.roxo {{ background:linear-gradient(135deg,{c['purple']},#4B3E7A);
                    border-color:transparent }}
    .cartao.destaque .rot,.cartao.destaque .sub,
    .cartao.roxo .rot,.cartao.roxo .sub {{ color:#E3EEF7 }}
    .cartao.destaque .val,.cartao.roxo .val {{ color:#fff }}

    /* comparativos: seta e variação contra o mês anterior e o ano anterior */
    .cartao.comparativo .val {{ margin-bottom:6px }}
    .stApp .cartao .cmp {{ font-size:11.5px; line-height:1.55; color:{c['ink3']} }}
    .stApp .cartao .cmp span {{ display:inline-block; width:13px; font-size:10.5px }}
    .stApp .cartao .cmp.bom, .stApp .cartao .cmp.bom span {{ color:{c['green']} }}
    .stApp .cartao .cmp.ruim, .stApp .cartao .cmp.ruim span {{ color:{c['red']} }}
    .stApp .cartao .cmp.neutro span {{ color:{c['ink3']} }}
    .stApp .cartao.destaque .cmp, .stApp .cartao.destaque .cmp span {{ color:#E3EEF7 }}
    .stApp .cartao.destaque .cmp.bom span {{ color:#A6EBDD }}
    .stApp .cartao.destaque .cmp.ruim span {{ color:#FFC79E }}
    .stApp .cartao .cmp em {{ font-style:normal; font-weight:700; margin-left:2px }}
    .stApp .cartao .cmp.bom em {{ color:{c['green']} }}
    .stApp .cartao .cmp.ruim em {{ color:{c['red']} }}
    .stApp .cartao.destaque .cmp.bom em {{ color:#A6EBDD }}
    .stApp .cartao.destaque .cmp.ruim em {{ color:#FFC79E }}
    /* título do gráfico fora do Plotly, com o (?) da explicação ao lado */
    /* cartão do gráfico: título + (?) + desenho numa moldura só, sempre branca (os
       gráficos são desenhados sobre branco também no tema escuro) */
    [class*="st-key-graf_"] {{ background:#FFFFFF; border:1px solid {c['line']};
      border-radius:14px; padding:14px 16px 6px; gap:10px;
      box-shadow:0 1px 2px rgba(26,39,51,.04), 0 4px 14px rgba(26,39,51,.04) }}
    [class*="st-key-graf_"] [data-testid="stPlotlyChart"] {{ border:none; box-shadow:none;
      padding:0; border-radius:0; background:transparent }}
    .graf-tit {{ font-size:14px; font-weight:600; color:{PALETA['claro']['ink']};
      line-height:1.35 }}
    .graf-tit sup, .graf-tit span {{ font-size:11.5px; font-weight:400;
      color:{PALETA['claro']['ink3']} }}
    [class*="st-key-graf_"] [data-testid="stTooltipIcon"] svg {{
      color:{PALETA['claro']['ink3']} }}

    /* tendências: um mini-gráfico por indicador */
    .mini-tend {{ display:flex; flex-direction:column; gap:2px; margin:0 0 4px }}
    /* o mini-gráfico já está num cartão: sem a moldura própria do gráfico */
    [class*="st-key-mini_"] {{ background:#FFFFFF }}
    [class*="st-key-mini_"] [data-testid="stPlotlyChart"] {{ border:none; box-shadow:none;
      padding:0; background:transparent }}
    /* cartão sempre branco: textos com as cores do tema claro, também no escuro */
    .stApp .mini-tend .mt-nome {{ font-size:12px; font-weight:600;
      color:{PALETA['claro']['ink2']}; text-transform:uppercase; letter-spacing:.04em }}
    .stApp .mini-tend b {{ font-size:15px; font-weight:650; color:{PALETA['claro']['ink']} }}
    .stApp .mini-tend.bom b {{ color:{PALETA['claro']['green']} }}
    .stApp .mini-tend.ruim b {{ color:{PALETA['claro']['red']} }}
    .stApp .mini-tend small {{ font-size:11.5px; color:{PALETA['claro']['ink3']} }}
    .selo {{ display:inline-block; font-size:10px; font-weight:700; padding:3px 9px;
             border-radius:999px; background:{c['wash']}; color:{c['blue_d']} }}
    .selo.crit {{ background:{c['red']}22; color:{c['red']} }}
    .selo.aten {{ background:{c['amber']}2E; color:{c['amber_t']} }}
    .selo.ok   {{ background:{c['green']}22; color:{c['green']} }}
    .selo.info {{ background:{c['blue']}22; color:{c['blue']} }}

    .faixa {{ display:flex; gap:12px; align-items:flex-start; margin:0 0 18px;
      padding:12px 18px 12px 15px; border-left:3px solid var(--ac);
      border-radius:0 14px 14px 0;
      background:linear-gradient(90deg,var(--acw) 0%, transparent 78%) }}
    .faixa p {{ margin:0; font-size:12.5px; color:{c['ink2']}; line-height:1.6 }}
    .faixa b {{ color:var(--ac); font-weight:600 }}

    .impactobox {{ background:linear-gradient(135deg,{c['blue_d']},{c['blue']});
      border-radius:12px; padding:18px 20px; color:#fff }}
    .impactobox span {{ font-size:11.5px; color:#D6E8F5; font-weight:500 }}
    .impactobox b.big {{ display:block; font-size:30px; font-weight:600;
      letter-spacing:-.035em; margin:6px 0 4px; color:#fff }}
    .impactobox small {{ font-size:11.5px; color:#C7E1F2; line-height:1.55 }}
    .impactobox small b {{ color:#fff; font-weight:600 }}

    .verbete {{ background:{c['surface']}; border:1px solid {c['line']};
      border-radius:14px; padding:16px 18px; height:100%;
      box-shadow:0 1px 2px rgba(26,39,51,.05), 0 6px 18px rgba(26,39,51,.05) }}
    .verbete.limite {{ border-left:4px solid {c['amber']} }}
    .verbete h4 {{ font-size:13px; margin-bottom:8px }}
    .verbete p {{ margin:0 0 9px; font-size:12.5px; color:{c['ink2']}; line-height:1.55 }}
    .formula {{ display:block; background:{c['surface2']}; border:1px solid {c['line']};
      border-radius:9px; padding:9px 12px; font-size:12px; color:{c['blue_d']};
      margin:0 0 9px; line-height:1.5 }}
    .onde {{ font-size:11px; color:{c['ink3']} }}
    .stApp p.onde {{ font-size:12px; margin:6px 0 6px }}
    .palavras-chave {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:4px }}
    .stApp .palavras-chave span {{ font-size:11.5px; color:{c['blue_d']};
      background:{c['wash']}; border:1px solid {c['blue_xl']}; border-radius:999px;
      padding:2px 9px }}

    /* preferências: um ajuste por linha, agrupados por categoria */
    .pref-cat {{ display:flex; gap:12px; align-items:flex-start; margin:2px 0 6px }}
    .pref-cat .ico {{ flex:0 0 38px; height:38px; border-radius:11px; display:flex;
      align-items:center; justify-content:center; background:{c['wash']} }}
    .stApp .pref-cat .ico span {{ font-family:'Material Symbols Rounded'; font-size:22px;
      color:{c['blue_d']} }}
    .pref-cat b {{ display:block; font-size:17px; color:{c['ink']} }}
    .stApp .pref-cat small {{ display:block; font-size:12.5px; color:{c['ink2']};
      line-height:1.5 }}
    .pref-item {{ display:flex; justify-content:space-between; gap:10px;
      align-items:baseline; flex-wrap:wrap; margin:6px 0 2px }}
    .pref-item b {{ font-size:14px; color:{c['ink']} }}
    .stApp .pref-item .padrao {{ font-size:11.5px; color:{c['ink3']} }}
    .stApp .pref-item .alterado {{ font-size:11px; font-weight:700; color:{c['amber']};
      background:{c['amber']}1F; border-radius:999px; padding:2px 8px }}
    .stApp p.pref-desc {{ font-size:12.5px; color:{c['ink2']}; line-height:1.55;
      margin:0 0 18px }}
    hr.pref-sep {{ border:none; border-top:1px dashed {c['line']}; margin:4px 0 2px }}
    /* apoio à decisão: leitura atual, réguas ajustadas e o que mudou */
    .leitura {{ display:flex; gap:10px; align-items:center; margin:0 0 12px;
      padding:10px 14px; border-radius:12px; background:{c['surface']};
      border:1px solid {c['line']} }}
    .stApp .leitura span {{ font-size:12.5px; color:{c['ink2']} }}
    .stApp .leitura b {{ color:{c['ink']} }}
    .stApp .leitura .material-symbols-rounded {{ font-family:'Material Symbols Rounded';
      font-size:22px; color:{c['blue']} }}
    /* selos de natureza: só o que não é observado (estimativa e projeção) é marcado */
    .stApp .nat {{ display:inline-block; font-size:9.5px; font-weight:700; letter-spacing:.05em;
      text-transform:uppercase; border-radius:999px; padding:1px 7px; margin-left:6px;
      vertical-align:middle; line-height:1.5; white-space:nowrap }}
    .stApp .nat-estimado {{ color:{c['amber']}; background:{c['amber']}1A;
      border:1px solid {c['amber']}55 }}
    .stApp .nat-projecao {{ color:{c['blue']}; background:{c['blue']}14;
      border:1px solid {c['blue']}55 }}
    .stApp .cartao.destaque .nat, .stApp .cartao.roxo .nat {{ color:#fff;
      background:rgba(255,255,255,.18); border-color:rgba(255,255,255,.45) }}
    .nat-legenda {{ display:flex; flex-wrap:wrap; gap:6px 18px; margin:-2px 0 14px }}
    .stApp .nat-legenda > span {{ font-size:12px; color:{c['ink3']} }}
    .stApp .nat-legenda .nat {{ margin:0 4px 0 0 }}
    /* telas da movimentação: perguntas, leitura automática e pontos de atenção */
    .perguntas-tela {{ display:flex; flex-wrap:wrap; gap:6px 8px; align-items:center;
      margin:-4px 0 12px }}
    .stApp .perguntas-tela b {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase;
      color:{c['ink3']}; margin-right:4px }}
    .stApp .perguntas-tela span {{ font-size:12.5px; color:{c['ink2']};
      background:{c['surface']}; border:1px solid {c['line']}; border-radius:999px;
      padding:3px 11px }}
    .leitura-auto {{ background:{c['surface']}; border:1px solid {c['line']};
      border-left:4px solid {c['teal']}; border-radius:10px; padding:12px 16px;
      margin:4px 0 18px }}
    .stApp .leitura-auto > b {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase;
      color:{c['teal']} }}
    .stApp .leitura-auto ul {{ margin:6px 0 0 0; padding-left:18px }}
    .stApp .leitura-auto li {{ font-size:13.5px; color:{c['ink2']}; margin:3px 0;
      line-height:1.5 }}
    .stApp .leitura-auto li b {{ color:{c['ink']} }}
    .ponto-atencao {{ display:flex; gap:14px; align-items:center }}
    /* ícone de traço num quadrado discreto, na cor do texto: sério e sem cor de alerta */
    .stApp .ponto-atencao .pa-ico {{ flex:0 0 36px; height:36px; border-radius:10px;
      display:flex; align-items:center; justify-content:center; font-size:21px;
      font-family:'Material Symbols Rounded'; font-weight:300; color:{c['ink2']};
      background:{c['surface2']}; border:1px solid {c['line']};
      font-variation-settings:'FILL' 0, 'wght' 300 }}
    .stApp .ponto-atencao p {{ margin:0; font-size:13.5px; color:{c['ink2']}; line-height:1.45 }}
    .stApp .ponto-atencao p b {{ color:{c['ink']} }}
    .regua-alterada {{ font-size:11px; font-weight:600; color:{c['amber']};
      background:{c['amber']}17; border-radius:8px; padding:5px 8px; margin-top:8px;
      line-height:1.4 }}
    .stApp .det-lista .alterado {{ font-size:10.5px; font-weight:700; color:{c['amber']};
      background:{c['amber']}1F; border-radius:999px; padding:1px 7px; margin-left:4px }}
    .det-lista.mudancas li {{ flex-direction:row; justify-content:space-between;
      align-items:center; gap:10px; flex-wrap:wrap }}
    .pref-indice {{ display:flex; flex-wrap:wrap; gap:7px; margin:4px 0 14px }}
    .pref-indice a {{ font-size:12.5px; text-decoration:none; color:{c['blue_d']} !important;
      background:{c['surface']}; border:1px solid {c['line']}; border-radius:999px;
      padding:4px 11px }}
    .pref-indice a:hover {{ border-color:{c['blue_l']} }}

    .efeito {{ font-size:11.5px; color:{c['teal']}; background:{c['teal_w']};
      border-radius:8px; padding:7px 10px; line-height:1.45; margin-top:6px }}

    div[data-testid="stExpander"] {{ background:{c['surface']};
      border:1px solid {c['line']}; border-radius:14px; overflow:hidden }}
    div[data-testid="stExpander"] summary {{ font-weight:600; color:{c['ink']} }}
    div[data-testid="stMetricValue"] {{ color:{c['ink']} }}
    .bloco-rot {{ font-size:11px; color:{c['ink3']}; font-weight:600; margin-bottom:4px }}
    .acao {{ background:{c['wash']}; border-radius:11px; padding:12px 15px;
             font-size:12.5px; color:{c['blue_d']}; line-height:1.55 }}

    /* visão geral: roteiro de leitura e cartões de prioridade */
    .roteiro-vg {{ display:flex; flex-wrap:wrap; gap:10px; margin:0 0 18px }}
    .roteiro-vg .passo {{ flex:1 1 180px; display:flex; gap:10px; align-items:center;
      background:{c['surface']}; border:1px solid {c['line']}; border-radius:12px;
      padding:10px 12px }}
    .roteiro-vg .num {{ flex:0 0 28px; height:28px; border-radius:50%; display:flex;
      align-items:center; justify-content:center; font-weight:700; font-size:13px;
      background:{c['wash']}; color:{c['blue_d']} !important }}
    .roteiro-vg b {{ display:block; font-size:13px; color:{c['ink']} }}
    .stApp .roteiro-vg small {{ font-size:11.5px; color:{c['ink3']} }}
    .cartao.prioridade .rot {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap;
      font-weight:600; color:{c['ink']} }}
    .cartao.prioridade .ordem {{ width:22px; height:22px; border-radius:50%;
      display:inline-flex; align-items:center; justify-content:center; font-size:11.5px;
      background:{c['wash']}; color:{c['blue_d']} !important }}
    .cartao.prioridade .selo {{ margin-left:auto }}
    .cartao.prioridade .impacto {{ font-size:11.5px; color:{c['ink2']}; margin-top:8px;
      padding-top:7px; border-top:1px dashed {c['line']}; font-weight:600 }}
    .cartao.prioridade .acao-curta {{ font-size:12px; color:{c['blue_d']};
      background:{c['wash']}; border-radius:8px; padding:8px 10px; margin-top:8px;
      line-height:1.45 }}
    /* prioridades da Visão Geral: uma linha por ponto, ação à direita */
    .prioridade-linha {{ padding:2px 0 2px 12px }}
    .prioridade-linha .pl-topo {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap }}
    .stApp .prioridade-linha .pl-topo b {{ font-size:14px; color:{c['ink']} }}
    .stApp .prioridade-linha .pl-valor {{ font-size:18px; font-weight:600; color:{c['ink']};
      margin:4px 0 2px }}
    .stApp .prioridade-linha .pl-valor small {{ font-size:12px; font-weight:500;
      color:{c['ink2']} }}
    .stApp .prioridade-linha .pl-frase {{ font-size:12.5px; color:{c['ink2']}; line-height:1.45 }}
    .pl-acao {{ background:{c['wash']}; border-radius:10px; padding:10px 12px }}
    .stApp .pl-acao b {{ display:block; font-size:11px; letter-spacing:.05em;
      text-transform:uppercase; color:{c['blue_d']}; margin-bottom:3px }}
    .stApp .pl-acao {{ font-size:12.5px; color:{c['blue_d']}; line-height:1.5 }}
    [data-testid="stPageLink"] a {{ background:{c['surface']}; border:1px solid {c['line']};
      border-radius:10px; padding:8px 12px }}
    [data-testid="stPageLink"] a:hover {{ border-color:{c['blue_l']} }}

    /* detalhe dos pontos do apoio à decisão: tudo quebra linha, nada é cortado */
    .det-topo {{ display:flex; justify-content:space-between; align-items:flex-start;
      gap:10px; flex-wrap:wrap; margin:2px 0 10px }}
    .det-num {{ font-size:26px; font-weight:700; color:{c['ink']}; letter-spacing:-.02em;
      margin-right:8px }}
    .stApp .det-txt {{ font-size:13px; color:{c['ink2']} }}
    .det-valores {{ display:grid; gap:8px; margin:0 0 14px;
      grid-template-columns:repeat(auto-fit, minmax(118px, 1fr)) }}
    .det-valor {{ background:{c['surface2']}; border:1px solid {c['line']};
      border-radius:10px; padding:9px 11px; min-width:0 }}
    .stApp .det-valor span {{ display:block; font-size:11px; color:{c['ink3']};
      line-height:1.3 }}
    .det-valor b {{ display:block; font-size:16px; font-weight:600; color:{c['ink']};
      margin-top:4px; line-height:1.25; overflow-wrap:anywhere }}
    .det-lista {{ list-style:none; margin:0 0 14px; padding:0;
      border:1px solid {c['line']}; border-radius:10px; overflow:hidden }}
    .det-lista li {{ display:flex; flex-direction:column; gap:2px; padding:7px 11px;
      margin:0; border-top:1px solid {c['line']}; background:{c['surface']} }}
    .det-lista li:first-child {{ border-top:none }}
    .stApp .det-nome {{ font-size:12.5px; font-weight:600; color:{c['ink']};
      overflow-wrap:anywhere }}
    .stApp .det-info {{ font-size:11.5px; color:{c['ink2']} }}
    .stApp p.det-expl {{ font-size:13px; line-height:1.6; margin:0 0 12px }}

    /* ------------------------------------------------ responsividade */
    .cartao .val {{ overflow-wrap:anywhere }}
    div[data-testid="stTabs"] [role="tablist"] {{ overflow-x:auto; scrollbar-width:thin }}

    /* notebooks e telas médias: linhas com 4 ou mais colunas (cartões)
       quebram em até três por linha, em vez de espremer o conteúdo */
    @media (max-width: 1280px) {{
      .block-container {{ padding:1.2rem 1.6rem 3rem }}
      div[data-testid="stHorizontalBlock"] {{ flex-wrap:wrap; row-gap:12px }}
      div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"]:nth-child(4))
        > div[data-testid="stColumn"] {{ min-width:calc(33.333% - 1rem) }}
    }}
    /* tablets e celulares: cartões em duas colunas, gráficos lado a lado empilham
       (!important porque as regras com :has acima são mais específicas) */
    @media (max-width: 900px) {{
      div[data-testid="stHorizontalBlock"] {{ flex-wrap:wrap; row-gap:12px }}
      div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
        min-width:calc(50% - 1rem) !important }}
      div[data-testid="stHorizontalBlock"]:not(:has(> div[data-testid="stColumn"]:nth-child(3)))
        > div[data-testid="stColumn"] {{ min-width:100% !important }}
      .cartao .val {{ font-size:21px }}
    }}
    @media (max-width: 640px) {{
      .block-container {{ padding:.8rem .8rem 2.5rem }}
      /* cartões com painel de detalhe (apoio à decisão) ocupam a linha inteira */
      div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"] [data-testid="stExpander"])
        > div[data-testid="stColumn"] {{ min-width:100% !important }}
      .cartao {{ padding:12px 13px }}
      .cartao .val {{ font-size:18px }}
      .cartao .val.sm {{ font-size:14px }}
      .banner {{ border-radius:14px;
        background:linear-gradient(90deg, #1B2835E6 0%, #1B2835B3 100%),
                   var(--img) center/cover no-repeat, #1B2835 }}
      .banner-sub {{ font-size:12px }}
      .faixa {{ padding:10px 12px }}
      [data-testid="stPlotlyChart"] {{ padding:2px 2px 0; border-radius:12px }}
    }}
    </style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#                              COMPONENTES
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def url_foto(nome: str) -> str:
    """Endereço da foto servida pela pasta static/ (ver .streamlit/config.toml).

    O navegador baixa a foto uma vez e reaproveita nas trocas de página; antes
    ela ia embutida em base64 (até 240 KB) a cada clique.
    """
    if not (PASTA_STATIC / nome).exists():
        return "none"
    return f"url('app/static/{nome}')"


SUBTITULO_PADRAO = "Sistema de Apoio à Decisão para Pequenas Farmácias – SADPF"


def _banner_html(secao: str, grupo: str, subtitulo: str) -> str:
    c = cores()
    img = url_foto(IMAGEM_GRUPO.get(grupo, "farmacia.jpg"))
    ac = c[COR_SECAO.get(secao, "blue")] if COR_SECAO.get(secao) != "ink3" else c["blue_l"]
    rotulo = "Painel" if grupo == secao else grupo
    return (f'<div class="banner" style="--img:{img}; --ac:{ac}">'
            f'<div class="banner-txt"><span class="banner-grupo">{rotulo}</span>'
            f'<div class="banner-tit">{secao}</div>'
            f'<p class="banner-sub">{subtitulo}</p></div></div>')


def cabecalho(secao: str, grupo: str) -> None:
    """Banner de abertura da seção, com a foto do grupo e a cor da seção.

    O banner fica num espaço reservado: quando a tela chama `faixa(texto)`, ele é
    redesenhado com a explicação da aba logo abaixo do nome, no lugar do subtítulo
    padrão. Telas sem explicação mantêm o nome do sistema.
    """
    lugar = st.empty()
    lugar.markdown(_banner_html(secao, grupo, SUBTITULO_PADRAO), unsafe_allow_html=True)
    st.session_state["_banner"] = (lugar, secao, grupo)
    st.session_state["_n_graf"] = 0          # numeração dos cartões de gráfico da tela


# Textos fixos da interface do Streamlit que não têm parâmetro de idioma.
# Um observador troca os textos em inglês assim que aparecem na página.
_TRADUCAO_JS = """
<script>
(() => {
  if (window.__sadpfTraducao) return;
  window.__sadpfTraducao = true;
  const exatos = {
    "Choose options": "Selecione", "Choose an option": "Selecione uma opção",
    "Choose or add options": "Selecione ou adicione", "Select all": "Selecionar todos",
    "No results": "Nenhum resultado", "No options to select.": "Nenhuma opção disponível.",
    "Clear all": "Limpar tudo", "Clear value": "Limpar", "Remove": "Remover",
    "Drag and drop file here": "Arraste e solte o arquivo aqui",
    "Drag and drop a file here": "Arraste e solte o arquivo aqui",
    "Drag and drop files here": "Arraste e solte os arquivos aqui",
    "Browse files": "Procurar arquivo", "Upload": "Enviar arquivo",
    "Download as CSV": "Baixar em CSV", "Download": "Baixar", "Search": "Buscar",
    "Fullscreen": "Tela cheia", "Close fullscreen": "Sair da tela cheia",
    "Close": "Fechar", "Show/hide columns": "Mostrar/ocultar colunas",
    "Download plot as a png": "Baixar gráfico em PNG", "Zoom": "Zoom",
    "Pan": "Mover", "Zoom in": "Aproximar", "Zoom out": "Afastar",
    "Reset axes": "Restaurar eixos", "Autoscale": "Ajustar escala",
    "View fullscreen": "Ver em tela cheia", "Exit fullscreen": "Sair da tela cheia",
    "Open sidebar": "Abrir menu", "Close sidebar": "Fechar menu",
    "Collapse sidebar": "Recolher menu", "Expand sidebar": "Expandir menu",
    "View more": "Ver mais", "View less": "Ver menos",
    "January": "Janeiro", "February": "Fevereiro", "March": "Março", "April": "Abril",
    "May": "Maio", "June": "Junho", "July": "Julho", "August": "Agosto",
    "September": "Setembro", "October": "Outubro", "November": "Novembro",
    "December": "Dezembro",
    "Previous month.": "Mês anterior.", "Next month.": "Próximo mês."
  };
  const dias = {"Su": "D", "Mo": "S", "Tu": "T", "We": "Q", "Th": "Q", "Fr": "S", "Sa": "S"};
  const padroes = [
    [/^Select all (\\d+) matches$/, "Selecionar os $1 resultados"],
    [/^Limit (.+) per file(.*)$/, "Limite de $1 por arquivo$2"],
    [/^(\\S+) per file(.*)$/, "Até $1 por arquivo$2"],
    [/^You can only select up to (\\d+) options?\\.?$/, "Selecione no máximo $1"],
    [/^(January|February|March|April|May|June|July|August|September|October|November|December) (\\d{4})$/,
      (m, mes, ano) => exatos[mes] + " " + ano]
  ];
  const traduzir = (txt, noCalendario) => {
    const t = txt.trim();
    if (!t) return null;
    if (exatos[t]) return txt.replace(t, exatos[t]);
    if (noCalendario && dias[t]) return txt.replace(t, dias[t]);
    for (const [re, novo] of padroes) {
      if (re.test(t)) return txt.replace(t, t.replace(re, novo));
    }
    return null;
  };
  const atributos = ["aria-label", "title", "placeholder", "data-title"];
  const textoNo = (n) => {
    const pai = n.parentElement;
    if (!pai || pai.closest("script,style,textarea,[contenteditable]")) return;
    const cal = !!pai.closest('[data-baseweb="calendar"]');
    const novo = traduzir(n.nodeValue, cal);
    if (novo !== null && novo !== n.nodeValue) n.nodeValue = novo;
  };
  const atributosEl = (el) => atributos.forEach((a) => {
    const v = el.getAttribute(a);
    if (!v) return;
    const novo = traduzir(v, false);
    if (novo !== null && novo !== v) el.setAttribute(a, novo);
  });
  const varrer = (raiz) => {
    if (raiz.nodeType === 3) { textoNo(raiz); return; }
    if (raiz.nodeType !== 1 || raiz.closest("script,style")) return;
    // gráficos e tabelas têm milhares de nós e nenhum texto a traduzir por dentro
    if (raiz.closest(".js-plotly-plot svg, [data-testid='stDataFrameResizable'] canvas")) return;
    const walker = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) textoNo(n);
    atributosEl(raiz);
    raiz.querySelectorAll("[aria-label],[title],[placeholder],[data-title]").forEach(atributosEl);
  };
  // só o que mudou é examinado, não a página inteira a cada alteração
  const pendentes = new Set();
  let agendado = false;
  const agendar = (registros) => {
    for (const r of registros) {
      if (r.type === "childList") r.addedNodes.forEach((n) => pendentes.add(n));
      else pendentes.add(r.target);
    }
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(() => {
      agendado = false;
      const lote = [...pendentes];
      pendentes.clear();
      lote.forEach((n) => { if (n.isConnected) varrer(n); });
    });
  };
  new MutationObserver(agendar).observe(document.body, {
    childList: true, subtree: true, characterData: true,
    attributes: true, attributeFilter: atributos
  });
  document.documentElement.lang = "pt-BR";
  agendar([{type: "childList", addedNodes: [document.body]}]);
})();
</script>
"""


def traduzir_interface() -> None:
    """Traduz para o português os textos fixos dos filtros e controles."""
    st.html(_TRADUCAO_JS, unsafe_allow_javascript=True)


def filtros_aplicados(ativos: list[tuple[str, str]]) -> None:
    """Faixa abaixo do banner com os filtros em uso: confirma o recorte da tela."""
    if not ativos:
        return
    chips = "".join(f"<span class='chip-filtro'><b>{escape(rot)}:</b> {escape(val)}</span>"
                    for rot, val in ativos)
    st.markdown(f"<div class='filtros-aplicados'><span class='fa-tit'>"
                f"<span class='material-symbols-rounded' aria-hidden='true'>filter_alt</span>"
                f"Filtros aplicados"
                f"</span>{chips}</div>", unsafe_allow_html=True)


def faixa(texto: str, secao: str) -> None:
    """Explicação da aba, logo abaixo do nome dela no banner.

    Fora do fluxo normal (sem banner desenhado nesta execução), cai na faixa
    colorida antiga, abaixo do banner.
    """
    banner = st.session_state.pop("_banner", None)
    if banner:
        lugar, secao_b, grupo = banner
        lugar.markdown(_banner_html(secao_b, grupo, texto), unsafe_allow_html=True)
        return
    c = cores()
    chave = COR_SECAO.get(secao, "blue")
    ac = c[chave]
    acw = c.get(chave + "_w", c["wash"]) if chave != "ink3" else c["surface2"]
    st.markdown(
        f'<div class="faixa" style="--ac:{ac}; --acw:{acw}"><p>{texto}</p></div>',
        unsafe_allow_html=True)


# Natureza de cada número. Valores observados (compras, entradas, saídas, saldo)
# não levam selo; o que é cálculo com premissa ou valor futuro leva, para não ser
# lido como resultado que já aconteceu. Os rótulos "real" e "simulado" usados no
# código (a origem do dado) não aparecem na tela: ficam na documentação técnica.
NATUREZA = {
    "estimado": ("Estimado", "cálculo com uma premissa declarada, não um valor observado"),
    "projecao": ("Projeção", "valor futuro calculado a partir do histórico"),
}


def selo_natureza(natureza: str) -> str:
    if natureza not in NATUREZA:
        return ""
    nome, explicacao = NATUREZA[natureza]
    return f"<span class='nat nat-{natureza}' title='{explicacao}'>{nome}</span>"


def legenda_natureza() -> None:
    """Linha explicando os selos, para o topo das telas que os usam."""
    st.markdown("<div class='nat-legenda'>" + "".join(
        f"<span>{selo_natureza(n)} {txt}</span>" for n, (_, txt) in NATUREZA.items())
        + "<span>Valores sem selo foram observados nos dados.</span></div>",
        unsafe_allow_html=True)


def cartao(rotulo: str, valor: str, sub: str = "", estilo: str = "",
           natureza: str = "") -> str:
    classe = "val sm" if len(str(valor)) > 14 else "val"
    extra = f" {estilo}" if estilo else ""
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    selo = selo_natureza(natureza)
    return (f'<div class="cartao{extra}"><div class="rot">{rotulo}{selo}</div>'
            f'<div class="{classe}">{valor}</div>{sub_html}</div>')


def linha_cartoes(itens: list[tuple], colunas: int = 4) -> None:
    """Distribui cartões em colunas. Item = (rótulo, valor, sub[, estilo[, natureza]])."""
    for inicio in range(0, len(itens), colunas):
        faixa_itens = itens[inicio:inicio + colunas]
        cols = st.columns(colunas, gap="small")
        for col, item in zip(cols, faixa_itens):
            rot, val = item[0], item[1]
            sub = item[2] if len(item) > 2 else ""
            estilo = item[3] if len(item) > 3 else ""
            natureza = item[4] if len(item) > 4 else ""
            col.markdown(cartao(rot, val, sub, estilo, natureza), unsafe_allow_html=True)
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)


def _variacao(comp: dict, chave: str, rotulo: str, formato: str,
              maior_e_melhor: bool | None) -> str:
    """Uma linha do comparativo: seta, variação e o mês comparado."""
    v = comp.get(chave)
    base = comp.get("anterior" if chave == "var_mes" else "ano_anterior")
    if v is None or (isinstance(v, float) and v != v):
        motivo = (f"sem dado {rotulo}" if base is None
                  else f"{rotulo.replace('vs ', '')} foi zero")
        return f"<div class='cmp neutro'><span>–</span> {motivo}</div>"
    if formato == "pp":
        texto = f"{abs(v) * 100:.1f}".replace(".", ",") + " p.p."
    else:
        texto = f"{abs(v) * 100:.0f}%" if abs(v) >= 0.095 else f"{abs(v) * 100:.1f}%".replace(".", ",")
    if abs(v) < 0.0005:
        return f"<div class='cmp neutro'><span>●</span> estável {rotulo}</div>"
    seta = "▲" if v > 0 else "▼"
    if maior_e_melhor is None:
        classe = "neutro"
    else:
        classe = "bom" if (v > 0) == maior_e_melhor else "ruim"
    # o juízo vai na cor (verde/laranja, paleta segura para daltonismo) e, por
    # extenso, na dica ao passar o mouse
    dica = {"bom": "variação favorável", "ruim": "variação desfavorável"}.get(
        classe, "sem juízo: subir não é bom nem ruim por si")
    return (f"<div class='cmp {classe}' title='{dica}'><span>{seta}</span> {texto} "
            f"{rotulo}</div>")


def cartao_comparativo(rotulo: str, valor: str, comp: dict, maior_e_melhor: bool | None,
                       formato: str = "pct", estilo: str = "", natureza: str = "") -> str:
    """Cartão com o valor do mês e a variação contra o mês anterior e o ano anterior.

    Verde = variação favorável; laranja = desfavorável (perdas
    que sobem são desfavoráveis; vendas e margem que sobem, favoráveis). Cinza,
    sem palavra, quando subir não é bom nem ruim por si (compras, estoque).
    """
    ref = comp["ref"]
    meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    nome = lambda m: f"{meses[m.month - 1]}/{str(m.year)[2:]}"   # noqa: E731
    linhas = (_variacao(comp, "var_mes", f"vs {nome(ref - 1)}", formato, maior_e_melhor) +
              _variacao(comp, "var_ano", f"vs {nome(ref - 12)}", formato, maior_e_melhor))
    classe = "val sm" if len(str(valor)) > 14 else "val"
    extra = f" {estilo}" if estilo else ""
    return (f'<div class="cartao comparativo{extra}"><div class="rot">{rotulo}'
            f'{selo_natureza(natureza)}</div><div class="{classe}">{valor}</div>{linhas}</div>')


def linha_comparativos(itens: list[str], colunas: int = 4) -> None:
    """Cartões comparativos (HTML pronto de cartao_comparativo) em colunas."""
    for inicio in range(0, len(itens), colunas):
        for col, html in zip(st.columns(colunas, gap="small"), itens[inicio:inicio + colunas]):
            col.markdown(html, unsafe_allow_html=True)
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)


EFEITO_NOME = {"bom": "Benéfico", "ruim": "Prejudicial", "neutro": "Neutro", "total": "Total"}


def _clarear(hexa: str, fracao: float = 0.30) -> str:
    """Mistura a cor com branco (0 = a própria cor, 1 = branco)."""
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(v + (255 - v) * fracao):02X}" for v in (r, g, b))


def cascata(passos: list[tuple], titulo: str, horizontal: bool = True,
            rotulos_curtos: dict | None = None) -> go.Figure:
    """Gráfico em cascata ("tijolinho") com a cor pelo efeito de cada passo.

    passo = (rótulo, valor, tipo, efeito, natureza):
      tipo     'total' (barra cheia a partir do zero), 'soma' ou 'subtrai';
      efeito   'bom' (verde), 'ruim' (laranja) ou 'neutro' (cinza) — o efeito
               no negócio, não a direção: vender tira do estoque e é benéfico;
      natureza 'estimado' deixa a barra em tom claro, com contorno, e "(estimado)"
               no rótulo.
    Os totais ficam no azul-escuro do projeto e o neutro, em azul-acinzentado claro. O sinal (+/−) no rótulo e a legenda repetem a
    cor, para quem não distingue verde de laranja. Usa a paleta clara porque os
    gráficos ficam sempre sobre fundo branco.
    """
    c = PALETA["claro"]
    curtos = rotulos_curtos or {}
    cor_efeito = {"bom": c["green"], "ruim": c["red"], "neutro": c["neutro"],
                  "total": c["total"]}
    cat, base, largura, cor, texto = [], [], [], [], []
    efeitos, contorno, tem_estimado = [], [], False
    acumulado = 0.0
    for rotulo, valor, tipo, efeito, natureza in passos:
        est = natureza == "estimado"
        tem_estimado |= est
        cat.append(curtos.get(rotulo, rotulo) + (" (estimado)" if est else ""))
        if tipo == "total":
            acumulado = valor
            base.append(0.0)
            largura.append(valor)
            efeito = "total"
            texto.append(brl0(valor))
        else:
            sinal = 1 if tipo == "soma" else -1
            novo = acumulado + sinal * valor
            base.append(min(acumulado, novo))
            largura.append(abs(valor))
            texto.append(("+ " if sinal > 0 else "− ") + brl0(valor))
            acumulado = novo
        efeitos.append(efeito)
        # estimado: o mesmo tom, mais claro, com contorno na cor cheia (sem hachura, que
        # foi retirada do painel); o "(estimado)" no rótulo diz o mesmo sem depender da cor
        cor.append(_clarear(cor_efeito[efeito]) if est else cor_efeito[efeito])
        contorno.append(cor_efeito[efeito])
    barra = dict(base=base, marker=dict(color=cor, line=dict(color=contorno, width=1.5)),
                 text=texto, textposition="outside", cliponaxis=False, showlegend=False,
                 customdata=[EFEITO_NOME[e] for e in efeitos])
    if horizontal:
        fig = go.Figure(go.Bar(y=cat, x=largura, orientation="h",
                               hovertemplate="%{y}<br><b>%{text}</b> · %{customdata}"
                                             "<extra></extra>", **barra))
    else:
        fig = go.Figure(go.Bar(x=cat, y=largura,
                               hovertemplate="%{x}<br><b>%{text}</b> · %{customdata}"
                                             "<extra></extra>", **barra))
    # legenda: uma entrada por efeito presente, na ordem de leitura
    for ef in ["bom", "ruim", "neutro", "total"]:
        if ef in efeitos:
            fig.add_trace(go.Bar(x=[None], y=[None], name=EFEITO_NOME[ef],
                                 marker_color=cor_efeito[ef], hoverinfo="skip"))
    if tem_estimado:
        fig.add_trace(go.Bar(x=[None], y=[None], name="Estimado",
                             marker=dict(color=_clarear(c["green"]),
                                         line=dict(color=c["green"], width=1.5)),
                             hoverinfo="skip"))
    topo = max(b + a for b, a in zip(base, largura))
    eixo_valor = dict(tickprefix="R$ ", tickformat=",.0f", range=[0, topo * 1.2])
    if horizontal:
        fig.update_layout(xaxis=eixo_valor, yaxis=dict(autorange="reversed"))
    else:
        fig.update_layout(yaxis=eixo_valor)
    fig.update_layout(title=titulo, bargap=0.3, barmode="overlay", margin=dict(r=40))
    return fig


# ---------------------------------------------------------------------------
#                                 PLOTLY
# ---------------------------------------------------------------------------
def _montar_template(tema: str) -> go.layout.Template:
    # os gráficos ficam sempre sobre fundo branco, nos dois temas: o texto e a
    # grade usam a paleta clara para continuarem legíveis sobre o branco
    c = PALETA["claro"]
    serie = PALETA[tema]
    base = pio.templates["plotly_white"]
    tpl = go.layout.Template(layout=base.layout.to_plotly_json())
    tpl.layout.paper_bgcolor = "#FFFFFF"
    tpl.layout.plot_bgcolor = "#FFFFFF"
    tpl.layout.font = dict(family="Inter, Segoe UI, sans-serif", size=12, color=c["ink2"])
    tpl.layout.title = dict(font=dict(size=14, color=c["ink"]), x=0.01, xanchor="left")
    tpl.layout.colorway = [serie["blue"], serie["teal"], serie["purple"], serie["green_c"],
                           serie["amber"], serie["blue_l"], serie["purple_l"], serie["teal_l"]]
    # grade só no eixo dos valores, pontilhada e clara: as linhas de referência
    # (média, ponto de pedido, limites) é que devem chamar a atenção
    eixo = dict(gridcolor=c["grid"], zeroline=False, linecolor=c["line"], automargin=True,
                title=dict(font=dict(size=11.5, color=c["ink3"]), standoff=10),
                tickfont=dict(size=11, color=c["ink2"]))
    # ticklabelstandoff: distância entre o rótulo e o início do gráfico, para os
    # nomes não encostarem nas barras
    tpl.layout.xaxis = dict(eixo, showgrid=False, showline=True, ticklabelstandoff=4)
    tpl.layout.yaxis = dict(eixo, showgrid=True, griddash="dot", showline=False,
                            ticklabelstandoff=10)
    tpl.layout.bargap = 0.32
    tpl.layout.bargroupgap = 0.08
    # legenda em uma linha no alto, à esquerda, logo acima da área do gráfico: não
    # disputa espaço com os rótulos de mês do eixo de baixo nem fica sob a barra de
    # ferramentas do canto direito (lá ela aparecia apagada)
    tpl.layout.legend = dict(bgcolor="rgba(255,255,255,0)", font=dict(color=c["ink2"], size=11.5),
                             orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                             itemsizing="constant")
    tpl.layout.hoverlabel = dict(bgcolor=c["slate"], font_color="#fff", bordercolor=c["line"])
    # rótulos das linhas de referência: pequenos, discretos e com fundo, para não
    # se misturarem às barras
    tpl.layout.annotationdefaults = dict(font=dict(size=10.5, color=c["ink2"]),
                                         bgcolor="rgba(255,255,255,.85)", borderpad=2)
    tpl.layout.shapedefaults = dict(line=dict(width=1.2, color=c["ink3"]), opacity=0.9)
    tpl.layout.modebar = dict(bgcolor="rgba(255,255,255,0)", color=c["ink3"],
                              activecolor=serie["blue"], orientation="h")
    tpl.data.bar = [go.Bar(marker=dict(line=dict(width=0)))]
    tpl.data.scatter = [go.Scatter(line=dict(width=2))]
    return tpl


# Os modelos são montados uma vez, ao carregar o módulo. Antes eram refeitos a
# cada gráfico (cerca de 0,1 s cada), o que pesava nas telas com vários gráficos.
# O do tema claro vira o padrão do Plotly, então os gráficos já nascem com ele.
for _tema in PALETA:
    pio.templates[f"sadpf_branco_{_tema}"] = _montar_template(_tema)
pio.templates.default = "sadpf_branco_claro"


def registrar_template() -> str:
    """Nome do modelo de gráfico do tema atual (já registrado no Plotly)."""
    return f"sadpf_branco_{st.session_state.get('tema', 'claro')}"


def _quebrar(texto, largura: int = 26, linhas: int = 2) -> str:
    """Nome de categoria em até duas linhas, com reticências se ainda sobrar texto."""
    partes = textwrap.wrap(str(texto), largura) or [""]
    if len(partes) > linhas:
        partes = partes[:linhas]
        partes[-1] = partes[-1][:largura - 1].rstrip() + "…"
    return "<br>".join(partes)


def _ajustar_barras_horizontais(fig: go.Figure, altura: int) -> int:
    """Rótulos do eixo vertical legíveis em barras deitadas; devolve a altura final.

    Nomes longos (medicamentos, fornecedores) quebram em duas linhas em vez de
    ser cortados ou empurrar o gráfico para um canto. Só o texto do eixo muda:
    o valor da categoria continua inteiro na dica do mouse. A altura cresce
    com o número de categorias para que as linhas não se sobreponham.
    """
    categorias: list = []
    for trace in fig.data:
        if getattr(trace, "type", "") == "bar" and getattr(trace, "orientation", None) == "h" \
                and trace.y is not None:
            for valor in trace.y:
                if valor not in categorias:
                    categorias.append(valor)
    if not categorias or not all(isinstance(v, str) for v in categorias):
        return altura
    textos = [_quebrar(v) for v in categorias]
    fig.update_yaxes(tickmode="array", tickvals=categorias, ticktext=textos)
    duas_linhas = any("<br>" in t for t in textos)
    por_linha = 34 if duas_linhas else 26
    return max(altura, len(categorias) * por_linha + 110)


def _folga_rotulos(fig: go.Figure) -> None:
    """Espaço para o rótulo de valor da maior barra, que ficava cortado na borda.

    Só em barras com texto do lado de fora: o eixo do valor ganha 18% de folga
    além da maior barra.
    """
    for eixo in ("x", "y"):
        barras = [t for t in fig.data if getattr(t, "type", "") == "bar"
                  and getattr(t, "textposition", None) == "outside"
                  and (getattr(t, "orientation", None) == "h") == (eixo == "x")]
        valores = []
        for t in barras:
            serie = getattr(t, eixo)
            if serie is not None:
                valores += [float(v) for v in serie if isinstance(v, numbers.Real) and v == v]
        if valores and max(valores) > 0 and min(valores) >= 0:
            atual = fig.layout[f"{eixo}axis"].range
            if atual is None:
                fig.update_layout({f"{eixo}axis": dict(range=[0, max(valores) * 1.18])})


def figura(fig: go.Figure, altura: int = 300) -> go.Figure:
    # o fundo branco vai também direto no layout: só no template, o Streamlit
    # ainda o substituía pela cor de fundo da página
    # separators=",.": vírgula decimal e ponto de milhar, como no restante do painel
    altura = _ajustar_barras_horizontais(fig, altura)
    _folga_rotulos(fig)
    # margem de cima com folga para o título e a barra de ferramentas não disputarem
    # espaço; a de baixo cresce sozinha com a legenda (automargin dos eixos)
    ajustes = dict(height=altura, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                   separators=",.", margin=dict(l=12, r=18, t=58, b=14),
                   title_y=0.985, title_yanchor="top", title_pad=dict(t=4))
    nome = registrar_template()
    if nome != pio.templates.default:          # só o tema escuro troca o modelo
        ajustes["template"] = nome
    # sem animação de transição: ela segurava cada gráfico por 0,3 s na tela
    fig.update_layout(**ajustes)
    return fig


# barra de ferramentas do gráfico: aproximar, afastar, ampliar uma área, mover,
# restaurar e baixar em PNG. A tela cheia é o botão do próprio Streamlit, que
# aparece no canto do cartão ao passar o mouse. Duplo clique volta ao original.
CONFIG_GRAFICO = {
    "displaylogo": False, "responsive": True, "scrollZoom": False,
    "doubleClick": "reset",
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d",
                               "hoverClosestCartesian", "hoverCompareCartesian",
                               "toggleSpikelines"],
    "toImageButtonOptions": {"format": "png", "filename": "sadpf-grafico", "scale": 2},
}


def _tem_legenda(fig: go.Figure) -> bool:
    if fig.layout.showlegend is False:
        return False
    nomeados = [t for t in fig.data if t.showlegend is not False and t.name]
    return bool(fig.layout.showlegend) or len(nomeados) > 1 or (
        len(fig.data) == 1 and getattr(fig.data[0], "type", "") == "pie")


def mostrar(fig: go.Figure, altura: int = 300, explicacao: str = "") -> None:
    """Desenha o gráfico num cartão único: título (com o (?) da explicação) e desenho.

    O título sai de dentro do Plotly e vai para o topo do cartão, com folga até o
    desenho; a explicação abre ao passar o mouse (ou tocar) no (?). Todos os
    gráficos com título ficam iguais, com ou sem explicação. A margem de cima só
    reserva espaço quando há legenda.
    """
    fig = figura(fig, altura)
    titulo = fig.layout.title.text
    if not titulo and not explicacao:
        # sem título: o próprio gráfico é o cartão
        st.plotly_chart(fig, width="stretch", theme=None, config=CONFIG_GRAFICO)
        return
    n = st.session_state.get("_n_graf", 0) + 1
    st.session_state["_n_graf"] = n
    fig.update_layout(title=None, margin=dict(t=34 if _tem_legenda(fig) else 12))
    with st.container(key=f"graf_{n}"):
        st.markdown(f"<div class='graf-tit'>{titulo or 'Sobre este gráfico'}</div>",
                    unsafe_allow_html=True, help=explicacao or None)
        # theme=None: sem isso o Streamlit repinta o fundo com a cor do próprio tema
        st.plotly_chart(fig, width="stretch", theme=None, config=CONFIG_GRAFICO)
