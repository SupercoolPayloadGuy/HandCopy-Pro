import uuid, enum
from datetime import datetime
from sqlalchemy import String, Float, Text, DateTime, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class JobStatus(str, enum.Enum):
    pending    = "pending"
    generating = "generating"
    ready      = "ready"
    printing   = "printing"
    done       = "done"
    error      = "error"


class HandwritingProfile(Base):
    __tablename__ = "handwriting_profiles"

    id             : Mapped[str]            = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name           : Mapped[str]            = mapped_column(String(120))
    description    : Mapped[str | None]     = mapped_column(Text, nullable=True)
    slant_deg      : Mapped[float]          = mapped_column(Float, default=0.0)
    letter_spacing : Mapped[float]          = mapped_column(Float, default=1.0)
    word_spacing   : Mapped[float]          = mapped_column(Float, default=2.5)
    baseline_waver : Mapped[float]          = mapped_column(Float, default=0.3)
    stroke_width   : Mapped[float]          = mapped_column(Float, default=0.4)
    created_at     : Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)

    glyphs : Mapped[list["Glyph"]]      = relationship("Glyph",      back_populates="profile", cascade="all, delete-orphan")
    jobs   : Mapped[list["WritingJob"]] = relationship("WritingJob", back_populates="profile")


class Glyph(Base):
    """
    Stroke data for one character in one handwriting style.
    strokes = [{"pen": "down", "points": [[x,y], ...]}, ...]
    Coordinates are normalized 0.0–1.0.
    """
    __tablename__ = "glyphs"

    id          : Mapped[str]       = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id  : Mapped[str]       = mapped_column(String(36), ForeignKey("handwriting_profiles.id"))
    character   : Mapped[str]       = mapped_column(String(1))
    strokes     : Mapped[list]      = mapped_column(JSON)
    width_ratio : Mapped[float]     = mapped_column(Float, default=0.6)

    profile : Mapped["HandwritingProfile"] = relationship("HandwritingProfile", back_populates="glyphs")


class WritingJob(Base):
    __tablename__ = "writing_jobs"

    id                : Mapped[str]        = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id        : Mapped[str]        = mapped_column(String(36), ForeignKey("handwriting_profiles.id"))
    source_image_path : Mapped[str | None] = mapped_column(String(255), nullable=True)
    scan_dpi          : Mapped[int]        = mapped_column(default=300)
    text_blocks       : Mapped[list]       = mapped_column(JSON, default=list)
    gcode             : Mapped[str | None] = mapped_column(Text, nullable=True)
    status            : Mapped[JobStatus]  = mapped_column(SAEnum(JobStatus), default=JobStatus.pending)
    error_message     : Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at        : Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow)

    profile : Mapped["HandwritingProfile"] = relationship("HandwritingProfile", back_populates="jobs")
