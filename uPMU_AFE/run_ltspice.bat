@echo off
REM Corre toda la simulacion del front-end analogico del uPMU.
REM Regenera los netlists y el esquematico desde codigo\params.py, los pasa por
REM LTspice en modo batch (-b) y deja resultados y graficas en este arbol.
REM
REM Si LTspice no esta en la ruta por defecto, define LTSPICE antes de llamar:
REM    set LTSPICE=C:\ruta\a\LTspice.exe
cd /d "%~dp0"

echo [1/3] LTspice: AC, transitorios, clamps, muestreo del ADC y Monte Carlo
python codigo\run_ltspice.py || goto :err

echo.
echo [2/3] Cadena completa: firmware de hoy y compensacion propuesta
python codigo\simulate_chain.py          > resultados\results_chain.txt       || goto :err
python codigo\simulate_chain.py --ct-nom > resultados\results_chain_ctnom.txt || goto :err

echo.
echo [3/3] Hojas del esquematico y diagrama de la cadena
python codigo\draw_sheet1.py || goto :err
python codigo\draw_sheet2.py || goto :err
python codigo\draw_sheet3.py || goto :err
python codigo\draw_cadena.py || goto :err

echo.
echo Listo.
echo   resultados\results_ltspice.txt   AC, transitorio, clamps, ADC, Monte Carlo
echo   resultados\results_chain*.txt    cadena completa (firmware actual y propuesta)
echo   figuras\                         graficas y hojas del esquematico en PNG
echo   docs\                            hojas del esquematico en PDF
echo   netlists\uPMU_AFE.asc            el circuito, para abrirlo en LTspice
goto :eof

:err
echo.
echo FALLO. Revisa que python, numpy, matplotlib y LTspice esten disponibles.
exit /b 1
