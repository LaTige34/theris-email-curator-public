"""Catalogue des labels Gmail utilisés par email-curator.

Règles de routage :
    - Un email peut recevoir plusieurs labels : 1 "priorité"
      (URGENT/DRAFT-REQUIRED/SPAM) + 1 "thématique"
      (WORK-MAIN/WORK-OPS/HR/PERSONAL).
    - SPAM = UN SEUL label fonctionnel, pas de thème (anti-faux-positif).
    - processed-by-curator toujours présent (idempotence).

Les noms de labels sont configurables : pour adapter à votre workspace,
changer simplement les constantes LABEL_* ci-dessous.
"""

from __future__ import annotations

# Priorité (exactement 0 ou 1 parmi ces 3)
LABEL_URGENT = "curator/URGENT"
LABEL_DRAFT = "curator/DRAFT-REQUIRED"
LABEL_SPAM = "curator/SPAM"

# Thématique (exactement 0 ou 1 parmi ces 4, sauf SPAM)
# WORK_MAIN  = activité principale (votre entreprise)
# WORK_OPS   = activité opérationnelle secondaire (client principal,
#              partenaire stratégique)
# HR         = ressources humaines (payroll, contrats, URSSAF, etc.)
# PERSONAL   = emails personnels (non-pro)
LABEL_WORK_MAIN = "curator/WORK-MAIN"
LABEL_WORK_OPS = "curator/WORK-OPS"
LABEL_HR = "curator/HR"
LABEL_PERSONAL = "curator/PERSONAL"

# Meta (toujours appliqué)
LABEL_PROCESSED = "processed-by-curator"

ALL_LABELS = (
    LABEL_URGENT,
    LABEL_DRAFT,
    LABEL_SPAM,
    LABEL_WORK_MAIN,
    LABEL_WORK_OPS,
    LABEL_HR,
    LABEL_PERSONAL,
    LABEL_PROCESSED,
)

PRIORITY_LABELS = frozenset({LABEL_URGENT, LABEL_DRAFT, LABEL_SPAM})
THEME_LABELS = frozenset(
    {LABEL_WORK_MAIN, LABEL_WORK_OPS, LABEL_HR, LABEL_PERSONAL}
)

# Aliases retro-compat (codes historiques : THERIS=WORK_MAIN, BELLEVISTE=WORK_OPS)
LABEL_THERIS = LABEL_WORK_MAIN
LABEL_BELLEVISTE = LABEL_WORK_OPS
LABEL_RH = LABEL_HR
LABEL_PERSO = LABEL_PERSONAL

__all__ = [
    "LABEL_URGENT",
    "LABEL_DRAFT",
    "LABEL_SPAM",
    "LABEL_WORK_MAIN",
    "LABEL_WORK_OPS",
    "LABEL_HR",
    "LABEL_PERSONAL",
    "LABEL_PROCESSED",
    "ALL_LABELS",
    "PRIORITY_LABELS",
    "THEME_LABELS",
    # aliases
    "LABEL_THERIS",
    "LABEL_BELLEVISTE",
    "LABEL_RH",
    "LABEL_PERSO",
]
