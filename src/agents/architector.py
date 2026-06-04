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
from src.services.codebase_scanner import CodebaseScanner

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
    code_context: Optional[str] = None


class ArchitectOutput(AgentOutput):
    hierarchy: List[HierarchyNode] = Field(default_factory=list)
    industry_profile: Optional[Dict] = None


class ArchitectAgent(BaseAgent):
    name = "architector"
    
    def __init__(self, model: str = "gemma4", timeout: float = 90.0, project_root: str = "."):
        """
        Инициализация агента-архитектора.
        
        :param model: Имя модели Ollama для генерации
        :param timeout: Таймаут запросов в секундах
        :param project_root: Корневая директория проекта для сканирования кода
        """
        super().__init__()
        self.model = model
        self.timeout = timeout
        self.project_root = project_root
        self.ollama_client = OllamaClient(
            base_url="http://localhost:11434",
            model=self.model,
            timeout=self.timeout
        )
        self.regulatory_classifier = RegulatoryClassifier()
        self.codebase_scanner = CodebaseScanner(project_root=project_root)
        self._scan_results: Optional[Dict] = None
        self._scanned = False
    
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
        regime, regulatory_profile = industry_profile
        
        logger.info(f"   Определён профиль: {regulatory_profile.name} ({regime.value})")
        logger.info(f"   Обязательные стандарты: {regulatory_profile.mandatory_standards}")
        logger.info(f"   Ключевые термины: {regulatory_profile.key_terms[:5]}")

        # === СКанирование кодовой базы для ВКР (однократно за сессию) ===
        if doc_type == "vkr_report" and not self._scanned:
            logger.info("Сканирование кодовой базы для контекста ВКР...")
            self._scan_results = self.codebase_scanner.scan(include_docs=True)
            self._scanned = True
            stats = self._scan_results.get("statistics", {})
            logger.info(f"✓ Сканирование завершено: {stats.get('total_files', 0)} файлов, "
                       f"{stats.get('total_classes', 0)} классов, "
                       f"{stats.get('total_functions', 0)} функций")

        template = rag.get_structure_template(doc_type, use_examples=True)
        
        use_example = (
            template["source"] == "example" 
            and template["hierarchy"] 
            and template.get("example_info", {}).get("doc_type") == doc_type
        )

        if use_example:
            logger.info(f"Архитектор: структура из примера {template['example_info']['file']}")
            hierarchy = self._build_hierarchy_from_example(
                template["hierarchy"],
                standards=standards,
                organization=organization,
                requirements=requirements,
                regulatory_profile=regulatory_profile
            )
        else:
            # === ИСПОЛЬЗУЕМ ШАБЛОН ПО УМОЛЧАНИЮ ===
            logger.info(f"Архитектор: пример не найден или не релевантен, используем шаблон для '{doc_type}'")
            base_structure = self._get_base_structure(doc_type)
            hierarchy = []
            for i, (num, title, desc) in enumerate(base_structure):
                # === ПОЛУЧЕНИЕ КОНТЕКСТА ИЗ КОДОВОЙ БАЗЫ (для ВКР) ===
                code_context = None
                if doc_type == "vkr_report" and self._scanned:
                    code_context = self.codebase_scanner.generate_section_context(
                        section_title=title,
                        section_number=num if num not in ["ВВЕДЕНИЕ", "ЗАКЛЮЧЕНИЕ", "ПРИЛОЖЕНИЯ"] else ""
                    )
                
                node = HierarchyNode(
                    id=f"node_{i}",
                    number=num,
                    title=title,
                    purpose=desc,
                    required_standards=standards,
                    code_context=code_context,
                    prompt_for_writer=self._build_writer_prompt(
                        number=num, title=title, desc=desc,
                        organization=organization, requirements=requirements, 
                        standards=standards, regulatory_profile=regulatory_profile,
                        code_context=code_context
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
                },
                # Передача метаданных сканирования для отладки
                "scan_info": {
                    "scanned": self._scanned,
                    "files_count": self._scan_results.get("statistics", {}).get("total_files") if self._scanned else None,
                } if doc_type == "vkr_report" else None
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
            
            # === КОНТЕКСТ КОДА ДЛЯ ПРИМЕРОВ ===
            code_context = None
            if hasattr(self, '_scanned') and self._scanned:
                code_context = self.codebase_scanner.generate_section_context(
                    section_title=title,
                    section_number=number
                )
            
            node = HierarchyNode(
                id=section.get("id", f"ex_{level}_{i}"),
                number=number,
                title=title,
                level=section.get("level", level),
                parent_id=section.get("parent_id"),
                purpose=purpose,
                required_standards=standards,
                code_context=code_context,
                prompt_for_writer=self._build_writer_prompt(
                    number=number,
                    title=title,
                    desc=purpose,
                    organization=organization,
                    requirements=requirements,
                    standards=standards,
                    regulatory_profile=regulatory_profile,
                    example_context=section.get("content_preview", ""),
                    code_context=code_context
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
        industry: Optional[str] = None,
        code_context: Optional[str] = None
    ) -> str:
        """Улучшенный промпт с учётом нормативного профиля и контекста кода."""

        # === БЛОК КОНТЕКСТА ИЗ КОДОВОЙ БАЗЫ (для ВКР) ===
        code_block = ""
        if code_context:
            code_block = f"""
КОНТЕКСТ РЕАЛИЗАЦИИ (на основе анализа кодовой базы проекта):
{code_context}

Используйте эту информацию для описания архитектуры и реализации 
в научно-техническом стиле. Ссылайтесь на конкретные классы, методы 
и файлы при описании компонентов системы.
""".strip()

        # БЛОК ОТРАСЛЕВОЙ СПЕЦИФИКИ
        industry_block = ""
        if regulatory_profile:
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

            if regulatory_profile.industry_vectors:
                vector_block = "\nОТРАСЛЕВЫЕ РЕКОМЕНДАЦИИ (опционально):\n"
                for vector_name, terms in regulatory_profile.industry_vectors.items():
                    if terms:
                        display_name = {
                            "key_terms": "Термины",
                            "protected_data": "Защищаемые данные",
                            "typical_roles": "Роли",
                            "typical_systems": "Системы"
                        }.get(vector_name, vector_name)
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

{code_block}

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
7. ДЛЯ ВКР: При описании архитектуры ссылайтесь на реализованные классы 
   и методы из контекста кодовой базы выше (если предоставлен).

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
        """Дефолтные шаблоны структур документов.
        
        Возвращает список кортежей: (номер, заголовок, описание_содержания)
        """
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
            "vkr_report": [
                # === ВВЕДЕНИЕ ===
                ("ВВЕДЕНИЕ", "Введение", 
                 "Актуальность темы, статистика публикаций (eLibrary/Scopus/IEEE), "
                 "проблематика ручной подготовки документов, ограничения LLM, "
                 "цель и 5 задач исследования, объект/предмет, практическая значимость. "
                 "Объём: ~800 слов. Стиль: научно-технический."),
                
                # === ГЛАВА 1: АНАЛИЗ ПРЕДМЕТНОЙ ОБЛАСТИ ===
                ("1", "Аудит информационной безопасности",
                 "Определение аудита ИБ, цели, виды (внутренний/внешний, периодический/непрерывный), "
                 "этапы проведения, что проверяется. Ссылки на источники."),
                
                ("1.1", "Источники требований в области ИБ",
                 "Обзор нормативной базы: 152-ФЗ, 149-ФЗ, 187-ФЗ, приказы ФСТЭК №21/117/239, "
                 "ГОСТ Р ИСО/МЭК 27001, внутренние документы организации. Таблица: акт → требования."),
                
                ("1.2", "Понятие и компоненты ИИ-агентов",
                 "Архитектура агентов: LLM-ядро, инструменты, память, оркестрация. "
                 "Паттерны: ReAct, Orchestrator-Workers. RAG-системы: принцип работы, варианты."),
                
                ("1.3", "Анализ научных публикаций",
                 "Обзор работ по RAG (Gao et al., Huang & Huang), LLM-агентам (Yao et al.), "
                 "применению LLM в кибербезопасности, рискам галлюцинаций и prompt injection."),
                
                ("1.4", "Сравнительный анализ инструментов",
                 "Сканеры уязвимостей (CVE Binary Tool, OpenVAS), аудит инфраструктуры (BTA, SharpHound), "
                 "комплексные платформы (RedCheck, MaxPatrol), ИИ-агенты (Windows-AI-Agent, Open Interpreter). "
                 "Таблица сравнения по 6 критериям."),
                
                # === ГЛАВА 2: ПРОЕКТИРОВАНИЕ АРХИТЕКТУРЫ ===
                ("2", "Общая архитектура системы",
                 "Модульный конвейер: User → Orchestrator → [Agents] → RAG → PDF. "
                 "Схема компонентов. Жизненный цикл генерации документа."),
                
                ("2.1", "Сбор конфигураций",
                 "Гибридный подход: WinSysData + собственные PowerShell-скрипты. "
                 "Категории собираемых параметров: password_policy, firewall, SMB, event_logs."),
                
                ("2.2", "Модуль RAG",
                 "Архитектура: чанкинг, эмбеддинги (BGE-m3), векторная БД (ChromaDB), "
                 "гибридный поиск (семантический + BM25), переранжирование кросс-энкодером."),
                
                ("2.3", "Используемые технологии и обоснование выбора",
                 "Таблица: инструмент → назначение → обоснование. Python, FastAPI, React, "
                 "PostgreSQL, Ollama, qwen2.5:7b, WinRM, PowerShell."),
                
                # === ГЛАВА 3: РЕАЛИЗАЦИЯ ПРОТОТИПА ===
                ("3", "Общая логика работы прототипа",
                 "Диаграмма последовательности: загрузка политики → извлечение требований → "
                 "RAG-индекс → сбор конфигураций → нормализация → проверка → отчёт."),
                
                ("3.1", "Загрузка и обработка политики безопасности",
                 "Поддержка форматов TXT/DOCX/PDF, очистка текста, подготовка к извлечению правил."),
                
                ("3.2", "Извлечение требований из политики",
                 "Гибридный механизм: детерминированные правила + LLM/RAG-извлечение, "
                 "объединение результатов, удаление дублей, кэширование."),
                
                ("3.3", "Сбор данных с Windows-хостов",
                 "Подключение через WinRM, collector-скрипты, обработка ошибок, "
                 "категории параметров: парольная политика, firewall, SMB, обновления."),
                
                ("3.4", "Нормализация собранных данных",
                 "Приведение к единой структуре host_data, преобразование типов, "
                 "группировка по категориям: password_policy, audit_policy, firewall и др."),
                
                ("3.5", "Механизм проверки соответствия",
                 "Статусы: PASS/FAIL/UNKNOWN/WARNING/COLLECTION_ERROR. "
                 "Детерминированная логика сравнения: >=, <=, == для числовых условий."),
                
                ("3.6", "Использование LLM при проверке и генерации рекомендаций",
                 "Сценарии: извлечение требований, объяснение UNKNOWN, генерация рекомендаций. "
                 "Запрет на PASS без подтверждённого факта."),
                
                ("3.7", "Формирование отчётов",
                 "JSON-отчёт для машинной обработки, HTML-отчёт для пользователя. "
                 "Поля результата: rule_id, status, evidence, recommendation, missing_data_query."),
                
                ("3.8", "Пользовательский интерфейс",
                 "Веб-интерфейс на React+FastAPI: загрузка политики, запуск аудита, "
                 "просмотр правил, отчётов, настроек, benchmark-модуль."),
                
                # === ГЛАВА 4: АНАЛИЗ И СРАВНЕНИЕ LLM-МОДЕЛЕЙ ===
                ("4", "Роль LLM-моделей в системе аудита",
                 "Задачи: извлечение требований, структурирование, рекомендации, оценка статусов. "
                 "Риски: галлюцинации, JSON-ошибки, ложные PASS."),
                
                ("4.1", "Метрики сравнения моделей",
                 "Для извлечения: Precision, Recall, F1. Для статусов: Accuracy, False PASS. "
                 "Дополнительно: JSON validity, latency, интегральный балл."),
                
                ("4.2", "Условия проведения benchmark",
                 "Параметры: timeout=300с, num_ctx=8192, temperature=0. "
                 "Единая тестовая база: политика, эталонные правила, задачи оценки."),
                
                ("4.3", "Результаты тестирования облачных моделей",
                 "Таблица: Claude Sonnet 4.5 (83.38), Gemini 2.5 Flash (81.91), "
                 "GPT-4.1-mini (76.26), Mistral Small (62.77)."),
                
                ("4.4", "Результаты тестирования локальных моделей",
                 "Таблица: qwen2.5:7b (77.66, 0 False PASS) — выбор для прототипа. "
                 "Обоснование: локальный запуск, приемлемое качество, стабильный JSON."),
                
                # === ГЛАВА 5: ТЕСТИРОВАНИЕ ПРОТОТИПА ===
                ("5", "Цели и задачи тестирования",
                 "Проверка загрузки политики, извлечения требований, сбора конфигураций, "
                 "нормализации, детерминированных проверок, формирования отчётов."),
                
                ("5.1", "Тестовый стенд",
                 "Управляющая машина + 2 Windows-хоста в виртуальной сети. "
                 "Взаимодействие через WinRM. Группы проверяемых требований."),
                
                # === ГЛАВА 6: БИЗНЕС-МОДЕЛЬ И ФИНАНСОВАЯ МОДЕЛЬ ===
                ("6", "Бизнес-модель продукта",
                 "Целевая аудитория, ценностное предложение, Business Model Canvas, "
                 "модели внедрения: внутренний инструмент, on-premise, SaaS, консалтинг."),
                
                ("6.1", "Финансовая модель проекта",
                 "Формулы: экономия времени, TCO, ROI, срок окупаемости. "
                 "Расчёт для пилотного/среднего/крупного сценариев."),
                
                ("6.2", "Дорожная карта развития проекта",
                 "Этапы: стабилизация MVP (0-3 мес), расширение collector (3-6 мес), "
                 "нормативная база (6-9 мес), интеграции (9-12 мес), промышленная эксплуатация (18-24 мес)."),
                
                # === ЗАКЛЮЧЕНИЕ (строго перед источниками!) ===
                ("ЗАКЛЮЧЕНИЕ", "Заключение",
                "Сокращенные выводы по всем главам: "
                "1) Результаты анализа предметной области; "
                "2) Обоснование архитектуры; "
                "3) Итоги реализации; "
                "4) Результаты benchmark; "
                "5) Подтверждение работоспособности; "
                "6) Экономическая эффективность. "
                "Объём: ~400 слов."),
                
                # === ИСТОЧНИКИ (строго после заключения!) ===
                ("ИСТОЧНИКИ", "Список использованных источников",
                "Список из 18+ источников: нормативные акты, научные статьи, документация. "
                "Оформление по ГОСТ 7.1-2003. "
                "ТРЕБОВАНИЯ: ≥30% источников — публикации за последние 3 года; "
                "приоритет рецензируемым журналам и официальным документам."),
                
                # === ПРИЛОЖЕНИЯ (строго последними) ===
                ("ПРИЛОЖЕНИЯ", "Приложения",
                "Фрагменты кода, скриншоты интерфейса, таблица результатов тестирования."),
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