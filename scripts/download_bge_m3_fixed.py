# scripts/download_bge_m3_fixed.py
"""
Скачивает модель BAAI/bge-m3 с полным отключением прокси.
Запускать при наличии интернета.
"""
import os
import sys
import subprocess

# === ШАГ 0: УБИВАЕМ ВСЕ ПРОКСИ ===
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'HTTPX_PROXY', 'REQUESTS_PROXY']:
    os.environ.pop(var, None)
    os.environ[var] = ''

# === ШАГ 1: Патч httpx ДО импорта библиотек ===
def _patch_httpx():
    try:
        import httpx
        orig_init = httpx.Client.__init__
        def patched_init(self, *args, **kwargs):
            kwargs['proxy'] = None
            kwargs['trust_env'] = False  # ← Игнорировать реестр/окружение
            return orig_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init
        print("✓ httpx пропатчен: trust_env=False")
    except Exception as e:
        print(f"⚠ Не удалось пропатчить httpx: {e}")

_patch_httpx()

# === ШАГ 2: Отключаем офлайн-режим ===
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["SENTENCE_TRANSFORMERS_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"

# === ШАГ 3: Скачивание модели ===
print("Загрузка модели BAAI/bge-m3...")
try:
    from huggingface_hub import snapshot_download
    from pathlib import Path
    
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    
    snapshot_download(
        repo_id="BAAI/bge-m3",
        cache_dir=str(cache_dir),
        local_dir_use_symlinks=False,
        resume_download=True,
        max_workers=4
    )
    print("✓ Модель успешно скачана!")
    
    # Проверка загрузки
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-m3", local_files_only=True)
    print(f"✓ Проверка: размер эмбеддинга = {model.get_sentence_embedding_dimension()}")
    
except Exception as e:
    print(f"✗ Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)