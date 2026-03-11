"""Context document schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.common import JSONB_SIZE_SMALL, validate_jsonb_size

DOCUMENT_TYPES = frozenset(
    {"runbook", "ir_plan", "sop", "playbook", "detection_guide", "other"}
)

# Supported operators for targeting rules
_VALID_OPS = frozenset({"eq", "in", "contains", "gte", "lte"})

# Fields that targeting rules may reference
_VALID_FIELDS = frozenset({"source_name", "severity", "tags"})


def _validate_rule(rule: object, path: str) -> list[str]:
    """Return list of error strings for a single targeting rule object."""
    errors: list[str] = []
    if not isinstance(rule, dict):
        return [f"{path}: rule must be an object"]
    for key in ("field", "op", "value"):
        if key not in rule:
            errors.append(f"{path}: missing required key '{key}'")
    if "field" in rule and rule["field"] not in _VALID_FIELDS:
        errors.append(
            f"{path}.field: '{rule['field']}' not in {sorted(_VALID_FIELDS)}"
        )
    if "op" in rule and rule["op"] not in _VALID_OPS:
        errors.append(f"{path}.op: '{rule['op']}' not in {sorted(_VALID_OPS)}")
    return errors


def validate_targeting_rules(rules: dict[str, Any] | None) -> list[str]:
    """
    Validate the structure of a targeting_rules object.

    Expected shape::

        {
            "match_any": [{"field": ..., "op": ..., "value": ...}, ...],
            "match_all": [{"field": ..., "op": ..., "value": ...}, ...]
        }

    At least one of match_any or match_all must be present.
    Returns a list of error strings — empty means valid.
    """
    if rules is None:
        return []

    errors: list[str] = []
    if not isinstance(rules, dict):
        return ["targeting_rules must be an object"]

    known_keys = {"match_any", "match_all"}
    unknown = set(rules.keys()) - known_keys
    if unknown:
        errors.append(f"targeting_rules has unknown keys: {sorted(unknown)}")

    if not any(k in rules for k in known_keys):
        errors.append("targeting_rules must contain at least one of: match_any, match_all")

    for array_key in ("match_any", "match_all"):
        if array_key in rules:
            arr = rules[array_key]
            if not isinstance(arr, list):
                errors.append(f"targeting_rules.{array_key} must be an array")
            else:
                for i, rule in enumerate(arr):
                    errors.extend(_validate_rule(rule, f"{array_key}[{i}]"))

    return errors


class ContextDocumentCreate(BaseModel):
    """Request body for POST /v1/context-documents (JSON path)."""

    title: str
    document_type: str
    is_global: bool = False
    description: str | None = None
    content: str
    tags: list[str] = []
    targeting_rules: dict[str, Any] | None = None

    @field_validator("document_type")
    @classmethod
    def _validate_document_type(cls, v: str) -> str:
        if v not in DOCUMENT_TYPES:
            raise ValueError(f"document_type must be one of: {sorted(DOCUMENT_TYPES)}")
        return v

    @field_validator("targeting_rules")
    @classmethod
    def _validate_targeting_rules(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None:
            validate_jsonb_size(v, JSONB_SIZE_SMALL, "targeting_rules")
            errors = validate_targeting_rules(v)
            if errors:
                raise ValueError("; ".join(errors))
        return v


class ContextDocumentPatch(BaseModel):
    """Request body for PATCH /v1/context-documents/{uuid}."""

    title: str | None = None
    document_type: str | None = None
    is_global: bool | None = None
    description: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    targeting_rules: dict[str, Any] | None = None

    @field_validator("document_type")
    @classmethod
    def _validate_document_type(cls, v: str | None) -> str | None:
        if v is not None and v not in DOCUMENT_TYPES:
            raise ValueError(f"document_type must be one of: {sorted(DOCUMENT_TYPES)}")
        return v

    @field_validator("targeting_rules")
    @classmethod
    def _validate_targeting_rules(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None:
            validate_jsonb_size(v, JSONB_SIZE_SMALL, "targeting_rules")
            errors = validate_targeting_rules(v)
            if errors:
                raise ValueError("; ".join(errors))
        return v


class ContextDocumentSummary(BaseModel):
    """List response — omits content to save tokens."""

    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    title: str
    document_type: str
    is_global: bool
    description: str | None
    tags: list[str]
    version: int
    created_at: datetime
    updated_at: datetime


class ContextDocumentResponse(ContextDocumentSummary):
    """Full response — includes content and targeting_rules."""

    content: str
    targeting_rules: dict[str, Any] | None
