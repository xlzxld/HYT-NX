@echo off
setlocal

set "JOURNAL=%~dp0import_to_nx10.py"
set "RUNNER="

if defined UGII_BASE_DIR if exist "%UGII_BASE_DIR%\NXBIN\run_journal.exe" set "RUNNER=%UGII_BASE_DIR%\NXBIN\run_journal.exe"

if not defined RUNNER for %%D in ("C:\Program Files\Siemens\NX 8.0" "C:\Program Files\Siemens\NX 8.5" "C:\Program Files\Siemens\NX 9.0" "C:\Program Files\Siemens\NX 10.0" "C:\Program Files\Siemens\NX10.0" "C:\Program Files\Siemens\NX 11.0" "C:\Program Files\Siemens\NX 12.0" "C:\Program Files\Siemens\NX1847" "C:\Program Files\Siemens\NX1872" "C:\Program Files\Siemens\NX1899" "C:\Program Files\Siemens\NX1926" "C:\Program Files\Siemens\NX1953" "C:\Program Files\Siemens\NX1980" "C:\Program Files\Siemens\NX2007" "C:\Program Files\Siemens\NX2206" "C:\Program Files\Siemens\NX2306" "C:\Program Files\Siemens\NX2312") do if not defined RUNNER if exist "%%~D\NXBIN\run_journal.exe" set "RUNNER=%%~D\NXBIN\run_journal.exe"

if not defined RUNNER (
  echo.
  echo [ERROR] NX run_journal.exe not found.
  echo.
  echo Alternative: open NX, then
  echo   File ^-^> Execute ^-^> NX Open ... and pick import_to_nx10.py
  echo.
  pause
  exit /b 1
)

echo NX runner : "%RUNNER%"
echo Journal   : "%JOURNAL%"
echo.
"%RUNNER%" "%JOURNAL%"
echo.
echo Done. See import_log.txt, output folder ..\NX10_prt
echo.
pause
