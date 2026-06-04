# scr/utils/chunker.py
import re
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SmartChunk:
    """Умный чанк с метаданными"""
    text: str
    source: str
    doc_type: str
    chunk_index: int
    section: Optional[str] = None
    clause: Optional[str] = None
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        result = {
            "text": self.text,
            "source": self.source,
            "doc_type": self.doc_type,
            "chunk_index": self.chunk_index,
        }
        if self.section:
            result["section"] = self.section
        if self.clause:
            result["clause"] = self.clause
        if self.metadata:
            result.update(self.metadata)
        return result


class SmartChunker:
    """
    Умная разбивка документов на чанки с учетом:
    - Структуры документа (разделы, пункты)
    - Семантических границ (абзацы)
    - Перекрытия для сохранения контекста
    """
    
    def __init__(self, chunk_size: int = 1024, overlap: int = 128):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def _extract_metadata_from_text(self, text: str) -> Dict:
        """Извлечение метаданных из начала текста"""
        metadata = {}
        
        # Ищем номер пункта
        clause_match = re.search(r'^(\d+(?:\.\d+){1,3})', text)
        if clause_match:
            metadata["clause"] = clause_match.group(1)
        
        # Ищем заголовок (первая строка после номера)
        lines = text.strip().split('\n')
        if lines:
            first_line = re.sub(r'^\d+(?:\.\d+)*[\s:—-]+', '', lines[0]).strip()
            if first_line and len(first_line) < 200:
                metadata["title"] = first_line
        
        return metadata
    
    def chunk_by_structure(self, documents: List[Dict]) -> List[SmartChunk]:
        """
        Разбивка с приоритетом на структурные единицы
        
        Если документ уже содержит section/clause, используем их.
        Иначе пытаемся извлечь из текста.
        """
        chunks = []
        
        for doc in documents:
            text = doc.get("text", "")
            source = doc.get("source", "unknown")
            doc_type = doc.get("doc_type", "unknown")
            section = doc.get("section")
            clause = doc.get("clause")
            
            # Если текст слишком короткий, создаем один чанк
            if len(text) <= self.chunk_size:
                metadata = self._extract_metadata_from_text(text)
                chunks.append(SmartChunk(
                    text=text.strip(),
                    source=source,
                    doc_type=doc_type,
                    chunk_index=len(chunks),
                    section=section or metadata.get("section"),
                    clause=clause or metadata.get("clause"),
                    metadata=metadata
                ))
                continue
            
            # Разбиваем по абзацам
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
            
            current_chunk_text = ""
            current_section = section
            current_clause = clause
            chunk_idx = 0
            
            for para in paragraphs:
                # Проверяем, не начинается ли новый пункт в этом абзаце
                para_metadata = self._extract_metadata_from_text(para)
                if para_metadata.get("clause"):
                    current_clause = para_metadata["clause"]
                
                # Если добавление абзаца превысит лимит
                if len(current_chunk_text) + len(para) > self.chunk_size and current_chunk_text:
                    # Сохраняем текущий чанк
                    chunks.append(SmartChunk(
                        text=current_chunk_text.strip(),
                        source=source,
                        doc_type=doc_type,
                        chunk_index=chunk_idx,
                        section=current_section,
                        clause=current_clause
                    ))
                    chunk_idx += 1
                    
                    # Создаем перекрытие
                    overlap_text = self._create_overlap(current_chunk_text, para)
                    current_chunk_text = overlap_text
                    current_clause = current_clause  # Сохраняем контекст
                else:
                    current_chunk_text += (" " if current_chunk_text else "") + para
            
            # Последний чанк
            if current_chunk_text.strip():
                chunks.append(SmartChunk(
                    text=current_chunk_text.strip(),
                    source=source,
                    doc_type=doc_type,
                    chunk_index=chunk_idx,
                    section=current_section,
                    clause=current_clause
                ))
        
        logger.info(f"Создано {len(chunks)} структурированных чанков из {len(documents)} документов")
        return chunks
    
    def _create_overlap(self, current_text: str, next_para: str) -> str:
        """Создание перекрытия между чанками"""
        if self.overlap == 0:
            return next_para
        
        # Берем последние слова из текущего чанка
        words = current_text.split()
        overlap_words = words[-(self.overlap // 6):] if len(words) > 0 else []
        
        return " ".join(overlap_words) + " " + next_para
    
    def chunk_documents(
        self, 
        documents: List[Dict], 
        preserve_structure: bool = True
    ) -> List[Dict]:
        """
        Публичный метод для разбивки документов
        
        Args:
            documents: Список документов
            preserve_structure: Если True, пытается сохранить структурные границы
        
        Returns:
            Список чанков в формате Dict
        """
        if preserve_structure:
            chunks = self.chunk_by_structure(documents)
        else:
            # Простая разбивка без учета структуры
            chunks = self._simple_chunk(documents)
        
        return [chunk.to_dict() for chunk in chunks]
    
    def _simple_chunk(self, documents: List[Dict]) -> List[SmartChunk]:
        """Простая разбивка без учета структуры (для обратной совместимости)"""
        chunks = []
        
        for doc in documents:
            text = doc.get("text", "")
            source = doc.get("source", "unknown")
            doc_type = doc.get("doc_type", "unknown")
            
            if len(text) <= self.chunk_size:
                chunks.append(SmartChunk(
                    text=text.strip(),
                    source=source,
                    doc_type=doc_type,
                    chunk_index=len(chunks)
                ))
                continue
            
            # Разбиваем по абзацам
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
            current_chunk = ""
            chunk_idx = 0
            
            for para in paragraphs:
                if len(current_chunk) + len(para) > self.chunk_size and current_chunk:
                    chunks.append(SmartChunk(
                        text=current_chunk.strip(),
                        source=source,
                        doc_type=doc_type,
                        chunk_index=chunk_idx
                    ))
                    chunk_idx += 1
                    
                    # Перекрытие
                    words = current_chunk.split()
                    overlap_words = words[-(self.overlap // 6):] if self.overlap > 0 else []
                    current_chunk = " ".join(overlap_words) + " " + para
                else:
                    current_chunk += (" " if current_chunk else "") + para
            
            if current_chunk.strip():
                chunks.append(SmartChunk(
                    text=current_chunk.strip(),
                    source=source,
                    doc_type=doc_type,
                    chunk_index=chunk_idx
                ))
        
        return chunks


# Фабричная функция для удобства
def create_chunker(chunk_size: int = 1024, overlap: int = 128) -> SmartChunker:
    return SmartChunker(chunk_size=chunk_size, overlap=overlap)


# Обратная совместимость
def chunk_documents(documents: List[Dict], chunk_size: int = 1024, overlap: int = 128) -> List[Dict]:
    """Старая функция для обратной совместимости"""
    chunker = SmartChunker(chunk_size=chunk_size, overlap=overlap)
    return chunker.chunk_documents(documents, preserve_structure=False)