@echo off
title Radar de Vagas
echo Abrindo o Radar de Vagas... o painel vai abrir no navegador.
echo Para encerrar, feche esta janela.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0abrir-interface.ps1"
if errorlevel 1 (
  echo.
  echo O Radar de Vagas encerrou com erro. Leia a mensagem acima.
  pause
)
