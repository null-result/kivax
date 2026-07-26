@echo off
REM Windows wrapper: the kivax CLI is a Python script; cmd.exe/PowerShell
REM don't interpret the shebang line, so we invoke it explicitly.
python "%~dp0kivax" %*
