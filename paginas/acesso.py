"""
Tela de entrada: login e cadastro de empresa.

Aparece antes de qualquer outra tela. Enquanto ninguém entrou, o app.py não
carrega a base nem monta o menu: só esta tela existe. Depois do login, o nome
da empresa fica em st.session_state["usuario"] até a pessoa clicar em Sair ou
fechar a aba do navegador.
"""
from __future__ import annotations

import streamlit as st

from core import usuarios as U
from core.tema import LOGO, url_foto

_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stExpandSidebarButton"], header[data-testid="stHeader"] { display:none !important }
.stApp { background:#EDF1F6 }
.block-container { max-width:1080px; padding:clamp(16px, 6vh, 64px) 16px 32px !important }
div[data-testid="stHorizontalBlock"]:has(.entrada-foto) { gap:0; align-items:stretch;
  background:#fff; border-radius:22px; overflow:hidden;
  box-shadow:0 1px 2px rgba(26,39,51,.06), 0 18px 48px rgba(26,39,51,.12) }
div[data-testid="stHorizontalBlock"]:has(.entrada-foto) > div[data-testid="stColumn"]:last-child {
  padding:clamp(22px, 4vw, 44px) clamp(18px, 4vw, 46px) }
.entrada-foto { height:100%; min-height:520px; display:flex; flex-direction:column;
  justify-content:space-between; padding:34px 34px 30px; color:#fff;
  background:linear-gradient(160deg, #1B2835F5 0%, #1B2835C7 45%, #1D5C8899 100%),
             var(--img) center/cover no-repeat, #1B2835 }
.entrada-foto img { width:200px; max-width:100% }
.entrada-foto h1 { color:#fff !important; font-size:clamp(24px, 2.6vw, 32px); line-height:1.15;
  letter-spacing:-.02em; margin:0 0 10px; padding:0 }
.stApp .entrada-foto p { color:#C7D6E2 !important; font-size:14px; line-height:1.6; margin:0 }
.entrada-lista { list-style:none; padding:0; margin:18px 0 0 }
.stApp .entrada-lista li { color:#DCE8F1 !important; font-size:13px; margin:0 0 8px;
  display:flex; gap:9px; align-items:center }
.entrada-lista li::before { content:""; width:7px; height:7px; border-radius:50%;
  background:#7FBEE3; flex:0 0 7px }
.entrada-tit { font-size:24px; font-weight:700; color:#1A2733; letter-spacing:-.02em; margin:0 }
.stApp .entrada-sub { font-size:13.5px; color:#5B6B7B; margin:4px 0 18px }
.stApp .entrada-dica { font-size:12px; color:#8697A6; margin-top:14px; line-height:1.5 }
div[data-testid="stForm"] { border:none; padding:0 }
@media (max-width: 760px) {
  div[data-testid="stHorizontalBlock"]:has(.entrada-foto) > div[data-testid="stColumn"] {
    min-width:100% !important }
  .entrada-foto { min-height:0; padding:24px 22px; gap:22px }
  .entrada-lista { display:none }
}
</style>
"""


def _painel_foto() -> None:
    logo = LOGO.read_text(encoding="utf-8") if LOGO.exists() else ""
    st.markdown(
        f"""<div class="entrada-foto" style="--img:{url_foto('farmacia.jpg')}">
          <div>{logo}</div>
          <div>
            <h1>Decisões de compra com base nos seus dados</h1>
            <p>Painel de compras, estoque e apoio à decisão construído sobre as
               cotações eletrônicas da farmácia.</p>
            <ul class="entrada-lista">
              <li>Curva ABC e prioridades do mês</li>
              <li>Economia possível por fornecedor</li>
              <li>Risco de validade no estoque</li>
            </ul>
          </div></div>""",
        unsafe_allow_html=True)


def _entrar() -> None:
    with st.form("form_entrar", border=False):
        nome = st.text_input("Empresa", placeholder="Nome da empresa")
        senha = st.text_input("Senha", type="password", placeholder="Sua senha")
        enviar = st.form_submit_button("Entrar", type="primary", width="stretch",
                                       icon=":material/login:")
    if enviar:
        empresa = U.autenticar(nome, senha)
        if empresa:
            st.session_state["usuario"] = empresa
            st.rerun()
        st.error("Empresa ou senha incorretas.")


def _cadastrar() -> None:
    with st.form("form_cadastro", border=False, clear_on_submit=False):
        nome = st.text_input("Nome da empresa", placeholder="Ex.: Farmácia Central")
        senha = st.text_input("Senha", type="password",
                              help=f"Pelo menos {U.SENHA_MINIMA} caracteres.")
        confirmacao = st.text_input("Confirme a senha", type="password")
        enviar = st.form_submit_button("Criar acesso", width="stretch",
                                       icon=":material/person_add:")
    if enviar:
        erro = U.cadastrar(nome, senha, confirmacao)
        if erro:
            st.error(erro)
        else:
            st.success(f"Acesso de **{nome.strip()}** criado. Agora é só entrar na aba "
                       "**Entrar**.")


def tela_entrada() -> None:
    """Desenha a tela de entrada. Quem chama deve parar o script logo depois."""
    U.garantir_padrao()
    st.markdown(_CSS, unsafe_allow_html=True)
    foto, formulario = st.columns([1.05, 1])
    with foto:
        _painel_foto()
    with formulario:
        st.markdown("<p class='entrada-tit'>Acesso ao painel</p>"
                    "<p class='entrada-sub'>Entre com o nome da empresa e a senha.</p>",
                    unsafe_allow_html=True)
        aba_entrar, aba_cadastro = st.tabs(["Entrar", "Criar acesso"])
        with aba_entrar:
            _entrar()
        with aba_cadastro:
            _cadastrar()
        st.markdown("<p class='entrada-dica'>O acesso vale para esta aba do navegador até "
                    "você clicar em <b>Sair</b>, recarregar a página ou fechar a aba.</p>",
                    unsafe_allow_html=True)
