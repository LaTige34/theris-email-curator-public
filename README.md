# email-curator

> Email triage skill for solo founders and operators — LLM classifier + Gmail
> label routing + Telegram digest. Claude Skills format (`SKILL.md`).

[![Tests](https://github.com/LaTige34/theris-email-curator-public/actions/workflows/tests.yml/badge.svg)](https://github.com/LaTige34/theris-email-curator-public/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Version : 0.1.0** — 76 tests verts, zero I/O réseau en test, AI Act art. 50
compliant, redaction PII systématique.

## Pourquoi

Quand on reçoit 50-200 emails par jour en tant que fondateur solo ou opérateur
d'un établissement (EHPAD, SaaS B2B, petit cabinet), trois douleurs
récurrentes :

1. **On rate des emails URGENT** (ARS, CPAM, LRAR, prospect chaud).
2. **On répond 3 fois par jour aux mêmes patterns** (candidature,
   demande info produit, devis, relance).
3. **On scrolle Gmail en boucle** sans savoir ce qui mérite une lecture
   aujourd'hui.

`email-curator` classifie chaque mail entrant, applique des labels Gmail,
prépare des brouillons FR pro pour les actions récurrentes, et envoie un
digest Telegram propre. Résultat : **2h/jour économisées**, zéro URGENT raté.

## Features clés

- **Classifier LLM** (Claude Haiku 4.5 ou Mistral Small) avec schema JSON
  strict, anti-injection, fallback safe, coût ≈ €0,002 / email.
- **Routeur labels** Gmail multi-dimensions : priorité
  (URGENT / DRAFT-REQUIRED / SPAM) + thème (WORK_MAIN / WORK_OPS / HR /
  PERSONAL). Anti faux-positif sur SPAM (single-label) et sur thèmes
  métier (exige mot-clé spécifique, pas juste le nom du secteur).
- **Générateur drafts** avec 7 templates FR pro (candidature soignant,
  candidature médecin coord, info commerciale, admission, question
  famille, devis, relance impayé) + footer **AI Act art. 50** (transparence
  IA, Règlement UE 2024/1689).
- **Digest Telegram** Markdown avec emojis contextuels, deep-links Gmail,
  séparateurs visuels, placeholder PII automatique.
- **Safety net** (`lib/safety.py`) : retry exponentiel + circuit breaker
  3-states + AlertPump avec dédup + audit JSONL signé SHA-256.
- **PII redaction** systématique avant tout log / alert / shadow_out
  (email, téléphone FR, NIR 13/15 digits, adresse postale).
- **Shadow mode** : appender JSONL pour comparer deux pipelines (ex: v1 vs
  v2) avec merge "last-wins-non-empty" par `thread_id`.

## Installation

```bash
git clone https://github.com/LaTige34/theris-email-curator-public.git
cd theris-email-curator-public
python3 -m venv .venv
. .venv/bin/activate
pip install pytest pyyaml
pytest tests/ -v
# 76 passed in ~2 seconds
```

## Use cases

### 1. Fondateur solo EHPAD / EdTech santé

- Reçoit ARS, CPAM, candidatures médecin coordonnateur, prospects pilote,
  LegalPlace, Qonto, Scalingo
- Objectif : ne jamais rater un URGENT régulateur, pré-rédiger drafts
  candidatures et devis, digest Telegram le soir

### 2. Cadre de santé / IDEC en EHPAD

- Reçoit famille résidents, médecin coordonnateur, prestataires, RH, CPAM
- Objectif : trier urgent médical vs admin, pré-rédiger réponses famille
  (rappel 24h), notifier équipe soignante

### 3. Opérateur SaaS B2B

- Reçoit prospects, clients, investisseurs, fournisseurs infra
- Objectif : identifier prospects chauds, auto-drafter démos,
  digest journalier deals + support

## Personnalisation

### Étape 1 — Fournisseurs critiques (`lib/senders.yaml`)

Copier le template et remplir avec vos domaines stratégiques :

```bash
cp lib/senders.yaml.example lib/senders.yaml
# Éditer : remplacer les exemples par vos vrais domaines banque, URSSAF,
# client principal, fournisseurs infra
```

### Étape 2 — Signature (`tools/generate_draft.py`)

```python
DEFAULT_SIGNATURE = (
    "Cordialement,\n\n"
    "Jean Dupont\n"
    "Fondateur Example SAS\n"
    "+33 6 00 00 00 00"
)
```

### Étape 3 — Patterns thématiques (`tools/apply_labels.py`)

Adapter les regex `PATTERNS_WORK_MAIN` / `PATTERNS_WORK_OPS` / `PATTERNS_HR`
à votre vocabulaire métier. Les exemples fournis couvrent EHPAD / santé.

### Étape 4 — Templates drafts (`tools/generate_draft.py` + `prompts/draft_generator.md`)

Les templates FR sont dans le dict `_TEMPLATES`. Remplacer les placeholders
`<YOUR_WEBSITE>`, adapter le vocabulaire (ex: "médecin coord" pour santé,
"account manager" pour SaaS).

### Étape 5 — Captures digest Telegram

Voir `prompts/digest_builder.md` pour le format. Le mapping
`_THEME_EMOJI` dans `tools/build_digest.py` est personnalisable.

## Intégration LLM (wiring)

Le skill ne fait PAS les appels LLM lui-même — il attend un objet
`llm_client` avec une méthode `.chat(messages, system, ...)`. Exemple
minimal avec l'SDK Anthropic :

```python
import anthropic
from tools.generate_draft import generate_draft

class AnthropicClient:
    def __init__(self):
        self._sdk = anthropic.Anthropic()
    def chat(self, *, messages, system, tier="standard",
             agent_name=None, max_tokens=500, temperature=0.3):
        r = self._sdk.messages.create(
            model="claude-haiku-4-5",
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return r.content[0].text

draft = generate_draft(
    llm_client=AnthropicClient(),
    subject="Candidature AS",
    sender_domain="gmail.com",
    body_preview="Je candidate pour un poste d'aide-soignante.",
    subcategory="candidature aide-soignante",
)
print(draft)
```

## Intégration Gmail (wiring)

Côté Gmail, utiliser l'API Google Workspace avec les scopes
`gmail.modify` + `gmail.labels`. Le skill ne fournit pas ce wiring — voir
la doc officielle Gmail API + `google-auth-oauthlib`.

## Conformité

### AI Act art. 50 (Règlement UE 2024/1689)

Tout draft généré par LLM inclut automatiquement un footer :

```
---
Rédigé avec assistance IA (Anthropic Claude Haiku). Validé par l'expéditeur
avant envoi. Conformément au Règlement (UE) 2024/1689 sur l'intelligence
artificielle (AI Act), art. 50.
```

Opt-out possible si fallback template sans appel LLM (pas d'IA effective
dans la boucle). Variante Mistral pour basculement PII / souveraineté France.

Article 50 applicable au **2 août 2026** — le skill anticipe.

### RGPD / redaction PII

`mask_pii()` (dans `lib/safety.py`) couvre :
- Emails (`user@example.com`)
- Téléphones FR (`+33 6 12 34 56 78` / `06 12 34 56 78`)
- NIR / numéros de sécurité sociale (13 ou 15 chiffres)
- Adresses postales (`3 rue de la Paix, 75002 Paris`)

Appliqué **avant** toute écriture audit_log, shadow_out, alerte Telegram.

## Tests

```bash
pytest tests/ -v
```

76 tests couvrent :
- Validation schema classifier + anti-injection (16 tests)
- Routing labels + anti-faux-positifs (14 tests)
- Templates drafts + footer AI Act (12 tests)
- Safety net (retry + breaker + mask) (12 tests)
- Shadow mode JSONL + merge (22 tests)

Offline, zero clé API requise.

## Architecture

```
theris-email-curator-public/
├── SKILL.md                    # Anthropic Claude Skills metadata
├── README.md
├── LICENSE                     # MIT
├── CHANGELOG.md
├── prompts/
│   ├── classifier.md
│   ├── draft_generator.md
│   ├── digest_builder.md
│   └── ai_disclosure_footer.md
├── tools/
│   ├── classify_email.py       # Validation JSON + anti-injection
│   ├── apply_labels.py         # Routeur Gmail labels
│   ├── generate_draft.py       # Templates + LLM + footer AI Act
│   └── build_digest.py         # Digest Markdown Telegram
├── lib/
│   ├── safety.py               # retry + breaker + mask_pii + audit
│   ├── shadow_out.py           # JSONL shadow mode
│   ├── neo_labels.py           # Catalogue labels
│   └── senders.yaml.example    # Template fournisseurs critiques
├── scripts/
│   └── rotate_shadow_out.sh    # Purge journalière > 30j
└── tests/                      # 76 tests pytest offline
    ├── conftest.py
    ├── test_classifier.py
    ├── test_label_router.py
    ├── test_draft_generator.py
    ├── test_circuit_breaker.py
    ├── test_shadow_out.py
    └── fixtures/
        └── golden_emails.jsonl # 31 emails anonymisés
```

## Contribuer

PRs bienvenus. Règles :
- Tests verts obligatoires
- PII redaction systématique dans logs / alerts
- Anglais ou français dans le code, français dans les templates FR

## License

MIT © 2026 THERIS / Mathieu Desobry — voir [LICENSE](LICENSE).

## Crédits

- Inspiré des patterns de l'écosystème [Anthropic Claude Skills](https://github.com/anthropics/skills)
- Contributeur open source : Mathieu Desobry ([@LaTige34](https://github.com/LaTige34))
- Support Nous Research écosystème (shout-out aux builders qui libèrent leurs
  outils, ici on rend la pareille).
