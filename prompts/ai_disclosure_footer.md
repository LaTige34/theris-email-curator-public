# AI Act Art. 50 — Footer transparence drafts

> Conformément au Règlement (UE) 2024/1689 sur l'intelligence artificielle
> (AI Act), art. 50 — "Obligations de transparence pour les fournisseurs et
> les déployeurs de certains systèmes d'IA".

## Footer standard (FR, provider Anthropic)

```
---
Rédigé avec assistance IA (Anthropic Claude Haiku). Validé par l'expéditeur
avant envoi. Conformément au Règlement (UE) 2024/1689 sur l'intelligence
artificielle (AI Act), art. 50.
```

## Variante provider Mistral (fallback PII / souveraineté France)

```
---
Rédigé avec assistance IA (Mistral Small, hébergement France). Validé par
l'expéditeur avant envoi. Conformément au Règlement (UE) 2024/1689 sur
l'intelligence artificielle (AI Act), art. 50.
```

## Règles d'insertion

1. Footer **obligatoire** dans TOUT draft généré par IA.
2. Inséré **après** la signature de l'expéditeur.
3. Séparé par `---` sur une ligne seule.
4. Opt-out possible uniquement si draft = template pur sans appel LLM
   (mode fallback). Dans ce cas, footer absent (pas d'IA dans la boucle).
5. Provider mentionné = provider réellement utilisé au runtime (pas
   boilerplate).

## Traçabilité audit

Chaque draft généré est loggé avec :
- `skill_id=email-curator`
- `provider=anthropic|mistral`
- `model=claude-haiku-4-5|mistral-small-latest`
- `footer_inserted=true|false`
- `draft_hash=sha256(body+signature+footer)` (pas le body brut — conformité PII)

Cf. `lib.safety.audit_log()` pour la signature SHA-256 des entrées
(remplacer par Ed25519 en prod via `cryptography`).

## Référence légale

- Règlement (UE) 2024/1689, Journal officiel L 12 juillet 2024
- Art. 50 §1 : systèmes d'IA générant ou manipulant du contenu texte publié
  dans l'intérêt du public doivent divulguer que le contenu a été généré
  ou manipulé artificiellement.
- Art. 50 §4 : applicable aux déployeurs du système d'IA (vous l'êtes dès
  lors que vous utilisez Claude / Mistral pour produire ces drafts).
- Date d'applicabilité art. 50 : 2 août 2026 (obligations transparence).
