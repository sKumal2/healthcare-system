"""Query parser: PII stripping, entity extraction, intent detection, expansion.

Uses a lightweight heuristic approach by default. spaCy is optional and is
loaded lazily — when unavailable, the parser falls back to regex-based entity
extraction so the pipeline still works in minimal environments.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from app.rag.models import ParsedQuery, QueryIntent

logger = logging.getLogger(__name__)


_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOB_RE = re.compile(
    r"\b(?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12]\d|3[01])[\/\-](?:19|20)\d{2}\b"
)
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_NAME_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Patient)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")


SYNONYM_MAP: dict[str, list[str]] = {
    "heart attack": ["myocardial infarction", "mi", "cardiac arrest"],
    "high blood pressure": ["hypertension", "htn"],
    "stroke": ["cerebrovascular accident", "cva"],
    "sugar": ["glucose", "blood glucose", "diabetes"],
    "diabetes": ["diabetes mellitus", "type 2 diabetes", "t2dm"],
    "cold": ["common cold", "upper respiratory infection", "uri"],
    "flu": ["influenza"],
    "cancer": ["malignancy", "neoplasm", "carcinoma"],
    "pain killer": ["analgesic", "pain reliever"],
    "tylenol": ["acetaminophen", "paracetamol"],
    "advil": ["ibuprofen", "nsaid"],
}


# Minimal medical vocabulary for fallback NER. A real deployment would plug in
# UMLS / SNOMED CT for clinically vetted concept extraction.
_MEDICAL_VOCAB: set[str] = {
    "diabetes", "hypertension", "asthma", "covid", "covid-19", "influenza",
    "cancer", "stroke", "migraine", "depression", "anxiety", "obesity",
    "pneumonia", "tuberculosis", "hiv", "aids", "hepatitis", "malaria",
    "metformin", "insulin", "ibuprofen", "acetaminophen", "aspirin",
    "amoxicillin", "lisinopril", "atorvastatin", "warfarin", "heparin",
    "heart", "lung", "kidney", "liver", "brain", "stomach", "spine",
}

_INTENT_KEYWORDS: dict[QueryIntent, list[str]] = {
    "diagnosis": ["symptom", "diagnose", "diagnosis", "what is", "what causes",
                  "why do i", "do i have", "is it"],
    "treatment": ["treat", "treatment", "cure", "manage", "therapy", "remedy",
                  "how to", "should i take"],
    "drug_info": ["drug", "medication", "medicine", "side effect", "dose",
                  "dosage", "interaction", "pill"],
}


class QueryParser:
    """Parse, expand, and sanitize user queries before retrieval.

    The parser is designed to never raise on malformed input — empty or
    nonsense queries produce a ``ParsedQuery`` with empty fields rather than
    blowing up the rest of the pipeline.
    """

    def __init__(
        self,
        synonym_map: dict[str, list[str]] | None = None,
        medical_vocab: Iterable[str] | None = None,
    ) -> None:
        self.synonym_map = synonym_map if synonym_map is not None else SYNONYM_MAP
        self.medical_vocab = (
            set(medical_vocab) if medical_vocab is not None else _MEDICAL_VOCAB
        )
        self._spacy_nlp = self._try_load_spacy()

    @staticmethod
    def _try_load_spacy():
        """Try to load a small spaCy model; return ``None`` if unavailable."""
        try:
            import spacy  # type: ignore

            try:
                return spacy.load("en_core_web_sm")
            except OSError:
                logger.info(
                    "spaCy model 'en_core_web_sm' not installed; "
                    "falling back to regex-based entity extraction."
                )
                return None
        except ImportError:
            logger.info("spaCy not installed; using lightweight entity extraction.")
            return None

    @staticmethod
    def strip_pii(text: str) -> str:
        """Remove obvious PII (SSN, DOB, phone, email, name salutations) from a query.

        This is a *defense-in-depth* layer; callers should not rely on it
        as the sole sanitizer for sensitive data.
        """
        if not text:
            return ""
        cleaned = _SSN_RE.sub("[REDACTED_SSN]", text)
        cleaned = _DOB_RE.sub("[REDACTED_DOB]", cleaned)
        cleaned = _PHONE_RE.sub("[REDACTED_PHONE]", cleaned)
        cleaned = _EMAIL_RE.sub("[REDACTED_EMAIL]", cleaned)
        cleaned = _NAME_RE.sub("[REDACTED_NAME]", cleaned)
        return cleaned

    def detect_intent(self, query: str) -> QueryIntent:
        """Heuristic intent classifier — returns 'general' when uncertain.

        Counts keyword hits per intent and picks the highest-scoring one. On
        ties, the more-specific intents (``drug_info`` > ``treatment`` >
        ``diagnosis``) win — generic patterns like "what is" should not
        outrank a clinically specific term like "dose".
        """
        lowered = query.lower()
        priority: list[QueryIntent] = ["drug_info", "treatment", "diagnosis"]
        scores: dict[QueryIntent, int] = {
            intent: sum(1 for kw in _INTENT_KEYWORDS[intent] if kw in lowered)
            for intent in priority
        }
        best = max(priority, key=lambda i: (scores[i], -priority.index(i)))
        if scores[best] == 0:
            return "general"
        return best

    def extract_entities(self, query: str) -> list[str]:
        """Extract candidate medical entities from the query.

        Uses spaCy when available, otherwise compares tokens against a small
        in-house vocabulary. Returns lowercased, de-duplicated entities in
        order of first appearance.
        """
        entities: list[str] = []
        seen: set[str] = set()

        if self._spacy_nlp is not None:
            doc = self._spacy_nlp(query)
            for ent in doc.ents:
                token = ent.text.lower().strip()
                if token and token not in seen:
                    entities.append(token)
                    seen.add(token)

        lowered = query.lower()
        for token in re.findall(r"[a-zA-Z][a-zA-Z\-]+", lowered):
            if token in self.medical_vocab and token not in seen:
                entities.append(token)
                seen.add(token)

        return entities

    def expand_terms(self, query: str, entities: list[str]) -> list[str]:
        """Expand query with medical synonyms.

        Uses the configured ``synonym_map``. A real deployment would back this
        with UMLS / SNOMED CT for full clinical coverage.
        """
        lowered = query.lower()
        expanded: list[str] = []
        seen: set[str] = set()

        for surface, synonyms in self.synonym_map.items():
            if surface in lowered:
                for syn in synonyms:
                    if syn not in seen:
                        expanded.append(syn)
                        seen.add(syn)

        for entity in entities:
            for syn in self.synonym_map.get(entity, []):
                if syn not in seen:
                    expanded.append(syn)
                    seen.add(syn)

        return expanded

    async def parse(self, query: str) -> ParsedQuery:
        """Parse a raw user query into a ``ParsedQuery``.

        Steps: strip PII, extract medical entities, expand synonyms, detect intent.
        Always returns a ``ParsedQuery`` — never raises on user input.
        """
        sanitized = self.strip_pii(query or "")
        entities = self.extract_entities(sanitized)
        expanded = self.expand_terms(sanitized, entities)
        intent = self.detect_intent(sanitized)

        return ParsedQuery(
            original_query=sanitized,
            expanded_terms=expanded,
            medical_entities=entities,
            intent=intent,
            language="en",
        )
