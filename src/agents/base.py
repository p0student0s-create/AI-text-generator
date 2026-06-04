# src/agents/base.py
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel

class DocumentMode(Enum):
    REGULATORY = "regulatory"  # Политика, регламент, инструкция
    THESIS = "thesis"          # Выпускная квалификационная работа
    REPORT = "report"          # Отчёт, статья

class AgentInput(BaseModel):
    task: str
    context: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    doc_mode: DocumentMode = DocumentMode.REGULATORY
    thesis_metadata: Optional[Dict] = None  # Для режима THESIS

class AgentOutput(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}

class BaseAgent(ABC):
    name: str = "base_agent"
    
    @abstractmethod
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        pass