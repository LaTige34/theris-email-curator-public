"""shadow_out — Appender JSONL pour le shadow mode.

Permet à un système de "juge" externe (LLM ou règles) de rejouer la journée
et comparer deux pipelines (baseline vs nouvelle implémentation) en écrivant
chaque classification / draft / routage dans `shadow_out/YYYY-MM-DD.jsonl`.

Format retenu : superset du schéma minimal consommé par un loader
externe `load_skill_shadow_outputs` (exemple de judge externe) :

    - thread_id        (clé de jointure)
    - category         (URGENT|ACTION|INFO|SPAM|UNKNOWN)
    - subcategory
    - confidence       (float 0-1)
    - reasoning        (déjà masqué PHI)
    - phi_detected     (bool)
    - should_draft     (bool)
    - telegram_priority
    - label_applied    (ex "curator/URGENT, curator/WORK-MAIN")
    - draft_preview    (≤ 400 chars, masqué PHI)
    - timestamp        (ISO 8601 UTC)

Champs extension :
    - email_id_hash    (SHA256 tronqué du thread_id, anti-rebond mémoire)
    - subject_masked   (subject après mask_pii, tronqué 200 chars)
    - theme            (label thème extrait parmi THEME_LABELS)
    - draft_template_chosen (clé template generate_draft)
    - tokens_in / tokens_out
    - cost_estimate_eur
    - provider         ("anthropic" | "mistral" | "openrouter")
    - tool             ("classify" | "labels" | "draft") — quelle étape a écrit la ligne

Sémantique loader : "last wins" par thread_id → on peut appeler l'appender
une fois par étape sans coordination.

Conformité PII :
    - `mask_pii` OBLIGATOIRE sur subject + reasoning + draft_preview avant
      écriture.
    - Rotation daily : un fichier `YYYY-MM-DD.jsonl` par jour (atomic append).
    - Purge > 30 jours : `scripts/rotate_shadow_out.sh` (cron journalier).

Tests : tests/test_shadow_out.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.safety import mask_pii as _mask_pii


def _mask(text: str) -> str:
    if not text:
        return ""
    try:
        return _mask_pii(text)
    except Exception:  # pragma: no cover - paranoia
        return text


# Path racine du skill (exporté pour tests et rotation)
SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHADOW_DIR = SKILL_ROOT / "shadow_out"

# Override par env var pour tests
SHADOW_OUT_ENV = "EMAIL_CURATOR_SHADOW_OUT"


def _resolve_shadow_dir(override: Path | str | None = None) -> Path:
    if override is not None:
        return Path(override)
    env = os.environ.get(SHADOW_OUT_ENV)
    if env:
        return Path(env)
    return DEFAULT_SHADOW_DIR


def _today_path(base: Path) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return base / f"{day}.jsonl"


def _email_id_hash(thread_id: str) -> str:
    return hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:16]


def _extract_theme(labels: list[str]) -> str:
    """Extrait le thème depuis une liste de labels routés."""
    from lib.labels import THEME_LABELS

    for lab in labels:
        if lab in THEME_LABELS:
            return lab
    return ""


def build_shadow_record(
    *,
    thread_id: str,
    tool: str,
    category: str = "UNKNOWN",
    subcategory: str = "",
    confidence: float = 0.0,
    reasoning: str = "",
    phi_detected: bool = False,
    should_draft: bool = False,
    telegram_priority: str = "silent",
    subject: str = "",
    sender_domain: str = "",
    label_applied: str = "",
    draft_preview: str = "",
    draft_template_chosen: str = "",
    provider: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_estimate_eur: float = 0.0,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Construit un enregistrement shadow_out, avec mask_phi sur champs libres.

    Ne PAS modifier : la clé de jointure `thread_id` reste telle quelle (c'est
    un identifiant opaque Gmail, jamais PHI en lui-même).
    """
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    return {
        "thread_id": thread_id,
        "email_id_hash": _email_id_hash(thread_id),
        "tool": tool,
        "category": category,
        "subcategory": subcategory[:50] if subcategory else "",
        "confidence": float(confidence),
        "reasoning": _mask(reasoning)[:500],
        "phi_detected": bool(phi_detected),
        "should_draft": bool(should_draft),
        "telegram_priority": telegram_priority,
        "subject_masked": _mask(subject)[:200],
        "sender_domain": sender_domain,
        "label_applied": label_applied,
        "theme": _extract_theme(
            [lab.strip() for lab in label_applied.split(",") if lab.strip()]
        )
        if label_applied
        else "",
        "draft_preview": _mask(draft_preview)[:400],
        "draft_template_chosen": draft_template_chosen,
        "provider": provider,
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "cost_estimate_eur": float(cost_estimate_eur),
        "timestamp": ts,
    }


def _load_latest_for_thread(fp: Path, thread_id: str) -> dict[str, Any] | None:
    """Retourne la dernière ligne shadow_out pour `thread_id` (ou None)."""
    if not fp.exists():
        return None
    latest: dict[str, Any] | None = None
    try:
        with fp.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("thread_id") == thread_id:
                    latest = row
    except OSError:
        return None
    return latest


# Champs à conserver depuis la ligne précédente si le nouveau record les a
# laissés "vides" (stratégie merge last-wins-non-empty).
_MERGEABLE_KEYS: tuple[str, ...] = (
    "category",
    "subcategory",
    "confidence",
    "reasoning",
    "phi_detected",
    "should_draft",
    "telegram_priority",
    "subject_masked",
    "sender_domain",
    "label_applied",
    "theme",
    "draft_preview",
    "draft_template_chosen",
    "provider",
    "tokens_in",
    "tokens_out",
    "cost_estimate_eur",
)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return True
    return False


def _merge_with_previous(new: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """Complète `new` avec les champs non-vides de `previous`.

    Stratégie :
        - Si `new[key]` est vide/zéro ET `previous[key]` non-vide → on reprend `previous[key]`.
        - Sinon `new[key]` gagne (écriture la plus récente fait foi).
    - `phi_detected` : un true quelque part reste true (OR logique).
    """
    merged = dict(new)
    for key in _MERGEABLE_KEYS:
        if _is_empty(merged.get(key)) and not _is_empty(previous.get(key)):
            merged[key] = previous[key]
    # phi_detected : OR logique (sécurité HDS)
    if bool(previous.get("phi_detected")) or bool(new.get("phi_detected")):
        merged["phi_detected"] = True
    return merged


def append_shadow_jsonl(
    record: dict[str, Any],
    shadow_dir: Path | str | None = None,
    merge_by_thread: bool = True,
) -> Path:
    """Append atomique d'un enregistrement dans `YYYY-MM-DD.jsonl`.

    Si `merge_by_thread=True` (défaut) et qu'une entrée précédente existe
    déjà aujourd'hui pour ce `thread_id`, les champs non-vides du record
    précédent sont conservés (last-wins-non-empty). Cela garantit que le
    dernier row écrit contient TOUT (classify + labels + draft), condition
    nécessaire pour un loader externe qui fait last-wins par thread_id.

    Retourne le path écrit. Crée le dossier si absent. Ne lève pas si
    l'écriture échoue (shadow mode ne doit PAS casser le pipeline prod) :
    l'erreur est imprimée sur stderr et l'appel est no-op.
    """
    base = _resolve_shadow_dir(shadow_dir)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"[shadow_out] cannot create {base}: {e}",
            file=sys.stderr,
        )
        return base
    fp = _today_path(base)
    final_record = record
    if merge_by_thread and record.get("thread_id"):
        previous = _load_latest_for_thread(fp, record["thread_id"])
        if previous:
            final_record = _merge_with_previous(record, previous)
    try:
        with fp.open("a", encoding="utf-8") as f:
            f.write(json.dumps(final_record, ensure_ascii=False) + "\n")
    except OSError as e:  # pragma: no cover - disque plein / ENOSPC
        print(f"[shadow_out] cannot append to {fp}: {e}", file=sys.stderr)
    return fp


def record_classification(
    *,
    thread_id: str,
    subject: str,
    sender_domain: str,
    category: str,
    subcategory: str,
    confidence: float,
    reasoning: str,
    phi_detected: bool,
    should_draft: bool,
    telegram_priority: str,
    provider: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_estimate_eur: float = 0.0,
    shadow_dir: Path | str | None = None,
) -> Path:
    """Helper haut niveau appelé par classify_email après validation."""
    rec = build_shadow_record(
        thread_id=thread_id,
        tool="classify",
        category=category,
        subcategory=subcategory,
        confidence=confidence,
        reasoning=reasoning,
        phi_detected=phi_detected,
        should_draft=should_draft,
        telegram_priority=telegram_priority,
        subject=subject,
        sender_domain=sender_domain,
        provider=provider,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate_eur=cost_estimate_eur,
    )
    return append_shadow_jsonl(rec, shadow_dir=shadow_dir)


def record_labels(
    *,
    thread_id: str,
    subject: str,
    sender_domain: str,
    category: str,
    subcategory: str,
    should_draft: bool,
    labels: list[str],
    shadow_dir: Path | str | None = None,
) -> Path:
    """Helper haut niveau appelé par apply_labels après route_labels."""
    rec = build_shadow_record(
        thread_id=thread_id,
        tool="labels",
        category=category,
        subcategory=subcategory,
        should_draft=should_draft,
        subject=subject,
        sender_domain=sender_domain,
        label_applied=", ".join(labels),
    )
    return append_shadow_jsonl(rec, shadow_dir=shadow_dir)


def record_draft(
    *,
    thread_id: str,
    subject: str,
    sender_domain: str,
    subcategory: str,
    draft_text: str,
    draft_template_chosen: str,
    provider: str = "anthropic",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_estimate_eur: float = 0.0,
    shadow_dir: Path | str | None = None,
) -> Path:
    """Helper haut niveau appelé par generate_draft après génération."""
    rec = build_shadow_record(
        thread_id=thread_id,
        tool="draft",
        category="ACTION",
        subcategory=subcategory,
        should_draft=True,
        subject=subject,
        sender_domain=sender_domain,
        draft_preview=draft_text,
        draft_template_chosen=draft_template_chosen,
        provider=provider,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate_eur=cost_estimate_eur,
    )
    return append_shadow_jsonl(rec, shadow_dir=shadow_dir)


__all__ = [
    "DEFAULT_SHADOW_DIR",
    "SHADOW_OUT_ENV",
    "append_shadow_jsonl",
    "build_shadow_record",
    "record_classification",
    "record_draft",
    "record_labels",
]
