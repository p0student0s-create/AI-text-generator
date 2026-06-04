# scripts/rag_service.py
"""
RAG-сервис для поиска требований в нормативных документах
с поддержкой отраслевых профилей и градуированного поиска примеров
"""
import logging
import re
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from src.services.industry_classifier import RegulatoryProfile, RegulatoryRegime

from src.database import get_chroma_collection, get_embedding_model

logger = logging.getLogger(__name__)


@dataclass
class RequirementItem:
    """Структурированное требование с метаданными"""
    text: str
    standard_type: str
    clause_number: str
    clause_title: str
    page: Optional[int] = None
    relevance_score: float = 0.0
    source_file: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "standard": self.standard_type,
            "clause": self.clause_number,
            "clause_title": self.clause_title,
            "page": self.page,
            "relevance_score": self.relevance_score,
            "source": self.source_file,
            "citation": self.format_citation()
        }
    
    def format_citation(self) -> str:
        if self.clause_number:
            return f"{self.standard_type}, п. {self.clause_number}"
        return self.standard_type


def _count_all_sections(sections: List[Dict], level: int = 1) -> int:
    """Рекурсивно подсчитывает общее количество разделов в структуре"""
    count = len(sections)
    for section in sections:
        children = section.get("children", [])
        if children:
            count += _count_all_sections(children, level + 1)
    return count


class RAGService:
    """Сервис для поиска требований в нормативных документах"""
    
    CLAUSE_PATTERNS = [
        r'(?:п\.?\s*|пункт\s*)?(\d+(?:\.\d+){1,3})',
        r'(?:раздел\s*)(\d+(?:\.\d+)?)',
        r'(?:ст\.?\s*|статья\s*)(\d+(?:\.\d+)?)',
        r'([A-Z]?\d+(?:\.\d+){1,2})(?:\s+[-–—])',
    ]
    
    STANDARDS_REGISTRY = {
        "152fz": {
            "name": "152-ФЗ",
            "date": "27.07.2006",
            "full_name": "О персональных данных",
            "applicable_to": ["все операторы пдн"],
            "always_applicable": True,
            "priority": 0
        },
        "fstek_21": {
            "name": "Приказ ФСТЭК России №21",
            "date": "18.02.2013",
            "full_name": "Об утверждении Состава и содержания организационных и технических мер по защите ПДн",
            "applicable_to": ["пдн", "испдн", "персональные данные", "оператор пдн"],
            "recommended_for": ["буз", "миац", "медицин", "здравоох", "больница"],
            "priority": 1
        },
        "fstek_239": {
            "name": "Приказ ФСТЭК России №239",
            "date": "25.12.2017",
            "full_name": "Об утверждении Требований по обеспечению безопасности значимых объектов КИИ",
            "applicable_to": ["кии", "критическая информационная инфраструктура", "значимые объекты"],
            "NOT_applicable_to": ["медицин", "буз", "миац", "здравоох", "больница", "клиника"],
            "priority": 2
        },
        "gost_57580": {
            "name": "ГОСТ Р 57580-2017",
            "full_name": "Информационная безопасность организаций. Общие требования",
            "applicable_to": ["банк", "банки", "финанс", "нко", "кредит"],
            "NOT_applicable_to": ["медицин", "буз", "миац", "здравоох", "больница"],
            "priority": 3
        },
        "minzdrav_956n": {
            "name": "Приказ Минздрава России №956н",
            "date": "15.12.2020",
            "full_name": "Об утверждении Требований к организации и выполнению работ по защите ПДн в сфере здравоохранения",
            "applicable_to": ["здравоох", "буз", "миац", "медицин", "больница", "клиника"],
            "priority": 1
        },
        "187fz": {
            "name": "187-ФЗ",
            "date": "26.07.2017",
            "full_name": "О безопасности критической информационной инфраструктуры РФ",
            "applicable_to": ["кии", "критическая информационная инфраструктура"],
            "priority": 2
        },
        "149fz": {
            "name": "149-ФЗ",
            "date": "27.07.2006",
            "full_name": "Об информации, информационных технологиях и о защите информации",
            "applicable_to": ["гис", "государственная информационная система"],
            "priority": 2
        },
        "fstek_17": {
            "name": "Приказ ФСТЭК России №17",
            "date": "11.02.2013",
            "full_name": "Об утверждении Требований о защите информации, не составляющей государственную тайну, содержащейся в государственных информационных системах",
            "applicable_to": ["гис", "государственная информационная система"],
            "priority": 2
        },
            "minobrnauki_orders": {
            "name": "Приказы Минобрнауки России",
            "full_name": "Отраслевые требования к защите информации в образовательных организациях",
            "applicable_to": ["образован", "университет", "вуз", "институт", "колледж", "школ", "лицей"],
            "recommended_for": ["сибгу", "сибади", "омгупс", "транспорт", "путей сообщения"],
            "priority": 3
        }
    }

    def __init__(self):
        self.collection = get_chroma_collection()
        self.embed_model = get_embedding_model()
    
    def _is_organization_matches(self, org_lower: str, keywords: List[str]) -> bool:
        return any(kw.lower() in org_lower for kw in keywords)
    
    def _normalize_standard_key(self, standard: str) -> str:
        return standard.lower().replace("-", "_").replace(".", "_").replace(" ", "_")
    
    def get_applicable_standards(
        self, 
        organization_type: str, 
        doc_type: Optional[str] = None,
        requested_standards: Optional[List[str]] = None,
        regulatory_profile: Optional['RegulatoryProfile'] = None
    ) -> List[str]:
        org_lower = organization_type.lower()
        
        if regulatory_profile is not None:
            from src.services.industry_classifier import RegulatoryClassifier
            classifier = RegulatoryClassifier()
            return classifier.get_applicable_standards(regulatory_profile)
        
        standards_to_check = requested_standards if requested_standards else list(self.STANDARDS_REGISTRY.keys())
        applicable = []
        
        for std_key in standards_to_check:
            if std_key not in self.STANDARDS_REGISTRY:
                continue
            std_info = self.STANDARDS_REGISTRY[std_key]
            
            if "NOT_applicable_to" in std_info:
                if self._is_organization_matches(org_lower, std_info["NOT_applicable_to"]):
                    continue
            
            if std_info.get("always_applicable"):
                applicable.append(std_key)
                continue
            
            is_applicable = False
            if "applicable_to" in std_info:
                if self._is_organization_matches(org_lower, std_info["applicable_to"]):
                    is_applicable = True
            if not is_applicable and "recommended_for" in std_info:
                if self._is_organization_matches(org_lower, std_info["recommended_for"]):
                    is_applicable = True
            
            if ("applicable_to" in std_info or "recommended_for" in std_info) and not is_applicable:
                continue
            
            applicable.append(std_key)
        
        if self._is_organization_matches(org_lower, ["буз", "миац", "медицин", "здравоох", "больница"]):
            for mandatory in ["152fz", "fstek_21"]:
                if mandatory not in applicable:
                    applicable.append(mandatory)
            applicable = [s for s in applicable if s != "gost_57580"]
        
        applicable.sort(key=lambda x: self.STANDARDS_REGISTRY.get(x, {}).get("priority", 99))
        return applicable

    def search_example_structures(
        self,
        doc_type: str,
        industry: Optional[str] = None,
        n_results: int = 5,
        min_relevance: float = 0.4,
        regulatory_profile: Optional['RegulatoryProfile'] = None
    ) -> List[Dict[str, Any]]:
        """
        Градуированный поиск примеров документов по трём уровням приоритета.
        """
        start_time = time.time()
        
        query_parts = [f"Пример документа типа {doc_type}"]
        if industry:
            query_parts.append(f"отрасль {industry}")
        if regulatory_profile:
            query_parts.extend(regulatory_profile.key_terms[:5])
            query_parts.append(f"профиль {regulatory_profile.regime.value}")
        query_parts.append("структура разделов иерархия")
        query = " ".join(query_parts)
        
        query_vector = self.embed_model.encode(query).tolist()
        
        # Уровень 1: Точный поиск с фильтрами
        examples = self._search_with_filters(
            query_vector=query_vector,
            doc_type=doc_type,
            industry=industry,
            regulatory_profile=regulatory_profile,
            n_results=n_results * 2,
            min_relevance=min_relevance
        )
        
        if examples:
            return self._post_process_examples(examples[:n_results], doc_type, regulatory_profile)
        
        # Уровень 2: Поиск только по doc_type
        examples = self._search_with_filters(
            query_vector=query_vector,
            doc_type=doc_type,
            industry=None,
            regulatory_profile=None,
            n_results=n_results * 3,
            min_relevance=max(0.0, min_relevance - 0.1)
        )
        
        if examples:
            return self._post_process_examples(examples[:n_results], doc_type, regulatory_profile)
        
        # Уровень 3: Поиск без фильтров (fallback)
        examples = self._search_all_examples(
            doc_type=doc_type,
            n_results=n_results * 4,
            min_relevance=max(0.0, min_relevance - 0.2)
        )
        
        if examples:
            return self._post_process_examples(examples[:n_results], doc_type, regulatory_profile)
        
        return []
    
    def _search_with_filters(
        self,
        query_vector: List[float],
        doc_type: str,
        industry: Optional[str],
        regulatory_profile: Optional['RegulatoryProfile'],
        n_results: int,
        min_relevance: float
    ) -> List[Dict[str, Any]]:
        where_filter: Dict[str, Any] = {
            "$and": [
                {"doc_type": {"$eq": "example"}},
                {"has_structure": {"$eq": True}}
            ]
        }
        
        if industry:
            where_filter["$and"].append({"industry": {"$eq": industry.lower()}})
        
        if regulatory_profile:
            where_filter["$and"].append({
                "regime": {"$eq": regulatory_profile.regime.value}
            })
        
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        return self._parse_search_results(results, min_relevance)
    
    def _search_all_examples(
        self,
        doc_type: str,
        n_results: int,
        min_relevance: float
    ) -> List[Dict[str, Any]]:
        where_filter = {
            "$and": [
                {"doc_type": {"$eq": "example"}},
                {"has_structure": {"$eq": True}}
            ]
        }
        
        results = self.collection.query(
            query_embeddings=[self.embed_model.encode(f"Пример {doc_type} структура").tolist()],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        return self._parse_search_results(results, min_relevance)
    
    def _parse_search_results(
        self,
        results: Dict[str, Any],
        min_relevance: float,
        target_industry: Optional[str] = None,
        target_regime: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        examples = []
        
        if not results["documents"] or not results["documents"][0]:
            return []
        
        docs = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results.get("distances", [[0.5] * len(docs)])[0]
        
        seen_sources = set()
        
        for idx, (doc, meta, dist) in enumerate(zip(docs, metadatas, distances)):
            base_relevance = max(0.0, min(1.0, 1.0 - dist))
            
            if base_relevance < min_relevance:
                continue
            
            source = meta.get("source_file", "unknown")
            if source in seen_sources:
                continue
            seen_sources.add(source)
            
            score_components = {
                "base_relevance": base_relevance * 0.4,
                "industry_match": 0.0,
                "regime_match": 0.0,
                "structure_completeness": 0.0,
                "doc_type_match": 0.0
            }
            
            example_industry = meta.get("industry", "").lower()
            if target_industry and example_industry:
                if target_industry.lower() == example_industry:
                    score_components["industry_match"] = 0.25
                elif any(kw in example_industry for kw in target_industry.lower().split()):
                    score_components["industry_match"] = 0.15
            elif not target_industry:
                score_components["industry_match"] = 0.1
            
            example_regime = meta.get("regime", "").lower()
            if target_regime and example_regime:
                if target_regime.lower() == example_regime:
                    score_components["regime_match"] = 0.15
            elif not target_regime:
                score_components["regime_match"] = 0.05
            
            structure = None
            if meta.get("structure_json"):
                try:
                    structure = json.loads(meta["structure_json"])
                    sections_count = _count_all_sections(structure.get("root", [])) if structure else 0
                    if 8 <= sections_count <= 15:
                        score_components["structure_completeness"] = 0.15
                    elif 5 <= sections_count < 8 or 15 < sections_count <= 20:
                        score_components["structure_completeness"] = 0.10
                    else:
                        score_components["structure_completeness"] = 0.05
                except (json.JSONDecodeError, TypeError):
                    continue
            
            if not structure or not structure.get("root"):
                continue
            
            example_doc_type = meta.get("doc_type", "")
            if example_doc_type == "example":
                score_components["doc_type_match"] = 0.05
            
            final_score = sum(score_components.values())
            
            if final_score < min_relevance:
                continue
            
            examples.append({
                "source": source,
                "doc_type": meta.get("doc_type", "example"),
                "industry": meta.get("industry", ""),
                "regime": meta.get("regime", ""),
                "structure": structure,
                "relevance_score": round(base_relevance, 3),
                "final_score": round(final_score, 3),
                "organization": meta.get("organization", ""),
                "preview": doc[:300] + "..." if doc else "",
                "sections_count": _count_all_sections(structure.get("root", []))
            })
        
        examples.sort(key=lambda x: x["final_score"], reverse=True)
        return examples
    
    def _post_process_examples(
        self,
        examples: List[Dict[str, Any]],
        doc_type: str,
        regulatory_profile: Optional['RegulatoryProfile']
    ) -> List[Dict[str, Any]]:
        processed = []
        for ex in examples:
            enriched_structure = self._validate_and_enrich_structure(
                ex["structure"],
                doc_type,
                regulatory_profile
            )
            processed.append({
                **ex,
                "structure": enriched_structure,
                "validated": True
            })
        return processed
    
    def _validate_and_enrich_structure(
        self,
        structure: Dict,
        doc_type: str,
        regulatory_profile: Optional['RegulatoryProfile']
    ) -> Dict:
        if not structure or not structure.get("root"):
            return structure
        
        root = structure["root"]
        min_sections = {"policy": 8, "regulation": 5, "instruction": 6}.get(doc_type, 4)
        if len(root) < min_sections:
            root = self._add_missing_sections(root, doc_type)
        
        if regulatory_profile:
            root = self._adapt_to_industry(root, regulatory_profile)
        
        structure["root"] = root
        structure["validated"] = True
        structure["sections_count"] = len(root)
        return structure
    
    def _add_missing_sections(self, sections: List[Dict], doc_type: str) -> List[Dict]:
        mandatory = {
            "policy": [
                {"title": "Общие положения", "level": 1},
                {"title": "Нормативные ссылки", "level": 1},
                {"title": "Термины и определения", "level": 1},
                {"title": "Требования к защите", "level": 1},
                {"title": "Ответственность", "level": 1},
                {"title": "Контроль и аудит", "level": 1},
                {"title": "Заключительные положения", "level": 1},
            ],
            "regulation": [
                {"title": "Общие положения", "level": 1},
                {"title": "Процедуры и процессы", "level": 1},
                {"title": "Роли и ответственность", "level": 1},
                {"title": "Контроль исполнения", "level": 1},
            ],
            "instruction": [
                {"title": "Область применения", "level": 1},
                {"title": "Подготовка к работе", "level": 1},
                {"title": "Порядок выполнения", "level": 1},
                {"title": "Требования безопасности", "level": 1},
            ]
        }.get(doc_type, [])
        
        existing_titles = [s.get("title", "").lower() for s in sections]
        
        for req in mandatory:
            if not any(req["title"].lower() in title for title in existing_titles):
                new_section = {
                    "number": f"{len(sections) + 1}",
                    "title": req["title"],
                    "level": req["level"],
                    "children": [],
                    "content_preview": f"Раздел '{req['title']}' добавлен автоматически"
                }
                sections.append(new_section)
        
        return sections
    
    def _adapt_to_industry(
        self,
        sections: List[Dict],
        profile: 'RegulatoryProfile'
    ) -> List[Dict]:
        has_industry_section = any(
            any(term.lower() in section.get("title", "").lower() for term in profile.key_terms)
            for section in sections
        )
        
        if not has_industry_section and profile.typical_systems:
            industry_section = {
                "number": f"{len(sections) + 1}",
                "title": f"Особенности защиты в {profile.name}",
                "level": 1,
                "children": [
                    {
                        "number": f"{len(sections) + 1}.1",
                        "title": f"Защита {profile.protected_data[0] if profile.protected_data else 'информации'}",
                        "level": 2
                    },
                    {
                        "number": f"{len(sections) + 1}.2",
                        "title": f"Работа с {profile.typical_systems[0] if profile.typical_systems else 'информационными системами'}",
                        "level": 2
                    }
                ],
                "content_preview": f"Специфика {profile.name}"
            }
            sections.append(industry_section)
        
        return sections

    def get_structure_template(
        self,
        doc_type: str,
        organization_type: str = "",
        standards: Optional[List[str]] = None,
        industry: Optional[str] = None,
        use_examples: bool = True,
        regulatory_profile: Optional['RegulatoryProfile'] = None
    ) -> Dict[str, Any]:
        applicable_standards = self.get_applicable_standards(
            organization_type=organization_type,
            doc_type=doc_type,
            requested_standards=standards,
            regulatory_profile=regulatory_profile
        )
        
        result = {
            "hierarchy": None,
            "source": "default",
            "standards": applicable_standards,
            "industry": industry,
            "regulatory_profile": regulatory_profile.regime.value if regulatory_profile else None,
            "example_info": None
        }
        
        if use_examples:
            examples = self.search_example_structures(
                doc_type, 
                industry=industry, 
                n_results=1,
                regulatory_profile=regulatory_profile
            )
            if examples:
                example = examples[0]
                result.update({
                    "hierarchy": example["structure"].get("root", []),
                    "source": "example",
                    "example_info": {
                        "file": example["source"],
                        "organization": example.get("organization"),
                        "relevance_score": example.get("relevance_score")
                    }
                })
        
        return result

    def search_requirements(
        self, 
        query: str, 
        n_results: int = 10,
        standards: Optional[List[str]] = None,
        min_relevance: float = 0.3,
        regulatory_profile: Optional['RegulatoryProfile'] = None
    ) -> List[Dict[str, Any]]:
        query_vector = self.embed_model.encode(query).tolist()
        
        where_filter: Dict[str, Any] = {
            "$and": [
                {"doc_type": {"$eq": "requirement"}},
            ]
        }
        
        if regulatory_profile:
            from src.services.industry_classifier import RegulatoryClassifier
            classifier = RegulatoryClassifier()
            profile_standards = classifier.get_applicable_standards(regulatory_profile)
            if profile_standards:
                normalized = [self._normalize_standard_key(s) for s in profile_standards]
                where_filter["$and"].append({
                    "standard_key": {"$in": normalized}
                })
        elif standards:
            normalized = [self._normalize_standard_key(s) for s in standards]
            where_filter["$and"].append({
                "standard_key": {"$in": normalized}
            })
        
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        requirements = []
        if not results["documents"] or not results["documents"][0]:
            return []
        
        docs = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results.get("distances", [[0.5] * len(docs)])[0]
        
        for doc, meta, dist in zip(docs, metadatas, distances):
            relevance = max(0.0, min(1.0, 1.0 - dist))
            if relevance < min_relevance:
                continue
            
            clause_number = self._extract_clause_number(doc, meta)
            clause_title = self._extract_clause_title(doc)
            
            req = RequirementItem(
                text=doc.strip(),
                standard_type=meta.get("standard_type", "unknown"),
                clause_number=clause_number,
                clause_title=clause_title,
                page=meta.get("page"),
                relevance_score=round(relevance, 3),
                source_file=meta.get("source_file")
            )
            requirements.append(req.to_dict())
        
        requirements.sort(key=lambda x: x["relevance_score"], reverse=True)
        return requirements[:n_results]
    
    def _extract_clause_number(self, text: str, metadata: Dict) -> str:
        if metadata.get("clause_number"):
            return str(metadata["clause_number"])
        
        text_preview = text[:200].strip()
        for pattern in self.CLAUSE_PATTERNS:
            match = re.search(pattern, text_preview, re.IGNORECASE)
            if match:
                return match.group(1)
        
        if metadata.get("section_number"):
            return str(metadata["section_number"])
        
        return ""
    
    def _extract_clause_title(self, text: str) -> str:
        lines = text.strip().split('\n')
        if not lines:
            return ""
        
        first_line = lines[0].strip()
        title = re.sub(r'^\d+(?:\.\d+)*[\s:—-]+', '', first_line)
        return title[:150].strip()
    
    def search_with_context(
        self,
        query: str,
        standards: Optional[List[str]] = None,
        context_size: int = 3,
        regulatory_profile: Optional['RegulatoryProfile'] = None
    ) -> Dict[str, Any]:
        requirements = self.search_requirements(
            query, 
            n_results=context_size * 3, 
            standards=standards,
            regulatory_profile=regulatory_profile
        )
        standards_found = list(set(req["standard"] for req in requirements))
        
        return {
            "requirements": requirements[:context_size],
            "summary": f"Найдено {len(requirements)} требований из {len(standards_found)} стандартов",
            "standards_found": standards_found,
            "total_found": len(requirements)
        }

    def add_documents(
        self, 
        documents: List[Dict[str, Any]], 
        standard_type: str,
        source_file: Optional[str] = None,
        doc_type: str = "requirement"
    ) -> int:
        if not documents:
            return 0
        
        chunks = []
        embeddings = []
        ids = []
        metadatas = []
        
        for i, doc in enumerate(documents):
            text = doc.get("text", "").strip()
            if not text:
                continue
            
            chunks.append(text)
            embeddings.append(self.embed_model.encode(text).tolist())
            
            doc_id = f"{standard_type}_{i:04d}"
            if source_file:
                doc_id = f"{standard_type}_{Path(source_file).stem}_{i:04d}"
            ids.append(doc_id)
            
            standard_key = self._normalize_standard_key(standard_type)
            metadata = {
                "standard_type": str(standard_type),
                "section_number": str(doc.get("section") or ""),
                "clause_number": str(doc.get("clause") or ""),
                "page": int(doc.get("page")) if doc.get("page") is not None else 0,
                "source_file": str(source_file or ""),
                "chunk_index": i,
                "indexed_at": datetime.now().isoformat(),
                "standard_key": standard_key,
                "doc_type": doc.get("doc_type", doc_type),
            }
            
            metadata = {
                k: v for k, v in metadata.items() 
                if isinstance(v, (str, int, float, bool))
            }
            
            metadatas.append(metadata)
        
        if chunks:
            self.collection.add(
                documents=chunks,
                embeddings=embeddings,
                ids=ids,
                metadatas=metadatas
            )
            return len(chunks)
        
        return 0

    def add_example_structure(
        self,
        structure: Dict[str, Any],
        source_file: str,
        doc_type: str,
        organization: str = "",
        industry: str = "",
        regime: Optional[str] = None
    ) -> bool:
        try:
            text = json.dumps(structure, ensure_ascii=False, indent=2)
            query_vector = self.embed_model.encode(text).tolist()
            
            doc_id = f"example_{Path(source_file).stem}"
            
            metadata = {
                "doc_type": "example",
                "source_file": str(source_file),
                "structure_json": text,
                "has_structure": True,
                "organization": str(organization),
                "industry": str(industry).lower(),
                "regime": str(regime) if regime else "",
                "indexed_at": datetime.now().isoformat(),
            }
            
            metadata = {
                k: v for k, v in metadata.items() 
                if isinstance(v, (str, int, float, bool))
            }
            
            self.collection.add(
                documents=[text],
                embeddings=[query_vector],
                ids=[doc_id],
                metadatas=[metadata]
            )
            return True
            
        except Exception as e:
            return False

    def add_documents_with_metadata(
        self,
        chunks: List[str],
        standard_type: str,
        source_file: str,
        extra_metadata: Optional[Dict] = None
    ) -> int:
        if not chunks:
            return 0
        
        embeddings = [self.embed_model.encode(chunk).tolist() for chunk in chunks]
        ids = [f"{standard_type}_{Path(source_file).stem}_{i:04d}" for i in range(len(chunks))]
        
        metadatas = []
        for i in range(len(chunks)):
            meta = {
                "standard_type": str(standard_type),
                "source_file": str(source_file),
                "chunk_index": i,
                "indexed_at": datetime.now().isoformat(),
                "doc_type": "requirement",
                "standard_key": self._normalize_standard_key(standard_type),
                **(extra_metadata or {})
            }
            meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}
            metadatas.append(meta)
        
        self.collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=ids,
            metadatas=metadatas
        )
        return len(chunks)

    def get_statistics(self) -> Dict[str, Any]:
        try:
            count = self.collection.count()
            return {
                "total_documents": count,
                "collection_name": self.collection.name
            }
        except Exception:
            return {"error": "Failed to get statistics"}

    def clear_collection(self) -> bool:
        try:
            self.collection.delete(where={})
            return True
        except Exception:
            return False


def create_rag_service() -> RAGService:
    return RAGService()