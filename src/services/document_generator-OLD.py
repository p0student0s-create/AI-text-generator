# src/services/document_generator.py
"""
Генератор документов с поддержкой ГОСТ-оформления и отраслевой адаптации.
Конвертирует Markdown-контент в PDF через pandoc + xelatex/pdflatex.
"""
import logging
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class DocumentGenerator:
    """
    Генератор документов с поддержкой ГОСТ-оформления.
    """
    TEMPLATE_MAP = {
        "policy": "policy.tex",
        "regulation": "regulation.tex",
        "instruction": "instruction.tex",
        "threat_model": "threat_model.tex",
        "risk_assessment": "risk_assessment.tex",
        "incident_response": "incident_response.tex",
        "access_control": "access_control.tex",
    }
    
    DOC_HEADER_TEMPLATES = {
        "policy": "ПОЛИТИКА ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ",
        "regulation": "РЕГЛАМЕНТ ОБЕСПЕЧЕНИЯ ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ",
        "instruction": "ИНСТРУКЦИЯ ПО ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ",
        "threat_model": "МОДЕЛЬ УГРОЗ ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ",
        "risk_assessment": "ОЦЕНКА РИСКОВ ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ",
        "incident_response": "ПОЛИТИКА РЕАГИРОВАНИЯ НА ИНЦИДЕНТЫ ИБ",
        "access_control": "ПОЛИТИКА УПРАВЛЕНИЯ ДОСТУПОМ",
    }
    
    def __init__(self, output_dir: str = "storage/generated", 
                 template_dir: str = "storage/templates",
                 pdf_engine: str = "xelatex"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.template_dir = Path(template_dir)
        self.pdf_engine = pdf_engine
        self._rag_service = None
        
        logger.info(f"DocumentGenerator initialized: output_dir={self.output_dir}, "
                   f"template_dir={self.template_dir}, engine={pdf_engine}")
    
    def _get_rag_service(self):
        """Ленивая инициализация RAGService"""
        if self._rag_service is None:
            from src.services.rag_service import RAGService
            self._rag_service = RAGService()
        return self._rag_service
    
    def _get_template_path(self, doc_type: str) -> Optional[Path]:
        """Возвращает путь к шаблону по типу документа"""
        template_name = self.TEMPLATE_MAP.get(doc_type)
        if not template_name:
            logger.warning(f"Шаблон для типа '{doc_type}' не найден, используется policy.tex")
            template_name = "policy.tex"
        
        template_path = self.template_dir / template_name
        if not template_path.exists():
            logger.error(f"Шаблон не найден: {template_path}")
            return None
        return template_path
    
    def check_dependencies(self) -> Dict[str, bool]:
        """Проверка наличия внешних инструментов."""
        return {
            "pandoc": shutil.which("pandoc") is not None,
            "xelatex": shutil.which("xelatex") is not None,
            "pdflatex": shutil.which("pdflatex") is not None,
        }
    
    @staticmethod
    def _format_yaml_field(value: str) -> str:
        """Экранирование специальных символов для YAML и LaTeX."""
        if not value:
            return ""
        
        # Экранируем для YAML
        value = value.replace('\\', '\\\\').replace('"', '\\"').replace(':', '\\:')
        
        # Экранируем для LaTeX (дополнительно)
        value = value.replace('&', r'\&').replace('%', r'\%').replace('$', r'\$')
        value = value.replace('#', r'\#').replace('_', r'\_').replace('{', r'\{').replace('}', r'\}')
        
        # Удаляем переносы строк
        value = value.replace('\n', ' ').replace('\r', '')
        
        return value.strip()
    
    @staticmethod
    def _remove_duplicate_paragraphs(content: str, threshold: float = 0.95) -> str:
        """Удаление повторяющихся абзацев с учётом нормализации."""
        import hashlib
        
        paragraphs = content.split('\n\n')
        seen_hashes = set()
        result = []
        
        for p in paragraphs:
            p_stripped = p.strip()
            if not p_stripped:
                continue
            
            # Нормализация: нижний регистр, удаление лишних пробелов
            p_normalized = re.sub(r'\s+', ' ', p_stripped.lower())
            p_hash = hashlib.md5(p_normalized.encode('utf-8')).hexdigest()
            
            if p_hash not in seen_hashes:
                seen_hashes.add(p_hash)
                result.append(p)
        
        return '\n\n'.join(result)
    
    def _format_standards_yaml(self, standards: List[str]) -> str:
        """Форматирование стандартов для YAML."""
        if not standards:
            return "  - Не указаны"
        
        standard_names = {
            "152fz": "Федеральный закон №152-ФЗ от 27.07.2006 «О персональных данных»",
            "187fz": "Федеральный закон №187-ФЗ от 26.07.2017 «О безопасности КИИ»",
            "fstek_21": "Приказ ФСТЭК России №21 от 18.02.2013 «Об утверждении Состава и содержания организационных и технических мер по обеспечению безопасности персональных данных»",
            "fstek_239": "Приказ ФСТЭК России №239 от 25.12.2017 «Об утверждении Требований по обеспечению безопасности значимых объектов КИИ»",
            "fstek_17": "Приказ ФСТЭК России №17 от 11.02.2013 «Об утверждении Требований о защите информации в ГИС»",
            "gost_57580": "ГОСТ Р 57580-2017 «Информационная безопасность организаций. Общие требования»",
            "minzdrav_956n": "Приказ Минздрава России №956н от 15.12.2020 «Требования к защите ПДн в сфере здравоохранения»",
        }
        
        lines = []
        for std_key in standards:
            name = standard_names.get(std_key, std_key)
            # Экранируем ТОЛЬКО кавычки для YAML
            name = name.replace('"', '\\"')
            lines.append(f'  - "{name}"')
        
        return "\n".join(lines)
    
    def _assemble_markdown(self, 
                          title: str,
                          organization: str,
                          object_type: str,
                          data_category: str,
                          city: str,
                          standards: List[str],
                          sections: Dict[str, str],
                          context: Optional[Dict[str, Any]] = None) -> str:
        """Сборка Markdown-документа с метаданными."""
        
        # Получаем применимые стандарты через RAG
        org_name = context.get("organization", organization) if context else organization
        rag = self._get_rag_service()
        filtered_standards = rag.get_applicable_standards(
            organization_type=org_name,
            requested_standards=standards
        )
        
        # YAML frontmatter с правильным экранированием
        yaml_header = f"""---
title: "{self._format_yaml_field(title)}"
author: "{self._format_yaml_field(organization)}"
date: "{datetime.now().strftime('%d.%m.%Y')}"
lang: ru-RU
babel-lang: russian
fontfamily: times
fontsize: 14pt
geometry: "left=30mm,right=10mm,top=20mm,bottom=20mm"
linestretch: 1.5
indent: true
toc: true
toc-title: "Оглавление"
object_type: "{self._format_yaml_field(object_type)}"
data_category: "{self._format_yaml_field(data_category)}"
city: "{self._format_yaml_field(city)}"
standards:
{self._format_standards_yaml(filtered_standards)}
---
"""
        
        md = yaml_header
        
        # Сортируем разделы по номерам
        sorted_sections = sorted(
            sections.items(),
            key=lambda x: self._extract_section_number(x[0])
        )
        
        for section_title, content in sorted_sections:
            # Очищаем контент от дубликатов
            clean_content = content.strip()
            
            # Удаляем дублирующую нумерацию в заголовках
            clean_content = re.sub(r'^(#+\s*)\d+(?:\.\d+)*[\.\s]+\s*', r'\1', 
                                  clean_content, flags=re.MULTILINE)
            
            # Удаляем дубликаты абзацев
            clean_content = self._remove_duplicate_paragraphs(clean_content)
            
            # Удаляем дублирующиеся заголовки "Цели"
            clean_content = self._remove_duplicate_goals_headers(clean_content)
            
            md += f"{clean_content}\n"
        
        return md
    
    @staticmethod
    def _remove_duplicate_goals_headers(content: str) -> str:
        """Удаляет повторяющиеся заголовки 'Цели' внутри контента раздела"""
        lines = content.split('\n')
        result = []
        goals_count = 0
        
        for line in lines:
            stripped = line.strip()
            # Проверяем, является ли строка заголовком "Цели"
            if re.match(r'^#+\s*Цели\s*$', stripped, re.IGNORECASE):
                goals_count += 1
                if goals_count == 1:
                    result.append(line)
            else:
                result.append(line)
        
        return '\n'.join(result)
    
    def _extract_section_number(self, section_title: str) -> tuple:
        """Извлечение номера раздела для сортировки."""
        match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', section_title.strip())
        if match:
            parts = [int(p) for p in match.groups() if p]
            return tuple(parts)
        return (0,)
    
    def generate_pdf(self,
                    markdown_content: Dict[str, str],
                    context: Dict[str, Any],
                    engine: Optional[str] = None,
                    template: Optional[str] = None) -> str:
        """Конвертирует Markdown-контент в PDF."""
        
        doc_id = context.get("doc_id", "unknown")
        doc_type = context.get("doc_type", "policy")
        title = context.get("title", "Документ")
        organization = context.get("organization", "Организация")
        object_type = context.get("object_type", "")
        data_category = context.get("data_category", "")
        city = context.get("city", "г. Омск")
        standards = context.get("standards", [])
        
        # 1. Сборка Markdown
        full_md = self._assemble_markdown(
            title=title,
            organization=organization,
            object_type=object_type,
            data_category=data_category,
            city=city,
            standards=standards,
            sections=markdown_content,
            context=context
        )
        
        # 2. Пути для файлов
        md_path = self.output_dir / f"{doc_id}.md"
        pdf_path = self.output_dir / f"{doc_id}.pdf"
        
        # 3. Выбор шаблона
        if template and Path(template).exists():
            template_path = Path(template)
        elif engine and Path(engine).exists():
            template_path = Path(engine)
        else:
            template_path = self._get_template_path(doc_type)
        
        # 4. Проверка зависимостей
        deps = self.check_dependencies()
        if not deps.get("pandoc"):
            logger.warning("Pandoc не найден — возвращаем Markdown")
            md_path.write_text(full_md, encoding="utf-8")
            return str(md_path)
        
        # Сохраняем Markdown для отладки
        md_path.write_text(full_md, encoding="utf-8")
        logger.debug(f"Markdown сохранён: {md_path.resolve()}")
        
        # 5. Конвертация через pandoc
        try:
            self._convert_via_pandoc(
                md_path=md_path,
                pdf_path=pdf_path,
                template=template_path,
                context=context,
                pdf_engine=self.pdf_engine
            )
            
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                logger.info(f"✓ PDF сгенерирован: {pdf_path}")
                return str(pdf_path)
            else:
                logger.warning("PDF создан, но пустой — возвращаем Markdown")
                return str(md_path)
                
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode() if hasattr(e.stderr, 'decode') else str(e)
            logger.error(f"Pandoc/LaTeX ошибка: {stderr_msg[:500]}")
            return str(md_path)
        except FileNotFoundError as e:
            logger.warning(f"Инструмент не найден: {e}")
            return str(md_path)
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
            return str(md_path)
    
    def _convert_via_pandoc(self,
                           md_path: Path,
                           pdf_path: Path,
                           template: Optional[Path],
                           context: Dict[str, Any],
                           pdf_engine: str = "xelatex"):
        """Конвертация Markdown → PDF через pandoc."""
        
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown не найден: {md_path}")
        
        if not shutil.which("pandoc"):
            raise FileNotFoundError("Pandoc не найден в PATH")
        
        if not shutil.which(pdf_engine):
            logger.warning(f"{pdf_engine} не найден, пробуем pdflatex")
            pdf_engine = "pdflatex" if shutil.which("pdflatex") else "xelatex"
            
            if not shutil.which(pdf_engine):
                raise FileNotFoundError(f"Ни {pdf_engine}, ни pdflatex не найдены")
        
        # Формирование заголовка документа
        doc_type = context.get("doc_type", "policy")
        organization = context.get("organization", "Организация")
        base_header = self.DOC_HEADER_TEMPLATES.get(doc_type, "ДОКУМЕНТ ПО ИБ")
        doc_header = f"{base_header} | {organization}"
        
        # Базовая команда pandoc
        cmd = [
            "pandoc",
            str(md_path.resolve()),
            "-o", str(pdf_path.resolve()),
            f"--pdf-engine={pdf_engine}",
            "--syntax-highlighting=none",
            "--toc", "--toc-depth=3",
            "--metadata", f"title={self._format_yaml_field(context.get('title', 'Документ'))}",
            "--metadata", f"author={self._format_yaml_field(organization)}",
            "--metadata", f"doc_header={self._format_yaml_field(doc_header)}",
            "--metadata", f"objectType={self._format_yaml_field(context.get('object_type', ''))}",
            "--metadata", f"dataCategory={self._format_yaml_field(context.get('data_category', ''))}",
            "--metadata", f"city={self._format_yaml_field(context.get('city', 'Омск'))}",
            "--metadata", f"date={self._format_yaml_field(datetime.now().strftime('%d.%m.%Y'))}",
        ]
        
        if template and template.exists():
            cmd.extend(["--template", str(template.resolve())])
            logger.info(f"Шаблон: {template}")
        
        logger.info(f"Base-директория: {self.template_dir / 'base'}")
        logger.info(f"Запуск pandoc: {' '.join(cmd[:10])}...")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            encoding='utf-8',
            cwd=str(self.template_dir)
        )
        
        if result.returncode != 0:
            error_log = (result.stderr or result.stdout or "").strip().split("\n")
            logger.error(f"Pandoc ошибка (код {result.returncode}):")
            for line in error_log[:10]:
                logger.error(f"  {line}")
            raise subprocess.CalledProcessError(
                result.returncode, cmd, output=result.stdout, stderr=result.stderr
            )
    
    def generate_markdown_only(self,
                              markdown_content: Dict[str, str],
                              context: Dict[str, Any]) -> str:
        """Генерация только Markdown."""
        doc_id = context.get("doc_id", "unknown")
        md_path = self.output_dir / f"{doc_id}.md"
        
        full_md = self._assemble_markdown(
            title=context.get("title", "Документ"),
            organization=context.get("organization", "Организация"),
            object_type=context.get("object_type", ""),
            data_category=context.get("data_category", ""),
            city=context.get("city", "г. Омск"),
            standards=context.get("standards", []),
            sections=markdown_content,
            context=context
        )
        
        md_path.write_text(full_md, encoding="utf-8")
        logger.info(f"Markdown сохранён: {md_path}")
        return str(md_path)
    
    def get_output_formats(self) -> List[str]:
        """Доступные форматы вывода."""
        formats = ["markdown"]
        deps = self.check_dependencies()
        if deps.get("pandoc"):
            formats.append("pdf")
        if deps.get("xelatex"):
            formats.append("pdf+xelatex")
        return formats