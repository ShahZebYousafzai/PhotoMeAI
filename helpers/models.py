"""SQLAlchemy models."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from helpers.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    predictions = relationship("Prediction", back_populates="user", cascade="all, delete-orphan")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    # Replicate prediction id.
    # Note: older SQLite DBs used `replicate_id` with NOT NULL; keep DB column name stable.
    prediction_id = Column("replicate_id", String(128), index=True, nullable=False)

    status = Column(String(64), nullable=False, default="starting")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    prompt = Column(Text, nullable=True)
    num_outputs = Column(Integer, nullable=True)
    output_format = Column(String(16), nullable=True)
    require_trigger_word = Column(Boolean, nullable=True)
    trigger_word = Column(String(64), nullable=True)

    # For history display; can be a relative API path or absolute URL
    thumbnail_url = Column(Text, nullable=True)

    # Full list of output URLs (relative API paths or absolute URLs), as JSON string
    output_urls_json = Column(Text, nullable=True)

    # Optional raw replicate payload snapshots as JSON string (avoid schema churn)
    create_payload_json = Column(Text, nullable=True)
    detail_payload_json = Column(Text, nullable=True)

    user = relationship("User", back_populates="predictions")
