#scr/database.py
import os
import chromadb
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from pathlib import Path
import logging

for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
    os.environ.pop(var, None)

# СОЗДАНИЕ ПАПОК ДЛЯ ЛОГОВ И ДАННЫХ
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

# Векторное хранилище для нормативных документов
# Используем persistent-режим для сохранения данных между сессиями
_vector_client = chromadb.PersistentClient(
    path=os.getenv("CHROMA_PERSIST_DIR", "./data/vector_store")
)

_collection = _vector_client.get_or_create_collection(
    name="ib_regulations_v1",
    metadata={
        "hnsw:space": "cosine",
        "description": "Векторный индекс нормативной документации (ГОСТ, ISO, внутренние политики)"
    }
)

# Графовая база для связей
_graph_driver = GraphDatabase.driver(
    uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
    auth=(
        os.getenv("NEO4J_USER", "neo4j"),
        os.getenv("NEO4J_PASSWORD", "IBsecure2026!")
    ),
    database="neo4j",
    connection_timeout=60,  # 1 минута на подключение
    max_transaction_retry_time=120  # 2 минуты на повторные попытки
)

# Модель эмбеддингов с поддержкой русского языка
_embedding_model = SentenceTransformer(
    "BAAI/bge-m3",
    device=os.getenv("EMBEDDING_DEVICE", "cpu"),
    cache_folder=os.getenv("HF_CACHE_DIR", r"C:\Users\IvanV\.ollama\models\manifests\registry.ollama.ai\library\bge-m3"),
    local_files_only=True,
    trust_remote_code=True
)

logger.info("✓ Инфраструктура инициализирована: ChromaDB, Neo4j, BGE-m3")

# Публичные функции-геттеры (используются в остальном коде проекта)
def get_chroma_collection():
    """
    Возвращает коллекцию ChromaDB для векторного поиска нормативных документов.
    """
    return _collection


def get_neo4j_driver():
    """
    Возвращает драйвер Neo4j для работы с графовой базой.
    """
    return _graph_driver


def get_embedding_model():
    """
    Возвращает модель эмбеддингов для векторизации текста.
    """
    return _embedding_model

# Вспомогательные функции для работы с шаблонами документов (Neo4j)
def index_template_section(template_type: str, section_name: str, content: str, order: int):
    """
    Индексация секции шаблона в графовой базе Neo4j.
    
    Args:
        template_type: Тип документа (например, "password_policy", "incident_response")
        section_name: Название секции (например, "1. Общие положения")
        content: Содержимое секции
        order: Порядок секции в документе
    """
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
        """, 
        type=template_type,
        name=section_name,
        content=content,
        order=order
        )
    logger.debug(f"✓ Секция '{section_name}' добавлена в шаблон '{template_type}'")


def get_template_sections(template_type: str) -> list[dict]:
    """
    Получение всех секций шаблона в порядке следования.
    
    Returns:
        Список словарей: [{"name": str, "content": str, "order": int, "id": str}, ...]
    """
    logger.debug(f"Запрос секций шаблона: {template_type}")
    
    with _graph_driver.session() as session:
        result = session.run("""
            MATCH (t:Template {doc_type: $type})-[:CONTAINS]->(s:Section)
            RETURN s.name AS name, s.content AS content, s.order AS order, s.id AS id
            ORDER BY s.order ASC
        """, type=template_type)
        
        return [dict(record) for record in result]


def get_template_metadata(template_type: str) -> dict | None:
    """
    Получение метаданных шаблона.
    
    Returns:
        {"type": str, "section_count": int} или None, если шаблон не найден
    """
    with _graph_driver.session() as session:
        result = session.run("""
            MATCH (t:Template {doc_type: $type})
            OPTIONAL MATCH (t)-[:CONTAINS]->(s:Section)
            RETURN t.doc_type AS type, count(s) AS section_count
        """, type=template_type).single()
        
        return dict(result) if result else None

# Диагностика (для отладки и CI/CD)
def verify_infrastructure() -> dict:
    """
    Проверка доступности всех компонентов инфраструктуры.
    
    Returns:
        dict со статусами: {"vector_db": {...}, "graph_db": {...}, "embeddings": {...}}
    """
    status = {}
    
    # ChromaDB
    try:
        cols = _vector_client.list_collections()
        status["vector_db"] = {
            "ok": True,
            "collections": [c.name for c in cols],
            "target": "ib_regulations_v1"
        }
    except Exception as e:
        status["vector_db"] = {"ok": False, "error": str(e)}
        logger.error(f"ChromaDB ошибка: {e}")
    
    # Neo4j
    try:
        with _graph_driver.session() as sess:
            res = sess.run("RETURN 1 AS ping").single()
            status["graph_db"] = {"ok": True, "ping": res["ping"]}
    except Exception as e:
        status["graph_db"] = {"ok": False, "error": str(e)}
        logger.error(f"Neo4j ошибка: {e}")
    
    # Embeddings
    try:
        test_vec = _embedding_model.encode("Проверка")
        status["embeddings"] = {
            "ok": True,
            "dimension": len(test_vec),
            "model": "BAAI/bge-m3"
        }
    except Exception as e:
        status["embeddings"] = {"ok": False, "error": str(e)}
        logger.error(f"Embedding ошибка: {e}")
    
    return status
    
# Точка входа для отладки: python -m src.database
if __name__ == "__main__":
    import sys
    result = verify_infrastructure()
    
    print("\nСтатус инфраструктуры:")
    for component, info in result.items():
        icon = "✓" if info.get("ok") else "✗"
        print(f"  {icon} {component}: {info}")
    
    # Выход с кодом ошибки при проблемах (для CI/CD)
    all_ok = all(s.get("ok") for s in result.values())
    sys.exit(0 if all_ok else 1)
