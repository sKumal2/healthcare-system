"""Shared fixtures for RAG tests."""

from __future__ import annotations

import pytest

from app.rag.models import RankedChunk, RetrievedChunk


@pytest.fixture
def trusted_chunks() -> list[RetrievedChunk]:
    """Five retrieval chunks spanning multiple trusted sources."""
    return [
        RetrievedChunk(
            chunk_id="c1",
            content="Type 2 diabetes is often managed with metformin and lifestyle changes.",
            source_url="https://www.cdc.gov/diabetes/basics/type2.html",
            source_name="CDC",
            score=0.91,
            metadata={"section": "overview"},
        ),
        RetrievedChunk(
            chunk_id="c2",
            content="Insulin therapy may be required for advanced type 2 diabetes patients.",
            source_url="https://www.fda.gov/drugs/insulin",
            source_name="FDA",
            score=0.86,
            metadata={},
        ),
        RetrievedChunk(
            chunk_id="c3",
            content="Diabetes mellitus is a chronic metabolic disease impacting glucose regulation.",
            source_url="https://www.who.int/health-topics/diabetes",
            source_name="WHO",
            score=0.83,
            metadata={},
        ),
        RetrievedChunk(
            chunk_id="c4",
            content="Patients with diabetes should monitor their HbA1c quarterly.",
            source_url="https://www.mayoclinic.org/diseases-conditions/diabetes",
            source_name="Mayo Clinic",
            score=0.78,
            metadata={},
        ),
        RetrievedChunk(
            chunk_id="c5",
            content="Common cold symptoms include runny nose and sore throat.",
            source_url="https://example.com/cold",
            source_name="Example Health",
            score=0.50,
            metadata={},
        ),
    ]


@pytest.fixture
def trusted_ranked_chunks(trusted_chunks: list[RetrievedChunk]) -> list[RankedChunk]:
    """The same chunks promoted to RankedChunk with arbitrary relevance scores."""
    out: list[RankedChunk] = []
    for rank, c in enumerate(trusted_chunks, start=1):
        out.append(
            RankedChunk(
                **c.model_dump(),
                rank=rank,
                relevance_score=1.0 - (rank * 0.1),
            )
        )
    return out
