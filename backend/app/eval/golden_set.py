from dataclasses import dataclass

from app.models import DocumentFormat


@dataclass(frozen=True)
class GoldenDocument:
    filename: str
    format: DocumentFormat
    content: str


@dataclass(frozen=True)
class GoldenItem:
    """One golden Q&A example: a question against `document`, the substring
    of `document.content` that answers it (`expected_passage` — used to score
    retrieval hit-rate: did the chunk actually containing this text make it
    into the LLM's context?), and a substring the generated answer should
    contain when the pipeline gets it right (`expected_answer_contains` —
    used only to sanity-check the golden set itself, e.g.
    test_golden_set_is_answerable_from_its_own_documents).
    """

    document: GoldenDocument
    question: str
    expected_passage: str
    expected_answer_contains: str


_HEALTH_INSURANCE = GoldenDocument(
    filename="health-insurance.md",
    format=DocumentFormat.MD,
    content="Full-time employees are eligible for health insurance starting on day one.",
)

_DENTAL_COVERAGE = GoldenDocument(
    filename="dental-coverage.md",
    format=DocumentFormat.MD,
    content=(
        "Dental and vision coverage begins after a 90-day waiting period for all new hires."
    ),
)

_VPN_POLICY = GoldenDocument(
    filename="vpn-policy.md",
    format=DocumentFormat.MD,
    content=(
        "All remote employees must connect through the corporate VPN client before "
        "accessing internal tools. VPN credentials expire every 180 days and must be "
        "renewed via the IT portal."
    ),
)

_EXPENSE_POLICY = GoldenDocument(
    filename="expense-policy.md",
    format=DocumentFormat.MD,
    content=(
        "Employees traveling for business may expense meals up to $75 per day without "
        "a receipt. Any single expense over $25 requires an itemized receipt."
    ),
)

# Kept small and single-chunk-per-document on purpose (each document's whole
# content fits well under settings.chunk_size_chars, and none of it contains a
# blank line/heading break — see app.ingestion.chunking) so each golden item's
# expected_passage is guaranteed to land in the same, single retrieved chunk,
# and within Citation's _SNIPPET_MAX_CHARS preview (app/qa/answering.py) rather
# than being truncated out of it. Each fact also gets its own document rather
# than sharing one — FakeLLMProvider (tests/fakes/llm.py) picks the best-
# scoring sentence from the assembled context and breaks a tie by keeping
# whichever it saw first, so two competing facts packed into the same
# single-chunk document could tie and make sentence choice arbitrary.
GOLDEN_SET: list[GoldenItem] = [
    GoldenItem(
        document=_HEALTH_INSURANCE,
        question="When are new employees eligible for health insurance?",
        expected_passage=(
            "Full-time employees are eligible for health insurance starting on day one."
        ),
        expected_answer_contains="day one",
    ),
    GoldenItem(
        document=_DENTAL_COVERAGE,
        question="When does dental coverage start for new employees?",
        expected_passage=(
            "Dental and vision coverage begins after a 90-day waiting period for all new hires."
        ),
        expected_answer_contains="90-day",
    ),
    GoldenItem(
        document=_VPN_POLICY,
        question="How often do VPN credentials need to be renewed?",
        expected_passage=(
            "VPN credentials expire every 180 days and must be renewed via the IT portal."
        ),
        expected_answer_contains="180",
    ),
    GoldenItem(
        document=_EXPENSE_POLICY,
        question="What is the daily meal expense limit without a receipt?",
        expected_passage=(
            "Employees traveling for business may expense meals up to $75 per day "
            "without a receipt."
        ),
        expected_answer_contains="$75",
    ),
]
