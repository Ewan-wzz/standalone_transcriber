@echo off
cd /d "%~dp0"
XHSOfflineTranscriber.exe
if errorlevel 1 pause
