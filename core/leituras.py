"""
Leituras do Sistema de Apoio à Decisão: o que mudou de uma para a outra.

Cada vez que o painel de decisão é aberto, o resultado (nível, valor e impacto
de cada ponto) é resumido num "retrato". Se o retrato mudou em relação ao
último registrado — porque entraram cotações novas, porque uma régua foi
ajustada em Preferências — o último vira "anterior" e o novo vira "atual".
O painel então mostra a diferença entre os dois: o motivo da mudança e os
pontos que mudaram de valor ou de gravidade.

Os retratos ficam em dados/leituras.json, separados por combinação de
filtros (comparar a base inteira com um único fornecedor não faria sentido),
e valem entre sessões: ao voltar no dia seguinte, a comparação continua lá.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from core.dados import PASTA_DADOS
from core import parametros as PR

ARQUIVO_LEITURAS = PASTA_DADOS / "leituras.json"
LIMITE_RECORTES = 20


def retrato(insights, diag: dict, df, p, versao_base) -> dict:
    """Resumo de uma leitura: base usada, réguas e o resultado de cada ponto."""
    return {
        "quando": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "versao_base": versao_base,
        "linhas": int(len(df)),
        "cotacoes": int(df["Cotação"].nunique()) if len(df) else 0,
        "ultima_compra": df["dt"].max().strftime("%d/%m/%Y") if len(df) else "",
        "parametros": {k: v for k, v in asdict(p).items() if k != "nomes_originais"},
        "economia": round(float(diag["economia"]), 2),
        "contagem": dict(diag["contagem"]),
        "pontos": {i.id: {"titulo": i.titulo, "nivel": i.nivel, "valor": i.valor,
                          "impacto": round(float(i.impacto), 2)} for i in insights},
    }


def _assinatura(r: dict) -> tuple:
    """O que define uma leitura diferente: base e réguas, não a hora."""
    return (r.get("versao_base"), r.get("linhas"),
            json.dumps(r.get("parametros", {}), sort_keys=True),
            json.dumps(r.get("pontos", {}), sort_keys=True))


def registrar(chave: str, atual: dict) -> dict | None:
    """Guarda o retrato atual e devolve o anterior, para comparação.

    Sem mudança desde o último retrato, nada é regravado e o anterior continua
    o mesmo — a comparação mostrada não some só porque a tela foi reaberta.
    """
    try:
        dados = json.loads(ARQUIVO_LEITURAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    reg = dados.get(chave, {})
    if reg.get("atual") and _assinatura(reg["atual"]) == _assinatura(atual):
        return reg.get("anterior")
    reg = {"anterior": reg.get("atual"), "atual": atual}
    dados.pop(chave, None)
    dados[chave] = reg                          # o mais recente fica no fim
    while len(dados) > LIMITE_RECORTES:
        dados.pop(next(iter(dados)))
    try:
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        ARQUIVO_LEITURAS.write_text(json.dumps(dados, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    except OSError:
        pass                                    # sem gravação, a comparação vale só agora
    return reg["anterior"]


def comparar(anterior: dict | None, atual: dict) -> dict | None:
    """Motivos e pontos que mudaram entre duas leituras; None se não há anterior."""
    if not anterior:
        return None
    motivos = []
    dl = atual["linhas"] - anterior.get("linhas", 0)
    if anterior.get("versao_base") != atual["versao_base"] or dl:
        txt = "base de dados atualizada"
        if dl:
            txt += f": {'+' if dl > 0 else ''}{dl:,} linhas".replace(",", ".")
        dc = atual["cotacoes"] - anterior.get("cotacoes", 0)
        if dc:
            txt += f", {'+' if dc > 0 else ''}{dc} cotação(ões)"
        if anterior.get("ultima_compra") != atual["ultima_compra"]:
            txt += f", última compra agora em {atual['ultima_compra']}"
        motivos.append(txt)
    reguas = []
    for campo, novo in atual["parametros"].items():
        velho = anterior.get("parametros", {}).get(campo)
        if velho is not None and velho != novo:
            rot, _ = PR.descrever(campo)
            reguas.append((rot, PR.formatar(campo, velho), PR.formatar(campo, novo)))
    pontos = []
    for pid, agora in atual["pontos"].items():
        antes = anterior.get("pontos", {}).get(pid)
        if antes is None:
            pontos.append({"titulo": agora["titulo"], "de": None, "para": agora["nivel"],
                           "valor_de": "—", "valor_para": agora["valor"], "novo": True})
        elif antes["nivel"] != agora["nivel"] or antes["valor"] != agora["valor"] \
                or abs(antes["impacto"] - agora["impacto"]) > 0.5:
            pontos.append({"titulo": agora["titulo"], "de": antes["nivel"],
                           "para": agora["nivel"], "valor_de": antes["valor"],
                           "valor_para": agora["valor"], "novo": False})
    return {"quando": anterior.get("quando", ""), "motivos": motivos, "reguas": reguas,
            "pontos": pontos, "economia_de": anterior.get("economia", 0.0),
            "economia_para": atual["economia"]}
