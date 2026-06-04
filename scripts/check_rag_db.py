# scripts/check_rag_db.py
from src.services.rag_service import RAGService

rag = RAGService()
stats = rag.get_statistics()
print(f"Документов в базе: {stats}")

# Тестовый поиск
results = rag.search_requirements(
    query="шифрование персональных данных",
    n_results=3
)
print(f"\nНайдено требований: {len(results)}")
for req in results:
    print(f"- {req['standard']}, п. {req['clause']}: {req['text'][:100]}...")