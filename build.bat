@echo off
title RSAC - Build Executável
echo ============================================
echo   RSAC - Construindo Executável Único
echo ============================================
echo.
echo Limpando builds anteriores...
if exist "dist\RSAC.exe" del /f "dist\RSAC.exe"
echo.
echo Executando PyInstaller...
pyinstaller --clean ConfiguradorRevisao.spec
echo.
if exist "dist\RSAC.exe" (
    echo ============================================
    echo   BUILD CONCLUÍDO COM SUCESSO!
    echo   Executável: dist\RSAC.exe
    echo ============================================
) else (
    echo ============================================
    echo   ERRO: Build falhou. Verifique os logs.
    echo ============================================
)
echo.
pause
