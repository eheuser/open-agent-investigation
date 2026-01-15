# PowerShell script to set up test environment
# Run this from the api/tests directory

Write-Host "Setting up test environment..." -ForegroundColor Green

# Check if we're in a virtual environment
if (-not $env:VIRTUAL_ENV) {
    Write-Host "WARNING: Not in a virtual environment!" -ForegroundColor Yellow
    Write-Host "Consider running: python -m venv venv; .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host ""
}

# Install main dependencies
Write-Host "Installing main dependencies..." -ForegroundColor Cyan
Set-Location ..
pip install -r requirements.txt

# Install test dependencies
Write-Host "Installing test dependencies..." -ForegroundColor Cyan
Set-Location tests
pip install -r requirements-test.txt

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "You can now run tests with: pytest -v" -ForegroundColor Cyan
