# src/agents/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel

class AgentInput(BaseModel):
    task: str
    context: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}

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