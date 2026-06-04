# scripts/test_generation.py
import asyncio
import os
import sys
sys.path.append('.')

# 1. Принудительный офлайн-режим (модель уже скачана, сеть не нужна)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["SENTENCE_TRANSFORMERS_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# 2. "Агрессивная" очистка проблемных прокси до инициализации httpx
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
    val = os.environ.get(var)
    if val and not val.startswith(('http://', 'https://', 'socks5://')):
        os.environ[var] = ''  # Убираем socks4 и другие неподдерживаемые схемы

print("✓ Окружение пропатчено. Запуск генерации...")

from src.agents.orchestrator import DocumentOrchestrator

async def test_medical_policy():
    """Генерация политики для медицинской организации"""
    
    orchestrator = DocumentOrchestrator(llm_config={
        "base_url": "http://localhost:11434",
        "policy_model": "gemma4",
        "critic_min_score": 0.7,
        "output_dir": "storage/test_output"
    })

    # Тест для БУЗОО "МИАЦ" (медицинская организация)
    result = await orchestrator.generate_document(
        doc_type="policy",
        standards=[
            "152fz",           # ✓ Должен остаться
            "fstek_21",        # ✓ Должен остаться
            "gost_57580",      # ✗ Должен быть исключён!
            'minzdrav_956n'
        ],
        title="Политика информационной безопасности",
        organization="БУЗОО «МИАЦ»",
        object_type="Информационная система персональных данных",
        data_category="Персональные данные",
        city="г. Омск"
    )
    
    print("\n=== РЕЗУЛЬТАТ ГЕНЕРАЦИИ ===")
    print(f"Успех: {result['success']}")
    if result['success']:
        print(f"Файл: {result['file_path']}")
        print(f"Время: {result['context']['duration']} сек")
        print(f"Разделов: {result['context']['sections_generated']}")
        print(f"Стандарты: {result['context']['standards']}")
        
        # Проверка: ГОСТ 57580 должен быть исключён
        if "gost_57580" in result['context']['standards']:
            print("❌ ОШИБКА: ГОСТ 57580 не должен быть в списке для медицины!")
        else:
            print("✓ ГОСТ 57580 корректно исключён")
    else:
        print(f"Ошибка: {result.get('error')}")
    
    return result

if __name__ == "__main__":
    asyncio.run(test_medical_policy())