# scripts/quick_test.py (исправленная версия)
from src.services.rag_service import RAGService

rag = RAGService()

print("=== ТЕСТ ФИЛЬТРАЦИИ ===\n")

# Тест 1: Медицина
med = rag.get_applicable_standards(
    "БУЗОО МИАЦ", 
    requested_standards=["152fz", "fstek_21", "gost_57580"]
)
print(f"1. Медицина (БУЗОО МИАЦ): {med}")
assert "152fz" in med, "❌ 152-ФЗ должен быть"
assert "fstek_21" in med, "❌ ФСТЭК 21 должен быть для медицины"
assert "gost_57580" not in med, "❌ ГОСТ 57580 НЕ должен быть для медицины"
print("   ✓ Медицина: тест пройден")

# Тест 2: Банк (разные варианты написания)
for org_name in ["АО Банк", "Банк", "ООО Финансы", "Кредитная организация"]:
    bank = rag.get_applicable_standards(
        org_name, 
        requested_standards=["152fz", "gost_57580"]
    )
    print(f"2. {org_name}: {bank}")
    assert "gost_57580" in bank, f"❌ ГОСТ 57580 должен быть для {org_name}"
print("   ✓ Банки: тест пройден")

# Тест 3: Валидация даты ФСТЭК 239
validation = rag.validate_standard_reference(
    "fstek_239", 
    "Приказ ФСТЭК №239 от 03.12.2019"
)
print(f"\n3. Валидация даты ФСТЭК 239:")
print(f"   Валиден: {validation['valid']}")
print(f"   Ошибки: {validation['errors']}")
assert not validation['valid'], "❌ Неправильная дата должна быть отклонена"
assert "25.12.2017" in str(validation['suggestions']), "❌ Должно быть предложение исправить дату"
print("   ✓ Валидация: тест пройден")

print("\n✅ Все тесты пройдены!")