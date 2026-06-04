# src/agents/orchestrator.py
"""
Оркестратор генерации документов: управление потоком выполнения агентов
"""
import logging
import asyncio
from typing import Optional, Callable, Dict, Any, List, Union
from datetime import datetime
from pathlib import Path

from src.agents.base import AgentInput, AgentOutput, DocumentMode
from src.agents.architector import ArchitectAgent
from src.agents.writer import create_writer, BaseWriter
from src.agents.critic import CriticAgent
from src.agents.auditor import AuditorAgent
from src.services.document_generator import DocumentGenerator
from src.services.ollama_client import OllamaClient
from src.services.rag_service import RAGService
from src.services.industry_classifier import (
    RegulatoryClassifier, 
    RegulatoryProfile, 
    RegulatoryRegime
)
from src.services.codebase_scanner import CodebaseScanner

logger = logging.getLogger(__name__)

# Маппинг режимов документа на конкретные типы
DOC_MODE_MAP: Dict[DocumentMode, Dict[str, str]] = {
    DocumentMode.REGULATORY: {
        "policy": "policy",
        "instruction": "instruction", 
        "regulation": "regulation",
        "threat_model": "threat_model",
    },
    DocumentMode.THESIS: {
        "vkr_report": "vkr_report",
        "article": "vkr_report",
    },
    DocumentMode.REPORT: {
        "report": "policy",
    },
}


def _resolve_doc_type(doc_mode: DocumentMode, subtype: Optional[str] = None) -> str:
    """Преобразует doc_mode + subtype в конкретный тип документа."""
    mapping = DOC_MODE_MAP.get(doc_mode, {})
    if subtype and subtype in mapping:
        return mapping[subtype]
    return list(mapping.values())[0] if mapping else "policy"


class GenerationContext:
    """Контекст генерации документа с поддержкой отраслевого профиля."""
    
    def __init__(
        self, 
        doc_type: str, 
        standards: List[str], 
        **kwargs: Any
    ):
        self.doc_type: str = doc_type
        self.standards: List[str] = standards
        self.organization: str = kwargs.get("organization", "Организация")
        self.object_type: str = kwargs.get("object_type", "Информационная система")
        self.data_category: str = kwargs.get("data_category", "Конфиденциальная информация")
        self.title: str = kwargs.get("title", "Документ")
        self.city: str = kwargs.get("city", "г. Омск")
        
        self.regulatory_regime: Optional[RegulatoryRegime] = None
        self.regulatory_profile: Optional[RegulatoryProfile] = None
        
        self.requirements: List[Dict[str, Any]] = []
        self.structure_plan: Optional[Dict[str, Any]] = None
        self.generated_content: Dict[str, str] = {}
        self.compliance_report: Optional[Dict[str, Any]] = None
        
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.errors: List[str] = []
        self.doc_id: str = f"doc_{doc_type}_{int(datetime.now().timestamp())}"
        
        # Дополнительные метаданные для ВКР
        self.vkr_metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация контекста в словарь."""
        duration = None
        if self.completed_at and self.started_at:
            duration = (self.completed_at - self.started_at).total_seconds()
        
        return {
            "doc_type": self.doc_type,
            "standards": self.standards,
            "organization": self.organization,
            "regulatory_regime": self.regulatory_regime.value if self.regulatory_regime else None,
            "regulatory_profile_name": self.regulatory_profile.name if self.regulatory_profile else None,
            "requirements_count": len(self.requirements),
            "sections_generated": len(self.generated_content),
            "compliance_score": self.compliance_report.get("score") if self.compliance_report else None,
            "errors": self.errors,
            "duration": duration,
            "doc_id": self.doc_id,
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like доступ к атрибутам для совместимости."""
        return getattr(self, key, default)


class DocumentOrchestrator:
    """
    Оркестратор генерации документов с поддержкой отраслевой адаптации.
    
    Управляет полным циклом создания документа:
    1. Классификация организации и фильтрация стандартов
    2. Проектирование структуры (Architect)
    3. Параллельная генерация разделов (Writer + Critic)
    4. Финальная проверка (Auditor)
    5. Экспорт в PDF (DocumentGenerator)
    """
    
    # === Порядок разделов ВКР для сортировки ===
    VKR_SECTION_ORDER = [
        "введен",           # Введение
        "1", "1.1", "1.2", "1.3", "1.4", "1.5",
        "вывод по главе 1",
        "2", "2.1", "2.2", "2.3", "2.4", "2.5",
        "вывод по главе 2",
        "3", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9",
        "вывод по главе 3",
        "4", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6",
        "вывод по главе 4",
        "5", "5.1", "5.2", "5.3",
        "вывод по главе 5",
        "6", "6.1", "6.2", "6.3", "6.4",
        "вывод по главе 6",
        "заключ",           # Заключение
        "источник",         # Используемые источники (после заключения!)
        "приложен",         # Приложения
    ]
    
    # Пороги качества для адаптивной оценки
    SCORE_EXCELLENT: float = 0.80
    SCORE_ACCEPTABLE: float = 0.65
    MAX_RETRIES: int = 2
    MAX_CONCURRENT_SECTIONS: int = 1  # Ограничение параллелизма для стабильности
    
    # Ключевые слова для идентификации технических разделов
    TECHNICAL_SECTIONS: set = {
        "норматив", "термин", "определ", "аббревиатур", "ссылк", 
        "сокращен", "обозначен", "приложен"
    }
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None, **kwargs: Any):
        """
        Инициализация оркестратора.
        
        Args:
            llm_config: Конфигурация LLM-клиентов и моделей
            **kwargs: Дополнительные параметры (institution, faculty, etc. для ВКР)
        """
        self.llm_config: Dict[str, Any] = llm_config or {}
        
        # === Метаданные для ВКР (опциональные) ===
        self.institution: str = kwargs.get("institution", "СибАДИ")
        self.faculty: str = kwargs.get("faculty", "")
        self.department: str = kwargs.get("department", "")
        self.specialty: str = kwargs.get("specialty", "")
        self.degree: str = kwargs.get("degree", "")
        self.year: int = kwargs.get("year", datetime.now().year)
        self.bibliography_file: str = kwargs.get("bibliography_file", "references.bib")
        self.supervisor: str = kwargs.get("supervisor", "")
        # === Инициализация сканера кодовой базы ===
        project_root = kwargs.get("project_root", ".")
        self.codebase_scanner = CodebaseScanner(project_root=project_root)
        self.vkr_code_context_cached: Optional[Dict] = None
        # === Конец метаданных ВКР ===
        
        # Инициализация клиентов и сервисов
        self.ollama_client = OllamaClient(
            base_url=self.llm_config.get("base_url", "http://localhost:11434"),
            timeout=600.0,
            use_openai_compat=self.llm_config.get("use_openai_compat", True)
        )
        
        self.regulatory_classifier = RegulatoryClassifier()
        
        # Инициализация агентов с конфигурацией моделей
        self.architect = ArchitectAgent(
            model=self.llm_config.get("architect_model", "gemma4"),
            timeout=90,
            project_root=project_root
        )
        
        self.critic = CriticAgent(
            model=self.llm_config.get("critic_model", "qwen2.5:7b-instruct"),
            timeout=120,
            min_score=self.llm_config.get("critic_min_score", self.SCORE_EXCELLENT)
        )
        
        self.auditor = AuditorAgent(
            model=self.llm_config.get("auditor_model", "qwen2.5:7b-instruct"),
            timeout=120
        )
        
        self.doc_generator = DocumentGenerator(
            output_dir=self.llm_config.get("output_dir", "storage/generated"),
            template_dir=self.llm_config.get("template_dir", "storage/templates")
        )
        
        self.writer: Optional[BaseWriter] = None
        self.doc_type: Optional[str] = None
        
        self.logger = logging.getLogger("orchestrator")
    
    def _create_writer(self) -> BaseWriter:
        """Создание экземпляра Writer для текущего типа документа."""
        model_config: Dict[str, str] = {
            "policy": self.llm_config.get("policy_model", "gemma4"),
            "instruction": self.llm_config.get("instruction_model", "gemma4"),
            "regulation": self.llm_config.get("regulation_model", "gemma4"),
            "threat_model": self.llm_config.get("threat_model_model", "gemma4"),
            "risk_assessment": self.llm_config.get("risk_model", "gemma4"),
            "incident_response": self.llm_config.get("incident_model", "gemma4"),
            "access_control": self.llm_config.get("access_model", "gemma4"),
            "vkr_report": self.llm_config.get("vkr_model", "gemma4"),
        }
        
        model: str = model_config.get(self.doc_type or "policy", "gemma4")
        temperature: float = self.llm_config.get("writer_temperature", 0.2)
        
        self.writer = create_writer(
            self.doc_type or "policy", 
            model=model, 
            temperature=temperature, 
            request_type="writer"
        )
        self.logger.info(f"✓ Writer создан: {self.writer.name} (модель: {model})")
        
        return self.writer

    def _is_technical_section(self, title: str) -> bool:
        """Определяет, является ли раздел техническим (допускает более мягкую оценку)."""
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in self.TECHNICAL_SECTIONS)
    
    def _get_effective_threshold(self, section_title: str, attempt: int, is_light: bool = False) -> float:
        """
        Расчёт адаптивного порога качества с учётом типа раздела и попытки.
        
        Для технических разделов и повторных попыток порог снижается.
        """
        base = self.SCORE_EXCELLENT
        if is_light:
            base = max(0.70, base - 0.10)  # Снижение для технических разделов
        if attempt >= 1:
            return max(self.SCORE_ACCEPTABLE, base - 0.05)  # Снижение после первой попытки
        return base
    
    def _sort_vkr_hierarchy(self, hierarchy: List[Dict]) -> List[Dict]:
        """
        Сортирует иерархию разделов ВКР согласно академическому порядку.
        
        :param hierarchy: Список узлов иерархии от ArchitectAgent
        :return: Отсортированный список узлов
        """
        def sort_key(item: Dict) -> int:
            """Ключ сортировки: ищет совпадение с ключевыми словами порядка."""
            title = item.get("title", "").lower()
            number = item.get("number", "").lower()
            combined = f"{number} {title}"
            
            for i, keyword in enumerate(self.VKR_SECTION_ORDER):
                if keyword in combined:
                    return i
            return 999  # Неизвестные разделы — в конец
        
        sorted_hierarchy = sorted(hierarchy, key=sort_key)
        logger.info(f"✓ Иерархия ВКР отсортирована: {[h['title'] for h in sorted_hierarchy[:5]]}...")
        return sorted_hierarchy
    
    def _quick_heuristic_check(self, text: str, title: str) -> bool:
        """
        Быстрая эвристическая проверка для технических разделов.
        
        Возвращает True, если текст проходит базовые критерии качества.
        """
        if len(text.strip()) < 150:
            return False
        
        # Проверка на наличие нормативных маркеров
        markers = ["должно", "требуется", "обязуется", "необходимо", "в соответствии", "согласно"]
        if not any(m in text.lower() for m in markers):
            return False
        
        # Проверка на отсутствие явных ошибок
        error_patterns = ["ошибка", "не удалось", "невозможно", "проблема"]
        if any(p in text.lower() for p in error_patterns):
            return False
        
        return True

    async def generate_document(
        self,
        doc_type: str,
        standards: List[str],
        title: str,
        organization: str,
        object_type: str = "Информационная система",
        data_category: str = "Конфиденциальная информация",
        city: str = "г. Омск",
        # === Опциональные параметры для ВКР ===
        specialty: Optional[str] = None,
        faculty: Optional[str] = None,
        degree: Optional[str] = None,
        reviewer: Optional[str] = None,
        year: Optional[int] = None,
        bibliography_file: Optional[str] = None,
        supervisor: Optional[str] = None,
        # === Конец параметров ВКР ===
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Основной метод генерации документа с отраслевой адаптацией.
        
        Args:
            doc_type: Тип документа (policy, instruction, vkr_report, etc.)
            standards: Список нормативных стандартов
            title: Заголовок документа
            organization: Наименование организации
            object_type: Тип объекта защиты
            data_category: Категория обрабатываемых данных
            city: Город для оформления документа
            **kwargs: Дополнительные параметры (включая метаданные ВКР)
            callback: Callback-функция для отслеживания прогресса
            
        Returns:
            Dict с результатом генерации (success, file_path, context, etc.)
        """
        self.doc_type = doc_type
        
        # === Этап 0: Классификация организации ===
        regulatory_regime, regulatory_profile = self.regulatory_classifier.classify(organization)
        
        self.logger.info(f"ОТРАСЛЕВОЙ ПРОФИЛЬ: {regulatory_profile.name} ({regulatory_regime.value})")
        self.logger.info(f"   Обязательные стандарты: {regulatory_profile.mandatory_standards}")
        self.logger.info(f"   Ключевые термины: {regulatory_profile.key_terms[:5]}")
        
        # === Фильтрация стандартов через RAG ===
        rag = RAGService()
        applicable_standards = rag.get_applicable_standards(
            organization_type=organization,
            doc_type=doc_type,
            requested_standards=standards,
            regulatory_profile=regulatory_profile
        )
        
        filtered_standards = [s for s in standards if s in applicable_standards]
        if len(filtered_standards) != len(standards):
            removed = set(standards) - set(filtered_standards)
            self.logger.warning(f"⚠ Исключены неприменимые стандарты: {removed}")
        
        # === Получение шаблона структуры ===
        structure_template = rag.get_structure_template(
            doc_type=doc_type,
            organization_type=organization,
            use_examples=True,
            regulatory_profile=regulatory_profile
        )

        # === Инициализация контекста ===
        context = GenerationContext(
            doc_type=doc_type,
            standards=filtered_standards,
            title=title,
            organization=organization,
            object_type=object_type,
            data_category=data_category,
            city=city
        )
        context.regulatory_regime = regulatory_regime
        context.regulatory_profile = regulatory_profile
        context.started_at = datetime.now()
        
        try:
            # === Этап 1: Architect (проектирование структуры) ===
            if callback:
                callback({"stage": "architector", "progress": 10})
            
            self.logger.info("Этап 1: Архитектор проектирует структуру")
            arch_input = AgentInput(
                task=f"Спроектируй структуру {doc_type}",
                context={
                    "doc_type": doc_type,
                    "standards": standards,
                    "organization": organization,
                    "object_type": object_type,
                    "city": city,
                    "regulatory_profile": regulatory_profile,
                    "regulatory_regime": regulatory_regime.value,
                }
            )
            arch_output = await self.architect.execute(arch_input)
            
            if not arch_output.success:
                context.errors.append(f"Ошибка архитектора: {arch_output.error}")
                return {"success": False, "error": arch_output.error, "context": context.to_dict()}
            
            context.structure_plan = arch_output.data
            hierarchy: List[Dict[str, Any]] = arch_output.data.get("hierarchy", [])
            
            # === Сортировка иерархии для ВКР перед генерацией ===
            if doc_type == "vkr_report":
                hierarchy = self._sort_vkr_hierarchy(hierarchy)
                logger.info(f"✓ Иерархия ВКР отсортирована: {len(hierarchy)} разделов")
            
            self.logger.info(f"   ✓ Спроектировано {len(hierarchy)} разделов")
            
            # === Специальная обработка для ВКР: метаданные ===
            if doc_type == "vkr_report":
                context.vkr_metadata = {
                    "title": title,
                    "author": organization,
                    "institution": self.institution,
                    "faculty": self.faculty or faculty or "",
                    "department": self.department or "",
                    "specialty": self.specialty or specialty or "",
                    "degree": self.degree or degree or "",
                    "city": city,
                    "year": self.year or year or datetime.now().year,
                    "bibliography_file": self.bibliography_file or bibliography_file or "references.bib",
                    "supervisor": self.supervisor or supervisor or reviewer or "",
                }

            # === Этап 2: Создание Writer ===
            writer = self._create_writer()
            
            # === Этап 3: Параллельная генерация контента ===
            if callback:
                callback({"stage": "generating", "progress": 30})
            
            self.logger.info("Этап 2: Генерация контента (Writer + Critic) [параллельно]")
            
            context.generated_content = await self._generate_sections_parallel(
                writer=writer,
                hierarchy=hierarchy,
                standards=standards,
                organization=organization,
                regulatory_profile=regulatory_profile,
                max_concurrent=self.MAX_CONCURRENT_SECTIONS,
                callback=callback,
                total_sections=len(hierarchy)
            )
            
            if not context.generated_content:
                context.errors.append("Не сгенерировано ни одного раздела")
                return {"success": False, "error": "Пустой документ", "context": context.to_dict()}
            
            # === Этап 4: Auditor (проверка структуры) ===
            if callback:
                callback({"stage": "auditing", "progress": 80})
            
            self.logger.info("Этап 3: Проверка структуры (Auditor)")
            aud_input = AgentInput(
                task="Проверь структуру документа",
                context={
                    "sections": context.generated_content,
                    "hierarchy": hierarchy,
                    "standards": standards,
                    "doc_type": doc_type,
                    "regulatory_profile": regulatory_profile,
                }
            )
            aud_output = await self.auditor.execute(aud_input)
            
            if aud_output.success:
                context.compliance_report = aud_output.data
                score = aud_output.data.get("score", 0)
                self.logger.info(f"   ✓ Оценка соответствия: {score:.2f}")
            else:
                self.logger.warning(f"   ⚠ Предупреждение аудитора: {aud_output.error}")
            
            # === Этап 5: Генерация PDF ===
            if callback:
                callback({"stage": "creating_pdf", "progress": 90})
            
            self.logger.info("Этап 4: Генерация PDF (Markdown → LaTeX → PDF)")
            
            # Проверка зависимостей
            deps = self.doc_generator.check_dependencies()
            if not deps.get("pandoc"):
                self.logger.warning("⚠ Pandoc не найден — будет сохранён Markdown")
                context.errors.append("Pandoc не установлен: PDF не сгенерирован")
            
            # Подготовка метаданных
            doc_metadata: Dict[str, Any] = {
                "doc_id": context.doc_id,
                "doc_type": doc_type,
                "organization": organization,
                "title": title,
                "object_type": object_type,
                "data_category": data_category,
                "city": city,
                "standards": standards,
                "regulatory_profile": regulatory_profile,
            }
            if context.vkr_metadata:
                doc_metadata.update(context.vkr_metadata)
            
            pdf_path = self.doc_generator.generate_pdf(
                markdown_content=context.generated_content,
                context=doc_metadata
            )
            
            context.completed_at = datetime.now()
            duration = context.to_dict().get("duration", 0)
            
            result = {
                "success": True,
                "document_id": context.doc_id,
                "file_path": pdf_path,
                "download_url": f"/api/documents/{context.doc_id}/download",
                "context": context.to_dict(),
                "compliance": context.compliance_report,
                "industry_info": {
                    "regime": regulatory_regime.value,
                    "profile_name": regulatory_profile.name,
                    "key_terms": regulatory_profile.key_terms,
                    "applicable_standards": filtered_standards,
                },
                "duration_sec": duration,
            }
            
            self.logger.info(f"✓ Документ сгенерирован: {pdf_path} (время: {duration:.1f} сек)")
            return result
            
        except Exception as e:
            context.errors.append(f"Критическая ошибка: {str(e)}")
            self.logger.error(f"✗ Ошибка генерации: {e}", exc_info=True)
            
            return {
                "success": False,
                "error": str(e),
                "context": context.to_dict(),
                "traceback": logging.getLogger().handlers[0].formatter if logging.getLogger().handlers else None
            }
    
    async def _generate_sections_parallel(
        self,
        writer: BaseWriter,
        hierarchy: List[Dict[str, Any]],
        standards: List[str],
        organization: str,
        regulatory_profile: Optional[RegulatoryProfile] = None,
        max_concurrent: int = 4,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        total_sections: Optional[int] = None
    ) -> Dict[str, str]:
        """
        Параллельная генерация разделов с ограничением конкуренции.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results: Dict[str, str] = {}
        
        self.logger.info(f"Генерация {len(hierarchy)} разделов с единым порогом качества")

        async def generate_with_semaphore(node: Dict[str, Any], index: int, is_light: bool = False):
            async with semaphore:
                section_title = node.get("title", "Unknown")
                
                if callback and total_sections:
                    progress = 30 + (40 * index / total_sections)
                    callback({
                        "stage": "generating_section",
                        "progress": progress,
                        "section": section_title,
                        "index": index + 1,
                        "total": total_sections,
                        "weight": "light" if is_light else "heavy"
                    })
                
                profile_name = regulatory_profile.name if regulatory_profile else "универсальная"
                self.logger.info(f"   → [{index+1}/{total_sections}] {section_title} ({profile_name})")

                max_retries = 1 if is_light else self.MAX_RETRIES

                content = await self._generate_section_with_refinement(
                    writer=writer,
                    node=node,
                    standards=standards,
                    organization=organization,
                    regulatory_profile=regulatory_profile,
                    max_retries=self.MAX_RETRIES,  # Всегда 2 попытки
                    is_light_section=False,  # ← Всегда полная проверка
                    doc_type=self.doc_type
                )
                
                if content:
                    results[section_title] = content
                    word_count = len(content.split())
                    self.logger.info(f"      ✓ {section_title} завершён ({word_count} слов)")
                else:
                    self.logger.warning(f"      ✗ {section_title} не сгенерирован")
                
                return section_title, content
        
        # Запуск всех задач параллельно
        tasks = [
            generate_with_semaphore(node, i)
            for i, node in enumerate(hierarchy)
        ]
        
        # Выполнение с обработкой исключений
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        # Логирование ошибок без прерывания
        for i, result in enumerate(gathered):
            if isinstance(result, Exception):
                title = hierarchy[i].get("title", f"section_{i}")
                self.logger.error(f"✗ Ошибка в разделе '{title}': {result}")
        
        return results
    
    async def _generate_section_with_refinement(
        self,
        writer: BaseWriter,
        node: Dict[str, Any],
        standards: List[str],
        organization: str,
        regulatory_profile: Optional[RegulatoryProfile] = None,
        max_retries: int = 2,
        is_light_section: bool = False,
        doc_type: str = "policy"
    ) -> Optional[str]:
        """
        Генерация раздела с адаптивной логикой повторных попыток.
        
        Для технических разделов применяется упрощённая проверка.
        """
        section_title = node.get("title", "")
        section_text = ""
        
        for attempt in range(max_retries + 1):
            context: Dict[str, Any] = {
                "section_plan": node,
                "standards": standards,
                "organization": organization,
                "section_number": node.get("number", "1"),
                "section_title": section_title,
                "references": node.get("required_standards", []),
                "attempt": attempt,
                "regulatory_profile": regulatory_profile,
                "code_context": "",
            }
            
            if doc_type == "vkr_report" and hasattr(self, 'codebase_scanner'):
                context["code_context"] = self.codebase_scanner.generate_section_context(
                    section_title=section_title,
                    section_number=node.get("number", "1")
                )

            writer_input = AgentInput(
                task=f"Напиши раздел: {section_title}",
                context=context
            )
            
            writer_output = await writer.execute(writer_input)
            if not writer_output.success:
                self.logger.warning(f"⚠ Ошибка писателя: {writer_output.error}")
                break
            
            section_text = writer_output.content
            
            # === Быстрая проверка для лёгких разделов ===
            if is_light_section and attempt == 0:
                if self._quick_heuristic_check(section_text, section_title):
                    word_count = len(section_text.split())
                    self.logger.info(f"   ✓ {section_title} (эвристика, {word_count} слов)")
                    return section_text

            # === Проверка через Critic ===
            critic_input = AgentInput(
                task="Проверь качество текста",
                context={
                    "text": section_text,
                    "section_title": section_title,
                    "standards": standards,
                    "regulatory_profile": regulatory_profile,
                    "min_words": 800,
                    "is_technical": False,
                }
            )
            
            critic_output = await self.critic.execute(critic_input)
            
            if critic_output.success:
                report = critic_output.data
                score = report.get("score", 0)
                threshold = self.SCORE_EXCELLENT
                
                # === Адаптивная логика принятия решения ===
                if score >= self.SCORE_EXCELLENT:
                    self.logger.info(f"   ✓ {section_title} ({score:.2f} ≥ {self.SCORE_EXCELLENT})")
                    return section_text
                elif score >= self.SCORE_ACCEPTABLE and attempt >= 1:
                    self.logger.info(f"   ✓ {section_title} (принято после доработки, {score:.2f})")
                    return section_text
                elif attempt >= max_retries:
                    self.logger.warning(f"   ⚠ {section_title} (принято после исчерпания попыток, {score:.2f})")
                    return section_text
                else:
                    feedback = report.get("feedback", "Улучши текст")[:100]
                    self.logger.info(f"   ↻ {section_title} ({score:.2f} < {threshold}): {feedback}...")
            else:
                if attempt >= 1:
                    return section_text
                break
        
        return section_text if section_text.strip() else None
    
    async def generate_batch(
        self,
        documents: List[Dict[str, Any]],
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Пакетная генерация нескольких документов.
        
        Args:
            documents: Список параметров для генерации
            callback: Callback для отслеживания прогресса
            
        Returns:
            Список результатов генерации
        """
        results: List[Dict[str, Any]] = []
        
        for i, doc_params in enumerate(documents):
            if callback:
                callback({
                    "stage": "batch_progress",
                    "progress": (i / len(documents)) * 100,
                    "current": i + 1,
                    "total": len(documents)
                })
            
            self.logger.info(f"Документ {i+1}/{len(documents)}: {doc_params.get('title', 'N/A')}")
            
            result = await self.generate_document(
                **doc_params,
                callback=callback
            )
            results.append(result)
            
            if not result.get("success"):
                self.logger.warning(f"⚠ Не удалось сгенерировать: {result.get('error')}")
        
        return results