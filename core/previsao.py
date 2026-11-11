"""
Previsão para a próxima cotação: orçamento provável e itens candidatos.

A base registra compras, não vendas, e cerca de metade dos itens comprados em
cada mês nunca tinha sido comprada antes. Por isso o módulo não promete um
"pedido previsto": ele estima uma FAIXA de gasto para o mês e lista os itens
recorrentes com maior chance de voltar a ser comprados, para a gestora
conferir antes de abrir a cotação.

Toda estimativa vem acompanhada do seu acerto no próprio histórico
(backtest): para cada mês passado, a previsão é refeita só com os dados
anteriores a ele e comparada com o que de fato foi comprado.

Métodos, escolhidos por esse teste na base original:
- orçamento: média e desvio-padrão do gasto mensal de todo o histórico
  anterior (faixa = média ± 1 desvio);
- chance de compra de um item: fração dos meses observados em que ele foi
  comprado; o ritmo (última compra + intervalo médio) indica se a compra
  está no prazo, atrasada ou ainda adiante.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core import metricas as M
from core.parametros import Parametros

MESES_MINIMOS_TESTE = 6        # o backtest só começa com 6 meses de histórico


def mes_alvo(df: pd.DataFrame) -> pd.Period:
    """Mês seguinte à última compra registrada: a próxima cotação a planejar."""
    return df["dt"].max().to_period("M") + 1


def _gasto_mensal(df: pd.DataFrame) -> pd.Series:
    m = df.groupby(df["dt"].dt.to_period("M"))["valor_pedido"].sum()
    return m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0.0)


# ---------------------------------------------------------------------------
#                              ORÇAMENTO DO MÊS
# ---------------------------------------------------------------------------
def orcamento(df: pd.DataFrame) -> dict:
    """Faixa provável de gasto do próximo mês e o acerto dessa faixa no passado."""
    serie = _gasto_mensal(df)
    media, desvio = float(serie.mean()), float(serie.std(ddof=1)) if len(serie) > 1 else 0.0
    teste = []
    for i in range(MESES_MINIMOS_TESTE, len(serie)):
        hist = serie.iloc[:i]
        m, s = hist.mean(), hist.std(ddof=1)
        real = serie.iloc[i]
        teste.append({"mes": str(serie.index[i]), "previsto": m,
                      "faixa_min": max(0.0, m - s), "faixa_max": m + s, "real": real,
                      "dentro": (m - s) <= real <= (m + s),
                      "erro": abs(m - real) / real if real else np.nan})
    teste = pd.DataFrame(teste)
    return {
        "alvo": mes_alvo(df), "media": media, "desvio": desvio,
        "faixa_min": max(0.0, media - desvio), "faixa_max": media + desvio,
        "media_3m": float(serie.iloc[-3:].mean()),
        "serie": serie.rename("valor").reset_index().rename(columns={"index": "mes"}),
        "teste": teste,
        "acerto_faixa": float(teste["dentro"].mean()) if len(teste) else float("nan"),
        "erro_mediano": float(teste["erro"].median()) if len(teste) else float("nan"),
    }


# ---------------------------------------------------------------------------
#                            ITENS CANDIDATOS
# ---------------------------------------------------------------------------
def _chance(prob: pd.Series, p: Parametros) -> pd.Series:
    return pd.Series(np.select([prob >= p.previsao_chance_alta, prob >= p.previsao_chance_minima],
                               ["alta", "média"], "baixa"), index=prob.index)


def _probabilidades(hist: pd.DataFrame, alvo: pd.Period) -> pd.DataFrame:
    """Por item: meses com compra, chance, ritmo e próxima compra prevista."""
    meses_obs = len(pd.period_range(hist["dt"].min().to_period("M"), alvo - 1, freq="M"))
    mes = hist["dt"].dt.to_period("M")
    por = (hist.assign(_mes=mes).groupby("sku")
               .agg(meses_com_compra=("_mes", "nunique"), compras=("Pedido", "nunique"),
                    ultima=("dt", "max")))
    por["prob"] = por["meses_com_compra"] / max(1, meses_obs)
    dias = (hist.assign(_dia=hist["dt"].dt.normalize())[["sku", "_dia"]]
                .drop_duplicates().sort_values(["sku", "_dia"]))
    intervalo = dias.groupby("sku")["_dia"].diff().dt.days.groupby(dias["sku"]).mean()
    por["intervalo_medio"] = intervalo
    por["proxima"] = por["ultima"] + pd.to_timedelta(por["intervalo_medio"], unit="D")
    ini, fim = alvo.start_time, alvo.end_time
    # "atrasada": a compra esperada já passou, mas há pouco (até um intervalo a mais);
    # "parada": passou de dois intervalos sem compra — provavelmente saiu da rotina
    parada = por["ultima"] + 2 * pd.to_timedelta(por["intervalo_medio"], unit="D") < ini
    por["ritmo"] = np.select(
        [por["intervalo_medio"].isna(), parada, por["proxima"] < ini, por["proxima"] <= fim],
        ["sem ritmo (1 dia de compra)", "parada", "atrasada", "prevista para o mês"],
        "mais adiante")
    return por


def candidatos(df: pd.DataFrame, abc: M.ResultadoABC, p: Parametros) -> pd.DataFrame:
    """Itens recorrentes com chance de compra no próximo mês, do mais provável ao menos."""
    colunas = ["sku", "medicamento", "classe", "chance", "prob", "ritmo", "meses_com_compra",
               "intervalo_medio", "ultima", "qtd_estimada", "custo_ultimo", "valor_estimado",
               "ultimo_fornecedor", "fornecedor_menor_custo", "menor_custo"]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    alvo = mes_alvo(df)
    por = _probabilidades(df, alvo)
    # só itens comprados em pelo menos dois meses: um único mês não indica rotina
    por = por[(por["meses_com_compra"] >= 2) &
              ((por["prob"] >= p.previsao_chance_minima) |
               por["ritmo"].isin(["prevista para o mês", "atrasada"]))].copy()
    if por.empty:
        return pd.DataFrame(columns=colunas)
    ordem = df.sort_values("dt", kind="stable")
    ultimo = ordem.groupby("sku").tail(1).set_index("sku")
    por_compra = df.groupby(["sku", "Pedido"])["Qtde. Ped."].sum()
    por["qtd_estimada"] = por_compra.groupby("sku").median().reindex(por.index).round()
    por["custo_ultimo"] = ultimo["Vl. Custo (R$)"].reindex(por.index)
    por["valor_estimado"] = por["qtd_estimada"] * por["custo_ultimo"]
    por["ultimo_fornecedor"] = ultimo["Nome do Fornecedor"].reindex(por.index)
    por["medicamento"] = ultimo["medicamento"].reindex(por.index)
    custo = M.custo_ponderado(df, ["sku", "Nome do Fornecedor"]).rename("c").reset_index()
    melhor = custo.loc[custo.groupby("sku")["c"].idxmin()].set_index("sku")
    por["fornecedor_menor_custo"] = melhor["Nome do Fornecedor"].reindex(por.index)
    por["menor_custo"] = melhor["c"].reindex(por.index)
    por["chance"] = _chance(por["prob"], p)
    classes = abc.itens.set_index("sku")["classe"] if not abc.itens.empty else pd.Series()
    por["classe"] = classes.reindex(por.index).fillna("C")
    r = por.reset_index()
    peso = r["chance"].map({"alta": 0, "média": 1, "baixa": 2})
    return r.assign(_peso=peso).sort_values(["_peso", "prob", "valor_estimado"],
                                            ascending=[True, False, False])[colunas]


# ---------------------------------------------------------------------------
#                       CONFIABILIDADE (BACKTEST DOS ITENS)
# ---------------------------------------------------------------------------
def confiabilidade(df: pd.DataFrame, p: Parametros) -> pd.DataFrame:
    """Taxa de confirmação de cada faixa de chance nos meses passados.

    Para cada mês com pelo menos 6 meses de histórico antes, refaz a lista de
    candidatos só com o passado e verifica quais foram de fato comprados.
    """
    meses = sorted(df["dt"].dt.to_period("M").unique())
    linhas = []
    for alvo in meses[MESES_MINIMOS_TESTE:]:
        hist = df[df["dt"].dt.to_period("M") < alvo]
        real = df[df["dt"].dt.to_period("M") == alvo]
        por = _probabilidades(hist, alvo)
        por = por[(por["meses_com_compra"] >= 2) &
                  ((por["prob"] >= p.previsao_chance_minima) |
                   por["ritmo"].isin(["prevista para o mês", "atrasada"]))]
        por = por.assign(chance=_chance(por["prob"], p),
                         comprado=por.index.isin(set(real["sku"])))
        valor_real = real["valor_pedido"].sum()
        valor_previsto = real[real["sku"].isin(por.index)]["valor_pedido"].sum()
        for chance, g in por.groupby("chance"):
            linhas.append({"mes": str(alvo), "chance": chance, "previstos": len(g),
                           "confirmados": int(g["comprado"].sum())})
        linhas.append({"mes": str(alvo), "chance": "_valor", "previstos": 0, "confirmados": 0,
                       "cobertura_valor": valor_previsto / valor_real if valor_real else np.nan,
                       "itens_novos": len(set(real["sku"]) - set(hist["sku"])) /
                                      max(1, real["sku"].nunique())})
    return pd.DataFrame(linhas)


def resumo_confiabilidade(teste: pd.DataFrame) -> dict:
    """Taxa de confirmação por faixa, cobertura do valor e parcela de itens novos."""
    if teste.empty:
        return {"faixas": pd.DataFrame(), "cobertura_valor": float("nan"),
                "itens_novos": float("nan"), "meses": 0}
    faixas = (teste[teste["chance"] != "_valor"].groupby("chance")[["previstos", "confirmados"]]
                  .sum().reindex(["alta", "média", "baixa"]).dropna())
    faixas["taxa"] = faixas["confirmados"] / faixas["previstos"].where(faixas["previstos"] > 0)
    v = teste[teste["chance"] == "_valor"]
    return {"faixas": faixas, "cobertura_valor": float(v["cobertura_valor"].mean()),
            "itens_novos": float(v["itens_novos"].mean()), "meses": len(v)}
