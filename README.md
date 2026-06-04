# AI Security Documentation Generator

> Прототип ИИ-помощника для автоматизированной генерации документации по информационной безопасности.

> ВКР-проект по разработке интеллектуальной системы формирования организационно-технической документации в соответствии с требованиями российских и международных стандартов ИБ.

---

## Overview

Система предназначена для автоматизированной разработки документации по информационной безопасности с использованием технологий Retrieval-Augmented Generation (RAG), графовых баз данных и локальных LLM.

Проект поддерживает генерацию документов с учётом требований:

* ГОСТ Р 57580.1-2017
* ГОСТ Р ИСО/МЭК 27001-2022
* Приказы ФСТЭК России №17, №21, №239
* Методические рекомендации Банка России

Система использует гибридный поиск:

* графовый поиск (Neo4j),
* векторный поиск (Milvus),
* семантическую генерацию через локальную LLM.

---

# Key Features

* Автоматическая генерация ИБ-документации
* Поддержка российских нормативных требований
* Гибридный поиск через LightRAG
* Граф связей между требованиями и документами
* Локальная работа LLM без внешних API
* Индексация нормативной документации
* Семантический поиск по базе знаний
* Расширяемая архитектура сервисов

---

# Tech Stack

| Layer            | Technology              |
| ---------------- | ----------------------- |
| Backend          | Python 3.10+            |
| RAG Framework    | LightRAG                |
| LLM              | Qwen2.5-14B-Instruct    |
| LLM Runtime      | Ollama                  |
| Graph Database   | Neo4j                   |
| Vector Database  | Milvus                  |
| Cache            | Redis                   |
| Containerization | Docker / Docker Compose |

---

# Architecture

```text
├── src/
│   ├── core/          # Ядро LightRAG (кастомизированное)
│   ├── domain/        # Предметная область ИБ
│   ├── services/      # Сервисы генерации документов
│   └── utils/         # Вспомогательные функции
│
├── data/
│   ├── raw/           # Исходные нормативные документы
│   ├── processed/     # Индексированные чанки и граф
│   └── output/        # Сгенерированные документы
│
├── notebooks/         # Эксперименты и исследования
├── tests/             # Тесты и валидация
│
└── docker-compose.yml
```

---

# Quick Start

## 1. Clone Repository

```bash
git clone https://github.com/your-username/ai-security-docs.git
cd ai-security-docs
```

---

## 2. Create Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Start Infrastructure

```bash
docker-compose up -d
```

Запускаются сервисы:

| Service | Description          |
| ------- | -------------------- |
| Neo4j   | Графовая база знаний |
| Milvus  | Векторное хранилище  |
| Redis   | Кеширование          |
| Ollama  | Локальная LLM        |

---

## 5. Run Prototype

```bash
python src/main.py
```

---

# Data Pipeline

```text
Нормативные документы
        ↓
Предобработка и чанкинг
        ↓
Векторизация embeddings
        ↓
Neo4j + Milvus indexing
        ↓
Hybrid Retrieval (Graph + Vector)
        ↓
LLM Generation
        ↓
Генерация документации
```

---

# Supported Standards

| Standard            | Description                              |
| ------------------- | ---------------------------------------- |
| ГОСТ Р 57580.1-2017 | Защита информации финансовых организаций |
| ISO/IEC 27001:2022  | Система менеджмента ИБ                   |
| ФСТЭК №17           | Защита государственных ИС                |
| ФСТЭК №21           | Защита персональных данных               |
| ФСТЭК №239          | Безопасность КИИ                         |

---

# Example Use Cases

* Генерация политики информационной безопасности
* Формирование модели угроз
* Подготовка регламентов ИБ
* Генерация организационно-распорядительных документов
* Проверка соответствия требованиям стандартов
* Подготовка документации для аудита

---

# Docker

## Start Services

```bash
docker-compose up -d
```

## Stop Services

```bash
docker-compose down
```

## Full Reset

```bash
docker-compose down -v
```

---

# Development

## Run Tests

```bash
pytest
```

## Run Linter

```bash
ruff check .
```

## Format Code

```bash
black .
```

---

# Future Improvements

* Web UI для работы с документами
* Multi-agent orchestration
* Поддержка дополнительных стандартов ИБ
* Интеграция с корпоративными DMS
* Fine-tuning специализированной модели
* Автоматическая валидация документации

---

# Research Goal

Цель ВКР — разработка интеллектуальной системы генерации документации по информационной безопасности с использованием технологий Retrieval-Augmented Generation и локальных языковых моделей.

---

# Author

**p0student0s**

---
