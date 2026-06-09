# src/agents/writer.py
import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable, Awaitable
from pydantic import BaseModel, Field
from src.agents.base import BaseAgent, AgentInput, AgentOutput
from src.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ПОСТ-ОБРАБОТКИ MARKDOWN ===

def _normalize_markdown_headers(content: str, expected_number: str) -> str:
    """
    Корректная нормализация: удаляет ДУБЛИРУЮЩУЮ нумерацию,
    но сохраняет структуру, если номер уже корректный.
    """
    lines = content.split('\n')
    result = []
    is_first_heading = True
    
    for line in lines:
        stripped = line.strip()
        
        # Обрабатываем только заголовки уровня 1 (# Текст)
        if stripped.startswith('# ') and not stripped.startswith('##'):
            title_text = stripped[2:].strip()
            
            # Удаляем существующую нумерацию в начале заголовка
            title_text = re.sub(r'^\d+(?:\.\d+)*[\.\s:—-]+\s*', '', title_text)
            
            # Добавляем ожидаемый номер
            normalized_heading = f"# {expected_number}. {title_text}"
            result.append(normalized_heading)
            
            # Добавляем разрыв страницы после заголовков глав
            if re.match(r'^\d+\.0$', expected_number) and is_first_heading:
                result.append('\n\\newpage\n')
                is_first_heading = False
        else:
            result.append(line)
    
    return '\n'.join(result)


def _normalize_markdown_tables(content: str) -> str:
    """
    Нормализация Markdown-таблиц:
    - Заменяет варианты выравнивания (:---:, :---, ---:) на | --- |
    - Добавляет недостающие разделители
    - Выравнивает количество колонок во всех строках
    """
    # Сначала простая замена вариантов выравнивания
    content = re.sub(r'\|\s*:-+:?\s*\|', '| --- |', content)
    content = re.sub(r'\|\s*:-+\s*\|', '| --- |', content)
    content = re.sub(r'\|\s*-+:?\s*\|', '| --- |', content)
    content = re.sub(r'\|\s*-+\s*\|', '| --- |', content)
    
    # Затем нормализация структуры таблиц
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Проверяем, начинается ли здесь таблица (строка с |)
        if '|' in line and not line.startswith('```'):
            table_lines = []
            while i < len(lines) and '|' in lines[i] and not lines[i].strip().startswith('```'):
                table_lines.append(lines[i].strip())
                i += 1
            
            if len(table_lines) >= 2:
                normalized = _fix_table_structure(table_lines)
                result.extend(normalized)
            else:
                result.extend(table_lines)
        else:
            result.append(lines[i])
            i += 1
    
    return '\n'.join(result)


def _fix_table_structure(table_lines: List[str]) -> List[str]:
    """
    Исправляет структуру Markdown-таблицы:
    - Определяет количество колонок по заголовку
    - Добавляет строку-разделитель, если её нет
    - Дополняет строки недостающими ячейками
    """
    if not table_lines:
        return table_lines
    
    header = table_lines[0]
    header_cells = [c.strip() for c in header.split('|') if c.strip()]
    num_cols = len(header_cells)
    
    if num_cols == 0:
        return table_lines
    
    # Проверяем, есть ли уже строка-разделитель
    has_separator = False
    separator_idx = -1
    
    for idx, line in enumerate(table_lines[1:], start=1):
        if re.match(r'^[\s|:\-]+$', line):
            has_separator = True
            separator_idx = idx
            break
    
    if not has_separator:
        separator = '|' + '|'.join(['---'] * num_cols) + '|'
        table_lines.insert(1, separator)
    else:
        separator = '|' + '|'.join(['---'] * num_cols) + '|'
        table_lines[separator_idx] = separator
    
    result = [table_lines[0], table_lines[1]]
    
    for line in table_lines[2:]:
        cells = [c.strip() for c in line.split('|')]
        while cells and cells[0] == '':
            cells.pop(0)
        while cells and cells[-1] == '':
            cells.pop()
        
        while len(cells) < num_cols:
            cells.append('')
        
        cells = cells[:num_cols]
        result.append('| ' + ' | '.join(cells) + ' |')
    
    return result


def _clean_metadata_artifacts(content: str) -> str:
    """Удаляет мета-информацию и служебные комментарии из текста."""
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    content = re.sub(r'\{\{[^}]+\}\}', '', content)
    content = re.sub(r'^\s+$', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()


def _add_figure_placeholders(content: str, section_title: str = "") -> str:
    """Добавляет плейсхолдеры для изображений в формате [Рис. – Описание]."""
    patterns = [
        (r'(как показано на )?(рисунке|схеме|диаграмме)(\s+\d+)?', r'\1[Рис. – Описание]'),
        (r'(см\.\s*)?(рис\.|сх\.)(\s+\d+)?', r'\1[Рис. – Описание]'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
    
    return content


def _add_table_placeholders(content: str) -> str:
    """Добавляет плейсхолдеры для таблиц в формате [Таблица – Название]."""
    content = re.sub(
        r'(как показано в )?(таблице)(\s+\d+)?',
        r'\1[Таблица – Название]',
        content,
        flags=re.IGNORECASE
    )
    return content


def _postprocess_content(content: str, section_number: str = "", section_title: str = "") -> str:
    """
    Полная пост-обработка контента.
    Применяется к финальному собранному тексту (не к отдельным чанкам streaming).
    """
    if section_number:
        content = _normalize_markdown_headers(content, section_number)
    
    content = _clean_metadata_artifacts(content)
    content = _normalize_markdown_tables(content)
    content = _add_figure_placeholders(content, section_title)
    content = _add_table_placeholders(content)
    
    return content


# === МОДЕЛИ ОТВЕТОВ ===

class WriterOutput(AgentOutput):
    section_number: str = Field(default="1", description="Номер раздела")
    title: str = Field(default="", description="Заголовок раздела")
    content: str = Field(default="", description="Сгенерированный текст в Markdown")
    word_count: int = Field(default=0, description="Количество слов")
    references: List[str] = Field(default_factory=list, description="Ссылки на нормативку")


# === БАЗОВЫЙ ПИСАТЕЛЬ С ПОДДЕРЖКОЙ STREAMING ===

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
        self.stream_callback: Optional[Callable] = None

    @abstractmethod
    def _build_prompt(self, input_data: AgentInput) -> str:
        pass

    async def execute(self, input_data: AgentInput) -> WriterOutput:
        try:
            prompt = self._build_prompt(input_data)
            section_title = input_data.context.get("section_title", "Unknown")
            section_number = input_data.context.get("section_number", "")
            attempt = input_data.context.get("attempt", 0)
            additional_context = input_data.context.get("additional_context", "")
            
            if additional_context:
                prompt += f"\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ ОТ ПОЛЬЗОВАТЕЛЯ:\n{additional_context}"
            
            logger.info(f"[{self.name}] Генерация раздела: {section_title} (попытка #{attempt+1})")
            logger.debug(f"[{self.name}] Промпт (первые 800 симв.): {prompt[:800]}...")
            
            # Передаём context_hint для корректного кэширования доработок
            context_hint = f"attempt:{attempt}|section:{section_title}"
            
            # Если есть callback — используем streaming
            if self.stream_callback:
                content = await self._generate_with_streaming(prompt, section_title, context_hint)
            else:
                response = await self.ollama_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    context_hint=context_hint
                )
                content = response.get("message", {}).get("content", "")
            
            # Пост-обработка финального контента
            content = _postprocess_content(content, section_number, section_title)
            
            word_count = len(content.split())
            logger.info(f"[{self.name}] Сгенерировано {word_count} слов")
            
            if word_count < 300:
                logger.warning(f"[{self.name}] ⚠ Мало слов ({word_count}), возможна деградация качества")
            
            return WriterOutput(
                success=True,
                section_number=section_number,
                title=section_title,
                content=content,
                word_count=word_count,
                references=input_data.context.get("references", [])
            )
        except Exception as e:
            logger.error(f"[{self.name}] Ошибка генерации: {e}", exc_info=True)
            return WriterOutput(success=False, error=str(e))

    async def _generate_with_streaming(self, prompt: str, section_title: str, context_hint: str = "") -> str:
        """Генерация с streaming через callback"""
        content_parts = []
        async for chunk in self.ollama_client.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            context_hint=context_hint,
        ):
            if chunk.content:
                content_parts.append(chunk.content)
                # Отправляем чанк через callback (сырой, без пост-обработки)
                if self.stream_callback:
                    await self.stream_callback({
                        "type": "text_chunk",
                        "section_title": section_title,
                        "chunk": chunk.content,
                        "total_so_far": len("".join(content_parts))
                    })
        return "".join(content_parts)


# === СПЕЦИАЛИЗИРОВАННЫЕ ПИСАТЕЛИ ===

class PolicyWriter(BaseWriter):
    name = "policy_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        standards = input_data.context.get("standards", [])
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        style_requirements = """
ТРЕБОВАНИЯ К СТИЛЮ (критично для качества!):
1. ЯЗЫК: Строго русский. Запрещено использовать китайский, английский
(кроме общепринятых аббревиатур: ИБ, ПДн, TLS, AES, VPN, SIEM)
или другие языки.
2. ВАРИАТИВНОСТЬ КОНСТРУКЦИЙ — используйте РАЗНЫЕ формы:
Императивные (40% текста): "Обязуется обеспечить...", "Необходимо внедрить..."
Описательные (30% текста): "Организация обеспечивает...", "Система включает..."
Пассивные (20% текста): "Должно быть обеспечено...", "Подлежит выполнению..."
Процедурные (10% текста): "Осуществляется мониторинг...", "Производится проверка..."
3. ЗАПРЕЩЕНО: местоимения "я", "мы", "вы"; разговорные обороты; эмоциональная окраска.
4. НЕ добавляйте нумерацию в заголовки! Пишите "# Шифрование", а не "# 1.1 Шифрование"
""".strip()
        
        standards_validation = """
1. ФСТЭК России №239 — дата: 25.12.2017 (НЕ 03.12.2019!)
2. Для медицинских организаций (БУЗ/МИАЦ): НЕ использовать ГОСТ Р 57580 (это для банков!)
3. Формат ссылок: [152-ФЗ, ст. 19], [ФСТЭК №21, п. 15]
4. НЕ выдумывайте пункты стандартов — если не знаете точный номер,
пишите обобщенно: "в соответствии с требованиями ФСТЭК России"
"""
        
        refinement_block = ""
        if attempt > 0 and feedback:
            refinement_block = f"""
УЧТИ ПРЕДЫДУЩИЕ ЗАМЕЧАНИЯ (попытка #{attempt+1}):
{feedback}
Исправьте указанные недостатки, сохранив структуру и ссылки на стандарты.
""".strip()
        
        return f"""
Ты — эксперт по разработке Политик информационной безопасности с опытом
работы в ФСТЭК России и банках.

ЗАДАЧА: Напиши раздел "{section.get('number', '1')}. {section.get('title', '')}"
для организации {org}.

ПРИМЕНИМЫЕ СТАНДАРТЫ: {', '.join(standards) if standards else 'не указаны'}

{style_requirements}

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат: Markdown (# для заголовков 1 уровня, ## для 2 уровня)
2. Объем: Минимум 350 слов содержательного текста (без заголовков)
3. Конкретика: Только реализуемые меры, без "воды" и общих фраз
4. Ссылки на стандарты с номерами пунктов

{standards_validation}

{refinement_block}

ЦЕЛЬ РАЗДЕЛА: {section.get('purpose', '')}

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
3. Минимум 300 слов
4. НЕ добавляй нумерацию в заголовки! Пиши "# Цели", а не "# 1.1 Цели"

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
• Официально-деловой стиль: "Осуществляется", "Производится", "Возлагается на"
• Распределение ответственности: "Ответственность возлагается на..."
• Используй безличные конструкции, избегай "я", "мы", "вы"

ТРЕБОВАНИЯ К КОНТЕНТУ:
1. Формат Markdown
2. Описание процессов и процедур с указанием исполнителей
3. Минимум 300 слов
4. Ссылки на нормативные документы С УКАЗАНИЕМ ПУНКТОВ
5. НЕ добавляй нумерацию в заголовки!

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
2. Методология оценки рисков
3. Количественные и качественные оценки с обоснованием
4. Минимум 350 слов
5. Ссылки на ISO 27005, ГОСТ Р 57580.2

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

РАЗДЕЛ: {section.get('purpose', '')}
{refinement_block}

Верни ТОЛЬКО текст раздела в Markdown.
"""


class AccessControlWriter(BaseWriter):
    name = "access_control_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        org = input_data.context.get("organization", "Организация")
        feedback = input_data.context.get("feedback", "")
        attempt = input_data.context.get("attempt", 0)
        
        style_requirements = """
ТРЕБОВАНИЯ К СТИЛЮ:
• ЯЗЫК: Строго русский.
• Используй безличные конструкции: "Обязуется", "Необходимо", "Запрещается"
• Избегай местоимений "я", "мы", "вы"
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

ВАЖНО: Весь ответ должен быть на РУССКОМ ЯЗЫКЕ.

РАЗДЕЛ: {section.get('purpose', '')}
{refinement_block}

Верни ТОЛЬКО текст раздела в Markdown.
"""


class VkrReportWriter(BaseWriter):
    name = "vkr_report_writer"
    default_model = "gemma4"
    
    def _build_prompt(self, input_data: AgentInput) -> str:
        section = input_data.context.get("section_plan", {})
        topic = input_data.context.get("topic", "Тема ВКР")
        section_type = input_data.context.get("section_type", "main")
        section_number = input_data.context.get("section_number", "")
        code_context = input_data.context.get("code_context", "")
        bibliography_file = input_data.context.get("bibliography_file", "references.bib")

        style_guide = """
АКАДЕМИЧЕСКИЙ СТИЛЬ (критично!):
• Безличные конструкции: "проведён анализ", "предложено", "установлено"
• Цитирование: идеи → [1], факты → [2, с. 45]
• Научная лексика: "методология", "эмпирический", "верификация"
• Запрещено: "я/мы/вы", императивы, разговорная лексика
• Рисунки/Таблицы: плейсхолдеры [Рис. 2.1 – Описание], [Таблица 3.2 – Название]
"""

        return f"""
Ты — научный редактор ВКР по специальности 10.03.01 "Информационная безопасность".

ТЕМА: {topic}
РАЗДЕЛ: "{section.get('number', '1')}. {section.get('title', '')}"
ТИП: {section_type}

{style_guide}

ТРЕБОВАНИЯ К ФОРМАТУ:
1. Markdown: # заголовки 1 уровня, ## заголовки 2 уровня — БЕЗ нумерации
2. Формулы: $$...$$ \\tag{{номер}}
3. Рисунки/Таблицы: Только плейсхолдеры [Рис. Х.Х – Описание]
4. Ссылки: [1], [2, с. 45] — квадратные скобки

{code_context if code_context else ""}

Верни ТОЛЬКО текст раздела в формате Markdown, без пояснений.
Весь ответ должен быть на РУССКОМ ЯЗЫКЕ.
"""


# === ФАБРИКА ===

def create_writer(
    doc_type: str,
    model: str = None,
    temperature: float = None,
    request_type: str = "default",
    ollama_client: Optional[OllamaClient] = None
) -> BaseWriter:
    """
    Создаёт экземпляр писателя для указанного типа документа.
    """
    writers_map = {
        "policy": PolicyWriter,
        "instruction": InstructionWriter,
        "regulation": RegulationWriter,
        "threat_model": ThreatModelWriter,
        "risk_assessment": RiskAssessmentWriter,
        "incident_response": IncidentResponseWriter,
        "access_control": AccessControlWriter,
        "vkr_report": VkrReportWriter,
    }
    
    writer_class = writers_map.get(doc_type, PolicyWriter)
    writer = writer_class(
        model=model,
        temperature=temperature,
        request_type=request_type
    )
    
    if ollama_client is not None:
        writer.ollama_client = ollama_client
    
    return writer