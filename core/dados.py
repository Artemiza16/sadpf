"""
Camada de dados do SADPF.

Responde por três coisas:
  1. ler a planilha de cotações e criar as colunas derivadas;
  2. aplicar as regras de limpeza (status, prefixos, correções de cadastro);
  3. receber cotações novas, validar e mesclar na base consolidada.

A base consolidada mora em dados/base_consolidada.csv. É ela que o painel lê.
A planilha original fica intacta.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

PASTA_DADOS = Path(__file__).parent.parent / "dados"
BASE_CONSOLIDADA = PASTA_DADOS / "base_consolidada.csv"
BASE_ORIGINAL = PASTA_DADOS / "cotacao_06_09.xlsx"
PASTA_HISTORICO = PASTA_DADOS / "historico"
ARQUIVO_APELIDOS = PASTA_DADOS / "apelidos.json"

# Campos que identificam a origem dos dados e o prefixo do código que os substitui
# quando os nomes originais estão ocultos (aba Preferências).
CAMPOS_APELIDO = {"Nome do Fornecedor": "Fornecedor", "Representante": "Representante"}

# ---------------------------------------------------------------------------
#                                  REGRAS
# ---------------------------------------------------------------------------
# Só estes status entram na análise. Lista vazia = considera todos.
# Atenção: as linhas com corte de faturamento vivem em "Enviado" e
# "Faturado Parcialmente" — removê-los leva o nível de atendimento a 100%.
STATUS_MANTIDOS = ["Faturado"]

# Prefixos de lixo no início da descrição do produto (regex).
PREFIXOS_REMOVER = [r"^#\s*-\s*"]

# Correções pontuais de cadastro.
CORRECOES = [
    {
        "motivo": "o nome do produto tinha sido gravado na coluna Fabricante; "
                  "a descrição ficou com um código solto",
        "onde": {"Descrição do Produto": "3604"},
        "para": {
            "Descrição do Produto": "AZITROMICINA 1500MG PO SUS OR FR+FLAC SOL "
                                    "DILX22ML+SER DOS EUROFARMA GEN",
            "Fabricante": "EUROFARMA",
        },
    },
]

COLUNAS_OBRIGATORIAS = [
    "Cotação", "Pedido", "Status do Pedido", "Data de Criação",
    "Nome do Fornecedor", "Representante", "Código do Produto",
    "Descrição do Produto", "Fabricante", "Qtde. Ped.", "Qtde. Fat.",
    "Vl. Custo (R$)", "Vl. Faturado (R$)", "Forma Farmacêutica",
    "Categoria Comercial", "Data de Validade", "Faixa de Recebimento",
    "Preço de Venda Unitário (R$)", "M/L",
]

# Identidade de uma linha: mesma cotação, pedido e produto.
CHAVE = ["Cotação", "Pedido", "Código do Produto"]

FAIXAS_CURTAS = ["Curto (30-50%)", "Crítico (<30%)"]
ORDEM_FAIXAS = ["Fresco (≥70%)", "Normal (50-70%)", "Curto (30-50%)", "Crítico (<30%)"]


# ---------------------------------------------------------------------------
#                                  LEITURA
# ---------------------------------------------------------------------------
COLUNAS_DATA = ["Data de Criação", "Data de Validade", "Data de Fabricação"]
_ORIGEM_EXCEL = pd.Timestamp("1899-12-30")


def _de_serial(serie: pd.Series) -> pd.Series:
    """Serial do Excel → data, arredondada ao segundo.

    O serial é um número com casas decimais para as horas; a ida e volta pelo
    ponto flutuante faria 09:30 voltar como 09:29:59,9999.
    """
    return pd.to_datetime(serie, unit="D", origin="1899-12-30").dt.round("s")


def _para_data(serie: pd.Series) -> pd.Series:
    """Converte a coluna de data, venha ela como serial do Excel, data ou texto.

    Cada valor é tratado pelo que é. Isso importa quando uma cotação nova chega
    com datas de verdade e a base guarda seriais do Excel: convertida em bloco,
    a coluna mista faria o pandas ler os seriais como nanossegundos (ano 1970).
    """
    if pd.api.types.is_numeric_dtype(serie):
        return _de_serial(serie)
    if pd.api.types.is_datetime64_any_dtype(serie):
        return pd.to_datetime(serie)

    # serial do Excel que chegou como texto, inclusive com vírgula decimal
    numeros = pd.to_numeric(serie.astype(str).str.strip().str.replace(",", ".", regex=False),
                            errors="coerce")
    serial = numeros.between(1, 2958465)          # 1900-01-01 a 9999-12-31
    resultado = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")
    if serial.any():
        resultado[serial] = _de_serial(numeros[serial])
    resto = ~serial & serie.notna()
    if resto.any():
        valores = serie[resto]
        eh_data = valores.map(lambda v: isinstance(v, (pd.Timestamp, datetime)))
        if eh_data.any():
            resultado[valores[eh_data].index] = pd.to_datetime(valores[eh_data])
        texto = valores[~eh_data].astype(str).str.strip()
        if len(texto):
            iso = texto.str.match(r"^\d{4}-\d{2}-\d{2}")
            resultado[texto[iso].index] = pd.to_datetime(texto[iso], errors="coerce")
            resultado[texto[~iso].index] = pd.to_datetime(texto[~iso], errors="coerce",
                                                          dayfirst=True)
    return resultado


def _para_serial(serie: pd.Series) -> pd.Series:
    """Data em qualquer formato → serial do Excel, o formato em que a base é gravada."""
    datas = _para_data(serie)
    return (datas - _ORIGEM_EXCEL) / pd.Timedelta(days=1)


def texto_chave(serie: pd.Series) -> pd.Series:
    """Valor de identificação como texto limpo: '12200476.0' e 12200476 viram o mesmo."""
    return (serie.astype("string").fillna("").str.strip()
            .str.replace(r"\.0+$", "", regex=True))


def chave_linha(df: pd.DataFrame) -> pd.Series:
    """Identidade de uma linha: cotação | pedido | produto, já normalizados."""
    return texto_chave(df["Cotação"]) + "|" + texto_chave(df["Pedido"]) + "|" + \
        texto_chave(df["Código do Produto"])


def ler_arquivo(origem) -> pd.DataFrame:
    """Lê xlsx ou csv e valida as colunas. Aceita caminho ou objeto de upload."""
    nome = getattr(origem, "name", str(origem))
    if str(nome).lower().endswith(".csv"):
        df = pd.read_csv(origem, sep=";", decimal=",", encoding="utf-8-sig")
    else:
        df = pd.read_excel(origem)

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError("Faltam colunas na planilha: " + ", ".join(faltando))
    return df


def limpar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Aplica correções, prefixos e filtro de status. Devolve o log do que mudou."""
    df = df.copy()
    log: list[str] = []
    antes = len(df)

    for corr in CORRECOES:
        mask = pd.Series(True, index=df.index)
        for col, val in corr["onde"].items():
            mask &= df[col].astype(str).str.strip() == str(val)
        if mask.any():
            for col, val in corr["para"].items():
                df.loc[mask, col] = val
            alvo = list(corr["onde"].values())[0]
            log.append(f"corrigido '{alvo}' em {int(mask.sum())} linha(s) — {corr['motivo']}")

    for padrao in PREFIXOS_REMOVER:
        n = int(df["Descrição do Produto"].astype(str).str.match(padrao).sum())
        if n:
            df["Descrição do Produto"] = (
                df["Descrição do Produto"].astype(str)
                .str.replace(padrao, "", regex=True).str.strip()
            )
            log.append(f"prefixo {padrao!r} removido de {n} linha(s)")

    if STATUS_MANTIDOS:
        status = df["Status do Pedido"].astype(str).str.strip()
        for st, qtd in status[~status.isin(STATUS_MANTIDOS)].value_counts().items():
            log.append(f"removidas {qtd} linha(s) com status '{st}'")
        df = df[status.isin(STATUS_MANTIDOS)].copy()

    # datas sempre como serial do Excel, o mesmo formato da base: assim uma
    # cotação com datas em texto não deixa a coluna com formatos misturados
    for coluna in COLUNAS_DATA:
        if coluna in df.columns and not pd.api.types.is_numeric_dtype(df[coluna]):
            convertidas = _para_serial(df[coluna])
            falhas = int((convertidas.isna() & df[coluna].notna()).sum())
            df[coluna] = convertidas
            if falhas:
                log.append(f"{falhas} data(s) ilegível(is) em '{coluna}' ficaram em branco")

    log.append(f"{antes} linhas na origem → {len(df)} após a limpeza")
    return df.reset_index(drop=True), log


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Cria as colunas derivadas usadas por todo o sistema."""
    df = df.copy()
    df["dt"] = _para_data(df["Data de Criação"])
    df["validade"] = _para_data(df["Data de Validade"])
    if "Data de Fabricação" in df.columns:
        df["fabricacao"] = _para_data(df["Data de Fabricação"])

    df["valor_pedido"] = df["Qtde. Ped."] * df["Vl. Custo (R$)"]
    df["valor_faturado"] = df["Qtde. Fat."] * df["Vl. Faturado (R$)"]

    preco = df["Preço de Venda Unitário (R$)"].replace(0, pd.NA)
    df["margem"] = (preco - df["Vl. Custo (R$)"]) / preco

    df["ano_mes"] = df["dt"].dt.to_period("M").astype(str)
    df["mes"] = df["dt"].dt.month
    df["validade_curta"] = df["Faixa de Recebimento"].isin(FAIXAS_CURTAS)
    df["fornecedor"] = df["Nome do Fornecedor"].astype(str).str.strip()
    df["medicamento"] = df["Descrição do Produto"].astype(str).str.strip()
    df["sku"] = texto_chave(df["Código do Produto"])

    return df.sort_values("dt", kind="stable").reset_index(drop=True)


def versao_base() -> float:
    """Marca de tempo do arquivo da base; muda sempre que a base é regravada."""
    try:
        return BASE_CONSOLIDADA.stat().st_mtime
    except OSError:
        return 0.0


def carregar_base() -> tuple[pd.DataFrame, str]:
    """Lê a base consolidada; se não existir, cria a partir da planilha original."""
    if BASE_CONSOLIDADA.exists():
        bruto = ler_arquivo(BASE_CONSOLIDADA)
        return preparar(bruto), "base consolidada"
    bruto, _ = limpar(ler_arquivo(BASE_ORIGINAL))
    gravar_base(bruto)
    return preparar(bruto), "planilha original"


COLUNAS_DERIVADAS = ["dt", "validade", "fabricacao", "valor_pedido", "valor_faturado",
                     "margem", "ano_mes", "mes", "validade_curta", "fornecedor",
                     "medicamento", "sku"]


def gravar_base(df: pd.DataFrame) -> None:
    """Salva a base consolidada, sem as colunas derivadas."""
    saida = df.drop(columns=[c for c in COLUNAS_DERIVADAS if c in df.columns])
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    saida.to_csv(BASE_CONSOLIDADA, index=False, sep=";", decimal=",", encoding="utf-8-sig")


# ---------------------------------------------------------------------------
#                       INGESTÃO DE NOVAS COTAÇÕES
# ---------------------------------------------------------------------------
@dataclass
class Previa:
    """O que aconteceria ao mesclar um arquivo novo, antes de confirmar."""
    novas: pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicadas: pd.DataFrame = field(default_factory=pd.DataFrame)
    log_limpeza: list[str] = field(default_factory=list)
    cotacoes_novas: list = field(default_factory=list)
    cotacoes_existentes: list = field(default_factory=list)
    erro: str = ""

    @property
    def ok(self) -> bool:
        return not self.erro and len(self.novas) > 0


def analisar_entrada(origem, base: pd.DataFrame) -> Previa:
    """Lê um arquivo de cotações novas e mostra o que entraria na base.

    Nada é gravado aqui: a ideia é que a gestora veja o efeito antes de
    confirmar. A duplicidade é verificada por cotação + pedido + produto, que é
    o que identifica uma linha de forma única.
    """
    try:
        bruto = ler_arquivo(origem)
    except (ValueError, OSError) as erro:
        return Previa(erro=str(erro))
    except Exception as erro:            # planilha corrompida, aba errada etc.
        return Previa(erro=f"não foi possível ler o arquivo: {erro}")

    limpo, log = limpar(bruto)
    if limpo.empty:
        return Previa(log_limpeza=log,
                      erro="nenhuma linha sobrou depois das regras de limpeza "
                           f"(status mantidos: {', '.join(STATUS_MANTIDOS) or 'todos'})")

    existentes = set(chave_linha(base))
    k = chave_linha(limpo)
    repetidas_no_arquivo = k.duplicated(keep="first")
    if repetidas_no_arquivo.any():
        log.append(f"{int(repetidas_no_arquivo.sum())} linha(s) repetida(s) dentro do próprio "
                   "arquivo foram consideradas uma vez só")
    novas = limpo[~k.isin(existentes) & ~repetidas_no_arquivo].copy()
    duplicadas = limpo[k.isin(existentes)].copy()

    cot_base = set(texto_chave(base["Cotação"]))
    cot_arq = texto_chave(limpo["Cotação"])

    return Previa(
        novas=novas, duplicadas=duplicadas, log_limpeza=log,
        cotacoes_novas=sorted(set(cot_arq[~cot_arq.isin(cot_base)])),
        cotacoes_existentes=sorted(set(cot_arq[cot_arq.isin(cot_base)])),
    )


def mesclar(base: pd.DataFrame, novas: pd.DataFrame) -> pd.DataFrame:
    """Junta as linhas novas à base, grava e devolve a base preparada.

    Antes de gravar, guarda uma cópia da base anterior em dados/historico/,
    para que uma inclusão errada possa ser desfeita.
    """
    _guardar_copia()

    # só as colunas de origem entram; as derivadas são recalculadas por preparar()
    colunas = [c for c in base.columns if c not in COLUNAS_DERIVADAS]
    novas = novas.copy()
    for c in colunas:
        if c not in novas.columns:
            novas[c] = pd.NA
    # a base guarda a cotação e o pedido como números: a linha nova segue o mesmo tipo
    for c in ("Cotação", "Pedido"):
        if pd.api.types.is_numeric_dtype(base[c]):
            convertido = pd.to_numeric(texto_chave(novas[c]), errors="coerce")
            if convertido.notna().all():
                novas[c] = convertido.astype(base[c].dtype)

    juntas = pd.concat([base[colunas], novas[colunas]], ignore_index=True)
    juntas = juntas[~chave_linha(juntas).duplicated(keep="first")]
    gravar_base(juntas)
    return preparar(juntas)


def _guardar_copia() -> None:
    """Guarda a base atual em dados/historico/ antes de qualquer regravação."""
    if not BASE_CONSOLIDADA.exists():
        return
    PASTA_HISTORICO.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destino = PASTA_HISTORICO / f"base-{carimbo}.csv"
    destino.write_bytes(BASE_CONSOLIDADA.read_bytes())


def versoes_anteriores() -> list[Path]:
    """Cópias da base guardadas antes de cada inclusão, da mais recente."""
    if not PASTA_HISTORICO.exists():
        return []
    return sorted(PASTA_HISTORICO.glob("base-*.csv"), reverse=True)


def restaurar_versao(caminho: Path) -> pd.DataFrame:
    """Volta a base para uma versão anterior.

    A base atual também é guardada antes, para que a própria restauração
    possa ser desfeita.
    """
    conteudo = Path(caminho).read_bytes()
    _guardar_copia()
    BASE_CONSOLIDADA.write_bytes(conteudo)
    return preparar(ler_arquivo(BASE_CONSOLIDADA))


# ---------------------------------------------------------------------------
#                          NOMES CODIFICADOS (APELIDOS)
# ---------------------------------------------------------------------------
def _rotulo(prefixo: str, n: int) -> str:
    """0 → 'Fornecedor A', 26 → 'Fornecedor AA'; representantes numerados."""
    if prefixo != "Fornecedor":
        return f"{prefixo} {n + 1:02d}"
    letras = ""
    while True:
        letras = chr(65 + n % 26) + letras
        n = n // 26 - 1
        if n < 0:
            return f"{prefixo} {letras}"


def apelidos(df: pd.DataFrame) -> dict[str, dict[str, str]]:
    """Código fixo para cada fornecedor e representante, gravado em dados/apelidos.json.

    O primeiro código vai para quem tem o maior valor comprado. Nomes novos,
    vindos de uma cotação incluída depois, recebem o próximo código livre: os já
    atribuídos nunca mudam, para que um mesmo fornecedor não troque de nome entre
    uma apresentação e outra.
    """
    try:
        salvos = json.loads(ARQUIVO_APELIDOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        salvos = {}
    mudou = False
    for coluna, prefixo in CAMPOS_APELIDO.items():
        mapa = salvos.setdefault(coluna, {})
        ordem = (df.assign(_nome=df[coluna].astype(str).str.strip())
                   .groupby("_nome")["valor_pedido"].sum()
                   .sort_values(ascending=False).index)
        for nome in ordem:
            if nome not in mapa:
                mapa[nome] = _rotulo(prefixo, len(mapa))
                mudou = True
    if mudou:
        try:
            PASTA_DADOS.mkdir(parents=True, exist_ok=True)
            ARQUIVO_APELIDOS.write_text(json.dumps(salvos, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
        except OSError:
            pass          # sem gravação, os códigos valem só nesta execução
    return salvos


def anonimizar(df: pd.DataFrame, mapas: dict[str, dict[str, str]]) -> pd.DataFrame:
    """Cópia da base com fornecedores e representantes trocados pelos códigos."""
    df = df.copy()
    for coluna in CAMPOS_APELIDO:
        nomes = df[coluna].astype(str).str.strip()
        df[coluna] = nomes.map(mapas.get(coluna, {})).fillna(nomes)
    df["fornecedor"] = df["Nome do Fornecedor"]
    # o CNPJ identificaria o fornecedor tanto quanto o nome
    return df.drop(columns=["CNPJ Fornecedor"], errors="ignore")


# ---------------------------------------------------------------------------
#                                  FILTROS
# ---------------------------------------------------------------------------
def _sem_acento(valor) -> str:
    """Chave de ordenação que ignora acentuação, para 'Não' não cair no fim."""
    texto = unicodedata.normalize("NFKD", str(valor))
    return texto.encode("ASCII", "ignore").decode().casefold()


def opcoes(df: pd.DataFrame, coluna: str) -> list:
    """Valores distintos de uma coluna, em ordem alfabética pt-BR."""
    return sorted(df[coluna].dropna().unique().tolist(), key=_sem_acento)


def aplicar_filtros(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """Aplica os filtros globais. Lista vazia significa 'todos'."""
    recorte = df
    inicio, fim = filtros.get("periodo", (None, None))
    if inicio is not None:
        recorte = recorte[recorte["dt"] >= pd.Timestamp(inicio)]
    if fim is not None:
        recorte = recorte[recorte["dt"] < pd.Timestamp(fim) + pd.Timedelta(days=1)]

    mapa = {
        "categorias": "Categoria Comercial", "cotacoes": "Cotação",
        "formas": "Forma Farmacêutica", "fornecedores": "Nome do Fornecedor",
        "medicamentos": "Descrição do Produto", "status": "Status do Pedido",
    }
    for chave, coluna in mapa.items():
        sel = filtros.get(chave) or []
        if sel:
            recorte = recorte[recorte[coluna].isin(sel)]
    return recorte
