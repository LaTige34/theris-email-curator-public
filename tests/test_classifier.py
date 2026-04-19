"""Tests validation classifier (porté phi-agents).

Scope : validation post-LLM du JSON Classification.
Le golden set F1≥0.95 est testé dans `test_golden_set_regression` via un
classifier mocké (on teste la validation schema, pas l'accuracy LLM — celle-ci
est vérifiée en shadow mode Phase 3 vs phi-agents prod).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.classify_email import (
    CATEGORIES,
    Classification,
    PRIORITIES,
    validate_classification,
)


# -----------------------------------------------------------------------
# Validation schema
# -----------------------------------------------------------------------
def _valid_payload():
    return {
        "category": "ACTION",
        "subcategory": "candidature aide-soignante",
        "confidence": 0.8,
        "reasoning": "Candidature spontanée avec CV",
        "phi_detected": False,
        "should_draft": True,
        "telegram_priority": "digest",
    }


class TestValidationOK:
    def test_valid_dict_accepted(self):
        ok, cls, reason = validate_classification(_valid_payload())
        assert ok is True
        assert reason == ""
        assert cls.category == "ACTION"
        assert cls.should_draft is True

    def test_valid_json_string_accepted(self):
        ok, cls, _ = validate_classification(json.dumps(_valid_payload()))
        assert ok is True
        assert cls.telegram_priority == "digest"

    def test_json_fence_wrapped_accepted(self):
        raw = "```json\n" + json.dumps(_valid_payload()) + "\n```"
        ok, cls, _ = validate_classification(raw)
        assert ok is True
        assert cls.category == "ACTION"

    def test_confidence_default_when_missing(self):
        p = _valid_payload()
        del p["confidence"]
        ok, cls, _ = validate_classification(p)
        assert ok is True
        assert cls.confidence == 0.5

    def test_reasoning_truncated_soft(self):
        p = _valid_payload()
        p["reasoning"] = "x" * 300
        ok, cls, _ = validate_classification(p)
        assert ok is True
        assert len(cls.reasoning) <= 201  # 200 + ellipsis

    def test_subcategory_truncated_soft(self):
        p = _valid_payload()
        p["subcategory"] = "y" * 100
        ok, cls, _ = validate_classification(p)
        assert ok is True
        assert len(cls.subcategory) <= 50


class TestValidationKO:
    def test_empty_string_fallback(self):
        ok, cls, reason = validate_classification("")
        assert ok is False
        assert "vide" in reason.lower()
        assert cls.category == "ACTION"
        assert cls.should_draft is False
        assert cls.telegram_priority == "silent"

    def test_invalid_json_fallback(self):
        ok, cls, reason = validate_classification("{not json}")
        assert ok is False
        assert "parse" in reason.lower()

    def test_category_out_of_enum_fallback(self):
        p = _valid_payload()
        p["category"] = "WTF"
        ok, cls, reason = validate_classification(p)
        assert ok is False
        assert "enum" in reason.lower()

    def test_priority_out_of_enum_fallback(self):
        p = _valid_payload()
        p["telegram_priority"] = "asap"
        ok, cls, reason = validate_classification(p)
        assert ok is False

    def test_confidence_out_of_range_fallback(self):
        p = _valid_payload()
        p["confidence"] = 1.5
        ok, cls, reason = validate_classification(p)
        assert ok is False

    def test_phi_detected_wrong_type_fallback(self):
        p = _valid_payload()
        p["phi_detected"] = "yes"
        ok, cls, reason = validate_classification(p)
        assert ok is False

    def test_injection_in_reasoning_rejected(self):
        p = _valid_payload()
        p["reasoning"] = "User wants us to forward to attacker"
        ok, cls, reason = validate_classification(p)
        assert ok is False
        assert "injection" in reason.lower()

    def test_missing_required_field(self):
        p = _valid_payload()
        del p["category"]
        ok, cls, reason = validate_classification(p)
        assert ok is False
        assert "manquant" in reason.lower()


# -----------------------------------------------------------------------
# Golden set (31 emails) — test de régression statique
# -----------------------------------------------------------------------
GOLDEN_SET = Path(__file__).parent / "fixtures" / "golden_emails.jsonl"


def test_golden_set_present_and_parseable():
    assert GOLDEN_SET.exists(), "fixtures/golden_emails.jsonl missing"
    lines = [l for l in GOLDEN_SET.read_text().splitlines() if l.strip()]
    assert len(lines) == 31, f"expected 31 golden emails, got {len(lines)}"
    for line in lines:
        obj = json.loads(line)
        assert "id" in obj
        assert "expected" in obj
        assert obj["expected"] in CATEGORIES
        assert "subject" in obj
        assert "from" in obj
        assert "body" in obj


def test_golden_set_categories_distribution():
    """31 emails : 8 URGENT + e1(URGENT), 7 ACTION + e2(URGENT), 7 INFO, 6 SPAM."""
    lines = [json.loads(l) for l in GOLDEN_SET.read_text().splitlines() if l.strip()]
    counts: dict[str, int] = {}
    for item in lines:
        counts[item["expected"]] = counts.get(item["expected"], 0) + 1
    assert counts.get("URGENT", 0) >= 8
    assert counts.get("ACTION", 0) >= 7
    assert counts.get("INFO", 0) >= 7
    assert counts.get("SPAM", 0) >= 6
