<#
.SYNOPSIS
    SecDocs.AI - Скрипт запуска системы

.DESCRIPTION
    Автоматизирует запуск всех компонентов системы:
    - Инициализация шаблонов
    - Запуск Docker-контейнеров (Neo4j, Milvus, Redis)
    - Активация Python-окружения
    - Запуск FastAPI-бэкенда
    - Запуск React-фронтенда

.USAGE
    .\start.ps1
#>

# Настройка цветов и форматирования
$ErrorActionPreference = 'Continue'
$Host.UI.RawUI.ForegroundColor = 'White'

function Write-Section {
    param([string]$Text, [string]$Color = 'Cyan')
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════╗" -ForegroundColor $Color
    Write-Host "║  $Text  ║" -ForegroundColor $Color
    Write-Host "╚════════════════════════════════════════════╝" -ForegroundColor $Color
    Write-Host ""
}

function Write-Step {
    param([string]$Text, [string]$Color = 'Yellow')
    Write-Host "[$Text]" -ForegroundColor $Color -NoNewline
    Write-Host " ..."
}

function Write-Success {
    param([string]$Text)
    Write-Host "  ✓ $Text" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Text)
    Write-Host "  ⚠ $Text" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Text)
    Write-Host "  ✗ $Text" -ForegroundColor Red
}

# ==================== ОСНОВНОЙ СКРИПТ ====================

Write-Section "SecDocs.AI - Запуск системы" "Cyan"

# [1/5] Инициализация шаблонов
Write-Step "1/5" "Yellow"
Write-Host "Проверка и инициализация шаблонов..." -ForegroundColor White

$templatesIndex = Join-Path $PSScriptRoot "storage/templates/templates_index.json"

if (-not (Test-Path $templatesIndex)) {
    Write-Host "  → Индекс шаблонов не найден. Запуск анализа..." -ForegroundColor Cyan
    
    $initScript = Join-Path $PSScriptRoot "scripts/init_templates.py"
    if (Test-Path $initScript) {
        python $initScript
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Шаблоны инициализированы"
        } else {
            Write-Warning "Ошибка инициализации шаблонов"
            Write-Host "  Система продолжит работу с шаблонами по умолчанию" -ForegroundColor Gray
        }
    } else {
        Write-Warning "Скрипт init_templates.py не найден"
    }
} else {
    Write-Success "Шаблоны уже инициализированы"
}

# [2/5] Проверка и запуск Docker
Write-Step "2/5" "Yellow"
Write-Host "Проверка Docker..." -ForegroundColor White

try {
    $dockerVersion = docker info --format '{{.ServerVersion}}' 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Docker запущен (версия: $dockerVersion)"
        
        # Запускаем docker-compose, если файл существует
        $composeFile = Join-Path $PSScriptRoot "docker-compose.yml"
        if (Test-Path $composeFile) {
            Write-Host "  → Запуск контейнеров..." -ForegroundColor Cyan
            docker-compose up -d
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Контейнеры запущены"
            } else {
                Write-Warning "Не удалось запустить контейнеры"
            }
        }
    }
} catch {
    Write-Warning "Docker недоступен или не установлен"
    Write-Host "  Некоторые функции могут быть недоступны" -ForegroundColor Gray
}

# [3/5] Активация Python-окружения
Write-Step "3/5" "Yellow"
Write-Host "Активация Python окружения..." -ForegroundColor White

$venvActivate = Join-Path $PSScriptRoot ".venv/Scripts/Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Окружение активировано"
    } else {
        Write-Warning "Не удалось активировать окружение"
    }
} else {
    Write-Warning "Виртуальное окружение не найдено (.venv)"
    Write-Host "  Создайте его командой: python -m venv .venv" -ForegroundColor Gray
}

# [4/5] Запуск бэкенда
Write-Step "4/5" "Yellow"
Write-Host "Запуск бэкенда (FastAPI)..." -ForegroundColor White

$backendScript = Join-Path $PSScriptRoot "src/main.py"
if (Test-Path $backendScript) {
    # Запускаем в новом окне PowerShell
    $backendArgs = @(
        "-NoExit",
        "-Command",
        @"
        Write-Host '╔═══════════════════════════════════════╗' -ForegroundColor Cyan
        Write-Host '║  SecDocs.AI Backend - FastAPI Server  ║' -ForegroundColor Cyan
        Write-Host '╚═══════════════════════════════════════╝' -ForegroundColor Cyan
        Write-Host ''
        Write-Host 'API доступен: http://localhost:8000' -ForegroundColor Green
        Write-Host 'Swagger UI:   http://localhost:8000/docs' -ForegroundColor Green
        Write-Host ''
        Write-Host 'Нажмите Ctrl+C для остановки...' -ForegroundColor Gray
        Write-Host ''
        Set-Location '$PSScriptRoot'
        if (Test-Path '.\.venv\Scripts\Activate.ps1') { .\.venv\Scripts\Activate.ps1 }
        python src/main.py
"@
    )
    
    $backendProcess = Start-Process powershell -ArgumentList $backendArgs -PassThru
    Start-Sleep -Seconds 3
    
    if ($backendProcess.HasExited) {
        Write-Error "Не удалось запустить бэкенд"
    } else {
        Write-Success "Бэкенд запущен (PID: $($backendProcess.Id))"
    }
} else {
    Write-Error "Файл src/main.py не найден"
}

# [5/5] Запуск фронтенда
Write-Step "5/5" "Yellow"
Write-Host "Запуск фронтенда (React + Vite)..." -ForegroundColor White

$frontendDir = Join-Path $PSScriptRoot "frontend"
$packageJson = Join-Path $frontendDir "package.json"

if (Test-Path $packageJson) {
    # Проверяем наличие Node.js
    try {
        $nodeVersion = node --version 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Node.js найден (версия: $nodeVersion)"
            
            # Запускаем в новом окне
            $frontendArgs = @(
                "-NoExit",
                "-Command",
                @"
                Write-Host '╔════════════════════════════════════════╗' -ForegroundColor Cyan
                Write-Host '║  SecDocs.AI Frontend - React + Vite    ║' -ForegroundColor Cyan
                Write-Host '╚════════════════════════════════════════╝' -ForegroundColor Cyan
                Write-Host ''
                Write-Host 'Интерфейс доступен: http://localhost:5173' -ForegroundColor Green
                Write-Host ''
                Write-Host 'Нажмите Ctrl+C для остановки...' -ForegroundColor Gray
                Write-Host ''
                Set-Location '$frontendDir'
                npm run dev
"@
            )
            
            $frontendProcess = Start-Process powershell -ArgumentList $frontendArgs -PassThru
            Start-Sleep -Seconds 2
            
            if ($frontendProcess.HasExited) {
                Write-Error "Не удалось запустить фронтенд"
            } else {
                Write-Success "Фронтенд запущен (PID: $($frontendProcess.Id))"
            }
        }
    } catch {
        Write-Warning "Node.js не найден или не установлен"
        Write-Host "  Установите Node.js с сайта: https://nodejs.org" -ForegroundColor Gray
    }
} else {
    Write-Warning "Папка frontend или package.json не найдены"
}

# ==================== ФИНАЛЬНЫЕ СООБЩЕНИЯ ====================

Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "SecDocs.AI успешно запущена!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  🔗 Backend API:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "  🌐 Frontend UI:   http://localhost:5173" -ForegroundColor Cyan
Write-Host "  📚 Swagger docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "  💡 Советы:" -ForegroundColor Yellow
Write-Host "     • Для остановки: закройте окна PowerShell или нажмите Ctrl+C" -ForegroundColor Gray
Write-Host "     • Логи: папка ./logs/" -ForegroundColor Gray
Write-Host "     • Документы: папка ./storage/generated/" -ForegroundColor Gray
Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan