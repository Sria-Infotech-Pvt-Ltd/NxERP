# Opens Chrome on the local NXDESK stacks (Docker). Run it from PowerShell, or double-click open-nxdesk-local.cmd.
#
# Why: the local front door (nginx, port 8180) picks the site from the NAME in the address, so a bare http://127.0.0.1:8180 answers 404 on purpose.
# This starts a separate Chrome window that maps *.example.test to the front door, so these addresses work in it:
#   http://id.example.test:8080/    the NXDESK front page and sign-in
#   http://hd.example.test:8080/    Sria Helpdesk
#   http://erp.example.test:8080/   NXERP
# Change $Port if your edge.env uses another NXERP_EDGE_PORT (default 8180). Nothing is installed or changed on the machine.
param([int]$Port = 8180, [string]$Start = "http://id.example.test:8080/")

$chrome = @(
	"$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
	"${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
	"$env:LocalAppData\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { Write-Error "Chrome was not found. Install Google Chrome, or use a hosts-file entry (docs/runbooks/local-docker-setup.md)."; exit 1 }

try { $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -Headers @{ Host = "id.example.test" } -UseBasicParsing -TimeoutSec 5 }
catch { Write-Warning "Nothing answers on 127.0.0.1:$Port. Start the stacks first (docs/runbooks/local-docker-setup.md, step 5) and check that Docker Desktop is running." }

$profile = Join-Path $env:TEMP "nxdesk-local-chrome"
Start-Process $chrome -ArgumentList @(
	"--host-resolver-rules=`"MAP *.example.test 127.0.0.1:$Port`"",
	"--no-proxy-server",
	"--disable-features=HttpsUpgrades",
	"--user-data-dir=$profile",
	"--new-window",
	$Start
)
Write-Host "Opened $Start in a separate Chrome window (the 'unsupported command-line flag' bar in it is harmless)."
