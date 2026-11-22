"""Treatment taxonomy used to map free-text treatments to policy categories.

Claims rarely use the same words as the policy title: a bill says "Root canal"
or "RCT" while the policy is titled "Dental". The taxonomy resolves treatments
to a canonical category and expands queries with synonyms so both lexical and
semantic retrieval find the right clause.

Category names intentionally match the demo policy ``policy_type`` values.
Organisations can extend the taxonomy at runtime with ``RAG_TAXONOMY_PATH``
pointing to a JSON file of ``{"Category": ["synonym", ...]}``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rag.services.text_processing import GENERIC_POLICY_TERMS, STOPWORDS, contains_phrase

logger = logging.getLogger(__name__)

DEFAULT_TAXONOMY: dict[str, tuple[str, ...]] = {
    "Dental": (
        "dental", "dentist", "tooth", "teeth", "root canal", "rct", "filling", "extraction", "scaling",
        "crown", "denture", "orthodontic", "braces", "gum", "periodontal", "wisdom tooth", "oral surgery",
    ),
    "Vision": (
        "vision", "eye examination", "eye exam", "eye test", "spectacles", "glasses", "contact lens", "lens",
        "eyewear", "sunglasses", "frames", "eyeglasses",
        "optical", "optometrist", "ophthalmology", "ophthalmic", "eye",
    ),
    "Opd": (
        "opd", "outpatient", "out-patient", "consultation", "general physician", "doctor visit", "gp visit",
        "clinic visit", "fever", "cold", "flu",
    ),
    "Hospitalization": (
        "hospitalization", "hospitalisation", "in-patient", "inpatient", "admission", "admitted", "surgery",
        "surgical", "operation", "icu", "ward", "room rent", "discharge", "appendectomy", "cataract", "cataract surgery",
        "eye surgery", "angioplasty",
    ),
    "Maternity": (
        "maternity", "pregnancy", "prenatal", "antenatal", "postnatal", "delivery", "childbirth", "c-section",
        "caesarean", "cesarean", "obstetric",
    ),
    "Preventive": ("preventive", "health checkup", "health check-up", "annual checkup", "screening package", "master checkup"),
    "Diagnostics": (
        "diagnostic", "diagnostics", "mri", "ct scan", "ultrasound", "x-ray", "xray", "imaging", "scan",
        "blood test", "lab test", "laboratory", "pathology", "urine test", "biopsy", "ecg", "echo",
    ),
    "Physiotherapy": ("physiotherapy", "physio", "physical therapy", "physiotherapist"),
    "Mental Wellness": (
        "mental health", "mental wellness", "psychiatrist", "psychologist", "counselling", "counseling",
        "therapy session", "psychotherapy", "depression", "anxiety",
    ),
    "Pharmacy": ("pharmacy", "medicine", "medicines", "drug", "drugs", "prescription medicine", "chemist", "tablet"),
    "Emergency": ("emergency", "emergency room", "casualty", "er visit", "ambulance"),
    "Accident": ("accident", "accidental", "injury", "fracture", "trauma", "road traffic"),
    "Chronic Care": ("chronic", "chronic disease", "hypertension", "asthma", "copd", "thyroid", "arthritis"),
    "Diabetes": ("diabetes", "diabetic", "insulin", "hba1c", "glucose", "blood sugar"),
    "Cardiac": ("cardiac", "cardiology", "cardiologist", "heart", "angiography", "stent", "bypass"),
    "Orthopedic": ("orthopedic", "orthopaedic", "orthopedics", "bone", "joint", "knee", "spine", "cast", "ligament"),
    "Dermatology": ("dermatology", "dermatologist", "skin", "eczema", "psoriasis", "acne", "rash"),
    "Ent": ("ent", "ear", "nose", "throat", "sinus", "tonsil", "hearing", "audiometry"),
    "Women Wellness": ("women wellness", "gynecology", "gynaecology", "gynecologist", "pap smear", "mammogram"),
    "Pediatric": ("pediatric", "paediatric", "pediatrician", "child", "children", "infant", "vaccination", "immunization"),
    "Senior Care": ("senior", "senior citizen", "geriatric", "elderly", "parent"),
    "Home Healthcare": ("home healthcare", "home nursing", "home care", "nurse at home", "home visit"),
    "Rehabilitation": ("rehabilitation", "rehab", "occupational therapy", "speech therapy"),
    "Wellness": ("wellness", "wellness program", "fitness", "nutrition", "dietician", "yoga"),
}

# Categories that are broad umbrellas. When a treatment matches both an
# umbrella and a specific category, the specific one wins.
_UMBRELLA_CATEGORIES = {"Opd", "Wellness", "Hospitalization"}


@dataclass(frozen=True, slots=True)
class CategoryMatch:
    category: str
    score: float
    matched_terms: tuple[str, ...]


def normalize_policy_type(value: str | None) -> str | None:
    """Policy types are stored title-cased at ingestion; keep lookups consistent with that."""
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned.title() if cleaned else None


class TreatmentTaxonomy:
    def __init__(self, categories: dict[str, tuple[str, ...]] | None = None) -> None:
        source = categories or DEFAULT_TAXONOMY
        self.categories: dict[str, tuple[str, ...]] = {}
        for name, synonyms in source.items():
            canonical = normalize_policy_type(name) or name
            terms = {canonical.lower(), *[synonym.lower().strip() for synonym in synonyms if synonym.strip()]}
            self.categories[canonical] = tuple(sorted(terms, key=len, reverse=True))

    @classmethod
    def from_file(cls, path: str | Path) -> "TreatmentTaxonomy":
        merged = {name: tuple(values) for name, values in DEFAULT_TAXONOMY.items()}
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for name, synonyms in data.items():
            existing = merged.get(name, ())
            merged[name] = tuple(dict.fromkeys([*existing, *[str(item) for item in synonyms]]))
        return cls(merged)

    def match(self, text: str | None, limit: int = 3) -> list[CategoryMatch]:
        if not text or not text.strip():
            return []
        matches: list[CategoryMatch] = []
        for category, terms in self.categories.items():
            hits = tuple(term for term in terms if contains_phrase(text, term))
            if not hits:
                continue
            # Longer, more specific phrases score higher than single generic words.
            score = sum(1.0 + 0.5 * (len(term.split()) - 1) for term in hits)
            if category.lower() in hits:
                score += 1.0
            if category in _UMBRELLA_CATEGORIES:
                score *= 0.8
            matches.append(CategoryMatch(category=category, score=score, matched_terms=hits))
        matches.sort(key=lambda item: (item.score, len(item.matched_terms)), reverse=True)
        return matches[:limit]

    def resolve(self, text: str | None) -> str | None:
        matches = self.match(text, limit=1)
        return matches[0].category if matches else None

    def synonyms(self, category: str | None) -> tuple[str, ...]:
        if not category:
            return ()
        return self.categories.get(normalize_policy_type(category) or category, ())

    def expand(self, treatment: str | None, max_terms: int = 40) -> list[str]:
        """Query expansion: the treatment itself plus the most specific synonyms of its category."""
        if not treatment:
            return []
        terms = [treatment.strip()]
        category = self.resolve(treatment)
        if category:
            terms.append(category)
            terms.extend(self.synonyms(category))
        else:
            # Unknown treatment: fall back to its meaningful words so partial matches still count.
            terms.extend(
                word for word in re.findall(r"[a-z][a-z-]{3,}", treatment.lower())
                if word not in STOPWORDS and word not in GENERIC_POLICY_TERMS
            )
        return list(dict.fromkeys(term for term in terms if term))[:max_terms]

    def other_category_terms(self, category: str | None) -> set[str]:
        """Distinctive terms that belong to categories other than ``category``."""
        own = set(self.synonyms(category))
        others: set[str] = set()
        for name, terms in self.categories.items():
            if name == category:
                continue
            others.update(term for term in terms if term not in own)
        return others


@lru_cache(maxsize=1)
def get_taxonomy() -> TreatmentTaxonomy:
    path = os.getenv("RAG_TAXONOMY_PATH")
    if path:
        try:
            return TreatmentTaxonomy.from_file(path)
        except (OSError, ValueError) as exc:
            logger.warning("Could not load taxonomy from %s (%s); using defaults", path, exc)
    return TreatmentTaxonomy()
