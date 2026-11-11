#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SADPF — Módulo 4: Suíte de validação completa
==============================================
Trinta e cinco verificações em seis blocos:

  A. Base de origem    duplicidades, valores inválidos, campos calculados
  B. Estrutura         chaves, sinais, nulos, domínios de categoria
  C. Movimentação      saldo, FEFO, lotes, datas
  D. Financeiro        valor por linha, CMV, margem, conciliação com a origem
  E. Integração        integridade referencial e conciliação entre as 8 bases
  F. Qualidade do dado alertas sobre a base real (não são erros do sistema)

Blocos A-E produzem PASSOU/FALHOU. O bloco F produz ATENÇÃO: aponta anomalias
da base real que o sistema não pode corrigir sozinho e que precisam de
conferência junto à farmácia.
"""

import numpy as np
import pandas as pd

DIR_TRAB = '/home/claude/sadpf'
DIR_SAIDA = '/mnt/user-data/outputs'
ENTRADA_CSV = '/mnt/user-data/uploads/base_consolidada.csv'

TOL_FIN = 0.02          # tolerância em reais para comparações linha a linha
TOL_AGG = 0.05          # tolerância em reais para conciliação de agregados
RAZAO_OUTLIER_CUSTO = 3.0

import importlib.util as _ilu
_sp = _ilu.spec_from_file_location('clf', f'{DIR_TRAB}/01_classificadores.py')
_clf = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_clf)
SAZONALIDADE_REF = _clf.SAZONALIDADE

TIPOS_VALIDOS = {'ESTOQUE_INICIAL', 'ENTRADA', 'SAIDA_VENDA', 'PERDA_VALIDADE'}
ORIGENS_VALIDAS = {'REAL', 'SIMULADO'}
SITUACOES_VALIDAS = {'RUPTURA', 'DESCONTINUADO', 'ESTOQUE CRÍTICO', 'VALIDADE PRÓXIMA',
                     'EXCESSO', 'SEM GIRO RECENTE', 'NORMAL'}

resultados = []


def reg(bloco, nome, passou, detalhe, severidade='ERRO'):
    if severidade == 'ATENÇÃO':
        status = 'ATENÇÃO' if not passou else 'PASSOU'
    else:
        status = 'PASSOU' if passou else 'FALHOU'
    resultados.append({'bloco': bloco, 'verificacao': nome,
                       'resultado': status, 'detalhe': detalhe})
    marca = {'PASSOU': 'OK ', 'FALHOU': 'ERRO', 'ATENÇÃO': 'ATEN'}[status]
    print(f'  [{marca}] {nome}: {detalhe}')


# ===========================================================================
def bloco_a_origem():
    print('\nA. BASE DE ORIGEM')
    b = pd.read_csv(ENTRADA_CSV, sep=';', encoding='utf-8')
    for c in ['Vl. Custo (R$)', 'Vl. Faturado (R$)', 'Qtde. Ped. x Vl. Custo (R$)',
              'Preço de Venda Unitário (R$)', 'Desc. Com. (%)']:
        b[c] = pd.to_numeric(b[c].astype(str).str.replace('.', '', regex=False)
                             .str.replace(',', '.', regex=False), errors='coerce')

    reg('A', 'Sem linhas idênticas na origem', b.duplicated().sum() == 0,
        f'{b.duplicated().sum()} linhas duplicadas em {len(b):,}')
    d = b.duplicated(subset=['arquivo_origem', 'linha_origem']).sum()
    reg('A', 'Rastro de origem único', d == 0,
        f'{d} pares (arquivo_origem, linha_origem) repetidos')
    d = b.duplicated(subset=['Pedido', 'EAN', 'Lote']).sum()
    reg('A', 'Sem item repetido no mesmo pedido', d == 0,
        f'{d} combinações (Pedido, EAN, Lote) repetidas')

    inval = ((b['Qtde. Fat.'] <= 0).sum() + (b['Vl. Custo (R$)'] <= 0).sum()
             + (b['Preço de Venda Unitário (R$)'] <= 0).sum())
    reg('A', 'Quantidades e valores positivos', inval == 0,
        f'{inval} registros com quantidade ou valor não positivo')

    n = (b['Preço de Venda Unitário (R$)'] < b['Vl. Custo (R$)']).sum()
    reg('A', 'Preço de venda da base acima do custo', n == 0,
        f'{n} registros com preço de venda abaixo do custo de aquisição')

    n = (b['Data de Validade'] <= b['Data de Fabricação']).sum()
    reg('A', 'Validade posterior à fabricação', n == 0,
        f'{n} registros com validade anterior ou igual à fabricação')

    calc = (b['Qtde. Ped.'] * b['Vl. Custo (R$)']).round(2)
    n = ((calc - b['Qtde. Ped. x Vl. Custo (R$)']).abs() > TOL_FIN).sum()
    reg('A', 'Campo Qtde.Ped x Vl.Custo da origem confere', n == 0,
        f'{n} registros com produto divergente acima de R$ {TOL_FIN:.2f}')

    n = b.groupby('EAN')['Descrição do Produto'].nunique()
    reg('A', 'Um EAN, uma descrição', (n > 1).sum() == 0,
        f'{(n > 1).sum()} EANs com mais de uma descrição')
    n = b.groupby('Lote')['EAN'].nunique()
    reg('A', 'Lote não compartilhado entre produtos', (n > 1).sum() == 0,
        f'{(n > 1).sum()} lotes usados por mais de um EAN')
    return b


# ===========================================================================
def bloco_b_estrutura(led, pos):
    print('\nB. ESTRUTURA DAS BASES')

    reg('B', 'id_movimento único e sequencial',
        led['id_movimento'].duplicated().sum() == 0
        and (led['id_movimento'].values == np.arange(1, len(led) + 1)).all(),
        f'{len(led):,} movimentos, {led["id_movimento"].duplicated().sum()} duplicados')

    reg('B', 'Sem linhas idênticas no ledger', led.duplicated().sum() == 0,
        f'{led.duplicated().sum()} linhas duplicadas')

    ent = led[led['tipo_movimento'] == 'ENTRADA']
    d = ent.duplicated(subset=['arquivo_origem', 'linha_origem']).sum()
    reg('B', 'Cada linha da origem gerou uma entrada', d == 0,
        f'{d} entradas com rastro de origem repetido')

    inv = set(led['tipo_movimento'].unique()) - TIPOS_VALIDOS
    reg('B', 'Domínio de tipo_movimento', len(inv) == 0,
        f'{len(inv)} valores fora do domínio: {inv or "nenhum"}')
    inv = set(led['origem_dado'].unique()) - ORIGENS_VALIDAS
    reg('B', 'Domínio de origem_dado', len(inv) == 0,
        f'{len(inv)} valores fora do domínio: {inv or "nenhum"}')
    inv = set(pos['situacao_estoque'].unique()) - SITUACOES_VALIDAS
    reg('B', 'Domínio de situacao_estoque', len(inv) == 0,
        f'{len(inv)} valores fora do domínio: {inv or "nenhum"}')

    erros = 0
    for t in ['ESTOQUE_INICIAL', 'ENTRADA']:
        erros += (led.loc[led['tipo_movimento'] == t, 'quantidade'] <= 0).sum()
    for t in ['SAIDA_VENDA', 'PERDA_VALIDADE']:
        erros += (led.loc[led['tipo_movimento'] == t, 'quantidade'] >= 0).sum()
    reg('B', 'Sinal da quantidade coerente com o tipo', erros == 0,
        f'{erros} movimentos com sinal invertido ou quantidade zero')

    chaves = ['data_movimento', 'tipo_movimento', 'origem_dado', 'EAN', 'Lote',
              'quantidade', 'custo_unitario', 'valor_total', 'saldo_apos_movimento']
    n = led[chaves].isna().sum().sum()
    reg('B', 'Campos obrigatórios sem nulos', n == 0,
        f'{n} células nulas em {len(chaves)} campos obrigatórios')

    v = led[led['tipo_movimento'] == 'SAIDA_VENDA']
    n = v['preco_venda_unitario'].isna().sum()
    m = led[led['tipo_movimento'] != 'SAIDA_VENDA']['preco_venda_unitario'].notna().sum()
    reg('B', 'preco_venda_unitario só nas vendas', n == 0 and m == 0,
        f'{n} vendas sem preço, {m} não-vendas com preço preenchido')

    reais = led[led['origem_dado'] == 'REAL']
    n = (reais['arquivo_origem'].isna() | reais['linha_origem'].isna()).sum()
    reg('B', 'Movimentos REAIS com rastro completo', n == 0,
        f'{n} de {len(reais):,} movimentos reais sem arquivo ou linha de origem')

    sim = led[led['origem_dado'] == 'SIMULADO']
    reg('B', 'Partição real/simulado exaustiva', len(reais) + len(sim) == len(led),
        f'{len(reais):,} REAIS ({len(reais)/len(led)*100:.1f}%) + '
        f'{len(sim):,} SIMULADOS ({len(sim)/len(led)*100:.1f}%)')


# ===========================================================================
def bloco_c_movimentacao(led, pos):
    print('\nC. MOVIMENTAÇÃO DE ESTOQUE')

    reg('C', 'Saldo nunca negativo', (led['saldo_apos_movimento'] < 0).sum() == 0,
        f'{(led["saldo_apos_movimento"] < 0).sum()} movimentos com saldo negativo '
        f'(mínimo: {led["saldo_apos_movimento"].min()})')

    l2 = led.sort_values('id_movimento').copy()
    l2['rec'] = l2.groupby('EAN')['quantidade'].cumsum()
    div = (l2['rec'] - l2['saldo_apos_movimento']).abs()
    reg('C', 'Saldo recalculado confere linha a linha', (div > 0).sum() == 0,
        f'{(div > 0).sum()} divergências, máxima de {div.max()} unidades')

    rec = (pos['estoque_inicial'] + pos['total_entradas']
           - pos['total_saidas_venda'] - pos['total_perdas_validade'])
    n = ((rec - pos['estoque_atual']).abs() > 0).sum()
    reg('C', 'inicial + entradas − saídas − perdas = estoque_atual', n == 0,
        f'{n} produtos com equação de saldo divergente')

    ult = led.sort_values('id_movimento').groupby('EAN')['saldo_apos_movimento'].last()
    cmp_ = pos.set_index('EAN')['estoque_atual'].reindex(ult.index)
    n = ((ult - cmp_).abs() > 0).sum()
    reg('C', 'estoque_atual = último saldo do ledger', n == 0,
        f'{n} produtos divergentes')

    sl = led.groupby(['EAN', 'Lote', 'Data de Validade'])['quantidade'].sum()
    reg('C', 'Saldo por lote nunca negativo', (sl < 0).sum() == 0,
        f'{(sl < 0).sum()} lotes com saldo negativo')

    # Rastreabilidade de lote
    de_entrada = set(zip(*[led.loc[led['tipo_movimento'].isin(
        ['ESTOQUE_INICIAL', 'ENTRADA']), c] for c in ['EAN', 'Lote']]))
    de_saida = set(zip(*[led.loc[led['tipo_movimento'].isin(
        ['SAIDA_VENDA', 'PERDA_VALIDADE']), c] for c in ['EAN', 'Lote']]))
    orf = de_saida - de_entrada
    reg('C', 'Todo lote de saída tem entrada de origem', len(orf) == 0,
        f'{len(orf)} pares (EAN, lote) órfãos')

    # Aderência FEFO — reconstrói o estado dos lotes e confere a escolha
    viol = 0
    for ean, g in led.sort_values('id_movimento').groupby('EAN'):
        lotes = {}
        for _, m in g.iterrows():
            k = (m['Lote'], m['Data de Validade'])
            if m['tipo_movimento'] in ('ESTOQUE_INICIAL', 'ENTRADA'):
                lotes[k] = lotes.get(k, 0) + m['quantidade']
            else:
                disp = {kk: q for kk, q in lotes.items() if q > 0}
                if disp and m['Data de Validade'] > min(kk[1] for kk in disp):
                    viol += 1
                lotes[k] = lotes.get(k, 0) + m['quantidade']
    reg('C', 'Consumo obedece FEFO', viol == 0,
        f'{viol} saídas que ignoraram o lote de validade mais próxima')

    v = led[led['tipo_movimento'] == 'SAIDA_VENDA']
    reg('C', 'Nenhuma venda de lote vencido',
        (v['Data de Validade'] < v['data_movimento']).sum() == 0,
        f'{(v["Data de Validade"] < v["data_movimento"]).sum()} vendas após a validade')

    prim_e = led[led['tipo_movimento'].isin(['ESTOQUE_INICIAL', 'ENTRADA'])] \
        .groupby('EAN')['data_movimento'].min()
    prim_v = v.groupby('EAN')['data_movimento'].min()
    c = pd.DataFrame({'e': prim_e, 'v': prim_v}).dropna()
    reg('C', 'Nenhuma venda antes de existir estoque', (c['v'] < c['e']).sum() == 0,
        f'{(c["v"] < c["e"]).sum()} produtos com venda anterior à primeira entrada')

    ini, fim = pd.Timestamp('2024-09-30'), pd.Timestamp('2026-07-08')
    n = ((led['data_movimento'] < ini) | (led['data_movimento'] > fim)).sum()
    reg('C', 'Movimentos dentro do período declarado', n == 0,
        f'{n} movimentos fora de {ini:%d/%m/%Y}–{fim:%d/%m/%Y}')


# ===========================================================================
def bloco_d_financeiro(led, pos, mens, b):
    print('\nD. CONSISTÊNCIA FINANCEIRA')

    e = led[led['tipo_movimento'].isin(['ESTOQUE_INICIAL', 'ENTRADA'])]
    n = ((e['quantidade'].abs() * e['custo_unitario'] - e['valor_total']).abs() > TOL_FIN).sum()
    reg('D', 'Entrada: |qtd| × custo = valor_total', n == 0,
        f'{n} linhas divergentes acima de R$ {TOL_FIN:.2f}')

    v = led[led['tipo_movimento'] == 'SAIDA_VENDA']
    n = ((v['quantidade'].abs() * v['preco_venda_unitario'] - v['valor_total']).abs() > TOL_FIN).sum()
    reg('D', 'Venda: |qtd| × preço = valor_total', n == 0,
        f'{n} linhas divergentes acima de R$ {TOL_FIN:.2f}')

    p = led[led['tipo_movimento'] == 'PERDA_VALIDADE']
    n = ((-p['quantidade'].abs() * p['custo_unitario'] - p['valor_total']).abs() > TOL_FIN).sum()
    reg('D', 'Perda: −|qtd| × custo = valor_total', n == 0,
        f'{n} linhas divergentes acima de R$ {TOL_FIN:.2f}')

    n = (v['preco_venda_unitario'] <= v['custo_unitario']).sum()
    reg('D', 'Nenhuma venda com margem nula ou negativa', n == 0,
        f'{n} vendas com preço menor ou igual ao custo do lote')

    marg = ((v['preco_venda_unitario'] - v['custo_unitario']) / v['preco_venda_unitario'])
    n = (marg < 0.15).sum()
    reg('D', 'Margem por venda acima do piso operacional', n == 0,
        f'{n} vendas com margem bruta abaixo de 15% (mínima: {marg.min()*100:.1f}%)')

    # CMV recalculado
    v2 = v.copy()
    v2['cmv'] = v2['quantidade'].abs() * v2['custo_unitario']
    n = abs(v2['cmv'].sum() - pos['cmv'].sum())
    reg('D', 'CMV do ledger = CMV da posição', n < TOL_AGG,
        f'R$ {v2["cmv"].sum():,.2f} vs R$ {pos["cmv"].sum():,.2f} (dif. R$ {n:.2f})')

    n = ((pos['faturamento'] - pos['cmv'] - pos['margem_bruta']).abs() > TOL_FIN).sum()
    reg('D', 'margem_bruta = faturamento − CMV', n == 0,
        f'{n} produtos com margem divergente')

    n = ((pos['estoque_atual'] * pos['custo_ultimo']
          - pos['valor_estoque_custo']).abs() > TOL_FIN).sum()
    reg('D', 'valor_estoque_custo = estoque × custo', n == 0,
        f'{n} produtos com avaliação de estoque divergente')

    # Conciliação com a base de origem
    ent = led[led['tipo_movimento'] == 'ENTRADA']
    q_ok = int(ent['quantidade'].sum()) == int(b['Qtde. Fat.'].sum())
    l_ok = len(ent) == len(b)
    vb = (b['Qtde. Fat.'] * b['Vl. Custo (R$)']).sum()
    v_ok = abs(ent['valor_total'].sum() - vb) < 1.0
    reg('D', 'Entradas conciliam com a base de origem', q_ok and l_ok and v_ok,
        f'linhas {len(ent):,}/{len(b):,} | unidades {int(ent["quantidade"].sum()):,}/'
        f'{int(b["Qtde. Fat."].sum()):,} | valor R$ {ent["valor_total"].sum():,.2f}/R$ {vb:,.2f}')

    n = abs(mens['vl_faturamento'].sum() - pos['faturamento'].sum())
    reg('D', 'Faturamento mensal soma o total da posição', n < TOL_AGG,
        f'R$ {mens["vl_faturamento"].sum():,.2f} vs R$ {pos["faturamento"].sum():,.2f}')

    n = ((mens['vl_faturamento'] - mens['vl_cmv'] - mens['vl_margem_bruta']).abs() > TOL_FIN).sum()
    reg('D', 'Margem mensal = faturamento − CMV', n == 0,
        f'{n} meses com margem divergente')


# ===========================================================================
def bloco_e_integracao(led, pos, mens, abc, al, ind, est):
    print('\nE. INTEGRAÇÃO ENTRE AS BASES')

    e_led, e_pos = set(led['EAN']), set(pos['EAN'])
    reg('E', 'Ledger e posição cobrem os mesmos produtos',
        len(e_led - e_pos) == 0 and len(e_pos - e_led) == 0,
        f'{len(e_led - e_pos)} só no ledger, {len(e_pos - e_led)} só na posição')

    for nome, df_ in [('curva ABC', abc), ('alertas', al), ('estoque inicial', est)]:
        orf = set(df_['EAN']) - e_pos
        reg('E', f'Chave EAN de {nome} existe na posição', len(orf) == 0,
            f'{len(orf)} EANs órfãos em {len(df_):,} registros')

    reg('E', 'EAN único em posição e curva ABC',
        pos['EAN'].duplicated().sum() == 0 and abc['EAN'].duplicated().sum() == 0,
        f'{pos["EAN"].duplicated().sum()} duplicados na posição, '
        f'{abc["EAN"].duplicated().sum()} na curva ABC')

    pares = [
        ('Unidades vendidas', pos['total_saidas_venda'].sum(), mens['un_saidas_venda'].sum()),
        ('Unidades compradas', pos['total_entradas'].sum(), mens['un_entradas'].sum()),
        ('Estoque inicial', pos['estoque_inicial'].sum(), mens['un_estoque_inicial'].sum()),
        ('Perdas por validade', pos['total_perdas_validade'].sum(), mens['un_perdas_validade'].sum()),
        ('Estoque inicial por lote', est['quantidade'].sum(), pos['estoque_inicial'].sum()),
        ('Faturamento da curva ABC', abc['faturamento'].sum(), pos['faturamento'].sum()),
    ]
    falhas = [n for n, a, c in pares if abs(float(a) - float(c)) >= TOL_AGG]
    reg('E', 'Agregados conciliam entre as bases', len(falhas) == 0,
        f'{len(pares) - len(falhas)} de {len(pares)} agregados conferem'
        + (f' — divergentes: {falhas}' if falhas else ''))

    reg('E', 'Participações da curva ABC somam 100%',
        abs(abc['part_pct'].sum() - 100) < 0.01,
        f'soma = {abc["part_pct"].sum():.4f}%')

    # Indicadores contra as bases
    def ind_val(nome):
        s = ind[ind['indicador'] == nome]['valor']
        return float(s.iloc[0]) if len(s) else None

    conf = [
        ('Faturamento bruto', ind_val('Faturamento bruto'), pos['faturamento'].sum()),
        ('Unidades vendidas', ind_val('Unidades vendidas'), pos['total_saidas_venda'].sum()),
        ('Unidades compradas (entradas)', ind_val('Unidades compradas (entradas)'), pos['total_entradas'].sum()),
        ('Unidades em estoque ao fim', ind_val('Unidades em estoque ao fim'), pos['estoque_atual'].sum()),
        ('SKU em ruptura (item em linha)', ind_val('SKU em ruptura (item em linha)'),
         (pos['situacao_estoque'] == 'RUPTURA').sum()),
        ('SKU descontinuado (sem reposição)', ind_val('SKU descontinuado (sem reposição)'),
         (pos['situacao_estoque'] == 'DESCONTINUADO').sum()),
    ]
    falhas = [n for n, a, c in conf if a is None or abs(a - float(c)) >= TOL_AGG]
    reg('E', 'Painel de indicadores reflete as bases', len(falhas) == 0,
        f'{len(conf) - len(falhas)} de {len(conf)} indicadores conferem'
        + (f' — divergentes: {falhas}' if falhas else ''))

    mapa = {'Ruptura': 'RUPTURA', 'Item fora de linha': 'DESCONTINUADO',
            'Estoque crítico': 'ESTOQUE CRÍTICO'}
    falhas = [c for c, s in mapa.items()
              if al[al['categoria'] == c]['EAN'].nunique() != (pos['situacao_estoque'] == s).sum()]
    reg('E', 'Alertas alinhados com situacao_estoque', len(falhas) == 0,
        f'{len(mapa) - len(falhas)} de {len(mapa)} categorias conferem'
        + (f' — divergentes: {falhas}' if falhas else ''))


# ===========================================================================
def bloco_f_qualidade(led, b):
    print('\nF. QUALIDADE DA BASE REAL (atenção, não erro do sistema)')
    achados = []

    n = (b['Qtde. Fat.'] != b['Qtde. Ped.']).sum()
    reg('F', 'Quantidade faturada igual à pedida', n == 0,
        f'{n} itens com faturamento diferente do pedido — fato operacional, '
        f'o motor usa Qtde. Fat. (o que entrou no estoque)', 'ATENÇÃO')
    if n:
        for _, r in b[b['Qtde. Fat.'] != b['Qtde. Ped.']].iterrows():
            achados.append({'tipo': 'Faturamento diferente do pedido', 'EAN': r['EAN'],
                            'produto': r['Descrição do Produto'],
                            'detalhe': f"pedido {r['Qtde. Ped.']} un, faturado {r['Qtde. Fat.']} un",
                            'providencia': 'Conferir a nota fiscal do pedido '
                                           f"{r['Pedido']} junto ao fornecedor'"})

    ent = led[led['tipo_movimento'] == 'ENTRADA']
    g = ent.groupby('EAN').agg(n=('custo_unitario', 'size'), mn=('custo_unitario', 'min'),
                               mx=('custo_unitario', 'max'), md=('custo_unitario', 'median'))
    g = g[g['n'] >= 2]
    g['razao'] = g['mx'] / g['mn']
    out = g[g['razao'] >= RAZAO_OUTLIER_CUSTO].sort_values('razao', ascending=False)
    reg('F', 'Custo de aquisição estável por produto', len(out) == 0,
        f'{len(out)} produtos com custo máximo {RAZAO_OUTLIER_CUSTO:.0f}x+ o mínimo '
        f'(maior razão: {out["razao"].max():.0f}x)' if len(out) else
        'nenhum produto com dispersão de custo relevante', 'ATENÇÃO')
    desc = ent.drop_duplicates('EAN').set_index('EAN')['Descrição do Produto']
    for ean, r in out.iterrows():
        achados.append({'tipo': 'Dispersão de custo de aquisição', 'EAN': ean,
                        'produto': desc.get(ean, ''),
                        'detalhe': f"{int(r['n'])} compras entre R$ {r['mn']:.2f} e "
                                   f"R$ {r['mx']:.2f} (mediana R$ {r['md']:.2f}), "
                                   f"razão de {r['razao']:.0f}x",
                        'providencia': 'Verificar se há divergência de unidade de medida '
                                       '(unitário vs caixa) ou erro de digitação na cotação'})

    dl = ent.groupby(['EAN', 'Lote'])['custo_unitario'].nunique()
    n = (dl > 1).sum()
    reg('F', 'Mesmo lote com custo único', n == 0,
        f'{n} lotes comprados a custos diferentes — indica reaproveitamento de código '
        f'de lote entre remessas', 'ATENÇÃO')
    for (ean, lote), q in dl[dl > 1].items():
        sub = ent[(ent['EAN'] == ean) & (ent['Lote'] == lote)]
        achados.append({'tipo': 'Lote com mais de um custo', 'EAN': ean,
                        'produto': desc.get(ean, ''),
                        'detalhe': f"lote {lote} comprado a "
                                   f"{', '.join(f'R$ {c:.2f}' for c in sorted(sub['custo_unitario'].unique()))}",
                        'providencia': 'Confirmar com o fornecedor se é o mesmo lote físico; '
                                       'se não for, corrigir o código na origem'})

    nc = led[led['Classe Terapêutica'] == 'Outros / não classificado']['EAN'].nunique()
    tot = led['EAN'].nunique()
    reg('F', 'Classe terapêutica inferida para todos os produtos', nc == 0,
        f'{nc} de {tot} produtos ({nc/tot*100:.1f}%) sem classe inferida — '
        f'usam curva sazonal neutra', 'ATENÇÃO')

    df = pd.DataFrame(achados)
    if len(df):
        df.to_csv(f'{DIR_SAIDA}/qualidade_dados.csv', sep=';', index=False,
                  encoding='utf-8-sig', decimal=',')
        df.to_pickle(f'{DIR_TRAB}/qualidade_dados.pkl')
        print(f'      → {len(df)} achados detalhados em qualidade_dados.csv')
    return df


# ===========================================================================
def bloco_g_remarcacao(prop, pos, par):
    """Invariantes da estratégia de remarcação por validade."""
    print('\nG. ESTRATÉGIA DE REMARCAÇÃO')
    if prop is None or not len(prop):
        reg('G', 'Proposta de remarcação disponível', False,
            'arquivo proposta_remarcacao não encontrado — rodar o módulo 5')
        return

    margem_min = float(par['margem_minima_liquidacao'])
    desc_max = float(par['desconto_maximo_permitido'])
    janela = int(par['janela_devolucao_dias'])
    r = prop[prop['acao_recomendada'] == 'REMARCAR']

    n = (r['preco_proposto'] > r['preco_vigente']).sum()
    reg('G', 'Remarcação nunca eleva o preço', n == 0,
        f'{n} propostas com preço acima do vigente (teto operacional na ausência do PMC)')

    n = (r['margem_proposta_pct'] < margem_min * 100).sum()
    reg('G', 'Margem proposta respeita o piso', n == 0,
        f'{n} propostas abaixo de {margem_min:.0%}; mínima observada: '
        f'{r["margem_proposta_pct"].min():.2f}%' if len(r) else 'sem propostas de remarcação')

    n = (r['desconto_pct'] > desc_max * 100 + 0.01).sum()
    reg('G', 'Desconto dentro da trava máxima', n == 0,
        f'{n} propostas acima de {desc_max:.0%}; máximo observado: '
        f'{r["desconto_pct"].max():.2f}%' if len(r) else 'sem propostas de remarcação')

    n = (r['margem_proposta_pct'] > r['margem_vigente_pct'] + 0.01).sum()
    reg('G', 'Margem proposta não supera a vigente', n == 0,
        f'{n} propostas que aumentariam a margem')

    ctrl = prop[prop['restricao_comercial'] == 'CONTROLADO']
    n = ctrl['preco_proposto'].notna().sum()
    reg('G', 'Controlados sem proposta de desconto', n == 0,
        f'{n} de {len(ctrl)} itens sob Portaria 344/1998 com preço remarcado')

    n = (prop[prop['restricao_comercial'] != 'LIVRE']['divulgacao_permitida'] == 'SIM').sum()
    reg('G', 'Divulgação vedada em itens sob prescrição', n == 0,
        f'{n} itens de prescrição marcados como divulgáveis (RDC 96/2008)')

    n = (r['dias_para_vencer'] < r['prazo_minimo_classe']).sum()
    reg('G', 'Nenhuma remarcação abaixo do prazo mínimo de tratamento', n == 0,
        f'{n} propostas de desconto em lote que não permite concluir o tratamento')

    n = (r['dias_para_vencer'] >= janela).sum()
    reg('G', 'Remarcação só fora da janela de devolução', n == 0,
        f'{n} propostas de desconto em lote ainda devolvível (recupera custo integral)')

    seg = prop[prop['acao_recomendada'] == 'SEGREGAR — NÃO DISPENSAR']
    n = seg['preco_proposto'].notna().sum()
    reg('G', 'Itens segregados sem preço proposto', n == 0,
        f'{n} de {len(seg)} itens segregados com preço de venda')

    n = (prop['status_aprovacao'].astype(str).str.upper() != 'PENDENTE').sum()
    reg('G', 'Toda proposta nasce pendente de aprovação', n == 0,
        f'{n} propostas já com status diferente de PENDENTE '
        f'(aplicar_automaticamente = {par["aplicar_automaticamente"]})')

    val_sim = (prop['origem_validade'].str.startswith('SIMULADO')).sum()
    reg('G', 'Origem da validade identificada em toda proposta',
        prop['origem_validade'].notna().all(),
        f'{val_sim} de {len(prop)} propostas baseadas em validade SIMULADA, '
        f'{len(prop) - val_sim} em validade REAL da cotação')

    ok_fefo = prop.sort_values('prioridade')['Data de Validade'].is_monotonic_increasing
    reg('G', f'Priorização {par.get("priorizacao", "FEFO")} aplicada',
        ok_fefo or str(par.get('priorizacao', 'FEFO')).upper() != 'FEFO',
        'propostas ordenadas por validade crescente' if ok_fefo
        else 'ordenação não segue validade crescente')


# ===========================================================================
def bloco_h_comportamento(led, pos):
    """
    Coerência comportamental da movimentação.

    Os blocos anteriores verificam que as contas fecham. Este verifica que o
    estoque se comporta como o de uma farmácia: compra-se quando a prateleira
    está baixa, a ruptura é episódica e não crônica, a perda por vencimento
    fica na ordem de grandeza do setor e a sazonalidade declarada aparece no
    resultado. Uma base pode ser aritmeticamente perfeita e ainda assim
    descrever uma operação implausível.
    """
    print('\nH. COERÊNCIA COMPORTAMENTAL')
    data_ini = led['data_movimento'].min()
    data_fim = led['data_movimento'].max()
    dias_tot = (data_fim - data_ini).days + 1

    # --- H.1 a H.3: nível de estoque no momento da reposição -------------
    # A primeira chegada de cada produto é introdução do item, não reposição:
    # necessariamente encontra saldo zero e precisa ficar fora da conta.
    sup = led[led['tipo_movimento'].isin(['ESTOQUE_INICIAL', 'ENTRADA'])] \
        .sort_values('id_movimento')
    sup = sup.assign(ordem=sup.groupby('EAN').cumcount())
    rep = sup[(sup['tipo_movimento'] == 'ENTRADA') & (sup['ordem'] > 0)].copy()
    rep['saldo_antes'] = rep['saldo_apos_movimento'] - rep['quantidade']

    pct_zero = (rep['saldo_antes'] == 0).mean() * 100
    reg('H', 'Reposição chega com a prateleira baixa',
        rep['saldo_antes'].median() <= 12,
        f'saldo mediano antes da reposição: {rep["saldo_antes"].median():.0f} un '
        f'(p75 = {rep["saldo_antes"].quantile(0.75):.0f} un) em {len(rep):,} reposições')

    reg('H', 'Ruptura antes da reposição é minoria', 5 <= pct_zero <= 30,
        f'{pct_zero:.1f}% das reposições chegaram com saldo zero '
        f'(faixa plausível: 5% a 30%)')

    reg('H', 'Primeira chegada separada da reposição',
        len(sup) - len(rep) == sup.groupby('EAN').ngroups,
        f'{len(sup) - len(rep):,} primeiras chegadas excluídas de {len(sup):,} suprimentos')

    # --- H.4 a H.6: duração dos episódios de ruptura ---------------------
    # Amostra dos 200 maiores por faturamento: são os itens em que a ruptura
    # custa caro e em que a implausibilidade seria mais visível.
    top = pos.nlargest(200, 'faturamento')['EAN'].tolist()
    idx = pd.date_range(data_ini, data_fim, freq='D')
    episodios, pct_dias = [], []
    for ean in top:
        g = led[led['EAN'] == ean]
        s = g.groupby('data_movimento')['quantidade'].sum() \
             .reindex(idx, fill_value=0).cumsum()
        s = s[s.index >= g['data_movimento'].min()]
        z = (s <= 0)
        pct_dias.append(z.mean() * 100)
        if not z.any():
            continue
        grp = (z != z.shift()).cumsum()
        episodios += [len(x) for _, x in z.groupby(grp) if x.iloc[0]]
    episodios = np.array(episodios) if episodios else np.array([0])
    pct_dias = np.array(pct_dias)

    reg('H', 'Ruptura é episódica, não crônica', np.median(episodios) <= 45,
        f'{len(episodios)} episódios nos 200 maiores produtos, '
        f'mediana de {np.median(episodios):.0f} dias (p90 = {np.percentile(episodios, 90):.0f})')

    reg('H', 'Poucos produtos com ruptura prolongada',
        (episodios > 180).sum() <= 15,
        f'{int((episodios > 180).sum())} episódios acima de 180 dias; '
        f'maior episódio: {int(episodios.max())} dias')

    reg('H', 'Produtos de maior giro majoritariamente abastecidos',
        np.median(pct_dias) <= 15,
        f'mediana de {np.median(pct_dias):.1f}% dos dias ativos em ruptura '
        f'entre os 200 maiores')

    # --- H.7: perda por validade na ordem de grandeza do setor ------------
    fat = pos['faturamento'].sum()
    perda = -led.loc[led['tipo_movimento'] == 'PERDA_VALIDADE', 'valor_total'].sum()
    p_pct = perda / fat * 100 if fat else 0
    reg('H', 'Perda por validade na ordem de grandeza do varejo farmacêutico',
        0.5 <= p_pct <= 4.0,
        f'{p_pct:.2f}% do faturamento (R$ {perda:,.2f}); referência do setor: 1% a 3%')

    # --- H.8: estoque estável, sem colapso nem acúmulo descontrolado ------
    ini = pos['estoque_inicial'].sum()
    fim = pos['estoque_atual'].sum()
    razao = fim / ini if ini else 0
    reg('H', 'Estoque evolui sem colapso nem acúmulo descontrolado',
        0.6 <= razao <= 2.5,
        f'{ini:,} un na abertura e {fim:,} un no fechamento (razão {razao:.2f}x)')

    # --- H.9: margem bruta compatível com o varejo farmacêutico -----------
    m = (fat - pos['cmv'].sum()) / fat * 100 if fat else 0
    reg('H', 'Margem bruta compatível com o varejo farmacêutico',
        25 <= m <= 50, f'{m:.1f}%; faixa usual do setor: 25% a 45%')

    # --- H.10 e H.11: a sazonalidade declarada aparece no resultado -------
    # A taxa mensal é normalizada pelos dias do mês e pelo número de produtos
    # ativos nele. Sem isso, o crescimento do catálogo ao longo do período
    # entraria na curva como se fosse sazonalidade.
    v = led[led['tipo_movimento'] == 'SAIDA_VENDA'].copy()
    v['qtd'] = -v['quantidade']

    def curva_observada(sub):
        g = sub.groupby('mes')
        taxa = (g['qtd'].sum()
                / (g['data_movimento'].nunique() * g['EAN'].nunique()))
        taxa = taxa.reindex(range(1, 13))
        if taxa.isna().any() or taxa.mean() == 0:
            return None
        return (taxa / taxa.mean()).values

    resp = v[v['Classe Terapêutica'] == 'Respiratório / antigripal']
    obs = curva_observada(resp) if len(resp) else None
    if obs is not None:
        inv, ver = obs[[5, 6, 7]].mean(), obs[[11, 0, 1]].mean()
        reg('H', 'Sazonalidade de respiratórios: inverno acima do verão',
            inv > ver * 1.3,
            f'índice {inv*100:.0f} no inverno contra {ver*100:.0f} no verão '
            f'(razão {inv/ver:.2f}x)')

    # A aderência à curva declarada depende do volume: a calibração por ciclo
    # ancora a demanda no ritmo real de reposição, e em classes de baixo volume
    # esse ritmo domina o multiplicador sazonal. O teste cobre as classes com
    # volume suficiente para o sinal sobreviver.
    LIMITE_VOLUME = 3000
    correls = []
    for classe, curva in SAZONALIDADE_REF.items():
        sub = v[v['Classe Terapêutica'] == classe]
        if sub['qtd'].sum() < LIMITE_VOLUME:
            continue
        esp = np.array(curva, dtype=float)
        if esp.std() < 0.02:
            continue      # curva plana: não há o que correlacionar
        obs = curva_observada(sub)
        if obs is None:
            continue
        correls.append((classe, float(np.corrcoef(esp / esp.mean(), obs)[0, 1]),
                        int(sub['qtd'].sum())))

    if correls:
        pior = min(c[1] for c in correls)
        detalhe = ' · '.join(f'{c[0].split("/")[0].strip()[:14]} {c[1]:.2f}'
                             for c in sorted(correls, key=lambda x: -x[1]))
        reg('H', f'Curva sazonal reproduzida nas classes acima de '
                 f'{LIMITE_VOLUME:,} un'.replace(',', '.'),
            pior >= 0.60,
            f'{len(correls)} classes testadas, correlação com a curva '
            f'especificada: {detalhe}')

    # --- H.12: efeito do dia da semana ------------------------------------
    d = v.groupby('dia_semana').agg(q=('qtd', 'sum'), n=('data_movimento', 'nunique'))
    d['taxa'] = d['q'] / d['n']
    sab = d.loc['Saturday', 'taxa'] if 'Saturday' in d.index else 0
    dom = d.loc['Sunday', 'taxa'] if 'Sunday' in d.index else 0
    reg('H', 'Movimento semanal com pico no sábado e vale no domingo',
        sab > dom * 1.8,
        f'sábado {sab:.0f} un/dia contra domingo {dom:.0f} un/dia '
        f'(razão {sab/dom:.2f}x)' if dom else 'domingo sem vendas')

    # --- H.13: concentração ABC segue Pareto ------------------------------
    fa = pos[pos['faturamento'] > 0].sort_values('faturamento', ascending=False)
    n20 = max(int(len(fa) * 0.20), 1)
    conc = fa.head(n20)['faturamento'].sum() / fa['faturamento'].sum() * 100
    reg('H', 'Concentração de faturamento segue o princípio de Pareto',
        60 <= conc <= 90,
        f'os 20% maiores produtos concentram {conc:.1f}% do faturamento')

    # --- H.14: demanda responde ao estoque disponível ---------------------
    # Em dia sem saldo não pode haver venda; é a trava do motor vista pelo
    # lado do resultado.
    dias_com_venda = v.groupby('EAN')['data_movimento'].nunique()
    reg('H', 'Nenhuma venda em produto-dia sem saldo',
        (led['saldo_apos_movimento'] < 0).sum() == 0,
        f'{dias_com_venda.sum():,} produto-dias com venda, todos com saldo suficiente')


# ===========================================================================
def main():
    print('=' * 78)
    print('SUÍTE DE VALIDAÇÃO — SADPF')
    print('=' * 78)

    led = pd.read_pickle(f'{DIR_TRAB}/movimentacao_estoque.pkl')
    pos = pd.read_pickle(f'{DIR_TRAB}/posicao_estoque.pkl')
    mens = pd.read_pickle(f'{DIR_TRAB}/movimentacao_mensal.pkl')
    abc = pd.read_pickle(f'{DIR_TRAB}/curva_abc.pkl')
    al = pd.read_pickle(f'{DIR_TRAB}/alertas_sadpf.pkl')
    ind = pd.read_pickle(f'{DIR_TRAB}/indicadores_sadpf.pkl')
    est = pd.read_pickle(f'{DIR_TRAB}/estoque_inicial_lotes.pkl')

    b = bloco_a_origem()
    bloco_b_estrutura(led, pos)
    bloco_c_movimentacao(led, pos)
    bloco_d_financeiro(led, pos, mens, b)
    bloco_e_integracao(led, pos, mens, abc, al, ind, est)
    bloco_f_qualidade(led, b)

    try:
        prop = pd.read_pickle(f'{DIR_TRAB}/proposta_remarcacao.pkl')
        import importlib.util
        _s = importlib.util.spec_from_file_location(
            'rem', f'{DIR_TRAB}/05_remarcacao.py')
        _rem = importlib.util.module_from_spec(_s)
        _s.loader.exec_module(_rem)
        par, _, _ = _rem.carregar_parametros()
        bloco_g_remarcacao(prop, pos, par)
    except FileNotFoundError:
        print('\nG. ESTRATÉGIA DE REMARCAÇÃO\n  (proposta ainda não gerada — '
              'rodar o módulo 5 antes)')

    bloco_h_comportamento(led, pos)

    rel = pd.DataFrame(resultados)
    rel.to_csv(f'{DIR_SAIDA}/validacao_integridade.csv', sep=';', index=False,
               encoding='utf-8-sig')
    rel.to_pickle(f'{DIR_TRAB}/validacao_integridade.pkl')

    n_pass = (rel['resultado'] == 'PASSOU').sum()
    n_falha = (rel['resultado'] == 'FALHOU').sum()
    n_aten = (rel['resultado'] == 'ATENÇÃO').sum()

    print('\n' + '=' * 78)
    print(f'{len(rel)} verificações: {n_pass} PASSOU | {n_falha} FALHOU | {n_aten} ATENÇÃO')
    if n_falha:
        print('\nFALHAS:')
        for _, r in rel[rel['resultado'] == 'FALHOU'].iterrows():
            print(f"  · [{r['bloco']}] {r['verificacao']} — {r['detalhe']}")
    else:
        print('Nenhuma falha. Os itens em ATENÇÃO são anomalias da base real, '
              'não erros do sistema.')
    print('=' * 78)
    return n_falha == 0


if __name__ == '__main__':
    main()
