@echo off
echo === Installing NSSM Services ===
echo.
echo This script must be run as Administrator!
echo Right-click → Run as administrator
echo.

set NSSM=C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe
set PROXY_DIR=D:\Проэкты Клод\garmin-proxy
set PYTHON=%PROXY_DIR%\.venv\Scripts\python.exe

:: Read env vars
set /p GARMIN_TOKENS=<%PROXY_DIR%\GARMIN_TOKENS.txt
set /p ANTHROPIC_API_KEY=<%PROXY_DIR%\.env.anthropic_key

:: === GarminProxy Service ===
echo [1/2] Installing GarminProxy service...
"%NSSM%" install GarminProxy "%PYTHON%" "app.py"
"%NSSM%" set GarminProxy AppDirectory "%PROXY_DIR%"
"%NSSM%" set GarminProxy DisplayName "Garmin Health Proxy"
"%NSSM%" set GarminProxy Description "Flask proxy for Garmin health data with auto-restart"
"%NSSM%" set GarminProxy Start SERVICE_AUTO_START
"%NSSM%" set GarminProxy AppRestartDelay 5000
"%NSSM%" set GarminProxy AppStdout "%PROXY_DIR%\proxy_service.log"
"%NSSM%" set GarminProxy AppStderr "%PROXY_DIR%\proxy_error.log"
"%NSSM%" set GarminProxy AppStdoutCreationDisposition 4
"%NSSM%" set GarminProxy AppStderrCreationDisposition 4
"%NSSM%" set GarminProxy AppRotateFiles 1
"%NSSM%" set GarminProxy AppRotateBytes 1048576

:: Set environment variables
"%NSSM%" set GarminProxy AppEnvironmentExtra ^
  GARMIN_TOKENS=%GARMIN_TOKENS% ^
  API_KEY=myhealthkey2026 ^
  PORT=5001 ^
  FATSECRET_CLIENT_ID=fddbfa79a1a94a1d929a5df4b09a2b12 ^
  FATSECRET_CLIENT_SECRET=76f131b4e1664a0d8db59742072841a2 ^
  FATSECRET_USER=al.shipunov1986@gmail.com ^
  FATSECRET_PASS=Al0634400474! ^
  ANTHROPIC_API_KEY=%ANTHROPIC_API_KEY%

:: Start the service
"%NSSM%" start GarminProxy
echo GarminProxy installed and started!
echo.

:: === TailscaleFunnel Service ===
echo [2/2] Installing TailscaleFunnel service...
"%NSSM%" install TailscaleFunnel "C:\Program Files\Tailscale\tailscale.exe" "funnel 5001"
"%NSSM%" set TailscaleFunnel DisplayName "Tailscale Funnel (port 5001)"
"%NSSM%" set TailscaleFunnel Description "Tailscale Funnel for Garmin proxy"
"%NSSM%" set TailscaleFunnel Start SERVICE_AUTO_START
"%NSSM%" set TailscaleFunnel AppRestartDelay 10000
"%NSSM%" start TailscaleFunnel
echo TailscaleFunnel installed and started!
echo.

echo === Done! Both services are running ===
echo.
echo To check status: services.msc → look for "Garmin Health Proxy"
echo To remove:  "%NSSM%" remove GarminProxy confirm
echo.
pause
