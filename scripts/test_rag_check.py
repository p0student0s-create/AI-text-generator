# test_rag_check.py
from src.services.rag_service import RAGService

rag = RAGService()

# Статистика
stats = rag.get_statistics()
print('📊 Общая статистика:', stats)

# 🔍 ПРОВЕРКА: сколько примеров со структурой в базе?
results = rag.collection.get(
    where={
        '$and': [
            {'doc_type': {'$eq': 'example'}},
            {'has_structure': {'$eq': True}}
        ]
    },
    include=['metadatas']
)

print(f'\n📋 Всего примеров со структурой: {len(results["metadatas"])}')

# Считаем политики
policy_count = 0
for m in results['metadatas']:
    if m.get('doc_type') == 'example' and m.get('has_structure'):
        source = m.get('source_file', 'unknown')
        fname = source.split('\\')[-1].split('/')[-1]
        if 'policy' in source.lower() or 'политик' in source.lower():
            policy_count += 1
            print(f'  ✓ Политика: {fname}')

print(f'\n🎯 Политик типа "policy": {policy_count}')

# 🔍 Тест поиска с увеличенным n_results
print('\n🔍 Тест поиска примеров (n_results=10):')
examples = rag.search_example_structures('policy', n_results=10)
print(f'   Найдено: {len(examples)} примеров')
for i, ex in enumerate(examples, 1):
    fname = ex['source'].split('\\')[-1].split('/')[-1]
    print(f'   {i}. {fname} (релевантность: {ex["relevance_score"]})')