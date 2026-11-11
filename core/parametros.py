"""
Parâmetros do motor de decisão.

Todo limite que separa "crítico" de "saudável" está reunido aqui. As mensagens
leem estes valores em vez de tê-los escritos no texto, então mudar um número
muda o diagnóstico, a cor e a frase junto — é o que permite reaproveitar o
sistema com uma base nova sem reescrever nada.

As alterações feitas na aba Preferências são gravadas em dados/preferencias.json
e voltam a valer na próxima abertura.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

ARQUIVO_PREFS = Path(__file__).parent.parent / "dados" / "preferencias.json"


@dataclass
class Parametros:
    # --- fornecedores ---
    concentracao_fornecedor: float = 0.40   # dependência crítica de um distribuidor
    atendimento_minimo: float = 0.97        # abaixo disto entra na lista de corte
    pedidos_minimos: int = 3                # pedidos p/ avaliar confiabilidade
    linhas_minimas: int = 20                # linhas p/ avaliar qualidade de entrega
    pedido_minimo_folga: float = 0.10       # pedido até 10% acima do mínimo = no limite
    # --- compras e caixa ---
    concentracao_cotacao: float = 0.40      # % do valor nas 3 maiores cotações
    pico_mensal: float = 1.25               # múltiplo da média que vira pico
    prazo_pagamento_minimo: int = 30        # prazo abaixo disto aperta o caixa
    # --- regularidade (XYZ) ---
    cv_x: float = 0.50                      # coeficiente de variação até aqui = X (regular)
    cv_y: float = 1.00                      # até aqui = Y; acima = Z (irregular)
    # --- previsão de compras ---
    previsao_chance_minima: float = 0.15    # fração de meses com compra p/ ser candidato
    previsao_chance_alta: float = 0.35      # a partir daqui a chance é "alta"
    # --- movimentação de estoque ---
    mov_janela_demanda: int = 90            # dias de venda que definem a demanda diária
    mov_cobertura_critica: int = 15         # cobertura abaixo disto = estoque crítico
    mov_cobertura_excesso: int = 120        # cobertura acima disto = excesso
    mov_validade_proxima: int = 180         # lote vencendo em menos que isto
    mov_dias_descontinuado: int = 180       # sem reposição há mais que isto = fora de linha
    mov_lead_time: int = 7                  # dias entre pedir e receber
    mov_cobertura_alvo: int = 30            # dias de venda que a compra deve cobrir
    mov_nivel_servico: float = 0.95         # chance de não faltar durante a reposição
    mov_custo_pedido: float = 15.0          # custo de pedir um item (lote econômico)
    mov_taxa_manutencao: float = 0.25       # custo anual de manter estoque, % do custo
    # --- validade e recorrência ---
    validade_risco_meses: int = 6           # janela de risco de vencimento
    recorrencia_minima: int = 4             # compras p/ o item ser recorrente
    # --- preço e margem ---
    alta_custo_relevante: float = 0.15      # variação que merece revisão de preço
    variacao_implausivel: float = 3.00      # acima disto é erro de cadastro
    razao_preco_suspeita: float = 3.00      # diferença entre fornecedores suspeita
    valor_minimo_analise: float = 300.0     # valor abaixo do qual a variação é irrelevante
    margem_baixa: float = 0.25              # margem bruta considerada apertada
    # --- régua de gravidade ---
    economia_critica: float = 0.03          # dinheiro recuperável que vira crítico
    economia_atencao: float = 0.01
    exposicao_critica: float = 0.10         # valor só exposto exige mais p/ ser crítico
    exposicao_atencao: float = 0.03
    # --- curva ABC ---
    corte_a: float = 0.80
    corte_b: float = 0.95
    base_abc: str = "valor_faturado"        # ou "valor_pedido"
    # --- referência ---
    data_referencia: str = "2026-09-06"     # usada no cálculo de meses até vencer
    # --- privacidade ---
    nomes_originais: bool = False           # False = fornecedores e representantes codificados

    @property
    def corte(self) -> tuple[float, float]:
        return (self.corte_a, self.corte_b)

    def nivel_por_impacto(self, valor: float, total: float,
                          tem_caso: bool = True, tipo: str = "exposicao") -> str:
        """Gravidade a partir do impacto medido, não de um rótulo fixo.

        A régua é mais dura para economia do que para exposição: dinheiro que dá
        para recuperar é mais urgente, por real, do que dinheiro apenas sob risco.
        """
        if not tem_caso:
            return "ok"
        crit, aten = ((self.economia_critica, self.economia_atencao)
                      if tipo == "economia"
                      else (self.exposicao_critica, self.exposicao_atencao))
        razao = valor / max(1.0, total)
        return "crit" if razao >= crit else ("aten" if razao >= aten else "ok")


PADRAO = Parametros()

# Metadados usados pela aba Preferências: rótulo, descrição, limites e formato.
# (campo, rótulo, descrição, mínimo, máximo, passo, formato)
CONTROLES = [
    ("Validade e estoque", [
        ("validade_risco_meses", "Risco de validade",
         "Um lote entra na lista de risco quando falta menos que isto para vencer. "
         "Afeta a Validade no recebimento (tela Validade e Remarcação) e o alerta de "
         "validade no apoio à decisão.",
         1, 24, 1, "meses"),
        ("recorrencia_minima", "Item recorrente a partir de",
         "Quantas vezes o medicamento precisa ter sido comprado no período para ser "
         "tratado como item de reposição, e não como compra pontual.",
         2, 12, 1, "compras"),
    ]),
    ("Fornecedores", [
        ("concentracao_fornecedor", "Concentração crítica",
         "Participação de um único distribuidor no valor comprado a partir da qual "
         "a dependência é tratada como crítica.", 0.20, 0.80, 0.05, "pct"),
        ("atendimento_minimo", "Atendimento mínimo aceitável",
         "Abaixo deste nível de entrega o fornecedor entra na lista de confiabilidade baixa.",
         0.80, 1.00, 0.01, "pct"),
        ("pedidos_minimos", "Pedidos mínimos para avaliar",
         "Evita julgar um distribuidor por uma ou duas entregas.", 1, 15, 1, "pedidos"),
        ("linhas_minimas", "Linhas mínimas para qualidade de entrega",
         "Mesma ideia aplicada à análise de validade curta na entrega.", 5, 80, 5, "linhas"),
        ("pedido_minimo_folga", "Folga sobre o faturamento mínimo",
         "Pedido que passa do faturamento mínimo do fornecedor por menos que esta folga é "
         "tratado como 'no limite': qualquer corte na nota o deixa abaixo do mínimo.",
         0.0, 0.50, 0.05, "pct"),
    ]),
    ("Preço e margem", [
        ("alta_custo_relevante", "Alta de custo relevante",
         "Variação entre a primeira e a última compra a partir da qual o item "
         "aparece como custo em alta.", 0.05, 0.60, 0.05, "pct"),
        ("variacao_implausivel", "Variação implausível",
         "Acima disto a variação deixa de ser reajuste e passa a ser sinalizada "
         "como provável erro de cadastro.", 1.00, 10.00, 0.50, "pct"),
        ("razao_preco_suspeita", "Diferença suspeita entre fornecedores",
         "Quantas vezes o maior custo pode superar o menor para o mesmo medicamento "
         "antes de ser tratado como erro de cadastro.", 1.5, 10.0, 0.5, "vezes"),
        ("valor_minimo_analise", "Valor mínimo para analisar preço",
         "Abaixo deste valor comprado a variação de preço do item é irrelevante.",
         0.0, 2000.0, 50.0, "moeda"),
        ("margem_baixa", "Margem considerada apertada",
         "Margem bruta abaixo da qual um item de classe A entra no alerta de precificação.",
         0.05, 0.60, 0.05, "pct"),
    ]),
    ("Compras e caixa", [
        ("pico_mensal", "Pico mensal a partir de",
         "Quantas vezes acima da média mensal um mês precisa estar para ser tratado "
         "como pico de desembolso.", 1.05, 3.00, 0.05, "vezes"),
        ("concentracao_cotacao", "Concentração em poucas cotações",
         "Participação das três maiores cotações no valor total a partir da qual a "
         "compra é considerada concentrada demais.", 0.20, 0.90, 0.05, "pct"),
        ("prazo_pagamento_minimo", "Prazo de pagamento mínimo desejado",
         "Compras com prazo menor que este pesam no caixa: o pagamento vence antes de o "
         "produto girar.", 7, 90, 1, "dias"),
    ]),
    ("Previsão de compras", [
        ("previsao_chance_minima", "Chance mínima para ser candidato",
         "Fração dos meses do histórico em que o item foi comprado a partir da qual ele "
         "entra na lista de candidatos da próxima cotação.", 0.05, 0.60, 0.05, "pct"),
        ("previsao_chance_alta", "Chance alta a partir de",
         "Fração dos meses com compra a partir da qual a chance do item é tratada como "
         "alta.", 0.15, 0.90, 0.05, "pct"),
    ]),
    ("Movimentação de estoque", [
        ("mov_janela_demanda", "Janela da demanda",
         "Dias de venda, contados até a data final do período, usados para calcular a "
         "demanda diária de cada produto. É a demanda recente que importa para repor.",
         30, 180, 15, "dias"),
        ("mov_cobertura_critica", "Estoque crítico abaixo de",
         "Cobertura (estoque ÷ demanda diária) abaixo da qual o produto entra como "
         "estoque crítico.", 5, 60, 5, "dias"),
        ("mov_cobertura_excesso", "Excesso acima de",
         "Cobertura acima da qual o produto é tratado como excesso: dinheiro parado e "
         "risco de vencer na prateleira.", 45, 365, 15, "dias"),
        ("mov_validade_proxima", "Validade próxima abaixo de",
         "Prazo até o vencimento do lote mais antigo em estoque a partir do qual o "
         "produto entra em validade próxima.", 30, 365, 15, "dias"),
        ("mov_dias_descontinuado", "Fora de linha sem reposição há",
         "Produto comprado uma única vez e sem reposição há mais que isto, com saldo "
         "zero, é descontinuado — não ruptura.", 60, 365, 30, "dias"),
        ("mov_lead_time", "Prazo de reposição",
         "Dias entre fazer o pedido e a mercadoria chegar. Define o ponto de pedido.",
         1, 30, 1, "dias"),
        ("mov_cobertura_alvo", "Cobertura desejada na compra",
         "Quantos dias de venda a compra sugerida deve cobrir, além do prazo de reposição.",
         7, 120, 1, "dias"),
        ("mov_nivel_servico", "Nível de serviço",
         "Chance desejada de não faltar o produto enquanto a reposição não chega. Mais "
         "alto = estoque de segurança maior.", 0.80, 0.99, 0.01, "pct"),
        ("mov_custo_pedido", "Custo de pedir um item",
         "Quanto custa incluir um item numa cotação (tempo de conferir, receber e lançar). "
         "Entra no lote econômico: custo maior pede lotes maiores e menos pedidos.",
         0.0, 100.0, 5.0, "moeda"),
        ("mov_taxa_manutencao", "Custo anual de manter estoque",
         "Custo de capital, espaço e risco de perda por ano, em proporção do custo do "
         "produto. Entra no lote econômico: taxa maior pede lotes menores.",
         0.05, 0.60, 0.05, "pct"),
    ]),
    ("Regularidade (XYZ)", [
        ("cv_x", "Limite da classe X (regular)",
         "Coeficiente de variação das compras mês a mês até o qual o item é regular — "
         "a demanda é previsível e aceita reposição automática.", 0.10, 1.50, 0.05, "decimal"),
        ("cv_y", "Limite da classe Y (variável)",
         "Até este coeficiente o item é variável; acima, é irregular (classe Z) e exige "
         "compra sob encomenda ou estoque de segurança.", 0.50, 3.00, 0.05, "decimal"),
    ]),
    ("Régua de gravidade", [
        ("economia_critica", "Economia crítica",
         "Dinheiro recuperável, como proporção do valor comprado, que torna um ponto crítico.",
         0.01, 0.20, 0.01, "pct"),
        ("economia_atencao", "Economia em atenção",
         "Mesma régua, para o nível intermediário.", 0.005, 0.15, 0.005, "pct"),
        ("exposicao_critica", "Exposição crítica",
         "Valor apenas sob risco exige mais para virar crítico do que dinheiro "
         "recuperável, porque não é perda certa.", 0.02, 0.40, 0.01, "pct"),
        ("exposicao_atencao", "Exposição em atenção",
         "Mesma régua, para o nível intermediário.", 0.01, 0.25, 0.01, "pct"),
    ]),
]

CORTES_ABC = {
    "A até 80% · B até 95% (padrão)": (0.80, 0.95),
    "A até 75% · B até 95%": (0.75, 0.95),
    "A até 70% · B até 90%": (0.70, 0.90),
    "A até 65% · B até 90%": (0.65, 0.90),
    "A até 50% · B até 80%": (0.50, 0.80),
}

BASES_ABC = {
    "Valor faturado (padrão)": ("valor_faturado", "Qtde. Fat."),
    "Valor pedido": ("valor_pedido", "Qtde. Ped."),
}


def salvar(p: Parametros, tentativas: int = 5) -> bool:
    """Grava as preferências em disco. Devolve False se não conseguiu.

    Grava num arquivo temporário e troca de uma vez (o arquivo nunca fica pela
    metade) e tenta de novo por alguns instantes: numa pasta sincronizada (OneDrive),
    o arquivo pode estar travado por um momento, e uma falha calada deixaria valendo
    a preferência anterior — por exemplo, os nomes originais ligados.
    """
    import time
    conteudo = json.dumps(asdict(p), indent=2, ensure_ascii=False)
    temporario = ARQUIVO_PREFS.with_suffix(".tmp")
    for tentativa in range(tentativas):
        try:
            ARQUIVO_PREFS.parent.mkdir(parents=True, exist_ok=True)
            temporario.write_text(conteudo, encoding="utf-8")
            temporario.replace(ARQUIVO_PREFS)
            return True
        except OSError:
            time.sleep(0.2 * (tentativa + 1))
    return False


def carregar() -> Parametros:
    """Lê as preferências salvas; volta ao padrão se o arquivo não existir."""
    p = Parametros()
    if not ARQUIVO_PREFS.exists():
        return p
    try:
        dados = json.loads(ARQUIVO_PREFS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return p
    validos = {f.name: f.type for f in fields(p)}
    for chave, valor in dados.items():
        if chave in validos:
            setattr(p, chave, valor)
    return p


def restaurar() -> Parametros:
    """Apaga o arquivo de preferências e devolve os valores de fábrica."""
    try:
        ARQUIVO_PREFS.unlink(missing_ok=True)
    except OSError:
        pass
    return Parametros()


_FORA_DOS_CONTROLES = {
    "corte_a": ("Corte da classe A", "pct"), "corte_b": ("Corte da classe B", "pct"),
    "base_abc": ("Base de valor da Curva ABC", "texto"),
    "data_referencia": ("Data de referência", "data"),
    "nomes_originais": ("Nomes originais", "sim/não"),
}


def descrever(campo: str) -> tuple[str, str]:
    """(rótulo, formato) de um parâmetro, como aparece na tela Preferências."""
    for _, controles in CONTROLES:
        for c, rot, _, _, _, _, fmt in controles:
            if c == campo:
                return rot, fmt
    return _FORA_DOS_CONTROLES.get(campo, (campo, "texto"))


def formatar(campo: str, valor) -> str:
    """Valor de um parâmetro em português: 12 meses, 40%, R$ 300, 0,50."""
    _, fmt = descrever(campo)
    if fmt == "pct":
        return f"{float(valor) * 100:.1f}%".replace(".", ",").replace(",0%", "%")
    if fmt == "moeda":
        return f"R$ {float(valor):,.0f}".replace(",", ".")
    if fmt == "vezes":
        return f"{float(valor):.2f}×".replace(".", ",")
    if fmt == "decimal":
        return f"{float(valor):.2f}".replace(".", ",")
    if fmt == "data":
        ano, mes, dia = str(valor)[:10].split("-")
        return f"{dia}/{mes}/{ano}"
    if fmt == "sim/não":
        return "sim" if valor else "não"
    if campo == "base_abc":
        return "valor faturado" if valor == "valor_faturado" else "valor pedido"
    if fmt == "texto":
        return str(valor)
    return f"{int(valor)} {fmt}"


def alterados(p: Parametros) -> list[str]:
    """Nomes dos parâmetros que estão fora do padrão de fábrica."""
    return [f.name for f in fields(p)
            if getattr(p, f.name) != getattr(PADRAO, f.name)]
