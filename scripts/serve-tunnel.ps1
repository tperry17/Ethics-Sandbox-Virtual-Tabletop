<#
.SYNOPSIS
Serve the Ethics Sandbox from this Windows computer to anyone on the
internet, through a Cloudflare tunnel.

.DESCRIPTION
The Windows counterpart of scripts/deploy.sh and scripts/serve-tunnel.sh.
It updates to the latest main, installs dependencies, runs the checks,
builds the table client, migrates its own database, opens a tunnel, and
serves on the tunnel's address, which every invite link carries. Ctrl-C
stops the server and the tunnel together.

With a named tunnel set up (-SetUpNamedTunnel, which writes
.sandbox-tunnel-url and .sandbox-tunnel-token), the address is the same
every time. Without one, it opens a quick tunnel, whose
https://<random words>.trycloudflare.com address is new every time.

Like deploy.sh, it keeps its own database (ethics-sandbox-live.db) and
cookie secret (.sandbox-secret), so a restart keeps every room.

Run it with scripts\serve-tunnel.cmd, which starts it whatever Windows'
script policy is.

.PARAMETER SkipChecks
Skip Ruff, mypy and pytest.

.PARAMETER NoPull
Serve the checkout as it is, without switching to and updating main.

.PARAMETER Port
The local port to serve on (default 8000).

.PARAMETER Quick
Open a quick tunnel even when a named tunnel is set up.

.PARAMETER SetUpNamedTunnel
Ask for a named tunnel's address and token, store them, and stop. Every
later start then uses that tunnel.
#>
[CmdletBinding()]
param(
    [switch]$SkipChecks,
    [switch]$NoPull,
    [int]$Port = 8000,
    [switch]$Quick,
    [switch]$SetUpNamedTunnel,
    # Set when the script restarts itself after updating main.
    [switch]$Updated
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host "==> $Text"
}

# Run a program and stop the script if it fails.
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "'$Program $($Arguments -join ' ')' failed (exit code $LASTEXITCODE)."
    }
}

function Assert-Command([string]$Name, [string]$Install) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing '$Name'. Install it with: $Install"
    }
}

# Whether a program starts and succeeds, with its output thrown away.
function Test-Runs([string]$Program, [string[]]$Arguments) {
    if (-not (Test-Path $Program)) { return $false }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Program @Arguments *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previous
    }
}

# Read a file another process is still writing.
function Read-SharedText([string]$Path) {
    if (-not (Test-Path $Path)) { return '' }
    try {
        $stream = [System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        try {
            $reader = New-Object System.IO.StreamReader($stream)
            return $reader.ReadToEnd()
        } finally {
            $stream.Dispose()
        }
    } catch [System.IO.IOException] {
        return ''
    }
}

# Keep Windows from sleeping while this script runs (not the screen).
function Set-KeepAwake([bool]$On) {
    try {
        if (-not ('SandboxPower.Native' -as [type])) {
            Add-Type -Namespace SandboxPower -Name Native -MemberDefinition @'
[DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
        }
        # ES_CONTINUOUS (0x80000000), plus ES_SYSTEM_REQUIRED (0x1) when on.
        $flags = [uint32]2147483648
        if ($On) { $flags = [uint32]2147483649 }
        [void][SandboxPower.Native]::SetThreadExecutionState($flags)
    } catch {
        Write-Warning "Could not keep the computer awake: $($_.Exception.Message)"
    }
}

Assert-Command git 'winget install --id Git.Git'
Assert-Command uv 'winget install --id astral-sh.uv'
Assert-Command npm.cmd 'winget install --id OpenJS.NodeJS.LTS'
Assert-Command cloudflared 'winget install --id Cloudflare.cloudflared'

# A named tunnel: its address, and its token, which cloudflared reads from
# the file so that it never appears in a process list.
$urlFile = Join-Path $ProjectRoot '.sandbox-tunnel-url'
$tokenFile = Join-Path $ProjectRoot '.sandbox-tunnel-token'

if ($SetUpNamedTunnel) {
    Write-Host 'The address people will open, as set up in Cloudflare (for example'
    Write-Host 'https://sandbox.example.org):'
    $address = ([string](Read-Host)).Trim().TrimEnd('/')
    if (-not $address) { throw 'No address given; nothing changed.' }
    if ($address -like 'http://*') { throw 'The address must start with https://.' }
    if ($address -notlike 'https://*') { $address = "https://$address" }
    Write-Host "The tunnel's token (Cloudflare shows it when the tunnel is made; it"
    Write-Host 'is not shown as you paste it):'
    $secure = Read-Host -AsSecureString
    $token = [System.Net.NetworkCredential]::new('', $secure).Password
    # A tunnel token is base64 of a JSON object, so it begins "eyJ". Take it
    # out of whatever was pasted: the token alone, or any of the commands
    # Cloudflare shows around it ("cloudflared.exe service install <token>",
    # "cloudflared tunnel run --token <token>", the docker line).
    $found = [regex]::Match(($token -replace '\s', ''), 'eyJ[A-Za-z0-9+/_=-]{20,}')
    if (-not $found.Success) { throw 'That has no tunnel token in it (a token begins "eyJ"); nothing changed.' }
    $token = $found.Value
    [System.IO.File]::WriteAllText($urlFile, $address)
    [System.IO.File]::WriteAllText($tokenFile, $token)
    Write-Host "Saved $urlFile and $tokenFile."
    Write-Host "In Cloudflare, the tunnel's published application route must point to http://localhost:$Port."
    exit 0
}

$named = $false
if (-not $Quick -and ((Test-Path $urlFile) -or (Test-Path $tokenFile))) {
    if (-not ((Test-Path $urlFile) -and (Test-Path $tokenFile))) {
        throw "A named tunnel needs both $urlFile and $tokenFile. Run scripts\serve-tunnel.cmd -SetUpNamedTunnel, or add -Quick for a quick tunnel."
    }
    $named = $true
}

if (-not $NoPull -and -not $Updated) {
    Write-Step 'Updating to the latest main'
    $changes = git status --porcelain --untracked-files=no
    if ($changes) {
        Write-Host ($changes -join "`n")
        throw 'This checkout has uncommitted changes, so it was not switched to main. Commit or discard them, or run with -NoPull to serve it as it is.'
    }
    Invoke-Checked git @('fetch', 'origin', 'main')
    Invoke-Checked git @('checkout', 'main')
    Invoke-Checked git @('merge', '--ff-only', 'origin/main')
    # Run the version of this script that just arrived, not the one in memory.
    $again = @{ Port = $Port; Updated = $true }
    if ($SkipChecks) { $again['SkipChecks'] = $true }
    if ($Quick) { $again['Quick'] = $true }
    & $PSCommandPath @again
    exit $LASTEXITCODE
}

Write-Step "Stopping anything an earlier run left on port $Port"
# Closing the window or VS Code's "Terminate Task" can end this script
# before it stops what it started. Its server and quick tunnel are known by
# their command lines, which nothing else shares: the app's module and this
# port, the exact quick-tunnel arguments below, and this checkout's pid
# file. Another Cloudflare tunnel on this computer does not match and is
# left alone. The named tunnel's token goes to cloudflared in its
# TUNNEL_TOKEN environment variable, which every cloudflared that runs a
# tunnel by token reads, and so stays out of the command line.
$quickArguments = "tunnel --no-autoupdate --url http://localhost:$Port"
$pidFile = Join-Path $ProjectRoot '.sandbox-tunnel.pid'
$namedArguments = "tunnel --no-autoupdate run --pidfile `"$pidFile`""
$leftovers = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $line = [string]$_.CommandLine
    ($line -like '*sandbox.web.app:app*' -and $line -like "*--port $Port*") -or
    ($_.Name -eq 'cloudflared.exe' -and $line -like "*$quickArguments*") -or
    ($_.Name -eq 'cloudflared.exe' -and $line.Contains("--pidfile `"$pidFile`""))
})
if ($leftovers.Count -eq 0) {
    Write-Host 'Nothing left over.'
}
foreach ($leftover in $leftovers) {
    Write-Host "Stopping an earlier run's $($leftover.Name) (process $($leftover.ProcessId))."
    Stop-Process -Id $leftover.ProcessId -Force -ErrorAction SilentlyContinue
}
foreach ($leftover in $leftovers) {
    Wait-Process -Id $leftover.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
}

Write-Step "Checking that port $Port is free"
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($owner in $owners) {
        $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
        $name = if ($process) { $process.ProcessName } else { 'an unknown program' }
        throw "Port $Port is already in use by $name (process $owner), which is not an earlier run of this script. Close that program, or run with -Port 8001."
    }
}
Write-Host 'Free.'

Write-Step 'Installing Python and client dependencies'
# A virtualenv activated in this terminal must not stand in for the project's.
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
# A .venv moved or copied from another folder keeps that folder's path in its
# program launchers (uv says "trampoline failed to canonicalize script path").
# Rebuild it rather than reuse it.
$venv = Join-Path $ProjectRoot '.venv'
if ((Test-Path $venv) -and -not (Test-Runs (Join-Path $venv 'Scripts\pytest.exe') @('--version'))) {
    Write-Host 'The .venv here was built for another folder; rebuilding it.'
    try {
        Remove-Item -Recurse -Force $venv
    } catch {
        throw "Could not delete $venv ($($_.Exception.Message)). Close VS Code and any other terminal using it, then run this again."
    }
}
Invoke-Checked uv @('sync', '--frozen')
Invoke-Checked npm.cmd @('ci', '--no-audit', '--no-fund')

if (-not $SkipChecks) {
    Write-Step 'Running Ruff, mypy, and pytest'
    Invoke-Checked uv @('run', 'ruff', 'check', '.')
    Invoke-Checked uv @('run', 'mypy', 'sandbox', 'tests')
    Invoke-Checked uv @('run', 'pytest', '-q')
}

Write-Step 'Building the table client'
Invoke-Checked npm.cmd @('run', 'build')

Write-Step 'Preparing the cookie secret and database'
$secretFile = Join-Path $ProjectRoot '.sandbox-secret'
if (-not $env:SANDBOX_SECRET_KEY) {
    if (-not (Test-Path $secretFile) -or (Get-Item $secretFile).Length -eq 0) {
        $bytes = New-Object byte[] 48
        $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $random.GetBytes($bytes)
        $random.Dispose()
        $secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        [System.IO.File]::WriteAllText($secretFile, $secret)
        Write-Host "Created $secretFile"
    }
    $env:SANDBOX_SECRET_KEY = ([System.IO.File]::ReadAllText($secretFile)).Trim()
}
if (-not $env:DATABASE_URL) {
    $database = (Join-Path $ProjectRoot 'ethics-sandbox-live.db').Replace('\', '/')
    $env:DATABASE_URL = "sqlite:///$database"
}
Invoke-Checked uv @('run', 'alembic', 'upgrade', 'head')

$log = Join-Path ([System.IO.Path]::GetTempPath()) ('sandbox-tunnel-' + [guid]::NewGuid().ToString('N'))
$tunnel = $null
$exitCode = 0
try {
    if ($named) {
        $address = ([System.IO.File]::ReadAllText($urlFile)).Trim().TrimEnd('/')
        Write-Step "Opening the named Cloudflare tunnel for $address"
        $tunnelArguments = $namedArguments
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        # Read by cloudflared as it starts; removed again below, so the
        # server never sees it.
        $env:TUNNEL_TOKEN = ([System.IO.File]::ReadAllText($tokenFile)).Trim()
    } else {
        Write-Step "Opening a Cloudflare quick tunnel to port $Port"
        if (-not $Quick) {
            Write-Host 'No named tunnel is set up, so the address will be new. For a permanent one,'
            Write-Host 'see docs\FACILITATING-ON-WINDOWS.md, step 5, and run -SetUpNamedTunnel.'
        }
        $address = $null
        $tunnelArguments = $quickArguments
    }
    # One string, so that paths with spaces stay quoted.
    $tunnel = Start-Process -FilePath (Get-Command cloudflared).Source `
        -ArgumentList $tunnelArguments `
        -RedirectStandardError "$log.err" -RedirectStandardOutput "$log.out" `
        -NoNewWindow -PassThru
    Remove-Item Env:TUNNEL_TOKEN -ErrorAction SilentlyContinue

    # A named tunnel is ready once cloudflared writes its pid file, which it
    # does after its first connection to Cloudflare; a quick one once it
    # prints its address.
    $ready = $false
    $deadline = (Get-Date).AddSeconds(30)
    while (-not $ready) {
        if ($named) {
            $ready = (Test-Path $pidFile) -and ((Get-Item $pidFile).Length -gt 0)
        } else {
            $found = [regex]::Match((Read-SharedText "$log.err") + (Read-SharedText "$log.out"),
                'https://[a-z0-9-]+\.trycloudflare\.com')
            if ($found.Success) { $address = $found.Value; $ready = $true }
        }
        if ($ready) { break }
        if ($tunnel.HasExited) {
            Write-Host (Read-SharedText "$log.out")
            Write-Host (Read-SharedText "$log.err")
            Write-Host "cloudflared version: $(& cloudflared --version 2>&1)"
            throw 'cloudflared stopped before connecting. Its output is above.'
        }
        if ((Get-Date) -gt $deadline) {
            Write-Host (Read-SharedText "$log.out")
            Write-Host (Read-SharedText "$log.err")
            throw 'cloudflared did not connect within 30 seconds. Its output is above.'
        }
        Start-Sleep -Milliseconds 500
    }

    # Every invite link is built from this.
    $env:SANDBOX_PUBLIC_URL = $address

    Write-Step 'Serving'
    Write-Host "Share this address:  $address"
    Write-Host "Check from a phone:  $address/health  (it can take a minute to answer)"
    if ($named) {
        Write-Host "In Cloudflare, its published application route must point to http://localhost:$Port."
    }
    Write-Host 'Press Ctrl-C to stop the server and the tunnel.'

    Set-KeepAwake $true
    # One worker: the WebSocket hub holds each room's live state in this
    # process. Only the tunnel needs to reach it, so it listens on this
    # computer alone and Windows Firewall has nothing to ask.
    & uv run uvicorn sandbox.web.app:app --host 127.0.0.1 --port $Port --workers 1
    $exitCode = $LASTEXITCODE
} finally {
    Set-KeepAwake $false
    if ($tunnel -and -not $tunnel.HasExited) {
        Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item Env:TUNNEL_TOKEN -ErrorAction SilentlyContinue
    Remove-Item "$log.err", "$log.out", $pidFile -ErrorAction SilentlyContinue
    Write-Host ''
    if ($named) {
        Write-Host 'The server and the tunnel have stopped; the address answers again when this is next started.'
    } else {
        Write-Host 'The server and the tunnel have stopped; the address no longer works.'
    }
}
exit $exitCode
