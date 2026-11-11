"""
Cadastro manual de compras, no mesmo formato do arquivo de importação.

A tela Base de Dados › Cadastro manual monta as linhas com estas funções e só
grava pelo mesmo caminho da importação (dados.mesclar), que guarda uma cópia da
base anterior. Nada aqui desenha na tela.

As regras de validação saíram da própria base (conferidas em todas as 1.657
linhas): uma data por cotação; um fornecedor, uma cotação, um prazo, um
faturamento mínimo e um representante por pedido; um EAN, uma descrição e uma
categoria por código de produto; quantidade respondida ≤ cotada; faixa de
recebimento calculada pelas três datas; CNPJ e EAN com dígito verificador.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd

from core import dados as D

ORIGEM_MANUAL = "cadastro manual"

# Colunas do modelo de importação, na ordem da base consolidada. As de origem
# (arquivo e linha) e as calculadas são preenchidas pelo sistema.
COLUNAS_MODELO = [
    "Cotação", "Pedido", "Status do Pedido", "Data de Criação", "CNPJ Fornecedor",
    "Nome do Fornecedor", "Representante", "Prazo de Pagamento", "Faturamento Mínimo", "M/L",
    "Código do Produto", "EAN", "Descrição do Produto", "Fabricante", "Qtde. Cot", "Qtde. Resp",
    "Qtde. Ped.", "Qtde. Fat.", "Desc. Com. (%)", "Vl. Custo (R$)", "Vl. Faturado (R$)",
    "Qtde. Ped. x Vl. Custo (R$)", "Forma Farmacêutica", "Categoria Comercial",
    "Data de Fabricação", "Data de Validade", "Lote", "Faixa de Recebimento",
    "Preço de Venda Unitário (R$)",
]
CALCULADAS = {"Qtde. Ped. x Vl. Custo (R$)": "Qtde. Ped. × Vl. Custo",
              "Faixa de Recebimento": "(validade − data da compra) ÷ (validade − fabricação)"}
STATUS_CONHECIDOS = ["Faturado", "Faturado Parcialmente", "Enviado", "Cancelado"]

# o que cada campo exige, para o modelo em Excel e para a tela
DESCRICAO_CAMPOS = {
    "Cotação": "número da cotação; se já existir, a data de criação tem de ser a mesma",
    "Pedido": "número do pedido; um pedido pertence a um só fornecedor e a uma só cotação",
    "Status do Pedido": "só 'Faturado' entra na análise (regra STATUS_MANTIDOS)",
    "Data de Criação": "data da cotação (dd/mm/aaaa)",
    "CNPJ Fornecedor": "14 dígitos, com dígito verificador válido",
    "Nome do Fornecedor": "distribuidor", "Representante": "vendedor do distribuidor",
    "Prazo de Pagamento": "em dias, gravado como 'N dia(s)'",
    "Faturamento Mínimo": "valor mínimo do pedido para o distribuidor faturar (R$)",
    "M/L": "M = preço monitorado, L = liberado",
    "Código do Produto": "código do produto; um código tem um só EAN e uma só descrição",
    "EAN": "código de barras de 8, 12, 13 ou 14 dígitos, com dígito verificador válido",
    "Descrição do Produto": "nome do medicamento", "Fabricante": "laboratório",
    "Qtde. Cot": "quantidade cotada", "Qtde. Resp": "quantidade respondida (≤ cotada)",
    "Qtde. Ped.": "quantidade pedida (maior que zero)",
    "Qtde. Fat.": "quantidade faturada (normalmente ≤ pedida)",
    "Desc. Com. (%)": "desconto comercial, de 0 a 100",
    "Vl. Custo (R$)": "custo unitário (maior que zero)",
    "Vl. Faturado (R$)": "valor unitário na nota (na base atual, igual ao custo)",
    "Qtde. Ped. x Vl. Custo (R$)": "calculado pelo sistema",
    "Forma Farmacêutica": "uma das formas já cadastradas",
    "Categoria Comercial": "uma das categorias já cadastradas",
    "Data de Fabricação": "anterior à data da compra",
    "Data de Validade": "posterior à data da compra",
    "Lote": "código do lote (até 20 letras e números)",
    "Faixa de Recebimento": "calculada pelo sistema a partir das três datas",
    "Preço de Venda Unitário (R$)": "preço de venda ao consumidor (maior que zero)",
}


# ---------------------------------------------------------------------------
#                         DÍGITOS VERIFICADORES E DATAS
# ---------------------------------------------------------------------------
def so_digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor if valor is not None else "")).lstrip("0") or "0"


def cnpj_valido(valor) -> bool:
    """Dígitos verificadores do CNPJ (a base guarda sem o zero à esquerda)."""
    s = re.sub(r"\D", "", str(valor)).zfill(14)
    if len(s) != 14 or s == s[0] * 14:
        return False

    def dv(corpo, pesos):
        r = sum(int(a) * b for a, b in zip(corpo, pesos)) % 11
        return "0" if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return s[12] == dv(s[:12], p1) and s[13] == dv(s[:13], [6] + p1)


def ean_valido(valor) -> bool:
    """Dígito verificador GTIN (EAN-8, UPC-12, EAN-13, GTIN-14)."""
    s = re.sub(r"\D", "", str(valor))
    if len(s) not in (8, 12, 13, 14):
        return False
    d = [int(c) for c in s]
    soma = sum(x * (3 if i % 2 == 0 else 1) for i, x in enumerate(d[:-1][::-1]))
    return (10 - soma % 10) % 10 == d[-1]


def para_serial(valor) -> float | None:
    """Data (date, datetime, Timestamp ou texto dd/mm/aaaa) → serial do Excel."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    serie = D._para_serial(pd.Series([valor], dtype="object"))
    v = serie.iloc[0]
    return None if pd.isna(v) else float(v)


def faixa_recebimento(criacao: float, fabricacao: float, validade: float) -> str | None:
    """Quanto restava da validade quando o lote chegou (regra conferida na base)."""
    if None in (criacao, fabricacao, validade) or validade <= fabricacao:
        return None
    fracao = (validade - np.floor(criacao)) / (validade - fabricacao)
    if fracao >= 0.7:
        return "Fresco (≥70%)"
    if fracao >= 0.5:
        return "Normal (50-70%)"
    if fracao >= 0.3:
        return "Curto (30-50%)"
    return "Crítico (<30%)"


# ---------------------------------------------------------------------------
#                                MONTAGEM
# ---------------------------------------------------------------------------
def montar_linhas(pedido: dict, itens: list[dict], quando: datetime | None = None
                  ) -> pd.DataFrame:
    """Pedido (campos comuns) + itens → linhas no formato da base.

    Preenche o que é calculado: valor pedido, faixa de recebimento, prazo como
    'N dia(s)', valor faturado igual ao custo quando vier vazio, e a origem
    ('cadastro manual' + data e hora) com o número da linha.
    """
    quando = quando or datetime.now()
    linhas = []
    for n, item in enumerate(itens, 1):
        linha = {**pedido, **item}
        prazo = linha.get("Prazo de Pagamento")
        if isinstance(prazo, (int, float)) and not pd.isna(prazo):
            linha["Prazo de Pagamento"] = f"{int(prazo)} dia(s)"
        for c in ("Data de Criação", "Data de Fabricação", "Data de Validade"):
            linha[c] = para_serial(linha.get(c))
        if not linha.get("Vl. Faturado (R$)"):
            linha["Vl. Faturado (R$)"] = linha.get("Vl. Custo (R$)")
        ped, custo = linha.get("Qtde. Ped."), linha.get("Vl. Custo (R$)")
        linha["Qtde. Ped. x Vl. Custo (R$)"] = (round(float(ped) * float(custo), 2)
                                                if ped is not None and custo is not None
                                                else None)
        linha["Faixa de Recebimento"] = faixa_recebimento(
            linha["Data de Criação"], linha["Data de Fabricação"], linha["Data de Validade"])
        linha["arquivo_origem"] = f"{ORIGEM_MANUAL} {quando:%d/%m/%Y %H:%M}"
        linha["linha_origem"] = n
        linhas.append(linha)
    df = pd.DataFrame(linhas)
    for c in COLUNAS_MODELO + ["arquivo_origem", "linha_origem"]:
        if c not in df.columns:
            df[c] = None
    return df[["arquivo_origem", "linha_origem"] + COLUNAS_MODELO]


# ---------------------------------------------------------------------------
#                                VALIDAÇÃO
# ---------------------------------------------------------------------------
@dataclass
class Validacao:
    erros: list[tuple[int, str, str]] = field(default_factory=list)    # linha, campo, motivo
    avisos: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.erros

    def tabela(self) -> pd.DataFrame:
        linhas = ([("Erro", *e) for e in self.erros] + [("Aviso", *a) for a in self.avisos])
        return pd.DataFrame(linhas, columns=["Tipo", "Linha", "Campo", "Motivo"])


def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v)) or \
        (isinstance(v, str) and not v.strip()) or (v is pd.NA) or (v is pd.NaT)


def _num(v):
    try:
        x = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
        return None if np.isnan(x) else x
    except (TypeError, ValueError):
        return None


def validar(linhas: pd.DataFrame, base: pd.DataFrame, hoje: date | None = None) -> Validacao:
    """Confere linhas novas contra a base antes de gravar.

    Erros impedem a gravação; avisos só pedem atenção. `base` é a base com os
    nomes originais (a mesma que a importação usa).
    """
    v = Validacao()
    hoje_serial = para_serial(pd.Timestamp(hoje or date.today()))
    obrig = [c for c in COLUNAS_MODELO if c not in CALCULADAS]
    formas = set(base["Forma Farmacêutica"].dropna().astype(str))
    categorias = set(base["Categoria Comercial"].dropna().astype(str))
    chaves_base = set(D.chave_linha(base))
    data_cot = base.groupby(D.texto_chave(base["Cotação"]))["Data de Criação"].first()
    por_pedido = base.assign(_p=D.texto_chave(base["Pedido"])).groupby("_p").first()
    por_codigo = base.assign(_c=D.texto_chave(base["Código do Produto"])).groupby("_c").first()
    codigo_do_ean = (base.assign(_e=D.texto_chave(base["EAN"]),
                                 _c=D.texto_chave(base["Código do Produto"]))
                     .groupby("_e")["_c"].agg(lambda s: set(s)))
    cnpjs_do_forn = base.groupby(base["Nome do Fornecedor"].astype(str).str.strip())[
        "CNPJ Fornecedor"].agg(lambda s: {so_digitos(x) for x in s})
    vistos: dict[str, int] = {}

    for i, r in linhas.reset_index(drop=True).iterrows():
        n = i + 1
        erro = lambda campo, motivo: v.erros.append((n, campo, motivo))   # noqa: E731
        aviso = lambda campo, motivo: v.avisos.append((n, campo, motivo))  # noqa: E731

        for c in obrig:
            if _vazio(r.get(c)):
                erro(c, "campo obrigatório vazio")
        # ------------------------------------------------ números e faixas
        inteiros = ["Cotação", "Pedido", "Qtde. Cot", "Qtde. Resp", "Qtde. Ped.", "Qtde. Fat."]
        for c in inteiros:
            x = _num(r.get(c))
            if not _vazio(r.get(c)) and (x is None or x != int(x) or x < 0):
                erro(c, "deve ser um número inteiro maior ou igual a zero")
        for c in ("Vl. Custo (R$)", "Preço de Venda Unitário (R$)", "Vl. Faturado (R$)"):
            x = _num(r.get(c))
            if not _vazio(r.get(c)) and (x is None or x <= 0):
                erro(c, "deve ser um valor maior que zero")
        qc, qr, qp, qf = (_num(r.get(c)) for c in ("Qtde. Cot", "Qtde. Resp", "Qtde. Ped.",
                                                     "Qtde. Fat."))
        if qp is not None and qp == 0:
            erro("Qtde. Ped.", "pedido com quantidade zero não é uma compra")
        if qc is not None and qr is not None and qr > qc:
            erro("Qtde. Resp", f"respondida ({qr:.0f}) maior que a cotada ({qc:.0f})")
        if qp is not None and qf is not None and qf > qp:
            aviso("Qtde. Fat.", f"faturada ({qf:.0f}) maior que a pedida ({qp:.0f})")
        desc = _num(r.get("Desc. Com. (%)"))
        if desc is not None and not 0 <= desc <= 100:
            erro("Desc. Com. (%)", "o desconto vai de 0 a 100")
        custo, preco = _num(r.get("Vl. Custo (R$)")), _num(r.get("Preço de Venda Unitário (R$)"))
        if custo and preco and preco < custo:
            aviso("Preço de Venda Unitário (R$)", "preço de venda abaixo do custo (margem negativa)")
        fminimo = _num(r.get("Faturamento Mínimo"))
        if not _vazio(r.get("Faturamento Mínimo")) and (fminimo is None or fminimo < 0):
            erro("Faturamento Mínimo", "deve ser um valor maior ou igual a zero")
        # ------------------------------------------------------------ datas
        cr, fa, va = (r.get(c) for c in ("Data de Criação", "Data de Fabricação",
                                          "Data de Validade"))
        if all(x is not None and not pd.isna(x) for x in (cr, fa, va)):
            if fa >= np.floor(cr) + 1:
                erro("Data de Fabricação", "fabricação depois da data da compra")
            if va <= fa:
                erro("Data de Validade", "validade igual ou anterior à fabricação")
            elif va <= np.floor(cr):
                erro("Data de Validade", "o lote chegaria já vencido")
            elif r.get("Faixa de Recebimento") == "Crítico (<30%)":
                aviso("Data de Validade", "chegou com menos de 30% da validade (faixa crítica)")
        if cr is not None and not pd.isna(cr) and hoje_serial and cr > hoje_serial + 1:
            erro("Data de Criação", "data no futuro")
        # ---------------------------------------------------------- textos
        if not _vazio(r.get("Status do Pedido")):
            status = str(r["Status do Pedido"]).strip()
            if D.STATUS_MANTIDOS and status not in D.STATUS_MANTIDOS:
                erro("Status do Pedido", f"'{status}' não entra na análise (só "
                                         f"{', '.join(D.STATUS_MANTIDOS)}); a linha seria descartada")
        if not _vazio(r.get("M/L")) and str(r["M/L"]).strip() not in ("M", "L"):
            erro("M/L", "use M ou L")
        if not _vazio(r.get("Forma Farmacêutica")) and str(r["Forma Farmacêutica"]) not in formas:
            erro("Forma Farmacêutica", "forma não cadastrada; escolha uma da lista")
        if not _vazio(r.get("Categoria Comercial")) and str(r["Categoria Comercial"]) not in categorias:
            erro("Categoria Comercial", "categoria não cadastrada; escolha uma da lista")
        lote = str(r.get("Lote") or "").strip()
        if lote and not re.fullmatch(r"[A-Za-z0-9\-/\.]{1,20}", lote):
            erro("Lote", "use até 20 letras, números, hífen, barra ou ponto")
        if not _vazio(r.get("Prazo de Pagamento")) and \
                not re.fullmatch(r"\d{1,3} dia\(s\)", str(r["Prazo de Pagamento"]).strip()):
            erro("Prazo de Pagamento", "informe o número de dias")
        # ---------------------------------------------------- dígitos verif.
        if not _vazio(r.get("CNPJ Fornecedor")) and not cnpj_valido(r["CNPJ Fornecedor"]):
            erro("CNPJ Fornecedor", "CNPJ inválido (dígito verificador)")
        ean = D.texto_chave(pd.Series([r.get("EAN")])).iloc[0]
        codigo = D.texto_chave(pd.Series([r.get("Código do Produto")])).iloc[0]
        if ean and not ean_valido(ean):
            (aviso if codigo in por_codigo.index else erro)(
                "EAN", "EAN com dígito verificador inválido")
        # ------------------------------------------- consistência com a base
        cot = D.texto_chave(pd.Series([r.get("Cotação")])).iloc[0]
        ped = D.texto_chave(pd.Series([r.get("Pedido")])).iloc[0]
        if cot in data_cot.index and cr is not None and not pd.isna(cr) and \
                abs(float(data_cot[cot]) - float(cr)) >= 1:
            erro("Data de Criação", f"a cotação {cot} já existe com outra data")
        if ped in por_pedido.index:
            antes = por_pedido.loc[ped]
            for c in ("Nome do Fornecedor", "Cotação", "Prazo de Pagamento",
                      "Faturamento Mínimo", "Representante"):
                if not _vazio(r.get(c)) and \
                        D.texto_chave(pd.Series([antes[c]])).iloc[0] != \
                        D.texto_chave(pd.Series([r[c]])).iloc[0]:
                    erro(c, f"o pedido {ped} já existe com {c.lower()} '{antes[c]}'")
        if codigo in por_codigo.index:
            antes = por_codigo.loc[codigo]
            for c in ("EAN", "Descrição do Produto", "Categoria Comercial"):
                if not _vazio(r.get(c)) and \
                        D.texto_chave(pd.Series([antes[c]])).iloc[0].strip() != \
                        D.texto_chave(pd.Series([r[c]])).iloc[0].strip():
                    erro(c, f"o código {codigo} já está cadastrado com {c.lower()} "
                            f"'{antes[c]}'")
        if ean in codigo_do_ean.index and codigo not in codigo_do_ean[ean]:
            aviso("EAN", f"este EAN já pertence ao código {', '.join(sorted(codigo_do_ean[ean]))}")
        forn = str(r.get("Nome do Fornecedor") or "").strip()
        if forn in cnpjs_do_forn.index and not _vazio(r.get("CNPJ Fornecedor")) and \
                so_digitos(r["CNPJ Fornecedor"]) not in cnpjs_do_forn[forn]:
            aviso("CNPJ Fornecedor", "CNPJ diferente dos já registrados para este fornecedor "
                                     "(outra filial?)")
        # ------------------------------------------------------ duplicidade
        chave = f"{cot}|{ped}|{codigo}"
        if chave in chaves_base:
            erro("Código do Produto", f"o produto {codigo} já está no pedido {ped} da cotação "
                                      f"{cot} (linha duplicada)")
        if chave in vistos:
            erro("Código do Produto", f"repete a linha {vistos[chave]} deste cadastro")
        vistos.setdefault(chave, n)
    return v


# ---------------------------------------------------------------------------
#                       MODELO DE IMPORTAÇÃO EM EXCEL
# ---------------------------------------------------------------------------
def modelo_excel(base: pd.DataFrame) -> bytes:
    """Planilha com as colunas do modelo, uma linha de exemplo e as instruções."""
    exemplo = base.sort_values("Data de Criação").iloc[[-1]][COLUNAS_MODELO].copy()
    for c in ("Data de Criação", "Data de Fabricação", "Data de Validade"):
        exemplo[c] = D._para_data(exemplo[c]).dt.strftime("%d/%m/%Y")
    instrucoes = pd.DataFrame({
        "Coluna": COLUNAS_MODELO,
        "Obrigatória": ["calculada" if c in CALCULADAS else "sim" for c in COLUNAS_MODELO],
        "O que preencher": [DESCRICAO_CAMPOS.get(c, "") for c in COLUNAS_MODELO]})
    saida = io.BytesIO()
    with pd.ExcelWriter(saida, engine="openpyxl") as w:
        exemplo.to_excel(w, sheet_name="Cotação", index=False)
        instrucoes.to_excel(w, sheet_name="Instruções", index=False)
    return saida.getvalue()
