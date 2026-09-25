@echo off
chcp 65001 >nul
cd /d "%~dp0"
python scripts\bootstrap-local-classroom.py
if errorlevel 1 pause
