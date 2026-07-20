$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

