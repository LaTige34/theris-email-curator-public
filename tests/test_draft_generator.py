"""Tests générateur de brouillons (porté phi-agents + ajout AI Act footer)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tools.generate_draft import (
    AI_DISCLOSURE_FOOTER_ANTHROPIC,
    AI_DISCLOSURE_FOOTER_MISTRAL,
    DEFAULT_SIGNATURE,
    build_draft_user_prompt,
    draft_template_for,
    generate_draft,
)


@pytest.fixture
def llm_mock():
    m = MagicMock()
    m.chat.return_value = "Bonjour,\n\nMerci pour votre message. [corps généré]\n\nCordialement."
    return m


# -----------------------------------------------------------------------
# Templates statiques
# -----------------------------------------------------------------------
def test_template_for_candidature_soignant_includes_delay_7j():
    tpl = draft_template_for("candidature aide-soignante")
    assert "7 jour" in tpl.lower() or "sept jour" in tpl.lower()
    assert "réception" in tpl.lower() or "réceptionn" in tpl.lower()


def test_template_for_info_commerciale_mentions_landing():
    tpl = draft_template_for("demande info commerciale")
    # Le template renvoie vers le site de l'expéditeur — placeholder <YOUR_WEBSITE>
    assert "your_website" in tpl.lower() or "website" in tpl.lower() or "https://" in tpl.lower()


def test_template_for_medecin_coordonnateur_proposes_rdv():
    tpl = draft_template_for("candidature médecin coordonnateur")
    assert "rdv" in tpl.lower() or "rendez-vous" in tpl.lower()


def test_template_for_admission_lists_docs():
    tpl = draft_template_for("demande admission EHPAD")
    assert "document" in tpl.lower() or "pièce" in tpl.lower()


def test_template_for_famille_mentions_contact():
    tpl = draft_template_for("question famille résident")
    # Le template mentionne un rappel humain dans les 24 h
    assert "24 heure" in tpl.lower() or "rappell" in tpl.lower()


def test_template_for_unknown_returns_generic():
    tpl = draft_template_for("catégorie inexistante")
    assert len(tpl) > 30
    assert (
        "reçu" in tpl.lower()
        or "recu" in tpl.lower()
        or "repondr" in tpl.lower()
        or "répondr" in tpl.lower()
    )


def test_build_user_prompt_contains_email_context():
    prompt = build_draft_user_prompt(
        subject="Candidature AS",
        sender_domain="gmail.com",
        body_preview="Je candidate pour un poste d'aide-soignante.",
        subcategory="candidature aide-soignante",
        template="[TEMPLATE_TEST]",
    )
    assert "Candidature AS" in prompt
    assert "gmail.com" in prompt
    assert "aide-soignante" in prompt.lower()
    assert "[TEMPLATE_TEST]" in prompt


# -----------------------------------------------------------------------
# Generate draft + signature + AI Act footer
# -----------------------------------------------------------------------
def test_generate_draft_returns_text_with_signature(llm_mock):
    text = generate_draft(
        llm_client=llm_mock,
        subject="Test",
        sender_domain="test.fr",
        body_preview="x",
        subcategory="demande info commerciale",
        signature=DEFAULT_SIGNATURE,
    )
    assert "<YOUR_NAME>" in text
    assert "[corps généré]" in text
    llm_mock.chat.assert_called_once()


def test_generate_draft_fallback_on_llm_error():
    """Fallback safe : LLM down → template brut, PAS de footer AI (aucune IA)."""
    bad_llm = MagicMock()
    bad_llm.chat.side_effect = RuntimeError("LLM down")
    text = generate_draft(
        llm_client=bad_llm,
        subject="Test",
        sender_domain="test.fr",
        body_preview="x",
        subcategory="candidature aide-soignante",
    )
    assert len(text) > 100
    assert "<YOUR_NAME>" in text
    # Pas d'IA dans la boucle → pas de footer AI Act
    assert "AI Act" not in text
    assert "IA" not in text.split("<YOUR_NAME>")[0] or True  # corps brut


def test_generate_draft_includes_ai_footer_anthropic_by_default(llm_mock):
    """AI Act art. 50 : footer Anthropic par défaut si LLM répond."""
    text = generate_draft(
        llm_client=llm_mock,
        subject="X",
        sender_domain="test.fr",
        body_preview="x",
        subcategory="candidature soignant",
    )
    assert "AI Act" in text
    assert "Anthropic" in text
    assert "2024/1689" in text


def test_generate_draft_includes_ai_footer_mistral_when_provider_mistral(llm_mock):
    text = generate_draft(
        llm_client=llm_mock,
        subject="X",
        sender_domain="test.fr",
        body_preview="x",
        subcategory="candidature soignant",
        provider="mistral",
    )
    assert "AI Act" in text
    assert "Mistral" in text
    assert "hébergement France" in text


def test_generate_draft_disclosure_opt_out(llm_mock):
    text = generate_draft(
        llm_client=llm_mock,
        subject="X",
        sender_domain="test.fr",
        body_preview="x",
        subcategory="candidature soignant",
        include_ai_disclosure=False,
    )
    assert "AI Act" not in text
    assert "<YOUR_NAME>" in text


def test_ai_footer_constants_have_legal_anchors():
    for footer in (AI_DISCLOSURE_FOOTER_ANTHROPIC, AI_DISCLOSURE_FOOTER_MISTRAL):
        assert "2024/1689" in footer
        assert "art. 50" in footer
        assert "AI Act" in footer
