# src/services/bibliography_manager.py
import re
from typing import List, Dict, Optional
from pathlib import Path

class BibliographyManager:
    """Управление источниками и цитированием по ГОСТ Р 7.0.5-2008"""
    
    GOST_TEMPLATES = {
        "book": "{author}. {title} / {author}. — {edition}. — {city}: {publisher}, {year}. — {pages} с.",
        "article": "{author}. {title} // {journal}. — {year}. — №{issue}. — С. {pages}.",
        "online": "{author}. {title} [Электронный ресурс]. — Режим доступа: {url} (дата обращения: {access_date}).",
        "standard": "{title} : {type} {number}. — Введ. {date}. — {city}: {publisher}, {year}. — {pages} с.",
    }
    
    def __init__(self, bib_file: Optional[str] = None):
        self.sources: Dict[str, Dict] = {}
        self.citation_counter = 1
        if bib_file and Path(bib_file).exists():
            self.load_from_bib(bib_file)
    
    def add_source(self, source: Dict) -> str:
        """Добавляет источник и возвращает ключ цитирования [1], [2]..."""
        key = source.get("key") or f"src_{self.citation_counter}"
        if key not in self.sources:
            self.sources[key] = {**source, "citation_number": self.citation_counter}
            self.citation_counter += 1
        return f"[{self.sources[key]['citation_number']}]"
    
    def format_citation(self, keys: List[str], style: str = "gost") -> str:
        """Форматирует ссылку: [1], [2-5], [1, 3, 7]"""
        if not keys:
            return ""
        
        # Фильтруем только существующие ключи
        valid_keys = [k for k in keys if k in self.sources]
        if not valid_keys:
            return ""
        
        numbers = sorted([self.sources[k]["citation_number"] for k in valid_keys])
        if not numbers:
            return ""
        
        # Группировка диапазонов: [1,2,3,5,6] → [1-3, 5-6]
        ranges = []
        start = end = numbers[0]
        for n in numbers[1:]:
            if n == end + 1:
                end = n
            else:
                ranges.append(f"{start}-{end}" if start != end else str(start))
                start = end = n
        ranges.append(f"{start}-{end}" if start != end else str(start))
        
        return "[" + ", ".join(ranges) + "]"
    
    def get_source_by_key(self, key: str) -> Optional[Dict]:
        """Возвращает источник по ключу или None"""
        return self.sources.get(key)

    def generate_bibliography(self, style: str = "gost-r-7-0-5-2008") -> str:
        """Генерирует список литературы в формате ГОСТ"""
        lines = []
        for key, src in sorted(self.sources.items(), key=lambda x: x[1]["citation_number"]):
            entry_type = src.get("type", "online")
            template = self.GOST_TEMPLATES.get(entry_type, self.GOST_TEMPLATES["online"])
            
            # Подстановка полей с обработкой None
            formatted = template
            for field in ["author", "title", "journal", "publisher", "city", "year", "pages", "issue", "url", "access_date", "edition", "type", "number", "date"]:
                value = src.get(field, "б. и." if field == "publisher" else "б. г." if field == "year" else "")
                formatted = formatted.replace(f"{{{field}}}", str(value))
            
            lines.append(f"{src['citation_number']}. {formatted}")
        
        return "\n".join(lines)
    
    def load_from_bib(self, bib_path: str):
        """Загрузка из BibTeX-файла (упрощённый парсер)"""
        with open(bib_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Простой парсер @article{key, ...}
        entries = re.findall(r'@(\w+)\{([^,]+),\s*([^@]+?)\n*\}', content, re.DOTALL)
        for entry_type, key, fields_str in entries:
            fields = {"type": entry_type, "key": key.strip()}
            for field in re.findall(r'(\w+)\s*=\s*\{([^}]+)\}', fields_str):
                fields[field[0].strip()] = field[1].strip()
            self.add_source(fields)