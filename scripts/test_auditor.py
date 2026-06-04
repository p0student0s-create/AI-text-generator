# scripts/test_auditor.py
import asyncio
from src.agents.auditor import AuditorAgent, AgentInput

async def test_audit():
    auditor = AuditorAgent()
    
    # Тестовый контент с ошибками
    test_sections = {
        "1": """
        # Цели
        Должно быть обеспечено соблюдение Приказа ФСТЭК России №239 от 03.12.2019
        и ГОСТ Р 57580-2017.
        """,
        "2": """
        # Меры защиты
        Применяется шифрование по ГОСТ Р 57580-2017, п. 6.3
        """
    }
    
    input_data = AgentInput(
        task="Проверка",
        context={
            "sections": test_sections,
            "hierarchy": [{"number": "1"}, {"number": "2"}],
            "standards": ["152fz", "fstek_21"],
            "organization": "БУЗОО МИАЦ"
        }
    )
    
    result = await auditor.execute(input_data)
    
    print("=== РЕЗУЛЬТАТ АУДИТА ===")
    print(f"Соответствует: {result.data['compliant']}")
    print(f"Оценка: {result.data['score']:.2f}")
    print(f"Проблемы: {len(result.data['issues'])}")
    
    for issue in result.data['issues']:
        print(f"  ❌ {issue['type']}: {issue['description']}")

asyncio.run(test_audit())