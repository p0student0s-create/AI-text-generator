# src/agents/critic.py
"""
Агент-Критик: проверка качества сгенерированного текста
"""
import logging
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from src.agents.base import BaseAgent, AgentInput, AgentOutput
from src.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# === Маппинг ключей стандартов на варианты написания ===
STANDARD_ALIASES = {
    "gost_57580": ["ГОСТ Р 57580", "57580", "ГОСТ 57580", "ГОСТР57580"],
    "gost_r_57580_1": ["ГОСТ Р 57580.1", "57580.1", "ГОСТ 57580.1"],
    "gost_r_57580_2": ["ГОСТ Р 57580.2", "57580.2", "ГОСТ 57580.2"],
    "fstek_239": [
        "ФСТЭК 239", "приказ ФСТЭК №239", "приказ ФСТЭК России от 25.12.2017 № 239",
        "ФСТЭК №239", "ФСТЭК-239", "239-ФСТЭК"
    ],
    "fstek_21": ["ФСТЭК 21", "приказ ФСТЭК №21", "СЗКИ", "ФСТЭК-21"],
    "iso_27001": ["ISO 27001", "ISO/IEC 27001", "ГОСТ Р ИСО/МЭК 27001", "ИСО 27001"],
    "iso_27002": ["ISO 27002", "ISO/IEC 27002", "ИСО 27002"],
    "iso_27005": ["ISO 27005", "ISO/IEC 27005", "ИСО 27005"],
    "pd_152fz": ["152-ФЗ", "Федеральный закон №152-ФЗ", "О персональных данных", "152 ФЗ"],
    "187fz": ["187-ФЗ", "О безопасности КИИ", "187 ФЗ"],
}

# === Ключевые слова для определения типа раздела ===
TECHNICAL_SECTION_KEYWORDS = {
    "норматив", "термин", "определ", "аббревиатур", "ссылк", "сокращ",
    "глоссар", "словар", "приложен", "список"
}


def _check_standards(text: str, standards: List[str]) -> bool:
    """
    Проверяет наличие упоминаний стандартов в тексте с учётом алиасов.
    
    :param text: Текст для проверки
    :param standards: Список ключей стандартов (например, ["gost_57580", "fstek_239"])
    :return: True, если найден хотя бы один стандарт
    """
    if not text or not standards:
        return False
    
    text_lower = text.lower()
    
    for std_key in standards:
        # Получаем все варианты написания стандарта
        aliases = STANDARD_ALIASES.get(std_key, [std_key])
        
        # Проверяем каждый алиас
        for alias in aliases:
            if alias.lower() in text_lower:
                logger.debug(f"Найден стандарт: {std_key} (через '{alias}')")
                return True
    
    return False


def _is_technical_section(title: str) -> bool:
    """Определяет, является ли раздел техническим (термины, нормативные ссылки и т.п.)"""
    if not title:
        return False
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in TECHNICAL_SECTION_KEYWORDS)


class CriticReport(BaseModel):
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    feedback: str = Field(default="")
    needs_revision: bool = Field(default=True)
    details: Dict[str, Any] = Field(default_factory=dict)


class CriticOutput(AgentOutput):
    report: CriticReport = CriticReport()


class CriticAgent(BaseAgent):
    name = "critic"
    
    # Веса для расчёта оценки
    WEIGHT_LENGTH = 0.4
    WEIGHT_STANDARDS = 0.3
    WEIGHT_STYLE = 0.3
    WEIGHT_VARIETY = 0.15
    
    def __init__(
        self,
        model: str = "gemma4",
        timeout: float = 120.0,
        min_score: float = 0.8,
        min_words: int = 250,
        smart_threshold: bool = True
    ):
        super().__init__()
        self.model = model
        self.timeout = timeout
        self.min_score = min_score
        self.min_words = min_words
        self.smart_threshold = smart_threshold
        self.ollama_client = OllamaClient(
            base_url="http://localhost:11434",
            model=self.model,
            timeout=self.timeout
        )

    def _check_style_variety(self, text: str) -> tuple[bool, float, Dict]:
        """
        Проверяет разнообразие стилистических конструкций.
        
        :return: (has_variety, variety_score, details)
        """
        details = {}
        
        # Считаем частоту конструкций
        imperative_markers = [
            "Обязуется", "Необходимо", "Запрещается", "Требуется", 
            "Следует", "Надлежит", "Предписывается"
        ]
        passive_markers = [
            "должно быть обеспечено", "должно осуществляться", 
            "подлежит выполнению", "является обязательным"
        ]
        descriptive_markers = [
            "Организация обеспечивает", "Система включает", 
            "Политика определяет", "Процедура предусматривает"
        ]
        procedural_markers = [
            "Осуществляется", "Производится", "Выполняется", 
            "Проводится", "Реализуется"
        ]
        
        # Подсчёт
        imperative_count = sum(text.count(m) for m in imperative_markers)
        passive_count = sum(text.count(m) for m in passive_markers)
        descriptive_count = sum(text.count(m) for m in descriptive_markers)
        procedural_count = sum(text.count(m) for m in procedural_markers)
        
        total = imperative_count + passive_count + descriptive_count + procedural_count
        
        details["imperative_count"] = imperative_count
        details["passive_count"] = passive_count
        details["descriptive_count"] = descriptive_count
        details["procedural_count"] = procedural_count
        details["total_markers"] = total
        
        # Проверка на доминирование одной конструкции
        if total == 0:
            return False, 0.0, details
        
        max_count = max(imperative_count, passive_count, descriptive_count, procedural_count)
        dominance_ratio = max_count / total
        
        # Если одна конструкция составляет >70% — плохо
        has_variety = dominance_ratio < 0.7
        variety_score = max(0.0, 1.0 - dominance_ratio)
        
        details["dominance_ratio"] = round(dominance_ratio, 2)
        details["has_variety"] = has_variety
        
        return has_variety, variety_score, details

    def _calculate_score(
        self,
        text: str,
        standards: List[str],
        is_technical: bool = False
    ) -> tuple[float, Dict[str, Any]]:
        """Рассчитывает оценку качества текста с учётом разнообразия стиля"""
        details = {}
        
        # 1. Проверка длины
        word_count = len(text.split())
        is_long_enough = word_count >= self.min_words
        details["word_count"] = word_count
        details["length_ok"] = is_long_enough
        
        length_score = self.WEIGHT_LENGTH if is_long_enough else 0.0
        
        # 2. Проверка стандартов
        has_standards = _check_standards(text, standards)
        details["standards_ok"] = has_standards
        
        standards_score = self.WEIGHT_STANDARDS if has_standards else 0.0
        
        # 3. Проверка стиля (наличие маркеров ОДС)
        style_markers = [
            "Обязуется", "Необходимо", "Запрещается", "Должен", "Следует",
            "должно быть обеспечено", "должно осуществляться", "подлежит"
        ]
        has_style = any(marker in text for marker in style_markers)
        details["style_ok"] = has_style
        
        style_score = self.WEIGHT_STYLE if has_style else 0.0
        
        # 4. Проверка разнообразия стиля
        has_variety, variety_score, variety_details = self._check_style_variety(text)
        details.update(variety_details)
        details["variety_ok"] = has_variety
        
        variety_final_score = self.WEIGHT_VARIETY if has_variety else 0.0
        
        # Итоговая оценка
        raw_score = length_score + standards_score + style_score + variety_final_score
        score = min(1.0, raw_score)
        
        # Для технических разделов — небольшая коррекция
        if is_technical and not has_style:
            score = min(1.0, length_score + standards_score + 0.15)
            details["technical_adjustment"] = True
        
        details["raw_score"] = raw_score
        details["final_score"] = round(score, 2)
        
        return score, details
    
    def _get_effective_threshold(self, is_technical: bool, attempt: int = 0) -> float:
        """Возвращает порог принятия с учётом типа раздела и попытки"""
        threshold = self.min_score
        
        # Для технических разделов снижаем порог
        if self.smart_threshold and is_technical:
            threshold = max(0.7, threshold - 0.1)
        
        # После первой доработки — чуть мягче
        if attempt >= 1:
            threshold = max(0.65, threshold - 0.05)
        
        return threshold
    
    # Метод валидации нормативных ссылок
    def _validate_regulatory_references(
        self, 
        text: str, 
        standards: List[str]
    ) -> Dict[str, Any]:
        """
        Проверяет, соответствуют ли цитируемые пункты стандартов реальному содержанию.
        
        :param text: Текст для проверки
        :param standards: Список стандартов
        :return: Результат валидации
        """
        from src.services.rag_service import RAGService
        rag = RAGService()
        
        # Извлекаем все ссылки на стандарты из текста
        # Паттерн: [Стандарт, п. X.Y] или [Стандарт, ст. X]
        citation_pattern = r'\[([^\]]+,\s*(?:п\.?\s*|ст\.?\s*)?\d+(?:\.\d+)*)\]'
        citations = re.findall(citation_pattern, text)
        
        valid_citations = []
        invalid_citations = []
        
        for citation in citations:
            # Парсим цитату: "ФСТЭК №21, п. 15" → standard="fstek_21", clause="15"
            parts = citation.split(',')
            if len(parts) < 2:
                invalid_citations.append(citation)
                continue
            
            std_name = parts[0].strip()
            clause = parts[1].strip().replace('п.', '').replace('ст.', '').strip()
            
            # Ищем требование в RAG
            requirements = rag.search_requirements(
                query=f"{std_name} пункт {clause}",
                standards=standards,
                n_results=1
            )
            
            if requirements and len(requirements) > 0:
                valid_citations.append(citation)
            else:
                invalid_citations.append(citation)
        
        return {
            "total_citations": len(citations),
            "valid_citations": valid_citations,
            "invalid_citations": invalid_citations,
            "validation_score": len(valid_citations) / max(len(citations), 1)
        }

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        text = input_data.context.get("text", "")
        standards = input_data.context.get("standards", [])
        is_technical = input_data.context.get("is_technical", False)
        attempt = input_data.context.get("attempt", 0)
        
        if not text or not text.strip():
            return CriticOutput(
                success=False,
                error="Текст пуст",
                data=CriticReport(score=0.0, feedback="Пустой текст", needs_revision=True).model_dump()
            )

        # Расчёт оценки
        score, details = self._calculate_score(text, standards, is_technical)
        
        # Валидация нормативных ссылок
        validation_result = self._validate_regulatory_references(text, standards)
        details["validation"] = validation_result
        
        # Если есть невалидные ссылки — снижаем оценку
        if validation_result["invalid_citations"]:
            invalid_count = len(validation_result["invalid_citations"])
            score *= (1.0 - 0.1 * invalid_count)  # Снижаем на 10% за каждую невалидную ссылку
            score = max(0.0, score)
            details["final_score"] = round(score, 2)
        
        # Определение необходимости доработки
        threshold = self._get_effective_threshold(is_technical, attempt)
        needs_revision = score < threshold
        
        # Формирование обратной связи
        feedback_parts = []
        feedback_parts.append(f"Слов: {details['word_count']}")
        feedback_parts.append(f"Стандарты: {'✓' if details['standards_ok'] else '✗'}")
        feedback_parts.append(f"Стиль: {'ОДС' if details['style_ok'] else '–'}")
        
        # Добавляем информацию о валидации ссылок
        if validation_result["invalid_citations"]:
            feedback_parts.append(f"⚠ Невалидные ссылки: {len(validation_result['invalid_citations'])}")
        
        if details.get("technical_adjustment"):
            feedback_parts.append("[тех. раздел]")
        
        report = CriticReport(
            score=round(score, 2),
            feedback=" | ".join(feedback_parts),
            needs_revision=needs_revision,
            details=details
        )
        
        log_level = logging.INFO if not needs_revision else logging.DEBUG
        logger.log(log_level, f"Критик: {report.score:.2f} | {report.feedback} | порог: {threshold:.2f}")
        
        return CriticOutput(success=True, data=report.model_dump())