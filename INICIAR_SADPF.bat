@echo off
rem SADPF - instala na primeira vez e abre o painel no navegador.
rem Basta dar dois cliques neste arquivo. Requer Python 3.10 ou superior.
chcp 65001 >nul
cd /d "%~dp0"
title SADPF - Sistema de Apoio a Decisao

if exist ".venv\instalado.ok" goto executar

echo.
echo  Primeira execucao: preparando o ambiente (precisa de internet, alguns minutos).
echo.
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  Python nao encontrado. Instale em https://www.python.org/downloads/
  echo  marcando a opcao "Add python.exe to PATH", e rode este arquivo de novo.
  echo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  Falha ao instalar as bibliotecas. Verifique a internet e rode de novo.
  echo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" verificar.py
echo ok> ".venv\instalado.ok"

:executar
echo.
echo  Abrindo o SADPF no navegador: http://localhost:8501
echo  Acesso padrao: empresa Farmacia, senha 123
echo  Para encerrar, feche esta janela.
echo.
rem headless: sem a pergunta de e-mail do Streamlit na primeira execucao;
rem o navegador e aberto aqui, alguns segundos depois de o servidor subir
start "" /b ".venv\Scripts\python.exe" -c "import time, webbrowser; time.sleep(6); webbrowser.open('http://localhost:8501')"
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true
pause
