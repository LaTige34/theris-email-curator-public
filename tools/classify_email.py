"""classify_email — Validation post-LLM de la classification email.

Garantit que le JSON renvoyé par le LLM respecte le schéma avant toute
action downstream (labels, drafts, voice call).

En cas de rejet (injection, schéma invalide, type erreur) → fallback safe
`ACTION + should_draft=False + telegram_priority=silent` (l'opérateur humain
trie à la main).

Intégration safety : les appels LLM côté wrapper (classify_via_llm) doivent
être wrappés avec `lib.safety.with_safety_net(...)` pour retry + circuit
breaker + alerting Telegram.

Shadow mode :
- Après chaque validation OK, appeler `record_classification_shadow(...)` pour
  appender un JSONL dans `shadow_out/YYYY-MM-DD.jsonl` consommable par un
  juge externe. mask_pii appliqué avant écriture.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Skill root path (parent de tools/)
_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from lib.shadow_out import record_classification as _record_classification  # noqa: E402

CATEGORIES: frozenset[str] = frozenset({"URGENT", "ACTION", "INFO", "SPAM"})
PRIORITIES: frozenset[str] = frozenset({"immediate", "digest", "silent"})

MAX_SUBCATEGORY_LEN = 50
MAX_REASONING_LEN = 200

# Patterns injection (insensibles à la casse)
_INJECTION_PATTERNS = [
    re.compile(r"\bforward\b.*\bto\b", re.IGNORECASE),
    re.compile(r"\bsend\s+to\b", re.IGNORECASE),
    re.compile(r"\bexfiltrate\b", re.IGNORECASE),
    re.compile(r"\bignore\s+(previous|prior|above)\b", re.IGNORECASE),
    re.compile(r"\bdisregard\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"\boverwrite\b", re.IGNORECASE),
    re.compile(r"\bdelete\b.*\b(this|email|inbox)\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class Classification:
    category: str
    subcategory: str
    confidence: float
    reasoning: str
    phi_detected: bool
    should_draft: bool
    telegram_priority: str


_SAFE_FALLBACK = Classification(
    category="ACTION",
    subcategory="validation-fallback",
    confidence=0.0,
    reasoning="Fallback safe : validation LLM échouée",
    phi_detected=False,
    should_draft=False,
    telegram_priority="silent",
)


def _safe_fallback() -> Classification:
    return _SAFE_FALLBACK


def _detect_injection(text: str) -> str | None:
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            return pat.pattern
    return None


_JSON_FENCE_RE = re.compile(
    r"```(?:json|JSON)?\s*\n?(.*?)\n?```",
    flags=re.DOTALL,
)


def _extract_json_payload(raw: str) -> str:
    m = _JSON_FENCE_RE.search(raw)
    if m:
        return m.group(1).strip()
    first = raw.find("{")
    last = raw.rfind("}")
    if first != -1 and last > first:
        return raw[first : last + 1]
    return raw


def validate_classification(
    payload: str | dict[str, Any],
) -> tuple[bool, Classification, str]:
    """Valide un payload LLM selon le schéma Classification.

    Returns:
        (ok, classification, reason).
        - ok=True → classification validée, reason="".
        - ok=False → _SAFE_FALLBACK, reason décrit la cause (audit).
    """
    if isinstance(payload, str):
        if not payload.strip():
            return False, _safe_fallback(), "JSON vide"
        cleaned = _extract_json_payload(payload)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            return False, _safe_fallback(), f"JSON parse error: {e.msg}"
    elif isinstance(payload, dict):
        data = payload
    else:
        return False, _safe_fallback(), f"Type payload invalide: {type(payload).__name__}"

    if not isinstance(data, dict):
        return False, _safe_fallback(), "Payload n'est pas un objet JSON"

    required = (
        "category",
        "subcategory",
        "reasoning",
        "phi_detected",
        "should_draft",
        "telegram_priority",
    )
    missing = [k for k in required if k not in data]
    if missing:
        return False, _safe_fallback(), f"Champs category/manquants: {missing}"

    data.setdefault("confidence", 0.5)

    category = data["category"]
    if not isinstance(category, str) or category not in CATEGORIES:
        return (
            False,
            _safe_fallback(),
            f"category hors enum (valeurs: {sorted(CATEGORIES)})",
        )

    subcategory = data["subcategory"]
    if not isinstance(subcategory, str):
        return False, _safe_fallback(), "subcategory doit être str"
    if len(subcategory) > MAX_SUBCATEGORY_LEN:
        subcategory = subcategory[:MAX_SUBCATEGORY_LEN]
        data["subcategory"] = subcategory

    confidence = data["confidence"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return False, _safe_fallback(), "confidence doit être numérique"
    if not (0.0 <= confidence <= 1.0):
        return False, _safe_fallback(), "confidence hors [0.0, 1.0]"

    reasoning = data["reasoning"]
    if not isinstance(reasoning, str):
        return False, _safe_fallback(), "reasoning doit être str"
    if len(reasoning) > MAX_REASONING_LEN:
        reasoning = reasoning[:MAX_REASONING_LEN] + "…"
        data["reasoning"] = reasoning

    if pat := _detect_injection(reasoning):
        return (
            False,
            _safe_fallback(),
            f"Possible prompt injection détectée (pattern: {pat})",
        )

    phi = data["phi_detected"]
    if not isinstance(phi, bool):
        return False, _safe_fallback(), "phi_detected doit être bool"

    draft = data["should_draft"]
    if not isinstance(draft, bool):
        return False, _safe_fallback(), "should_draft doit être bool"

    priority = data["telegram_priority"]
    if not isinstance(priority, str) or priority not in PRIORITIES:
        return (
            False,
            _safe_fallback(),
            f"telegram_priority hors enum (valeurs: {sorted(PRIORITIES)})",
        )

    return (
        True,
        Classification(
            category=category,
            subcategory=subcategory,
            confidence=float(confidence),
            reasoning=reasoning,
            phi_detected=phi,
            should_draft=draft,
            telegram_priority=priority,
        ),
        "",
    )


def record_classification_shadow(
    *,
    thread_id: str,
    subject: str,
    sender_domain: str,
    classification: Classification,
    provider: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_estimate_eur: float = 0.0,
    shadow_dir: Path | str | None = None,
) -> Path:
    """Append la classification dans shadow_out (shadow mode).

    mask_pii appliqué côté `lib.shadow_out.build_shadow_record` via
    `lib.safety` avant écriture. Cette fonction est idempotente : appelable
    plusieurs fois sans casse (le loader prend "last wins" par thread_id).
    """
    return _record_classification(
        thread_id=thread_id,
        subject=subject,
        sender_domain=sender_domain,
        category=classification.category,
        subcategory=classification.subcategory,
        confidence=classification.confidence,
        reasoning=classification.reasoning,
        phi_detected=classification.phi_detected,
        should_draft=classification.should_draft,
        telegram_priority=classification.telegram_priority,
        provider=provider,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate_eur=cost_estimate_eur,
        shadow_dir=shadow_dir,
    )


__all__ = [
    "CATEGORIES",
    "PRIORITIES",
    "Classification",
    "validate_classification",
    "record_classification_shadow",
]
