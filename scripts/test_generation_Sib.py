# scripts/test_generation_Sib.py
"""
Тестовый скрипт генерации документов
"""
import asyncio
import os
import sys
sys.path.append('.')
import logging
logging.getLogger("src.services.rag_service").setLevel(logging.DEBUG)

# 1. Принудительный офлайн-режим (модель уже скачана, сеть не нужна)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["SENTENCE_TRANSFORMERS_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# 2. "Агрессивная" очистка проблемных прокси до инициализации httpx
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
    val = os.environ.get(var)
    if val and not val.startswith(('http://', 'https://', 'socks5://')):
        os.environ[var] = ''  # Убираем socks4 и другие неподдерживаемые схемы

from src.agents.orchestrator import DocumentOrchestrator

async def test_education_policy():
    """Генерация политики для образовательной организации (СИБАДИ)"""
    
    orchestrator = DocumentOrchestrator(llm_config={
        "base_url": "http://localhost:11434",
        "policy_model": "gemma4",
        "critic_min_score": 0.7,
        "output_dir": "storage/test_output"
    })

    # Тест для СИБАДИ (образовательная организация — оператор ПДн)
    result = await orchestrator.generate_document(
        doc_type="policy",
        standards=[
            "152fz",              # ✓ Должен остаться (базовый)
            "fstek_21",           # ✓ Должен остаться (ПДн в ИС)
            "gost_57580",         # ✗ Должен быть исключён! (для банков)
            "fstek_239",          # ✗ Должен быть исключён! (для КИИ)
        ],
        title="Политика информационной безопасности",
        organization="СИБИРСКИЙ ГОСУДАРСТВЕННЫЙ АВТОМОБИЛЬНО-ДОРОЖНЫЙ УНИВЕРСИТЕТ",
        object_type="Информационная система персональных данных",
        data_category="Персональные данные обучающихся и сотрудников",
        city="г. Омск"
    )
    
    print("\n" + "="*60)
    print("=== РЕЗУЛЬТАТ ГЕНЕРАЦИИ: СИБАДИ ===")
    print("="*60)
    print(f"Успех: {result['success']}")
    
    if result['success']:
        print(f"Файл: {result['file_path']}")
        print(f"Время: {result['context']['duration']:.1f} сек")
        print(f"Разделов: {result['context']['sections_generated']}")
        print(f"Стандарты: {result['context']['standards']}")
        
        # Проверка фильтрации стандартов для образования
        standards = result['context']['standards']
        
        print("\nВАЛИДАЦИЯ СТАНДАРТОВ:")
        
        # ✓ Должны присутствовать
        if "152fz" in standards:
            print("   ✓ 152-ФЗ: присутствует (обязательный)")
        else:
            print("   152-ФЗ: ОТСУТСТВУЕТ (критическая ошибка!)")
            
        if "fstek_21" in standards:
            print("   ✓ ФСТЭК №21: присутствует (ПДн в ИС)")
        else:
            print("   ФСТЭК №21: ОТСУТСТВУЕТ")
            
        # ✗ Должны отсутствовать
        if "gost_57580" not in standards:
            print("   ✓ ГОСТ Р 57580: корректно исключён (для банков)")
        else:
            print("   ГОСТ Р 57580: НЕ ИСКЛЮЧЁН (ошибка классификации!)")
            
        if "fstek_239" not in standards:
            print("   ✓ ФСТЭК №239: корректно исключён (для КИИ)")
        else:
            print("   ФСТЭК №239: НЕ ИСКЛЮЧЁН (СИБАДИ не субъект КИИ)")
            
        # Информация об отрасли
        if 'industry_info' in result:
            info = result['industry_info']
            print(f"\nОТРАСЛЕВОЙ ПРОФИЛЬ:")
            print(f"   Режим: {info['regime']}")
            print(f"   Название: {info['profile_name']}")
            print(f"   Ключевые термины: {', '.join(info['key_terms'][:5])}")
        
    else:
        print(f"Ошибка: {result.get('error')}")
        if 'context' in result:
            print(f"   Контекст: {result['context']}")
    
    print("="*60 + "\n")
    
    return result

if __name__ == "__main__":
    print("Запуск генерации для СИБАДИ...")
    try:
        result = asyncio.run(test_education_policy())
        sys.exit(0 if result['success'] else 1)
    except KeyboardInterrupt:
        print("\n⚠ Прервано пользователем")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)