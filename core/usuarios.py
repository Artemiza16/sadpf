"""
Cadastro e conferência dos acessos ao painel.

Cada acesso é uma empresa (nome + senha), gravada em dados/usuarios.json. A
senha nunca é guardada como foi digitada: fica só o resultado do PBKDF2-SHA256
com um sal aleatório por empresa, o mesmo esquema usado por frameworks web como
o Django. Quem abrir o arquivo vê o hash, não a senha.

Na primeira execução o arquivo é criado com o acesso padrão (Farmacia / 123).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import unicodedata
from datetime import datetime

from core.dados import PASTA_DADOS

ARQUIVO_USUARIOS = PASTA_DADOS / "usuarios.json"
ACESSO_PADRAO = ("Farmacia", "123")
ITERACOES = 200_000
SENHA_MINIMA = 3


def _chave(nome: str) -> str:
    """'Farmácia ' e 'farmacia' são a mesma empresa no login."""
    sem_acento = unicodedata.normalize("NFKD", nome.strip()).encode("ASCII", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def _hash(senha: str, sal: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"),
                               bytes.fromhex(sal), ITERACOES).hex()


def _ler() -> dict:
    try:
        return json.loads(ARQUIVO_USUARIOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(usuarios: dict) -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    ARQUIVO_USUARIOS.write_text(json.dumps(usuarios, indent=2, ensure_ascii=False),
                                encoding="utf-8")


def _registro(nome: str, senha: str) -> dict:
    sal = secrets.token_hex(16)
    return {"nome": nome.strip(), "sal": sal, "hash": _hash(senha, sal),
            "criado_em": datetime.now().strftime("%d/%m/%Y %H:%M")}


def garantir_padrao() -> None:
    """Cria o arquivo com o acesso padrão, se ainda não houver nenhum acesso."""
    usuarios = _ler()
    if not usuarios:
        nome, senha = ACESSO_PADRAO
        _gravar({_chave(nome): _registro(nome, senha)})


def autenticar(nome: str, senha: str) -> str | None:
    """Nome da empresa como foi cadastrado, se nome e senha conferem."""
    garantir_padrao()
    registro = _ler().get(_chave(nome))
    if not registro or not senha:
        return None
    # comparação em tempo constante, para não revelar quantos caracteres acertou
    if hmac.compare_digest(_hash(senha, registro["sal"]), registro["hash"]):
        return registro["nome"]
    return None


def cadastrar(nome: str, senha: str, confirmacao: str) -> str:
    """Grava uma empresa nova. Devolve '' se deu certo, ou o motivo da recusa."""
    nome = " ".join(nome.split())
    if len(nome) < 3:
        return "Informe o nome da empresa (pelo menos 3 letras)."
    if len(senha) < SENHA_MINIMA:
        return f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
    if senha != confirmacao:
        return "A confirmação não é igual à senha."
    garantir_padrao()
    usuarios = _ler()
    if _chave(nome) in usuarios:
        return "Já existe uma empresa com esse nome. Use a aba Entrar."
    usuarios[_chave(nome)] = _registro(nome, senha)
    try:
        _gravar(usuarios)
    except OSError as erro:
        return f"Não foi possível gravar o cadastro: {erro}"
    return ""
