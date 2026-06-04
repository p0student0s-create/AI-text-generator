# src/services/codebase_scanner.py
"""
Сканер структуры проекта для извлечения контекста при генерации ВКР
"""
import logging
import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CodeElement:
    """Представление элемента кода для анализа."""
    name: str
    element_type: str  # class, function, method, variable
    file_path: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    signature: Optional[str] = None
    dependencies: Set[str] = field(default_factory=set)
    imports: List[str] = field(default_factory=list)
    
    def to_markdown(self) -> str:
        """Конвертация в Markdown для включения в ВКР."""
        md = f"### `{self.name}` ({self.element_type})\n"
        md += f"**Файл:** `{self.file_path}` (строки {self.line_start}-{self.line_end})\n\n"
        if self.signature:
            md += f"```python\n{self.signature}\n```\n\n"
        if self.docstring:
            md += f"{self.docstring.strip()}\n\n"
        if self.dependencies:
            md += f"**Зависимости:** {', '.join(sorted(self.dependencies))}\n"
        return md


class CodebaseScanner:
    """
    Сканер кодовой базы для извлечения архитектурного контекста.
    
    Используется при генерации разделов ВКР:
    - Глава 2: Проектирование архитектуры
    - Глава 3: Реализация прототипа
    - Приложения: фрагменты кода
    """
    
    TARGET_EXTENSIONS = {'.py', '.md', '.yaml', '.yml', '.json', '.toml'}
    EXCLUDE_DIRS = {'.git', '__pycache__', 'venv', '.venv', 'node_modules', 'storage'}
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.elements: Dict[str, List[CodeElement]] = {}  # file_path -> elements
        self.modules: Dict[str, Dict] = {}  # module_name -> metadata
        
    def scan(self, include_docs: bool = True) -> Dict[str, any]:
        """
        Сканирование проекта и извлечение структурной информации.
        
        :param include_docs: Включать ли markdown-документацию
        :return: Словарь с результатами сканирования
        """
        logger.info(f"Сканирование проекта: {self.project_root}")
        
        results = {
            "project_root": str(self.project_root),
            "scan_time": datetime.now().isoformat(),
            "structure": {},
            "modules": {},
            "statistics": {},
            "architecture_notes": [],
        }
        
        # 1. Сканирование Python-файлов
        py_files = list(self.project_root.rglob("*.py"))
        py_files = [f for f in py_files if not any(excl in f.parts for excl in self.EXCLUDE_DIRS)]
        
        for py_file in py_files:
            try:
                elements = self._parse_python_file(py_file)
                if elements:
                    rel_path = str(py_file.relative_to(self.project_root))
                    self.elements[rel_path] = elements
                    results["structure"][rel_path] = [
                        {"name": e.name, "type": e.element_type, "line": e.line_start}
                        for e in elements
                    ]
            except Exception as e:
                logger.warning(f"⚠ Ошибка парсинга {py_file}: {e}")
        
        # 2. Извлечение метаданных модулей
        for file_path, elements in self.elements.items():
            module_name = file_path.replace("/", ".").replace(".py", "")
            classes = [e for e in elements if e.element_type == "class"]
            functions = [e for e in elements if e.element_type == "function"]
            
            self.modules[module_name] = {
                "classes": [c.name for c in classes],
                "functions": [f.name for f in functions],
                "total_elements": len(elements),
                "has_docstrings": any(e.docstring for e in elements),
            }
        
        # 3. Генерация архитектурных заметок для ВКР
        results["architecture_notes"] = self._generate_architecture_notes()
        
        # 4. Статистика
        all_elements = [e for elems in self.elements.values() for e in elems]
        results["statistics"] = {
            "total_files": len(self.elements),
            "total_classes": sum(1 for e in all_elements if e.element_type == "class"),
            "total_functions": sum(1 for e in all_elements if e.element_type == "function"),
            "files_with_docstrings": sum(1 for elems in self.elements.values() 
                                       if any(e.docstring for e in elems)),
        }
        
        logger.info(f"✓ Просканировано: {results['statistics']['total_files']} файлов, "
                   f"{results['statistics']['total_classes']} классов, "
                   f"{results['statistics']['total_functions']} функций")
        
        return results
    
    def _parse_python_file(self, file_path: Path) -> List[CodeElement]:
        """Парсинг Python-файла с извлечением AST-элементов."""
        elements = []
        
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return elements
        
        rel_path = str(file_path.relative_to(self.project_root))
        
        # Извлечение классов
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                docstring = ast.get_docstring(node)
                methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                
                elements.append(CodeElement(
                    name=node.name,
                    element_type="class",
                    file_path=rel_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    docstring=docstring,
                    signature=f"class {node.name}:",
                    dependencies=set(methods),
                ))
            
            elif isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
                # Пропускаем методы внутри классов (они уже учтены)
                if any(isinstance(parent, ast.ClassDef) for parent in ast.walk(tree) 
                      if hasattr(parent, 'body') and node in parent.body):
                    continue
                    
                docstring = ast.get_docstring(node)
                args = [arg.arg for arg in node.args.args if arg.arg != "self"]
                signature = f"def {node.name}({', '.join(args)})"
                
                # Извлечение импортов в функции
                imports = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        imports.extend(alias.name for alias in child.names)
                    elif isinstance(child, ast.ImportFrom):
                        imports.append(f"{child.module}")
                
                elements.append(CodeElement(
                    name=node.name,
                    element_type="function",
                    file_path=rel_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    docstring=docstring,
                    signature=signature,
                    imports=imports,
                ))
        
        return elements
    
    def _generate_architecture_notes(self) -> List[str]:
        """Генерация заметок об архитектуре для включения в ВКР."""
        notes = []
        
        # Анализ агентов
        agent_files = [f for f in self.elements if "agent" in f.lower()]
        if agent_files:
            agents = []
            for f in agent_files:
                for e in self.elements[f]:
                    if e.element_type == "class" and "Agent" in e.name:
                        agents.append(e.name)
            if agents:
                notes.append(f"Многоагентная архитектура: {', '.join(agents)}")
        
        # Анализ сервисов
        service_files = [f for f in self.elements if "service" in f.lower()]
        if service_files:
            services = [Path(f).stem for f in service_files]
            notes.append(f"Сервисный слой: {', '.join(services)}")
        
        # Анализ RAG-компонентов
        rag_elements = []
        for elems in self.elements.values():
            for e in elems:
                if "rag" in e.name.lower() or "retrieval" in (e.docstring or "").lower():
                    rag_elements.append(f"{e.name} ({Path(e.file_path).name})")
        if rag_elements:
            notes.append(f"RAG-компоненты: {', '.join(rag_elements[:5])}")
        
        # Анализ конфигурации
        config_files = list(self.project_root.rglob("*.yaml")) + list(self.project_root.rglob("*.toml"))
        if config_files:
            notes.append(f"Конфигурация: {len(config_files)} файлов")
        
        return notes
    
    def get_element_for_section(self, section_title: str) -> Optional[CodeElement]:
        """
        Поиск элемента кода, релевантного для раздела ВКР.
        
        :param section_title: Заголовок раздела (например, "Оркестрация")
        :return: Наиболее релевантный CodeElement или None
        """
        keywords = {
            "оркестр": ["orchestrator", "Orchestrator", "управление", "поток"],
            "агент": ["agent", "Agent", "архитектор", "писатель", "критик", "аудитор"],
            "rag": ["rag", "retrieval", "chroma", "эмбеддинг", "поиск"],
            "граф": ["neo4j", "graph", "узел", "связь", "knowledge"],
            "писатель": ["writer", "Writer", "генерация", "контент", "prompt"],
            "критик": ["critic", "Critic", "оценка", "качество", "валидация"],
        }
        
        section_lower = section_title.lower()
        
        for elems in self.elements.values():
            for elem in elems:
                elem_text = f"{elem.name} {elem.docstring or ''}".lower()
                for key_group, keywords_list in keywords.items():
                    if key_group in section_lower:
                        if any(kw.lower() in elem_text for kw in keywords_list):
                            return elem
        
        return None
    
    def generate_section_context(self, section_title: str, section_number: str) -> str:
        """
        Генерация контекста для раздела ВКР на основе сканирования кода.
        
        :param section_title: Заголовок раздела
        :param section_number: Номер раздела (например, "2.1")
        :return: Markdown-контекст для включения в промпт
        """
        context = f"## {section_number}. {section_title}\n\n"
        context += "### Реализация в коде проекта:\n\n"
        
        elem = self.get_element_for_section(section_title)
        if elem:
            context += elem.to_markdown()
        else:
            # fallback: показать статистику по релевантным файлам
            relevant_files = [f for f in self.elements 
                            if any(kw in f.lower() for kw in section_title.lower().split())]
            if relevant_files:
                context += "**Релевантные файлы:**\n"
                for f in relevant_files[:3]:
                    context += f"- `{f}` ({len(self.elements[f])} элементов)\n"
            else:
                context += "*Контекст кода не найден — раздел описывает концептуальные аспекты.*\n"
        
        return context