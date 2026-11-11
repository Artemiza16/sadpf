@echo off
rem SADPF - gera a Curva ABC em Excel (saidas\curva_abc.xlsx) e abre o arquivo.
rem Usa a base inteira e as preferencias salvas no painel.
chcp 65001 >nul
cd /d "%~dp0"
title SADPF - Curva ABC

if not exist ".venv\instalado.ok" (
  echo.
  echo  O ambiente ainda nao foi instalado. Rode primeiro o INICIAR_SADPF.bat
  echo  ^(ele instala tudo na primeira vez^) e depois volte a este arquivo.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" gerar_curva_abc.py
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "saidas\curva_abc.xlsx"
echo.
pause
