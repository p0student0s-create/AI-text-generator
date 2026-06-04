# src/agents/writer.py
import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from src.agents.base import BaseAgent, AgentInput, AgentOutput
from src.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class WriterOutput(AgentOutput):
    section_number: str = Field(default="1", description="Номер раздела")
    title: str = Field(default="", description="Заголовок раздела")
    content: str = Field(default="", description="Сгенерированный текст в Markdown")
    word_count: int = Field(default=0, description="Количество слов")
    references: List[str] = Field(default_factory=list, description="Ссылки на нормативку")


class BaseWriter(BaseAgent, ABC):
    name = "base_writer"
    role = "Генератор контента нормативных документов"
    default_model = "gemma4"
    default_temperature = 0.2
    default_timeout = 600.0
    
    def __init__(self, model: str = None, temperature: float = None, timeout: float = 600.0, request_type: str = "default"):
        super().__init__()
        self.model = model or self.default_model
        self.temperature = temperature or self.default_temperature
        self.timeout = timeout if timeout is not None else self.default_timeout
        self.request_type = request_type
        self.ollama_client = OllamaClient(
            base_url="http://localhost:11434",
            model=self.model,
            timeout=self.timeout,
            request_type=self.request_type
        )
    
    @abstractmethod
    def _build_prompt(self, input_data: AgentInput) -> str:
        pass
    
    async def execute(self, input_data: AgentInput) -> WriterOutput:
        try:
            prompt = self._build_prompt(input_data)
            section_title = input_data.context.get("section_title", "Unknown")
            attempt = input_data.context.get("attempt", 0)
                
            # Логирование промптов для отладки
            logger.info(f"[{self.name}] Генерация раздела: {section_title} (попытка #{attempt+1})")
            logger.debug(f"[{self.name}] Промпт (первые 800 симв.): {prompt[:800]}...")
            logger.debug(f"[{self.name}] Контекст: attempt={attempt}, standards={input_data.context.get('standards', [])}")
                
            # Передаём context_hint для корректного кэширования доработок
            context_hint = f"attempt:{attempt}|section:{section_title}"
                
            response = await self.ollama_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                context_hint=context_hint  # ← Дифференциация кэша по попытке
            )
                
            content = response.get("message", {}).get("content", "")
            word_count = len(content.split())
                
            logger.info(f"[{self.name}] Сгенерировано {word_count} слов")
            if word_count < 300:
                logger.warning(f"[{self.name}] ⚠ Мало слов ({word_count}), возможна деградация качества")
                
            return WriterOutput(
                success=True,
                section_number=input_data.context.get("section_number", "1"),
                title=section_title,
                content=content,
                word_count=word_count,
                references=input_data.context.get("references", [])
            )
                
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка генерации: {e}", exc_info=True)
            return WriterOutput(success=False, error=str(e))


# === Специализированные писатели ===

class PolicyWriter(BaseWriter):
    name = "policy_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        standards = input_data.context.get("standards", [])
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        # Явные требования к стилю ОДС
        style_requirements = """
ТРЕБОВАНИЯ К СТИЛЮ (критично для качества!):

1. ЯЗЫК: Строго русский. Запрещено использовать китайский, английский 
   (кроме общепринятых аббревиатур: ИБ, ПДн, TLS, AES, VPN, SIEM) 
   или другие языки.

2. ВАРИАТИВНОСТЬ КОНСТРУКЦИЙ — используйте РАЗНЫЕ формы:
   
   Императивные (40% текста):
      • "Обязуется обеспечить..."
      • "Необходимо внедрить..."
      • "Запрещается передавать..."
      • "Требуется организовать..."
   
   Описательные (30% текста):
      • "Организация обеспечивает..."
      • "Система включает..."
      • "Процедура предусматривает..."
      • "Политика определяет..."
   
   Пассивные (20% текста):
      • "Должно быть обеспечено..."
      • "Подлежит выполнению..."
      • "Является обязательным..."
   
   Процедурные (10% текста):
      • "Осуществляется мониторинг..."
      • "Производится проверка..."
      • "Выполняется анализ..."

3. ЗАПРЕЩЕНО:
   • Использовать местоимения "я", "мы", "вы", "наш", "ваш"
   • Разговорные обороты ("нужно сделать", "надо проверить")
   • Эмоциональную окраску ("очень важно", "крайне необходимо")
   • Повторять одну и ту же конструкцию более 3 раз подряд

4. РАЗНООБРАЗИЕ ПРЕДЛОЖЕНИЙ:
   • Чередуйте короткие (10-15 слов) и длинные (20-30 слов) предложения
   • Используйте вводные конструкции: "в частности", "например", 
     "в соответствии с", "с учетом"
   • Применяйте причастные и деепричастные обороты для связности

5. НЕ создавайте заголовки "Цели", "Задачи" внутри текста — 
   они уже есть в структуре документа!
   • Используйте конкретные названия: "Технические меры", 
     "Шифрование данных", "Журналирование событий"
   
6. НЕ добавляйте нумерацию в заголовки! 
   • Пишите "# Шифрование", а не "# 1.1 Шифрование"
   • Нумерация добавится автоматически при компиляции
""".strip()

        # Блок для нормативных ссылок
        standards_validation = """
1. ФСТЭК России №239 — дата: 25.12.2017 (НЕ 03.12.2019!)
2. Для медицинских организаций (БУЗ/МИАЦ):
   • НЕ использовать ГОСТ Р 57580 (это для банков!)
   • Использовать: 152-ФЗ, Приказ ФСТЭК №21, Приказ Минздрава №956н
3. Формат ссылок: [152-ФЗ, ст. 19], [ФСТЭК №21, п. 15]
4. НЕ выдумывайте пункты стандартов — если не знаете точный номер, 
   пишите обобщенно: "в соответствии с требованиями ФСТЭК России"
"""

        # Блок для доработок
        refinement_block = ""
        if attempt > 0 and feedback:
            refinement_block = f"""
УЧТИ ПРЕДЫДУЩИЕ ЗАМЕЧАНИЯ (попытка #{attempt+1}):
{feedback}

Исправьте указанные недостатки, сохранив структуру и ссылки на стандарты.
Особое внимание уделите разнообразию стилевых конструкций!
""".strip()
        
        return f"""
Ты — эксперт по разработке Политик информационной безопасности с опытом 
работы в ФСТЭК России и банках. Ты знаешь, как писать документы, которые
проходят проверки и реально используются в организациях.

ЗАДАЧА: Напиши раздел "{section.get('number', '1')}. {section.get('title', '')}" 
для организации {org}.

ПРИМЕНИМЫЕ СТАНДАРТЫ: {', '.join(standards) if standards else 'не указаны'}

{style_requirements}

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат: Markdown (# для заголовков 1 уровня, ## для 2 уровня)
2. Объем: Минимум 350 слов содержательного текста (без заголовков)
3. Конкретика: Только реализуемые меры, без "воды" и общих фраз
4. Структура: Каждый подраздел — 2-3 конкретных меры с пояснениями
5. Ссылки на стандарты с номерами пунктов:
   • ГОСТ: "[ГОСТ Р 57580-2017, п. 6.3]"
   • ФСТЭК: "[ФСТЭК России №239, раздел 5]"
   • 152-ФЗ: "[152-ФЗ, ст. 19]"

{standards_validation}

{refinement_block}

ЦЕЛЬ РАЗДЕЛА: {section.get('purpose', '')}

СОВЕТ: Представь, что пишешь документ для реальной организации.
Текст должен быть понятен сотрудникам, но при этом соответствовать 
требованиям регуляторов. Избегай канцелярита, но сохраняйте официальный стиль.

Верни ТОЛЬКО текст раздела в формате Markdown, без пояснений и преамбулы.
Начни сразу с заголовка раздела.
"""


class InstructionWriter(BaseWriter):
    name = "instruction_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        refinement_block = ""
        if attempt > 0 and feedback:
            refinement_block = f"\n\nУЧТИ ЗАМЕЧАНИЯ: {feedback}"
        
        return f"""
Ты — эксперт по разработке инструкций по информационной безопасности.

ЗАДАЧА: Напиши раздел "{section.get('number', '1')}. {section.get('title', '')}" 
для организации {org}.

ТРЕБОВАНИЯ К СТИЛЮ:
• Используй императивные конструкции: "Обязуется", "Необходимо", "Запрещается", "Следует"
• Пиши пошагово: "1. Действие... 2. Действие..."
• Избегай местоимений "я", "мы", "вы"

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат Markdown
2. Пошаговые алгоритмы действий с нумерацией
3. Чёткие, однозначные формулировки
4. Минимум 300 слов
5. Конкретные действия, а не общие слова
6. НЕ добавляй нумерацию в заголовки! Пиши "# Цели", а не "# 1.1 Цели"
   • Нумерация добавится автоматически при компиляции Pandoc + LaTeX

РАЗДЕЛ: {section.get('purpose', '')}
{refinement_block}

Верни ТОЛЬКО текст раздела в Markdown.
"""


class RegulationWriter(BaseWriter):
    name = "regulation_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        refinement_block = ""
        if attempt > 0 and feedback:
            refinement_block = f"\n\nУЧТИ ЗАМЕЧАНИЯ: {feedback}"
        
        return f"""
Ты — эксперт по разработке регламентов по информационной безопасности.

ЗАДАЧА: Напиши раздел "{section.get('number', '1')}. {section.get('title', '')}" 
для организации {org}.

ТРЕБОВАНИЯ К СТИЛЮ:
• Официально-деловой стиль: "Осуществляется", "Производится", "Возлагается на", "Контроль осуществляет"
• Распределение ответственности: "Ответственность возлагается на...", "Контроль осуществляет..."
• Используй безличные конструкции, избегай "я", "мы", "вы"

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат Markdown
2. Описание процессов и процедур с указанием исполнителей
3. Распределение ролей и ответственности
4. Минимум 300 слов
5. Ссылки на нормативные документы С УКАЗАНИЕМ ПУНКТОВ:
   • "[ГОСТ Р 57580-2017, п. 6.3]"
   • "[ФСТЭК России №239, раздел 5]"
   • "[152-ФЗ, ст. 19]"
6. Конкретные процедуры, а не общие слова
7. НЕ добавляй нумерацию в заголовки! Пиши "# Цели", а не "# 1.1 Цели"
   • Нумерация добавится автоматически при компиляции Pandoc + LaTeX

РАЗДЕЛ: {section.get('purpose', '')}
{refinement_block}

Верни ТОЛЬКО текст раздела в Markdown.
"""


class ThreatModelWriter(BaseWriter):
    name = "threat_model_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        refinement_block = ""
        if attempt > 0 and feedback:
            refinement_block = f"\n\nУЧТИ ЗАМЕЧАНИЯ: {feedback}"
        
        return f"""
Ты — эксперт по моделированию угроз информационной безопасности по методологии ФСТЭК.

ЗАДАЧА: Напиши раздел "{section.get('number', '1')}. {section.get('title', '')}" 
для организации {org}.

ТРЕБОВАНИЯ К СТИЛЮ:
• Аналитический стиль: "Выявлена угроза...", "Вероятность реализации...", "Последствия..."
• Используй термины: "актив", "уязвимость", "вектор атаки", "контрмера"

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат Markdown
2. Описание угроз, уязвимостей, каналов утечки
3. Оценка рисков: вероятность × последствия
4. Минимум 350 слов
5. Ссылки на ФСТЭК №239 с номерами пунктов
6. НЕ добавляй нумерацию в заголовки! Пиши "# Цели", а не "# 1.1 Цели"
   • Нумерация добавится автоматически при компиляции Pandoc + LaTeX

РАЗДЕЛ: {section.get('purpose', '')}
{refinement_block}

Верни ТОЛЬКО текст раздела в Markdown.
"""


class RiskAssessmentWriter(BaseWriter):
    name = "risk_assessment_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        refinement_block = ""
        if attempt > 0 and feedback:
            refinement_block = f"\n\nУЧТИ ЗАМЕЧАНИЯ: {feedback}"
        
        return f"""
Ты — эксперт по оценке рисков информационной безопасности.

ЗАДАЧА: Напиши раздел "{section.get('number', '1')}. {section.get('title', '')}" 
для организации {org}.

ТРЕБОВАНИЯ К СТИЛЮ:
• Количественные оценки: "Уровень риска: высокий (8/10)", "Вероятность: 0.3"
• Обоснование: "На основании...", "С учётом..."

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат Markdown
2. Методология оценки рисков (качественная или количественная)
3. Количественные и качественные оценки с обоснованием
4. Минимум 350 слов
5. Ссылки на ISO 27005, ГОСТ Р 57580.2
6. НЕ добавляй нумерацию в заголовки! Пиши "# Цели", а не "# 1.1 Цели"
   • Нумерация добавится автоматически при компиляции Pandoc + LaTeX

РАЗДЕЛ: {section.get('purpose', '')}
{refinement_block}

Верни ТОЛЬКО текст раздела в Markdown.
"""


class IncidentResponseWriter(BaseWriter):
    name = "incident_response_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        refinement_block = ""
        if attempt > 0 and feedback:
            refinement_block = f"\n\nУЧТИ ЗАМЕЧАНИЯ: {feedback}"
        
        return f"""
Ты — эксперт по реагированию на инциденты ИБ.

ЗАДАЧА: Напиши раздел "{section.get('number', '1')}. {section.get('title', '')}" 
для организации {org}.

ТРЕБОВАНИЯ К СТИЛЮ:
• Алгоритмический стиль: "При обнаружении инцидента: 1. ... 2. ... 3. ..."
• Чёткие роли: "Ответственный: ..., Действие: ..."

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат Markdown
2. Алгоритмы действий при инцидентах с нумерацией шагов
3. Роли и ответственность на каждом этапе
4. Минимум 300 слов
5. НЕ добавляй нумерацию в заголовки! Пиши "# Цели", а не "# 1.1 Цели"
   • Нумерация добавится автоматически при компиляции Pandoc + LaTeX

РАЗДЕЛ: {section.get('purpose', '')}
{refinement_block}

Верни ТОЛЬКО текст раздела в Markdown.
"""

@staticmethod
def _normalize_markdown_headers(content: str, expected_number: str) -> str:
    """
    Корректная нормализация: удаляет ДУБЛИРУЮЩУЮ нумерацию,
    но сохраняет структуру, если номер уже корректный.
    """
    lines = content.split('\n')
    result = []
    
    for line in lines:
        stripped = line.strip()
        
        # Обрабатываем только заголовки уровня 1 (# Текст)
        if stripped.startswith('# ') and not stripped.startswith('# #'):
            title_text = stripped[2:].strip()  # Убираем "# "
            
            # Проверяем: если заголовок УЖЕ начинается с нужного номера — не трогаем
            if re.match(rf'^{re.escape(expected_number)}[\.\s]', title_text):
                result.append(f"# {title_text}")
                continue
            
            # Если есть ЛЮБОЙ номер в начале — удаляем его
            title_text = re.sub(r'^\d+(?:\.\d+)*[\.\s:—-]+', '', title_text)
            
            # Добавляем ожидаемый номер
            result.append(f"# {expected_number}. {title_text}")
        else:
            result.append(line)
    
    return '\n'.join(result)

class AccessControlWriter(BaseWriter):
    name = "access_control_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        # Усиленные требования к стилю
        style_requirements = """
ТРЕБОВАНИЯ К СТИЛЮ:
• ЯЗЫК: Строго русский. Запрещено использовать китайский, английский (кроме общепринятых аббревиатур: ИБ, ПДн, TLS, AES) или другие языки.
• Используй безличные конструкции: "Обязуется", "Необходимо", "Запрещается", "Следует"
• Избегай местоимений "я", "мы", "вы"
• Пиши в настоящем времени, утвердительно
• Для правил доступа: "Доступ предоставляется...", "Доступ запрещается..."
""".strip()
        
        refinement_block = ""
        if attempt > 0 and feedback:
            refinement_block = f"\n\nУЧТИ ЗАМЕЧАНИЯ: {feedback}"
        
        return f"""
Ты — эксперт по управлению доступом в информационных системах.

ЗАДАЧА: Напиши раздел "{section.get('number', '1')}. {section.get('title', '')}" 
для организации {org}.

{style_requirements}

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат Markdown
2. Правила аутентификации и авторизации с конкретными параметрами
3. Разграничение прав: роли, группы, уровни доступа
4. Минимум 300 слов
5. Ссылки на ФСТЭК с номерами пунктов
6. НЕ добавляй нумерацию в заголовки! Пиши "# Цели", а не "# 1.1 Цели"
   • Нумерация добавится автоматически при компиляции Pandoc + LaTeX

ВАЖНО: Весь ответ должен быть на РУССКОМ ЯЗЫКЕ. Если в процессе генерации возникнет переключение на другой язык — немедленно вернитесь к русскому.

РАЗДЕЛ: {section.get('purpose', '')}
{refinement_block}

Верни ТОЛЬКО текст раздела в Markdown.
"""

# Фабрика для создания писателя
def create_writer(
    doc_type: str,
    model: str = None,
    temperature: float = None,
    request_type: str = "default",
    ollama_client: Optional[OllamaClient] = None
) -> BaseWriter:
    """
    Создаёт экземпляр писателя для указанного типа документа.
    
    :param doc_type: Тип документа (policy, instruction, regulation, etc.)
    :param model: Имя модели Ollama (опционально)
    :param temperature: Температура генерации (опционально)
    :param ollama_client: Готовый клиент Ollama (опционально, для тестов)
    :return: Экземпляр BaseWriter
    """
    writers_map = {
        "policy": PolicyWriter,
        "instruction": InstructionWriter,
        "regulation": RegulationWriter,
        "threat_model": ThreatModelWriter,
        "risk_assessment": RiskAssessmentWriter,
        "incident_response": IncidentResponseWriter,
        "access_control": AccessControlWriter,
    }
    
    writer_class = writers_map.get(doc_type, PolicyWriter)
    writer = writer_class(
        model=model, 
        temperature=temperature, 
        request_type=request_type
    )
    
    # Если передан готовый клиент — используем его (для тестов/моков)
    if ollama_client is not None:
        writer.ollama_client = ollama_client
    
    return writer