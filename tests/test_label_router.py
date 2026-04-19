"""Tests routeur labels Gmail curator/*.

Inclut les régressions anti-faux-positif WORK_OPS + SPAM single-label.
Les aliases historiques (LABEL_BELLEVISTE = LABEL_WORK_OPS, etc.) sont
exposés pour maintenir les tests de routage par mot-clé secteur santé.
"""

from __future__ import annotations

import pytest

from lib.neo_labels import (
    LABEL_BELLEVISTE,  # alias WORK_OPS — régressions patterns santé
    LABEL_DRAFT,
    LABEL_HR,
    LABEL_PERSONAL,
    LABEL_PERSO,  # alias PERSONAL
    LABEL_PROCESSED,
    LABEL_RH,  # alias HR
    LABEL_SPAM,
    LABEL_THERIS,  # alias WORK_MAIN
    LABEL_URGENT,
    LABEL_WORK_MAIN,
    LABEL_WORK_OPS,
)
from tools.apply_labels import route_labels


def test_urgent_pattern_match_gets_urgent_plus_work_main():
    """Pattern 'scalingo' matche WORK_MAIN via les patterns infra."""
    labels = route_labels(
        category="URGENT",
        subcategory="Incident technique critique scalingo prod",
        should_draft=False,
        sender_domain="github.com",
        subject="Deploy failed scalingo",
    )
    assert LABEL_PROCESSED in labels
    assert LABEL_URGENT in labels
    assert LABEL_WORK_MAIN in labels


def test_urgent_ars_gets_urgent_plus_work_ops():
    """Pattern 'ars occitanie' / 'medecin coord' matche WORK_OPS (santé)."""
    labels = route_labels(
        category="URGENT",
        subcategory="ARS Occitanie signalement EIG",
        should_draft=False,
        sender_domain="ars.sante.fr",
        subject="Déclaration EIG — medecin coordonnateur",
    )
    assert LABEL_URGENT in labels
    assert LABEL_WORK_OPS in labels


def test_action_draft_gets_draft_required():
    labels = route_labels(
        category="ACTION",
        subcategory="Candidature aide-soignante",
        should_draft=True,
        sender_domain="outlook.fr",
        subject="Candidature poste AS",
    )
    assert LABEL_DRAFT in labels
    assert LABEL_HR in labels  # candidature → HR


def test_action_without_draft_no_draft_label():
    labels = route_labels(
        category="ACTION",
        subcategory="Question famille résident medecin coord",
        should_draft=False,
        sender_domain="gmail.com",
        subject="Demande visite médecin coordonnateur",
    )
    assert LABEL_DRAFT not in labels
    assert LABEL_WORK_OPS in labels


def test_spam_gets_spam_single_label():
    labels = route_labels(
        category="SPAM",
        subcategory="Démarchage photocopieur",
        should_draft=False,
        sender_domain="office-deals.example.com",
        subject="Promo photocopieur -40%",
    )
    assert LABEL_SPAM in labels


def test_spam_ignores_theme_false_positives():
    """Régression anti-FP : SPAM NE DOIT JAMAIS recevoir de label thématique."""
    labels = route_labels(
        category="SPAM",
        subcategory="Démarchage résidents EHPAD imaginaire",
        should_draft=False,
        sender_domain="random-ads.example.com",
        subject="Bienvenue Cercle - offre résident famille EHPAD",
    )
    assert LABEL_SPAM in labels
    assert LABEL_WORK_OPS not in labels
    assert LABEL_PERSONAL not in labels
    assert LABEL_WORK_MAIN not in labels
    assert LABEL_HR not in labels


def test_legalplace_domiciliation_routed_to_work_main():
    """Courrier domiciliation LegalPlace pour SASU → WORK_MAIN."""
    labels = route_labels(
        category="ACTION",
        subcategory="Courrier domiciliation SASU reçu LegalPlace",
        should_draft=False,
        sender_domain="email.legalplace.fr",
        subject="Vous avez du courrier !",
    )
    assert LABEL_WORK_MAIN in labels
    assert LABEL_PROCESSED in labels


def test_qonto_banque_pro_routed_to_work_main():
    """Compte bancaire pro (Qonto) → WORK_MAIN."""
    labels = route_labels(
        category="ACTION",
        subcategory="Qonto - compte pro SASU - alerte solde",
        should_draft=False,
        sender_domain="qonto.com",
        subject="Alerte solde compte SASU",
    )
    assert LABEL_WORK_MAIN in labels


def test_work_ops_requires_specific_keyword():
    """WORK_OPS exige idec / médecin coord / ARS / etc. pour matcher."""
    labels = route_labels(
        category="INFO",
        subcategory="Nouvelle tarification CPOM EHPAD 2027",
        should_draft=False,
        sender_domain="newsletter-sector.example.com",
        subject="Newsletter : marché EHPAD France",
    )
    # "EHPAD" seul ne suffit pas (anti-FP)
    assert LABEL_WORK_OPS not in labels
    labels2 = route_labels(
        category="ACTION",
        subcategory="Admission résident medecin coord",
        should_draft=True,
        sender_domain="gmail.com",
        subject="Demande admission — medecin coordonnateur",
    )
    assert LABEL_WORK_OPS in labels2


def test_info_without_theme_defaults_personal():
    labels = route_labels(
        category="INFO",
        subcategory="Confirmation commande personnelle",
        should_draft=False,
        sender_domain="amazon.fr",
        subject="Your order confirmation",
    )
    assert LABEL_PERSONAL in labels
    assert LABEL_URGENT not in labels


def test_work_main_domains_hook():
    """Vérifie que WORK_MAIN_DOMAINS permet un routage par domaine."""
    from tools import apply_labels

    original = set(apply_labels.WORK_MAIN_DOMAINS)
    try:
        apply_labels.WORK_MAIN_DOMAINS.add("mycompany.example.com")
        labels = route_labels(
            category="INFO",
            subcategory="news",
            should_draft=False,
            sender_domain="mycompany.example.com",
            subject="Newsletter interne",
        )
        assert LABEL_WORK_MAIN in labels
    finally:
        apply_labels.WORK_MAIN_DOMAINS.clear()
        apply_labels.WORK_MAIN_DOMAINS.update(original)


def test_processed_always_applied():
    for cat in ("URGENT", "ACTION", "INFO", "SPAM"):
        labels = route_labels(
            category=cat,
            subcategory="x",
            should_draft=False,
            sender_domain="example.com",
            subject="test",
        )
        assert LABEL_PROCESSED in labels


def test_legacy_aliases_equivalent_to_new_constants():
    assert LABEL_BELLEVISTE == LABEL_WORK_OPS
    assert LABEL_THERIS == LABEL_WORK_MAIN
    assert LABEL_RH == LABEL_HR
    assert LABEL_PERSO == LABEL_PERSONAL
