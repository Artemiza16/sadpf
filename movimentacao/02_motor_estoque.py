#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SADPF — Módulo 2: Motor de movimentação de estoque
===================================================
Gera, a partir da base_consolidada.csv (dados REAIS de compra):

  1. ESTOQUE_INICIAL  — posição simulada em 01/10/2024 (anterior aos pedidos)
  2. ENTRADA          — dados REAIS dos pedidos faturados
  3. SAIDA_VENDA      — vendas simuladas, com consumo FEFO e saldo nunca negativo
  4. PERDA_VALIDADE   — baixa simulada de lotes vencidos em estoque
  5. Saldo corrente   — estoque inicial + entradas − saídas − perdas

Toda linha do ledger carrega `origem_dado` (REAL | SIMULADO) e, quando REAL,
`arquivo_origem` + `linha_origem` para rastrear até a planilha de cotação.
"""

import sys
import os
import random
import string
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util

_spec = importlib.util.spec_from_file_location(
    'clf', os.path.join(os.path.dirname(os.path.abspath(__file__)), '01_classificadores.py'))
clf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clf)

# ===========================================================================
# PARÂMETROS DA SIMULAÇÃO  (todos explícitos e auditáveis)
# ===========================================================================
SEED = 42

ENTRADA_CSV = '/mnt/user-data/uploads/base_consolidada.csv'
DIR_SAIDA = '/mnt/user-data/outputs'

# Estoque inicial posicionado 30 dias antes do primeiro pedido real
DIAS_ANTES_PRIMEIRO_PEDIDO = 30

# Um produto entra no estoque inicial se:
#   - foi comprado 2+ vezes no período (item de giro recorrente), OU
#   - foi comprado 1 vez dentro dos primeiros N meses (já era de linha)
MESES_JANELA_ITEM_DE_LINHA = 6
PROB_ITEM_LINHA_COMPRA_UNICA = 0.70

# Estoque inicial = média da qtde comprada x fator aleatório nesta faixa
FAIXA_FATOR_ESTOQUE_INICIAL = (0.50, 1.40)

# ---------------------------------------------------------------------------
# CALIBRAÇÃO DA DEMANDA — por ciclo de reposição
#
# A base real informa quando a farmácia voltou a comprar cada produto e quanto
# comprou. Esse par é um sinal direto de consumo: se ela comprou 24 unidades e
# retornou 60 dias depois, consumiu aproximadamente 24 unidades em 60 dias. A
# razão entre a quantidade e o intervalo é, portanto, a taxa de consumo que a
# própria operação revela — 0,082 unidade por dia na mediana da base, com ciclo
# mediano de 104 dias.
#
# A versão anterior do motor usava uma taxa única por produto para todo o
# período, calibrada para consumir uma fração do estoque total. O diagnóstico
# mostrou que isso não reproduz o comportamento de um estoque real: 51% das
# compras chegavam com saldo zerado e 22% com mais de 180 dias de cobertura,
# e 18 dos 200 maiores produtos passavam mais de 180 dias seguidos em ruptura.
# A média anulava justamente o ritmo que os dados revelavam.
#
# A calibração por ciclo usa a taxa local de cada intervalo entre compras, o
# que produz o dente de serra característico do estoque: sobe na entrada, desce
# no consumo, e a próxima compra chega quando o saldo está baixo.
# ---------------------------------------------------------------------------

# Fração da quantidade recebida que se espera consumir até a próxima compra.
# Abaixo de 1,00 o estoque acumula lentamente ao longo do período, que é o
# comportamento observado (estoque final acima do inicial).
FATOR_CONSUMO_CICLO = 1.03

# Teto da taxa de um ciclo, em múltiplos da taxa típica do próprio produto.
# Protege contra o intervalo curto demais: duas compras separadas por poucos
# dias implicariam consumo absurdo se tomadas ao pé da letra.
#
# Não há piso, e isso é deliberado. Um hiato longo entre compras significa que
# a farmácia não precisou repor, e a taxa baixa que dele resulta é o próprio
# dado falando. A primeira versão impunha piso de 0,35 da taxa típica e foi a
# causa das rupturas de centenas de dias: no TORSILAX, por exemplo, um hiato de
# 496 dias revela consumo de 0,013 unidade por dia, mas o piso o elevava a
# 0,072 — cinco vezes mais —, esvaziando a prateleira em 83 dias e deixando o
# item 413 dias zerado.
TETO_TAXA_CICLO = 2.80

# Trechos de borda — antes da primeira compra e depois da última — não têm uma
# chegada seguinte que revele o ritmo, e por isso precisam de teto próprio.
#
# No trecho final, a AUSÊNCIA de nova compra é informação: se a farmácia não
# repôs o item por mais um ciclo, é porque não precisou. Projetar a taxa de
# ciclo sobre um hiato longo esvazia o estoque e produz rupturas de centenas de
# dias, que foi exatamente o defeito medido na primeira tentativa de calibração
# local. O consumo do trecho final fica, então, limitado ao que chegou na
# última compra.
#
# No trecho de abertura, o teto preserva parte do saldo inicial, de modo que a
# primeira reposição encontre a prateleira baixa, e não vazia.
TETO_CONSUMO_TRECHO_FINAL = 1.20    # fração da última quantidade recebida
TETO_CONSUMO_ABERTURA = 0.80        # fração do estoque de abertura

# Produtos comprados uma única vez não têm intervalo entre compras e, portanto,
# não revelam taxa. Para eles mantém-se a calibração por fração do recebido,
# espalhada pelos dias restantes: são itens de giro esporádico.
FRACAO_VENDIDA_ESPORADICO = 0.70

# Deriva mensal de preço (IPCA-like) aplicada ao preço de venda da base
DERIVA_PRECO_MENSAL = 0.0037          # ~4,5% a.a.

# Piso operacional de margem bruta sobre o custo DO LOTE vendido.
# Justificativa: o preço precisa cobrir a tributação sobre a receita (Simples
# Nacional, faixa de comércio: 4% a 11%) e a taxa de meio de pagamento (~2,5%)
# antes de sobrar contribuição. Abaixo de ~18% a venda destrói resultado.
# Sem este piso, o FEFO pode consumir um lote mais caro que o preço de
# referência do produto (que vem da última compra), gerando margem negativa.
MARGEM_MINIMA_OPERACIONAL = 0.18

# Validade dos lotes do estoque inicial (mesma regra da base consolidada)
DIAS_VALIDADE_OPCOES = np.array([500, 750, 1200])
DIAS_VALIDADE_PESOS = np.array([0.089, 0.582, 0.329])
DIAS_VALIDADE_PESOS = DIAS_VALIDADE_PESOS / DIAS_VALIDADE_PESOS.sum()

PREFIXOS_LOTE = [
    'PH', 'AZ', 'KL', 'AI', 'LE', 'EM', 'VI', 'CE', 'GE', 'ME',
    'RA', 'NE', 'TE', 'AR', 'SO', 'BE', 'MU', 'EU', 'BL', 'AL',
    'MA', 'PA', 'HI', 'CA', 'BR', 'NO', 'TU', 'ZA', 'XA', 'DI',
]

EPOCH_EXCEL = datetime(1899, 12, 30)


# ===========================================================================
# UTILITÁRIOS
# ===========================================================================
def excel_para_data(serial):
    return EPOCH_EXCEL + timedelta(days=float(serial))


def data_para_excel(dt):
    return int((dt - EPOCH_EXCEL).days)


def gerar_lote(data_fabricacao, rng):
    """Lote no padrão CCNNNNXXX: 2 letras + MMAA da fabricação + 3 alfanuméricos."""
    prefixo = PREFIXOS_LOTE[rng.integers(0, len(PREFIXOS_LOTE))]
    mes_ano = data_fabricacao.strftime('%m%y')
    alfabeto = string.ascii_uppercase + string.digits
    sufixo = ''.join(alfabeto[i] for i in rng.integers(0, len(alfabeto), 3))
    return f'{prefixo}{mes_ano}{sufixo}'


def calcular_taxas_locais(eventos_suprimento, data_fim):
    """
    Converte o calendário de suprimento de um produto em taxas diárias de
    demanda, uma por ciclo de reposição.

    `eventos_suprimento` é a lista ordenada de (data, quantidade) com o estoque
    inicial, quando existe, e cada compra faturada.

    A taxa de um ciclo é a quantidade que chegou dividida pelos dias até a
    próxima chegada: é o consumo que a farmácia revela ao voltar a comprar. O
    estoque inicial não entra nesse cálculo, porque é saldo de abertura e não
    quantidade de ciclo — durante o intervalo que o antecede aplica-se a taxa
    típica do produto.

    Devolve [(data_inicio, data_fim_inclusive, lambda_diario), ...] cobrindo
    toda a janela do produto.
    """
    if not eventos_suprimento:
        return []

    eventos = sorted(eventos_suprimento, key=lambda e: e[0])

    # --- taxas reveladas pelos intervalos entre COMPRAS -------------------
    compras = [e for e in eventos if e[2] == 'COMPRA']
    taxas_reveladas = []
    for i in range(len(compras) - 1):
        dias = (compras[i + 1][0] - compras[i][0]).days
        if dias > 0:
            taxas_reveladas.append(compras[i][1] / dias)

    if taxas_reveladas:
        taxa_tipica = float(np.median(taxas_reveladas))
    else:
        # Produto de compra única: não há ciclo. Espalha a fração esperada
        # pelos dias restantes a partir da primeira chegada.
        qtd = sum(e[1] for e in eventos)
        dias = max((data_fim - eventos[0][0]).days + 1, 1)
        taxa_tipica = qtd * FRACAO_VENDIDA_ESPORADICO / dias

    if taxa_tipica <= 0:
        return []

    lim_max = taxa_tipica * TETO_TAXA_CICLO

    # --- uma taxa por trecho ---------------------------------------------
    trechos = []
    for i, (data, qtd, tipo) in enumerate(eventos):

        if i + 1 < len(eventos):
            # Trecho interno: a próxima chegada revela o ritmo de consumo.
            fim_trecho = eventos[i + 1][0] - timedelta(days=1)
            dias = max((eventos[i + 1][0] - data).days, 1)

            if tipo == 'COMPRA':
                lam = min(qtd * FATOR_CONSUMO_CICLO / dias, lim_max)
            else:
                # Abertura: o saldo inicial é reserva, não lote de reposição.
                # Consome-se no ritmo típico, sem exaurir o saldo antes da
                # primeira entrada.
                lam = min(taxa_tipica, qtd * TETO_CONSUMO_ABERTURA / dias)
        else:
            # Trecho final: não há próxima compra. Projetar a taxa típica
            # sobre um hiato longo esvaziaria o estoque, então o consumo do
            # trecho é limitado ao que chegou na última entrada.
            fim_trecho = data_fim
            dias = max((data_fim - data).days + 1, 1)
            teto = (qtd * TETO_CONSUMO_TRECHO_FINAL / dias if tipo == 'COMPRA'
                    else qtd * TETO_CONSUMO_ABERTURA / dias)
            lam = min(taxa_tipica, teto)

        if fim_trecho >= data and lam > 0:
            trechos.append((data, fim_trecho, lam))

    return trechos


def classificar_faixa_recebimento(dias_totais_validade):
    if dias_totais_validade >= 730:
        return 'Fresco (≥70%)'
    if dias_totais_validade >= 600:
        return 'Normal (50-70%)'
    if dias_totais_validade >= 500:
        return 'Curto (30-50%)'
    return 'Crítico (<30%)'


def _arredondar_x9(preco):
    """Arredonda para o padrão .x9 praticado no varejo farmacêutico."""
    p = round(float(preco) + 1e-9, 4)
    centavos = np.floor(p * 10) / 10
    return round(centavos + 0.09, 2) if centavos >= 0.1 else round(max(p, 0.10), 2)


def preco_com_deriva(preco_base, data_ref, data_mov, custo_lote=None):
    """
    Preço praticado na venda.

    Parte do preço de venda da base, aplica a deriva mensal e então impõe o
    piso de margem mínima sobre o custo do LOTE efetivamente vendido. O piso é
    necessário porque o preço de referência vem da última compra do produto,
    enquanto o FEFO pode estar consumindo um lote adquirido a custo maior.
    """
    meses = (data_mov.year - data_ref.year) * 12 + (data_mov.month - data_ref.month)
    preco = preco_base * ((1 + DERIVA_PRECO_MENSAL) ** max(meses, 0))
    preco = _arredondar_x9(preco)

    if custo_lote is not None and custo_lote > 0:
        piso = _arredondar_x9(custo_lote * (1 + MARGEM_MINIMA_OPERACIONAL))
        if preco < piso:
            return piso, True       # preço elevado ao piso de margem
    return preco, False


# ===========================================================================
# 1. CARGA E PREPARO DA BASE REAL
# ===========================================================================
def carregar_base():
    print('[1/6] Carregando base consolidada (dados REAIS)...')
    df = pd.read_csv(ENTRADA_CSV, sep=';', encoding='utf-8')

    colunas_numericas = [
        'Data de Criação', 'Faturamento Mínimo', 'Desc. Com. (%)',
        'Vl. Custo (R$)', 'Vl. Faturado (R$)', 'Qtde. Ped. x Vl. Custo (R$)',
        'Preço de Venda Unitário (R$)',
    ]
    for col in colunas_numericas:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
            errors='coerce')

    df['data_pedido'] = df['Data de Criação'].apply(excel_para_data).dt.normalize()
    df['classe_terapeutica'] = [
        clf.classificar_classe_terapeutica(d, f)
        for d, f in zip(df['Descrição do Produto'], df['Forma Farmacêutica'])
    ]

    print(f'      {len(df):,} registros | {df["EAN"].nunique():,} produtos (EAN) | '
          f'{df["data_pedido"].min():%d/%m/%Y} a {df["data_pedido"].max():%d/%m/%Y}')
    return df


# ===========================================================================
# 2. CADASTRO DE PRODUTOS (chave = EAN)
# ===========================================================================
def montar_cadastro(df):
    print('[2/6] Montando cadastro de produtos...')

    def agrega(g):
        ultimo = g.sort_values('data_pedido').iloc[-1]
        return pd.Series({
            'Código do Produto': ultimo['Código do Produto'],
            'Descrição do Produto': ultimo['Descrição do Produto'],
            'Fabricante': ultimo['Fabricante'],
            'Forma Farmacêutica': ultimo['Forma Farmacêutica'],
            'Categoria Comercial': ultimo['Categoria Comercial'],
            'classe_terapeutica': ultimo['classe_terapeutica'],
            'n_compras': len(g),
            'qtd_total_comprada': int(g['Qtde. Fat.'].sum()),
            'qtd_media_compra': float(g['Qtde. Fat.'].mean()),
            'custo_medio': float(g['Vl. Custo (R$)'].mean()),
            'custo_ultimo': float(ultimo['Vl. Custo (R$)']),
            'preco_venda_base': float(ultimo['Preço de Venda Unitário (R$)']),
            'data_preco_ref': ultimo['data_pedido'],
            'primeira_compra': g['data_pedido'].min(),
            'ultima_compra': g['data_pedido'].max(),
            'fornecedor_principal': g['Nome do Fornecedor'].mode().iloc[0],
        })

    cad = df.groupby('EAN', sort=False).apply(agrega, include_groups=False).reset_index()
    print(f'      {len(cad):,} produtos no cadastro')
    return cad


# ===========================================================================
# 3. ESTOQUE INICIAL (SIMULADO)
# ===========================================================================
def gerar_estoque_inicial(cad, data_corte, rng):
    print(f'[3/6] Gerando estoque inicial simulado em {data_corte:%d/%m/%Y}...')

    limite_item_linha = data_corte + pd.DateOffset(months=MESES_JANELA_ITEM_DE_LINHA)
    registros = []

    for _, p in cad.iterrows():
        recorrente = p['n_compras'] >= 2
        compra_unica_precoce = (
            p['n_compras'] == 1
            and p['primeira_compra'] <= limite_item_linha
            and rng.random() < PROB_ITEM_LINHA_COMPRA_UNICA
        )
        if not (recorrente or compra_unica_precoce):
            continue   # produto introduzido depois: não existia no estoque inicial

        fator = rng.uniform(*FAIXA_FATOR_ESTOQUE_INICIAL)
        qtd = int(round(p['qtd_media_compra'] * fator))
        if qtd < 1:
            continue

        # Lote do estoque inicial: fabricado antes da data de corte
        dias_desde_fab = int(rng.integers(30, 420))
        data_fab = (data_corte - timedelta(days=dias_desde_fab)).replace(day=1)
        dias_validade = int(rng.choice(DIAS_VALIDADE_OPCOES, p=DIAS_VALIDADE_PESOS)
                            + rng.integers(-15, 16))
        data_val = data_fab + timedelta(days=dias_validade)

        registros.append({
            'EAN': p['EAN'],
            'quantidade': qtd,
            'Lote': gerar_lote(data_fab, rng),
            'Data de Fabricação': data_fab,
            'Data de Validade': data_val,
            'dias_validade_total': dias_validade,
            'Faixa de Recebimento': classificar_faixa_recebimento(dias_validade),
            'custo_unitario': round(p['custo_medio'], 2),
        })

    est = pd.DataFrame(registros)
    print(f'      {len(est):,} produtos com estoque inicial | '
          f'{est["quantidade"].sum():,} unidades | '
          f'R$ {(est["quantidade"] * est["custo_unitario"]).sum():,.2f} em custo')
    return est


# ===========================================================================
# 4. MOTOR DE MOVIMENTAÇÃO — FEFO com restrição de saldo
# ===========================================================================
class ControleEstoque:
    """Controla os lotes de um produto e consome por FEFO (vence primeiro, sai primeiro)."""

    def __init__(self):
        self.lotes = []   # dicts: lote, validade, qtd, custo, origem

    @property
    def saldo(self):
        return sum(l['qtd'] for l in self.lotes)

    def entrar(self, lote, validade, qtd, custo, origem):
        self.lotes.append({'lote': lote, 'validade': validade, 'qtd': int(qtd),
                           'custo': float(custo), 'origem': origem})

    def baixar_vencidos(self, data):
        """Remove lotes vencidos e devolve o que foi baixado."""
        vencidos, mantidos = [], []
        for l in self.lotes:
            if l['validade'] < data and l['qtd'] > 0:
                vencidos.append(l)
            else:
                mantidos.append(l)
        self.lotes = mantidos
        return vencidos

    def consumir(self, qtd_desejada):
        """Consome por FEFO. Devolve a lista (lote, qtd, custo) efetivamente retirada."""
        restante = min(int(qtd_desejada), self.saldo)
        if restante <= 0:
            return []
        retirado = []
        for l in sorted(self.lotes, key=lambda x: x['validade']):
            if restante <= 0:
                break
            if l['qtd'] <= 0:
                continue
            usa = min(l['qtd'], restante)
            l['qtd'] -= usa
            restante -= usa
            retirado.append((l['lote'], usa, l['custo'], l['validade']))
        self.lotes = [l for l in self.lotes if l['qtd'] > 0]
        return retirado


def simular_movimentacao(df, cad, est_inicial, data_corte, data_fim, rng):
    print(f'[4/6] Simulando movimentação de {data_corte:%d/%m/%Y} a {data_fim:%d/%m/%Y}...')

    cad_idx = cad.set_index('EAN')
    est_idx = est_inicial.set_index('EAN') if len(est_inicial) else pd.DataFrame()
    entradas_por_ean = {ean: g for ean, g in df.groupby('EAN', sort=False)}

    ledger = []
    mov_id = 0
    total_produtos = len(cad_idx)

    for i, (ean, p) in enumerate(cad_idx.iterrows(), 1):
        if i % 200 == 0:
            print(f'      ... {i:,}/{total_produtos:,} produtos')

        ctrl = ControleEstoque()
        eventos = []        # (data, prioridade, payload)
        suprimento = []     # (data, quantidade, tipo) para calibrar a demanda

        # --- 1. Estoque inicial (SIMULADO) -------------------------------
        tem_inicial = len(est_idx) and ean in est_idx.index
        if tem_inicial:
            ei = est_idx.loc[ean]
            eventos.append((data_corte, 0, ('INICIAL', ei)))
            suprimento.append((data_corte, int(ei['quantidade']), 'ABERTURA'))

        # --- 2. Entradas reais -------------------------------------------
        compras = entradas_por_ean[ean].sort_values('data_pedido')
        for _, c in compras.iterrows():
            eventos.append((c['data_pedido'], 1, ('ENTRADA', c)))
            suprimento.append((c['data_pedido'], int(c['Qtde. Fat.']), 'COMPRA'))

        # --- 3. Demanda calibrada por ciclo de reposição -----------------
        # Cada trecho entre duas chegadas tem sua própria taxa diária,
        # derivada do que chegou e de quanto tempo levou até a próxima
        # compra. É o que produz o dente de serra do estoque.
        trechos = calcular_taxas_locais(suprimento, data_fim)
        for ini, fim, lam in trechos:
            dias_trecho = (fim - ini).days + 1
            for d in range(dias_trecho):
                dia = ini + timedelta(days=d)
                if dia > data_fim:
                    break
                eventos.append((dia, 2, ('VENDA', lam)))

        # --- 4. Processa eventos em ordem cronológica --------------------
        eventos.sort(key=lambda e: (e[0], e[1]))
        saldo = 0
        data_anterior = None

        for data_mov, _prio, (tipo, payload) in eventos:

            # Baixa de lotes vencidos ao virar o dia
            if data_anterior != data_mov:
                for lv in ctrl.baixar_vencidos(data_mov):
                    mov_id += 1
                    saldo -= lv['qtd']
                    ledger.append({
                        'id_movimento': mov_id, 'data_movimento': data_mov,
                        'tipo_movimento': 'PERDA_VALIDADE', 'origem_dado': 'SIMULADO',
                        'EAN': ean, 'Lote': lv['lote'],
                        'Data de Validade': lv['validade'],
                        'quantidade': -lv['qtd'],
                        'custo_unitario': lv['custo'],
                        'preco_venda_unitario': np.nan,
                        'valor_total': -round(lv['qtd'] * lv['custo'], 2),
                        'saldo_apos_movimento': saldo,
                        'Cotação': np.nan, 'Pedido': np.nan,
                        'Nome do Fornecedor': None,
                        'arquivo_origem': None, 'linha_origem': np.nan,
                        'observacao': 'Baixa por vencimento de lote em estoque',
                    })
                data_anterior = data_mov

            # ---- ESTOQUE INICIAL ----
            if tipo == 'INICIAL':
                ei = payload
                ctrl.entrar(ei['Lote'], ei['Data de Validade'], ei['quantidade'],
                            ei['custo_unitario'], 'SIMULADO')
                saldo += int(ei['quantidade'])
                mov_id += 1
                ledger.append({
                    'id_movimento': mov_id, 'data_movimento': data_mov,
                    'tipo_movimento': 'ESTOQUE_INICIAL', 'origem_dado': 'SIMULADO',
                    'EAN': ean, 'Lote': ei['Lote'],
                    'Data de Validade': ei['Data de Validade'],
                    'quantidade': int(ei['quantidade']),
                    'custo_unitario': ei['custo_unitario'],
                    'preco_venda_unitario': np.nan,
                    'valor_total': round(ei['quantidade'] * ei['custo_unitario'], 2),
                    'saldo_apos_movimento': saldo,
                    'Cotação': np.nan, 'Pedido': np.nan,
                    'Nome do Fornecedor': None,
                    'arquivo_origem': None, 'linha_origem': np.nan,
                    'observacao': 'Posição inicial simulada (anterior aos pedidos)',
                })

            # ---- ENTRADA REAL ----
            elif tipo == 'ENTRADA':
                c = payload
                qtd = int(c['Qtde. Fat.'])
                val = excel_para_data(c['Data de Validade']).replace(hour=0)
                ctrl.entrar(c['Lote'], pd.Timestamp(val), qtd, c['Vl. Custo (R$)'], 'REAL')
                saldo += qtd
                mov_id += 1
                ledger.append({
                    'id_movimento': mov_id, 'data_movimento': data_mov,
                    'tipo_movimento': 'ENTRADA', 'origem_dado': 'REAL',
                    'EAN': ean, 'Lote': c['Lote'],
                    'Data de Validade': pd.Timestamp(val),
                    'quantidade': qtd,
                    'custo_unitario': round(float(c['Vl. Custo (R$)']), 2),
                    'preco_venda_unitario': np.nan,
                    'valor_total': round(qtd * float(c['Vl. Custo (R$)']), 2),
                    'saldo_apos_movimento': saldo,
                    'Cotação': c['Cotação'], 'Pedido': c['Pedido'],
                    'Nome do Fornecedor': c['Nome do Fornecedor'],
                    'arquivo_origem': c['arquivo_origem'],
                    'linha_origem': c['linha_origem'],
                    'observacao': 'Entrada por pedido de cotação faturado',
                })

            # ---- SAÍDA POR VENDA (SIMULADA) ----
            else:
                if ctrl.saldo <= 0:
                    continue
                lam = payload * clf.fator_sazonal(p['classe_terapeutica'], data_mov)
                qtd_demanda = int(rng.poisson(lam)) if lam > 0 else 0
                if qtd_demanda <= 0:
                    continue

                retirado = ctrl.consumir(qtd_demanda)
                if not retirado:
                    continue

                # O preço é calculado por lote, porque o piso de margem mínima
                # depende do custo do lote que o FEFO entregou.
                for lote, qtd_l, custo_l, val_l in retirado:
                    preco, no_piso = preco_com_deriva(
                        p['preco_venda_base'], p['data_preco_ref'], data_mov, custo_l)
                    saldo -= qtd_l
                    mov_id += 1
                    obs = f'Venda simulada (demanda={qtd_demanda}, FEFO)'
                    if no_piso:
                        obs += f'; preço elevado ao piso de margem mínima ' \
                               f'({MARGEM_MINIMA_OPERACIONAL:.0%} sobre o custo do lote)'
                    ledger.append({
                        'id_movimento': mov_id, 'data_movimento': data_mov,
                        'tipo_movimento': 'SAIDA_VENDA', 'origem_dado': 'SIMULADO',
                        'EAN': ean, 'Lote': lote, 'Data de Validade': val_l,
                        'quantidade': -qtd_l,
                        'custo_unitario': round(custo_l, 2),
                        'preco_venda_unitario': preco,
                        'valor_total': round(qtd_l * preco, 2),
                        'saldo_apos_movimento': saldo,
                        'Cotação': np.nan, 'Pedido': np.nan,
                        'Nome do Fornecedor': None,
                        'arquivo_origem': None, 'linha_origem': np.nan,
                        'observacao': obs,
                    })

    led = pd.DataFrame(ledger)
    print(f'      {len(led):,} movimentos gerados')
    return led


# ===========================================================================
# 5. ENRIQUECIMENTO E EXPORTAÇÃO
# ===========================================================================
def enriquecer(led, cad):
    print('[5/6] Enriquecendo ledger com cadastro...')
    cols_cad = ['EAN', 'Código do Produto', 'Descrição do Produto', 'Fabricante',
                'Forma Farmacêutica', 'Categoria Comercial', 'classe_terapeutica']
    led = led.merge(cad[cols_cad], on='EAN', how='left')
    led = led.rename(columns={'classe_terapeutica': 'Classe Terapêutica'})

    led['ano_mes'] = led['data_movimento'].dt.to_period('M').astype(str)
    led['ano'] = led['data_movimento'].dt.year
    led['mes'] = led['data_movimento'].dt.month
    led['dia_semana'] = led['data_movimento'].dt.day_name()

    led = led.sort_values(['data_movimento', 'EAN', 'id_movimento']).reset_index(drop=True)
    led['id_movimento'] = range(1, len(led) + 1)

    ordem = [
        'id_movimento', 'data_movimento', 'ano_mes', 'ano', 'mes', 'dia_semana',
        'tipo_movimento', 'origem_dado',
        'EAN', 'Código do Produto', 'Descrição do Produto', 'Fabricante',
        'Forma Farmacêutica', 'Categoria Comercial', 'Classe Terapêutica',
        'Lote', 'Data de Validade',
        'quantidade', 'custo_unitario', 'preco_venda_unitario', 'valor_total',
        'saldo_apos_movimento',
        'Cotação', 'Pedido', 'Nome do Fornecedor',
        'arquivo_origem', 'linha_origem', 'observacao',
    ]
    return led[ordem]


def main():
    rng = np.random.default_rng(SEED)
    random.seed(SEED)
    os.makedirs(DIR_SAIDA, exist_ok=True)

    df = carregar_base()
    cad = montar_cadastro(df)

    data_corte = (df['data_pedido'].min() - timedelta(days=DIAS_ANTES_PRIMEIRO_PEDIDO)).normalize()
    data_fim = df['data_pedido'].max().normalize()

    est_inicial = gerar_estoque_inicial(cad, data_corte, rng)
    led = simular_movimentacao(df, cad, est_inicial, data_corte, data_fim, rng)
    led = enriquecer(led, cad)

    print('[6/6] Salvando artefatos intermediários...')
    led.to_pickle('/home/claude/sadpf/ledger.pkl')
    cad.to_pickle('/home/claude/sadpf/cadastro.pkl')
    est_inicial.to_pickle('/home/claude/sadpf/estoque_inicial.pkl')

    print('\n' + '=' * 70)
    print('RESUMO DA MOVIMENTAÇÃO')
    print('=' * 70)
    res = led.groupby(['tipo_movimento', 'origem_dado']).agg(
        movimentos=('id_movimento', 'count'),
        unidades=('quantidade', 'sum'),
        valor=('valor_total', 'sum')).reset_index()
    print(res.to_string(index=False))
    print(f'\nPeríodo: {led["data_movimento"].min():%d/%m/%Y} a {led["data_movimento"].max():%d/%m/%Y}')
    print(f'Saldo mínimo observado: {led["saldo_apos_movimento"].min()}')


if __name__ == '__main__':
    main()
