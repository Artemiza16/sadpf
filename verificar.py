#!/usr/bin/env python3
"""
Verificação do ambiente do SADPF.

Roda antes de subir o painel: confere versão do Python, bibliotecas, leitura da
base, os principais cálculos e o motor de decisão. Não abre navegador nem sobe
servidor — só imprime o resultado no terminal.

Uso:
    python verificar.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

OK, FALHA = "  [ok]  ", "  [ERRO]"
problemas: list[str] = []


def secao(titulo: str) -> None:
    print(f"\n{titulo}\n" + "-" * 62)


# ------------------------------------------------------------------ 1. Python
secao("1. Versão do Python")
v = sys.version_info
print(f"  Python {v.major}.{v.minor}.{v.micro}")
if v < (3, 10):
    problemas.append("Python 3.10 ou superior é necessário.")
    print(FALHA, "versão muito antiga — instale o Python 3.11 ou 3.12")
else:
    print(OK, "versão compatível")

# ------------------------------------------------------------- 2. Bibliotecas
secao("2. Bibliotecas")
for nome in ("pandas", "numpy", "plotly", "streamlit", "openpyxl"):
    try:
        mod = __import__(nome)
        print(OK, f"{nome:<10} {getattr(mod, '__version__', '?')}")
    except ImportError:
        problemas.append(f"Falta instalar {nome}.")
        print(FALHA, f"{nome} não encontrado")

if problemas:
    print("\nInstale o que falta com:  pip install -r requirements.txt")
    sys.exit(1)

import pandas as pd  # noqa: E402

from core import dados as D          # noqa: E402
from core import decisao as Dc       # noqa: E402
from core import metricas as M       # noqa: E402
from core import parametros as PR    # noqa: E402

# -------------------------------------------------------------------- 3. Base
secao("3. Base de dados")
if not D.BASE_ORIGINAL.exists() and not D.BASE_CONSOLIDADA.exists():
    print(FALHA, f"nenhuma base encontrada em {D.PASTA_DADOS}")
    print("         coloque a planilha em dados/cotacao_06_09.xlsx")
    sys.exit(1)

try:
    df, origem = D.carregar_base()
except Exception as erro:                                   # noqa: BLE001
    print(FALHA, f"não foi possível preparar a base: {erro}")
    sys.exit(1)

print(OK, f"origem: {origem}")
print(OK, f"{len(df):,} linhas preparadas".replace(",", "."))
print(OK, f"período de {df['dt'].min():%d/%m/%Y} a {df['dt'].max():%d/%m/%Y}")
print(OK, f"regras ativas: status {', '.join(D.STATUS_MANTIDOS) or 'todos'} · "
          f"{len(D.CORRECOES)} correção(ões) de cadastro")

# ---------------------------------------------------------------- 4. Cálculos
secao("4. Cálculos (comparados com os valores esperados)")
p = PR.Parametros()
ind = M.indicadores(df)
abc = M.curva_abc(df, p)
lotes = M.posicao_lotes(df, abc, pd.Timestamp(p.data_referencia))
oport = M.oportunidades_fornecedor(df, p)
insights = Dc.gerar(df, abc, p)

conferencias = [
    ("Valor pedido", round(ind.valor_pedido, 2), 216658.42),
    ("Valor faturado", round(ind.valor_faturado, 2), 216798.38),
    ("Linhas", ind.linhas, 1657),
    ("Pedidos", ind.pedidos, 116),
    ("Cotações", ind.cotacoes, 23),
    ("Medicamentos (SKU)", ind.medicamentos, 960),
    ("Fornecedores", ind.fornecedores, 10),
    ("Curva ABC — classe A", int(abc.classes.loc[0, "itens"]), 306),
    ("Curva ABC — classe B", int(abc.classes.loc[1, "itens"]), 312),
    ("Curva ABC — classe C", int(abc.classes.loc[2, "itens"]), 342),
    ("Lotes monitorados", len(lotes), 960),
    ("Lotes já vencidos", int((lotes["meses_restantes"] < 0).sum()), 133),
    ("Economia possível", round(oport[~oport["suspeito"]]["economia"].sum(), 2), 8584.82),
    ("Itens com erro de cadastro", int(oport["suspeito"].sum()), 3),
    ("Insights gerados", len(insights), 21),
]
for nome, obtido, esperado in conferencias:
    if obtido == esperado:
        print(OK, f"{nome:<28} {obtido}")
    else:
        problemas.append(f"{nome}: obtido {obtido}, esperado {esperado}")
        print(FALHA, f"{nome:<28} obtido {obtido} · esperado {esperado}")

print("\n  (os valores esperados valem para a base original; com dados novos eles")
print("   mudam, e uma divergência aqui passa a ser apenas informativa)")

# ----------------------------------------------------------------- 5. Filtros
secao("5. Filtros")
r1 = D.aplicar_filtros(df, {"fornecedores": D.opcoes(df, "Nome do Fornecedor")[:2]})
print(OK, f"filtro por 2 fornecedores: {len(r1)} de {len(df)} linhas")
r2 = D.aplicar_filtros(df, {"categorias": ["Genérico"]})
print(OK, f"filtro por categoria: {len(r2)} linhas")

# -------------------------------------------------------- 6. Motor de decisão
secao("6. Motor de decisão")
diag = Dc.diagnostico(insights, ind.valor_pedido)
print(OK, "gravidade: " + " · ".join(f"{Dc.NIVEIS[k]} {v}" for k, v in diag["contagem"].items()))
print(OK, f"economia direta: R$ {diag['economia']:,.2f}".replace(",", "@")
          .replace(".", ",").replace("@", "."))
print(OK, f"pontos com ação: {len(diag['acionaveis'])}")

# o diagnóstico precisa reagir a uma mudança de parâmetro
p2 = PR.Parametros(exposicao_critica=0.30)
diag2 = Dc.diagnostico(Dc.gerar(df, abc, p2), ind.valor_pedido)
if diag2["contagem"] != diag["contagem"]:
    print(OK, "o diagnóstico muda quando a régua de gravidade muda")
else:
    print(FALHA, "o diagnóstico não reagiu à mudança de parâmetro")
    problemas.append("motor de decisão não reage aos parâmetros")

# ------------------------------------------------ 7. Importação de cotações
# Simulada sobre uma cópia temporária: a base real em dados/ não é alterada.
secao("7. Importação de cotações (simulada numa cópia da base)")


def conferir(condicao: bool, texto: str) -> None:
    if condicao:
        print(OK, texto)
    else:
        print(FALHA, texto)
        problemas.append(f"importação: {texto}")


import shutil      # noqa: E402
import tempfile    # noqa: E402

originais = (D.BASE_CONSOLIDADA, D.PASTA_HISTORICO)
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    D.BASE_CONSOLIDADA = tmp / "base_consolidada.csv"
    D.PASTA_HISTORICO = tmp / "historico"
    try:
        shutil.copy(originais[0], D.BASE_CONSOLIDADA)
        base, _ = D.carregar_base()
        n_base = len(base)
        bruto = D.ler_arquivo(D.BASE_CONSOLIDADA)

        # 30 linhas de uma cotação nova, com datas como data de verdade (e não
        # serial do Excel), 2 linhas repetidas no próprio arquivo e 5 linhas que
        # já estão na base
        novas = bruto.head(30).copy()
        novas["Cotação"] = 99000001
        novas["Pedido"] = [99100000 + i for i in range(len(novas))]
        novas["Data de Criação"] = pd.Timestamp("2026-10-15 09:30")
        novas["Data de Validade"] = pd.Timestamp("2028-03-31")
        arquivo = pd.concat([novas, novas.head(2), bruto.tail(5)], ignore_index=True)
        caminho = tmp / "cotacao_nova.xlsx"
        arquivo.to_excel(caminho, index=False)

        previa = D.analisar_entrada(caminho, base)
        conferir(previa.ok and len(previa.novas) == 30,
                 f"prévia: {len(previa.novas)} linhas novas (esperado 30)")
        conferir(len(previa.duplicadas) == 5,
                 f"prévia: {len(previa.duplicadas)} já existentes (esperado 5)")
        conferir(any("repetida" in linha for linha in previa.log_limpeza),
                 "linhas repetidas dentro do arquivo foram identificadas")

        D.mesclar(base, previa.novas)
        depois, _ = D.carregar_base()          # relido do disco, como faz o painel
        conferir(len(depois) == n_base + 30,
                 f"base passou de {n_base} para {len(depois)} linhas (esperado +30)")
        conferir(not D.chave_linha(depois).duplicated().any(),
                 "nenhuma linha duplicada por cotação + pedido + produto")
        conferir(depois["dt"].notna().all() and depois["validade"].notna().all(),
                 "todas as datas legíveis após a mistura de formatos")
        conferir(depois["dt"].max() == pd.Timestamp("2026-10-15 09:30"),
                 f"datas novas lidas corretamente (última compra: {depois['dt'].max():%d/%m/%Y})")
        conferir(depois["sku"].nunique() == base["sku"].nunique(),
                 "os mesmos produtos não viraram códigos diferentes")

        de_novo = D.analisar_entrada(caminho, depois)
        conferir(len(de_novo.novas) == 0, "reenviar o mesmo arquivo não inclui nada")

        # estoque: compras depois da data de referência configurada
        ref, ajustada = M.data_referencia(depois, p)
        conferir(ajustada and ref == pd.Timestamp("2026-10-15"),
                 f"data de referência acompanha a última compra ({ref:%d/%m/%Y})")
        abc2 = M.curva_abc(depois, p)
        lotes2 = M.posicao_lotes(depois, abc2, ref)
        sku_novo = str(novas["Código do Produto"].iloc[0]).strip()
        lote = lotes2[lotes2["sku"] == sku_novo].iloc[0]
        conferir(lote["recebido_em"] == pd.Timestamp("2026-10-15 09:30")
                 and lote["validade"] == pd.Timestamp("2028-03-31"),
                 "Gestão de Estoque usa o lote mais recente de cada medicamento")
        conferir(len(Dc.gerar(depois, abc2, p)) == 21, "motor de decisão roda com a base nova")

        # CSV com datas em texto dd/mm/aaaa
        csv_novas = bruto.head(10).copy()
        csv_novas["Cotação"] = 99000002
        csv_novas["Pedido"] = [99200000 + i for i in range(len(csv_novas))]
        csv_novas["Data de Criação"] = "20/11/2026"
        csv_novas["Data de Validade"] = "31/12/2027"
        caminho_csv = tmp / "cotacao_texto.csv"
        csv_novas.to_csv(caminho_csv, index=False, sep=";", decimal=",", encoding="utf-8-sig")
        previa_csv = D.analisar_entrada(caminho_csv, depois)
        D.mesclar(depois, previa_csv.novas)
        final, _ = D.carregar_base()
        lidas = final[final["Cotação"] == 99000002]
        conferir(len(lidas) == 10 and (lidas["dt"] == pd.Timestamp("2026-11-20")).all(),
                 "CSV com datas em texto (dd/mm/aaaa) entra com as datas certas")

        # restauração
        versoes = D.versoes_anteriores()
        restaurada = D.restaurar_versao(versoes[-1])
        conferir(len(restaurada) == n_base, "restaurar a primeira cópia volta à base original")
        conferir(len(D.versoes_anteriores()) == len(versoes) + 1,
                 "a restauração guardou antes uma cópia da base que substituiu")
    except Exception as erro:                                   # noqa: BLE001
        conferir(False, f"erro inesperado: {erro!r}")
    finally:
        D.BASE_CONSOLIDADA, D.PASTA_HISTORICO = originais

# ----------------------------------------- 8. Nomes codificados (privacidade)
secao("8. Nomes codificados de fornecedores e representantes")
original_apelidos = D.ARQUIVO_APELIDOS
with tempfile.TemporaryDirectory() as tmp:
    D.ARQUIVO_APELIDOS = Path(tmp) / "apelidos.json"
    try:
        mapas = D.apelidos(df)
        anon = D.anonimizar(df, mapas)
        forn = mapas["Nome do Fornecedor"]
        conferir(len(set(forn.values())) == len(forn) == df["Nome do Fornecedor"].nunique(),
                 f"{len(forn)} fornecedores com códigos distintos")
        lider = df.groupby("Nome do Fornecedor")["valor_pedido"].sum().idxmax()
        conferir(forn[lider.strip()] == "Fornecedor A", "Fornecedor A é o de maior valor comprado")
        visiveis = set(anon["Nome do Fornecedor"]) | set(anon["Representante"].astype(str))
        conferir(not visiveis & (set(forn) | set(mapas["Representante"])),
                 "nenhum nome original aparece na base exibida")
        conferir("CNPJ Fornecedor" not in anon.columns, "CNPJ removido da base exibida")
        conferir(round(anon["valor_pedido"].sum(), 2) == round(df["valor_pedido"].sum(), 2)
                 and M.curva_abc(anon, p).classes["itens"].tolist()
                 == M.curva_abc(df, p).classes["itens"].tolist(),
                 "valores e Curva ABC idênticos com os nomes codificados")
        # um fornecedor novo recebe o próximo código, sem mudar os já atribuídos
        extra = df.head(1).assign(**{"Nome do Fornecedor": "FORNECEDOR NOVO TESTE"})
        mapas2 = D.apelidos(pd.concat([df, extra], ignore_index=True))
        conferir(all(mapas2["Nome do Fornecedor"][k] == v for k, v in forn.items())
                 and mapas2["Nome do Fornecedor"]["FORNECEDOR NOVO TESTE"] == D._rotulo(
                     "Fornecedor", len(forn)),
                 "códigos existentes não mudam quando entra um fornecedor novo")
    except Exception as erro:                                   # noqa: BLE001
        conferir(False, f"erro inesperado: {erro!r}")
    finally:
        D.ARQUIVO_APELIDOS = original_apelidos

# ------------------------------------------------------- 9. Login e cadastro
# Testado num arquivo temporário: o dados/usuarios.json real não é alterado.
secao("9. Login e cadastro de empresas")
from core import usuarios as U      # noqa: E402

original_usuarios = U.ARQUIVO_USUARIOS
with tempfile.TemporaryDirectory() as tmp:
    U.ARQUIVO_USUARIOS = Path(tmp) / "usuarios.json"
    try:
        conferir(U.autenticar("Farmacia", "123") == "Farmacia", "acesso padrão Farmacia / 123 entra")
        conferir(U.autenticar("farmácia ", "123") == "Farmacia",
                 "nome aceito sem diferenciar maiúsculas, acento e espaços")
        conferir(U.autenticar("Farmacia", "1234") is None, "senha errada é recusada")
        conferir('"123"' not in U.ARQUIVO_USUARIOS.read_text(encoding="utf-8"),
                 "a senha não fica gravada em texto no arquivo, só o hash")
        conferir(U.cadastrar("Drogaria Teste", "abc", "abd") != "",
                 "cadastro recusado quando a confirmação difere")
        conferir(U.cadastrar("Drogaria Teste", "abc", "abc") == ""
                 and U.autenticar("Drogaria Teste", "abc") == "Drogaria Teste",
                 "empresa nova é cadastrada e consegue entrar")
        conferir(U.cadastrar("drogaria teste", "xyz", "xyz") != "",
                 "não permite cadastrar a mesma empresa duas vezes")
    except Exception as erro:                                   # noqa: BLE001
        conferir(False, f"erro inesperado: {erro!r}")
    finally:
        U.ARQUIVO_USUARIOS = original_usuarios

# ------------------------------------------------ 10. Exportação da Curva ABC
secao("10. Exportação da Curva ABC em Excel")
try:
    import io                                    # noqa: E402
    from core.exportar import curva_abc_excel    # noqa: E402
    abc_x = M.curva_abc(df, p)
    abas = pd.read_excel(io.BytesIO(curva_abc_excel(df, abc_x, p)), sheet_name=None)
    conferir(list(abas) == ["Resumo das classes", "Ranking ABC", "Parâmetros"],
             "planilha com as abas Resumo, Ranking e Parâmetros")
    conferir(len(abas["Ranking ABC"]) == abc_x.n,
             f"ranking com todos os {abc_x.n} medicamentos")
    conferir(abas["Resumo das classes"]["Medicamentos"].tolist()
             == abc_x.classes["itens"].tolist(), "contagem por classe igual à da tela")
except Exception as erro:                                       # noqa: BLE001
    conferir(False, f"erro inesperado: {erro!r}")

# ------------------------------------- 11. Preferências refletem no apoio à decisão
secao("11. Preferências e novas leituras do apoio à decisão")
from core import leituras as L    # noqa: E402

original_leituras = L.ARQUIVO_LEITURAS
with tempfile.TemporaryDirectory() as tmp:
    L.ARQUIVO_LEITURAS = Path(tmp) / "leituras.json"
    try:
        def pontos(params):
            return {i.id: (i.nivel, i.valor, round(i.impacto, 2))
                    for i in Dc.gerar(df, M.curva_abc(df, params), params)}
        base_pts = pontos(p)
        # cada régua, levada a um valor bem diferente, precisa mexer em algum ponto
        testes = {"validade_risco_meses": 12, "recorrencia_minima": 2,
                  "concentracao_fornecedor": 0.60, "pico_mensal": 2.0,
                  "alta_custo_relevante": 0.05, "margem_baixa": 0.45,
                  "prazo_pagamento_minimo": 60, "cv_y": 2.5, "pedido_minimo_folga": 0.40,
                  "corte_a": 0.70, "base_abc": "valor_pedido", "linhas_minimas": 60,
                  "razao_preco_suspeita": 1.5, "data_referencia": "2027-06-01"}
        sem_efeito = [campo for campo, valor in testes.items()
                      if pontos(PR.Parametros(**{campo: valor})) == base_pts]
        conferir(not sem_efeito, f"{len(testes)} réguas mudam o apoio à decisão"
                 + (f" (sem efeito: {', '.join(sem_efeito)})" if sem_efeito else ""))
        # nova leitura: a régua de validade muda e o painel aponta o que mudou
        p12 = PR.Parametros(validade_risco_meses=12)
        ins6, ins12 = Dc.gerar(df, abc, p), Dc.gerar(df, abc, p12)
        r6 = L.retrato(ins6, Dc.diagnostico(ins6, ind.valor_pedido), df, p, 1.0)
        r12 = L.retrato(ins12, Dc.diagnostico(ins12, ind.valor_pedido), df, p12, 1.0)
        L.registrar("teste", r6)
        mudanca = L.comparar(L.registrar("teste", r12), r12)
        conferir(mudanca and any(r[0] == "Risco de validade" for r in mudanca["reguas"])
                 and any(pt["titulo"] == "Validade dos lotes recebidos"
                         for pt in mudanca["pontos"]),
                 "nova leitura mostra a régua alterada e o ponto que mudou")
        # base com uma linha a menos simula a inclusão de cotações novas
        r_novo = L.retrato(ins12, Dc.diagnostico(ins12, ind.valor_pedido),
                           df.iloc[1:], p12, 2.0)
        mud2 = L.comparar(L.registrar("teste", r_novo), r_novo)
        conferir(mud2 and any("base de dados atualizada" in m for m in mud2["motivos"]),
                 "nova leitura reconhece base de dados atualizada")
    except Exception as erro:                                   # noqa: BLE001
        conferir(False, f"erro inesperado: {erro!r}")
    finally:
        L.ARQUIVO_LEITURAS = original_leituras

# --------------------------------- 12. Cotação nova muda o apoio à decisão
# Mesmo caminho da tela Base de Dados, numa cópia temporária da base.
secao("12. Cotação nova atualiza o apoio à decisão")
originais = (D.BASE_CONSOLIDADA, D.PASTA_HISTORICO, L.ARQUIVO_LEITURAS)
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    D.BASE_CONSOLIDADA = tmp / "base_consolidada.csv"
    D.PASTA_HISTORICO = tmp / "historico"
    L.ARQUIVO_LEITURAS = tmp / "leituras.json"
    try:
        shutil.copy(originais[0], D.BASE_CONSOLIDADA)
        antes_df, _ = D.carregar_base()
        abc_a = M.curva_abc(antes_df, p)
        ins_a = Dc.gerar(antes_df, abc_a, p)
        ret_a = L.retrato(ins_a, Dc.diagnostico(ins_a, antes_df["valor_pedido"].sum()),
                          antes_df, p, D.versao_base())
        L.registrar("[]", ret_a)

        # cotação nova: os 25 itens de maior valor, recomprados 40% mais caros
        bruto = D.ler_arquivo(D.BASE_CONSOLIDADA)
        top = antes_df.groupby("sku")["valor_pedido"].sum().nlargest(25).index
        nova = (bruto.assign(_sku=D.texto_chave(bruto["Código do Produto"]))
                     .loc[lambda d: d["_sku"].isin(top)]
                     .drop_duplicates("_sku", keep="last").drop(columns="_sku"))
        nova["Cotação"], nova["Pedido"] = 99800000, 99800001
        nova["Data de Criação"] = antes_df["dt"].max() + pd.Timedelta(days=15)
        nova["Vl. Custo (R$)"] = (nova["Vl. Custo (R$)"] * 1.40).round(2)
        nova["Vl. Faturado (R$)"] = nova["Vl. Custo (R$)"]
        caminho = tmp / "cotacao_nova.xlsx"
        nova.to_excel(caminho, index=False)

        previa = D.analisar_entrada(caminho, antes_df)
        D.mesclar(antes_df, previa.novas)
        depois_df, _ = D.carregar_base()                 # relido do disco, como o painel
        abc_d = M.curva_abc(depois_df, p)
        ins_d = Dc.gerar(depois_df, abc_d, p)
        ret_d = L.retrato(ins_d, Dc.diagnostico(ins_d, depois_df["valor_pedido"].sum()),
                          depois_df, p, D.versao_base())
        mudanca = L.comparar(L.registrar("[]", ret_d), ret_d)

        conferir(len(depois_df) == len(antes_df) + len(nova),
                 f"cotação nova incluída: {len(antes_df)} → {len(depois_df)} linhas")
        por_id = lambda ins: {i.id: (i.nivel, i.valor) for i in ins}   # noqa: E731
        pa, pd_ = por_id(ins_a), por_id(ins_d)
        mudaram = [k for k in pa if pa[k] != pd_[k]]
        conferir(len(mudaram) >= 5, f"{len(mudaram)} pontos do apoio à decisão mudaram")
        conferir(pa["m1"] != pd_["m1"] and pa["m3"] != pd_["m3"],
                 f"custos em alta {pa['m1'][1]} → {pd_['m1'][1]}; inflação da cesta "
                 f"{pa['m3'][1]} → {pd_['m3'][1]}")
        conferir(mudanca and any(f"+{len(nova)} linhas" in m for m in mudanca["motivos"]),
                 "nova leitura explica: base de dados atualizada com as linhas novas")
    except Exception as erro:                                   # noqa: BLE001
        conferir(False, f"erro inesperado: {erro!r}")
    finally:
        D.BASE_CONSOLIDADA, D.PASTA_HISTORICO, L.ARQUIVO_LEITURAS = originais

# ------------------------------------------------- 13. Previsão de compras
secao("13. Previsão de compras para o próximo mês")
try:
    from core import previsao as PV    # noqa: E402
    orc = PV.orcamento(df)
    conferir(orc["alvo"] == df["dt"].max().to_period("M") + 1,
             f"previsão para o mês seguinte à última compra ({orc['alvo']})")
    conferir(orc["faixa_min"] <= orc["media"] <= orc["faixa_max"] and len(orc["teste"]) > 0,
             f"faixa de gasto R$ {orc['faixa_min']:,.0f} a R$ {orc['faixa_max']:,.0f}"
             .replace(",", ".") + f" — acerto de {orc['acerto_faixa']:.0%} em "
             f"{len(orc['teste'])} meses testados")
    cand = PV.candidatos(df, abc, p)
    conferir(len(cand) > 0 and cand["chance"].iloc[0] == "alta"
             and (cand["meses_com_compra"] >= 2).all(),
             f"{len(cand)} candidatos, todos recorrentes, os de chance alta primeiro")
    conf = PV.resumo_confiabilidade(PV.confiabilidade(df, p))["faixas"]["taxa"]
    conferir(conf.get("alta", 0) >= conf.get("baixa", 0),
             "no histórico, a chance alta se confirma mais que a baixa "
             f"({conf.get('alta', 0):.0%} × {conf.get('baixa', 0):.0%})")
    mais_rigido = PV.candidatos(df, abc, PR.Parametros(previsao_chance_minima=0.40))
    conferir(len(mais_rigido) < len(cand), "a régua de chance mínima muda a lista de candidatos")
except Exception as erro:                                       # noqa: BLE001
    conferir(False, f"erro inesperado: {erro!r}")

# ----------------------------------------------- 14. Movimentação de estoque
secao("14. Movimentação de estoque (entradas, vendas e perdas)")
try:
    import math                            # noqa: E402
    from core import movimentacao as MV    # noqa: E402
    mov = MV.carregar()
    if mov is None:
        conferir(False, "livro de movimentação não encontrado em movimentacao/ "
                        "(SADPF_movimentacao_estoque.xlsx)")
    else:
        val = MV.validar(mov, df, p)
        falhas = val[val["resultado"] == "FALHOU"]
        conferir(falhas.empty, f"{len(val)} verificações do livro: "
                               f"{int((val['resultado'] == 'PASSOU').sum())} aprovadas, "
                               f"{int((val['resultado'] == 'ATENÇÃO').sum())} em atenção, "
                               f"{len(falhas)} falhas"
                               + ("" if falhas.empty else " — " + "; ".join(falhas["verificacao"])))
        rec = MV.recortar(mov)
        pos = MV.posicao(rec, p)
        res = MV.resumo(rec, pos)
        conferir(res["estoque_unidades"] == int(mov.groupby("ean")["quantidade"].sum().sum()),
                 f"saldo final = soma dos movimentos ({res['estoque_unidades']:,} un)"
                 .replace(",", "."))
        ent = mov[mov["tipo"] == "ENTRADA"]
        # compras incluídas depois do livro (importação ou cadastro manual) ainda não
        # têm entrada; as que têm precisam bater linha a linha
        no_livro = df[df["arquivo_origem"].astype(str).isin(set(ent["arquivo_origem"].astype(str)))]
        conferir(len(ent) == len(no_livro) and
                 int(ent["quantidade"].sum()) == int(no_livro["Qtde. Fat."].sum()),
                 f"entradas = linhas e unidades faturadas da base de compras "
                 f"({len(ent):,} linhas".replace(",", ".") +
                 (f"; {len(df) - len(no_livro)} incluída(s) depois do livro)"
                  if len(df) > len(no_livro) else ")"))
        abc_v = MV.curva_abc_vendas(pos, p)
        conferir(abs(abc_v.classes["valor"].sum() - res["faturamento"]) < 0.01 and
                 abc_v.classes.set_index("classe").loc["A", "pct_valor"] >= p.corte_a - 0.01,
                 f"Curva ABC por vendas: A {int(abc_v.classes.loc[0, 'itens'])} itens com "
                 f"{abc_v.classes.loc[0, 'pct_valor']:.1%} do faturamento".replace(".", ","))
        repor = pos[pos["repor_agora"]]
        conferir((repor["estoque_atual"] <= repor["ponto_pedido"]).all() and
                 (pos["qtd_sugerida"] >= 0).all(),
                 f"ponto de pedido coerente: {len(repor)} itens a repor agora")
        mais_seguro = MV.posicao(rec, PR.Parametros(mov_nivel_servico=0.99))
        conferir(mais_seguro["estoque_seguranca"].sum() >= pos["estoque_seguranca"].sum(),
                 "nível de serviço maior aumenta o estoque de segurança")
        pv = MV.previsao_vendas(rec)
        conferir(pv["melhor"] is not None and pv["previsao"] > 0,
                 f"previsão de vendas testada no histórico ({pv['melhor']}, erro mediano "
                 f"{pv['erro_mediano']:.0%})")
        ins_mov = Dc.gerar(df, abc, p, MV.para_decisao(rec, mov, p))
        novos = [i for i in ins_mov if i.categoria == "movimentacao"]
        conferir(len(ins_mov) == 26 and all(i.simulado for i in novos),
                 f"apoio à decisão com movimentação: {len(ins_mov)} pontos, "
                 f"{len(novos)} marcados como venda simulada")
        diag = Dc.diagnostico(ins_mov, ind.valor_pedido)
        conferir(diag["maior_exposicao"] is None or not diag["maior_exposicao"].simulado,
                 "o destaque de maior exposição continua vindo de dado real")
        so_generico = MV.recortar(mov, MV.eans_do_recorte(df[df["Categoria Comercial"] ==
                                                             "Genérico"]))
        conferir(0 < so_generico.mov["ean"].nunique() < mov["ean"].nunique(),
                 "filtros globais limitam a movimentação aos produtos do recorte")
        conferir(MV.arquivo_livro().suffix.lower() == ".csv",
                 f"fonte do livro: {MV.arquivo_livro().name}")
        soma_cat = sum(MV.resumo(r_, MV.posicao(r_, p))["faturamento"] for r_ in
                       (MV.recortar(mov, MV.eans_do_recorte(df[df["Categoria Comercial"] == c_]))
                        for c_ in df["Categoria Comercial"].unique()))
        conferir(abs(soma_cat - res["faturamento"]) < 0.01,
                 "filtro de categoria: as categorias somam o faturamento total")
        meio = pd.Timestamp("2025-06-30")
        f1 = MV.resumo(r1 := MV.recortar(mov, None, None, meio), MV.posicao(r1, p))["faturamento"]
        f2 = MV.resumo(r2 := MV.recortar(mov, None, meio + pd.Timedelta(days=1)),
                       MV.posicao(r2, p))["faturamento"]
        conferir(abs(f1 + f2 - res["faturamento"]) < 0.01,
                 "filtro de período: dois intervalos vizinhos somam o total")
        rs = MV.resumo_sazonal(MV.sazonalidade(rec))
        resp = rs[rs["classe"].str.startswith("Respirat")]
        derm = rs[rs["classe"].str.startswith("Dermat")]
        conferir(len(resp) and resp["inverno_verao"].iloc[0] > 1.2 and
                 (derm.empty or derm["inverno_verao"].iloc[0] < 1),
                 "sazonalidade como a literatura espera: respiratórios inverno ÷ verão "
                 f"{resp['inverno_verao'].iloc[0]:.2f}".replace(".", ",") +
                 (f"; dermatológicos {derm['inverno_verao'].iloc[0]:.2f}".replace(".", ",")
                  if len(derm) else ""))
        xyz = MV.xyz_vendas(rec, p)["xyz"].value_counts()
        conferir(xyz.get("X", 0) > 0 and xyz.get("Z", 0) > 0,
                 f"XYZ pelas vendas: X {xyz.get('X', 0)} · Y {xyz.get('Y', 0)} · "
                 f"Z {xyz.get('Z', 0)}")
        lote = MV.lote_economico(pos, rec, p)
        teto = (lote["demanda_anual"] / 365 * p.mov_cobertura_excesso).clip(lower=1)
        conferir((lote["lec"].fillna(0) <= teto.apply(math.ceil) + 0.001).all() and
                 (lote["estoque_maximo"].fillna(0) >= lote["estoque_minimo"].fillna(0)).all(),
                 "lote econômico limitado pela cobertura máxima e mínimo ≤ máximo")
        politicas = pos["politica"].value_counts()
        conferir(set(pos.loc[pos["repor_agora"], "politica"]) <= {"ponto de pedido"} and
                 pos["fator_sazonal"].between(0.6, 1.6).all(),
                 "sugestão de compra só para itens de ponto de pedido; fator sazonal "
                 "entre 0,6 e 1,6 · " + " · ".join(f"{k} {v}" for k, v in politicas.items()))
        teto_compra = (pos["demanda_prevista"] * p.mov_cobertura_excesso).apply(math.ceil)
        conferir((pos["qtd_sugerida"] <= teto_compra + 1).all(),
                 f"nenhuma sugestão passa de {p.mov_cobertura_excesso} dias de demanda")
        serra = MV.dente_serra_modelo(2.0, 60, 10, 24, 7, pd.Timestamp("2025-01-01"), 120)
        conferir(serra["saldo"].min() >= 10 - 0.001 and serra["saldo"].max() <= 70 + 0.001
                 and serra["pedido"].sum() >= 3,
                 f"dente de serra do modelo oscila entre o mínimo e o máximo "
                 f"({int(serra['pedido'].sum())} pedidos em 120 dias)")
        td = MV.teste_demanda(rec, p)
        conferir(not td.empty and {"wape", "wape_media", "wape_ingenuo"} <= set(td.columns),
                 f"teste da demanda: erro (WAPE) sazonal {td['wape'].mean():.0%}, média "
                 f"simples {td['wape_media'].mean():.0%}, ingênuo {td['wape_ingenuo'].mean():.0%}")
        from core.tema import selo_natureza
        estimados = [i.id for i in ins_mov if i.natureza == "estimado"]
        conferir(all(i.natureza in ("real", "estimado") for i in ins_mov) and
                 {"o1", "m1", "e1", "v4", "v5"} <= set(estimados) and
                 selo_natureza("real") == "" and selo_natureza("simulado") == "" and
                 selo_natureza("estimado") != "",
                 f"selos: só valores estimados ou projetados são marcados na tela "
                 f"({len(estimados)} pontos estimados: {', '.join(estimados)})")
        conferir(abs(pt_ := MV.ponte_estoque(rec)["diferenca"]) < 0.01,
                 "ponte do estoque fecha: partida + compras − custo vendido − perdas = chegada "
                 f"(diferença R$ {pt_:.2f})".replace(".", ","))
        prop = MV.propostas_validade(rec, p)
        remarca = prop[prop["acao"] == "Remarcar"]
        conferir(len(prop) > 0 and (remarca["preco_proposto"] >= remarca["custo"] * 1.08 - 0.005).all()
                 and (remarca["desconto_pct"] <= 0.6 + 1e-9).all()
                 and (prop.loc[prop["dias_para_vencer"] >= 120, "acao"]
                      .isin(["Devolver ao fornecedor", "Devolver ou baixa controlada"])).all(),
                 f"propostas por lote calculadas pelo sistema: {len(prop)} lotes · "
                 + " · ".join(f"{a.lower()} {n}" for a, n in prop["acao"].value_counts().items()))
        ref = MV.referencias(rec, pos, res, MV.curva_abc_vendas(pos, p), p)
        conferir(len(ref) >= 8 and ref["leitura"].isin(["dentro", "acima", "abaixo"]).all(),
                 f"{len(ref)} indicadores comparados com a literatura: "
                 f"{int((ref['leitura'] == 'dentro').sum())} dentro da faixa")
        causas = MV.causas_perdas(rec, df)
        conferir(abs(causas["valor"].sum() - res["perda_valor"]) < 0.01
                 and causas["causa"].isin(MV.CAUSAS_PERDA).all(),
                 "causas das perdas: cada perda tem um único fator e a soma fecha com a "
                 f"perda do período ({MV._brl(causas['valor'].sum())})")
        pf = MV.projecao_fechamento(rec)
        conferir(bool(pf) and pf["curso"]["vendas"] >= pf["realizado"]["vendas"] - 0.01
                 and abs(pf["proximo"]["vendas"]
                         - pf["ritmo_diario"] * pf["proximo_mes"].days_in_month) < 0.01,
                 f"projeção de fechamento: {pf['mes']} = realizado "
                 f"{MV._brl(pf['realizado']['vendas'])} + ritmo × {pf['faltam']} dias "
                 f"→ {MV._brl(pf['curso']['vendas'])}")
        serie_t = pd.Series({pd.Period("2025-06", "M"): 100.0, pd.Period("2026-05", "M"): 80.0,
                             pd.Period("2026-06", "M"): 120.0})
        cmp_ = M.comparar_mes(serie_t, pd.Period("2026-06", "M"))
        conferir(abs(cmp_["var_mes"] - 0.5) < 1e-9 and abs(cmp_["var_ano"] - 0.2) < 1e-9
                 and M.mes_referencia(pd.Timestamp("2026-07-08")) == pd.Period("2026-06", "M"),
                 "comparativos: mês fechado de referência, +50% vs mês anterior e "
                 "+20% vs mesmo mês do ano anterior no caso-teste")
        mapas = D.apelidos(df)
        anon = MV.anonimizar(mov, mapas)
        reais = set(df["Nome do Fornecedor"].astype(str).str.strip())
        conferir(not (set(anon["Nome do Fornecedor"].dropna()) & reais),
                 "fornecedores da movimentação aparecem codificados")
except Exception as erro:                                       # noqa: BLE001
    conferir(False, f"erro inesperado: {erro!r}")

# ------------------------------------------------- 15. Cadastro manual
# Também numa cópia temporária: a base real em dados/ não é alterada.
secao("15. Cadastro manual de compras (simulado numa cópia da base)")
from core import cadastro as CD    # noqa: E402
originais = (D.BASE_CONSOLIDADA, D.PASTA_HISTORICO)
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    D.BASE_CONSOLIDADA = tmp / "base_consolidada.csv"
    D.PASTA_HISTORICO = tmp / "historico"
    try:
        shutil.copy(originais[0], D.BASE_CONSOLIDADA)
        base, _ = D.carregar_base()
        ult = base.sort_values("dt").iloc[-1]
        prod = base[base["sku"] != ult["sku"]].sort_values("dt").iloc[-1]
        dia = (ult["dt"] + pd.Timedelta(days=3)).normalize()
        pedido = {"Cotação": 99000001, "Pedido": 99000002, "Status do Pedido": "Faturado",
                  "Data de Criação": dia, "CNPJ Fornecedor": int(ult["CNPJ Fornecedor"]),
                  "Nome do Fornecedor": ult["Nome do Fornecedor"],
                  "Representante": ult["Representante"],
                  "Prazo de Pagamento": 30, "Faturamento Mínimo": 300.0}

        def item(fonte, **troca):
            i = {c: fonte[c] for c in ["Código do Produto", "EAN", "Descrição do Produto",
                                       "Fabricante", "Forma Farmacêutica",
                                       "Categoria Comercial", "M/L"]}
            i.update({"Qtde. Cot": 10, "Qtde. Resp": 10, "Qtde. Ped.": 10, "Qtde. Fat.": 10,
                      "Desc. Com. (%)": 0.0, "Vl. Custo (R$)": 5.0, "Vl. Faturado (R$)": None,
                      "Preço de Venda Unitário (R$)": 9.0, "Lote": "TESTE0001",
                      "Data de Fabricação": dia - pd.Timedelta(days=200),
                      "Data de Validade": dia + pd.Timedelta(days=700)})
            i.update(troca)
            return i
        linhas = CD.montar_linhas(pedido, [item(ult), item(prod, **{"Lote": "TESTE0002"})])
        val = CD.validar(linhas, base, hoje=dia.date())
        conferir(val.ok and linhas["Faixa de Recebimento"].eq("Fresco (≥70%)").all() and
                 (linhas["Qtde. Ped. x Vl. Custo (R$)"] == 50.0).all(),
                 "pedido válido: sem erros, faixa de recebimento e valor calculados")
        nova = D.mesclar(base, linhas)
        recarregada, _ = D.carregar_base()
        conferir(len(recarregada) == len(base) + 2 and
                 abs(M.indicadores(recarregada).valor_pedido -
                     M.indicadores(base).valor_pedido - 100.0) < 0.01 and
                 len(D.versoes_anteriores()) == 1,
                 "gravado pelo mesmo caminho da importação: +2 linhas, +R$ 100 no valor "
                 "pedido, cópia da base anterior guardada")
        conferir(not CD.validar(linhas, recarregada).ok,
                 "o mesmo pedido de novo é recusado (cotação + pedido + produto)")
        casos = {
            "linha repetida no próprio cadastro": [item(ult), item(ult)],
            "quantidade pedida zero": [item(ult, **{"Qtde. Ped.": 0})],
            "respondida maior que a cotada": [item(ult, **{"Qtde. Resp": 20})],
            "validade antes da fabricação": [item(ult, **{"Data de Validade":
                                                          dia - pd.Timedelta(days=300)})],
            "lote já vencido na chegada": [item(ult, **{"Data de Validade":
                                                        dia - pd.Timedelta(days=1)})],
            "custo zero": [item(ult, **{"Vl. Custo (R$)": 0})],
            "código com outro EAN": [item(ult, EAN=7891234567895)],
            "EAN inválido em produto novo": [item(ult, **{"Código do Produto": "NOVO-1",
                                                          "EAN": 7891234567890})],
            "categoria fora da lista": [item(ult, **{"Categoria Comercial": "Outra"})],
            "status descartado pela limpeza": "status",
            "CNPJ inválido": "cnpj",
            "cotação existente com outra data": "data",
        }
        recusados = 0
        for nome, itens_teste in casos.items():
            ped = dict(pedido, Pedido=99000003)
            if itens_teste == "status":
                ped["Status do Pedido"], itens_teste = "Cancelado", [item(ult)]
            elif itens_teste == "cnpj":
                ped["CNPJ Fornecedor"], itens_teste = 12345678000100, [item(ult)]
            elif itens_teste == "data":
                ped["Cotação"], itens_teste = int(ult["Cotação"]), [item(ult)]
                ped["Data de Criação"] = ult["dt"] - pd.Timedelta(days=40)
            v = CD.validar(CD.montar_linhas(ped, itens_teste), recarregada, hoje=dia.date())
            recusados += not v.ok
            if v.ok:
                conferir(False, f"cadastro com {nome} deveria ser recusado")
        conferir(recusados == len(casos), f"{recusados} de {len(casos)} cadastros inválidos "
                                          "recusados (duplicidade, quantidades, datas, valores, "
                                          "EAN, CNPJ, categoria, status, data da cotação)")
        conferir(CD.cnpj_valido(int(ult["CNPJ Fornecedor"])) and CD.ean_valido(ult["EAN"]) and
                 not CD.cnpj_valido("11111111111111") and not CD.ean_valido("7891234567890"),
                 "dígitos verificadores de CNPJ e EAN")
    except Exception as erro:                                       # noqa: BLE001
        conferir(False, f"erro inesperado no cadastro manual: {erro!r}")
    finally:
        D.BASE_CONSOLIDADA, D.PASTA_HISTORICO = originais

# ------------------------------------------- 16. Cores acessíveis e coerência das telas
secao("16. Cores acessíveis (daltonismo e contraste) e coerência entre telas")
try:
    from core import acessibilidade as AC     # noqa: E402
    from core.tema import PALETA, cascata     # noqa: E402
    claro, escuro = PALETA["claro"], PALETA["escuro"]
    d, tipo = AC.menor_distancia(claro["green"], claro["red"])
    conferir(d >= 15, f"verde × laranja distinguíveis nos 3 tipos de daltonismo "
                      f"(menor ΔE00 = {d:.1f}, em {tipo})")
    # total (azul-escuro) e neutro (azul-claro) contra verde e laranja, nos daltonismos
    # comuns (protanopia e deuteranopia, mais de 99% dos casos). Na tritanopia (~0,01%)
    # o azul dos totais fica perto do verde; os totais partem do zero e têm rótulo próprio
    comuns = ("protanopia", "deuteranopia")
    for cor in ("total", "neutro"):
        piores = [AC.distancia(claro[cor], claro[x], t) for x in ("green", "red")
                  for t in comuns + (None,)]
        conferir(min(piores) >= 10, f"'{cor}' da cascata se distingue de verde e laranja na "
                                    f"visão comum, em protanopia e em deuteranopia (menor "
                                    f"ΔE00 = {min(piores):.1f})")
    textos = {"green": claro["green"], "red": claro["red"], "amber_t": claro["amber_t"]}
    conferir(all(AC.contraste(v) >= 4.5 for v in textos.values()),
             "texto verde, laranja e âmbar com contraste ≥ 4,5:1 no fundo branco ("
             + ", ".join(f"{k} {AC.contraste(v):.1f}" for k, v in textos.items()) + ")")
    conferir(all(AC.contraste(escuro[k], escuro["surface"]) >= 4.5 for k in ("green", "red")),
             "no tema escuro, verde e laranja com contraste ≥ 4,5:1")
    antigo = AC.menor_distancia("#4D8A70", "#B5625B")[0]
    conferir(d > 1.5 * antigo, f"paleta nova separa bom × ruim {d / antigo:.1f}× mais que a "
                               f"anterior (ΔE00 {antigo:.1f} → {d:.1f})")

    # cascata: cada passo parte de onde o anterior terminou e o total fecha
    passos = [("Vendas", 1000.0, "total", "total", ""), ("Custo", 600.0, "subtrai", "neutro", ""),
              ("Perdas", 50.0, "subtrai", "ruim", ""), ("Ganho", 80.0, "soma", "bom", "estimado"),
              ("Resultado", 430.0, "total", "total", "")]
    barras = cascata(passos, "teste").data[0]
    fim_ganho = barras.base[3] + barras.x[3]
    cores_b = list(barras.marker.color)
    claros = [c_ != l_ for c_, l_ in zip(cores_b, barras.marker.line.color)]
    conferir(abs(fim_ganho - 430.0) < 1e-9 and claros == [False, False, False, True, False]
             and barras.marker.pattern.shape is None and "(estimado)" in barras.y[3],
             "cascata: os passos encadeados chegam ao total; só o estimado tem tom claro e "
             "'(estimado)' no rótulo, sem hachura")

    # tendências: direção pela média do último trimestre contra o anterior
    from paginas.compras import _tendencia                            # noqa: E402
    meses_t = [str(m) for m in pd.period_range("2025-07", "2026-06", freq="M")]
    serie_t = pd.Series([100.0] * 9 + [130.0] * 3, index=meses_t)
    var_t, dir_t = _tendencia(serie_t, meses_t, percentual=False)
    conferir(dir_t == "subindo" and abs(var_t - 0.30) < 1e-9,
             "tendência: trimestre 30% acima do anterior = 'subindo 30%'")

    # ficha do medicamento × apoio à decisão: a mesma economia por troca de fornecedor
    opo = M.oportunidades_fornecedor(df, p).head(25)
    difs = [abs(M.melhor_fornecedor_item(df[df["sku"] == s])["economia"] - e)
            for s, e in zip(opo["sku"], opo["economia"])]
    conferir(len(difs) > 0 and max(difs) < 0.01,
             f"ficha do medicamento: economia por troca igual à do apoio à decisão "
             f"({len(difs)} itens conferidos)")

    # Gestão de Compras: a concentração vem da Curva ABC (mesmo corte de Preferências)
    classe_a = abc.itens[abc.itens["classe"] == "A"]
    conferir(abs(classe_a["valor"].sum() / abc.total
                 - abc.classes.set_index("classe").loc["A", "pct_valor"]) < 1e-6,
             f"Gestão de Compras: {len(classe_a)} itens A = "
             f"{abc.classes.set_index('classe').loc['A', 'pct_valor']:.1%} do gasto, como na "
             "Curva ABC")

    # arquitetura: a camada de modelos (core/, menos tema e memória) não depende da interface
    import subprocess                                                  # noqa: E402
    sonda = ("import sys, importlib\n"
             "class B:\n"
             "    def find_spec(self, n, c=None, a=None):\n"
             "        if n == 'streamlit' or n.startswith('streamlit.'):\n"
             "            raise ImportError('streamlit')\n"
             "sys.meta_path.insert(0, B())\n"
             "for m in ('dados','parametros','metricas','movimentacao','previsao','decisao',"
             "'cadastro','leituras','usuarios','exportar','formato','acessibilidade'):\n"
             "    importlib.import_module('core.' + m)\n")
    camada = subprocess.run([sys.executable, "-c", sonda], cwd=Path(__file__).parent,
                            capture_output=True, text=True)
    conferir(camada.returncode == 0, "camada de modelos (core/) funciona sem o Streamlit: a "
                                     "interface pode ser trocada sem reescrever os cálculos")

    # ficha: próxima compra prevista depois da última compra
    ritmo = M.intervalo_compras(df)
    conferir(len(ritmo) > 0 and (ritmo["proxima_prevista"] > ritmo["ultima_compra"]).all(),
             f"próxima compra prevista sempre depois da última ({len(ritmo)} itens com ritmo)")
except Exception as erro:                                           # noqa: BLE001
    conferir(False, f"erro inesperado nas cores ou na coerência das telas: {erro!r}")

# ----------------------------------------------------------------- resultado
secao("Resultado")
if problemas:
    print(f"  {len(problemas)} problema(s):")
    for item in problemas:
        print(f"    - {item}")
    sys.exit(1)

print("  Tudo certo. O sistema está pronto para rodar.\n")
print("  Agora execute:  streamlit run app.py")
print("  O navegador abre em http://localhost:8501")
print("  Para parar, volte ao terminal e pressione Ctrl+C\n")
