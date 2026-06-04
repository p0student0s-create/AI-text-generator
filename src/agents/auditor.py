# src/agents/auditor.py
import logging
import re
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from src.agents.base import BaseAgent, AgentInput, AgentOutput
from src.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

class AuditIssue(BaseModel):
    section: str
    type: str  # "missing", "wrong_order", "duplicate"
    description: str

class AuditorOutput(AgentOutput):
    compliant: bool = False
    issues: List[AuditIssue] = Field(default_factory=list)
    score: float = 0.0

class AuditorAgent(BaseAgent):
    name = "auditor"
    
    def __init__(self, model: str = "gemma4", timeout: float = 120.0):
        super().__init__()
        self.model = model
        self.timeout = timeout
        self.ollama_client = OllamaClient(
            base_url="http://localhost:11434",
            model=self.model,
            timeout=self.timeout
        )
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        generated_sections = input_data.context.get("sections", {})
        expected_hierarchy = input_data.context.get("hierarchy", [])
        standards = input_data.context.get("standards", [])
        
        issues = []
        expected_numbers = [n.get("number") for n in expected_hierarchy]
        actual_numbers = list(generated_sections.keys())
        
        # Проверка полноты
        missing = set(expected_numbers) - set(actual_numbers)
        if missing:
            issues.append(AuditIssue(section="document", type="missing", description=f"Отсутствуют разделы: {missing}"))
            
        # Проверка порядка
        if actual_numbers != expected_numbers:
            issues.append(AuditIssue(section="document", type="wrong_order", description="Нарушена последовательность разделов"))
            
        compliant = len(issues) == 0
        score = 1.0 if compliant else max(0.0, 1.0 - (len(issues) * 0.2))
        
        logger.info(f"Аудитор проверил документ: compliant={compliant}, issues={len(issues)}")
        return AuditorOutput(success=True, data={
            "compliant": compliant, 
            "issues": [i.model_dump() for i in issues], 
            "score": score
        })
    
    def _check_official_style(self, text: str) -> bool:
        """Проверяет наличие маркеров официально-делового стиля"""
        markers = [
            "Обязуется", "Необходимо", "Запрещается", "Должен", "Следует",
            "должно быть обеспечено", "должно осуществляться", "подлежит"
        ]
        return any(m in text for m in markers)

    # В методе execute() ЗАМЕНИТЬ блок проверки на:
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        generated_sections = input_data.context.get("sections", {})
        expected_hierarchy = input_data.context.get("hierarchy", [])
        standards = input_data.context.get("standards", [])
        organization = input_data.context.get("organization", "")  # ← НОВОЕ
        
        issues = []
        
        # 1. Проверка полноты (оставить как было)
        expected_numbers = [n.get("number") for n in expected_hierarchy]
        actual_numbers = list(generated_sections.keys())
        missing = set(expected_numbers) - set(actual_numbers)
        if missing:
            issues.append(AuditIssue(section="document", type="missing", 
                                description=f"Отсутствуют разделы: {missing}"))
        
        # 2. Проверка контента (НОВОЕ)
        for section_title, content in generated_sections.items():
            # ФСТЭК 239 — правильная дата
            if "ФСТЭК" in content and "№239" in content and "03.12.2019" in content:
                issues.append(AuditIssue(
                    section=section_title, type="wrong_reference",
                    description="Неправильная дата ФСТЭК №239 (должно быть 25.12.2017)"
                ))
            
            # ГОСТ 57580 для медицинских организаций
            if any(kw in organization.lower() for kw in ["буз", "миац", "медицин"]):
                if "ГОСТ Р 57580" in content:
                    issues.append(AuditIssue(
                        section=section_title, type="inapplicable_standard",
                        description="ГОСТ Р 57580 не применяется к медицинским организациям!"
                    ))
            
            # Артефакты OCR
            if re.search(r'[\uFFFD\u200B\u200C]', content):
                issues.append(AuditIssue(
                    section=section_title, type="ocr_artifacts",
                    description="Обнаружены артефакты OCR/кодировки"
                ))
        
        # 3. Расчёт оценки (обновить коэффициент)
        compliant = len(issues) == 0
        score = max(0.0, 1.0 - (len(issues) * 0.15))  # было 0.2
        
        return AuditorOutput(success=True, data={
            "compliant": compliant, 
            "issues": [i.model_dump() for i in issues], 
            "score": score
        })