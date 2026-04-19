---
name: email-curator
description: Triage d'emails pour fondateurs solo et opérateurs — classifie chaque message (URGENT/ACTION/INFO/SPAM) via un LLM (Claude Haiku 4.5 ou Mistral Small), applique des labels Gmail sémantiques, génère un brouillon FR pro avec footer AI Act art. 50, et envoie un digest Telegram premium. Safety net complet (retry + circuit breaker + alerting) et redaction PII systématique avant logs et alertes. Use when the user wants to triage their Gmail inbox, auto-draft replies to recurring email patterns, or monitor high-signal emails via Telegram.
version: 0.1.0
license: MIT
author: THERIS — open-sourced by Mathieu Desobry
tags:
  - email
  - gmail
  - triage
  - productivity
  - founder-ops
  - llm
  - claude-haiku
  - mistral
  - ai-act
  - gdpr
repository: https://github.com/LaTige34/theris-email-curator-public
---

# email-curator

Skill Python pour triage automatique d'emails, pensé pour un fondateur
solo ou un opérateur qui reçoit 50-200 mails/jour et veut :

- Ne plus **rater** un URGENT (ARS, CPAM, LRAR, prospect chaud)
- Auto-**pré-rédiger** les réponses récurrentes (candidatures, devis, demandes info)
- Recevoir un **digest Telegram quotidien** propre avec deep-links Gmail
- Respecter **AI Act art. 50** (transparence IA dans les drafts)
- Garder **zéro PII dans les logs** via redaction systématique

## Installation

```bash
git clone https://github.com/LaTige34/theris-email-curator-public.git
cd theris-email-curator-public
python3 -m venv .venv && . .venv/bin/activate
pip install pytest pyyaml
pytest tests/ -v  # 76 tests, doivent tous passer
```

## Composition

- `prompts/classifier.md` — prompt système classifier (URGENT/ACTION/INFO/SPAM)
- `prompts/draft_generator.md` — 7 templates FR pro + règles rédaction
- `prompts/digest_builder.md` — format digest Telegram premium
- `prompts/ai_disclosure_footer.md` — footer AI Act art. 50 (Anthropic / Mistral)
- `tools/classify_email.py` — validation schema JSON post-LLM + anti-injection
- `tools/apply_labels.py` — routeur labels Gmail (priorité + thème)
- `tools/generate_draft.py` — fusion template + LLM + signature + footer AI
- `tools/build_digest.py` — digest Markdown Telegram avec emojis contextuels
- `lib/safety.py` — retry exponentiel + circuit breaker + alerting + audit log
- `lib/shadow_out.py` — shadow mode JSONL (comparaison pipeline v1 vs v2)
- `lib/neo_labels.py` — catalogue labels (WORK_MAIN / WORK_OPS / HR / PERSONAL)
- `lib/senders.yaml.example` — template fournisseurs critiques (à copier)
- `scripts/rotate_shadow_out.sh` — purge quotidienne shadow_out/ > 30j

## Pipeline

```
Email Gmail entrant
        ↓
classify_email (Haiku 4.5 ou Mistral Small si PII)
        ↓
apply_labels → Gmail curator/URGENT | curator/DRAFT-REQUIRED | curator/SPAM
                          + THEME : WORK-MAIN | WORK-OPS | HR | PERSONAL
        ↓
   ├─ URGENT   → alerte immédiate (SMS / voice call / Telegram)
   ├─ ACTION   → generate_draft (7 templates FR + footer AI Act)
   │           → digest Telegram (batching)
   ├─ INFO     → digest Telegram uniquement
   └─ SPAM     → label silent, pas de digest, pas de voix
```

## Personnalisation minimale

1. Copier `lib/senders.yaml.example` → `lib/senders.yaml` et remplir avec vos
   domaines stratégiques (banque, URSSAF, client principal…).
2. Dans `tools/generate_draft.py`, remplacer `DEFAULT_SIGNATURE` :
   `<YOUR_NAME>` / `<YOUR_TITLE>` / `<YOUR_PHONE>`.
3. Dans `prompts/draft_generator.md`, remplacer `<YOUR_WEBSITE>` dans les
   templates commerciaux.
4. Dans `tools/apply_labels.py`, adapter `PATTERNS_WORK_MAIN` /
   `PATTERNS_WORK_OPS` / `PATTERNS_HR` à votre vocabulaire métier.

## Conformité

- **AI Act art. 50** — Footer transparence IA inséré automatiquement dans
  tout draft généré par LLM (Règlement UE 2024/1689, applicable 2 août 2026).
- **RGPD / HDS** — `mask_pii()` appliqué avant toute écriture shadow_out,
  avant tout log, avant toute alerte Telegram. Patterns couverts : email,
  téléphone FR (+33 / 06), NIR 13/15 chiffres, adresses postales.
- **PII router** — Si `phi_detected=true`, bascule automatique vers Mistral
  Small (hébergement France) pour la génération du draft.

## Tests

76 tests pytest offline (zero I/O réseau, zero clé API requise) :

```
tests/test_classifier.py         — 16 tests validation schema + anti-injection
tests/test_label_router.py       — 14 tests routing + anti-faux-positif
tests/test_draft_generator.py    — 12 tests templates + AI Act footer
tests/test_circuit_breaker.py    — 12 tests safety (retry + breaker + mask)
tests/test_shadow_out.py         — 22 tests shadow JSONL + merge last-wins
```

## Prérequis runtime

- Python ≥ 3.10
- `pyyaml` pour `senders.yaml`
- Un client LLM minimal (ex: `anthropic>=0.40` ou `mistralai>=1.0`) injecté
  via DI — `llm_client.chat(messages=..., system=..., ...)`.
- Un client Gmail (OAuth2) pour appliquer les labels et créer des drafts.
- Un token Bot Telegram (optionnel) pour les digests et alertes.

## License

MIT — voir `LICENSE`. Open-sourcé par THERIS (fondateur Mathieu Desobry)
dans le cadre de la contribution à l'écosystème Claude Skills / Agent Skills.
