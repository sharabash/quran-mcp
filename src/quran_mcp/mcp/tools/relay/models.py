"""Typed schemas for relay tool parameters and responses.

These replace raw `dict` parameters with constrained Pydantic models,
ensuring structured data with length caps flows into PostgreSQL JSONB columns.
"""

from pydantic import BaseModel, Field


# --- Input models ---


class TurnExpectations(BaseModel):
    """Structured expectations for a turn."""

    expected_tools: list[str] | None = None
    expected_topics: list[str] | None = None
    confidence: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=500)


class TurnReflection(BaseModel):
    """Structured post-turn reflection."""

    found: str | None = Field(None, max_length=500)
    missing: str | None = Field(None, max_length=500)
    quality: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=500)


class ToolEffectiveness(BaseModel):
    """Per-tool effectiveness rating."""

    tool_name: str
    effective: bool
    notes: str | None = Field(None, max_length=200)


class TurnStartResponse(BaseModel):
    """Returned by turn_start on success."""

    turn_id: str
    origin: str
    interpreted_intent: str | None = None


class TurnEndResponse(BaseModel):
    """Returned by turn_end on success."""

    turn_id: str
    status: str
    overall_satisfaction: int | None = None


class UsageGapResponse(BaseModel):
    """Returned by usage_gap on success."""

    gap_id: str
    turn_id: str
    gap_type: str
    severity: int


class UserFeedbackResponse(BaseModel):
    """Returned by user_feedback on success."""

    feedback_id: str
    turn_id: str
    feedback_type: str
    severity: int
