# scripts\index_standards.py
"""
Индексация нормативных документов в RAG-базу
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_requirements_from_text(text: str, standard_key: str, source_file: str) -> List[Dict[str, Any]]:
    """
    Извлекает требования из текстового файла стандарта.
    
    :param text: Текст стандарта
    :param standard_key: Ключ стандарта (152fz, fstek_21 и т.д.)
    :param source_file: Путь к исходному файлу
    :return: Список требований
    """
    requirements = []
    
    # Разбиваем текст на строки
    lines = text.split('\n')
    
    current_section = ""
    current_clause = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Ищем номера статей/пунктов
        # Для 152-ФЗ: "Статья 1.", "Статья 19"
        # Для ФСТЭК: "15.", "п. 15"
        clause_match = re.match(r'^(?:Статья\s+)?(\d+(?:\.\d+)?)\.?\s+(.+)$', line)
        
        if clause_match:
            current_clause = clause_match.group(1)
            clause_title = clause_match.group(2)
            
            requirements.append({
                "text": line,
                "standard_type": standard_key,
                "section": current_section,
                "clause": current_clause,
                "clause_title": clause_title,
                "page": None,
                "source_file": source_file,
            })
        elif line and current_clause:
            # Продолжение пункта — добавляем к предыдущему
            if requirements:
                requirements[-1]["text"] += " " + line
        
        # Ищем разделы
        section_match = re.search(r'Глава\s+(\d+)|Раздел\s+(\d+)|Глава\s+([IVX]+)', line)
        if section_match:
            current_section = section_match.group(0)
    
    logger.info(f"Извлечено {len(requirements)} требований из {source_file}")
    return requirements


def index_standards(standards_dir: str = "data/documents/standards"):
    """
    Индексирует все стандарты из директории.
    """
    from src.services.rag_service import RAGService
    rag = RAGService()
    
    # Маппинг файлов на ключи стандартов
    standard_mapping = {
        "152-fz": "152fz",
        "187-fz": "187fz",
        "fstek_239": "fstek_239",
        "fstek_21": "fstek_21",
        "gost-57580": "gost_57580",
        "minzdrav_956n": "minzdrav_956n",
    }
    
    standards_path = Path(standards_dir)
    
    if not standards_path.exists():
        logger.warning(f"Директория стандартов не найдена: {standards_dir}")
        return
    
    for file_path in standards_path.glob("*"):
        if file_path.suffix.lower() not in [".txt", ".md", ".pdf"]:
            continue
            
        logger.info(f"Обработка файла: {file_path.name}")
        
        # Определяем ключ стандарта
        standard_key = None
        for key_pattern, std_key in standard_mapping.items():
            if key_pattern in file_path.name.lower():
                standard_key = std_key
                break
        
        if not standard_key:
            # Используем имя файла без расширения
            standard_key = file_path.stem.replace("-", "_").replace(".", "_")
            logger.warning(f"Не найден маппинг для {file_path.name}, используем ключ: {standard_key}")
        
        # Извлекаем текст (для PDF нужен PyPDF2)
        text = ""
        if file_path.suffix.lower() == ".pdf":
            try:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
            except ImportError:
                logger.warning(f"PyPDF2 не установлен, пропускаем PDF: {file_path.name}")
                continue
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        
        # Извлекаем требования
        requirements = extract_requirements_from_text(text, standard_key, str(file_path))
        
        if requirements:
            # Добавляем в RAG
            rag.add_documents(
                documents=requirements,
                standard_type=standard_key,
                source_file=str(file_path)
            )
            logger.info(f"✓ Добавлено {len(requirements)} требований для {standard_key}")
        else:
            logger.warning(f"⚠ Не извлечено требований из {file_path.name}")
    
    # Показываем статистику
    stats = rag.get_statistics()
    logger.info(f"\nСтатистика RAG-базы: {stats}")


if __name__ == "__main__":
    index_standards()