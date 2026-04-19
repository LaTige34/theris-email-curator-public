# Digest Builder — Telegram Bot digest

> Format Markdown FR premium avec emojis contextuels, deep-links Gmail,
> séparateurs visuels, accents. Personnalisable.

## Règles de composition

- URGENT **JAMAIS** dans le digest (voix/SMS direct en amont).
- SPAM **JAMAIS** dans le digest (déplacé en spam folder Gmail).
- `phi_detected=true` → `subject` et `summary` masqués (`Contenu sensible,
  consulter Gmail`). Seul le domaine + type d'action restent visibles.
  C'est le dernier barrage PII avant Telegram Bot API (infra US).
- Limite 4000 chars (marge sécurité, Telegram limite 4096).
- Accents FR obligatoires.
- Deep-link Gmail si `thread_id` dispo :
  `https://mail.google.com/mail/u/0/#inbox/{thread_id}`.

## Structure type

```
📬 *Digest*
_18 avril 2026 · 14:35_

🟡 3 à traiter · 🟢 2 à lire

━━━━━━━━━━━━━━━━━━━━
🟡 *À TRAITER* (3)

🎯 *Demande pilote produit*
   _info commerciale_ · `prospect.example.com` · [📂](link)
🏥 *Question visite médecin traitant*
   _question famille_ · `gmail.com` · [📂](link)
🏦 *Alerte solde compte pro*
   _alerte banque pro_ · `qonto.com` · [📂](link)

━━━━━━━━━━━━━━━━━━━━
🟢 *À LIRE* (2)

🟦 *Facture hébergement réglée*
   _notification paiement_ · `infra-provider.example.com` · [📂](link)
📡 *Newsletter sectorielle*
   _newsletter_ · `newsletter.example.com` · [📂](link)
```

## Emojis contextuels (matching substring sur subcategory + sender_domain)

### Activité principale (exemples, à adapter)
- `prospect`, `pilote` → 🎯
- `investisseur` → 💼
- `ovh`, `hetzner` → 🟦

### Santé / EHPAD (optionnel)
- `idec`, `medecin`, `résident`, `ars` → 🏥

### RH
- `candidature`, `aide-soignante`, `infirmi`, `urssaf`, `cpam`, `dreets`
  → 👤

### Institutionnel / fiscal
- `legalplace`, `greffe`, `inpi`, `bodacc` → 📜
- `impots`, `dgfip` → 🧾

### Banque
- `qonto`, `stripe`, `crédit agricole`, `bnp` → 🏦

### Énergie / télécom
- `edf`, `engie` → ⚡
- `veolia` → 💧
- `orange`, `free`, `sfr`, `bouygues` → 📡

### Perso
- `ameli`, `mutuelle` → 💊
- `assurance` → 🛡️

### Fallback
- défaut → 📧

## Emojis catégorie (header)

- URGENT → 🔴 (jamais affiché dans digest ; référence seulement)
- ACTION → 🟡
- INFO → 🟢
- SPAM → ⚫ (jamais affiché dans digest)

## Header date

Format FR humain : `18 avril 2026 · 14:35` (mois en toutes lettres).

Mois FR : janvier, février, mars, avril, mai, juin, juillet, août,
septembre, octobre, novembre, décembre.

## Placeholder PII

`Contenu sensible, consulter Gmail` (défini `DIGEST_PHI_PLACEHOLDER`).

## Troncature

Si message > 4000 chars, couper à la dernière ligne propre + note :
`_[…] digest tronqué, consulter Gmail._`.

## Vide

Si aucune entrée ACTION/INFO : `_Aucun email à traiter sur cette période._`.
