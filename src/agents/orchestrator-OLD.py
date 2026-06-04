# src/agents/orchestrator.py
"""
Оркестратор генерации документов: управление потоком выполнения агентов
с поддержкой отраслевой адаптации через RegulatoryClassifier
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable, Awaitable
from datetime import datetime
from pathlib import Path

from src.agents.base import AgentInput, AgentOutput
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

logger = logging.getLogger(__name__)


class GenerationContext:
    """Контекст генерации документа с поддержкой отраслевого профиля"""
    
    def __init__(self, doc_type: str, standards: List[str], **kwargs):
        self.doc_type = doc_type
        self.standards = standards
        self.organization = kwargs.get("organization", "Организация")
        self.object_type = kwargs.get("object_type", "Информационная система")
        self.data_category = kwargs.get("data_category", "Конфиденциальная информация")
        self.title = kwargs.get("title", "Документ")
        self.city = kwargs.get("city", "г. Омск")
        
        self.regulatory_regime: Optional[RegulatoryRegime] = None
        self.regulatory_profile: Optional[RegulatoryProfile] = None
        
        self.requirements: List[Dict] = []
        self.structure_plan: Optional[Dict] = None
        self.generated_content: Dict[str, str] = {}
        self.compliance_report: Optional[Dict] = None
        
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.errors: List[str] = []
        self.doc_id: str = f"doc_{doc_type}_{int(datetime.now().timestamp())}"
    
    def to_dict(self) -> Dict[str, Any]:
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
            "duration": duration
        }


class DocumentOrchestrator:
    """Оркестратор генерации документов с поддержкой отраслевой адаптации"""
    
    # Пороги для адаптивной оценки
    SCORE_EXCELLENT = 0.8
    SCORE_ACCEPTABLE = 0.65
    MAX_RETRIES = 2
    MAX_CONCURRENT_SECTIONS = 1  # Параллельная генерация
    
    # Разделы, где допустимы более мягкие требования
    TECHNICAL_SECTIONS = {"норматив", "термин", "определ", "аббревиатур", "ссылк"}
    
    def __init__(self, llm_config: Optional[Dict] = None):
        self.llm_config = llm_config or {}
        
        self.ollama_client = OllamaClient(
            base_url=self.llm_config.get("base_url", "http://localhost:11434"),
            timeout=600.0,
            use_openai_compat=self.llm_config.get("use_openai_compat", True)
        )
        
        self.regulatory_classifier = RegulatoryClassifier()
        
        self.architector = ArchitectAgent(
            model=self.llm_config.get("architect_model", "gemma4"),
            timeout=90
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
        self.doc_type = None
        
        self.logger = logging.getLogger("orchestrator")
    
    def _create_writer(self) -> BaseWriter:
        model_config = {
            "policy": self.llm_config.get("policy_model", "gemma4"),
            "instruction": self.llm_config.get("instruction_model", "gemma4"),
            "regulation": self.llm_config.get("regulation_model", "gemma4"),
            "threat_model": self.llm_config.get("threat_model_model", "gemma4"),
            "risk_assessment": self.llm_config.get("risk_model", "gemma4"),
            "incident_response": self.llm_config.get("incident_model", "gemma4"),
            "access_control": self.llm_config.get("access_model", "gemma4"),
        }
        
        model = model_config.get(self.doc_type, "gemma4")
        temperature = self.llm_config.get("writer_temperature", 0.2)
        
        self.writer = create_writer(self.doc_type, model=model, temperature=temperature, request_type="writer")
        self.logger.info(f"Создан писатель: {self.writer.name} (модель: {model})")
        
        return self.writer

    def _create_critic(self) -> CriticAgent:
        """Создаёт критика с быстрым таймаутом и меньшей моделью"""
        from src.agents.critic import CriticAgent
        return CriticAgent(
            model=self.llm_config.get("critic_model", "qwen2.5:7b-instruct"),  # ← Меньшая модель
            timeout=90,  # ← 90 сек вместо 120
            min_score=self.llm_config.get("critic_min_score", self.SCORE_EXCELLENT),
            request_type="critic"  # ← Для адаптивного таймаута
        )

    def _is_technical_section(self, title: str) -> bool:
        """Определяет, является ли раздел техническим (допускает более мягкую оценку)"""
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in self.TECHNICAL_SECTIONS)
    
    def _get_effective_threshold(self, section_title: str, attempt: int, is_light: bool = False) -> float:
        """Адаптивный порог с учётом типа раздела"""
        base = self.SCORE_EXCELLENT
        if is_light:
            base = max(0.70, base - 0.10)  # ↓ для технических разделов
        if attempt >= 1:
            return max(self.SCORE_ACCEPTABLE, base - 0.05)
        return base
    
    def _quick_heuristic_check(self, text: str, title: str) -> bool:
        """Быстрая эвристическая проверка для технических разделов"""
        if len(text.strip()) < 150:
            return False
        # Проверка на наличие ключевых маркеров
        markers = ["должно", "требуется", "обязуется", "необходимо", "в соответствии"]
        if not any(m in text.lower() for m in markers):
            return False
        # Проверка на отсутствие явных ошибок
        if "ошибка" in text.lower() or "не удалось" in text.lower():
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
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Основной метод генерации документа с отраслевой адаптацией.
        """
        self.doc_type = doc_type
        
        regulatory_regime, regulatory_profile = self.regulatory_classifier.classify(organization)
        
        self.logger.info(f"   ОТРАСЛЕВОЙ ПРОФИЛЬ: {regulatory_profile.name} ({regulatory_regime.value})")
        self.logger.info(f"   Обязательные стандарты: {regulatory_profile.mandatory_standards}")
        self.logger.info(f"   Ключевые термины: {regulatory_profile.key_terms[:5]}")
        
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
            self.logger.warning(f"Исключены неприменимые стандарты: {removed}")
        
        # Получение структуры с учётом профиля
        structure_template = rag.get_structure_template(
            doc_type=doc_type,
            organization_type=organization,
            use_examples=True,
            regulatory_profile=regulatory_profile
        )

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
            # Этап 1: Архитектор
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
            arch_output = await self.architector.execute(arch_input)
            
            if not arch_output.success:
                context.errors.append(f"Ошибка архитектора: {arch_output.error}")
                return {"success": False, "error": arch_output.error}
            
            context.structure_plan = arch_output.data
            hierarchy = arch_output.data.get("hierarchy", [])
            self.logger.info(f"   Спроектировано {len(hierarchy)} разделов")
            
            # Этап 2: Создание писателя
            writer = self._create_writer()
            
            # Этап 3: Генерация контента (ПАРАЛЛЕЛЬНО)
            if callback:
                callback({"stage": "generating", "progress": 30})
            
            self.logger.info("Этап 2: Генерация контента (Writer + Critic) [параллельно]")
            
            # Параллельная генерация с ограничением конкуренции
            context.generated_content = await self._generate_sections_parallel(
                writer=writer,
                hierarchy=hierarchy,
                standards=standards,
                organization=organization,
                regulatory_profile=regulatory_profile,  # ← Передаём профиль
                max_concurrent=self.MAX_CONCURRENT_SECTIONS,
                callback=callback,
                total_sections=len(hierarchy)
            )
            
            # Проверка: не пустой ли документ
            if not context.generated_content:
                context.errors.append("Не сгенерировано ни одного раздела")
                return {"success": False, "error": "Пустой документ"}
            
            # Этап 4: Auditor
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
                self.logger.info(f"   Оценка соответствия: {aud_output.data.get('score', 0):.2f}")
            
            self.logger.info("Этап 4: Проверка соответствия")
            
            # Этап 5: Генерация PDF
            if callback:
                callback({"stage": "creating_pdf", "progress": 90})
            
            self.logger.info("Этап 5: Генерация PDF (Markdown → LaTeX → PDF)")
            
            # Проверка зависимостей перед генерацией
            deps = self.doc_generator.check_dependencies()
            if not deps.get("pandoc"):
                self.logger.warning("Pandoc не найден — будет сохранён Markdown")
                context.errors.append("Pandoc не установлен: PDF не сгенерирован")
            
            pdf_path = self.doc_generator.generate_pdf(
                markdown_content=context.generated_content,
                context={
                    "doc_id": context.doc_id,
                    "doc_type": doc_type,
                    "organization": organization,
                    "title": title,
                    "object_type": object_type,
                    "data_category": data_category,
                    "city": city,
                    "standards": standards,
                    "regulatory_profile": regulatory_profile,  # ← Передаём профиль
                }
            )
            
            context.completed_at = datetime.now()
            
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
                }
            }
            
            self.logger.info(f"✓ Документ сгенерирован: {pdf_path} (время: {context.to_dict()['duration']:.1f} сек)")
            return result
            
        except Exception as e:
            context.errors.append(f"Критическая ошибка: {str(e)}")
            self.logger.error(f"Ошибка генерации: {e}", exc_info=True)
            
            return {
                "success": False,
                "error": str(e),
                "context": context.to_dict()
            }
    
    async def _generate_sections_parallel(
        self,
        writer: BaseWriter,
        hierarchy: List[Dict],
        standards: List[str],
        organization: str,
        regulatory_profile: Optional[RegulatoryProfile] = None,
        max_concurrent: int = 4,
        callback: Optional[Callable] = None,
        total_sections: int = None
    ) -> Dict[str, str]:
        """Параллельная генерация разделов с ограничением конкуренции"""
        semaphore = asyncio.Semaphore(max_concurrent)
        results = {}
        
        light_sections = [n for n in hierarchy if self._is_technical_section(n.get("title", ""))]
        heavy_sections = [n for n in hierarchy if n not in light_sections]

        async def generate_with_semaphore(node: Dict, index: int, is_light: bool = False):
            async with semaphore:
                if callback and total_sections:
                    progress = 30 + (40 * index / total_sections)
                    callback({
                        "stage": "generating_section",
                        "progress": progress,
                        "section": node["title"],
                        "index": index + 1,
                        "total": total_sections,
                        "weight": "light" if is_light else "heavy"
                    })
                
                profile_name = regulatory_profile.name if regulatory_profile else "универсальная"
                self.logger.info(f"→ [{index+1}/{total_sections}] {node['title']} ({profile_name})")

                max_retries = 1 if is_light else self.MAX_RETRIES

                content = await self._generate_section_with_refinement(
                    writer=writer,
                    node=node,
                    standards=standards,
                    organization=organization,
                    regulatory_profile=regulatory_profile,
                    max_retries=max_retries,
                    is_light_section=is_light
                )
                
                if content:
                    results[node["title"]] = content
                    self.logger.info(f"   ✓ Раздел {node['title']} завершён")
                else:
                    self.logger.warning(f"   ✗ Раздел {node['title']} не сгенерирован")
                
                return node["title"], content
        
        # Запускаем все задачи параллельно
        tasks = []
        for i, node in enumerate(hierarchy):
            is_light = self._is_technical_section(node.get("title", ""))
            tasks.append(generate_with_semaphore(node, i, is_light))
        
        # Выполняем с обработкой таймаутов на уровне задач
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        # Логируем исключения, но не прерываем весь процесс
        for i, result in enumerate(gathered):
            if isinstance(result, Exception):
                title = hierarchy[i].get("title", f"section_{i}")
                self.logger.error(f"Ошибка в разделе '{title}': {result}")
        
        return results
    
    async def _generate_section_with_refinement(
        self,
        writer: BaseWriter,
        node: Dict[str, Any],
        standards: List[str],
        organization: str,
        regulatory_profile: Optional[RegulatoryProfile] = None,
        max_retries: int = 2,
        is_light_section: bool = False
    ) -> Optional[str]:
        """Генерация раздела с адаптивной логикой повторных попыток"""
        section_title = node.get("title", "")
        section_text = ""
        
        for attempt in range(max_retries + 1):
            # Для лёгких разделов — сокращённый контекст
            context = {
                "section_plan": node,
                "standards": standards,
                "organization": organization,
                "section_number": node.get("number", "1"),
                "section_title": section_title,
                "references": node.get("required_standards", []),
                "attempt": attempt,
                "regulatory_profile": regulatory_profile,
            }
            if is_light_section:
                context["mode"] = "concise"  # Подсказка для писателя

            writer_input = AgentInput(
                task=f"Напиши раздел: {section_title}",
                context=context
            )
            
            writer_output = await writer.execute(writer_input)
            if not writer_output.success:
                self.logger.warning(f"Ошибка писателя: {writer_output.error}")
                break
            
            if not writer_output.success:
                self.logger.warning(f"   Ошибка писателя: {writer_output.error}")
                break
            
            section_text = writer_output.content
            
            # Для лёгких разделов — быстрая эвристическая проверка вместо LLM-критика
            if is_light_section and attempt == 0:
                if self._quick_heuristic_check(section_text, section_title):
                    self.logger.info(f"   ✓ {section_title} (эвристика, {writer_output.word_count} слов)")
                    return section_text

            critic_input = AgentInput(
                task="Проверь качество текста",
                context={
                    "text": section_text,
                    "section_title": section_title,
                    "standards": standards,
                    "regulatory_profile": regulatory_profile,
                    "min_words": 200 if is_light_section else 250,  # ↓ для лёгких
                    "is_technical": self._is_technical_section(section_title)
                }
            )
            
            critic_output = await self.critic.execute(critic_input)
            
            if critic_output.success:
                report = critic_output.data
                score = report.get("score", 0)
                threshold = self._get_effective_threshold(section_title, attempt)
                
                # Адаптивная логика принятия
                if score >= self.SCORE_EXCELLENT:
                    self.logger.info(f"   ✓ {section_title} ({score:.2f} ≥ {self.SCORE_EXCELLENT})")
                    return section_text
                elif score >= threshold and attempt >= 1:
                    self.logger.info(f"   ✓ {section_title} (принято после доработки, {score:.2f})")
                    return section_text
                elif attempt >= max_retries:
                    self.logger.warning(f"   ⚠ {section_title} (принято после исчерпания попыток)")
                    return section_text
                else:
                    feedback = report.get("feedback", "Улучши текст")
                    # Для лёгких разделов — не дорабатываем, если близко к порогу
                    if is_light_section and score >= threshold - 0.1:
                        self.logger.info(f"   ✓ {section_title} (достаточно для технического раздела)")
                        return section_text
                    self.logger.info(f"   ↻ {section_title} ({score:.2f} < {threshold}): {feedback[:100]}...")
            else:
                if attempt >= 1 or is_light_section:
                    return section_text
                break
        
        return section_text if section_text.strip() else None