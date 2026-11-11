"""
Movimentação de estoque: o livro-razão de entradas, vendas e perdas.

A base de cotação registra só as compras. O livro de movimentação, gerado a
partir dela (pasta movimentacao/), completa o fluxo: estoque inicial, entradas,
saídas por venda e perdas por validade, com o saldo após cada movimento e o
lote consumido. Com ele o sistema passa a medir giro, cobertura, ruptura,
excesso, perda real por vencimento, Curva ABC por vendas e ponto de pedido.

Natureza do dado, que acompanha todos os resultados:
- ENTRADA é real: cada linha vem de uma linha faturada da base de cotação;
- ESTOQUE_INICIAL, SAIDA_VENDA e PERDA_VALIDADE são simulados pelo gerador
  descrito em SADPF_documentacao_tecnica.pdf (mesma pasta).
Os indicadores de venda mostram que o sistema funciona e como decidiria; não
medem a farmácia. Quando a farmácia exportar as vendas reais no mesmo layout,
basta trocar o arquivo: todo o cálculo deste módulo vale igual.

Nada aqui depende da interface: as funções recebem tabelas e devolvem tabelas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from core import dados as D
from core import metricas as M
from core.parametros import Parametros

PASTA_MOV = Path(__file__).parent.parent / "movimentacao"
PASTA_HISTORICO_MOV = PASTA_MOV / "historico"
CACHE_MOV = D.PASTA_DADOS / "movimentacao_estoque.csv"
PADRAO_LIVRO = "SADPF_movimentacao_estoque*.xlsx"
NOME_LIVRO = "SADPF_movimentacao_estoque.xlsx"
ABA_LIVRO = "Movimentação"
LINHA_CABECALHO = 3            # as três primeiras linhas da aba são título e nota

TIPOS = {"ESTOQUE_INICIAL": "Estoque inicial", "ENTRADA": "Entrada (compra)",
         "SAIDA_VENDA": "Venda", "PERDA_VALIDADE": "Perda por validade"}
SINAL = {"ESTOQUE_INICIAL": 1, "ENTRADA": 1, "SAIDA_VENDA": -1, "PERDA_VALIDADE": -1}

COLUNAS_LIVRO = [
    "id_movimento", "data_movimento", "tipo_movimento", "origem_dado", "EAN",
    "Código do Produto", "Descrição do Produto", "Categoria Comercial",
    "Forma Farmacêutica", "Classe Terapêutica", "Lote", "Data de Validade",
    "quantidade", "custo_unitario", "preco_venda_unitario", "valor_total",
    "saldo_apos_movimento", "Cotação", "Pedido", "Nome do Fornecedor",
    "arquivo_origem", "linha_origem",
]

SITUACOES = ["Ruptura", "Descontinuado", "Estoque crítico", "Validade próxima",
             "Excesso", "Sem giro recente", "Normal"]


# ---------------------------------------------------------------------------
#                                  LEITURA
# ---------------------------------------------------------------------------
def _mais_recente(padrao: str) -> Path | None:
    """Arquivo mais novo da pasta movimentacao/ que segue o padrão do nome.

    Aceita os sufixos que o navegador acrescenta ao baixar de novo ("(1)",
    "(2)"): vale sempre o arquivo gravado por último.
    """
    if not PASTA_MOV.exists():
        return None
    achados = [a for a in PASTA_MOV.glob(padrao) if a.is_file()]
    return max(achados, key=lambda a: a.stat().st_mtime) if achados else None


PADRAO_CSV = "movimentacao_estoque*.csv"


def arquivo_livro() -> Path | None:
    """Fonte do livro: o CSV exportado pelo gerador, se existir; senão a planilha.

    O CSV tem as mesmas colunas da aba Movimentação e é lido em uma fração do
    tempo. Os dois foram conferidos linha a linha (24.167 movimentos idênticos).
    """
    return _mais_recente(PADRAO_CSV) or _mais_recente(PADRAO_LIVRO)


def versao() -> float:
    """Marca de tempo do livro; muda quando um arquivo novo é colocado na pasta."""
    arq = arquivo_livro()
    return arq.stat().st_mtime if arq else 0.0


def disponivel() -> bool:
    return arquivo_livro() is not None


def _normalizar(bruto: pd.DataFrame) -> pd.DataFrame:
    """Tipos e colunas auxiliares; falha com a lista do que faltar."""
    faltam = [c for c in COLUNAS_LIVRO if c not in bruto.columns]
    if faltam:
        raise ValueError("faltam colunas no livro de movimentação: " + ", ".join(faltam))
    m = bruto.copy()
    m["data"] = pd.to_datetime(m["data_movimento"], errors="coerce").dt.normalize()
    m["validade"] = pd.to_datetime(m["Data de Validade"], errors="coerce")
    m["ean"] = D.texto_chave(m["EAN"])
    m["sku"] = D.texto_chave(m["Código do Produto"])
    m["tipo"] = m["tipo_movimento"].astype(str).str.strip()
    m["origem"] = m["origem_dado"].astype(str).str.strip()
    m["medicamento"] = m["Descrição do Produto"].astype(str).str.strip()
    m["Lote"] = m["Lote"].astype(str).str.strip()
    for c in ("quantidade", "saldo_apos_movimento"):
        m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0).astype("int64")
    for c in ("custo_unitario", "preco_venda_unitario", "valor_total", "linha_origem"):
        m[c] = pd.to_numeric(m[c], errors="coerce")
    m["ano_mes"] = m["data"].dt.to_period("M").astype(str)
    return m.sort_values("id_movimento", kind="stable").reset_index(drop=True)


def ler_livro(origem, nome: str = "") -> pd.DataFrame:
    """Lê o livro: CSV (separador ;, decimal ,) ou a aba Movimentação da planilha."""
    nome = nome or str(getattr(origem, "name", origem))
    if nome.lower().endswith(".csv"):
        bruto = pd.read_csv(origem, sep=";", decimal=",", encoding="utf-8-sig",
                            dtype={"EAN": str, "Código do Produto": str, "Lote": str})
    else:
        bruto = pd.read_excel(origem, sheet_name=ABA_LIVRO, header=LINHA_CABECALHO)
    return _normalizar(bruto)


_MEMO: dict = {}


def carregar() -> pd.DataFrame | None:
    """Livro de movimentação pronto para uso, ou None se a pasta estiver vazia.

    A primeira leitura da planilha (cerca de 3 s) gera um CSV em dados/; as
    seguintes leem o CSV, a não ser que a planilha seja mais nova que ele.
    """
    arq = arquivo_livro()
    if arq is None:
        return None
    chave = (str(arq), arq.stat().st_mtime)
    if chave in _MEMO:
        return _MEMO[chave]
    mov = None
    if arq.suffix.lower() == ".csv":
        mov = ler_livro(arq)
        _MEMO.clear()
        _MEMO[chave] = mov
        return mov
    if CACHE_MOV.exists() and CACHE_MOV.stat().st_mtime >= arq.stat().st_mtime:
        try:
            bruto = pd.read_csv(CACHE_MOV, sep=";", decimal=",", encoding="utf-8-sig",
                                dtype={"EAN": str, "Código do Produto": str, "Lote": str})
            mov = _normalizar(bruto)
        except (OSError, ValueError):
            mov = None
    if mov is None:
        mov = ler_livro(arq)
        try:
            D.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
            mov[COLUNAS_LIVRO + ["observacao"]].to_csv(
                CACHE_MOV, index=False, sep=";", decimal=",", encoding="utf-8-sig")
        except (OSError, KeyError):
            pass
    _MEMO.clear()
    _MEMO[chave] = mov
    return mov


def _csv_auxiliar(padrao: str) -> pd.DataFrame | None:
    arq = _mais_recente(padrao)
    if arq is None:
        return None
    try:
        return pd.read_csv(arq, sep=";", decimal=",", encoding="utf-8-sig",
                           dtype={"EAN": str})
    except (OSError, ValueError):
        return None


def remarcacao() -> pd.DataFrame:
    """Propostas de remarcação por validade geradas junto com o livro."""
    prop = _csv_auxiliar("proposta_remarcacao*.csv")
    if prop is None:
        return pd.DataFrame()
    prop["ean"] = D.texto_chave(prop["EAN"])
    prop["Lote"] = prop["Lote"].astype(str).str.strip()
    prop["validade"] = pd.to_datetime(prop["Data de Validade"], errors="coerce")
    return prop


def validacao_do_gerador() -> pd.DataFrame:
    """As 80 verificações que o próprio gerador da base executou."""
    val = _csv_auxiliar("validacao_integridade*.csv")
    return val if val is not None else pd.DataFrame()


def substituir_livro(conteudo: bytes, base: pd.DataFrame,
                     nome: str = NOME_LIVRO) -> tuple[bool, pd.DataFrame]:
    """Troca o livro por uma versão nova (.csv ou .xlsx), só se ela passar na validação.

    O arquivo anterior vai para movimentacao/historico/. Devolve (gravou?,
    resultado da validação) para a tela mostrar o motivo de uma recusa.
    """
    import io
    from datetime import datetime
    csv = nome.lower().endswith(".csv")
    try:
        novo = ler_livro(io.BytesIO(conteudo), nome)
    except Exception as erro:                       # noqa: BLE001
        return False, pd.DataFrame([{"bloco": "Leitura", "verificacao": "Arquivo legível",
                                     "resultado": "FALHOU", "detalhe": str(erro)}])
    resultado = validar(novo, base)
    if (resultado["resultado"] == "FALHOU").any():
        return False, resultado
    PASTA_MOV.mkdir(parents=True, exist_ok=True)
    # o CSV tem prioridade sobre a planilha: a versão anterior do mesmo formato e,
    # se a nova for planilha, também um CSV antigo vão para o histórico
    padroes = [PADRAO_CSV] if csv else [PADRAO_CSV, PADRAO_LIVRO]
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    for padrao in padroes:
        for atual in PASTA_MOV.glob(padrao):
            PASTA_HISTORICO_MOV.mkdir(parents=True, exist_ok=True)
            atual.replace(PASTA_HISTORICO_MOV / f"{atual.stem}-{carimbo}{atual.suffix}")
    (PASTA_MOV / ("movimentacao_estoque.csv" if csv else NOME_LIVRO)).write_bytes(conteudo)
    _MEMO.clear()
    return True, resultado


def anonimizar(mov: pd.DataFrame, mapas: dict) -> pd.DataFrame:
    """Fornecedores trocados pelos mesmos códigos usados no resto do sistema."""
    mov = mov.copy()
    nomes = mov["Nome do Fornecedor"].astype(str).str.strip()
    codigos = nomes.map(mapas.get("Nome do Fornecedor", {}))
    mov["Nome do Fornecedor"] = codigos.where(mov["Nome do Fornecedor"].notna())
    return mov


# ---------------------------------------------------------------------------
#                                  RECORTE
# ---------------------------------------------------------------------------
@dataclass
class Recorte:
    """O livro limitado aos produtos e ao período dos filtros globais.

    `mov` vai do início do livro até `fim`: o saldo de uma data depende de
    tudo o que veio antes dela. Os fluxos (vendas, compras, perdas) contam só
    o intervalo [inicio, fim].
    """
    mov: pd.DataFrame
    inicio: pd.Timestamp
    fim: pd.Timestamp

    @property
    def periodo(self) -> pd.DataFrame:
        return self.mov[self.mov["data"] >= self.inicio]

    @property
    def dias(self) -> int:
        return max(1, (self.fim - self.inicio).days + 1)


def recortar(mov: pd.DataFrame, eans: set | None = None,
             inicio=None, fim=None) -> Recorte:
    limite_ini, limite_fim = mov["data"].min(), mov["data"].max()
    ini = max(pd.Timestamp(inicio), limite_ini) if inicio is not None else limite_ini
    fim_ = min(pd.Timestamp(fim), limite_fim) if fim is not None else limite_fim
    m = mov[mov["data"] <= fim_]
    if eans is not None:
        m = m[m["ean"].isin(eans)]
    return Recorte(m, ini, fim_)


def eans_do_recorte(recorte_compras: pd.DataFrame) -> set:
    """Produtos que os filtros de compra deixaram no recorte."""
    return set(D.texto_chave(recorte_compras["EAN"]))


# ---------------------------------------------------------------------------
#                       POSIÇÃO E INDICADORES POR PRODUTO
# ---------------------------------------------------------------------------
def _estoque_medio(m: pd.DataFrame, inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.Series:
    """Saldo médio ponderado pelo tempo, no intervalo [inicio, fim].

    Cada saldo vale do dia do movimento até o próximo movimento do produto; o
    intervalo que começou antes do início do período entra só com a parte que
    cai dentro dele.
    """
    dia = (m.sort_values(["ean", "data", "id_movimento"])
             .drop_duplicates(["ean", "data"], keep="last")[["ean", "data",
                                                            "saldo_apos_movimento"]])
    proximo = dia.groupby("ean")["data"].shift(-1).fillna(fim + pd.Timedelta(days=1))
    comeco = dia["data"].clip(lower=inicio)
    final = proximo.clip(upper=fim + pd.Timedelta(days=1))
    dur = (final - comeco).dt.days.clip(lower=0)
    peso = dur * dia["saldo_apos_movimento"]
    soma_peso = peso.groupby(dia["ean"]).sum()
    soma_dur = dur.groupby(dia["ean"]).sum()
    return (soma_peso / soma_dur.replace(0, np.nan)).fillna(0.0)


def _lotes(m: pd.DataFrame) -> pd.DataFrame:
    """Saldo e custo de cada lote.

    Saldo = soma das quantidades dos movimentos do lote. Custo unitário = custo
    residual: o que entrou a custo menos o que saiu a custo, dividido pelo saldo.
    Um mesmo código de lote pode chegar em duas compras com custos diferentes
    (45 lotes na base atual); a média simples dos custos fazia a ponte do estoque
    (inicial + entradas − saídas = final) não fechar. Lote zerado fica com o custo
    médio ponderado das entradas.
    """
    entra = m[m["quantidade"] > 0]
    sai = m[m["quantidade"] < 0]
    valor_in = entra.groupby(["ean", "Lote"])["valor_total"].sum()
    qtd_in = entra.groupby(["ean", "Lote"])["quantidade"].sum()
    valor_out = (sai["quantidade"] * sai["custo_unitario"]).groupby([sai["ean"], sai["Lote"]]).sum()
    lotes = (m.groupby(["ean", "Lote"])
               .agg(saldo=("quantidade", "sum"), validade=("validade", "max")))
    residual = valor_in.reindex(lotes.index).fillna(0) + valor_out.reindex(lotes.index).fillna(0)
    medio = (valor_in / qtd_in.replace(0, np.nan)).reindex(lotes.index)
    lotes["custo"] = np.where(lotes["saldo"] > 0,
                              residual / lotes["saldo"].where(lotes["saldo"] > 0), medio)
    return lotes.reset_index()


def posicao(rec: Recorte, p: Parametros) -> pd.DataFrame:
    """Uma linha por produto com saldo, fluxo, giro, cobertura, situação e reposição."""
    m, ref = rec.mov, rec.fim
    if m.empty:
        return pd.DataFrame()
    per = rec.periodo
    janela = int(p.mov_janela_demanda)

    cad = (m.sort_values("id_movimento")
             .groupby("ean")
             .agg(sku=("sku", "last"), medicamento=("medicamento", "last"),
                  categoria=("Categoria Comercial", "last"),
                  forma=("Forma Farmacêutica", "last"),
                  classe_terapeutica=("Classe Terapêutica", "last"),
                  estoque_atual=("saldo_apos_movimento", "last"),
                  soma_movimentos=("quantidade", "sum")))

    qtd = m.pivot_table(index="ean", columns="tipo", values="quantidade",
                        aggfunc="sum", fill_value=0)
    for t in TIPOS:
        if t not in qtd.columns:
            qtd[t] = 0
    cad["estoque_inicial"] = qtd["ESTOQUE_INICIAL"]
    cad["entradas_total"] = qtd["ENTRADA"]

    vend = per[per["tipo"] == "SAIDA_VENDA"]
    perda = per[per["tipo"] == "PERDA_VALIDADE"]
    ent = per[per["tipo"] == "ENTRADA"]
    cad["vendas"] = (-vend.groupby("ean")["quantidade"].sum()).reindex(cad.index).fillna(0)
    cad["faturamento"] = vend.groupby("ean")["valor_total"].sum().reindex(cad.index).fillna(0)
    cad["cmv"] = ((-vend["quantidade"]) * vend["custo_unitario"]) \
        .groupby(vend["ean"]).sum().reindex(cad.index).fillna(0)
    cad["perdas"] = (-perda.groupby("ean")["quantidade"].sum()).reindex(cad.index).fillna(0)
    cad["valor_perdas"] = (-perda.groupby("ean")["valor_total"].sum()) \
        .reindex(cad.index).fillna(0)
    cad["entradas"] = ent.groupby("ean")["quantidade"].sum().reindex(cad.index).fillna(0)
    cad["valor_compras"] = ent.groupby("ean")["valor_total"].sum().reindex(cad.index).fillna(0)
    cad["margem"] = cad["faturamento"] - cad["cmv"]
    cad["margem_pct"] = cad["margem"] / cad["faturamento"].replace(0, np.nan)

    # demanda recente: a janela das Preferências, terminando na data de referência
    todas_vendas = m[m["tipo"] == "SAIDA_VENDA"]
    # "últimos 90 dias" inclui o dia de início, como no gerador da base
    rec_v = todas_vendas[todas_vendas["data"] >= ref - pd.Timedelta(days=janela)]
    diario = (-rec_v.groupby(["ean", "data"])["quantidade"].sum())
    soma = diario.groupby(level=0).sum().reindex(cad.index).fillna(0)
    soma2 = (diario ** 2).groupby(level=0).sum().reindex(cad.index).fillna(0)
    cad["vendas_janela"] = soma
    cad["demanda_diaria"] = soma / janela
    variancia = (soma2 / janela - cad["demanda_diaria"] ** 2).clip(lower=0)
    cad["desvio_diario"] = np.sqrt(variancia)
    cad["cobertura_dias"] = cad["estoque_atual"] / cad["demanda_diaria"].replace(0, np.nan)
    cad["ultima_venda"] = todas_vendas.groupby("ean")["data"].max()

    cad["estoque_medio"] = _estoque_medio(m, rec.inicio, ref).reindex(cad.index).fillna(0)
    cad["giro"] = cad["vendas"] / cad["estoque_medio"].replace(0, np.nan)

    lotes = _lotes(m)
    vivos = lotes[lotes["saldo"] > 0].copy()
    vivos["valor"] = vivos["saldo"] * vivos["custo"]
    cad["valor_estoque"] = vivos.groupby("ean")["valor"].sum().reindex(cad.index).fillna(0)
    prox = vivos.sort_values("validade").drop_duplicates("ean").set_index("ean")
    cad["validade_proxima"] = prox["validade"]
    cad["qtd_lote_proximo"] = prox["saldo"]
    cad["dias_para_vencer"] = (cad["validade_proxima"] - ref).dt.days
    cad["lotes_em_estoque"] = vivos.groupby("ean").size().reindex(cad.index).fillna(0)

    entradas = m[m["tipo"] == "ENTRADA"].sort_values("id_movimento")
    cad["n_compras"] = entradas.groupby("ean")["Pedido"].nunique() \
        .reindex(cad.index).fillna(0).astype(int)
    cad["ultima_compra"] = entradas.groupby("ean")["data"].max()
    cad["custo_ultimo"] = entradas.groupby("ean")["custo_unitario"].last()
    cad["custo_ultimo"] = cad["custo_ultimo"].fillna(
        m.sort_values("id_movimento").groupby("ean")["custo_unitario"].last())
    forn = (entradas.groupby(["ean", "Nome do Fornecedor"])["quantidade"].sum()
                    .reset_index().sort_values("quantidade", ascending=False)
                    .drop_duplicates("ean").set_index("ean")["Nome do Fornecedor"])
    cad["fornecedor_principal"] = forn
    cad["dias_sem_compra"] = (ref - cad["ultima_compra"]).dt.days

    # item "em linha": reposto mais de uma vez, ou comprado há pouco tempo
    em_linha = (cad["n_compras"] >= 2) | (cad["dias_sem_compra"] <= p.mov_dias_descontinuado)
    cad["em_linha"] = em_linha
    zero = cad["estoque_atual"] <= 0
    cob = cad["cobertura_dias"]
    condicoes = [
        zero & em_linha,
        zero & ~em_linha,
        cob < p.mov_cobertura_critica,
        cad["dias_para_vencer"] < p.mov_validade_proxima,
        cob > p.mov_cobertura_excesso,
        ~zero & (cad["vendas_janela"] == 0),
    ]
    cad["situacao"] = np.select(condicoes, SITUACOES[:-1], SITUACOES[-1])

    # ---------------- reposição: demanda prevista, política e ponto de pedido
    lt = float(p.mov_lead_time)
    fator = fator_sazonal(rec, ref, janela, lt + p.mov_cobertura_alvo)
    cad["fator_sazonal"] = cad["classe_terapeutica"].map(fator).fillna(1.0)
    cad["demanda_prevista"] = cad["demanda_diaria"] * cad["fator_sazonal"]
    desvio = cad["desvio_diario"] * cad["fator_sazonal"]

    xyz = xyz_vendas(rec, p)
    if len(xyz):
        x = xyz.set_index("ean")
        cad["xyz"] = x["xyz"].reindex(cad.index).fillna("—")
        cad["venda_mensal_media"] = x["media_mensal"].reindex(cad.index)
    else:
        cad["xyz"], cad["venda_mensal_media"] = "—", np.nan
    # item irregular que vende menos de 1 unidade por mês não vale estoque parado:
    # compra-se quando o cliente pede (Pontes, 2013: política CZ / sob encomenda)
    encomenda = (cad["xyz"] == "Z") & (cad["venda_mensal_media"].fillna(0) < 1)
    cad["politica"] = np.select(
        [~em_linha, encomenda, cad["demanda_prevista"] <= 0],
        ["fora de linha", "sob encomenda", "sem venda recente"], "ponto de pedido")

    z = NormalDist().inv_cdf(min(0.999, max(0.5, p.mov_nivel_servico)))
    cad["estoque_seguranca"] = np.ceil(z * desvio * math.sqrt(lt))
    cad["ponto_pedido"] = np.ceil(cad["demanda_prevista"] * lt + cad["estoque_seguranca"])
    alvo = cad["demanda_prevista"] * (lt + p.mov_cobertura_alvo) + cad["estoque_seguranca"]
    # nenhuma compra deixa o estoque acima da cobertura de excesso (risco de vencer)
    teto = cad["demanda_prevista"] * p.mov_cobertura_excesso
    alvo = np.minimum(alvo, teto)
    pode = cad["politica"] == "ponto de pedido"
    cad["qtd_sugerida"] = np.where(pode, np.ceil((alvo - cad["estoque_atual"]).clip(lower=0)), 0)
    cad["valor_sugerido"] = cad["qtd_sugerida"] * cad["custo_ultimo"].fillna(0)
    cad["repor_agora"] = pode & (cad["estoque_atual"] <= cad["ponto_pedido"])
    return cad.reset_index()


def fator_sazonal(rec: "Recorte", ref: pd.Timestamp, janela: int,
                  horizonte: float) -> pd.Series:
    """Ajuste sazonal da demanda recente para o período que a compra vai cobrir.

    fator = índice da classe nos meses do horizonte ÷ índice nos meses da janela
    usada para medir a demanda. Só para classes com volume suficiente e com 12
    meses de histórico; nas demais o fator é 1. Limitado a 0,6–1,6 para que um
    mês atípico não dispare a compra.
    """
    if rec.dias < 365:
        return pd.Series(dtype=float)
    saz = sazonalidade(rec)
    if saz.empty:
        return pd.Series(dtype=float)
    saz = saz[saz["legivel"]].pivot(index="classe", columns="mes", values="indice")

    def media_meses(inicio: pd.Timestamp, dias: int) -> pd.Series:
        meses = pd.date_range(inicio, periods=max(1, int(dias)), freq="D").month
        pesos = pd.Series(meses).value_counts()
        cols = [m for m in pesos.index if m in saz.columns]
        return (saz[cols] * pesos[cols]).sum(axis=1) / pesos[cols].sum()

    janela_idx = media_meses(ref - pd.Timedelta(days=janela), janela)
    horiz_idx = media_meses(ref + pd.Timedelta(days=1), horizonte)
    return (horiz_idx / janela_idx.replace(0, np.nan)).clip(0.6, 1.6).dropna()


def para_decisao(rec: Recorte, mov_completo: pd.DataFrame, p: Parametros) -> dict:
    """O que o motor de decisão precisa da movimentação, num pacote só.

    As propostas por lote são calculadas pelo sistema para a data final do
    recorte (propostas_validade); o arquivo de propostas que veio com a base só
    é usado na conferência da tela Base de Dados.
    """
    pos = posicao(rec, p)
    return {"pos": pos, "resumo": resumo(rec, pos), "remarc": propostas_validade(rec, p),
            "ponte": ponte_estoque(rec)}


# ---------------------------------------------------------------------------
#                                  RESUMOS
# ---------------------------------------------------------------------------
def resumo(rec: Recorte, pos: pd.DataFrame) -> dict:
    """Números de síntese do período, para os cartões e o apoio à decisão."""
    per = rec.periodo
    v = per[per["tipo"] == "SAIDA_VENDA"]
    fat = float(v["valor_total"].sum())
    cmv = float(((-v["quantidade"]) * v["custo_unitario"]).sum())
    perdas = per[per["tipo"] == "PERDA_VALIDADE"]
    sit = pos["situacao"].value_counts() if len(pos) else pd.Series(dtype=int)
    giro_med = pos.loc[pos["vendas"] > 0, "giro"].median() if len(pos) else float("nan")
    cob_med = pos.loc[pos["estoque_atual"] > 0, "cobertura_dias"].median() if len(pos) else float("nan")
    return {
        "inicio": rec.inicio, "fim": rec.fim, "dias": rec.dias,
        "movimentos": len(per), "produtos": int(pos["ean"].nunique()) if len(pos) else 0,
        "reais": int((per["origem"] == "REAL").sum()),
        "simulados": int((per["origem"] != "REAL").sum()),
        "unidades_vendidas": int(-v["quantidade"].sum()),
        "faturamento": fat, "cmv": cmv, "margem": fat - cmv,
        "margem_pct": (fat - cmv) / fat if fat else float("nan"),
        "compras": float(per.loc[per["tipo"] == "ENTRADA", "valor_total"].sum()),
        "unidades_compradas": int(per.loc[per["tipo"] == "ENTRADA", "quantidade"].sum()),
        "perda_valor": float(-perdas["valor_total"].sum()),
        "perda_unidades": int(-perdas["quantidade"].sum()),
        "perda_pct": float(-perdas["valor_total"].sum()) / fat if fat else float("nan"),
        "estoque_unidades": int(pos["estoque_atual"].sum()) if len(pos) else 0,
        "estoque_valor": float(pos["valor_estoque"].sum()) if len(pos) else 0.0,
        "giro_mediano": giro_med, "cobertura_mediana": cob_med,
        "situacao": {s: int(sit.get(s, 0)) for s in SITUACOES},
        "ticket_medio": fat / max(1, int(-v["quantidade"].sum())),
    }


def serie_mensal(rec: Recorte) -> pd.DataFrame:
    """Entradas, vendas, perdas e estoque ao fim de cada mês do período."""
    per = rec.periodo
    if per.empty:
        return pd.DataFrame()
    q = per.pivot_table(index="ano_mes", columns="tipo", values="quantidade",
                        aggfunc="sum", fill_value=0)
    v = per.pivot_table(index="ano_mes", columns="tipo", values="valor_total",
                        aggfunc="sum", fill_value=0)
    for t in TIPOS:
        q[t] = q.get(t, 0)
        v[t] = v.get(t, 0)
    vend = per[per["tipo"] == "SAIDA_VENDA"]
    cmv = ((-vend["quantidade"]) * vend["custo_unitario"]).groupby(vend["ano_mes"]).sum()
    s = pd.DataFrame({
        "un_entradas": q["ENTRADA"] + q["ESTOQUE_INICIAL"],
        "un_vendas": -q["SAIDA_VENDA"], "un_perdas": -q["PERDA_VALIDADE"],
        "compras": v["ENTRADA"], "faturamento": v["SAIDA_VENDA"],
        "perdas": -v["PERDA_VALIDADE"], "cmv": cmv,
    }).fillna(0)
    s["margem"] = s["faturamento"] - s["cmv"]
    # estoque ao fim do mês: último saldo de cada produto até ali, somado
    m = rec.mov.sort_values("id_movimento")
    ult = m.groupby(["ean", "ano_mes"])["saldo_apos_movimento"].last().unstack()
    ult = ult.reindex(columns=sorted(ult.columns)).ffill(axis=1)
    s["estoque_fim"] = ult.sum().reindex(s.index).fillna(0)
    dias = per.groupby("ano_mes")["data"].agg(lambda d: d.dt.day.nunique())
    s["dias_com_movimento"] = dias
    s["itens_vendidos"] = vend.groupby("ano_mes")["ean"].nunique()
    s.index.name = "ano_mes"
    return s.fillna(0).reset_index()


def trajetoria(rec: Recorte, ean: str) -> pd.DataFrame:
    """Saldo dia a dia de um produto, com as entradas marcadas (dente de serra)."""
    m = rec.mov[rec.mov["ean"] == ean].sort_values("id_movimento")
    if m.empty:
        return m
    dia = m.groupby("data").agg(saldo=("saldo_apos_movimento", "last"))
    ent = m[m["tipo"].isin(["ENTRADA", "ESTOQUE_INICIAL"])].groupby("data")["quantidade"].sum()
    perda = -m[m["tipo"] == "PERDA_VALIDADE"].groupby("data")["quantidade"].sum()
    dia["entrada"], dia["perda"] = ent, perda
    return dia.reset_index()


# ---------------------------------------------------------------------------
#                       CURVA ABC PELAS VENDAS
# ---------------------------------------------------------------------------
def curva_abc_vendas(pos: pd.DataFrame, p: Parametros) -> M.ResultadoABC:
    """Mesma regra da Curva ABC de compras, sobre o faturamento das vendas.

    A classe sai do acumulado anterior ao item, como em metricas.curva_abc,
    para que as duas curvas sejam comparáveis item a item.
    """
    vendidos = pos[pos["faturamento"] > 0]
    itens = pd.DataFrame({
        "sku": vendidos["sku"], "ean": vendidos["ean"],
        "medicamento": vendidos["medicamento"], "valor": vendidos["faturamento"],
        "quantidade": vendidos["vendas"], "margem_pct": vendidos["margem_pct"],
        "giro": vendidos["giro"], "estoque_atual": vendidos["estoque_atual"],
        "cobertura_dias": vendidos["cobertura_dias"], "situacao": vendidos["situacao"],
        "compras": vendidos["n_compras"], "fornecedores": 1,
    })
    itens = (itens.sort_values(["valor", "medicamento"], ascending=[False, True])
                  .reset_index(drop=True))
    total = float(itens["valor"].sum()) or 1.0
    itens["participacao"] = itens["valor"] / total
    itens["acumulado"] = itens["valor"].cumsum()
    itens["acumulado_pct"] = itens["acumulado"] / total
    anterior = itens["acumulado_pct"].shift(1).fillna(0.0)
    itens["classe"] = np.where(anterior < p.corte_a, "A",
                               np.where(anterior < p.corte_b, "B", "C"))
    itens["posicao"] = range(1, len(itens) + 1)
    idx20 = max(0, round(len(itens) * 0.2) - 1)
    conc = float(itens.loc[idx20, "acumulado_pct"]) if len(itens) else 0.0
    return M.ResultadoABC(itens, M._resumo_classes(itens, total), total, p.corte,
                          "faturamento", conc)


def abc_cruzada(abc_compras: M.ResultadoABC, abc_vendas: M.ResultadoABC) -> pd.DataFrame:
    """Classe de cada medicamento na curva de compras e na de vendas.

    Item que é A nas compras e C nas vendas é dinheiro parado; o inverso é item
    barato que gira muito e não pode faltar.
    """
    comp = abc_compras.itens[["sku", "medicamento", "classe", "valor"]].rename(
        columns={"classe": "classe_compras", "valor": "valor_compras"})
    vend = abc_vendas.itens[["sku", "classe", "valor", "quantidade", "giro",
                             "situacao"]].rename(
        columns={"classe": "classe_vendas", "valor": "faturamento",
                 "quantidade": "unidades_vendidas"})
    cruz = comp.merge(vend, on="sku", how="outer")
    cruz["classe_compras"] = cruz["classe_compras"].fillna("—")
    cruz["classe_vendas"] = cruz["classe_vendas"].fillna("sem venda")
    return cruz


FAIXAS_COBERTURA = ["Sem estoque", "Até 15 dias", "15 a 30 dias", "30 a 60 dias",
                    "60 a 120 dias", "Mais de 120 dias", "Com estoque, sem venda recente"]


def faixas_cobertura(pos: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Produtos e valor em estoque por faixa de cobertura.

    A faixa de 30 a 60 dias é a recomendada na literatura (TCC, seção 2.6.2);
    as pontas mostram risco de faltar (à esquerda) e dinheiro parado (à direita).
    """
    if pos.empty:
        return pd.DataFrame(columns=["faixa", "produtos", "valor"])
    cob = pos["cobertura_dias"]
    zero = pos["estoque_atual"] <= 0
    faixa = np.select(
        [zero, cob.isna(), cob < 15, cob < 30, cob <= 60, cob <= 120],
        [FAIXAS_COBERTURA[0], FAIXAS_COBERTURA[6], FAIXAS_COBERTURA[1], FAIXAS_COBERTURA[2],
         FAIXAS_COBERTURA[3], FAIXAS_COBERTURA[4]], FAIXAS_COBERTURA[5])
    out = (pos.assign(faixa=faixa).groupby("faixa")
              .agg(produtos=("ean", "size"), valor=("valor_estoque", "sum"),
                   vendas=("faturamento", "sum"))
              .reindex(FAIXAS_COBERTURA).fillna(0).reset_index())
    return out


def lotes_a_vencer(rec: Recorte, dias: int) -> pd.DataFrame:
    """Lotes ainda em estoque que vencem dentro de `dias` a partir da data final."""
    lotes = _lotes(rec.mov)
    vivos = lotes[lotes["saldo"] > 0].copy()
    vivos["dias_para_vencer"] = (vivos["validade"] - rec.fim).dt.days
    vivos = vivos[vivos["dias_para_vencer"] < dias]
    nomes = rec.mov.groupby("ean")["medicamento"].last()
    demanda = (-rec.mov[(rec.mov["tipo"] == "SAIDA_VENDA") &
                        (rec.mov["data"] >= rec.fim - pd.Timedelta(days=90))]
               .groupby("ean")["quantidade"].sum()) / 90
    vivos["medicamento"] = vivos["ean"].map(nomes)
    vivos["valor"] = vivos["saldo"] * vivos["custo"]
    vivos["demanda_diaria"] = vivos["ean"].map(demanda).fillna(0)
    vivos["dias_para_escoar"] = vivos["saldo"] / vivos["demanda_diaria"].replace(0, np.nan)
    vivos["escoa_antes"] = vivos["dias_para_escoar"] <= vivos["dias_para_vencer"]
    return vivos.sort_values("dias_para_vencer").reset_index(drop=True)


# ---------------------------------------------------------------------------
#               PONTE DO ESTOQUE: DO PONTO DE PARTIDA AO DE CHEGADA
# ---------------------------------------------------------------------------
def _valor_em(m: pd.DataFrame, ate: pd.Timestamp) -> tuple[int, float]:
    """Unidades e valor a custo do estoque ao fim de um dia (lote a lote)."""
    antes = m[m["data"] <= ate]
    if antes.empty:
        return 0, 0.0
    lotes = _lotes(antes)
    vivos = lotes[lotes["saldo"] > 0]
    return int(vivos["saldo"].sum()), float((vivos["saldo"] * vivos["custo"]).sum())


def ponte_estoque(rec: Recorte) -> dict:
    """Do estoque de partida ao de chegada, com o que entrou e saiu no meio.

    estoque inicial + entradas − custo do que foi vendido − perdas = estoque final

    O estoque de partida é o saldo da véspera do início do período (no primeiro
    dia do livro, o estoque inicial registrado); o de chegada, o saldo na data
    final. Tudo a custo do lote, em unidades e em reais. Dos dois pontos saem os
    indicadores clássicos de gestão de estoque: giro pelo estoque médio
    (inicial + final) ÷ 2, dias de estoque, variação, escoamento e perda sobre o
    disponível.
    """
    m, per = rec.mov, rec.periodo
    vespera = rec.inicio - pd.Timedelta(days=1)
    # no primeiro dia do livro o "estoque inicial" é um movimento do próprio período
    primeiro = per[per["tipo"] == "ESTOQUE_INICIAL"]
    un_ini, val_ini = _valor_em(m, vespera)
    un_ini += int(primeiro["quantidade"].sum())
    val_ini += float(primeiro["valor_total"].sum())
    ent = per[per["tipo"] == "ENTRADA"]
    vend = per[per["tipo"] == "SAIDA_VENDA"]
    perd = per[per["tipo"] == "PERDA_VALIDADE"]
    un_fim, val_fim = _valor_em(m, rec.fim)
    cmv = float(((-vend["quantidade"]) * vend["custo_unitario"]).sum())
    perdas = float(-perd["valor_total"].sum())
    compras = float(ent["valor_total"].sum())
    medio = (val_ini + val_fim) / 2
    disponivel_un = un_ini + int(ent["quantidade"].sum())
    dias = rec.dias
    return {
        "inicio": rec.inicio, "fim": rec.fim, "dias": dias,
        "un_inicial": un_ini, "valor_inicial": val_ini,
        "un_entradas": int(ent["quantidade"].sum()), "valor_entradas": compras,
        "un_vendas": int(-vend["quantidade"].sum()), "cmv": cmv,
        "faturamento": float(vend["valor_total"].sum()),
        "un_perdas": int(-perd["quantidade"].sum()), "valor_perdas": perdas,
        "un_final": un_fim, "valor_final": val_fim,
        # conferência: a ponte fecha quando a diferença é zero (arredondamento)
        "diferenca": val_ini + compras - cmv - perdas - val_fim,
        "estoque_medio": medio,
        "giro": cmv / medio if medio else float("nan"),
        "dias_estoque": medio / (cmv / dias) if cmv else float("nan"),
        "cobertura_final": val_fim / (cmv / dias) if cmv else float("nan"),
        "variacao": val_fim - val_ini,
        "variacao_pct": (val_fim - val_ini) / val_ini if val_ini else float("nan"),
        "escoamento": int(-vend["quantidade"].sum()) / disponivel_un if disponivel_un else float("nan"),
        "perda_disponivel": int(-perd["quantidade"].sum()) / disponivel_un if disponivel_un else float("nan"),
        "compra_sobre_venda": compras / cmv if cmv else float("nan"),
    }


def ponte_por_grupo(rec: Recorte, coluna: str = "Classe Terapêutica") -> pd.DataFrame:
    """A mesma ponte, por grupo (classe terapêutica ou categoria), em reais."""
    linhas = []
    for grupo, eans in rec.mov.groupby(coluna)["ean"].unique().items():
        sub = Recorte(rec.mov[rec.mov["ean"].isin(set(eans))], rec.inicio, rec.fim)
        pt = ponte_estoque(sub)
        linhas.append({"grupo": grupo, "inicial": pt["valor_inicial"],
                       "entradas": pt["valor_entradas"], "cmv": pt["cmv"],
                       "perdas": pt["valor_perdas"], "final": pt["valor_final"],
                       "variacao": pt["variacao"], "giro": pt["giro"],
                       "dias_estoque": pt["dias_estoque"], "escoamento": pt["escoamento"]})
    return pd.DataFrame(linhas).sort_values("cmv", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
#             LOTES PERTO DE VENCER: DEVOLVER, REMARCAR OU SEGREGAR
# ---------------------------------------------------------------------------
# Prazo mínimo de validade para o paciente concluir o tratamento, por classe
# terapêutica (dias). Abaixo dele o lote não deve ser dispensado, com ou sem
# desconto. Valores das premissas da base de movimentação; ajustáveis aqui.
PRAZO_MINIMO_CLASSE = {
    "Analgésico / anti-inflamatório": 20, "Oftálmico": 20, "Respiratório / antigripal": 20,
    "Contraceptivo / hormonal": 60, "Crônico cardiometabólico": 60,
    "Neuro / psiquiátrico": 60, "Urológico / saúde sexual": 45,
}
PRAZO_MINIMO_PADRAO = 30
JANELA_DEVOLUCAO = 120          # dias de validade que o distribuidor aceita na troca
MARGEM_PISO = 0.08              # remarcação nunca abaixo do custo + 8%
DESCONTO_MAXIMO = 0.60
# desconto inicial por faixa de dias até o vencimento (a partir de, desconto)
FAIXAS_DESCONTO = [(91, 0.10), (61, 0.20), (31, 0.30), (0, 0.40)]
ACOES = ["Devolver ao fornecedor", "Remarcar", "Devolver ou baixa controlada",
         "Segregar — não dispensar", "Sem margem para remarcar"]


def _restricoes() -> dict:
    """Restrição comercial de cada EAN (livre, prescrição, controlado), do cadastro.

    O livro não traz essa informação; ela vem do cadastro que acompanha a base
    (coluna restricao_comercial). Sem o arquivo, todos os itens são tratados
    como de venda livre.
    """
    cad = _csv_auxiliar("proposta_remarcacao*.csv")
    if cad is None or "restricao_comercial" not in cad.columns:
        return {}
    cad["ean"] = D.texto_chave(cad["EAN"])
    return cad.drop_duplicates("ean").set_index("ean")["restricao_comercial"] \
              .astype(str).str.upper().to_dict()


def propostas_validade(rec: Recorte, p: Parametros) -> pd.DataFrame:
    """Uma proposta para cada lote em estoque que não será vendido antes de vencer.

    Cascata, da opção que mais recupera para a que menos recupera:
    1. controlado → devolver ou dar baixa com escrituração;
    2. 120 dias ou mais até vencer → devolver ao fornecedor (troca);
    3. menos dias que o prazo mínimo da classe → segregar, não dispensar;
    4. senão → remarcar: desconto pela faixa de prazo, com preço nunca abaixo do
       custo + 8% e desconto de no máximo 60%.
    Excedente = o que não sai no ritmo atual de venda até a validade. Perda
    evitada = custo do excedente que deixa de virar perda (devolução ou venda
    remarcada); contribuição = (preço proposto − custo) × excedente.
    """
    vencer = lotes_a_vencer(rec, p.mov_validade_proxima)
    if vencer.empty:
        return pd.DataFrame()
    m = rec.mov
    vendas = m[m["tipo"] == "SAIDA_VENDA"].sort_values("id_movimento")
    preco = vendas.groupby("ean")["preco_venda_unitario"].last()
    classe = m.groupby("ean")["Classe Terapêutica"].last()
    entradas = m[m["tipo"] == "ENTRADA"]
    forn = (entradas.groupby(["ean", "Nome do Fornecedor"])["quantidade"].sum().reset_index()
                    .sort_values("quantidade", ascending=False).drop_duplicates("ean")
                    .set_index("ean")["Nome do Fornecedor"])
    restr = _restricoes()

    v = vencer.copy()
    v["vende_ate_vencer"] = np.floor(v["demanda_diaria"] * v["dias_para_vencer"].clip(lower=0))
    v["excedente"] = (v["saldo"] - v["vende_ate_vencer"]).clip(lower=0).astype(int)
    v = v[v["excedente"] > 0].copy()
    if v.empty:
        return pd.DataFrame()
    v["classe_terapeutica"] = v["ean"].map(classe)
    v["prazo_minimo"] = v["classe_terapeutica"].map(PRAZO_MINIMO_CLASSE) \
        .fillna(PRAZO_MINIMO_PADRAO).astype(int)
    v["restricao"] = v["ean"].map(restr).fillna("LIVRE")
    v["preco_vigente"] = v["ean"].map(preco)
    v["fornecedor_principal"] = v["ean"].map(forn)
    dias = v["dias_para_vencer"]
    desconto = np.select([dias >= a for a, _ in FAIXAS_DESCONTO],
                         [d for _, d in FAIXAS_DESCONTO], FAIXAS_DESCONTO[-1][1])
    piso = v["custo"] * (1 + MARGEM_PISO)
    alvo = v["preco_vigente"] * (1 - desconto)
    proposto = np.maximum(alvo, piso)
    proposto = np.maximum(proposto, v["preco_vigente"] * (1 - DESCONTO_MAXIMO))
    sem_margem = v["preco_vigente"].isna() | (v["preco_vigente"] < piso)

    acao = np.select(
        [v["restricao"].str.contains("CONTROL"), dias >= JANELA_DEVOLUCAO,
         dias < v["prazo_minimo"], sem_margem],
        [ACOES[2], ACOES[0], ACOES[3], ACOES[4]], ACOES[1])
    v["acao"] = acao
    remarca = v["acao"] == ACOES[1]
    v["preco_proposto"] = np.where(remarca, np.round(proposto, 2), np.nan)
    v["desconto_pct"] = np.where(remarca, 1 - v["preco_proposto"] / v["preco_vigente"], np.nan)
    v["valor_excedente"] = v["excedente"] * v["custo"]
    recupera = v["acao"].isin([ACOES[0], ACOES[1], ACOES[2]])
    v["perda_evitada"] = np.where(recupera, v["valor_excedente"], 0.0)
    v["contribuicao"] = np.where(remarca, (v["preco_proposto"] - v["custo"]) * v["excedente"],
                                 0.0)
    motivo = {
        ACOES[0]: "ainda dentro da janela de troca do distribuidor (120 dias ou mais)",
        ACOES[1]: "fora da janela de troca e com prazo para o paciente concluir o tratamento",
        ACOES[2]: "medicamento controlado: devolução ou baixa com escrituração",
        ACOES[3]: "validade menor que o prazo mínimo de tratamento da classe",
        ACOES[4]: "o preço atual já está abaixo do custo + 8%",
    }
    v["justificativa"] = [f"{motivo[a]}; {e} de {s} un não saem até vencer no ritmo atual"
                          for a, e, s in zip(v["acao"], v["excedente"], v["saldo"])]
    v["status"] = "pendente de aprovação"
    ordem = {a: i for i, a in enumerate(ACOES)}
    return (v.assign(_o=v["acao"].map(ordem))
             .sort_values(["_o", "dias_para_vencer"]).drop(columns="_o")
             .reset_index(drop=True))


# ---------------------------------------------------------------------------
#                        POR QUE AS PERDAS ACONTECEM
# ---------------------------------------------------------------------------
# Cada lote perdido recebe UM fator, o primeiro da lista que os dados comprovam.
# São fatores associados, medidos nos movimentos, não uma prova de causa.
CAUSAS_PERDA = [
    "Estoque de abertura",
    "Chegou com validade curta",
    "Lote maior que a venda até a validade",
    "Comprado sem histórico de venda",
    "Venda caiu depois da compra",
    "Outros fatores",
]
CRITERIO_CAUSA = {
    "Estoque de abertura": "o lote já estava no estoque no início do livro; não há compra "
                           "registrada para medir validade na entrega ou ritmo de venda",
    "Chegou com validade curta": "a compra chegou com menos de 50% da validade (faixa curta ou "
                                 "crítica da cotação)",
    "Lote maior que a venda até a validade": "quantidade recebida maior que a venda diária dos 180 "
                                             "dias anteriores × dias de validade na chegada",
    "Comprado sem histórico de venda": "nenhuma venda do produto nos 180 dias antes da compra",
    "Venda caiu depois da compra": "venda diária entre a chegada e a validade menor que metade "
                                   "da venda diária dos 180 dias anteriores",
    "Outros fatores": "nenhum dos critérios acima: a venda média seria suficiente, mas lotes "
                      "simultâneos ou a variação da venda deixaram sobra",
}


def causas_perdas(rec: Recorte, base: pd.DataFrame | None = None) -> pd.DataFrame:
    """Um registro por perda do período, com o lote de origem e o fator associado.

    Para cada baixa por validade, localiza a entrada que trouxe o lote (compra
    ou estoque de abertura) e mede: validade restante na chegada (faixa da
    cotação, quando há `base`), tamanho do lote, venda diária do produto nos
    180 dias antes da compra e entre a chegada e o vencimento.
    """
    per = rec.periodo
    perdas = per[per["tipo"] == "PERDA_VALIDADE"]
    if perdas.empty:
        return pd.DataFrame()
    m = rec.mov
    entradas = (m[m["tipo"].isin(["ENTRADA", "ESTOQUE_INICIAL"])].sort_values("id_movimento")
                .groupby(["ean", "Lote"])
                .agg(chegada=("data", "first"), qtd_lote=("quantidade", "sum"),
                     origem_lote=("tipo", "first"), validade_lote=("validade", "max"),
                     arquivo=("arquivo_origem", "first"), linha=("linha_origem", "first"))
                .reset_index())
    d = perdas.merge(entradas, on=["ean", "Lote"], how="left")
    d["valor"] = -d["valor_total"]
    d["unidades"] = -d["quantidade"]
    vendas = m[m["tipo"] == "SAIDA_VENDA"][["ean", "data", "quantidade"]]
    antes, depois = [], []
    for ean, cheg, val in zip(d["ean"], d["chegada"], d["validade_lote"]):
        v = vendas[vendas["ean"] == ean]
        antes.append(-v[(v["data"] > cheg - pd.Timedelta(days=180)) &
                        (v["data"] <= cheg)]["quantidade"].sum() / 180)
        vida = max(1, (val - cheg).days)
        depois.append(-v[(v["data"] > cheg) & (v["data"] <= val)]["quantidade"].sum() / vida)
    d["venda_dia_antes"], d["venda_dia_depois"] = antes, depois
    d["vida_na_chegada"] = (d["validade_lote"] - d["chegada"]).dt.days
    d["venda_ate_validade"] = d["venda_dia_antes"] * d["vida_na_chegada"]
    d["faixa_recebimento"] = None
    if base is not None and {"arquivo_origem", "linha_origem", "Faixa de Recebimento"} <= set(base.columns):
        chave_b = base["arquivo_origem"].astype(str) + "|" + \
            pd.to_numeric(base["linha_origem"], errors="coerce").astype("Int64").astype(str)
        faixa = dict(zip(chave_b, base["Faixa de Recebimento"]))
        chave_d = d["arquivo"].astype(str) + "|" + \
            pd.to_numeric(d["linha"], errors="coerce").astype("Int64").astype(str)
        d["faixa_recebimento"] = chave_d.map(faixa)
    curta = d["faixa_recebimento"].isin(D.FAIXAS_CURTAS)
    sem_hist = d["venda_dia_antes"] <= 0
    d["causa"] = np.select(
        [d["origem_lote"] == "ESTOQUE_INICIAL", curta,
         ~sem_hist & (d["qtd_lote"] > d["venda_ate_validade"]),
         sem_hist, d["venda_dia_depois"] < 0.5 * d["venda_dia_antes"]],
        CAUSAS_PERDA[:5], CAUSAS_PERDA[5])
    return d[["ean", "medicamento", "Lote", "data", "unidades", "valor", "Classe Terapêutica",
              "Categoria Comercial", "origem_lote", "chegada", "qtd_lote", "vida_na_chegada",
              "faixa_recebimento", "venda_dia_antes", "venda_dia_depois", "venda_ate_validade",
              "causa"]].sort_values("valor", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
#                     PROJEÇÃO DO FECHAMENTO DO MÊS
# ---------------------------------------------------------------------------
def projecao_fechamento(rec: Recorte, compras_mes: float | None = None,
                        erro_vendas: float | None = None) -> dict:
    """Fechamento projetado do mês em curso e do mês seguinte.

    Realizado = movimentos até a data final. Mês em curso: realizado + ritmo
    diário dos últimos 30 dias × dias que faltam (estimativa pelo ritmo).
    Próximo mês: venda diária dos últimos 30 dias × dias do mês. Margem = a
    média dos 3 últimos meses fechados; perdas = média mensal dos 6 últimos
    meses fechados; compras = `compras_mes` (orçamento pelas compras) ou a
    média mensal das entradas. Estoque ao fim = estoque atual + compras −
    custo vendido − perdas do que falta.
    """
    fim = rec.fim
    mes = fim.to_period("M")
    fechado = fim.normalize() >= mes.end_time.normalize()
    m = rec.mov
    serie = serie_mensal(rec)
    if serie.empty:
        return {}
    s = serie.set_index("ano_mes")
    completos = [x for x in s.index if pd.Period(x, "M") < mes]
    ult3, ult6 = completos[-3:], completos[-6:]
    margem_pct = (s.loc[ult3, "margem"].sum() / s.loc[ult3, "faturamento"].sum()
                  if ult3 and s.loc[ult3, "faturamento"].sum() else float("nan"))
    perdas_mes = float(s.loc[ult6, "perdas"].mean()) if ult6 else 0.0
    compras_media = float(s.loc[completos, "compras"].mean()) if completos else 0.0
    compras_prev = float(compras_mes) if compras_mes is not None else compras_media

    no_mes = m[(m["data"] >= mes.start_time) & (m["data"] <= fim)]
    vend = no_mes[no_mes["tipo"] == "SAIDA_VENDA"]
    real = {"vendas": float(vend["valor_total"].sum()),
            "cmv": float(((-vend["quantidade"]) * vend["custo_unitario"]).sum()),
            "perdas": float(-no_mes.loc[no_mes["tipo"] == "PERDA_VALIDADE", "valor_total"].sum()),
            "compras": float(no_mes.loc[no_mes["tipo"] == "ENTRADA", "valor_total"].sum())}
    real["margem"] = real["vendas"] - real["cmv"]
    janela = m[(m["data"] > fim - pd.Timedelta(days=30)) & (m["tipo"] == "SAIDA_VENDA")]
    ritmo = float(janela["valor_total"].sum()) / 30
    dias_mes = mes.days_in_month
    dias_feitos = (fim - mes.start_time).days + 1
    faltam = 0 if fechado else dias_mes - dias_feitos
    estoque_atual = float(posicao_valor(rec))

    def fechamento(vendas, compras, perdas, estoque_inicio):
        cmv = vendas * (1 - margem_pct) if margem_pct == margem_pct else float("nan")
        return {"vendas": vendas, "margem": vendas - cmv, "margem_pct": margem_pct,
                "cmv": cmv, "compras": compras, "perdas": perdas,
                "estoque_fim": estoque_inicio + compras - cmv - perdas}

    resto = fechamento(ritmo * faltam, max(0.0, compras_prev - real["compras"]) if faltam else 0.0,
                       perdas_mes * faltam / dias_mes, estoque_atual)
    curso = {"vendas": real["vendas"] + resto["vendas"],
             "cmv": real["cmv"] + resto["cmv"],
             "compras": real["compras"] + resto["compras"],
             "perdas": real["perdas"] + resto["perdas"],
             "estoque_fim": resto["estoque_fim"]}
    curso["margem"] = curso["vendas"] - curso["cmv"]
    curso["margem_pct"] = curso["margem"] / curso["vendas"] if curso["vendas"] else float("nan")
    prox_mes = mes + 1
    proximo = fechamento(ritmo * prox_mes.days_in_month, compras_prev, perdas_mes,
                         curso["estoque_fim"])
    return {"mes": mes, "proximo_mes": prox_mes, "fechado": fechado, "fim": fim,
            "dias_feitos": dias_feitos, "dias_mes": dias_mes, "faltam": faltam,
            "realizado": real, "curso": curso, "proximo": proximo,
            "ritmo_diario": ritmo, "margem_pct": margem_pct, "perdas_mes": perdas_mes,
            "compras_prev": compras_prev, "estoque_atual": estoque_atual,
            "erro_vendas": erro_vendas, "meses_margem": ult3, "meses_perdas": ult6}


def posicao_valor(rec: Recorte) -> float:
    """Valor a custo do estoque na data final do recorte."""
    return _valor_em(rec.mov, rec.fim)[1]


# ---------------------------------------------------------------------------
#                    SAZONALIDADE, REGULARIDADE E LOTE DE COMPRA
# ---------------------------------------------------------------------------
INVERNO, VERAO = (6, 7, 8), (12, 1, 2)       # hemisfério sul
VOLUME_MINIMO_SAZONAL = 3000                  # unidades vendidas p/ a curva ser legível


def sazonalidade(rec: Recorte) -> pd.DataFrame:
    """Índice sazonal de venda por classe terapêutica e mês do ano (média = 100).

    Somar unidades por mês-calendário misturaria duas coisas que não são
    estação: meses que aparecem duas vezes no período e o catálogo que cresce
    (cada produto só existe a partir da primeira compra). Por isso a taxa de
    cada mês é dividida pelos dias do mês no período e pelos produtos ativos da
    classe naquele mês.
    """
    m = rec.mov
    v = rec.periodo[rec.periodo["tipo"] == "SAIDA_VENDA"]
    if v.empty:
        return pd.DataFrame()
    estreia = m.groupby("ean").agg(inicio=("data", "min"),
                                   classe=("Classe Terapêutica", "last"))
    meses = pd.period_range(rec.inicio.to_period("M"), rec.fim.to_period("M"), freq="M")
    linhas = []
    for per in meses:
        ini = max(per.start_time, rec.inicio)
        fim = min(per.end_time.normalize(), rec.fim)
        dias = (fim - ini).days + 1
        ativos = estreia[estreia["inicio"] <= fim].groupby("classe").size()
        for classe, n in ativos.items():
            linhas.append({"ano_mes": str(per), "mes": per.month, "classe": classe,
                           "dias": dias, "ativos": n})
    base = pd.DataFrame(linhas)
    vend = (-v.groupby(["ano_mes", "Classe Terapêutica"])["quantidade"].sum()) \
        .rename("unidades").reset_index().rename(columns={"Classe Terapêutica": "classe"})
    base = base.merge(vend, on=["ano_mes", "classe"], how="left").fillna({"unidades": 0})
    base["exposicao"] = base["dias"] * base["ativos"]
    por_mes = base.groupby(["classe", "mes"]).agg(unidades=("unidades", "sum"),
                                                   exposicao=("exposicao", "sum"))
    por_mes["taxa"] = por_mes["unidades"] / por_mes["exposicao"].replace(0, np.nan)
    media = por_mes.groupby(level=0)["taxa"].transform("mean")
    por_mes["indice"] = por_mes["taxa"] / media * 100
    out = por_mes.reset_index()
    total = out.groupby("classe")["unidades"].transform("sum")
    out["volume_classe"] = total
    out["legivel"] = total >= VOLUME_MINIMO_SAZONAL
    return out


def resumo_sazonal(saz: pd.DataFrame) -> pd.DataFrame:
    """Por classe: pico, vale e razão inverno ÷ verão do índice."""
    if saz.empty:
        return saz
    linhas = []
    for classe, g in saz.groupby("classe"):
        g = g.dropna(subset=["indice"])
        if len(g) < 12:
            continue
        inv = g[g["mes"].isin(INVERNO)]["indice"].mean()
        ver = g[g["mes"].isin(VERAO)]["indice"].mean()
        pico = g.loc[g["indice"].idxmax()]
        vale = g.loc[g["indice"].idxmin()]
        linhas.append({"classe": classe, "unidades": int(g["unidades"].sum()),
                       "legivel": bool(g["legivel"].iloc[0]),
                       "mes_pico": int(pico["mes"]), "indice_pico": pico["indice"],
                       "mes_vale": int(vale["mes"]), "indice_vale": vale["indice"],
                       "inverno_verao": inv / ver if ver else np.nan,
                       "amplitude": (g["indice"].max() - g["indice"].min())})
    if not linhas:          # nenhuma classe com os 12 meses (ex.: um só produto filtrado)
        return pd.DataFrame(columns=["classe", "unidades", "legivel", "mes_pico", "indice_pico",
                                     "mes_vale", "indice_vale", "inverno_verao", "amplitude"])
    return pd.DataFrame(linhas).sort_values("unidades", ascending=False).reset_index(drop=True)


def xyz_vendas(rec: Recorte, p: Parametros) -> pd.DataFrame:
    """Regularidade da DEMANDA: coeficiente de variação das vendas mensais.

    É a XYZ como a literatura a define (variabilidade do consumo). A versão da
    base de compras mede a regularidade da compra, o único sinal que havia.
    Conta só meses completos a partir da estreia do produto, com os meses sem
    venda valendo zero.
    """
    s = rec.periodo[rec.periodo["tipo"] == "SAIDA_VENDA"]
    if s.empty:
        return pd.DataFrame()
    completos = set(_meses_completos(pd.DataFrame({"ano_mes": sorted(rec.periodo["ano_mes"]
                                                                     .unique())}), rec)["ano_mes"])
    s = s[s["ano_mes"].isin(completos)]
    mensal = (-s.pivot_table(index="ean", columns="ano_mes", values="quantidade",
                             aggfunc="sum", fill_value=0))
    mensal = mensal.reindex(columns=sorted(completos), fill_value=0)
    estreia = rec.mov.groupby("ean")["data"].min().dt.to_period("M").astype(str)
    cols = np.array(mensal.columns)
    ativo = cols[None, :] >= estreia.reindex(mensal.index).to_numpy()[:, None]
    valores = mensal.to_numpy(dtype=float)
    valores = np.where(ativo, valores, np.nan)
    n = ativo.sum(axis=1)
    with np.errstate(all="ignore"):
        media = np.where(n > 0, np.nansum(valores, axis=1) / np.maximum(n, 1), np.nan)
        quad = np.nansum((valores - media[:, None]) ** 2, axis=1)
        desvio = np.where(n > 1, np.sqrt(quad / np.maximum(n - 1, 1)), np.nan)
    out = pd.DataFrame({"ean": mensal.index, "meses": n, "media_mensal": media,
                        "desvio_mensal": desvio})
    out["cv"] = out["desvio_mensal"] / out["media_mensal"].replace(0, np.nan)
    out["xyz"] = np.select([out["cv"] <= p.cv_x, out["cv"] <= p.cv_y], ["X", "Y"], "Z")
    out.loc[out["meses"] < 6, "xyz"] = "—"          # pouco histórico para medir
    return out


def lote_economico(pos: pd.DataFrame, rec: Recorte, p: Parametros) -> pd.DataFrame:
    """Lote econômico de compra (LEC/EOQ) e níveis mínimo e máximo de estoque.

    LEC = √(2·D·S ÷ H), com D = demanda anual (venda do período anualizada),
    S = custo de emitir um pedido do item e H = custo de manter uma unidade por
    um ano (custo × taxa de manutenção). Compara com o lote praticado: a
    mediana das quantidades realmente compradas (dado real).

    O modelo de Harris supõe produto que não se deteriora. Para itens de giro
    lento ele sugere lotes que durariam mais de um ano, às vezes mais que a
    validade. Por isso o lote recomendado é o LEC limitado à cobertura de
    excesso das Preferências (o mesmo limite que marca o item como excesso).
    """
    ent = rec.mov[rec.mov["tipo"] == "ENTRADA"]
    praticado = ent.groupby("ean")["quantidade"].median()
    d = pos.set_index("ean")
    anual = d["vendas"] / max(1, rec.dias) * 365
    custo = d["custo_ultimo"].fillna(0)
    h = (custo * p.mov_taxa_manutencao).replace(0, np.nan)
    lec_teorico = np.ceil(np.sqrt(2 * anual * p.mov_custo_pedido / h))
    teto = np.ceil(anual / 365 * p.mov_cobertura_excesso).clip(lower=1)
    lec = np.minimum(lec_teorico, teto)
    out = pd.DataFrame({
        "medicamento": d["medicamento"], "situacao": d["situacao"],
        "demanda_anual": anual, "custo": custo, "lec_teorico": lec_teorico,
        "limitado_validade": lec_teorico > teto, "lec": lec,
        "lote_praticado": praticado.reindex(d.index),
        "pedidos_ano_lec": anual / lec.replace(0, np.nan),
        "estoque_minimo": d["estoque_seguranca"],
        "ponto_pedido": d["ponto_pedido"],
        "estoque_maximo": d["estoque_seguranca"] + np.ceil(lec),
        "politica": d["politica"], "demanda_prevista": d["demanda_prevista"],
        "estoque_atual": d["estoque_atual"],
    })
    out["razao_lote"] = out["lote_praticado"] / out["lec"].replace(0, np.nan)
    out["leitura"] = np.select(
        [out["lec"].isna() | (out["demanda_anual"] <= 0), out["razao_lote"].isna(),
         out["razao_lote"] > 1.5, out["razao_lote"] < 0.67],
        ["sem venda", "sem compra no período", "compra acima do lote econômico",
         "compra abaixo do lote econômico"], "compra próxima do lote econômico")
    out["acima_maximo"] = out["estoque_atual"] > out["estoque_maximo"]
    return out.reset_index()


def dente_serra_modelo(demanda: float, lote: float, seguranca: float, ponto: float,
                       prazo: int, inicio: pd.Timestamp, dias: int = 180) -> pd.DataFrame:
    """Trajetória do estoque sob a política recomendada (modelo de lote econômico).

    O estoque começa no máximo (segurança + lote), cai com a demanda prevista; ao
    tocar o ponto de pedido, um pedido do tamanho do lote é feito e chega após o
    prazo de reposição. É o "dente de serra" teórico dos livros de gestão de
    estoque, para comparar com o saldo que de fato aconteceu.
    """
    if demanda <= 0 or lote <= 0:
        return pd.DataFrame(columns=["data", "saldo", "pedido", "chegada"])
    saldo = seguranca + lote
    chegada_em = None
    linhas = []
    for i in range(dias):
        dia = inicio + pd.Timedelta(days=i)
        chegou = False
        if chegada_em is not None and i >= chegada_em:
            saldo += lote
            chegada_em, chegou = None, True
        pedido = False
        if chegada_em is None and saldo <= ponto:
            chegada_em, pedido = i + prazo, True
        linhas.append({"data": dia, "saldo": saldo, "pedido": pedido, "chegada": chegou})
        saldo = max(0.0, saldo - demanda)
    return pd.DataFrame(linhas)


def referencias(rec: Recorte, pos: pd.DataFrame, res: dict, abc_v: M.ResultadoABC,
                p: Parametros) -> pd.DataFrame:
    """Cada indicador da movimentação ao lado da referência da literatura.

    A coluna `natureza` diz de onde vem o número (real, simulado ou cálculo
    sobre os dois); `leitura` diz se ele está dentro, acima ou abaixo da faixa
    citada no próprio TCC (seção 2.6) ou na documentação do gerador.
    """
    em_linha = pos[pos["em_linha"]]
    ruptura_pct = (em_linha["estoque_atual"] <= 0).mean() if len(em_linha) else np.nan
    com_estoque = pos[pos["estoque_atual"] > 0]
    cob = com_estoque["cobertura_dias"]
    dentro_cob = cob.between(30, 60).mean() if len(cob) else np.nan
    repos = _reposicoes(rec.mov)
    vazio = (repos["saldo_antes"] == 0).mean() if len(repos) else np.nan
    saz = resumo_sazonal(sazonalidade(rec))
    resp = saz[saz["classe"].str.startswith("Respirat")] if len(saz) else saz

    def faixa(valor, lo, hi):
        if valor is None or pd.isna(valor):
            return "sem dado"
        return "dentro" if lo <= valor <= hi else ("abaixo" if valor < lo else "acima")

    linhas = [
        ("Concentração de Pareto (vendas)", abc_v.concentracao_20, "pct",
         "20% dos itens com cerca de 80% do valor", 0.70, 0.90,
         "Princípio de Pareto; Nguyen et al. (2022) — seção 2.4", "simulado"),
        ("Perda por validade ÷ faturamento", res["perda_pct"], "pct",
         "1% a 3% no varejo farmacêutico pequeno", 0.01, 0.03,
         "Documentação técnica do gerador; Diriba et al. (2023) para o risco", "simulado"),
        ("Margem bruta", res["margem_pct"], "pct", "25% a 50%", 0.25, 0.50,
         "Faixa usada na validação do gerador (bloco H)", "simulado"),
        ("Itens em linha zerados (ruptura)", ruptura_pct, "pct",
         "abaixo de 2% dos itens", 0.0, 0.02, "TCC seção 2.6.3 (meta varejista)", "calculado"),
        ("Itens com cobertura entre 30 e 60 dias", dentro_cob, "pct",
         "cobertura recomendada de 30 a 60 dias", 0.5, 1.0,
         "Slack, Brandon-Jones e Johnston (2022) — TCC seção 2.6.2", "calculado"),
        ("Cobertura mediana", res["cobertura_mediana"], "dias", "30 a 60 dias", 30, 60,
         "Slack, Brandon-Jones e Johnston (2022) — TCC seção 2.6.2", "calculado"),
        ("Reposições com prateleira vazia", vazio, "pct",
         "minoria das reposições (5% a 30%)", 0.05, 0.30,
         "Critério de plausibilidade do gerador (bloco H)", "calculado"),
        ("Respiratórios: inverno ÷ verão",
         resp["inverno_verao"].iloc[0] if len(resp) else np.nan, "vezes",
         "venda maior no inverno (razão acima de 1)", 1.1, 3.0,
         "Oblizajek et al. (2024); Vadaga et al. (2025) — TCC seção 2.5.3", "simulado"),
    ]
    out = pd.DataFrame(linhas, columns=["indicador", "valor", "unidade", "referencia",
                                        "minimo", "maximo", "fonte", "natureza"])
    out["leitura"] = [faixa(v, lo, hi) for v, lo, hi in
                      zip(out["valor"], out["minimo"], out["maximo"])]
    return out


# ---------------------------------------------------------------------------
#                       PREVISÃO E TESTE NO HISTÓRICO
# ---------------------------------------------------------------------------
def _meses_completos(serie: pd.DataFrame, rec: Recorte) -> pd.DataFrame:
    """Tira o mês de abertura e o mês em curso, que só têm alguns dias."""
    s = serie.copy()
    ini = rec.mov["data"].min()
    primeiro = ini.to_period("M")
    ultimo = rec.fim.to_period("M")
    fim_completo = rec.fim == (rec.fim + pd.offsets.MonthEnd(0))
    excluir = set()
    if ini.day > 1:
        excluir.add(str(primeiro))
    if not fim_completo:
        excluir.add(str(ultimo))
    return s[~s["ano_mes"].isin(excluir)].reset_index(drop=True)


METODOS_VENDAS = {
    "Último mês": lambda h, i: h[i - 1],
    "Média dos últimos 3 meses": lambda h, i: np.mean(h[i - 3:i]),
    "Média dos últimos 6 meses": lambda h, i: np.mean(h[i - 6:i]),
    "Mesmo mês do ano anterior": lambda h, i: h[i - 12] if i >= 12 else np.nan,
}


def previsao_vendas(rec: Recorte, coluna: str = "faturamento") -> dict:
    """Escolhe, pelo teste no histórico, o método que menos erra o mês seguinte."""
    serie = serie_mensal(rec)
    if serie.empty:
        return {"serie": serie, "teste": pd.DataFrame(), "metodos": pd.DataFrame(),
                "melhor": None, "previsao": float("nan"), "alvo": None}
    s = _meses_completos(serie, rec)
    h = s[coluna].to_numpy(dtype=float)
    linhas = []
    for nome, f in METODOS_VENDAS.items():
        for i in range(6, len(h)):
            prev = f(h, i)
            if np.isnan(prev) or h[i] == 0:
                continue
            linhas.append({"metodo": nome, "mes": s.loc[i, "ano_mes"], "previsto": prev,
                           "real": h[i], "erro": abs(prev - h[i]) / h[i]})
    teste = pd.DataFrame(linhas)
    if teste.empty:
        return {"serie": s, "teste": teste, "metodos": pd.DataFrame(), "melhor": None,
                "previsao": float("nan"), "alvo": None}
    met = (teste.groupby("metodo")
                .agg(meses=("erro", "size"), erro_mediano=("erro", "median"),
                     erro_medio=("erro", "mean"))
                .sort_values("erro_mediano").reset_index())
    # só concorre quem foi testado em pelo menos 4 meses
    validos = met[met["meses"] >= 4]
    melhor = (validos if len(validos) else met).iloc[0]["metodo"]
    alvo = (pd.Period(s["ano_mes"].iloc[-1]) + 1) if len(s) else None
    previsto = METODOS_VENDAS[melhor](np.append(h, np.nan), len(h))
    return {"serie": s, "teste": teste, "metodos": met, "melhor": melhor,
            "previsao": float(previsto), "alvo": alvo,
            "erro_mediano": float(met.set_index("metodo").loc[melhor, "erro_mediano"])}


def teste_demanda(rec: Recorte, p: Parametros, cortes: int = 6, horizonte: int = 30) -> pd.DataFrame:
    """Testa a demanda diária usada na reposição contra o que foi vendido depois.

    Em cada data de corte, a previsão de 30 dias de cada produto é a média da
    janela anterior × 30; o real é o que vendeu nos 30 dias seguintes. O erro
    WAPE (soma dos erros ÷ soma do real) evita que itens pequenos dominem.
    """
    v = rec.mov[rec.mov["tipo"] == "SAIDA_VENDA"]
    if v.empty:
        return pd.DataFrame()
    janela = int(p.mov_janela_demanda)
    classe = rec.mov.groupby("ean")["Classe Terapêutica"].last()
    inicio_livro = rec.mov["data"].min()
    linhas = []
    for k in range(cortes, 0, -1):
        corte = rec.fim - pd.Timedelta(days=horizonte * k)
        if corte - pd.Timedelta(days=janela) < inicio_livro:
            continue
        antes = v[(v["data"] >= corte - pd.Timedelta(days=janela)) & (v["data"] <= corte)]
        depois = v[(v["data"] > corte) & (v["data"] <= corte + pd.Timedelta(days=horizonte))]
        media = (-antes.groupby("ean")["quantidade"].sum()) / janela * horizonte
        # o fator usa só o histórico até a data de corte: nada do futuro entra no teste
        hist = Recorte(rec.mov[rec.mov["data"] <= corte], inicio_livro, corte)
        fat = fator_sazonal(hist, corte, janela, horizonte)
        sazonal = media * classe.reindex(media.index).map(fat).fillna(1.0)
        ingenuo = -v[(v["data"] > corte - pd.Timedelta(days=horizonte)) &
                     (v["data"] <= corte)].groupby("ean")["quantidade"].sum()
        real = -depois.groupby("ean")["quantidade"].sum()
        idx = media.index.union(real.index)
        media, sazonal, real, ingenuo = (x.reindex(idx).fillna(0)
                                         for x in (media, sazonal, real, ingenuo))
        soma_real = max(1.0, real.sum())
        linhas.append({"corte": corte, "itens": len(idx), "real": real.sum(),
                       "previsto": sazonal.sum(), "previsto_media": media.sum(),
                       "wape": float((sazonal - real).abs().sum() / soma_real),
                       "wape_media": float((media - real).abs().sum() / soma_real),
                       "wape_ingenuo": float((ingenuo - real).abs().sum() / soma_real),
                       "ajuste_sazonal": bool(len(fat))})
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
#                                 VALIDAÇÃO
# ---------------------------------------------------------------------------
def _brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _linha(bloco, verificacao, ok, detalhe, atencao=False):
    resultado = "PASSOU" if ok else ("ATENÇÃO" if atencao else "FALHOU")
    return {"bloco": bloco, "verificacao": verificacao, "resultado": resultado,
            "detalhe": detalhe}


def _fefo(m: pd.DataFrame) -> tuple[int, int, int, int]:
    """Reconstrói os lotes movimento a movimento.

    Devolve (vendas fora de FEFO, lotes que ficaram negativos, vendas de lote
    vencido, vendas antes da primeira entrada do produto).
    """
    fora = negativos = vencidos = antecipadas = 0
    cols = ["ean", "tipo", "Lote", "validade", "quantidade", "data"]
    for _, g in m.sort_values("id_movimento")[cols].groupby("ean", sort=False):
        saldo_lote: dict = {}
        validade_lote: dict = {}
        teve_entrada = False
        for ean, tipo, lote, val, qtd, dia in g.itertuples(index=False):
            if qtd > 0:
                teve_entrada = True
                saldo_lote[lote] = saldo_lote.get(lote, 0) + qtd
                validade_lote[lote] = val
                continue
            if tipo == "SAIDA_VENDA":
                if not teve_entrada:
                    antecipadas += 1
                if pd.notna(val) and dia > val:
                    vencidos += 1
                disponiveis = [validade_lote[l] for l, s in saldo_lote.items()
                               if s > 0 and l != lote and pd.notna(validade_lote.get(l))]
                if disponiveis and pd.notna(val) and min(disponiveis) < val:
                    fora += 1
            saldo_lote[lote] = saldo_lote.get(lote, 0) + qtd
            if saldo_lote[lote] < 0:
                negativos += 1
    return fora, negativos, vencidos, antecipadas


def validar(mov: pd.DataFrame, base: pd.DataFrame | None = None,
            p: Parametros | None = None) -> pd.DataFrame:
    """Verificações do livro, da integração com a base de compras e dos arquivos.

    FALHOU = o livro não pode ser usado (conta que não fecha, saldo negativo).
    ATENÇÃO = diferença que o sistema aponta mas não corrige sozinho.
    """
    p = p or Parametros()
    r = []
    m = mov.sort_values("id_movimento")

    # ---------------------------------------------------------- estrutura
    r.append(_linha("Estrutura", "Identificador único de movimento",
                    m["id_movimento"].is_unique,
                    f"{m['id_movimento'].duplicated().sum()} repetidos em {len(m):,}"
                    .replace(",", ".")))
    fora_dom = ~m["tipo"].isin(TIPOS)
    r.append(_linha("Estrutura", "Tipos de movimento conhecidos", not fora_dom.any(),
                    f"{int(fora_dom.sum())} fora de {', '.join(TIPOS)}"))
    sinal = m["tipo"].map(SINAL)
    errado = (np.sign(m["quantidade"]) != sinal) & sinal.notna()
    r.append(_linha("Estrutura", "Sinal da quantidade coerente com o tipo",
                    not errado.any(), f"{int(errado.sum())} movimentos com sinal trocado"))
    reais_fora = (m["origem"] == "REAL") & (m["tipo"] != "ENTRADA")
    r.append(_linha("Estrutura", "Só as entradas são dado real", not reais_fora.any(),
                    f"{int((m['origem'] == 'REAL').sum())} reais · "
                    f"{int((m['origem'] != 'REAL').sum())} simulados"))
    nulos = m[["data", "ean", "Lote", "custo_unitario"]].isna().sum().sum()
    r.append(_linha("Estrutura", "Campos obrigatórios preenchidos", nulos == 0,
                    f"{int(nulos)} valores vazios em data, EAN, lote e custo"))
    ean_desc = m.groupby("ean")["medicamento"].nunique()
    r.append(_linha("Estrutura", "Cada EAN com uma única descrição",
                    (ean_desc <= 1).all(), f"{int((ean_desc > 1).sum())} EAN com mais de uma",
                    atencao=True))

    # ------------------------------------------------------------- saldos
    recalculado = m.groupby("ean")["quantidade"].cumsum()
    difere = recalculado != m["saldo_apos_movimento"]
    r.append(_linha("Saldo", "Saldo registrado = soma cronológica dos movimentos",
                    not difere.any(), f"{int(difere.sum())} divergências em "
                    f"{len(m):,} movimentos".replace(",", ".")))
    r.append(_linha("Saldo", "Nenhum saldo negativo", (m["saldo_apos_movimento"] >= 0).all(),
                    f"mínimo observado: {int(m['saldo_apos_movimento'].min())}"))
    fora, negativos, vencidos, antecipadas = _fefo(m)
    n_vendas = int((m["tipo"] == "SAIDA_VENDA").sum())
    r.append(_linha("Lotes", "Nenhum lote com saldo negativo", negativos == 0,
                    f"{negativos} ocorrências"))
    r.append(_linha("Lotes", "Vendas seguem FEFO (vence primeiro, sai primeiro)", fora == 0,
                    f"{fora} de {n_vendas:,} vendas usaram lote de validade mais longa"
                    .replace(",", ".")))
    r.append(_linha("Lotes", "Nenhuma venda de lote vencido", vencidos == 0,
                    f"{vencidos} vendas após a validade"))
    r.append(_linha("Lotes", "Nenhuma venda antes da primeira entrada do produto",
                    antecipadas == 0, f"{antecipadas} ocorrências"))

    # --------------------------------------------------------- financeiro
    entra = m[m["quantidade"] > 0]
    dif_e = (entra["valor_total"] - entra["quantidade"] * entra["custo_unitario"]).abs() > 0.02
    vend = m[m["tipo"] == "SAIDA_VENDA"]
    dif_v = (vend["valor_total"] - (-vend["quantidade"]) * vend["preco_venda_unitario"]).abs() > 0.02
    r.append(_linha("Financeiro", "Valor = quantidade × custo nas entradas",
                    not dif_e.any(), f"{int(dif_e.sum())} divergências acima de R$ 0,02"))
    r.append(_linha("Financeiro", "Valor = quantidade × preço nas vendas",
                    not dif_v.any(), f"{int(dif_v.sum())} divergências acima de R$ 0,02"))
    margem_neg = vend["preco_venda_unitario"] <= vend["custo_unitario"]
    r.append(_linha("Financeiro", "Nenhuma venda com margem nula ou negativa",
                    not margem_neg.any(), f"{int(margem_neg.sum())} vendas"))

    # ---------------------------------------------- integração com compras
    if base is not None and not base.empty:
        ent = m[m["tipo"] == "ENTRADA"]
        # linhas incluídas depois do livro (importação ou cadastro manual) não são erro
        # do livro: ele só está desatualizado. Mais entradas que linhas, sim, é erro
        fora = len(base) - len(ent)
        r.append(_linha("Integração", "Uma entrada para cada linha da base de cotação",
                        fora == 0,
                        f"{len(ent):,} entradas · {len(base):,} linhas na base".replace(",", ".")
                        + (f" · {fora} linha(s) incluída(s) depois do livro: atualize o livro "
                           "de movimentação para que entrem no estoque" if fora > 0 else ""),
                        atencao=fora > 0))
        chave_b = base["arquivo_origem"].astype(str) + "|" + \
            pd.to_numeric(base["linha_origem"], errors="coerce").astype("Int64").astype(str)
        chave_m = ent["arquivo_origem"].astype(str) + "|" + \
            ent["linha_origem"].astype("Int64").astype(str)
        sem_par = ~chave_m.isin(set(chave_b))
        r.append(_linha("Integração", "Toda entrada aponta para uma linha da cotação",
                        not sem_par.any(), f"{int(sem_par.sum())} entradas sem linha de origem"))
        b = base.assign(_k=chave_b.values).set_index("_k")
        e = ent.assign(_k=chave_m.values).set_index("_k")
        comum = e.index.intersection(b.index)
        dq = (e.loc[comum, "quantidade"] != b.loc[comum, "Qtde. Fat."]).sum()
        dc = ((e.loc[comum, "custo_unitario"] - b.loc[comum, "Vl. Custo (R$)"]).abs() > 0.005).sum()
        r.append(_linha("Integração", "Quantidade da entrada = quantidade faturada na cotação",
                        dq == 0, f"{int(dq)} divergências"))
        r.append(_linha("Integração", "Custo da entrada = custo da cotação", dc == 0,
                        f"{int(dc)} divergências"))
        eans_base = set(D.texto_chave(base["EAN"]))
        so_livro = set(m["ean"]) - eans_base
        r.append(_linha("Integração", "Todo produto do livro existe na base de compras",
                        not so_livro, f"{len(so_livro)} EAN só no livro"))
        skus_por_ean = base.assign(_e=D.texto_chave(base["EAN"])).groupby("_e")["sku"].nunique()
        r.append(_linha("Integração", "Cada EAN corresponde a um único código de produto",
                        (skus_por_ean <= 1).all(),
                        f"{int((skus_por_ean > 1).sum())} EAN com mais de um código na base "
                        f"({base['sku'].nunique()} códigos para {len(skus_por_ean)} EAN)",
                        atencao=True))

    # ------------------------------------- conferência com os arquivos gerados
    planilha = _mais_recente(PADRAO_LIVRO)
    if planilha is not None and _mais_recente(PADRAO_CSV) is not None:
        chave = ("planilha", str(planilha), planilha.stat().st_mtime)
        if chave not in _MEMO:
            try:
                _MEMO[chave] = ler_livro(planilha)
            except Exception:                            # noqa: BLE001
                _MEMO[chave] = None
        outra = _MEMO[chave]
        if outra is not None:
            cols = ["id_movimento", "tipo", "ean", "Lote", "quantidade",
                    "saldo_apos_movimento"]
            iguais = (len(outra) == len(m) and
                      (outra[cols].reset_index(drop=True).astype(str)
                       == m[cols].reset_index(drop=True).astype(str)).all().all() and
                      abs(outra["valor_total"].sum() - m["valor_total"].sum()) < 0.01)
            r.append(_linha("Arquivos", "CSV e planilha do livro idênticos", iguais,
                            f"{len(m):,} movimentos no CSV · {len(outra):,} na planilha"
                            .replace(",", ".") + (" — o sistema usa o CSV" if iguais else
                                                  " — DIVERGEM; o sistema usa o CSV")))
    rec = recortar(mov)
    pos = posicao(rec, p)
    pos_arq = _csv_auxiliar("posicao_estoque*.csv")
    if pos_arq is not None and len(pos):
        pa = pos_arq.assign(ean=D.texto_chave(pos_arq["EAN"])).set_index("ean")
        mine = pos.set_index("ean")
        comum = mine.index.intersection(pa.index)
        dif = (mine.loc[comum, "estoque_atual"] != pa.loc[comum, "estoque_atual"]).sum()
        r.append(_linha("Arquivos", "Estoque atual igual ao de posicao_estoque.csv",
                        dif == 0 and len(comum) == len(mine),
                        f"{len(comum)} produtos comparados · {int(dif)} divergências"))
        dfat = ((mine.loc[comum, "faturamento"] - pa.loc[comum, "faturamento"]).abs() > 0.05).sum()
        r.append(_linha("Arquivos", "Faturamento por produto igual ao do arquivo",
                        dfat == 0, f"{int(dfat)} divergências acima de R$ 0,05"))
        # o arquivo escreve as situações em maiúsculas ("VALIDADE PRÓXIMA")
        sit_arq = pa.loc[comum, "situacao_estoque"].map(D._sem_acento)
        sit_sis = mine.loc[comum, "situacao"].map(D._sem_acento)
        iguais = int((sit_arq == sit_sis).sum())
        r.append(_linha("Arquivos", "Situação do estoque igual à do arquivo",
                        iguais >= 0.99 * len(comum),
                        f"{iguais} de {len(comum)} produtos com a mesma situação; as "
                        "diferenças vêm da demanda arredondada a 3 casas no arquivo",
                        atencao=True))
        v90 = int((mine.loc[comum, "vendas_janela"] == pa.loc[comum, "vendas_90d"]).sum())
        r.append(_linha("Arquivos", "Vendas dos últimos 90 dias iguais às do arquivo",
                        v90 == len(comum) or p.mov_janela_demanda != 90,
                        f"{v90} de {len(comum)} produtos (janela de "
                        f"{p.mov_janela_demanda} dias em Preferências)", atencao=True))
        val_arq = float(pa["valor_estoque_custo"].sum())
        val_sis = float(mine["valor_estoque"].sum())
        r.append(_linha("Arquivos", "Valor do estoque igual ao do arquivo",
                        abs(val_arq - val_sis) < 1,
                        f"sistema {_brl(val_sis)} (cada lote pelo seu custo) · arquivo "
                        f"{_brl(val_arq)} (saldo × último custo)", atencao=True))
        giro_simples = mine.loc[comum, "vendas"] / ((mine.loc[comum, "estoque_inicial"] +
                                                    mine.loc[comum, "estoque_atual"]) / 2) \
            .replace(0, np.nan)
        corr = giro_simples.corr(pa.loc[comum, "giro_periodo"])
        r.append(_linha("Arquivos", "Giro reproduz o do arquivo pela mesma fórmula",
                        corr > 0.99,
                        f"correlação {corr:.3f} com (inicial + final) ÷ 2. O sistema usa o "
                        "estoque médio ponderado pelo tempo, que considera todo o período: "
                        "giro mediano "
                        f"{mine.loc[mine['vendas'] > 0, 'giro'].median():.2f} contra "
                        f"{pa.loc[comum][mine.loc[comum, 'vendas'] > 0]['giro_periodo'].median():.2f}"
                        " no arquivo", atencao=True))
    abc_arq = _csv_auxiliar("curva_abc*.csv")
    if abc_arq is not None and len(pos):
        abc_v = curva_abc_vendas(pos, p)
        cont_arq = abc_arq["classe_abc"].value_counts()
        cont = abc_v.itens["classe"].value_counts()
        iguais = all(int(cont.get(c, 0)) == int(cont_arq.get(c, 0)) for c in "ABC")
        r.append(_linha("Arquivos", "Classes ABC por vendas iguais às de curva_abc.csv", iguais,
                        "sistema " + " / ".join(f"{c} {int(cont.get(c, 0))}" for c in "ABC") +
                        " · arquivo " + " / ".join(f"{c} {int(cont_arq.get(c, 0))}" for c in "ABC")
                        + ". O arquivo fecha a classe pelo acumulado do próprio item; o sistema, "
                        "pelo acumulado anterior, como na curva de compras",
                        atencao=True))
    ind = _csv_auxiliar("indicadores_sadpf*.csv")
    if ind is not None:
        valores = dict(zip(ind["indicador"], pd.to_numeric(ind["valor"].astype(str)
                                                           .str.replace(",", "."), errors="coerce")))
        ini = m[m["tipo"] == "ESTOQUE_INICIAL"]
        v_ini = float(ini["valor_total"].sum())
        declarado = valores.get("Valor do estoque inicial (custo)")
        if declarado is not None and not np.isnan(declarado):
            r.append(_linha("Arquivos", "Valor do estoque inicial igual ao de indicadores_sadpf.csv",
                            abs(declarado - v_ini) < 1,
                            f"livro {_brl(v_ini)} · arquivo {_brl(declarado)}; a documentação "
                            "técnica cita o valor do livro", atencao=True))
    prop = remarcacao()
    if len(prop):
        lotes = _lotes(m).set_index(["ean", "Lote"])
        chaves = list(zip(prop["ean"], prop["Lote"]))
        existe = [k in lotes.index for k in chaves]
        saldo_ok = [lotes.loc[k, "saldo"] == s if e else False
                    for k, s, e in zip(chaves, prop["saldo_lote"], existe)]
        r.append(_linha("Remarcação", "Lotes das propostas existem no livro com o mesmo saldo",
                        all(saldo_ok), f"{sum(existe)} de {len(prop)} lotes encontrados · "
                        f"{sum(saldo_ok)} com saldo igual"))
        com_preco = prop[pd.to_numeric(prop["preco_proposto"], errors="coerce").notna()]
        preco = pd.to_numeric(com_preco["preco_proposto"], errors="coerce")
        custo = pd.to_numeric(com_preco["custo_unitario"], errors="coerce")
        abaixo_piso = (preco < custo * 1.08 - 0.005).sum()
        r.append(_linha("Remarcação", "Preço proposto cobre o custo + 8% (piso de liquidação)",
                        abaixo_piso == 0, f"{int(abaixo_piso)} de {len(com_preco)} abaixo do piso"))
        desc = pd.to_numeric(prop["desconto_pct"], errors="coerce").fillna(0)
        r.append(_linha("Remarcação", "Desconto nunca acima de 60%", (desc <= 60.0001).all(),
                        f"maior desconto: {desc.max():.1f}%".replace(".", ",")))
        pend = (prop["status_aprovacao"].astype(str).str.upper() == "PENDENTE").all()
        r.append(_linha("Remarcação", "Nenhuma proposta aplicada sem aprovação", pend,
                        f"{len(prop)} propostas pendentes de aprovação"))
        sis = propostas_validade(rec, p)
        if len(sis):
            familia = lambda a: str(a).split(" ")[0].upper()[:5]  # noqa: E731
            arq = prop.assign(f=prop["acao_recomendada"].map(familia)).set_index(["ean", "Lote"])
            nos = sis.assign(f=sis["acao"].map(familia)).set_index(["ean", "Lote"])
            comuns = nos.index.intersection(arq.index)
            iguais = int((nos.loc[comuns, "f"] == arq.loc[comuns, "f"]).sum())
            r.append(_linha("Remarcação", "Propostas calculadas pelo sistema × arquivo do gerador",
                            len(comuns) > 0 and iguais / len(comuns) >= 0.6,
                            f"sistema: {len(sis)} lotes · arquivo: {len(prop)} · em comum "
                            f"{len(comuns)}, mesma ação em {iguais}. O arquivo usa também o "
                            "ritmo de venda e uma restrição de prescrição; o sistema usa o "
                            "excedente no ritmo atual", atencao=True))
        sis_preco = sis[sis["preco_proposto"].notna()] if len(sis) else sis
        if len(sis_preco):
            abaixo = (sis_preco["preco_proposto"] < sis_preco["custo"] * (1 + MARGEM_PISO) - 0.005).sum()
            r.append(_linha("Remarcação", "Propostas do sistema respeitam o piso e o desconto máximo",
                            abaixo == 0 and (sis_preco["desconto_pct"] <= DESCONTO_MAXIMO + 1e-6).all(),
                            f"{len(sis_preco)} remarcações · {int(abaixo)} abaixo do piso"))

    pt = ponte_estoque(rec)
    r.append(_linha("Saldo", "Ponte do estoque fecha: inicial + entradas − custo vendido − "
                             "perdas = final",
                    abs(pt["diferenca"]) < 1.0,
                    f"{_brl(pt['valor_inicial'])} + {_brl(pt['valor_entradas'])} − "
                    f"{_brl(pt['cmv'])} − {_brl(pt['valor_perdas'])} = {_brl(pt['valor_final'])} "
                    f"(diferença {_brl(pt['diferenca'])})"))

    # -------------------------------------------------------- plausibilidade
    res = resumo(rec, pos)
    r.append(_linha("Plausibilidade", "Perda por validade entre 0,5% e 4% do faturamento",
                    0.005 <= res["perda_pct"] <= 0.04,
                    f"{res['perda_pct']:.2%} do faturamento".replace(".", ","), atencao=True))
    r.append(_linha("Plausibilidade", "Margem bruta entre 25% e 50%",
                    0.25 <= res["margem_pct"] <= 0.50,
                    f"{res['margem_pct']:.1%}".replace(".", ","), atencao=True))
    repos = _reposicoes(m)
    if len(repos):
        vazio = (repos["saldo_antes"] == 0).mean()
        r.append(_linha("Plausibilidade", "Reposições com prateleira vazia entre 5% e 30%",
                        0.05 <= vazio <= 0.30,
                        f"{vazio:.1%} de {len(repos):,} reposições · saldo mediano antes "
                        f"da entrada: {repos['saldo_antes'].median():.0f} un"
                        .replace(",", ".").replace(".", ",", 1), atencao=True))
    return pd.DataFrame(r)


def _reposicoes(m: pd.DataFrame) -> pd.DataFrame:
    """Saldo de cada produto no instante em que uma reposição chegou.

    A primeira entrada de um produto sem estoque inicial é a estreia do item,
    não uma reposição, e fica de fora.
    """
    m = m.sort_values("id_movimento")
    m = m.assign(saldo_antes=m["saldo_apos_movimento"] - m["quantidade"])
    ent = m[m["tipo"] == "ENTRADA"]
    com_inicial = set(m.loc[m["tipo"] == "ESTOQUE_INICIAL", "ean"])
    primeira = ent.groupby("ean")["id_movimento"].transform("min") == ent["id_movimento"]
    estreia = primeira & ~ent["ean"].isin(com_inicial)
    return ent[~estreia]
