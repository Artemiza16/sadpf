#!/usr/bin/env bash
# SADPF - instala na primeira vez e abre o painel no navegador (macOS / Linux).
# Uso: abra o Terminal nesta pasta e rode:  bash iniciar_sadpf.sh
set -e
cd "$(dirname "$0")"

if [ ! -f ".venv/instalado.ok" ]; then
  echo "Primeira execução: preparando o ambiente (precisa de internet, alguns minutos)."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python verificar.py
  echo ok > .venv/instalado.ok
fi

echo "Abrindo o SADPF em http://localhost:8501 (acesso padrão: Farmacia / 123)."
echo "Para encerrar, pressione Ctrl+C."
# headless: sem a pergunta de e-mail do Streamlit; o navegador abre logo depois
( sleep 6; .venv/bin/python -m webbrowser http://localhost:8501 >/dev/null 2>&1 ) &
.venv/bin/python -m streamlit run app.py --server.headless true
