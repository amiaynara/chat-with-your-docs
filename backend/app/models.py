import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base


class DocumentStatus(enum.StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentFormat(enum.StrEnum):
    PDF = "pdf"
    TXT = "txt"
    MD = "md"


class DocumentErrorCategory(enum.StrEnum):
    """Set alongside error_reason whenever status=FAILED — distinguishes a
    problem the user can fix by re-uploading (USER_ERROR) from one that may
    resolve itself and is worth retrying against the same stored bytes
    (SYSTEM_ERROR). See app.ingestion.tasks.ingest_document for how each
    failure is classified, and the /documents/{id}/retry route for how this
    gates whether a retry is allowed.
    """

    USER_ERROR = "user_error"
    SYSTEM_ERROR = "system_error"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[DocumentFormat] = mapped_column(
        Enum(
            DocumentFormat,
            name="document_format",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DocumentStatus.QUEUED,
    )
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_category: Mapped[DocumentErrorCategory | None] = mapped_column(
        Enum(
            DocumentErrorCategory,
            name="document_error_category",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    object_storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    location_ref: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base):
    """One turn of a session's chat transcript — a user question or an
    assistant answer. Keyed by the same raw session-cookie string used by
    Document.session_id (there's no separate session/account entity), so
    history is scoped to the anonymous session that asked it.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            name="message_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Citation metadata (see qa/answering.py::Citation), serialized as plain
    # dicts — only ever set on an assistant message; null for a user message
    # or an assistant message with no supporting citations.
    citations: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
