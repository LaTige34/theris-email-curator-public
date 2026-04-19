# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] — 2026-04-19

### Fixed

- Anonymization: removed 9 critical/high leaks identified by external audit
  (renamed `lib/neo_labels.py` → `lib/labels.py`, purged internal codenames,
  neutralized LICENSE / README / SKILL.md author metadata, generalized
  regex patterns, replaced fixture strings with neutral placeholders).

## [0.1.0] — 2026-04-19

### Added

- Initial public release (MIT license) — code stripped down and anonymized
  from an internal `email-curator` skill.
- `SKILL.md` in Anthropic Claude Skills format (YAML frontmatter).
- Classifier email LLM (prompt FR verrouillé + schema JSON strict +
  anti-injection + fallback safe).
- Routeur Gmail labels (priorité : URGENT / DRAFT-REQUIRED / SPAM +
  thème : WORK_MAIN / WORK_OPS / HR / PERSONAL) avec anti-FP SPAM et
  anti-FP thèmes métier.
- Générateur drafts (7 templates FR pro + footer AI Act art. 50 obligatoire
  + fallback safe si LLM down).
- Digest Telegram Markdown (emojis contextuels, deep-links Gmail,
  placeholder PII, troncature 4000 chars).
- `lib/safety.py` : retry exponentiel + circuit breaker 3-states + AlertPump
  avec dédup + `audit_log()` signé SHA-256 + décorateur `with_safety_net`.
- `lib/shadow_out.py` : appender JSONL pour shadow mode (comparaison
  pipelines) avec merge "last-wins-non-empty" par `thread_id`.
- Script `scripts/rotate_shadow_out.sh` — purge journalière shadow_out/ > 30j.
- 75 tests pytest offline (zero I/O réseau, zero clé API) :
  - 16 tests classifier (validation + injection + fallbacks)
  - 13 tests label router (routing + anti-FP)
  - 12 tests draft generator (templates + AI Act footer)
  - 12 tests safety (retry + breaker + mask_pii + wrapper)
  - 22 tests shadow_out (append + merge + phi_detected OR logique)
- GitHub Actions CI (pytest + ruff lint).
- Fixtures : 31 emails anonymisés pour tests régression.

### Security

- `mask_pii()` couvre : email, téléphone FR (+33 / 06…), NIR 13/15 chiffres,
  adresses postales.
- Redaction appliquée AVANT toute écriture audit / alert / shadow_out.
- Placeholder PII automatique dans digest Telegram si `phi_detected=true`.

### Compliance

- AI Act art. 50 (Règlement UE 2024/1689, applicable 2 août 2026) — footer
  transparence IA inséré automatiquement dans tout draft généré par LLM.
- Variante Mistral Small (hébergement France) pour cas PII / souveraineté.
