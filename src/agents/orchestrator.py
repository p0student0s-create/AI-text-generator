# src/agents/orchestrator.py
"""
Оркестратор генерации документов с поддержкой streaming
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
        self.doc_id = f"doc_{doc_type}_{int(datetime.now().timestamp())}"

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
    SCORE_EXCELLENT = 0.8
    SCORE_ACCEPTABLE = 0.65
    MAX_RETRIES = 2
    MAX_CONCURRENT_SECTIONS = 1

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
        self._stream_callback: Optional[Callable] = None
        self._generation_id: Optional[str] = None
        self._additional_prompts: List[str] = []

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
        self.writer.stream_callback = self._stream_callback  # Передаём callback в writer
        self.logger.info(f"Создан писатель: {self.writer.name} (модель: {model})")
        return self.writer

    async def _emit(self, event: Dict[str, Any]):
        """Отправка события через callback"""
        if self._stream_callback:
            await self._stream_callback(event)

    async def generate_document_stream(
        self,
        doc_type: str,
        standards: List[str],
        title: str,
        organization: str,
        object_type: str = "Информационная система",
        data_category: str = "Конфиденциальная информация",
        city: str = "г. Омск",
        generation_id: str = "",
        callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Генерация документа с streaming событиями.
        """
        self._stream_callback = callback
        self._generation_id = generation_id
        self.doc_type = doc_type
        
        await self._emit({"type": "status", "stage": "initializing", "message": "Инициализация генерации..."})
        
        # Классификация отрасли
        regulatory_regime, regulatory_profile = self.regulatory_classifier.classify(organization)
        await self._emit({
            "type": "industry_detected",
            "regime": regulatory_regime.value,
            "profile_name": regulatory_profile.name,
            "key_terms": regulatory_profile.key_terms[:5]
        })
        
        rag = RAGService()
        applicable_standards = rag.get_applicable_standards(
            organization_type=organization,
            doc_type=doc_type,
            requested_standards=standards,
            regulatory_profile=regulatory_profile
        )
        filtered_standards = [s for s in standards if s in applicable_standards]
        
        await self._emit({
            "type": "standards_filtered",
            "standards": filtered_standards,
            "removed": list(set(standards) - set(filtered_standards))
        })
        
        # Получение структуры
        await self._emit({"type": "status", "stage": "architecture", "message": "Проектирование структуры..."})
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
            await self._emit({"type": "status", "stage": "architector", "progress": 10, "message": "Архитектор проектирует структуру"})
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
                await self._emit({"type": "error", "error": arch_output.error})
                return {"success": False, "error": arch_output.error}
            
            context.structure_plan = arch_output.data
            hierarchy = arch_output.data.get("hierarchy", [])
            
            await self._emit({
                "type": "structure_ready",
                "sections_count": len(hierarchy),
                "hierarchy": hierarchy
            })
            
            # Этап 2: Создание писателя
            writer = self._create_writer()
            
            # Этап 3: Генерация контента с streaming
            await self._emit({"type": "status", "stage": "generating", "progress": 30, "message": "Начинаем генерацию контента"})
            
            context.generated_content = await self._generate_sections_streaming(
                writer=writer,
                hierarchy=hierarchy,
                standards=standards,
                organization=organization,
                regulatory_profile=regulatory_profile,
                total_sections=len(hierarchy)
            )
            
            if not context.generated_content:
                await self._emit({"type": "error", "error": "Не сгенерировано ни одного раздела"})
                return {"success": False, "error": "Пустой документ"}
            
            # Этап 4: Auditor
            await self._emit({"type": "status", "stage": "auditing", "progress": 80, "message": "Проверка структуры"})
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
                await self._emit({
                    "type": "audit_complete",
                    "score": aud_output.data.get("score", 0),
                    "compliant": aud_output.data.get("compliant", False)
                })
            
            # Этап 5: Генерация PDF
            await self._emit({"type": "status", "stage": "creating_pdf", "progress": 90, "message": "Генерация PDF"})
            deps = self.doc_generator.check_dependencies()
            if not deps.get("pandoc"):
                await self._emit({"type": "warning", "message": "Pandoc не установлен — будет сохранён Markdown"})
            
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
                    "regulatory_profile": regulatory_profile,
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
            }
            
            await self._emit({"type": "completed", "result": result})
            return result
            
        except Exception as e:
            await self._emit({"type": "error", "error": str(e)})
            return {"success": False, "error": str(e)}

    async def _generate_sections_streaming(
        self,
        writer: BaseWriter,
        hierarchy: List[Dict],
        standards: List[str],
        organization: str,
        regulatory_profile: Optional[RegulatoryProfile] = None,
        total_sections: int = 0
    ) -> Dict[str, str]:
        """Генерация разделов с streaming"""
        results = {}
        
        for i, node in enumerate(hierarchy):
            section_title = node.get("title", "")
            section_number = node.get("number", str(i + 1))
            
            await self._emit({
                "type": "section_start",
                "section_number": section_number,
                "section_title": section_title,
                "index": i + 1,
                "total": total_sections
            })
            
            # Проверяем дополнительные промпты
            additional_context = ""
            if self._additional_prompts:
                additional_context = self._additional_prompts.pop(0)
                await self._emit({
                    "type": "prompt_applied",
                    "section": section_title,
                    "prompt": additional_context
                })
            
            content = await self._generate_single_section_streaming(
                writer=writer,
                node=node,
                standards=standards,
                organization=organization,
                regulatory_profile=regulatory_profile,
                additional_context=additional_context
            )
            
            if content:
                results[section_title] = content
                await self._emit({
                    "type": "section_complete",
                    "section_number": section_number,
                    "section_title": section_title,
                    "word_count": len(content.split()),
                    "index": i + 1,
                    "total": total_sections
                })
            else:
                await self._emit({
                    "type": "section_error",
                    "section_title": section_title,
                    "error": "Не удалось сгенерировать раздел"
                })
        
        return results

    async def _generate_single_section_streaming(
        self,
        writer: BaseWriter,
        node: Dict[str, Any],
        standards: List[str],
        organization: str,
        regulatory_profile: Optional[RegulatoryProfile] = None,
        additional_context: str = ""
    ) -> Optional[str]:
        """Генерация одного раздела с streaming"""
        section_title = node.get("title", "")
        
        context = {
            "section_plan": node,
            "standards": standards,
            "organization": organization,
            "section_number": node.get("number", "1"),
            "section_title": section_title,
            "references": node.get("required_standards", []),
            "attempt": 0,
            "regulatory_profile": regulatory_profile,
            "additional_context": additional_context,
        }
        
        writer_input = AgentInput(
            task=f"Напиши раздел: {section_title}",
            context=context
        )
        
        writer_output = await writer.execute(writer_input)
        
        if not writer_output.success:
            return None
        
        return writer_output.content

    # Оставляем старый метод для совместимости
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
        """Старый метод — для совместимости"""
        return await self.generate_document_stream(
            doc_type=doc_type,
            standards=standards,
            title=title,
            organization=organization,
            object_type=object_type,
            data_category=data_category,
            city=city,
            callback=callback
        )