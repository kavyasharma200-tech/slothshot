# Installs Slothshot on Windows and starts it.
#
#   irm https://raw.githubusercontent.com/kavyasharma200-tech/slothshot/main/install.ps1 | iex
#   .\install.ps1 -Source C:\code\slothshot        (install from a local copy instead)
#
# What it does: installs uv if it's missing, offers to install Ollama, installs slothshot as a
# uv tool on Python 3.12, pulls the small model, then runs `slothshot up`.

param(
    [string]$Source = "git+https://github.com/kavyasharma200-tech/slothshot",
    [string]$Model = "gemma3:1b",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

function Say($text) { Write-Host "  sloth  $text" -ForegroundColor DarkGreen }

# 1. uv, which brings its own Python, so nothing else needs to be installed first
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Say "Installing uv (Astral's Python tool manager)..."
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv was installed but isn't on PATH yet. Open a new terminal and run this script again."
    }
}

# 2. Ollama, which runs the model that names your screenshots
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    $guess = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $guess) { $ollama = Get-Item $guess }
}
if (-not $ollama) {
    $answer = Read-Host "  sloth  Ollama isn't installed. Install it now with winget? [Y/n]"
    if ($answer -eq "" -or $answer -match "^[Yy]") {
        winget install --id Ollama.Ollama -e
        $guess = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
        if (Test-Path $guess) { $ollama = Get-Item $guess }
    } else {
        Say "Skipping. Get it later from https://ollama.com/download; slothshot waits for it."
    }
}

# 3. slothshot itself, on Python 3.12 (its OCR engine doesn't support 3.13 yet)
Say "Installing slothshot from $Source ..."
uv tool install --force --python 3.12 $Source
if ($LASTEXITCODE -ne 0) { throw "uv tool install failed." }
$bin = (uv tool dir --bin).Trim()
$env:Path = "$bin;$env:Path"

# 4. the model (about 800 MB, once)
if ($ollama) {
    Say "Pulling $Model (about 800 MB, only the first time)..."
    & $ollama.Source pull $Model
    if ($LASTEXITCODE -ne 0) {
        Say "Couldn't pull yet. Open the Ollama app, then run: slothshot pull $Model"
    }
}

Say "Installed. Check it any time with: slothshot doctor"
if (-not $NoStart) {
    slothshot up
}
