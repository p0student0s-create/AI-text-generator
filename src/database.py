# src/database.py
import os
import chromadb
import requests
import numpy as np
from neo4j import GraphDatabase
from dotenv import load_dotenv
from pathlib import Path
import logging

# Принудительно убираем прокси
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
    os.environ.pop(var, None)

# СОЗДАНИЕ ПАПОК
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "database.log", encoding="utf-8", mode="a"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# === КЛАСС-ОБЁРТКА ДЛЯ OLLAMA EMBEDDINGS ===
class OllamaEmbeddingModel:
    """
    Обёртка над Ollama API для генерации эмбеддингов.
    Полностью заменяет sentence_transformers.SentenceTransformer.
    """
    def __init__(self, model_name: str, base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api/embeddings"
        logger.info(f"Инициализация Ollama Embeddings: model={model_name}, url={self.base_url}")
        
        # Проверка доступности
        try:
            resp = requests.post(self.api_url, json={
                "model": self.model_name, 
                "prompt": "test"
            }, timeout=15)
            if resp.status_code == 200:
                logger.info(f"✓ Ollama модель '{model_name}' доступна")
            else:
                logger.warning(f"⚠ Ollama вернула статус {resp.status_code}. Выполните: ollama pull {self.model_name}")
        except Exception as e:
            logger.error(f"✗ Нет связи с Ollama по адресу {self.base_url}: {e}")

    def encode(self, sentences, **kwargs):
        """
        Генерирует эмбеддинги. Интерфейс совместим с SentenceTransformer.encode().
        """
        is_single = isinstance(sentences, str)
        if is_single:
            sentences = [sentences]
        
        embeddings = []
        for text in sentences:
            try:
                response = requests.post(self.api_url, json={
                    "model": self.model_name,
                    "prompt": text
                }, timeout=60)
                response.raise_for_status()
                embeddings.append(response.json()["embedding"])
            except Exception as e:
                logger.error(f"Ошибка получения эмбеддинга от Ollama: {e}")
                # Fallback: нулевой вектор размерности 1024 (bge-m3)
                embeddings.append([0.0] * 1024)
        
        if is_single:
            return np.array(embeddings[0])
        return np.array(embeddings)


# === ИНИЦИАЛИЗАЦИЯ МОДЕЛИ (ТОЛЬКО OLLAMA) ===
# Значение по умолчанию — ollama, даже если переменная не задана в .env
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3:latest")
EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE", "http://localhost:11434")

logger.info(f"Используем Ollama для эмбеддингов: {EMBEDDING_MODEL}")
_embedding_model = OllamaEmbeddingModel(
    model_name=EMBEDDING_MODEL,
    base_url=EMBEDDING_API_BASE
)


# === ВЕКТОРНОЕ ХРАНИЛИЩЕ ===
_vector_client = chromadb.PersistentClient(
    path=os.getenv("CHROMA_PERSIST_DIR", "./data/vector_store")
)

_collection = _vector_client.get_or_create_collection(
    name="ib_regulations_v1",
    metadata={
        "hnsw:space": "cosine",
        "description": "Векторный индекс нормативной документации"
    }
)


# === ГРАФОВАЯ БАЗА ===
_graph_driver = GraphDatabase.driver(
    uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
    auth=(
        os.getenv("NEO4J_USER", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "IBsecure2026!")
    ),
    database="neo4j",
    connection_timeout=60,
    max_transaction_retry_time=120
)

logger.info("✓ Инфраструктура инициализирована: ChromaDB, Neo4j, Ollama Embeddings")


# === ПУБЛИЧНЫЕ ФУНКЦИИ ===
def get_chroma_collection():
    return _collection

def get_neo4j_driver():
    return _graph_driver

def get_embedding_model():
    return _embedding_model


# === NEO4J: ШАБЛОНЫ ДОКУМЕНТОВ ===
def index_template_section(template_type: str, section_name: str, content: str, order: int):
    logger.info(f"Индексация шаблона: {template_type} → {section_name}")
    with _graph_driver.session() as session:
        session.run("""
            MERGE (t:Template {doc_type: $type})
            CREATE (s:Section {
                id: randomUUID(),
                name: $name,
                content: $content,
                order: $order,
                created_at: datetime()
            })
            CREATE (t)-[:CONTAINS {position: $order}]->(s)
        """, type=template_type, name=section_name, content=content, order=order)

def get_template_sections(template_type: str) -> list[dict]:
    with _graph_driver.session() as session:
        result = session.run("""
            MATCH (t:Template {doc_type: $type})-[:CONTAINS]->(s:Section)
            RETURN s.name AS name, s.content AS content, s.order AS order, s.id AS id
            ORDER BY s.order ASC
        """, type=template_type)
        return [dict(record) for record in result]

def get_template_metadata(template_type: str) -> dict | None:
    with _graph_driver.session() as session:
        result = session.run("""
            MATCH (t:Template {doc_type: $type})
            OPTIONAL MATCH (t)-[:CONTAINS]->(s:Section)
            RETURN t.doc_type AS type, count(s) AS section_count
        """, type=template_type).single()
        return dict(result) if result else None


# === ДИАГНОСТИКА ===
def verify_infrastructure() -> dict:
    status = {}
    try:
        cols = _vector_client.list_collections()
        status["vector_db"] = {"ok": True, "collections": [c.name for c in cols]}
    except Exception as e:
        status["vector_db"] = {"ok": False, "error": str(e)}
    
    try:
        with _graph_driver.session() as sess:
            res = sess.run("RETURN 1 AS ping").single()
            status["graph_db"] = {"ok": True, "ping": res["ping"]}
    except Exception as e:
        status["graph_db"] = {"ok": False, "error": str(e)}
    
    try:
        test_vec = _embedding_model.encode("Проверка")
        status["embeddings"] = {
            "ok": True,
            "dimension": len(test_vec),
            "model": f"Ollama {EMBEDDING_MODEL}"
        }
    except Exception as e:
        status["embeddings"] = {"ok": False, "error": str(e)}
    
    return status

if __name__ == "__main__":
    import sys
    result = verify_infrastructure()
    print("\nСтатус инфраструктуры:")
    for component, info in result.items():
        icon = "✓" if info.get("ok") else "✗"
        print(f"  {icon} {component}: {info}")
    all_ok = all(s.get("ok") for s in result.values())
    sys.exit(0 if all_ok else 1)