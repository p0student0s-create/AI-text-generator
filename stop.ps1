<#
.SYNOPSIS
    SecDocs.AI - Скрипт остановки системы

.DESCRIPTION
    Останавливает все запущенные компоненты:
    - Фронтенд (React/Vite)
    - Бэкенд (FastAPI/Uvicorn)
    - Docker-контейнеры (опционально)

.USAGE
    .\stop.ps1
#>

Write-Host ""
Write-Host "╔════════════════════════════════════════════╗" -ForegroundColor Red
Write-Host "║     SecDocs.AI - Остановка системы        ║" -ForegroundColor Red
Write-Host "╚════════════════════════════════════════════╝" -ForegroundColor Red
Write-Host ""

# [1/3] Остановка процессов Python (бэкенд)
Write-Host "[1/3] Остановка бэкенда..." -ForegroundColor Yellow
$backendProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue | 
    Where-Object { $_.MainWindowTitle -like "*FastAPI*" -or $_.CommandLine -like "*main.py*" }

if ($backendProcesses) {
    foreach ($proc in $backendProcesses) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ Остановлен процесс Python (PID: $($proc.Id))" -ForegroundColor Green
    }
} else {
    Write-Host "  → Процессы бэкенда не найдены" -ForegroundColor Gray
}

# [2/3] Остановка процессов Node.js (фронтенд)
Write-Host "[2/3] Остановка фронтенда..." -ForegroundColor Yellow
$frontendProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue | 
    Where-Object { $_.CommandLine -like "*vite*" -or $_.CommandLine -like "*frontend*" }

if ($frontendProcesses) {
    foreach ($proc in $frontendProcesses) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ Остановлен процесс Node (PID: $($proc.Id))" -ForegroundColor Green
    }
} else {
    Write-Host "  → Процессы фронтенда не найдены" -ForegroundColor Gray
}

# [3/3] Docker-контейнеры (опционально)
Write-Host "[3/3] Docker-контейнеры..." -ForegroundColor Yellow
Write-Host "  → Контейнеры не остановлены автоматически" -ForegroundColor Gray
Write-Host "  → Для остановки выполните: docker-compose down" -ForegroundColor Gray

Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "SecDocs.AI остановлена" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""