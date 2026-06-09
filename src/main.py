# src/main.py
import sys
import logging
import time
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel, Field

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
    version="2.1.0",
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
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# === МОДЕЛИ ОТВЕТОВ ===
class HealthResponse(BaseModel):
    status: str
    services: Dict[str, str]
    timestamp: str

class GenerateRequest(BaseModel):
    doc_type: str = Field(..., description="Тип документа")
    standards: List[str] = Field(..., description="Список стандартов")
    title: str = Field(..., description="Название документа")
    organization: str = Field(..., description="Название организации")
    object_type: Optional[str] = Field(default="Информационная система")
    data_category: Optional[str] = Field(default="Конфиденциальная информация")

class GenerateResponse(BaseModel):
    status: str
    document_id: Optional[str] = None
    download_url: Optional[str] = None
    path: Optional[str] = None
    error: Optional[str] = None

class PromptRequest(BaseModel):
    generation_id: str = Field(..., description="ID активной генерации")
    prompt: str = Field(..., description="Дополнительный контекст/промпт")

class CancelRequest(BaseModel):
    generation_id: str

# === ХРАНИЛИЩЕ АКТИВНЫХ ГЕНЕРАЦИЙ ===
_active_generations: Dict[str, Dict[str, Any]] = {}

def _get_generation(generation_id: str) -> Optional[Dict]:
    return _active_generations.get(generation_id)

def _register_generation(generation_id: str, queue: asyncio.Queue):
    _active_generations[generation_id] = {
        "queue": queue,
        "status": "running",
        "created_at": datetime.now().isoformat(),
        "additional_prompts": [],
        "cancelled": False,
    }

def _unregister_generation(generation_id: str):
    if generation_id in _active_generations:
        _active_generations[generation_id]["status"] = "completed"
        del _active_generations[generation_id]

# === ГЛОБАЛЬНЫЕ СЕРВИСЫ ===
_orchestrator = None

def get_orchestrator():
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
        "version": "2.1.0",
        "status": "online",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    try:
        services = {}
        orchestrator = get_orchestrator()
        if orchestrator.ollama_client.health_check():
            services["ollama"] = "connected"
        else:
            services["ollama"] = "unreachable"
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
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")

@app.post("/api/documents/generate", response_model=GenerateResponse)
async def generate_document(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Старый endpoint — оставлен для совместимости"""
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
            return GenerateResponse(status="error", error=result.get("error", "Unknown error"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")


@app.post("/api/documents/generate-stream")
async def generate_document_stream(request: GenerateRequest):
    """
    Streaming endpoint для генерации документа в реальном времени.
    Возвращает SSE (Server-Sent Events) с событиями генерации.
    """
    generation_id = f"gen_{int(time.time())}_{hash(request.title) % 10000}"
    queue: asyncio.Queue = asyncio.Queue()
    
    # Регистрируем генерацию
    _register_generation(generation_id, queue)
    logger.info(f"Создана генерация: {generation_id}")
    
    async def run_generation():
        """Фоновая задача: запускает генерацию и кладёт события в очередь"""
        try:
            orchestrator = get_orchestrator()
            
            # Callback — просто кладёт событие в очередь (синхронный вызов через call_soon_threadsafe не нужен, 
            # т.к. всё в одном event loop)
            async def stream_callback(event: Dict[str, Any]):
                await queue.put(event)
            
            # Запускаем генерацию с callback
            result = await orchestrator.generate_document_stream(
                doc_type=request.doc_type,
                standards=request.standards,
                title=request.title,
                organization=request.organization,
                object_type=request.object_type,
                data_category=request.data_category,
                generation_id=generation_id,
                callback=stream_callback
            )
            
            # Отправляем финальное событие
            await queue.put({"type": "completed", "result": result})
            
        except Exception as e:
            logger.error(f"Ошибка в генерации {generation_id}: {e}", exc_info=True)
            await queue.put({"type": "error", "error": str(e)})
        finally:
            # Сигнал о завершении
            await queue.put(None)
    
    async def event_generator():
        """Генератор SSE событий"""
        try:
            # Отправляем ID генерации сразу
            yield f"data: {json.dumps({'type': 'generation_id', 'generation_id': generation_id}, ensure_ascii=False)}\n\n"
            
            # Запускаем генерацию в фоне
            gen_task = asyncio.create_task(run_generation())
            
            # Читаем события из очереди
            while True:
                try:
                    # Ждём событие с таймаутом, чтобы проверять статус задачи
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    if event is None:
                        # Сигнал о завершении
                        break
                    
                    # Проверяем дополнительные промпты
                    gen_info = _get_generation(generation_id)
                    if gen_info and gen_info["additional_prompts"]:
                        while gen_info["additional_prompts"]:
                            prompt_data = gen_info["additional_prompts"].pop(0)
                            yield f"data: {json.dumps({'type': 'prompt_applied', 'prompt': prompt_data['prompt']}, ensure_ascii=False)}\n\n"
                    
                    # Отправляем событие клиенту
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    
                    # Если это финальное событие — выходим
                    if event.get("type") in ("completed", "error"):
                        break
                        
                except asyncio.TimeoutError:
                    # Проверяем, не завершилась ли задача
                    if gen_task.done():
                        exc = gen_task.exception()
                        if exc:
                            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)}, ensure_ascii=False)}\n\n"
                        break
                    # Продолжаем ждать
                    
        except Exception as e:
            logger.error(f"Ошибка в event_generator: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            _unregister_generation(generation_id)
            logger.info(f"Генерация {generation_id} завершена")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/documents/prompt")
async def send_additional_prompt(request: PromptRequest):
    """Отправка дополнительного промпта во время генерации"""
    gen_info = _get_generation(request.generation_id)
    if not gen_info:
        raise HTTPException(status_code=404, detail="Генерация не найдена или завершена")
    
    if gen_info["status"] != "running":
        raise HTTPException(status_code=400, detail="Генерация не активна")
    
    gen_info["additional_prompts"].append({
        "prompt": request.prompt,
        "timestamp": datetime.now().isoformat()
    })
    
    logger.info(f"Добавлен промпт для генерации {request.generation_id}: {request.prompt[:50]}...")
    return {"status": "ok", "message": "Промпт добавлен в очередь"}


@app.post("/api/documents/cancel")
async def cancel_generation(request: CancelRequest):
    """Отмена активной генерации"""
    gen_info = _get_generation(request.generation_id)
    if not gen_info:
        raise HTTPException(status_code=404, detail="Генерация не найдена")
    
    gen_info["cancelled"] = True
    gen_info["status"] = "cancelled"
    
    return {"status": "ok", "message": "Генерация отменена"}


@app.get("/api/documents/{doc_id}/download")
async def download_document(doc_id: str):
    try:
        file_path = PROJECT_ROOT / "storage" / "generated" / f"{doc_id}.pdf"
        if not file_path.exists():
            # Пробуем markdown
            md_path = PROJECT_ROOT / "storage" / "generated" / f"{doc_id}.md"
            if md_path.exists():
                return FileResponse(
                    path=str(md_path),
                    filename=f"{doc_id}.md",
                    media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{doc_id}.md"'}
                )
            raise HTTPException(status_code=404, detail="Документ не найден")
        return FileResponse(
            path=str(file_path),
            filename=f"{doc_id}.pdf",
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{doc_id}.pdf"'}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка скачивания: {str(e)}")


# === ОБРАБОТЧИКИ ОШИБОК ===
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "detail": exc.detail})

@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"status": "error", "detail": "Внутренняя ошибка сервера"})


if __name__ == "__main__":
    logger.info("Запуск SecDocs.AI API...")
    try:
        get_orchestrator()
        logger.info("✓ Все сервисы готовы к работе")
    except Exception as e:
        logger.warning(f"Не все сервисы инициализированы: {e}")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info", access_log=True)