"""apply_labels — Routeur labels Gmail curator/*.

Règles anti-faux-positif clés :
- SPAM = un seul label (pas de thème) — une publicité mentionnant votre
  secteur ne doit pas être rangée dans le thème métier.
- WORK_OPS (client principal/partenaire) exige un mot-clé spécifique ;
  le nom du secteur seul ne suffit pas.
- Domaines figurant dans `WORK_MAIN_DOMAINS` → WORK_MAIN direct, précédence
  absolue.

Les listes de patterns sont **configurables** : chaque utilisateur peut
modifier `PATTERNS_WORK_MAIN` / `PATTERNS_WORK_OPS` / `PATTERNS_HR` pour
matcher son domaine métier. Les valeurs fournies sont des exemples génériques.

Shadow mode :
- Après routage, appeler `record_labels_shadow(...)` pour tracer ce qui
  aurait été appliqué (dry_run pendant shadow mode, pas de mutation Gmail).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Import lib co-located
_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from lib.labels import (  # noqa: E402
    LABEL_DRAFT,
    LABEL_HR,
    LABEL_PERSONAL,
    LABEL_PROCESSED,
    LABEL_SPAM,
    LABEL_URGENT,
    LABEL_WORK_MAIN,
    LABEL_WORK_OPS,
)
from lib.shadow_out import record_labels as _record_labels  # noqa: E402

# Patterns thématiques — exemples génériques, à adapter à votre secteur.
PATTERNS_WORK_OPS = re.compile(
    r"\b(idec|medecin.?coord|residents?\s+(?:age|dependants?)|"
    r"ars\s+\w+|cnsa)\b",
    re.IGNORECASE,
)
PATTERNS_HR = re.compile(
    r"\b(rh\s|candidature\s|recrutement\s|accident.?travail|salaries?\s|"
    r"bulletin.?paie|urssaf|dreets|carsat|cpam|aide.?soignante?|"
    r"auxiliaire\s+de\s+vie|infirmi(?:er|ere)|as\s+diplom)\b",
    re.IGNORECASE,
)
PATTERNS_WORK_MAIN = re.compile(
    r"\b(prospect|pilote|investisseur|incubateur|scaleway|ovhcloud?\s+(?:hds|scale)|"
    r"postgrest|supabase|logiciel\s+(?:ehpad|metier)|"
    r"domiciliation\s+(?:sasu|societe|soci[ée]t[ée])|"
    r"legalplace|legal-place|greffe|inpi|bodacc|kbis|"
    r"qonto|stripe\s+account|urssaf\s+(?:entrep|societ)|"
    r"sasu|sas)\b",
    re.IGNORECASE,
)

# Domaines émetteurs → thème WORK_MAIN direct
WORK_MAIN_DOMAINS: set[str] = set()


@dataclass
class LabelRoute:
    priority: str | None
    theme: str


def _theme_from_signals(sender_domain: str, subcategory: str, subject: str) -> str:
    """Déduit le thème depuis domaine émetteur + subcategory classifier + subject."""
    if sender_domain.lower() in WORK_MAIN_DOMAINS:
        return LABEL_WORK_MAIN
    haystack = f"{subcategory} {subject}"
    if PATTERNS_WORK_OPS.search(haystack):
        return LABEL_WORK_OPS
    if PATTERNS_HR.search(haystack):
        return LABEL_HR
    if PATTERNS_WORK_MAIN.search(haystack):
        return LABEL_WORK_MAIN
    return LABEL_PERSONAL


def route_labels(
    *,
    category: str,
    subcategory: str,
    should_draft: bool,
    sender_domain: str,
    subject: str,
) -> list[str]:
    """Retourne la liste des labels Gmail à appliquer.

    Inclut toujours `processed-by-curator` pour l'idempotence.
    """
    labels = [LABEL_PROCESSED]

    if category == "URGENT":
        labels.append(LABEL_URGENT)
    elif category == "SPAM":
        # SPAM = UN SEUL label fonctionnel pour éviter faux positifs
        labels.append(LABEL_SPAM)
        return labels
    elif category == "ACTION" and should_draft:
        labels.append(LABEL_DRAFT)

    theme = _theme_from_signals(sender_domain, subcategory, subject)
    if theme:
        labels.append(theme)

    return labels


def record_labels_shadow(
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
    """Append les labels dans shadow_out (shadow mode dry_run).

    Pendant le shadow mode, aucune mutation Gmail n'est effectuée — on
    trace juste ce qui SERAIT appliqué pour qu'un juge externe compare avec
    la baseline.
    """
    return _record_labels(
        thread_id=thread_id,
        subject=subject,
        sender_domain=sender_domain,
        category=category,
        subcategory=subcategory,
        should_draft=should_draft,
        labels=labels,
        shadow_dir=shadow_dir,
    )


__all__ = ["route_labels", "LabelRoute", "record_labels_shadow"]
