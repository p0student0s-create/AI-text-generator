# src/utils/structure_extractor.py
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

try:
    from docx import Document
except ImportError:
    Document = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

logger = logging.getLogger(__name__)

@dataclass
class StructureNode:
    """Узел иерархии документа"""
    id: str
    number: str  # "1", "1.1", "1.1.1"
    title: str
    level: int  # 1, 2, 3...
    parent_id: Optional[str] = None
    content_preview: str = ""
    page: Optional[int] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "level": self.level,
            "parent_id": self.parent_id,
            "content_preview": self.content_preview[:200],
            "page": self.page
        }

class StructureExtractor:
    """
    Извлечение иерархической структуры из нормативных документов.
    Поддерживает: DOCX, PDF, TXT, MD
    """
    
    # Паттерны для нумерации разделов (ГОСТ, общие)
    SECTION_PATTERNS = [
        # "1.1.1 Заголовок" или "1.1.1. Заголовок"
        (r'^(\d+(?:\.\d+){0,3})\.?\s+([А-Я][а-яА-Я0-9\-\(\)\"]{3,})', 3),
        # "1 ОБЩИЕ ПОЛОЖЕНИЯ" (раздел верхнего уровня)
        (r'^(\d+)\s+([А-Я][А-Яа-я\-\ ]{5,})$', 1),
        # "## 1.1 Подраздел" (Markdown)
        (r'^#{1,3}\s*(\d+(?:\.\d+){0,3})\.?\s+([А-Я][а-яА-Я0-9\-\(\)\"]{3,})', 2),
        # "Раздел 1. Название"
        (r'^(?:раздел|глава)\s+(\d+(?:\.\d+){0,3})\.?\s*[:\-]?\s*([А-Я][а-яА-Я0-9\-\(\)\"]{3,})', 2),
    ]
    
    def __init__(self, min_title_length: int = 5):
        self.min_title_length = min_title_length
    
    def _calculate_level(self, number: str) -> int:
        """Определение уровня вложенности по номеру (1=1, 1.1=2, 1.1.1=3)"""
        return len(number.split('.'))
    
    def _parse_line(self, line: str, prev_level: int) -> Tuple[Optional[StructureNode], int]:
        """
        Анализ строки на наличие заголовка раздела.
        
        Returns:
            (StructureNode или None, новый уровень)
        """
        line = line.strip()
        if not line or len(line) < self.min_title_length + 3:
            return None, prev_level
        
        for pattern, priority in self.SECTION_PATTERNS:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                number = match.group(1).rstrip('.')
                title = match.group(2).strip()
                
                # Фильтр: заголовок должен быть осмысленным
                if len(title) < self.min_title_length:
                    continue
                
                level = self._calculate_level(number)
                
                return StructureNode(
                    id=f"sec_{number.replace('.', '_')}",
                    number=number,
                    title=title,
                    level=level,
                    content_preview=""  # Заполняется позже
                ), level
        
        return None, prev_level
    
    def extract_from_text(self, text: str, source_file: str) -> List[StructureNode]:
        """
        Извлечение структуры из текста документа.
        
        Алгоритм:
        1. Разбиваем на строки
        2. Ищем заголовки по паттернам
        3. Строим иерархию по уровням вложенности
        4. Добавляем превью контента для каждого раздела
        """
        nodes = []
        lines = text.split('\n')
        
        stack: List[StructureNode] = []  # Стек для построения иерархии
        current_node: Optional[StructureNode] = None
        current_content: List[str] = []
        
        for i, line in enumerate(lines):
            # Проверяем, не заголовок ли это
            node, level = self._parse_line(line, stack[-1].level if stack else 0)
            
            if node:
                # Сохраняем предыдущий узел с накопленным контентом
                if current_node and current_content:
                    current_node.content_preview = '\n'.join(current_content[:5]).strip()
                    nodes.append(current_node)
                
                # Устанавливаем родителя по уровню вложенности
                while stack and stack[-1].level >= level:
                    stack.pop()
                
                if stack:
                    node.parent_id = stack[-1].id
                
                stack.append(node)
                current_node = node
                current_content = []
            else:
                # Накопление контента для текущего раздела
                if current_node and line.strip():
                    current_content.append(line.strip())
        
        # Добавляем последний узел
        if current_node and current_content:
            current_node.content_preview = '\n'.join(current_content[:5]).strip()
            nodes.append(current_node)
        
        logger.info(f"Извлечено {len(nodes)} разделов из {source_file}")
        return nodes
    
    def extract_from_docx(self, file_path: Path) -> List[StructureNode]:
        """Извлечение структуры из DOCX с учётом стилей заголовков"""
        if Document is None:
            raise ImportError("Установите python-docx: pip install python-docx")
        
        doc = Document(file_path)
        text_parts = []
        
        for para in doc.paragraphs:
            style = para.style.name.lower() if para.style else ""
            text = para.text.strip()
            
            if not text:
                continue
            
            # Если стиль — заголовок, добавляем маркер уровня
            if 'heading' in style:
                level = int(style.replace('heading', '').strip()) if style.replace('heading', '').strip().isdigit() else 1
                text_parts.append(f"{'#' * level} {text}")
            else:
                text_parts.append(text)
        
        full_text = '\n'.join(text_parts)
        return self.extract_from_text(full_text, file_path.name)
    
    def extract_from_pdf(self, file_path: Path) -> List[StructureNode]:
        """Извлечение структуры из PDF (базовое, без OCR)"""
        if PyPDF2 is None:
            raise ImportError("Установите PyPDF2: pip install PyPDF2")
        
        text_parts = []
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
        
        full_text = '\n\n'.join(text_parts)
        return self.extract_from_text(full_text, file_path.name)
    
    def extract_from_file(self, file_path: Path) -> List[StructureNode]:
        """Универсальный метод извлечения структуры из файла"""
        ext = file_path.suffix.lower()
        
        if ext == '.docx':
            return self.extract_from_docx(file_path)
        elif ext == '.pdf':
            return self.extract_from_pdf(file_path)
        elif ext in ['.txt', '.md', '.markdown']:
            text = file_path.read_text(encoding='utf-8')
            return self.extract_from_text(text, file_path.name)
        else:
            logger.warning(f"Неподдерживаемый формат: {ext}")
            return []
    
    def build_hierarchy_tree(self, nodes: List[StructureNode]) -> Dict:
        """
        Преобразование плоского списка узлов в дерево.
        
        Returns:
            {"root": [...], "nodes_by_id": {...}}
        """
        nodes_by_id = {node.id: node.to_dict() for node in nodes}
        root_children = []
        
        for node in nodes:
            node_dict = nodes_by_id[node.id]
            if node.parent_id and node.parent_id in nodes_by_id:
                parent = nodes_by_id[node.parent_id]
                if 'children' not in parent:
                    parent['children'] = []
                parent['children'].append(node_dict)
            else:
                root_children.append(node_dict)
        
        return {
            "root": root_children,
            "nodes_by_id": nodes_by_id,
            "total_sections": len(nodes)
        }