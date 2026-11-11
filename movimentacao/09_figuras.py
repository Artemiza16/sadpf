#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SADPF — Módulo 9: Figuras da documentação
Gera as evidências visuais de plausibilidade da movimentação.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd
import numpy as np

DIR_TRAB = '/home/claude/sadpf'
DIR_FIG = '/home/claude/sadpf/figuras'

# Paleta validada (light mode, surface #fcfcfb)
SURF = '#fcfcfb'
INK = '#0b0b0b'
INK2 = '#52514e'
INK3 = '#8a8984'
GRID = '#e4e3df'
S1 = '#2a78d6'   # azul
S2 = '#eb6834'   # laranja
S3 = '#1baf7a'   # aqua
S4 = '#eda100'   # amarelo

plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 9,
    'axes.edgecolor': GRID, 'axes.linewidth': 0.8,
    'axes.labelcolor': INK2, 'text.color': INK,
    'xtick.color': INK2, 'ytick.color': INK2,
    'xtick.labelsize': 8, 'ytick.labelsize': 8,
    'figure.facecolor': SURF, 'axes.facecolor': SURF,
    'savefig.facecolor': SURF, 'axes.grid': True,
    'grid.color': GRID, 'grid.linewidth': 0.6, 'grid.alpha': 1.0,
})


def _limpar(ax):
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color(GRID)
    ax.set_axisbelow(True)
    ax.grid(axis='x', visible=False)


def figura_dente_de_serra(led, pos):
    """Trajetória do saldo de dois produtos, com as chegadas marcadas."""
    idx = pd.date_range(led['data_movimento'].min(), led['data_movimento'].max(), freq='D')
    alvos = pos[pos['n_compras'] >= 7].nlargest(2, 'faturamento')['EAN'].tolist()

    fig, axes = plt.subplots(2, 1, figsize=(7.4, 5.0), sharex=True)
    for ax, ean, cor in zip(axes, alvos, (S1, S2)):
        g = led[led['EAN'] == ean]
        desc = g['Descrição do Produto'].iloc[0]
        s = g.groupby('data_movimento')['quantidade'].sum() \
             .reindex(idx, fill_value=0).cumsum()
        s = s[s.index >= g['data_movimento'].min()]

        ax.plot(s.index, s.values, color=cor, linewidth=1.6, zorder=3)
        ax.fill_between(s.index, 0, s.values, color=cor, alpha=0.10, zorder=2)

        ent = g[g['tipo_movimento'] == 'ENTRADA']
        xs = ent['data_movimento'].values
        ys = [s.get(pd.Timestamp(d), 0) for d in xs]
        ax.scatter(xs, ys, s=38, facecolor=SURF, edgecolor=cor,
                   linewidth=1.6, zorder=5)
        for x, y, q in zip(xs, ys, ent['quantidade']):
            ax.annotate(f'+{int(q)}', (x, y), textcoords='offset points',
                        xytext=(0, 9), ha='center', fontsize=7, color=INK2)

        ax.set_title(desc[:54], fontsize=9.5, color=INK, loc='left', pad=8)
        ax.set_ylabel('unidades em estoque', fontsize=8)
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_locator(MaxNLocator(5, integer=True))
        _limpar(ax)

    axes[0].text(0.995, 0.93, 'círculo = chegada de pedido real',
                 transform=axes[0].transAxes, ha='right', fontsize=7.5,
                 color=INK3)
    fig.tight_layout(pad=0.9)
    fig.savefig(f'{DIR_FIG}/fig1_dente_de_serra.png', dpi=190,
                bbox_inches='tight')
    plt.close(fig)


def figura_sazonalidade(led, sazonalidade):
    """
    Curva sazonal especificada contra a observada na base gerada.

    A linha fina é o multiplicador declarado no módulo de classificadores; a
    grossa é o que efetivamente saiu do motor. A aderência entre as duas mostra
    que a sazonalidade não é afirmação de documentação, e sim comportamento
    mensurável da base.
    """
    v = led[led['tipo_movimento'] == 'SAIDA_VENDA'].copy()
    v['qtd'] = -v['quantidade']

    # As três classes com volume suficiente para o sinal sazonal sobreviver
    # ao ritmo de reposição (ver limitação discutida na documentação).
    classes = [
        ('Respiratório / antigripal', 'Respiratórios', S1),
        ('Antibiótico / antimicrobiano', 'Antibióticos', S2),
        ('Analgésico / anti-inflamatório', 'Analgésicos', S3),
    ]
    meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
             'jul', 'ago', 'set', 'out', 'nov', 'dez']

    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    rotulos = []
    ax.axvspan(6, 8, color=GRID, alpha=0.5, zorder=0)
    ax.axhline(100, color=INK3, linewidth=0.8, zorder=2)

    for classe, rotulo, cor in classes:
        s = v[v['Classe Terapêutica'] == classe]
        if not len(s):
            continue

        # A taxa de cada mês é normalizada por dois fatores de composição: o
        # número de dias que o mês aparece na janela de 21 meses e a
        # quantidade de produtos ativos naquele mês. Sem isso, o crescimento
        # do catálogo ao longo do período entraria na curva como se fosse
        # sazonalidade. Tomar a mediana entre produtos também não serve: a
        # maioria vende poucas unidades por mês, e o índice individual vira
        # ruído em torno de 1.
        g = s.groupby('mes')
        unid = g['qtd'].sum().reindex(range(1, 13))
        dias = g['data_movimento'].nunique().reindex(range(1, 13))
        ativos = g['EAN'].nunique().reindex(range(1, 13))
        taxa = unid / (dias * ativos)
        obs = taxa / taxa.mean() * 100

        esp = np.array(sazonalidade[classe], dtype=float)
        esp = esp / esp.mean() * 100

        ax.plot(range(1, 13), esp, color=cor, linewidth=1.0, alpha=0.55,
                zorder=3)
        ax.plot(range(1, 13), obs.values, color=cor, linewidth=2.2,
                marker='o', markersize=4.5, markerfacecolor=SURF,
                markeredgewidth=1.5, zorder=4)
        rotulos.append((obs.iloc[-1], rotulo, cor))

    # Rótulos diretos no fim da linha, afastados para não colidirem
    rotulos.sort()
    ultimo = -99
    for y, texto, cor in rotulos:
        y_pos = max(y, ultimo + 11)
        ax.annotate(texto, (12, y), xytext=(12.45, y_pos), fontsize=8.5,
                    color=INK2, va='center',
                    arrowprops=dict(arrowstyle='-', color=GRID, linewidth=0.8)
                    if abs(y_pos - y) > 2 else None)
        ultimo = y_pos

    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(meses)
    ax.set_ylabel('índice de venda diária (média anual = 100)', fontsize=8)
    ax.set_xlim(0.6, 14.9)
    ax.set_ylim(50, 175)
    ax.text(7, 168, 'inverno', ha='center', fontsize=7.5, color=INK3)
    ax.text(0.0, 1.07, 'linha grossa: observado na base   ·   '
            'linha fina: especificado no modelo',
            transform=ax.transAxes, fontsize=8, color=INK2)
    _limpar(ax)
    fig.tight_layout(pad=0.9)
    fig.savefig(f'{DIR_FIG}/fig2_sazonalidade.png', dpi=190, bbox_inches='tight')
    plt.close(fig)


def figura_saldo_na_reposicao(led):
    """Distribuição do saldo no momento da reposição, antes e depois."""
    sup = led[led['tipo_movimento'].isin(['ESTOQUE_INICIAL', 'ENTRADA'])] \
        .sort_values('id_movimento')
    sup = sup.assign(ordem=sup.groupby('EAN').cumcount())
    rep = sup[(sup['tipo_movimento'] == 'ENTRADA') & (sup['ordem'] > 0)].copy()
    rep['saldo_antes'] = rep['saldo_apos_movimento'] - rep['quantidade']

    bins = [0, 1, 3, 6, 11, 21, 41, 10 ** 6]
    rot = ['0', '1-2', '3-5', '6-10', '11-20', '21-40', '> 40']
    cat = pd.cut(rep['saldo_antes'], bins=bins, labels=rot, right=False)
    cont = cat.value_counts().reindex(rot)
    pcts = cont / cont.sum() * 100

    fig, ax = plt.subplots(figsize=(7.4, 2.9))
    cores = [S2] + [S1] * 6
    barras = ax.bar(range(len(rot)), pcts.values, color=cores, width=0.68,
                    zorder=3)
    for b in barras:
        b.set_linewidth(0)
    for i, (b, v_) in enumerate(zip(barras, pcts.values)):
        ax.annotate(f'{v_:.0f}%', (b.get_x() + b.get_width() / 2, v_),
                    textcoords='offset points', xytext=(0, 4), ha='center',
                    fontsize=8, color=INK2)
    ax.set_xticks(range(len(rot)))
    ax.set_xticklabels(rot)
    ax.set_xlabel('unidades em estoque no momento em que a reposição chegou',
                  fontsize=8)
    ax.set_ylabel('% das reposições', fontsize=8)
    ax.set_ylim(0, max(pcts.values) * 1.22)
    ax.text(0.0, 1.10, f'{len(rep):,} reposições · mediana de '
            f'{rep["saldo_antes"].median():.0f} unidades'.replace(',', '.'),
            transform=ax.transAxes, fontsize=8.5, color=INK2)
    _limpar(ax)
    fig.tight_layout(pad=0.9)
    fig.savefig(f'{DIR_FIG}/fig3_saldo_reposicao.png', dpi=190,
                bbox_inches='tight')
    plt.close(fig)


def figura_fluxo_mensal(mens):
    """Entradas, saídas e saldo acumulado por mês."""
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    x = np.arange(len(mens))
    larg = 0.38

    ax.bar(x - larg / 2, mens['un_entradas'], larg, color=S1,
           label='entradas (real)', zorder=3, linewidth=0)
    ax.bar(x + larg / 2, mens['un_saidas_venda'], larg, color=S2,
           label='saídas por venda (simulado)', zorder=3, linewidth=0)

    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks([])
    ax2.spines[:].set_visible(False)

    ax.set_xticks(x[::2])
    ax.set_xticklabels([m[2:].replace('-', '/') for m in mens['ano_mes']][::2],
                       rotation=0)
    ax.set_ylabel('unidades', fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc='upper left',
              bbox_to_anchor=(0, 1.16), ncol=2, handlelength=1.2,
              labelcolor=INK2)
    _limpar(ax)
    fig.tight_layout(pad=0.9)
    fig.savefig(f'{DIR_FIG}/fig4_fluxo_mensal.png', dpi=190, bbox_inches='tight')
    plt.close(fig)


def main():
    import os, importlib.util
    os.makedirs(DIR_FIG, exist_ok=True)
    _s = importlib.util.spec_from_file_location('clf', f'{DIR_TRAB}/01_classificadores.py')
    clf = importlib.util.module_from_spec(_s); _s.loader.exec_module(clf)
    led = pd.read_pickle(f'{DIR_TRAB}/movimentacao_estoque.pkl')
    pos = pd.read_pickle(f'{DIR_TRAB}/posicao_estoque.pkl')
    mens = pd.read_pickle(f'{DIR_TRAB}/movimentacao_mensal.pkl')

    figura_dente_de_serra(led, pos)
    figura_sazonalidade(led, clf.SAZONALIDADE)
    figura_saldo_na_reposicao(led)
    figura_fluxo_mensal(mens)
    print('✓ 4 figuras geradas em', DIR_FIG)
    for f in sorted(os.listdir(DIR_FIG)):
        print('   ', f, f'{os.path.getsize(DIR_FIG + "/" + f)/1024:.0f} KB')


if __name__ == '__main__':
    main()
