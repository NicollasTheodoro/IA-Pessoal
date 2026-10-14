@echo off
rem Liga o desktop pet da Alice (e o servidor, se ainda nao estiver no ar).
cd /d "%~dp0"
python -c "import PySide6" 2>nul || (echo Instalando a biblioteca da janela, so na primeira vez... && python -m pip install -r requirements-pet.txt)
python IA\pet.py
pause
