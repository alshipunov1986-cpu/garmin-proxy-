$ErrorActionPreference = "Stop"
$nssm = "C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$proxyDir = "D:\РџСЂРѕСЌРєС‚С‹ РљР»РѕРґ\garmin-proxy"
$python = "$proxyDir\.venv\Scripts\python.exe"

Write-Host "=== Installing NSSM Services ===" -ForegroundColor Green

# Read tokens
$garminTokens = Get-Content "$proxyDir\GARMIN_TOKENS.txt" -Raw
$anthropicKey = Get-Content "$proxyDir\.env.anthropic_key" -Raw

# Remove existing service if present
try { & $nssm stop GarminProxy 2>$null } catch {}
try { & $nssm remove GarminProxy confirm 2>$null } catch {}

Write-Host "[1/2] Installing GarminProxy..." -ForegroundColor Yellow

& $nssm install GarminProxy $python "app.py"
& $nssm set GarminProxy AppDirectory $proxyDir
& $nssm set GarminProxy DisplayName "Garmin Health Proxy"
& $nssm set GarminProxy Description "Flask proxy for Garmin health data with auto-restart"
& $nssm set GarminProxy Start SERVICE_AUTO_START
& $nssm set GarminProxy AppRestartDelay 5000
& $nssm set GarminProxy AppStdout "$proxyDir\proxy_service.log"
& $nssm set GarminProxy AppStderr "$proxyDir\proxy_error.log"
& $nssm set GarminProxy AppStdoutCreationDisposition 4
& $nssm set GarminProxy AppStderrCreationDisposition 4
& $nssm set GarminProxy AppRotateFiles 1
& $nssm set GarminProxy AppRotateBytes 1048576

# Set environment - each var on separate line
$envVars = @(
    "GARMIN_TOKENS=$($garminTokens.Trim())",
    "API_KEY=myhealthkey2026",
    "PORT=5001",
    "FATSECRET_CLIENT_ID=fddbfa79a1a94a1d929a5df4b09a2b12",
    "FATSECRET_CLIENT_SECRET=76f131b4e1664a0d8db59742072841a2",
    "FATSECRET_USER=al.shipunov1986@gmail.com",
    "FATSECRET_PASS=Al0634400474!",
    "ANTHROPIC_API_KEY=$($anthropicKey.Trim())"
)

# NSSM expects multi-string as null-separated
$envString = $envVars -join "`0"
& $nssm set GarminProxy AppEnvironmentExtra $envVars

& $nssm start GarminProxy
Write-Host "GarminProxy started!" -ForegroundColor Green

# TailscaleFunnel
try { & $nssm stop TailscaleFunnel 2>$null } catch {}
try { & $nssm remove TailscaleFunnel confirm 2>$null } catch {}

Write-Host "[2/2] Installing TailscaleFunnel..." -ForegroundColor Yellow

$tailscale = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $tailscale) { $tailscale = "C:\Program Files\Tailscale\tailscale.exe" }

& $nssm install TailscaleFunnel $tailscale "funnel 5001"
& $nssm set TailscaleFunnel DisplayName "Tailscale Funnel (port 5001)"
& $nssm set TailscaleFunnel Start SERVICE_AUTO_START
& $nssm set TailscaleFunnel AppRestartDelay 10000
& $nssm start TailscaleFunnel
Write-Host "TailscaleFunnel started!" -ForegroundColor Green

Write-Host ""
Write-Host "=== Done! Check: services.msc ===" -ForegroundColor Green
Write-Host "Test: curl http://localhost:5001/"
Write-Host ""
Read-Host "Press Enter to exit"
