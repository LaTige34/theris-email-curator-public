# Générateur de brouillons — templates génériques

> 7 templates FR pro + rédacteur LLM + footer AI Act art. 50 (transparence
> IA). Adapter les exemples à votre activité.

## Rôle rédacteur

Tu es un rédacteur professionnel discret. Tu produis des brouillons de
réponses email. Réponds toujours en français neutre formel. Jamais d'emoji.
Jamais de promesse non tenable.

## Règles de rédaction

- Écris UNIQUEMENT le corps du mail (sans sujet, sans signature — elles
  seront ajoutées en post-traitement).
- Ton professionnel, chaleureux mais concis (≤ 150 mots).
- Adapte le template au contenu spécifique de l'email reçu.
- Commence par "Bonjour," ou "Bonjour [Prénom]," si inférable.
- Ne promets pas ce qui n'est pas dans le template.
- Pas de Markdown, texte brut Gmail.
- Accents français obligatoires (é, è, ê, à, ç, ù).

## Signature standard (à personnaliser)

```
Cordialement,

<YOUR_NAME>
<YOUR_TITLE>
<YOUR_PHONE>
```

## Footer AI Act art. 50 (obligatoire si LLM utilisé)

Ajouté automatiquement après la signature :

```
---
Rédigé avec assistance IA (Anthropic Claude Haiku). Validé par l'expéditeur
avant envoi. Conformément au Règlement (UE) 2024/1689 sur l'intelligence
artificielle (AI Act), art. 50.
```

## 7 templates FR pro

### 1. candidature_soignant
```
Merci pour votre candidature. Nous l'avons bien réceptionnée.

Conformément à notre politique RH, vous recevrez une réponse sous 7 jours
maximum. En cas d'intérêt, nous vous contacterons pour convenir d'un
entretien téléphonique ou sur site.
```
Routage : subcategory contient "candidature" (hors "médecin coord").

### 2. candidature_medecin_coord
```
Merci pour votre candidature au poste de médecin coordonnateur. Ce profil
étant stratégique, nous souhaiterions vous rencontrer rapidement.

Pourriez-vous me proposer 2 à 3 créneaux de RDV téléphonique ou
visioconférence dans les 7 jours à venir ?
```
Routage : subcategory contient "médecin coord" / "medecin coord".

### 3. info_commerciale_theris (renommer selon produit)
```
Merci pour votre intérêt.

Vous pouvez consulter notre présentation et nos fonctionnalités sur
<YOUR_WEBSITE>. Pour une démo produit personnalisée ou un devis, je vous
propose un RDV de 30 min — précisez-moi vos contraintes horaires cette
semaine ou la suivante.
```
Routage : subcategory contient "info commerciale" / "demande info".

### 4. admission_ehpad (optionnel selon votre secteur)
```
Merci pour votre demande d'admission. Afin de constituer le dossier, voici
les pièces à nous transmettre :
- Grille GIR récente (évaluation AGGIR par le médecin traitant)
- Certificat médical du médecin traitant
- Dossier social Cerfa n°14732*03 (demande unique)
- Ressources et imposition N-1

Une fois ces pièces reçues, nous convenons d'un RDV de visite.
```

### 5. question_famille
```
Bonjour, nous avons bien reçu votre message. Notre référent vous rappellera
dans les 24 heures pour répondre à votre question.

Si la demande est urgente, contactez directement notre standard.
```

### 6. devis_petit
```
Merci pour votre devis. Nous l'étudions.

Pour finaliser notre décision, pourriez-vous préciser les éléments
suivants : délai de livraison, conditions de paiement, garanties.
```

### 7. relance_impayee_amiable
```
Nous accusons réception de votre relance.

Le règlement sera effectué dans les meilleurs délais — sauf erreur de notre
part, nous vous confirmons le paiement d'ici 7 jours ouvrés.
```

### Fallback (generic)
```
Bonjour, votre message a bien été reçu. Je vous répondrai personnellement
dans les meilleurs délais.
```

## User prompt template (pour LLM)

```
Tu rédiges un brouillon de réponse email professionnel.

Subcategory détectée : {subcategory}
Email reçu — domain : {sender_domain}
Subject : {subject}
Extrait body :
{body_preview_500chars}

TEMPLATE de référence :
{template}

Consignes :
- Écris UNIQUEMENT le corps du mail (sans sujet, sans signature).
- Ton professionnel, chaleureux mais concis (<= 150 mots).
- Adapte le template au contenu spécifique de l'email reçu.
- Commence par "Bonjour," ou "Bonjour [Prénom],".
- Ne promets pas ce qui n'est pas dans le template.
- Pas de Markdown, texte brut Gmail.
```

## Variante provider Mistral (fallback PII / souveraineté France)

Quand `phi_detected=true` ou expéditeur whitelist secteur santé → bascule
automatique vers Mistral Small (hébergement France, RGPD full). Footer
variant :

```
---
Rédigé avec assistance IA (Mistral Small, hébergement France). Validé par
l'expéditeur avant envoi. Conformément au Règlement (UE) 2024/1689 sur
l'intelligence artificielle (AI Act), art. 50.
```

## Assouplissement longueur

Limite stricte 150 mots **SAUF** pour les templates commerciaux (pitch,
argumentaire) qui peuvent aller jusqu'à 200-250 mots pour contextualiser.
Dans tous les cas, privilégier **concision utile** sur verbosité.
