"""build_digest — Telegram digest premium (via Bot API).

Format Markdown FR avec emojis contextuels, deep-links Gmail, séparateurs
visuels, placeholder PII.

Policy : URGENT et SPAM sont FILTRÉS OUT (URGENT = voix directe en amont,
SPAM = muet). `phi_detected=True` → subject+summary remplacés par un
placeholder (dernier barrage PII avant Telegram Bot API hébergée US).
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

try:
    from loguru import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)  # type: ignore


MAX_TELEGRAM_LEN = 4000
DIGEST_PHI_PLACEHOLDER = "Contenu sensible, consulter Gmail"

_MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


@dataclass
class DigestEntry:
    category: str
    subcategory: str
    sender_domain: str
    subject_safe: str
    summary_safe: str
    phi_detected: bool = False
    gmail_link: str = ""
    thread_id: str = ""


def _format_date_fr(now: datetime) -> str:
    """`18 avril 2026 · 14:35`"""
    return f"{now.day} {_MOIS_FR[now.month - 1]} {now.year} · {now.strftime('%H:%M')}"


# Mapping emojis contextuels — configurable par l'utilisateur.
# Clé = sous-chaîne (case-insensitive) matchée dans `subcategory` OU `sender_domain`.
# Valeur = emoji affiché devant l'entrée dans le digest.
_THEME_EMOJI: dict[str, str] = {
    # Activité principale
    "prospect": "🎯",
    "pilote": "🎯",
    "investisseur": "💼",
    "scalingo": "🟦",
    "ovh": "🟦",
    "hetzner": "🟦",
    # Santé / EHPAD (exemple — à adapter)
    "idec": "🏥",
    "medecin": "🏥",
    "résident": "🏥",
    "ars": "🏥",
    # RH
    "candidature": "👤",
    "aide-soignante": "👤",
    "infirmi": "👤",
    "urssaf": "👤",
    "cpam": "👤",
    "dreets": "👤",
    # Juridique / admin société
    "legalplace": "📜",
    "impots": "🧾",
    "dgfip": "🧾",
    "greffe": "📜",
    "inpi": "📜",
    "bodacc": "📜",
    # Banque
    "qonto": "🏦",
    "stripe": "🏦",
    "crédit agricole": "🏦",
    "bnp": "🏦",
    # Factures
    "edf": "⚡",
    "engie": "⚡",
    "veolia": "💧",
    "orange": "📡",
    "free": "📡",
    "sfr": "📡",
    "bouygues": "📡",
    # Perso
    "ameli": "💊",
    "mutuelle": "💊",
    "assurance": "🛡️",
}

_CATEGORY_EMOJI = {
    "URGENT": "🔴",
    "ACTION": "🟡",
    "INFO": "🟢",
    "SPAM": "⚫",
}


def _contextual_emoji(subcategory: str, sender_domain: str) -> str:
    haystack = f"{subcategory} {sender_domain}".lower()
    for keyword, emoji in _THEME_EMOJI.items():
        if keyword in haystack:
            return emoji
    return "📧"


def _gmail_link(thread_id: str) -> str:
    if not thread_id:
        return ""
    return f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"


def _format_entry(entry: DigestEntry) -> str:
    emoji = _contextual_emoji(entry.subcategory, entry.sender_domain)
    link = entry.gmail_link or _gmail_link(entry.thread_id)

    if entry.phi_detected:
        line1 = f"{emoji} *{entry.subcategory}* · `{entry.sender_domain}`"
        line2 = f"   _{DIGEST_PHI_PLACEHOLDER}_"
    else:
        subject = entry.subject_safe.strip() or "(sans objet)"
        if len(subject) > 75:
            subject = subject[:72] + "…"
        line1 = f"{emoji} *{subject}*"
        line2 = f"   _{entry.subcategory}_ · `{entry.sender_domain}`"

    if link:
        line2 += f" · [📂]({link})"

    return f"{line1}\n{line2}"


def build_digest(
    entries: Sequence[DigestEntry | object],
    now: datetime | None = None,
) -> str:
    """Construit le message Markdown Telegram.

    Returns:
        Message Markdown ≤ 4000 chars, accents FR, sans URGENT/SPAM.
    """
    now = now or datetime.now()

    filtered = [e for e in entries if e.category in ("ACTION", "INFO")]

    header = (
        f"📬 *Digest*\n"
        f"_{_format_date_fr(now)}_"
    )

    if not filtered:
        return header + "\n\n_Aucun email à traiter sur cette période._"

    actions = [e for e in filtered if e.category == "ACTION"]
    infos = [e for e in filtered if e.category == "INFO"]

    summary_bits = []
    if actions:
        summary_bits.append(f"🟡 {len(actions)} à traiter")
    if infos:
        summary_bits.append(f"🟢 {len(infos)} à lire")
    summary = " · ".join(summary_bits)

    sections: list[str] = [header, f"\n{summary}\n"]

    if actions:
        sections.append(f"━━━━━━━━━━━━━━━━━━━━")
        sections.append(f"🟡 *À TRAITER* ({len(actions)})")
        sections.append("")
        sections.extend(_format_entry(e) for e in actions)
    if infos:
        sections.append("")
        sections.append(f"━━━━━━━━━━━━━━━━━━━━")
        sections.append(f"🟢 *À LIRE* ({len(infos)})")
        sections.append("")
        sections.extend(_format_entry(e) for e in infos)

    msg = "\n".join(sections)

    if len(msg) > MAX_TELEGRAM_LEN:
        truncation_note = "\n\n_[…] digest tronqué, consulter Gmail._"
        budget = MAX_TELEGRAM_LEN - len(truncation_note)
        truncated = msg[:budget]
        last_nl = truncated.rfind("\n")
        if last_nl > 0:
            truncated = truncated[:last_nl]
        msg = truncated + truncation_note

    return msg


def send_digest(
    *,
    digest_text: str,
    chat_id: str,
    bot_token: str,
    dry_run: bool = False,
    timeout_s: float = 10.0,
) -> bool:
    """Envoie le digest sur Telegram via Bot API.

    Returns: True si API a répondu 200, False sinon.
    """
    if dry_run:
        try:
            logger.info("[build_digest] DRY-RUN ({} chars)", len(digest_text))
        except Exception:
            pass
        return True

    if not bot_token or not chat_id:
        try:
            logger.error("[build_digest] bot_token ou chat_id manquant")
        except Exception:
            pass
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "text": digest_text[:MAX_TELEGRAM_LEN + 96],
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status == 200:
                return True
            try:
                logger.error("[build_digest] status={}", resp.status)
            except Exception:
                pass
            return False
    except Exception as e:
        try:
            logger.error("[build_digest] échec envoi : {}", type(e).__name__)
        except Exception:
            pass
        return False


__all__ = [
    "DigestEntry",
    "DIGEST_PHI_PLACEHOLDER",
    "MAX_TELEGRAM_LEN",
    "build_digest",
    "send_digest",
]
