$ErrorActionPreference = "SilentlyContinue"

Write-Host "=========================================="
Write-Host "Checking CaRAG Backend Services..."
Write-Host "=========================================="
Write-Host ""

# 1. Check PostgreSQL (Local System)
Write-Host "1. Checking PostgreSQL Database (Local Port 5432)..."
$pgConnection = Test-NetConnection -ComputerName localhost -Port 5432
if ($pgConnection.TcpTestSucceeded) {
    Write-Host "[OK] PostgreSQL is running and accessible." -ForegroundColor Green
} else {
    Write-Host "[FAIL] PostgreSQL is NOT responding on port 5432." -ForegroundColor Red
    Write-Host "       Please ensure your local Postgres service is started via Windows Services." -ForegroundColor Yellow
}
Write-Host ""

# 2. Check Milvus (Docker Desktop)
Write-Host "2. Checking Milvus Database (Docker Port 19530)..."
$milvusConnection = Test-NetConnection -ComputerName localhost -Port 19530
if ($milvusConnection.TcpTestSucceeded) {
    Write-Host "[OK] Milvus is running and accessible." -ForegroundColor Green
} else {
    Write-Host "[FAIL] Milvus is NOT responding on port 19530." -ForegroundColor Red
    Write-Host "       Please ensure your Docker Desktop is running and the Milvus container is started." -ForegroundColor Yellow
}
Write-Host ""

Write-Host "=========================================="
Write-Host "Verification Complete."
Write-Host "=========================================="
