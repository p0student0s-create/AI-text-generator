# scripts/test_generation_VKR.py
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

# 3. Блокировка чтения .env, если он есть в проекте (опционально, но надёжно)
if os.path.exists('.env'):
    os.rename('.env', '.env.bak')

print("✓ Окружение пропатчено. Запуск генерации...")

from src.agents.orchestrator import DocumentOrchestrator

async def test_vkr_report():
    """Генерация отчета по ВКР для СибАДИ (Омск)"""
    
    orchestrator = DocumentOrchestrator(llm_config={
        "base_url": "http://localhost:11434",
        "vkr_model": "gemma4",
        "critic_min_score": 0.7,
        "output_dir": "storage/vkr_output",
        "template_dir": "storage/templates"
    })

    result = await orchestrator.generate_document(
        doc_type="vkr_report",
        standards=[
            "152fz",
            "fstek_21",
            "gost_57580",
            "iso_27001",
        ],
        title="Разработка AI-помощника для автоматизации создания организационно-технической документации по информационной безопасности",
        organization="Сибирский автомобильно-дорожный университет (СибАДИ)",
        object_type="Выпускная квалификационная работа",
        data_category="Научно-исследовательская работа",
        city="г. Омск",
        specialty="10.03.01 Информационная безопасность",
        degree="бакалавриат",
        faculty="Институт радиоэлектроники и информационных технологий – РТФ",
    )
    
    print("\n=== РЕЗУЛЬТАТ ГЕНЕРАЦИИ ВКР ===")
    print(f"Успех: {'✓' if result['success'] else '⚠'}")
    
    if result['success']:
        print(f"Файл: {result['file_path']}")
        print(f"Время: {result['context']['duration']:.1f} сек")
        print(f"Разделов: {result['context']['sections_generated']}")
        print(f"Стандарты: {result['context']['standards']}")
        
        if result['context'].get('compliance', {}).get('score', 0) >= 0.7:
            print("✓ Оценка соответствия: удовлетворительно")
        else:
            print("⚠ Оценка соответствия: ниже порога")
            
        profile = result.get('industry_info', {}).get('profile_name')
        if profile:
            print(f"✓ Отраслевой профиль: {profile}")
        else:
            print("⚠ Отраслевой профиль не определён")
    else:
        print(f"Ошибка: {result.get('error')}")
    
    return result

if __name__ == "__main__":
    print("Запуск генерации ВКР...")
    result = asyncio.run(test_vkr_report())
    sys.exit(0 if result['success'] else 1)