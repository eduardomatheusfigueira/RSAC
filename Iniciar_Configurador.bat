@echo off
title Iniciar Configurador de Revisão Sistemática
echo Iniciando o Configurador de Revisão Sistemática...
python config_app\main.py
if %errorlevel% neq 0 (
    echo.
    echo Ocorreu um erro ao tentar executar o configurador. Verifique se o Python está instalado e configurado nas variáveis de ambiente.
    pause
)
