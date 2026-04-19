"""Tests shadow_out — Phase 3 Lever 1 (alimentation shadow_judge.py).

Vérifie :
- mask_phi appliqué avant écriture (subject, reasoning, draft_preview).
- Format JSONL strictement aligné sur `load_hermes_shadow_outputs` consumer.
- Rotation daily : un fichier `YYYY-MM-DD.jsonl` par jour.
- Intégration tools/*.py : record_*_shadow() écrit bien dans shadow_out/.
- Override THERIS_EMAIL_CURATOR_SHADOW_OUT env var (pour tests & staging).
- No-op safe si disque en lecture seule (pas de crash pipeline prod).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib.shadow_out import (
    DEFAULT_SHADOW_DIR,
    SHADOW_OUT_ENV,
    append_shadow_jsonl,
    build_shadow_record,
    record_classification,
    record_draft,
    record_labels,
)
from tools.apply_labels import record_labels_shadow, route_labels
from tools.classify_email import (
    Classification,
    record_classification_shadow,
    validate_classification,
)
from tools.generate_draft import (
    DEFAULT_SIGNATURE,
    draft_template_key_for,
    generate_draft,
    record_draft_shadow,
)


@pytest.fixture
def tmp_shadow_dir(tmp_path, monkeypatch):
    d = tmp_path / "shadow_out"
    monkeypatch.setenv(SHADOW_OUT_ENV, str(d))
    return d


def _read_all(path: Path) -> list[dict]:
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


# ---------------------------------------------------------------------------
# Format JSONL & mask_phi
# ---------------------------------------------------------------------------
class TestBuildRecord:
    def test_required_fields_present(self):
        rec = build_shadow_record(
            thread_id="thr-001",
            tool="classify",
            category="URGENT",
            subcategory="incident scalingo",
            confidence=0.9,
            reasoning="Scalingo prod down",
            phi_detected=False,
            should_draft=False,
            telegram_priority="immediate",
            subject="Incident prod",
            sender_domain="scalingo.com",
        )
        # Schéma consommé par shadow_judge.load_hermes_shadow_outputs
        for k in (
            "thread_id",
            "category",
            "subcategory",
            "confidence",
            "reasoning",
            "phi_detected",
            "should_draft",
            "telegram_priority",
            "label_applied",
            "draft_preview",
            "timestamp",
        ):
            assert k in rec, f"champ manquant : {k}"
        # Extensions Phase 3++
        assert "email_id_hash" in rec
        assert "subject_masked" in rec
        assert "tool" in rec
        assert rec["tool"] == "classify"
        assert rec["confidence"] == 0.9

    def test_timestamp_is_iso8601_utc(self):
        rec = build_shadow_record(thread_id="t", tool="classify")
        dt = datetime.fromisoformat(rec["timestamp"])
        # Doit être aware (UTC)
        assert dt.tzinfo is not None

    def test_email_id_hash_is_deterministic(self):
        r1 = build_shadow_record(thread_id="thr-abc", tool="classify")
        r2 = build_shadow_record(thread_id="thr-abc", tool="labels")
        assert r1["email_id_hash"] == r2["email_id_hash"]
        assert len(r1["email_id_hash"]) == 16

    def test_theme_extracted_from_labels(self):
        from lib.neo_labels import LABEL_PROCESSED, LABEL_URGENT, LABEL_WORK_MAIN
        rec = build_shadow_record(
            thread_id="t",
            tool="labels",
            label_applied=f"{LABEL_PROCESSED}, {LABEL_URGENT}, {LABEL_WORK_MAIN}",
        )
        assert rec["theme"] == LABEL_WORK_MAIN

    def test_no_theme_when_spam(self):
        from lib.neo_labels import LABEL_PROCESSED, LABEL_SPAM
        rec = build_shadow_record(
            thread_id="t",
            tool="labels",
            label_applied=f"{LABEL_PROCESSED}, {LABEL_SPAM}",
        )
        assert rec["theme"] == ""


class TestMaskPhi:
    def test_subject_email_redacted(self):
        rec = build_shadow_record(
            thread_id="t",
            tool="classify",
            subject="Contact user@example.com urgent",
        )
        assert "user@example.com" not in rec["subject_masked"]
        assert "[REDACTED]" in rec["subject_masked"]

    def test_reasoning_phone_fr_redacted(self):
        rec = build_shadow_record(
            thread_id="t",
            tool="classify",
            reasoning="Appeler 06 38 70 52 23 dès que possible",
        )
        assert "06 38 70 52 23" not in rec["reasoning"]
        assert "[REDACTED]" in rec["reasoning"]

    def test_draft_preview_email_redacted(self):
        rec = build_shadow_record(
            thread_id="t",
            tool="draft",
            draft_preview="Bonjour, merci. Contact famille@proches.fr",
        )
        assert "famille@proches.fr" not in rec["draft_preview"]
        assert "[REDACTED]" in rec["draft_preview"]

    def test_thread_id_not_masked(self):
        """thread_id = identifiant opaque Gmail, PAS PHI → garde tel quel."""
        rec = build_shadow_record(
            thread_id="thr-user@example.com-123",
            tool="classify",
        )
        # On ne masque JAMAIS la clé de jointure
        assert rec["thread_id"] == "thr-user@example.com-123"


# ---------------------------------------------------------------------------
# Append JSONL + rotation daily
# ---------------------------------------------------------------------------
class TestAppendJsonl:
    def test_creates_daily_file(self, tmp_shadow_dir):
        rec = build_shadow_record(thread_id="t1", tool="classify")
        fp = append_shadow_jsonl(rec)
        assert fp.exists()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert fp.name == f"{day}.jsonl"

    def test_appends_multiple_lines(self, tmp_shadow_dir):
        for i in range(3):
            rec = build_shadow_record(thread_id=f"t{i}", tool="classify")
            fp = append_shadow_jsonl(rec)
        rows = _read_all(fp)
        assert len(rows) == 3
        assert {r["thread_id"] for r in rows} == {"t0", "t1", "t2"}

    def test_one_file_per_day(self, tmp_shadow_dir):
        rec = build_shadow_record(thread_id="a", tool="classify")
        append_shadow_jsonl(rec)
        rec2 = build_shadow_record(thread_id="b", tool="classify")
        append_shadow_jsonl(rec2)
        # Un seul fichier créé aujourd'hui
        files = list(tmp_shadow_dir.glob("*.jsonl"))
        assert len(files) == 1

    def test_explicit_shadow_dir_override(self, tmp_path):
        custom = tmp_path / "alt"
        rec = build_shadow_record(thread_id="x", tool="classify")
        fp = append_shadow_jsonl(rec, shadow_dir=custom)
        assert fp.parent == custom
        assert fp.exists()

    def test_safe_noop_on_readonly(self, tmp_path, monkeypatch):
        """Shadow mode ne doit JAMAIS casser le pipeline : readonly = no-op."""
        ro = tmp_path / "ro"
        ro.mkdir()
        monkeypatch.setenv(SHADOW_OUT_ENV, str(ro))
        # Render readonly après création
        os.chmod(ro, 0o500)
        try:
            rec = build_shadow_record(thread_id="t", tool="classify")
            # Ne doit PAS lever
            append_shadow_jsonl(rec)
        finally:
            os.chmod(ro, 0o700)


# ---------------------------------------------------------------------------
# Intégration tools/*.py
# ---------------------------------------------------------------------------
class TestClassifyIntegration:
    def test_record_classification_shadow_writes_jsonl(self, tmp_shadow_dir):
        payload = {
            "category": "URGENT",
            "subcategory": "Incident infra prod Scalingo",
            "confidence": 0.92,
            "reasoning": "App down depuis 5 minutes, déclencheur HTTP 503",
            "phi_detected": False,
            "should_draft": False,
            "telegram_priority": "immediate",
        }
        ok, cls, _ = validate_classification(payload)
        assert ok
        fp = record_classification_shadow(
            thread_id="thr-incid-42",
            subject="URGENT: Scalingo down",
            sender_domain="scalingo.com",
            classification=cls,
            provider="anthropic/claude-haiku-4-5",
            tokens_in=1500,
            tokens_out=220,
            cost_estimate_eur=0.0033,
        )
        rows = _read_all(fp)
        assert len(rows) == 1
        row = rows[0]
        assert row["thread_id"] == "thr-incid-42"
        assert row["category"] == "URGENT"
        assert row["confidence"] == 0.92
        assert row["telegram_priority"] == "immediate"
        assert row["provider"] == "anthropic/claude-haiku-4-5"
        assert row["tokens_in"] == 1500
        assert row["tool"] == "classify"


class TestApplyLabelsIntegration:
    def test_record_labels_shadow_writes_jsonl(self, tmp_shadow_dir):
        labels = route_labels(
            category="ACTION",
            subcategory="Candidature aide-soignante",
            should_draft=True,
            sender_domain="outlook.fr",
            subject="Candidature poste AS",
        )
        fp = record_labels_shadow(
            thread_id="thr-cand-7",
            subject="Candidature poste AS",
            sender_domain="outlook.fr",
            category="ACTION",
            subcategory="Candidature aide-soignante",
            should_draft=True,
            labels=labels,
        )
        rows = _read_all(fp)
        assert len(rows) == 1
        row = rows[0]
        from lib.neo_labels import LABEL_DRAFT, LABEL_HR
        assert row["thread_id"] == "thr-cand-7"
        assert LABEL_DRAFT in row["label_applied"]
        assert row["theme"] == LABEL_HR
        assert row["tool"] == "labels"


class TestGenerateDraftIntegration:
    def test_record_draft_shadow_writes_jsonl(self, tmp_shadow_dir):
        llm = MagicMock()
        llm.chat.return_value = "Bonjour, merci pour votre candidature."
        draft = generate_draft(
            llm_client=llm,
            subject="Candidature AS",
            sender_domain="gmail.com",
            body_preview="Je candidate pour un poste d'aide-soignante.",
            subcategory="candidature aide-soignante",
            signature=DEFAULT_SIGNATURE,
        )
        fp = record_draft_shadow(
            thread_id="thr-draft-9",
            subject="Candidature AS",
            sender_domain="gmail.com",
            subcategory="candidature aide-soignante",
            draft_text=draft,
            provider="anthropic",
            tokens_in=800,
            tokens_out=160,
            cost_estimate_eur=0.0021,
        )
        rows = _read_all(fp)
        assert len(rows) == 1
        row = rows[0]
        assert row["thread_id"] == "thr-draft-9"
        assert row["draft_template_chosen"] == "candidature_soignant"
        assert row["provider"] == "anthropic"
        assert row["should_draft"] is True
        assert row["tool"] == "draft"
        # Signature présente dans draft_preview (contenu non vide)
        assert len(row["draft_preview"]) > 0

    def test_draft_template_key_generic_fallback(self):
        assert draft_template_key_for("catégorie inexistante") == "generic"
        assert draft_template_key_for("candidature aide-soignante") == "candidature_soignant"
        assert draft_template_key_for("admission résident") == "admission_ehpad"


# ---------------------------------------------------------------------------
# Schema compatibility avec shadow_judge.load_hermes_shadow_outputs
# ---------------------------------------------------------------------------
class TestMergeByThread:
    def test_last_row_contains_previous_classify_after_draft(self, tmp_shadow_dir):
        """Scénario réel : classify → labels → draft → le DERNIER row
        (draft) doit contenir la catégorie/confidence/labels accumulés."""
        cls = Classification(
            category="ACTION",
            subcategory="candidature soignant",
            confidence=0.9,
            reasoning="CV joint",
            phi_detected=False,
            should_draft=True,
            telegram_priority="digest",
        )
        record_classification_shadow(
            thread_id="thr-merge-1",
            subject="Candidature",
            sender_domain="gmail.com",
            classification=cls,
            provider="anthropic",
            tokens_in=1400,
            tokens_out=200,
            cost_estimate_eur=0.003,
        )
        labels = route_labels(
            category="ACTION",
            subcategory="candidature soignant",
            should_draft=True,
            sender_domain="gmail.com",
            subject="Candidature",
        )
        record_labels_shadow(
            thread_id="thr-merge-1",
            subject="Candidature",
            sender_domain="gmail.com",
            category="ACTION",
            subcategory="candidature soignant",
            should_draft=True,
            labels=labels,
        )
        llm = MagicMock()
        llm.chat.return_value = "Bonjour."
        draft = generate_draft(
            llm_client=llm,
            subject="Candidature",
            sender_domain="gmail.com",
            body_preview="CV",
            subcategory="candidature soignant",
            signature=DEFAULT_SIGNATURE,
        )
        fp = record_draft_shadow(
            thread_id="thr-merge-1",
            subject="Candidature",
            sender_domain="gmail.com",
            subcategory="candidature soignant",
            draft_text=draft,
            provider="anthropic",
            tokens_in=900,
            tokens_out=180,
            cost_estimate_eur=0.002,
        )
        rows = _read_all(fp)
        assert len(rows) == 3
        last = rows[-1]
        # Le dernier row (draft) contient TOUT via merge
        assert last["tool"] == "draft"
        assert last["category"] == "ACTION"
        from lib.neo_labels import LABEL_DRAFT, LABEL_HR
        assert last["confidence"] == 0.9  # hérité du classify
        assert LABEL_DRAFT in last["label_applied"]  # hérité du labels
        assert last["theme"] == LABEL_HR
        assert last["draft_template_chosen"] == "candidature_soignant"
        assert last["draft_preview"]  # non vide

    def test_phi_detected_or_logic(self, tmp_shadow_dir, tmp_path, monkeypatch):
        """Si un step précédent a détecté PHI, les suivants propagent true."""
        import lib.shadow_out as so
        fp = tmp_shadow_dir / "test.jsonl"
        # Row 1 : phi=true
        r1 = so.build_shadow_record(thread_id="phi-t", tool="classify", phi_detected=True)
        so.append_shadow_jsonl(r1)
        # Row 2 : phi=false (mais précédent vrai)
        r2 = so.build_shadow_record(thread_id="phi-t", tool="labels", phi_detected=False)
        so.append_shadow_jsonl(r2)
        rows = _read_all(tmp_shadow_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl")
        assert rows[-1]["phi_detected"] is True  # OR logique sécurité

    def test_merge_disabled_keeps_partial(self, tmp_shadow_dir):
        import lib.shadow_out as so
        r1 = so.build_shadow_record(thread_id="nm-1", tool="classify", category="URGENT", confidence=0.9)
        so.append_shadow_jsonl(r1)
        r2 = so.build_shadow_record(thread_id="nm-1", tool="labels")
        so.append_shadow_jsonl(r2, merge_by_thread=False)
        rows = _read_all(tmp_shadow_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl")
        assert rows[-1]["category"] == "UNKNOWN"  # pas hérité


class TestShadowJudgeCompat:
    def test_output_matches_loader_expectations(self, tmp_shadow_dir):
        """Simule exactement ce que `load_hermes_shadow_outputs` lit."""
        cls = Classification(
            category="ACTION",
            subcategory="Candidature IDE",
            confidence=0.85,
            reasoning="Candidature spontanée IDE diplômée",
            phi_detected=False,
            should_draft=True,
            telegram_priority="digest",
        )
        fp = record_classification_shadow(
            thread_id="thr-compat",
            subject="Candidature IDE",
            sender_domain="outlook.fr",
            classification=cls,
        )
        rows = _read_all(fp)
        row = rows[0]
        # Tous les champs que le loader attend (shadow_judge.py §401-415)
        assert row.get("thread_id") or row.get("message_id")
        assert row["category"] in {"URGENT", "ACTION", "INFO", "SPAM", "UNKNOWN"}
        assert 0.0 <= row["confidence"] <= 1.0
        assert isinstance(row["phi_detected"], bool)
        assert isinstance(row["should_draft"], bool)
        assert row["telegram_priority"] in {"immediate", "digest", "silent"}
        # Timestamp ISO parseable
        datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
