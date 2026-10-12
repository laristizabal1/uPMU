@echo off
REM Corre todos los netlists en LTspice en modo batch (-b) y recoge resultados.
REM Si LTspice no esta en la ruta de abajo, define LTSPICE antes de llamar:
REM    set LTSPICE=C:\ruta\a\LTspice.exe
cd /d "%~dp0"

python make_netlists.py || goto :err
python run_ltspice.py   || goto :err
python compare_sims.py --no-run

echo.
echo Listo. Resultados en results_ltspice.txt y en los PNG ltspice_*.png
goto :eof

:err
echo.
echo FALLO. Revisa que python, numpy, matplotlib y LTspice esten disponibles.
exit /b 1
