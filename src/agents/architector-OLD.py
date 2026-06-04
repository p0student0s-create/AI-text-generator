# src/agents/architector.py
"""
Агент-Архитектор: проектирование структуры документа
"""
import logging
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from src.agents.base import BaseAgent, AgentInput, AgentOutput
from src.services.ollama_client import OllamaClient
from src.services.industry_classifier import RegulatoryClassifier, RegulatoryProfile

logger = logging.getLogger(__name__)


class HierarchyNode(BaseModel):
    id: str
    number: str
    title: str
    parent_id: Optional[str] = None
    level: int = 1
    purpose: str = ""
    required_standards: List[str] = Field(default_factory=list)
    prompt_for_writer: str = ""


class ArchitectOutput(AgentOutput):
    hierarchy: List[HierarchyNode] = Field(default_factory=list)
    industry_profile: Optional[Dict] = None


class ArchitectAgent(BaseAgent):
    name = "architector"
    
    def __init__(self, model: str = "gemma4", timeout: float = 90.0):
        super().__init__()
        self.model = model
        self.timeout = timeout
        self.ollama_client = OllamaClient(
            base_url="http://localhost:11434",
            model=self.model,
            timeout=self.timeout
        )
        self.regulatory_classifier = RegulatoryClassifier()
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        doc_type = input_data.context.get("doc_type", "policy")
        standards = input_data.context.get("standards", [])
        requirements = input_data.context.get("requirements", [])
        organization = input_data.context.get("organization", "Организация")
        city = input_data.context.get("city", "")

        from src.services.rag_service import RAGService
        rag = RAGService()

        # Определяем нормативный профиль организации
        industry_profile = self.regulatory_classifier.classify(organization)
        regime, regulatory_profile = industry_profile  # ← Переименовано для ясности
        
        logger.info(f"   Определён профиль: {regulatory_profile.name} ({regime.value})")
        logger.info(f"   Обязательные стандарты: {regulatory_profile.mandatory_standards}")
        logger.info(f"   Ключевые термины: {regulatory_profile.key_terms[:5]}")

        template = rag.get_structure_template(doc_type, use_examples=True)
        
        if template["source"] == "example" and template["hierarchy"]:
            logger.info(f"Архитектор: структура из примера {template['example_info']['file']}")
            hierarchy = self._build_hierarchy_from_example(
                template["hierarchy"],
                standards=standards,
                organization=organization,
                requirements=requirements,
                regulatory_profile=regulatory_profile
            )
        else:
            logger.info("Архитектор: используем дефолтную структуру")
            base_structure = self._get_base_structure(doc_type)
            hierarchy = []
            for i, (num, title, desc) in enumerate(base_structure):
                node = HierarchyNode(
                    id=f"node_{i}",
                    number=num,
                    title=title,
                    purpose=desc,
                    required_standards=standards,
                    prompt_for_writer=self._build_writer_prompt(
                        number=num, title=title, desc=desc,
                        organization=organization, requirements=requirements, 
                        standards=standards, regulatory_profile=regulatory_profile
                    )
                )
                hierarchy.append(node)

        logger.info(f"Архитектор построил иерархию: {len(hierarchy)} узлов")
        
        return ArchitectOutput(
            success=True, 
            data={
                "hierarchy": [h.model_dump() for h in hierarchy],
                "industry_profile": {
                    "regime": regime.value,
                    "name": regulatory_profile.name,
                    "key_terms": regulatory_profile.key_terms,
                    "protected_data": regulatory_profile.protected_data,
                    "typical_roles": regulatory_profile.typical_roles,
                    "typical_systems": regulatory_profile.typical_systems,
                    "specific_risks": regulatory_profile.specific_risks,
                    "mandatory_standards": regulatory_profile.mandatory_standards,
                }
            }
        )

    def _build_hierarchy_from_example(
        self,
        example_hierarchy: List[Dict],
        standards: List[str],
        organization: str,
        requirements: List[Dict],
        level: int = 1,
        regulatory_profile: Optional[RegulatoryProfile] = None
    ) -> List[HierarchyNode]:
        """Построение иерархии на основе примера из БД."""
        nodes = []
        
        for i, section in enumerate(example_hierarchy):
            number = section.get("number", f"{level}.{i+1}")
            title = section.get("title", f"Раздел {number}")
            purpose = section.get("content_preview", f"Содержание раздела {title}")
            
            node = HierarchyNode(
                id=section.get("id", f"ex_{level}_{i}"),
                number=number,
                title=title,
                level=section.get("level", level),
                parent_id=section.get("parent_id"),
                purpose=purpose,
                required_standards=standards,
                prompt_for_writer=self._build_writer_prompt(
                    number=number,
                    title=title,
                    desc=purpose,
                    organization=organization,
                    requirements=requirements,
                    standards=standards,
                    regulatory_profile=regulatory_profile,
                    example_context=section.get("content_preview", "")
                )
            )
            nodes.append(node)
            
            if "children" in section and section["children"]:
                child_nodes = self._build_hierarchy_from_example(
                    section["children"],
                    standards, organization, requirements,
                    level=level + 1,
                    regulatory_profile=regulatory_profile
                )
                nodes.extend(child_nodes)
        
        return nodes

    def _build_writer_prompt(
        self, 
        number: str, 
        title: str, 
        desc: str,
        organization: str, 
        requirements: List[Dict], 
        standards: List[str],
        regulatory_profile: Optional['RegulatoryProfile'] = None,
        example_context: str = "",
        industry: Optional[str] = None
    ) -> str:
        """Улучшенный промпт с учётом нормативного профиля"""

        # БЛОК ОТРАСЛЕВОЙ СПЕЦИФИКИ
        industry_block = ""
        if regulatory_profile:
            # Формируем блок с примерами использования
            example_phrases_block = ""
            if hasattr(regulatory_profile, 'example_phrases') and regulatory_profile.example_phrases:
                example_phrases_block = "\nПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:\n"
                for key, value in regulatory_profile.example_phrases.items():
                    example_phrases_block += f"• {key}: {value}\n"
            
            industry_block = f"""
АНАЛИЗ ОТРАСЛЕВОЙ СПЕЦИФИКИ:
Ты пишешь документ для организации: "{organization}"
Определён профиль: {regulatory_profile.name}

Перед генерацией текста выполни мысленный анализ названия организации 
и определи её сферу деятельности. Адаптируй текст под эту сферу 
согласно следующим параметрам:

КЛЮЧЕВЫЕ ТЕРМИНЫ (используйте их вместо общих):
{', '.join(regulatory_profile.key_terms)}

ЗАЩИЩАЕМЫЕ ДАННЫЕ (упоминайте конкретно):
{', '.join(regulatory_profile.protected_data[:5])}

ТИПИЧНЫЕ РОЛИ (вместо "пользователь"):
{', '.join(regulatory_profile.typical_roles[:5])}

ИНФОРМАЦИОННЫЕ СИСТЕМЫ (указывайте их):
{', '.join(regulatory_profile.typical_systems[:5])}

СПЕЦИФИЧНЫЕ РИСКИ (учитывайте при описании мер):
{', '.join(regulatory_profile.specific_risks[:5])}

ДОПОЛНИТЕЛЬНАЯ НОРМАТИВКА:
{chr(10).join(f"- {std}" for std in regulatory_profile.recommended_standards)}

{example_phrases_block}

ТРЕБОВАНИЯ К ГЕНЕРАЦИИ:
1. Вместо "пользователь" пишите: "{regulatory_profile.typical_roles[0] if regulatory_profile.typical_roles else 'сотрудник'}"
2. Вместо "конфиденциальные данные" пишите: "{regulatory_profile.protected_data[0] if regulatory_profile.protected_data else 'конфиденциальная информация'}"
3. Упоминайте системы: {', '.join(regulatory_profile.typical_systems[:3])}
4. Ссылайтесь на нормативку: {', '.join(regulatory_profile.recommended_standards[:2])}
5. Описывайте риски: {regulatory_profile.specific_risks[0] if regulatory_profile.specific_risks else 'утечка данных'}

ВАЖНО: Если организация явно относится к одной из сфер (медицина, образование, 
энергетика, госсектор, финансы), используй соответствующую терминологию и ссылайся 
на профильные нормативные акты. Если сфера неясна — пиши универсально.
"""

        if regulatory_profile and regulatory_profile.industry_vectors:
            # Формируем блок рекомендаций (не требований!)
            vector_block = "\nОТРАСЛЕВЫЕ РЕКОМЕНДАЦИИ (опционально):\n"
            for vector_name, terms in regulatory_profile.industry_vectors.items():
                if terms:
                    display_name = {
                        "key_terms": "Термины",
                        "protected_data": "Защищаемые данные",
                        "typical_roles": "Роли",
                        "typical_systems": "Системы"
                    }.get(vector_name, vector_name)
                    # Показываем первые 3 термина для краткости
                    vector_block += f"• {display_name}: {', '.join(terms[:3])}\n"
            
            vector_block += "\nЭти термины помогут сделать документ более релевантным отрасли,\n"
            vector_block += "но не обязательны к использованию — адаптируйте текст по необходимости.\n"
            
            industry_block += vector_block

        # Блок примера
        example_block = ""
        if example_context:
            example_block = f"""
ПРИМЕР ИЗ АНАЛОГИЧНОГО ДОКУМЕНТА:
{example_context[:400]}...
Используй этот пример как референс по оформлению, но адаптируй под организацию {organization}.
""".strip()
        
        return f"""
ЗАДАЧА: Напишите раздел "{number}. {title}" для организации {organization}.

{industry_block}

{example_block}

ТРЕБОВАНИЯ К СТИЛЮ:
• Используйте РАЗНООБРАЗНЫЕ конструкции (не только "Должно быть обеспечено")
• Чередуйте: "Обязуется", "Необходимо", "Организация обеспечивает", 
  "Система включает", "Осуществляется"
• Избегайте повторения одной конструкции более 3 раз подряд
• Официально-деловой стиль, но без избыточного канцелярита

ТРЕБОВАНИЯ ИЗ БАЗЫ ЗНАНИЙ:
{self._format_requirements(requirements)}

ПРАВИЛА:
1. Минимум 500 слов. Конкретные меры, алгоритмы, ссылки на стандарты.
2. Формат: Markdown (# для заголовков, • для списков).
3. Ссылайтесь на стандарты: [152-ФЗ, ст. 19], [ФСТЭК №21, п. 15]
4. Учтите отраслевую специфику "{organization}" и профиль "{regulatory_profile.name if regulatory_profile else 'универсальный'}".
5. НЕ используйте местоимения "я", "мы", "вы".
6. ВАЖНО: Избегайте механистического перечисления! 
   Текст должен быть связным, а не просто списком требований.

Верните ТОЛЬКО текст раздела.
"""
    
    @staticmethod
    def _format_requirements(requirements: List[Dict]) -> str:
        """Форматирование требований из RAG для промпта"""
        if not requirements:
            return "• Нет специфических требований из базы знаний"
        
        lines = []
        for req in requirements[:5]:
            citation = req.get("citation", "")
            text = req.get("text", "")[:200]
            lines.append(f"• [{citation}] {text}...")
        
        return "\n".join(lines)

    def _get_base_structure(self, doc_type: str) -> List[tuple]:
        """Дефолтные шаблоны структур документов"""
        templates = {
            "policy": [
                ("1", "Общие положения", "Цели, область применения, термины"),
                ("2", "Нормативные ссылки", "Перечень стандартов"),
                ("3", "Термины и определения", "Расшифровка аббревиатур"),
                ("4", "Требования к защите", "Технические и организационные меры"),
                ("5", "Управление доступом", "Аутентификация, авторизация, роли"),
                ("6", "Ответственность", "Распределение обязанностей"),
                ("7", "Контроль и аудит", "Проверки, журналирование, отчётность"),
                ("8", "Заключительные положения", "Порядок пересмотра"),
            ],
            "instruction": [
                ("1", "Область применения", "Кому и когда применяется"),
                ("2", "Подготовка к работе", "Ресурсы, доступы, проверки"),
                ("3", "Порядок выполнения", "Пошаговый алгоритм действий"),
                ("4", "Требования безопасности", "Меры предосторожности"),
                ("5", "Действия в нештатных ситуациях", "Алгоритмы реагирования"),
                ("6", "Завершение работы", "Закрытие сессий, отчёты"),
            ],
            "regulation": [
                ("1", "Общие положения", "Основания и цели регламента"),
                ("2", "Процедуры и процессы", "Описание регулируемых процессов"),
                ("3", "Роли и ответственность", "Распределение функций"),
                ("4", "Контроль исполнения", "Методы мониторинга"),
                ("5", "Ответственность за нарушения", "Санкции и меры"),
            ],
            "threat_model": [
                ("1", "Объект защиты", "Что защищаем"),
                ("2", "Актуальные угрозы", "Модель угроз"),
                ("3", "Каналы утечки", "Возможные векторы атак"),
                ("4", "Оценка рисков", "Анализ рисков"),
                ("5", "Меры защиты", "Контрмеры"),
            ],
            "risk_assessment": [
                ("1", "Методология", "Подход к оценке"),
                ("2", "Активы", "Что оцениваем"),
                ("3", "Угрозы и уязвимости", "Что может пойти не так"),
                ("4", "Оценка рисков", "Расчёт рисков"),
                ("5", "Меры обработки рисков", "Как минимизировать"),
            ],
            "incident_response": [
                ("1", "Классификация инцидентов", "Типы инцидентов"),
                ("2", "Процедуры реагирования", "Что делать"),
                ("3", "Роли и ответственность", "Кто что делает"),
                ("4", "Коммуникации", "Кого уведомлять"),
                ("5", "Восстановление", "Как вернуться к нормальной работе"),
            ],
            "access_control": [
                ("1", "Политика доступа", "Принципы"),
                ("2", "Аутентификация", "Как проверяем личность"),
                ("3", "Авторизация", "Как даём права"),
                ("4", "Учётные записи", "Управление учётками"),
                ("5", "Аудит доступа", "Контроль"),
            ],
        }
        return templates.get(doc_type, templates["policy"])
    
    @staticmethod
    def _remove_duplicate_sections(content: str) -> str:
        """Удаляет дублирующиеся разделы по заголовку"""
        sections = re.split(r'^(#\s+.+)$', content, flags=re.MULTILINE)
        if len(sections) < 3:
            return content
        
        seen_titles = set()
        result = []
        
        for i in range(0, len(sections), 2):
            header = sections[i+1] if i+1 < len(sections) else ""
            body = sections[i+2] if i+2 < len(sections) else sections[i] if i < len(sections) else ""
            
            title = header.replace('#', '').strip() if header else ""
            
            if title and title in seen_titles:
                continue
            if title:
                seen_titles.add(title)
            
            if header:
                result.append(header)
            result.append(body)
        
        return '\n'.join(result)