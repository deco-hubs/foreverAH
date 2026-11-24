@echo off
rem Updates the Forever Net Worth addon and its auction house prices. Point Task Scheduler at this file.
cd /d "%~dp0"
python sync_forever_addon.py
