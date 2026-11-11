"""
Gera a Curva ABC dos medicamentos em Excel, sem abrir o painel.

Usa a mesma base, as mesmas regras e as mesmas preferências do SADPF
(dados/preferencias.json, se existir), então os números batem com a tela
Curva ABC. A planilha é a mesma do botão "Baixar Curva ABC (Excel)" da tela.

Uso (na pasta do projeto):
    .venv\\Scripts\\python.exe gerar_curva_abc.py                  # Windows
    .venv/bin/python gerar_curva_abc.py                           # macOS / Linux

Opções:
    --base pedido|faturado      valor que ordena a curva (padrão: o das Preferências)
    --inicio 01/01/2025         só compras a partir desta data
    --fim 31/12/2025            só compras até esta data
    --saida arquivo.xlsx        nome do arquivo (padrão: saidas/curva_abc.xlsx)

Exemplo: Curva ABC de 2025 pelo valor pedido
    .venv\\Scripts\\python.exe gerar_curva_abc.py --base pedido --inicio 01/01/2025 --fim 31/12/2025
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))

from core import dados as D             # noqa: E402
from core import metricas as M          # noqa: E402
from core import parametros as PR       # noqa: E402
from core.exportar import curva_abc_excel  # noqa: E402


def _data(texto: str | None):
    return pd.to_datetime(texto, dayfirst=True).date() if texto else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera a Curva ABC em Excel.")
    parser.add_argument("--base", choices=["pedido", "faturado"],
                        help="valor que ordena a curva")
    parser.add_argument("--inicio", help="data inicial, dd/mm/aaaa")
    parser.add_argument("--fim", help="data final, dd/mm/aaaa")
    parser.add_argument("--saida", default=str(RAIZ / "saidas" / "curva_abc.xlsx"),
                        help="arquivo .xlsx de saída")
    args = parser.parse_args()

    p = PR.carregar()
    if args.base:
        p.base_abc = "valor_pedido" if args.base == "pedido" else "valor_faturado"

    df, _ = D.carregar_base()
    df = D.aplicar_filtros(df, {"periodo": (_data(args.inicio), _data(args.fim))})
    if df.empty:
        print("Nenhuma compra no período informado.")
        sys.exit(1)

    abc = M.curva_abc(df, p)
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    curva_abc_excel(df, abc, p, saida)

    base_txt = "valor faturado" if p.base_abc == "valor_faturado" else "valor pedido"
    print(f"Curva ABC por {base_txt}, de {df['dt'].min():%d/%m/%Y} a {df['dt'].max():%d/%m/%Y}")
    for _, r in abc.classes.iterrows():
        print(f"  Classe {r['classe']}: {int(r['itens']):>4} medicamentos "
              f"({r['pct_itens']:.1%} do mix) · {r['pct_valor']:.1%} do valor")
    print(f"Arquivo gerado: {saida}")


if __name__ == "__main__":
    main()
