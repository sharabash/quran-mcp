"""Shared warning models used across multiple tool response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GroundingWarning(BaseModel):
    """Warning indicating grounding rules are being sent with every response.

    Injected by the grounding gate middleware when the client has not yet
    called fetch_grounding_rules.  Calling that tool once acknowledges the
    rules and suppresses both the grounding_rules field and this warning.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["grounding"] = Field(
        default="grounding",
        description="Warning type discriminator",
    )
    message: str = Field(
        default=(
            "Grounding rules are included with every response (~2 KB). "
            "Call fetch_grounding_rules, extract the grounding_nonce from "
            "the response, and pass it to subsequent tool calls \u2014 the "
            "grounding_rules field and this warning will then be omitted, "
            "saving tokens on all subsequent calls."
        ),
        description="Token-saving guidance for the AI client",
    )


class DataGapWarning(BaseModel):
    """Warning for missing data in a specific edition."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data_gap"] = Field(
        default="data_gap",
        description="Warning type discriminator",
    )
    edition_id: str = Field(description="Edition identifier with missing data")
    missing_ayahs: list[str] = Field(description="List of ayah keys not found")


class UnresolvedEditionWarning(BaseModel):
    """Warning for an edition selector that could not be resolved."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["unresolved_edition"] = Field(
        default="unresolved_edition",
        description="Warning type discriminator",
    )
    selector: str = Field(description="The original selector string that didn't match any edition")
    suggestion: str = Field(description="Actionable message directing caller to list_editions")


WarningModel = DataGapWarning | UnresolvedEditionWarning | GroundingWarning


def build_unresolved_edition_warnings(
    selectors: list[str],
) -> list[UnresolvedEditionWarning]:
    """Build UnresolvedEditionWarning instances from a list of unresolved selectors."""
    return [
        UnresolvedEditionWarning(
            selector=s,
            suggestion="Call list_editions to discover valid edition selectors.",
        )
        for s in selectors
    ]


GROUNDING_RULES_FIELD_DESCRIPTION = (
    "Grounding rules for canonical Quran data — CRITICAL for user trust. "
    "Set automatically when fetch_grounding_rules has not been called in this "
    "conversation. Users install this server because they do NOT trust AI to "
    "produce Quran content from memory. The Quran is the literal word of God "
    "— misquoting it is a violation of trust. Read and follow these rules "
    "carefully for ALL Quran-related responses. To save tokens on subsequent "
    "calls, call fetch_grounding_rules explicitly — this field will then be null."
)
