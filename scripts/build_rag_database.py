# scripts/build_rag_database.py
"""
Построение RAG-базы: индексация стандартов и примеров
"""
# === 1. ОФФЛАЙН-РЕЖИМ — ДО ВСЕХ ИМПОРТОВ ===
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["SENTENCE_TRANSFORMERS_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

# === 2. АГРЕССИВНАЯ ОЧИСТКА ПРОКСИ — УДАЛЕНИЕ, а не обнуление ===
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 
            'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy']:
    os.environ.pop(var, None)  # ← Полностью удаляем переменную

# === 3. Теперь можно импортировать остальное ===
import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.index_standards import index_standards
from scripts.index_examples import index_examples

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("="*60)
    logger.info("Построение RAG-базы документов")
    logger.info("="*60)
    
    errors = []  # ← Счётчик ошибок для корректного завершения
    
    # Шаг 1: Индексация стандартов
    logger.info("\nШаг 1: Индексация нормативных документов...")
    try:
        index_standards(str(project_root / "data" / "documents" / "standards"))
        logger.info("✓ Стандарты проиндексированы")
    except Exception as e:
        logger.error(f"Ошибка индексации стандартов: {e}")
        errors.append(f"standards: {e}")
    
    # Шаг 2: Индексация примеров
    logger.info("\nШаг 2: Индексация примеров документов...")
    try:
        index_examples(str(project_root / "data" / "documents" / "examples"))
        logger.info("✓ Примеры проиндексированы")
    except Exception as e:
        logger.error(f"Ошибка индексации примеров: {e}")
        errors.append(f"examples: {e}")
    
    # Итоговый статус
    logger.info("\n" + "="*60)
    if errors:
        logger.error(f"✗ RAG-база построена с ошибками ({len(errors)}):")
        for err in errors:
            logger.error(f"  - {err}")
        logger.info("="*60)
        sys.exit(1)  # ← Выход с кодом ошибки
    else:
        logger.info("✓ RAG-база построена успешно!")
        logger.info("="*60)

if __name__ == "__main__":
    main()