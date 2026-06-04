# src/services/ollama_client.py
import logging
import requests
import asyncio
import aiohttp
from typing import Dict, Any, Optional, Union, List, AsyncIterator
import time
import re
import json
import hashlib
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """Чанк стримингового ответа"""
    content: str
    done: bool = False
    error: Optional[str] = None


def _hash_prompt(
    messages: List[Dict],
    temperature: float,
    model: str,
    context_hint: Optional[str] = None
) -> str:
    """Создаёт детерминированный хэш для кэширования"""
    context_part = context_hint or ""
    content = (
        f"{model}|{temperature}|{context_part}|"
        f"{json.dumps(messages, sort_keys=True, ensure_ascii=False)}"
    )
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


class OllamaClient:
    """
    Оптимизированный клиент для Ollama:
    - Streaming-ответы для снижения latency
    - Адаптивные таймауты (короткие для критика, длинные для генерации)
    - Агрессивное кэширование с семантическим ключом
    - Автоматический fallback между эндпоинтами
    """
    
    # Настройки кэша
    CACHE_MAX_SIZE = 256  # Увеличено для параллельных запросов
    CACHE_TTL_SECONDS = 600  # 10 минут — достаточно для сессии генерации
    
    # Таймауты по типу запроса
    TIMEOUTS = {
        "critic": 120,      # Критик: быстрая проверка
        "writer": 240,      # Писатель: генерация контента
        "architect": 180,   # Архитектор: структура
        "auditor": 180,     # Аудитор: финальная проверка
        "default": 180,
    }
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "gemma4",
        timeout: Optional[float] = None,
        max_retries: int = 2,  # Снижено с 3
        temperature: float = 0.1,
        use_openai_compat: bool = True,
        enable_cache: bool = True,
        enable_streaming: bool = True,
        request_type: str = "default"  # Для выбора таймаута
    ):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout or self.TIMEOUTS.get(request_type, self.TIMEOUTS["default"])
        self.max_retries = max_retries
        self.temperature = temperature
        self.use_openai_compat = use_openai_compat
        self.enable_cache = enable_cache
        self.enable_streaming = enable_streaming
        self.request_type = request_type
        
        self._response_cache: Dict[str, tuple] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        
        self.openai_url = f"{self.base_url}/v1/chat/completions"
        self.native_chat_url = f"{self.base_url}/api/chat"
        self.native_generate_url = f"{self.base_url}/api/generate"
        
        logger.info(
            f"OllamaClient: model={model}, timeout={self.timeout}s, "
            f"stream={enable_streaming}, cache={enable_cache}, type={request_type}"
        )
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout + 30))
        return self
    
    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
    
    def _is_cache_valid(self, timestamp: float) -> bool:
        return (time.time() - timestamp) < self.CACHE_TTL_SECONDS
    
    def _get_cached_response(self, prompt_hash: str) -> Optional[Dict]:
        if not self.enable_cache:
            return None
        if prompt_hash in self._response_cache:
            response, timestamp = self._response_cache[prompt_hash]
            if self._is_cache_valid(timestamp):
                logger.debug(f"✓ Кэш-хит: {prompt_hash}")
                return response
            del self._response_cache[prompt_hash]
        return None
    
    def _cache_response(self, prompt_hash: str, response: Dict):
        if not self.enable_cache:
            return
        if len(self._response_cache) >= self.CACHE_MAX_SIZE:
            oldest = min(self._response_cache, key=lambda k: self._response_cache[k][1])
            del self._response_cache[oldest]
        self._response_cache[prompt_hash] = (response, time.time())
    
    def _extract_json(self, text: str) -> str:
        """Быстрое извлечение JSON без рекурсии"""
        if not text:
            return ""
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.IGNORECASE)
        if text.startswith(('{', '[')):
            return text
        start = text.find('{') if '{' in text else text.find('[')
        if start == -1:
            return text
        # Простой парсер для плоских структур (достаточно для наших ответов)
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c in '{[':
                depth += 1
            elif c in '}]':
                depth -= 1
                if depth == 0:
                    return text[start:i+1]
        return text[start:]
    
    async def _stream_native_chat(
        self,
        payload: Dict,
        headers: Dict
    ) -> AsyncIterator[StreamChunk]:
        """Стриминг через нативный /api/chat"""
        url = self.native_chat_url
        payload["stream"] = True
        
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(
                total=self.timeout,      # 600+ секунд
                connect=30,              # таймаут подключения
                sock_read=self.timeout,  # чтение сокета
                sock_connect=30          # подключение сокета
            )
            async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    yield StreamChunk("", done=True, error=f"HTTP {resp.status}")
                    return
                
                async for line in resp.content:
                    line = line.decode().strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield StreamChunk(content)
                        if chunk.get("done", False):
                            yield StreamChunk("", done=True)
                            break
                    except json.JSONDecodeError:
                        continue
    
    async def _stream_openai_compat(
        self,
        payload: Dict,
        headers: Dict
    ) -> AsyncIterator[StreamChunk]:
        """Стриминг через OpenAI-compatible API"""
        url = self.openai_url
        payload["stream"] = True
        
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(
                total=self.timeout,         # 30 минут вместо 600с
                connect=60,                 # таймаут подключения
                sock_read=self.timeout,     # чтение сокета
                sock_connect=60             # подключение сокета
            )
            async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    yield StreamChunk("", done=True, error=f"HTTP {resp.status}")
                    return
                
                async for line in resp.content:
                    line = line.decode().strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield StreamChunk(content)
                    except json.JSONDecodeError:
                        continue
                yield StreamChunk("", done=True)
    
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        cache_key: Optional[str] = None,
        context_hint: Optional[str] = None
    ) -> AsyncIterator[StreamChunk]:
        """Streaming-версия chat() — возвращает чанки по мере генерации"""
        temp = temperature if temperature is not None else self.temperature
        headers = {"Content-Type": "application/json"}
        
        openai_payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "stream": True
        }
        native_payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "stream": True
        }
        
        prompt_hash = cache_key or _hash_prompt(messages, temp, self.model, context_hint)
        cached = self._get_cached_response(prompt_hash)
        if cached and not self.enable_streaming:
            content = cached.get("message", {}).get("content", "")
            if content:
                yield StreamChunk(content, done=True)
                return
        
        collected = []
        async for chunk in self._stream_native_chat(native_payload, headers) if not self.use_openai_compat else self._stream_openai_compat(openai_payload, headers):
            if chunk.error:
                logger.warning(f"Stream error: {chunk.error}")
                continue
            if chunk.content:
                collected.append(chunk.content)
                yield chunk
            if chunk.done:
                # Кэшируем полный ответ постфактум
                full_content = "".join(collected)
                if full_content.strip():
                    self._cache_response(prompt_hash, {"message": {"content": full_content}})
                break
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        response_model=None,
        cache_key: Optional[str] = None,
        context_hint: Optional[str] = None,
        use_streaming: Optional[bool] = None
    ) -> Union[Dict, Any]:
        """
        Chat API с опциональным streaming и адаптивными таймаутами.
        """
        use_stream = use_streaming if use_streaming is not None else self.enable_streaming
        
        if use_stream:
            # Собираем стрим в полный ответ для обратной совместимости
            content_parts = []
            async for chunk in self.chat_stream(messages, temperature, cache_key, context_hint):
                if chunk.content:
                    content_parts.append(chunk.content)
            content = "".join(content_parts)
            result = {"message": {"content": content.strip()}}
        else:
            # Legacy non-streaming fallback
            temp = temperature if temperature is not None else self.temperature
            headers = {"Content-Type": "application/json"}
            
            openai_payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temp,
                "stream": False
            }
            native_payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temp,
                "stream": False
            }
            
            prompt_hash = cache_key or _hash_prompt(messages, temp, self.model, context_hint)
            cached = self._get_cached_response(prompt_hash)
            if cached:
                return self._parse_response(cached, response_model)
            
            last_error = None
            # Попытка 1: OpenAI-compatible
            if self.use_openai_compat:
                result = await self._try_endpoint_async(self.openai_url, openai_payload, headers)
                if result:
                    self._cache_response(prompt_hash, result)
                    return self._parse_response(result, response_model)
            
            # Попытка 2: Native /api/chat
            result = await self._try_endpoint_async(self.native_chat_url, native_payload, headers)
            if result:
                self._cache_response(prompt_hash, result)
                return self._parse_response(result, response_model)
            
            raise RuntimeError(f"All endpoints failed. Last error: {last_error}")
        
        return self._parse_response(result, response_model)
    
    async def _try_endpoint_async(self, url: str, payload: dict, headers: dict) -> Optional[Dict]:
        """Асинхронная попытка запроса"""
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=self.timeout) as resp:
                        resp.raise_for_status()
                        return await resp.json()
            except asyncio.TimeoutError:
                logger.warning(f"Timeout ({self.timeout}s) on attempt {attempt+1} for {url}")
                last_error = f"Timeout after {self.timeout}s"
            except aiohttp.ClientError as e:
                logger.debug(f"Client error on {url}: {e}")
                last_error = str(e)
            except Exception as e:
                logger.debug(f"Unexpected error on {url}: {type(e).__name__}: {e}")
                last_error = str(e)
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
        
        return None
    
    def _parse_response(self, result: Dict, response_model=None):
        """Парсинг ответа (без изменений, совместимо)"""
        content = ""
        if "choices" in result and result["choices"]:
            content = result["choices"][0].get("message", {}).get("content", "")
        elif "message" in result and isinstance(result["message"], dict):
            content = result["message"].get("content", "")
        elif "response" in result:
            content = result["response"]
        
        if not content or not content.strip():
            raise ValueError(f"Пустой ответ от LLM: {result}")
        
        if response_model:
            from pydantic import BaseModel
            if issubclass(response_model, BaseModel):
                return self._parse_with_retry(content, response_model)
        
        return {"message": {"content": content.strip()}}
    
    def _parse_with_retry(self, content: str, model_type, max_attempts: int = 2):
        """Упрощённый парсер с 2 попытками вместо 3"""
        from pydantic import BaseModel, ValidationError
        last_error = None
        for attempt in range(max_attempts):
            try:
                clean = self._extract_json(content)
                data = json.loads(clean)
                if issubclass(model_type, BaseModel):
                    return model_type.model_validate(data)
                return data
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                if attempt < max_attempts - 1:
                    time.sleep(0.3)
        raise ValueError(f"Parse failed: {last_error}")
    
    def clear_cache(self):
        self._response_cache.clear()
        logger.info("Кэш очищен")
    
    def get_cache_stats(self) -> Dict[str, int]:
        return {
            "size": len(self._response_cache),
            "max_size": self.CACHE_MAX_SIZE,
            "ttl_seconds": self.CACHE_TTL_SECONDS
        }