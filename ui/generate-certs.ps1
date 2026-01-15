# PowerShell script to generate self-signed SSL certificates for HTTPS

$CertsDir = ".\certs"

# Create certs directory if it doesn't exist
if (-not (Test-Path $CertsDir)) {
    Write-Host "Creating certs directory..." -ForegroundColor Green
    New-Item -ItemType Directory -Path $CertsDir | Out-Null
}

# Check if certificates already exist
if ((Test-Path "$CertsDir\server.key") -and (Test-Path "$CertsDir\server.crt")) {
    Write-Host "SSL certificates already exist in $CertsDir" -ForegroundColor Yellow
    Write-Host "If you want to regenerate them, please delete the existing files first." -ForegroundColor Yellow
    exit 0
}

Write-Host "Generating new RSA private key and self-signed certificate..." -ForegroundColor Green

# Check if OpenSSL is available
$opensslPath = Get-Command openssl -ErrorAction SilentlyContinue

if (-not $opensslPath) {
    Write-Host "ERROR: OpenSSL is not installed or not in PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install OpenSSL:" -ForegroundColor Yellow
    Write-Host "  1. Download from: https://slproweb.com/products/Win32OpenSSL.html" -ForegroundColor Yellow
    Write-Host "  2. Or install via Chocolatey: choco install openssl" -ForegroundColor Yellow
    Write-Host "  3. Or use Git Bash which includes OpenSSL" -ForegroundColor Yellow
    exit 1
}

# Generate RSA private key (4096 bits for better security)
& openssl genrsa -out "$CertsDir\server.key" 4096

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to generate private key" -ForegroundColor Red
    exit 1
}

# Generate self-signed certificate valid for 365 days
& openssl req -new -x509 -sha256 -key "$CertsDir\server.key" `
    -out "$CertsDir\server.crt" -days 365 `
    -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=localhost" `
    -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to generate certificate" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✓ SSL certificates generated successfully!" -ForegroundColor Green
Write-Host "  - Private key: $CertsDir\server.key" -ForegroundColor Cyan
Write-Host "  - Certificate: $CertsDir\server.crt" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: This is a self-signed certificate. Browsers will show a security warning." -ForegroundColor Yellow
Write-Host "For production, use certificates from a trusted Certificate Authority." -ForegroundColor Yellow
