"""Tests for app.rag.query_parser."""

from __future__ import annotations

import pytest

from app.rag.query_parser import QueryParser


@pytest.fixture
def parser() -> QueryParser:
    return QueryParser()


class TestPiiStripping:
    def test_strips_ssn(self, parser: QueryParser) -> None:
        assert "[REDACTED_SSN]" in parser.strip_pii("Patient SSN 123-45-6789 has flu")

    def test_strips_dob(self, parser: QueryParser) -> None:
        assert "[REDACTED_DOB]" in parser.strip_pii("DOB 03/15/1985 history of asthma")

    def test_strips_email(self, parser: QueryParser) -> None:
        assert "[REDACTED_EMAIL]" in parser.strip_pii("Contact me at user@test.com")

    def test_strips_phone(self, parser: QueryParser) -> None:
        assert "[REDACTED_PHONE]" in parser.strip_pii("Call 555-123-4567")

    def test_strips_name_with_salutation(self, parser: QueryParser) -> None:
        assert "[REDACTED_NAME]" in parser.strip_pii("Mr. John Smith has hypertension")

    def test_empty_query(self, parser: QueryParser) -> None:
        assert parser.strip_pii("") == ""


class TestIntentDetection:
    def test_diagnosis_intent(self, parser: QueryParser) -> None:
        assert parser.detect_intent("What are the symptoms of diabetes?") == "diagnosis"

    def test_treatment_intent(self, parser: QueryParser) -> None:
        assert parser.detect_intent("How to treat hypertension?") == "treatment"

    def test_drug_intent(self, parser: QueryParser) -> None:
        assert parser.detect_intent("What is the dose of metformin?") == "drug_info"

    def test_general_fallback(self, parser: QueryParser) -> None:
        assert parser.detect_intent("Tell me about hospitals") == "general"


class TestEntityExtraction:
    def test_extracts_known_terms(self, parser: QueryParser) -> None:
        ents = parser.extract_entities("My diabetes and hypertension are concerning")
        assert "diabetes" in ents
        assert "hypertension" in ents

    def test_returns_empty_for_no_terms(self, parser: QueryParser) -> None:
        assert parser.extract_entities("hello world") == []


class TestExpansion:
    def test_expands_synonyms(self, parser: QueryParser) -> None:
        expanded = parser.expand_terms(
            "I had a heart attack", entities=[]
        )
        assert "myocardial infarction" in expanded

    def test_no_expansion_for_unknown(self, parser: QueryParser) -> None:
        assert parser.expand_terms("zorblax xenon", entities=[]) == []


class TestParseAsync:
    @pytest.mark.asyncio
    async def test_happy_path(self, parser: QueryParser) -> None:
        result = await parser.parse("How do I treat my heart attack?")
        assert result.intent == "treatment"
        assert "myocardial infarction" in result.expanded_terms

    @pytest.mark.asyncio
    async def test_empty_query_does_not_raise(self, parser: QueryParser) -> None:
        result = await parser.parse("")
        assert result.original_query == ""
        assert result.medical_entities == []
        assert result.expanded_terms == []

    @pytest.mark.asyncio
    async def test_query_with_pii_is_redacted(self, parser: QueryParser) -> None:
        result = await parser.parse("Patient SSN 999-88-7777 has diabetes")
        assert "999-88-7777" not in result.original_query
        assert "[REDACTED_SSN]" in result.original_query

    @pytest.mark.asyncio
    async def test_only_stopwords(self, parser: QueryParser) -> None:
        result = await parser.parse("the and or but")
        assert result.medical_entities == []
        assert result.intent == "general"
