@echo off
echo Administrative permissions required. Detecting permissions...

net session >nul 2>&1
if %errorLevel% == 0 (
	echo Success: Administrative permissions confirmed.
) else (
	echo Failure: Current permissions inadequate. Press [ENTER] to quit this script.
	pause >nul
	goto :eof
)

Powershell -nologo -noexit -executionpolicy bypass -File .\uninstall-client.ps1
