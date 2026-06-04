# src/main.py
import sys
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "logs" / "api.log", encoding="utf-8", mode="a")
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SecDocs.AI API",
    description="API для автоматической генерации нормативной документации по информационной безопасности",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# === МОДЕЛИ ОТВЕТОВ (были не определены) ===

class HealthResponse(BaseModel):
    """Ответ health check"""
    status: str
    services: Dict[str, str]
    timestamp: str

class GenerateRequest(BaseModel):
    """Запрос на генерацию документа"""
    doc_type: str = Field(..., description="Тип документа: policy, regulation, instruction, threat_model, risk_assessment, incident_response, access_control")
    standards: List[str] = Field(..., description="Список стандартов: gost_57580, fstek_239, iso_27001")
    title: str = Field(..., description="Название документа")
    organization: str = Field(..., description="Название организации")
    object_type: Optional[str] = Field(default="Информационная система", description="Объект защиты")
    data_category: Optional[str] = Field(default="Конфиденциальная информация", description="Категория данных")

class GenerateResponse(BaseModel):
    """Ответ на запрос генерации"""
    status: str = Field(..., description="status: success или error")
    document_id: Optional[str] = Field(default=None, description="ID сгенерированного документа")
    download_url: Optional[str] = Field(default=None, description="URL для скачивания")
    path: Optional[str] = Field(default=None, description="Путь к файлу на сервере")
    error: Optional[str] = Field(default=None, description="Текст ошибки")

# === ГЛОБАЛЬНЫЕ СЕРВИСЫ ===

_orchestrator = None

def get_orchestrator():
    """Ленивая инициализация оркестратора"""
    global _orchestrator
    if _orchestrator is None:
        from src.agents.orchestrator import DocumentOrchestrator
        _orchestrator = DocumentOrchestrator(llm_config={
            "base_url": "http://localhost:11434",
            "architect_model": "gemma4",
            "policy_model": "gemma4",
            "writer_temperature": 0.2,
            "use_openai_compat": False
        })
        logger.info("✓ Orchestrator инициализирован")
    return _orchestrator

# === ЭНДПОИНТЫ ===

@app.get("/")
async def root():
    return {
        "service": "SecDocs.AI",
        "version": "2.0.0",
        "status": "online",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Проверка здоровья сервиса"""
    try:
        services = {}
        
        # Проверка Ollama
        orchestrator = get_orchestrator()
        if orchestrator.ollama_client.health_check():
            services["ollama"] = "connected"
        else:
            services["ollama"] = "unreachable"
        
        # Проверка ChromaDB
        try:
            from src.database import get_chroma_collection
            collection = get_chroma_collection()
            collection.peek(limit=1)
            services["chromadb"] = "connected"
        except Exception as e:
            services["chromadb"] = f"error: {str(e)[:50]}"
        
        return HealthResponse(
            status="healthy" if all(v == "connected" for v in services.values()) else "degraded",
            services=services,
            timestamp=datetime.now().isoformat()
        )
     
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")

@app.post("/api/documents/generate", response_model=GenerateResponse)
async def generate_document(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Запуск генерации документа"""
    try:
        logger.info(f"Запрос на генерацию: type={request.doc_type}, org={request.organization}")
        
        orchestrator = get_orchestrator()
        
        result = await orchestrator.generate_document(
            doc_type=request.doc_type,
            standards=request.standards,
            title=request.title,
            organization=request.organization,
            object_type=request.object_type,
            data_category=request.data_category
        )
        
        if result["success"]:
            return GenerateResponse(
                status="completed",
                document_id=result["document_id"],
                download_url=result["download_url"],
                path=result["file_path"]
            )
        else:
            return GenerateResponse(
                status="error",
                error=result.get("error", "Unknown error")
            )
            
    except Exception as e:
        logger.error(f"Критическая ошибка генерации: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@app.get("/api/documents/{doc_id}/download")
async def download_document(doc_id: str):
    """Скачивание сгенерированного документа"""
    try:
        file_path = PROJECT_ROOT / "storage" / "generated" / f"{doc_id}.pdf"
        
        if not file_path.exists():
            logger.warning(f"Документ не найден: {doc_id}")
            raise HTTPException(status_code=404, detail="Документ не найден или ещё не сгенерирован")
        
        logger.info(f"Скачивание: {doc_id}")
        
        return FileResponse(
            path=str(file_path),
            filename=f"{doc_id}.pdf",
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{doc_id}.pdf"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка скачивания: {str(e)}")

# === ОБРАБОТЧИКИ ОШИБОК ===

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    logger.warning(f"HTTP {exc.status_code}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "detail": exc.detail}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "Внутренняя ошибка сервера"}
    )

# === ТОЧКА ВХОДА ===

if __name__ == "__main__":
    logger.info("Запуск SecDocs.AI API...")
    logger.info(f"Project root: {PROJECT_ROOT}")
    
    try:
        get_orchestrator()
        logger.info("✓ Все сервисы готовы к работе")
    except Exception as e:
        logger.warning(f"Не все сервисы инициализированы: {e}")
        logger.info("Сервисы будут инициализированы при первом запросе")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )