"""
Indicadores, séries temporais, Curva ABC e as análises derivadas.

Nada aqui importa Streamlit: as funções recebem o recorte já filtrado e os
parâmetros, e devolvem estruturas prontas. Isso permite testar todo o cálculo
por fora da interface, inclusive em um notebook.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.dados import FAIXAS_CURTAS
from core.parametros import Parametros


# ---------------------------------------------------------------------------
#                               INDICADORES
# ---------------------------------------------------------------------------
@dataclass
class Indicadores:
    valor_pedido: float = 0.0
    valor_faturado: float = 0.0
    linhas: int = 0
    pedidos: int = 0
    cotacoes: int = 0
    fornecedores: int = 0
    representantes: int = 0
    medicamentos: int = 0
    qtd_pedida: int = 0
    qtd_faturada: int = 0
    meses: int = 0
    inicio: pd.Timestamp | None = None
    fim: pd.Timestamp | None = None

    @property
    def ticket_medio(self) -> float:
        return self.valor_pedido / self.pedidos if self.pedidos else 0.0

    @property
    def ticket_linha(self) -> float:
        return self.valor_pedido / self.linhas if self.linhas else 0.0

    @property
    def media_mensal(self) -> float:
        return self.valor_pedido / self.meses if self.meses else 0.0

    @property
    def nivel_atendimento(self) -> float:
        return self.qtd_faturada / self.qtd_pedida if self.qtd_pedida else 0.0

    @property
    def nao_faturado(self) -> float:
        return self.valor_pedido - self.valor_faturado


def indicadores(df: pd.DataFrame) -> Indicadores:
    if df.empty:
        return Indicadores()
    return Indicadores(
        valor_pedido=float(df["valor_pedido"].sum()),
        valor_faturado=float(df["valor_faturado"].sum()),
        linhas=len(df),
        pedidos=int(df["Pedido"].nunique()),
        cotacoes=int(df["Cotação"].nunique()),
        fornecedores=int(df["Nome do Fornecedor"].nunique()),
        representantes=int(df["Representante"].nunique()),
        medicamentos=int(df["sku"].nunique()),
        qtd_pedida=int(df["Qtde. Ped."].sum()),
        qtd_faturada=int(df["Qtde. Fat."].sum()),
        meses=int(df["ano_mes"].nunique()),
        inicio=df["dt"].min(), fim=df["dt"].max(),
    )


# ---------------------------------------------------------------------------
#                           SÉRIES E AGRUPAMENTOS
# ---------------------------------------------------------------------------
def serie_mensal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["ano_mes", "valor_pedido", "valor_faturado",
                                     "pedidos", "itens"])
    return (df.groupby("ano_mes", as_index=False)
              .agg(valor_pedido=("valor_pedido", "sum"),
                   valor_faturado=("valor_faturado", "sum"),
                   pedidos=("Pedido", "nunique"),
                   itens=("Pedido", "size"))
              .sort_values("ano_mes"))


# ---------------------------------------------------------------------------
#                    COMPARATIVOS: MÊS × ANTERIOR × ANO ANTERIOR
# ---------------------------------------------------------------------------
def mes_referencia(fim: pd.Timestamp) -> pd.Period:
    """Último mês COMPLETO até a data final do recorte.

    Comparar um mês em curso (ex.: 8 dias de julho) com meses fechados faria
    toda variação parecer queda; por isso a referência é o último mês fechado.
    """
    fim = pd.Timestamp(fim)
    mes = fim.to_period("M")
    return mes if fim.normalize() >= mes.end_time.normalize() else mes - 1


def comparar_mes(serie: pd.Series, ref: pd.Period, relativo: bool = True,
                 inicio: pd.Period | None = None, zero_se_vazio: bool = True) -> dict:
    """Valor do mês de referência, do mês anterior e do mesmo mês do ano anterior.

    `serie` é indexada por mês ('2025-06' ou Period). Meses sem movimento dentro
    do histórico valem zero; meses antes do início (`inicio`, ou o primeiro mês
    da série) não existem e voltam None. `relativo` = variação percentual;
    senão, diferença simples (usada para margem, em pontos percentuais). Para
    uma taxa (margem), `zero_se_vazio=False`: mês sem venda não tem margem.
    """
    s = serie.copy()
    s.index = pd.PeriodIndex([str(i) for i in s.index], freq="M")
    s = s.groupby(level=0).sum()
    primeiro = inicio if inicio is not None else (s.index.min() if len(s) else ref)

    def valor(mes):
        if mes < primeiro or mes > ref:
            return None
        if mes not in s.index:
            return 0.0 if zero_se_vazio else None
        v = s[mes]
        return None if pd.isna(v) else float(v)

    def var(a, b):
        if a is None or b is None:
            return None
        if relativo:
            return None if b == 0 else (a - b) / abs(b)
        return a - b

    v, ant, ano = valor(ref), valor(ref - 1), valor(ref - 12)
    return {"ref": ref, "valor": v, "anterior": ant, "ano_anterior": ano,
            "var_mes": var(v, ant), "var_ano": var(v, ano)}


def por_dimensao(df: pd.DataFrame, coluna: str, topo: int | None = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[coluna, "valor_pedido", "valor_faturado",
                                     "pedidos", "itens", "quantidade"])
    agr = (df.groupby(coluna, as_index=False)
             .agg(valor_pedido=("valor_pedido", "sum"),
                  valor_faturado=("valor_faturado", "sum"),
                  pedidos=("Pedido", "nunique"),
                  itens=("Pedido", "size"),
                  quantidade=("Qtde. Ped.", "sum"))
             .sort_values("valor_pedido", ascending=False))
    return agr.head(topo) if topo else agr


def resumo_pedidos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    r = (df.groupby("Pedido", as_index=False)
           .agg(cotacao=("Cotação", "first"), data=("dt", "first"),
                fornecedor=("Nome do Fornecedor", "first"),
                representante=("Representante", "first"),
                status=("Status do Pedido", "first"),
                itens=("Pedido", "size"),
                qtd_pedida=("Qtde. Ped.", "sum"), qtd_faturada=("Qtde. Fat.", "sum"),
                valor_pedido=("valor_pedido", "sum"),
                valor_faturado=("valor_faturado", "sum"))
           .sort_values("data", ascending=False))
    r["atendimento"] = (r["qtd_faturada"] / r["qtd_pedida"]).fillna(0)
    return r


# ---------------------------------------------------------------------------
#                                CURVA ABC
# ---------------------------------------------------------------------------
@dataclass
class ResultadoABC:
    itens: pd.DataFrame
    classes: pd.DataFrame
    total: float
    corte: tuple[float, float]
    base: str
    concentracao_20: float = 0.0

    @property
    def n(self) -> int:
        return len(self.itens)


def curva_abc(df: pd.DataFrame, p: Parametros) -> ResultadoABC:
    """Classifica os medicamentos pela participação no valor de consumo.

    A classe sai do acumulado ANTERIOR ao item, de modo que o item que cruza o
    corte fecha a classe a que pertence — convenção usual da Curva ABC. Usar o
    acumulado do próprio item empurraria essa fronteira para a classe seguinte
    e mudaria a contagem.
    """
    base = p.base_abc
    col_qtd = "Qtde. Fat." if base == "valor_faturado" else "Qtde. Ped."
    vazio = pd.DataFrame(columns=["sku", "medicamento", "valor", "quantidade",
                                  "compras", "fornecedores", "participacao",
                                  "acumulado", "acumulado_pct", "classe", "posicao"])
    if df.empty:
        return ResultadoABC(vazio, _resumo_classes(vazio, 0.0), 0.0, p.corte, base)

    itens = (df.groupby("sku", as_index=False)
               .agg(valor=(base, "sum"), quantidade=(col_qtd, "sum"),
                    compras=("Pedido", "nunique"),
                    fornecedores=("Nome do Fornecedor", "nunique"),
                    preco_venda=("Preço de Venda Unitário (R$)", "last"),
                    categoria=("Categoria Comercial", "last")))
    itens.insert(1, "medicamento", itens["sku"].map(_nome_mais_frequente(df)))
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

    return ResultadoABC(itens, _resumo_classes(itens, total), total, p.corte, base, conc)


def _nome_mais_frequente(df: pd.DataFrame) -> pd.Series:
    """Descrição mais usada de cada SKU (a moda), com empate pela ordem alfabética.

    Mesmo resultado de aplicar Series.mode() grupo a grupo, mas calculado de uma
    vez só: a versão grupo a grupo era o trecho mais lento da Curva ABC.
    """
    contagem = df.groupby(["sku", "medicamento"]).size().reset_index(name="n")
    contagem = contagem.sort_values(["sku", "n", "medicamento"],
                                    ascending=[True, False, True])
    return contagem.drop_duplicates("sku").set_index("sku")["medicamento"]


def custo_ponderado(df: pd.DataFrame, chaves) -> pd.Series:
    """Custo unitário médio ponderado pela quantidade pedida, por grupo.

    soma(custo × quantidade) ÷ soma(quantidade), com divisor mínimo de 1 para
    um grupo sem quantidade não dividir por zero.
    """
    pesos = df.assign(_gasto=df["Vl. Custo (R$)"] * df["Qtde. Ped."])
    g = pesos.groupby(chaves)
    return g["_gasto"].sum() / g["Qtde. Ped."].sum().clip(lower=1)


def _resumo_classes(itens: pd.DataFrame, total: float) -> pd.DataFrame:
    n = len(itens)
    linhas = []
    for classe in ["A", "B", "C"]:
        sub = itens[itens["classe"] == classe] if n else itens
        valor = float(sub["valor"].sum()) if n else 0.0
        linhas.append({"classe": classe, "itens": len(sub),
                       "pct_itens": len(sub) / n if n else 0.0,
                       "valor": valor, "pct_valor": valor / total if total else 0.0,
                       "quantidade": int(sub["quantidade"].sum()) if n else 0,
                       "valor_medio": valor / len(sub) if len(sub) else 0.0})
    return pd.DataFrame(linhas)


def migracao_classe(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Compara a ABC da primeira metade do período com a da segunda.

    A curva do período inteiro é uma fotografia e esconde movimento. Dividindo
    o recorte ao meio aparecem os itens que estão ganhando importância — e que
    provavelmente ainda são tratados com o cuidado da classe antiga.
    """
    vazio = pd.DataFrame(columns=["sku", "medicamento", "de", "classe", "valor"])
    if df.empty:
        return vazio
    meses = sorted(df["ano_mes"].unique())
    if len(meses) < 4:
        return vazio
    corte = meses[len(meses) // 2]
    ini, fim = df[df["ano_mes"] < corte], df[df["ano_mes"] >= corte]
    if len(ini) < 30 or len(fim) < 30:
        return vazio

    antes = curva_abc(ini, p).itens.set_index("sku")["classe"]
    depois = curva_abc(fim, p).itens
    ordem = {"A": 0, "B": 1, "C": 2}
    depois = depois[depois["sku"].isin(antes.index)].copy()
    depois["de"] = depois["sku"].map(antes)
    subiu = depois[depois["classe"].map(ordem) < depois["de"].map(ordem)]
    return subiu.sort_values("valor", ascending=False)[
        ["sku", "medicamento", "de", "classe", "valor", "compras"]]


# ---------------------------------------------------------------------------
#                                 ESTOQUE
# ---------------------------------------------------------------------------
def data_referencia(df: pd.DataFrame, p: Parametros) -> tuple[pd.Timestamp, bool]:
    """Data usada para contar os meses até o vencimento, e se foi ajustada.

    Vale a data configurada em Preferências, a não ser que a base tenha compras
    depois dela: nesse caso vale a data da última compra, porque não faz sentido
    medir a validade de um lote a partir de um dia anterior à chegada dele.
    """
    configurada = pd.Timestamp(p.data_referencia).normalize()
    if df.empty or df["dt"].isna().all():
        return configurada, False
    ultima = df["dt"].max().normalize()
    return (ultima, True) if ultima > configurada else (configurada, False)


def posicao_lotes(df: pd.DataFrame, abc: ResultadoABC, hoje: pd.Timestamp) -> pd.DataFrame:
    """Último lote recebido de cada medicamento, com meses até vencer.

    A base registra compras, não saídas: isto indica risco de perda, não a
    posição física do estoque.
    """
    if df.empty:
        return pd.DataFrame()
    # tail(1) devolve a última LINHA de cada medicamento. groupby().last() pegaria
    # o último valor não nulo de cada coluna separadamente, o que pode misturar
    # dados de compras diferentes no mesmo registro.
    # kind="stable" garante o mesmo desempate quando duas compras têm a mesma data.
    ultimo = df.sort_values("dt", kind="stable").groupby("sku", as_index=False).tail(1)
    cols = ["sku", "medicamento", "Nome do Fornecedor", "Categoria Comercial",
            "Forma Farmacêutica", "Faixa de Recebimento", "dt", "validade",
            "Qtde. Fat.", "valor_faturado"]
    if "Lote" in ultimo.columns:
        cols.insert(6, "Lote")
    lotes = ultimo[cols].rename(columns={
        "Nome do Fornecedor": "fornecedor", "Categoria Comercial": "categoria",
        "Forma Farmacêutica": "forma", "Faixa de Recebimento": "vida_util_entrega",
        "Lote": "lote", "dt": "recebido_em", "Qtde. Fat.": "quantidade",
        "valor_faturado": "valor_lote"})

    # diferença exata em segundos: usar .dt.days truncaria e deslocaria itens
    # que estão na fronteira exata da janela de risco
    lotes["meses_restantes"] = ((lotes["validade"] - hoje).dt.total_seconds()
                                / (86400 * 30.44))
    hist = df.groupby("sku", as_index=False).agg(
        compras=("Pedido", "nunique"), gasto_acumulado=("valor_pedido", "sum"))
    lotes = lotes.merge(hist, on="sku", how="left")
    classes = (abc.itens[["sku", "classe"]] if not abc.itens.empty
               else pd.DataFrame(columns=["sku", "classe"]))
    lotes = lotes.merge(classes, on="sku", how="left")
    lotes["classe"] = lotes["classe"].fillna("C")
    return lotes.sort_values("meses_restantes")


def qualidade_entrega(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Percentual de entregas com menos de metade da validade, por fornecedor."""
    if df.empty:
        return pd.DataFrame(columns=["fornecedor", "linhas", "curtas", "pct", "valor"])
    curto = df[df["validade_curta"]]
    r = (df.groupby("Nome do Fornecedor", as_index=False)
           .agg(linhas=("validade_curta", "size"), curtas=("validade_curta", "sum"))
           .rename(columns={"Nome do Fornecedor": "fornecedor"}))
    valores = (curto.groupby("Nome do Fornecedor")["valor_faturado"].sum()
               if not curto.empty else pd.Series(dtype=float))
    r["valor"] = r["fornecedor"].map(valores).fillna(0.0)
    r = r[r["linhas"] >= p.linhas_minimas].copy()
    r["pct"] = r["curtas"] / r["linhas"]
    return r.sort_values("pct", ascending=False)


def atendimento_fornecedor(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["fornecedor", "atendimento", "pedidos",
                                     "perda", "linhas"])
    r = (df.groupby("Nome do Fornecedor", as_index=False)
           .agg(qtd_pedida=("Qtde. Ped.", "sum"), qtd_faturada=("Qtde. Fat.", "sum"),
                pedidos=("Pedido", "nunique"), linhas=("Pedido", "size"),
                valor_pedido=("valor_pedido", "sum"),
                valor_faturado=("valor_faturado", "sum"))
           .rename(columns={"Nome do Fornecedor": "fornecedor"}))
    r["atendimento"] = (r["qtd_faturada"] / r["qtd_pedida"]).fillna(0)
    r["perda"] = r["valor_pedido"] - r["valor_faturado"]
    return r.sort_values("atendimento")


# ---------------------------------------------------------------------------
#                              PREÇO E OPORTUNIDADE
# ---------------------------------------------------------------------------
def variacao_custo(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Compara o custo unitário da primeira e da última compra de cada item."""
    # tipos fixos: com "suspeito" como texto, tabela[~suspeito] viraria seleção
    # de colunas e apagaria todas (erro com filtros de um só fornecedor)
    vazio = pd.DataFrame(columns=["sku", "medicamento", "custo_inicial",
                                  "custo_atual", "variacao", "compras", "valor",
                                  "suspeito"]).astype({"variacao": float, "suspeito": bool})
    if df.empty:
        return vazio
    ord_ = df.sort_values("dt", kind="stable")   # desempate determinístico
    r = ord_.groupby("sku", as_index=False).agg(
        medicamento=("medicamento", "first"),
        custo_inicial=("Vl. Custo (R$)", "first"),
        custo_atual=("Vl. Custo (R$)", "last"),
        data_inicial=("dt", "first"), data_final=("dt", "last"),
        compras=("Pedido", "nunique"), valor=("valor_pedido", "sum"))
    r = r[(r["compras"] > 1) & (r["custo_inicial"] > 0) &
          (r["valor"] > p.valor_minimo_analise)].copy()
    if r.empty:
        return vazio
    r["variacao"] = (r["custo_atual"] - r["custo_inicial"]) / r["custo_inicial"]
    r["suspeito"] = r["variacao"].abs() > p.variacao_implausivel
    return r.sort_values("variacao", ascending=False)


def oportunidades_fornecedor(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Economia possível comprando cada item do fornecedor mais barato.

    Compara o custo unitário médio ponderado de cada fornecedor para o mesmo
    SKU. Itens com diferença acima de `razao_preco_suspeita` são marcados:
    diferença dessa ordem indica erro de cadastro, não negociação, e por isso
    ficam fora do total de economia.
    """
    vazio = pd.DataFrame(columns=["sku", "medicamento", "economia", "melhor_fornecedor",
                                  "melhor_custo", "pior_custo", "fornecedores",
                                  "valor", "suspeito"]).astype({"economia": float,
                                                                "suspeito": bool})
    if df.empty:
        return vazio

    custo = (custo_ponderado(df, ["sku", "Nome do Fornecedor"])
             .rename("custo_medio").reset_index())

    n_forn = custo.groupby("sku")["Nome do Fornecedor"].nunique()
    multi = n_forn[n_forn > 1].index
    if len(multi) == 0:
        return vazio

    custo = custo[custo["sku"].isin(multi)]
    melhores = custo.loc[custo.groupby("sku")["custo_medio"].idxmin()].set_index("sku")
    piores = custo.groupby("sku")["custo_medio"].max()

    base = df[df["sku"].isin(multi)].copy()
    base["melhor_custo"] = base["sku"].map(melhores["custo_medio"])
    base["economia_linha"] = ((base["Vl. Custo (R$)"] - base["melhor_custo"])
                              .clip(lower=0) * base["Qtde. Ped."])

    r = base.groupby("sku", as_index=False).agg(
        medicamento=("medicamento", "first"),
        economia=("economia_linha", "sum"), valor=("valor_pedido", "sum"))
    r["melhor_fornecedor"] = r["sku"].map(melhores["Nome do Fornecedor"])
    r["melhor_custo"] = r["sku"].map(melhores["custo_medio"])
    r["pior_custo"] = r["sku"].map(piores)
    r["fornecedores"] = r["sku"].map(n_forn)
    razao = r["pior_custo"] / r["melhor_custo"].replace(0, pd.NA)
    r["suspeito"] = (razao > p.razao_preco_suspeita).fillna(False)
    return r[r["economia"] > 1].sort_values("economia", ascending=False)


def melhor_fornecedor_item(sub: pd.DataFrame) -> dict | None:
    """Para um único medicamento: fornecedor de menor custo médio e a economia da troca.

    Mesma regra de `oportunidades_fornecedor` (custo médio ponderado por
    fornecedor; economia = Σ max(0, custo pago − menor custo) × quantidade), para
    que a ficha do medicamento e o apoio à decisão mostrem o mesmo valor.
    Devolve None quando só há um fornecedor.
    """
    custos = custo_ponderado(sub, "Nome do Fornecedor").sort_values()
    if len(custos) < 2:
        return None
    menor, maior = float(custos.iloc[0]), float(custos.iloc[-1])
    economia = float(((sub["Vl. Custo (R$)"] - menor).clip(lower=0) * sub["Qtde. Ped."]).sum())
    return {"fornecedor": custos.index[0], "menor": menor, "maior": maior,
            "economia": economia, "fornecedores": len(custos)}


def _com_preco(df: pd.DataFrame) -> pd.DataFrame:
    """Linhas com preço de venda válido: sem ele a margem não existe."""
    preco = pd.to_numeric(df["Preço de Venda Unitário (R$)"], errors="coerce")
    return df[preco > 0]


def margem_ponderada(df: pd.DataFrame, por: str | None = None):
    """Margem bruta ponderada pela quantidade pedida.

    margem = 1 − Σ(custo × qtde) ÷ Σ(preço de venda × qtde)

    É a mesma fórmula em todas as telas. A média simples das margens de cada
    linha daria a uma linha de 1 unidade o mesmo peso de uma de 500.
    Sem `por`, devolve um número; com `por`, uma série indexada pela coluna.
    """
    base = _com_preco(df)
    custo = base["Vl. Custo (R$)"] * base["Qtde. Ped."]
    venda = base["Preço de Venda Unitário (R$)"] * base["Qtde. Ped."]
    if por is None:
        total_venda = float(venda.sum())
        return 1 - float(custo.sum()) / total_venda if total_venda > 0 else float("nan")
    somas = pd.DataFrame({por: base[por], "custo": custo, "venda": venda}) \
        .groupby(por)[["custo", "venda"]].sum()
    somas = somas[somas["venda"] > 0]
    return (1 - somas["custo"] / somas["venda"]).rename("margem")


def margem_classe_a(df: pd.DataFrame, abc: ResultadoABC) -> pd.DataFrame:
    """Margem bruta ponderada dos itens de classe A, do menor para o maior.

    Itens sem preço de venda registrado ficam de fora do ranking, em vez de
    aparecerem com margem absurda por divisão por zero.
    """
    if df.empty or abc.itens.empty:
        return pd.DataFrame(columns=["sku", "medicamento", "valor", "margem", "compras"])
    m = margem_ponderada(df, por="sku")
    a = abc.itens[abc.itens["classe"] == "A"].merge(m, on="sku", how="inner")
    return a.sort_values("margem")[["sku", "medicamento", "valor", "margem", "compras"]]


# ---------------------------------------------------------------------------
#                       CONDIÇÕES COMERCIAIS DO PEDIDO
# ---------------------------------------------------------------------------
def _coluna(df: pd.DataFrame, nome: str) -> pd.Series:
    """Coluna da planilha, ou vazia se uma cotação nova vier sem ela."""
    return df[nome] if nome in df.columns else pd.Series(pd.NA, index=df.index)


def prazo_em_dias(serie: pd.Series) -> pd.Series:
    """'56 dia(s)' vira 56; texto sem número vira vazio."""
    return pd.to_numeric(serie.astype(str).str.extract(r"(\d+)")[0], errors="coerce")


def pedidos_condicoes(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Cada pedido com prazo de pagamento e situação frente ao faturamento mínimo.

    O faturamento mínimo é o valor mínimo que o distribuidor aceita faturar.
    Um pedido abaixo dele pode ser recusado ou cobrado com frete; um pedido
    que passa por pouco ('no limite') cai abaixo do mínimo com qualquer corte.
    """
    colunas = ["Pedido", "fornecedor", "representante", "cotacao", "data", "valor",
               "minimo", "prazo_dias", "folga", "situacao"]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    base = df.assign(_minimo=pd.to_numeric(_coluna(df, "Faturamento Mínimo"), errors="coerce"),
                     _prazo=prazo_em_dias(_coluna(df, "Prazo de Pagamento")))
    g = (base.groupby("Pedido", as_index=False)
             .agg(fornecedor=("Nome do Fornecedor", "first"),
                  representante=("Representante", "first"), cotacao=("Cotação", "first"),
                  data=("dt", "first"), valor=("valor_pedido", "sum"),
                  minimo=("_minimo", "first"), prazo_dias=("_prazo", "first")))
    tem_minimo = g["minimo"].fillna(0) > 0
    g["folga"] = np.where(tem_minimo, g["valor"] / g["minimo"].where(tem_minimo) - 1, np.nan)
    g["situacao"] = np.select(
        [~tem_minimo, g["folga"] < 0, g["folga"] < p.pedido_minimo_folga],
        ["sem mínimo informado", "abaixo do mínimo", "no limite"], "acima do mínimo")
    return g[colunas].sort_values("data", ascending=False)


def condicoes_fornecedor(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Prazo, faturamento mínimo, desconto, aderência à cotação e margem por fornecedor."""
    if df.empty:
        return pd.DataFrame()
    ped = pedidos_condicoes(df, p)
    ped["_peso_prazo"] = ped["prazo_dias"] * ped["valor"]
    r = (ped.groupby("fornecedor", as_index=False)
            .agg(pedidos=("Pedido", "size"), valor=("valor", "sum"),
                 _peso=("_peso_prazo", "sum"), minimo=("minimo", "median"),
                 pedido_medio=("valor", "mean"),
                 abaixo=("situacao", lambda s: int((s == "abaixo do mínimo").sum())),
                 no_limite=("situacao", lambda s: int((s == "no limite").sum()))))
    # prazo médio ponderado pelo valor: um pedido grande pesa mais no caixa
    r["prazo_medio"] = r["_peso"] / r["valor"].where(r["valor"] > 0)
    linhas = df.assign(_desc=pd.to_numeric(_coluna(df, "Desc. Com. (%)"), errors="coerce"),
                       _cot=pd.to_numeric(_coluna(df, "Qtde. Cot"), errors="coerce"))
    extra = (linhas.groupby("Nome do Fornecedor")
                   .agg(desconto=("_desc", "mean"), qtd_cotada=("_cot", "sum"),
                        qtd_pedida=("Qtde. Ped.", "sum"), qtd_faturada=("Qtde. Fat.", "sum"),
                        representantes=("Representante", "nunique")))
    r = r.merge(extra, left_on="fornecedor", right_index=True, how="left")
    r["pedido_vs_cotado"] = r["qtd_pedida"] / r["qtd_cotada"].where(r["qtd_cotada"] > 0)
    r["atendimento"] = r["qtd_faturada"] / r["qtd_pedida"].where(r["qtd_pedida"] > 0)
    r["margem"] = r["fornecedor"].map(margem_ponderada(df, por="Nome do Fornecedor"))
    r["participacao"] = r["valor"] / (r["valor"].sum() or 1.0)
    return r.drop(columns=["_peso"]).sort_values("valor", ascending=False)


def por_representante(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Valor, pedidos, prazo e atendimento por representante comercial."""
    if df.empty:
        return pd.DataFrame()
    ped = pedidos_condicoes(df, p)
    ped["_peso_prazo"] = ped["prazo_dias"] * ped["valor"]
    r = (ped.groupby("representante", as_index=False)
            .agg(fornecedor=("fornecedor", "first"), pedidos=("Pedido", "size"),
                 valor=("valor", "sum"), _peso=("_peso_prazo", "sum"),
                 abaixo=("situacao", lambda s: int((s == "abaixo do mínimo").sum()))))
    r["prazo_medio"] = r["_peso"] / r["valor"].where(r["valor"] > 0)
    at = (df.groupby("Representante")[["Qtde. Fat.", "Qtde. Ped."]].sum())
    r["atendimento"] = r["representante"].map(at["Qtde. Fat."] / at["Qtde. Ped."])
    return r.drop(columns=["_peso"]).sort_values("valor", ascending=False)


# ---------------------------------------------------------------------------
#                    REGULARIDADE (XYZ) E MATRIZ ABC × XYZ
# ---------------------------------------------------------------------------
def classificacao_xyz(df: pd.DataFrame, abc: ResultadoABC, p: Parametros) -> pd.DataFrame:
    """Regularidade da compra de cada medicamento, cruzada com a Curva ABC.

    Monta a quantidade comprada por TRIMESTRE (zero nos trimestres sem compra)
    e mede o coeficiente de variação, CV = desvio-padrão ÷ média. CV baixo é
    compra regular (X), médio é variável (Y), alto é irregular (Z). Sem dados
    de venda, a regularidade da compra é a melhor aproximação da demanda.

    O trimestre, e não o mês, porque as cotações são espaçadas: mês a mês quase
    todo item cairia em Z só por não ter sido cotado naquele mês.
    """
    colunas = ["sku", "medicamento", "classe", "xyz", "abc_xyz", "cv", "trimestres_com_compra",
               "media_trimestral", "valor", "compras"]
    if df.empty or abc.itens.empty:
        return pd.DataFrame(columns=colunas)
    periodos = pd.period_range(df["dt"].min(), df["dt"].max(), freq="Q").astype(str)
    col_qtd = "Qtde. Fat." if p.base_abc == "valor_faturado" else "Qtde. Ped."
    tri = (df.assign(_tri=df["dt"].dt.to_period("Q").astype(str))
             .pivot_table(index="sku", columns="_tri", values=col_qtd,
                          aggfunc="sum", fill_value=0)
             .reindex(columns=periodos, fill_value=0))
    media = tri.mean(axis=1)
    cv = (tri.std(axis=1, ddof=0) / media.where(media > 0)).fillna(np.inf)
    r = pd.DataFrame({"sku": tri.index, "cv": cv.values, "media_trimestral": media.values,
                      "trimestres_com_compra": (tri > 0).sum(axis=1).values})
    r["xyz"] = np.where(r["cv"] <= p.cv_x, "X", np.where(r["cv"] <= p.cv_y, "Y", "Z"))
    r = abc.itens[["sku", "medicamento", "classe", "valor", "compras"]].merge(r, on="sku")
    r["abc_xyz"] = r["classe"] + r["xyz"]
    return r[colunas].sort_values("valor", ascending=False)


def matriz_abc_xyz(xyz: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Contagem de itens e valor em cada combinação ABC × XYZ (linhas A-C, colunas X-Z)."""
    idx, cols = ["A", "B", "C"], ["X", "Y", "Z"]
    if xyz.empty:
        vazio = pd.DataFrame(0, index=idx, columns=cols)
        return vazio, vazio.astype(float)
    itens = pd.crosstab(xyz["classe"], xyz["xyz"]).reindex(index=idx, columns=cols,
                                                           fill_value=0)
    valor = (xyz.pivot_table(index="classe", columns="xyz", values="valor", aggfunc="sum",
                             fill_value=0.0)
                .reindex(index=idx, columns=cols, fill_value=0.0))
    return itens, valor


# ---------------------------------------------------------------------------
#                         REPOSIÇÃO E IDADE DO LOTE
# ---------------------------------------------------------------------------
def intervalo_compras(df: pd.DataFrame) -> pd.DataFrame:
    """Dias médios entre compras de cada medicamento e a próxima compra esperada.

    Considera um dia de compra por medicamento (dois pedidos no mesmo dia contam
    uma vez). Só entram itens com duas datas de compra ou mais.
    """
    colunas = ["sku", "medicamento", "compras", "intervalo_medio", "ultima_compra",
               "proxima_prevista"]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    d = (df.assign(_dia=df["dt"].dt.normalize())[["sku", "medicamento", "_dia"]]
           .drop_duplicates(["sku", "_dia"]).sort_values(["sku", "_dia"]))
    d["_gap"] = d.groupby("sku")["_dia"].diff().dt.days
    r = (d.groupby("sku", as_index=False)
          .agg(medicamento=("medicamento", "first"), compras=("_dia", "size"),
               intervalo_medio=("_gap", "mean"), ultima_compra=("_dia", "max")))
    r = r[r["compras"] >= 2].copy()
    r["proxima_prevista"] = r["ultima_compra"] + pd.to_timedelta(r["intervalo_medio"], unit="D")
    return r[colunas].sort_values("intervalo_medio")


def idade_na_entrega(df: pd.DataFrame) -> pd.DataFrame:
    """Idade do lote ao chegar: dias desde a fabricação e fração da validade que restava."""
    if df.empty or "fabricacao" not in df.columns:
        return pd.DataFrame(columns=["fornecedor", "linhas", "idade_mediana", "restante_medio"])
    v = df[df["fabricacao"].notna() & df["validade"].notna()].copy()
    if v.empty:
        return pd.DataFrame(columns=["fornecedor", "linhas", "idade_mediana", "restante_medio"])
    v["_idade"] = (v["dt"] - v["fabricacao"]).dt.days
    total = (v["validade"] - v["fabricacao"]).dt.days
    v["_restante"] = ((v["validade"] - v["dt"]).dt.days / total.where(total > 0)).clip(0, 1)
    return (v.groupby("Nome do Fornecedor", as_index=False)
              .agg(linhas=("_idade", "size"), idade_mediana=("_idade", "median"),
                   restante_medio=("_restante", "mean"))
              .rename(columns={"Nome do Fornecedor": "fornecedor"})
              .sort_values("restante_medio"))


# ---------------------------------------------------------------------------
#                    ÍNDICE DE CUSTO E DISPERSÃO DE PREÇO
# ---------------------------------------------------------------------------
def indice_custo(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Índice mensal de custo da cesta, base 100 na primeira compra de cada item.

    Cada linha compara o custo pago com o custo da primeira compra do mesmo
    medicamento; o mês é a média dessas razões, ponderada pelo valor da compra
    ao custo inicial. Mede inflação de custo, separando-a da mudança de mix.
    Razões implausíveis (erro de cadastro) ficam de fora.
    """
    if df.empty:
        return pd.DataFrame(columns=["ano_mes", "indice", "linhas"])
    o = df[df["Vl. Custo (R$)"] > 0].sort_values("dt", kind="stable")
    inicial = o.groupby("sku")["Vl. Custo (R$)"].transform("first")
    razao = o["Vl. Custo (R$)"] / inicial
    peso = o["Qtde. Ped."] * inicial
    ok = razao.between(1 / (1 + p.variacao_implausivel), 1 + p.variacao_implausivel)
    t = pd.DataFrame({"ano_mes": o["ano_mes"], "rp": razao * peso, "peso": peso})[ok]
    r = t.groupby("ano_mes", as_index=False).agg(rp=("rp", "sum"), peso=("peso", "sum"),
                                                  linhas=("peso", "size"))
    r["indice"] = 100 * r["rp"] / r["peso"]
    return r[["ano_mes", "indice", "linhas"]].sort_values("ano_mes")


def dispersao_preco(df: pd.DataFrame) -> pd.DataFrame:
    """Diferença entre o maior e o menor custo médio do mesmo item entre fornecedores."""
    colunas = ["sku", "medicamento", "fornecedores", "menor_custo", "maior_custo",
               "dispersao", "valor"]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    c = custo_ponderado(df, ["sku", "Nome do Fornecedor"]).rename("custo").reset_index()
    r = c.groupby("sku").agg(fornecedores=("custo", "size"), menor_custo=("custo", "min"),
                             maior_custo=("custo", "max"))
    r = r[(r["fornecedores"] > 1) & (r["menor_custo"] > 0)].copy()
    r["dispersao"] = r["maior_custo"] / r["menor_custo"] - 1
    valor = df.groupby("sku")["valor_pedido"].sum()
    nomes = df.groupby("sku")["medicamento"].first()
    r = r.reset_index()
    r["valor"] = r["sku"].map(valor)
    r["medicamento"] = r["sku"].map(nomes)
    return r[colunas].sort_values("dispersao", ascending=False)


# ---------------------------------------------------------------------------
#                          ESTATÍSTICA DESCRITIVA
# ---------------------------------------------------------------------------
def descritiva(serie: pd.Series) -> dict:
    """Medidas de posição e dispersão, outliers (1,5 × IQR) e IC de 95% da média.

    O intervalo de confiança usa a aproximação normal (1,96 × erro-padrão),
    adequada para amostras grandes como as desta base.
    """
    s = pd.to_numeric(serie, errors="coerce").dropna()
    n = len(s)
    if n == 0:
        return {"n": 0}
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    media, desvio = s.mean(), s.std(ddof=1) if n > 1 else 0.0
    erro = 1.96 * desvio / np.sqrt(n) if n > 1 else 0.0
    moda = s.mode()
    return {"n": n, "media": media, "mediana": s.median(),
            "moda": float(moda.iat[0]) if not moda.empty else float("nan"),
            "desvio": desvio, "cv": desvio / media if media else float("nan"),
            "minimo": s.min(), "q1": q1, "q3": q3, "maximo": s.max(), "iqr": iqr,
            "outliers": int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum()),
            "ic_inf": media - erro, "ic_sup": media + erro}
