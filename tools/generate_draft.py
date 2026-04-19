"""generate_draft — Générateur de brouillons ACTION avec footer AI Act.

Footer AI Act art. 50 (Règlement UE 2024/1689) obligatoire quand un LLM
est impliqué dans la rédaction, opt-out possible si le template est servi
tel quel (aucun appel LLM effectif).

Intégration safety : le wrapper d'appel LLM (hors de ce module) doit être
décoré `@with_safety_net(skill="email-curator", ...)` pour retry +
circuit breaker + alerting Telegram (lib/safety.py).

Shadow mode :
- Après génération, appeler `record_draft_shadow(...)` pour tracer le draft
  qui AURAIT été envoyé (dry_run pendant shadow mode, aucun envoi Gmail).
  `draft_template_chosen` + `provider` inclus pour comparaison externe.

Personnalisation :
- Variable `DEFAULT_SIGNATURE` → changez pour votre signature.
- `_TEMPLATES` → 8 templates FR génériques, personnalisables à votre activité.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Import shadow_out co-located
_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from lib.shadow_out import record_draft as _record_draft  # noqa: E402

# Signature par défaut — à personnaliser (ou passer `signature=...` à generate_draft)
DEFAULT_SIGNATURE = (
    "Cordialement,\n\n"
    "<YOUR_NAME>\n"
    "<YOUR_TITLE>\n"
    "<YOUR_PHONE>"
)

# Footer AI Act art. 50 — conformité Règlement (UE) 2024/1689
AI_DISCLOSURE_FOOTER_ANTHROPIC = (
    "---\n"
    "Rédigé avec assistance IA (Anthropic Claude Haiku). Validé par l'expéditeur "
    "avant envoi. Conformément au Règlement (UE) 2024/1689 sur l'intelligence "
    "artificielle (AI Act), art. 50."
)
AI_DISCLOSURE_FOOTER_MISTRAL = (
    "---\n"
    "Rédigé avec assistance IA (Mistral Small, hébergement France). Validé par "
    "l'expéditeur avant envoi. Conformément au Règlement (UE) 2024/1689 sur "
    "l'intelligence artificielle (AI Act), art. 50."
)


# Templates génériques — à adapter à votre activité
_TEMPLATES: dict[str, str] = {
    "candidature_soignant": (
        "Merci pour votre candidature. Nous l'avons bien réceptionnée.\n\n"
        "Conformément à notre politique RH, vous recevrez une réponse sous "
        "7 jours maximum. En cas d'intérêt, nous vous contacterons pour "
        "convenir d'un entretien téléphonique ou sur site."
    ),
    "candidature_medecin_coord": (
        "Merci pour votre candidature au poste de médecin coordonnateur. "
        "Ce profil étant stratégique, nous souhaiterions vous rencontrer "
        "rapidement.\n\n"
        "Pourriez-vous me proposer 2 à 3 créneaux de RDV téléphonique ou "
        "visioconférence dans les 7 jours à venir ?"
    ),
    "info_commerciale": (
        "Merci pour votre intérêt.\n\n"
        "Vous pouvez consulter notre présentation et nos fonctionnalités sur "
        "<YOUR_WEBSITE>. Pour une démo produit personnalisée ou un devis, je "
        "vous propose un RDV de 30 min — précisez-moi vos contraintes "
        "horaires cette semaine ou la suivante."
    ),
    "admission_ehpad": (
        "Merci pour votre demande d'admission. Afin de constituer le dossier, "
        "voici les pièces à nous transmettre :\n"
        "- Grille GIR récente (évaluation AGGIR par le médecin traitant)\n"
        "- Certificat médical du médecin traitant\n"
        "- Dossier social Cerfa n°14732*03 (demande unique)\n"
        "- Ressources et imposition N-1\n\n"
        "Une fois ces pièces reçues, nous convenons d'un RDV de visite."
    ),
    "question_famille": (
        "Bonjour, nous avons bien reçu votre message. "
        "Notre référent vous rappellera dans les 24 heures pour répondre à "
        "votre question.\n\n"
        "Si la demande est urgente, contactez directement notre standard."
    ),
    "devis_petit": (
        "Merci pour votre devis. Nous l'étudions.\n\n"
        "Pour finaliser notre décision, pourriez-vous préciser les éléments "
        "suivants : délai de livraison, conditions de paiement, garanties."
    ),
    "relance_impayee_amiable": (
        "Nous accusons réception de votre relance.\n\n"
        "Le règlement sera effectué dans les meilleurs délais — sauf erreur "
        "de notre part, nous vous confirmons le paiement d'ici 7 jours ouvrés."
    ),
    "generic": (
        "Bonjour, votre message a bien été reçu. Je vous répondrai "
        "personnellement dans les meilleurs délais."
    ),
}


# Ordre de priorité : substring match insensitive, premier match gagne.
_ROUTING: list[tuple[str, str]] = [
    ("medecin coord", "candidature_medecin_coord"),
    ("médecin coord", "candidature_medecin_coord"),
    ("candidature", "candidature_soignant"),
    ("admission", "admission_ehpad"),
    ("famille", "question_famille"),
    ("info commerciale", "info_commerciale"),
    ("demande info", "info_commerciale"),
    ("devis fournisseur", "devis_petit"),
    ("devis", "devis_petit"),
    ("relance impay", "relance_impayee_amiable"),
]


def draft_template_for(subcategory: str) -> str:
    """Retourne le template le plus proche ou le générique par défaut."""
    sc = (subcategory or "").lower()
    for key, tmpl_key in _ROUTING:
        if key in sc:
            return _TEMPLATES[tmpl_key]
    return _TEMPLATES["generic"]


def draft_template_key_for(subcategory: str) -> str:
    """Retourne la CLÉ du template utilisé (pour shadow_out traçabilité)."""
    sc = (subcategory or "").lower()
    for key, tmpl_key in _ROUTING:
        if key in sc:
            return tmpl_key
    return "generic"


def build_draft_user_prompt(
    *,
    subject: str,
    sender_domain: str,
    body_preview: str,
    subcategory: str,
    template: str,
) -> str:
    """Prompt user envoyé au LLM pour personnaliser le template."""
    return (
        "Tu rédiges un brouillon de réponse email professionnel.\n\n"
        f"Subcategory détectée : {subcategory}\n"
        f"Email reçu — domain : {sender_domain}\n"
        f"Subject : {subject}\n"
        f"Extrait body :\n{body_preview[:500]}\n\n"
        f"TEMPLATE de référence :\n{template}\n\n"
        "Consignes :\n"
        "- Écris UNIQUEMENT le corps du mail (sans sujet, sans signature — "
        "elles seront ajoutées en post-traitement).\n"
        "- Ton professionnel, chaleureux mais concis (≤ 150 mots).\n"
        "- Adapte le template au contenu spécifique de l'email reçu.\n"
        "- Commence par 'Bonjour,' ou 'Bonjour [Prénom],' si tu peux l'inférer.\n"
        "- Ne promets pas ce qui n'est pas dans le template.\n"
        "- Pas de Markdown, texte brut Gmail."
    )


CLASSIFIER_DRAFT_SYSTEM = (
    "Tu es un rédacteur professionnel discret. Tu produis des brouillons de "
    "réponses email. Réponds toujours en français neutre formel. Jamais "
    "d'emoji. Jamais de promesse non tenable."
)


def _ai_footer_for_provider(provider: str) -> str:
    p = (provider or "").lower()
    if p.startswith("mistral"):
        return AI_DISCLOSURE_FOOTER_MISTRAL
    return AI_DISCLOSURE_FOOTER_ANTHROPIC


def generate_draft(
    *,
    llm_client: Any,
    subject: str,
    sender_domain: str,
    body_preview: str,
    subcategory: str,
    signature: str = DEFAULT_SIGNATURE,
    provider: str = "anthropic",
    include_ai_disclosure: bool = True,
) -> str:
    """Génère le texte complet du brouillon (corps LLM + signature + AI footer).

    Args:
        llm_client: Objet exposant `.chat(messages, system, ...)`.
        subject, sender_domain, body_preview, subcategory: Contexte email.
        signature: Signature (par défaut DEFAULT_SIGNATURE).
        provider: "anthropic" | "mistral" — détermine quel footer insérer.
        include_ai_disclosure: False uniquement si fallback sans LLM.

    Fallback safe : si le LLM plante → template brut + signature SANS footer
    AI (car pas d'IA effective dans la boucle).
    """
    template = draft_template_for(subcategory)
    prompt = build_draft_user_prompt(
        subject=subject,
        sender_domain=sender_domain,
        body_preview=body_preview,
        subcategory=subcategory,
        template=template,
    )
    llm_was_called = False
    try:
        body = llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            system=CLASSIFIER_DRAFT_SYSTEM,
            tier="standard",
            agent_name="email-curator-draft",
            max_tokens=500,
            temperature=0.3,
        )
        llm_was_called = True
    except Exception:
        body = template

    body = (body or "").strip()
    if not body:
        body = template
        llm_was_called = False

    draft = f"{body}\n\n{signature}"
    if include_ai_disclosure and llm_was_called:
        draft += f"\n\n{_ai_footer_for_provider(provider)}"
    return draft


def record_draft_shadow(
    *,
    thread_id: str,
    subject: str,
    sender_domain: str,
    subcategory: str,
    draft_text: str,
    provider: str = "anthropic",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_estimate_eur: float = 0.0,
    shadow_dir: Path | str | None = None,
) -> Path:
    """Append le draft dans shadow_out (shadow mode dry_run).

    `draft_template_chosen` est déterminé automatiquement depuis la
    subcategory via `draft_template_key_for`. mask_pii appliqué sur le corps
    avant écriture côté `lib.shadow_out`.
    """
    return _record_draft(
        thread_id=thread_id,
        subject=subject,
        sender_domain=sender_domain,
        subcategory=subcategory,
        draft_text=draft_text,
        draft_template_chosen=draft_template_key_for(subcategory),
        provider=provider,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate_eur=cost_estimate_eur,
        shadow_dir=shadow_dir,
    )


__all__ = [
    "DEFAULT_SIGNATURE",
    "AI_DISCLOSURE_FOOTER_ANTHROPIC",
    "AI_DISCLOSURE_FOOTER_MISTRAL",
    "draft_template_for",
    "draft_template_key_for",
    "build_draft_user_prompt",
    "generate_draft",
    "record_draft_shadow",
    "CLASSIFIER_DRAFT_SYSTEM",
]
