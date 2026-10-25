@echo off
rem Double-click to run Slothshot from a cloned copy. Needs uv: https://docs.astral.sh/uv/
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
    echo uv isn't installed. Run install.ps1, or get uv from https://docs.astral.sh/uv/
    pause
    exit /b 1
)
uv run --python 3.12 slothshot up
pause
