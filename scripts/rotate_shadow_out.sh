#!/usr/bin/env bash
# rotate_shadow_out.sh — Purge les fichiers shadow_out/ > 30 jours.
#
# Le skill écrit un JSONL par jour dans `shadow_out/YYYY-MM-DD.jsonl`.
# Ce script purge les fichiers de plus de 30 jours pour limiter l'empreinte
# disque (≈ 2 KB/email × ~50/jour × 30j = ~3 MB, marge large).
#
# Usage :
#   bash scripts/rotate_shadow_out.sh
#
# Cron (journalier, 04h15) :
#   15 4 * * * bash /path/to/email-curator/scripts/rotate_shadow_out.sh
#
# Conformité RGPD :
# - 30 jours = durée minimale shadow mode (14 j cutover + 14 j buffer).
# - Audit log (stderr).

set -euo pipefail

SHADOW_DIR="${EMAIL_CURATOR_SHADOW_OUT:-$(dirname "$0")/../shadow_out}"
RETENTION_DAYS="${EMAIL_CURATOR_SHADOW_RETENTION_DAYS:-30}"

if [ ! -d "$SHADOW_DIR" ]; then
    echo "[rotate_shadow_out] dossier inexistant : $SHADOW_DIR — rien à faire" >&2
    exit 0
fi

# Compte avant purge pour audit
before=$(find "$SHADOW_DIR" -maxdepth 1 -name "*.jsonl" -type f | wc -l)

# Purge fichiers > RETENTION_DAYS
deleted=0
while IFS= read -r -d '' file; do
    rm -f "$file"
    deleted=$((deleted + 1))
    echo "[rotate_shadow_out] purgé : $file" >&2
done < <(find "$SHADOW_DIR" -maxdepth 1 -name "*.jsonl" -type f -mtime +"$RETENTION_DAYS" -print0)

after=$(find "$SHADOW_DIR" -maxdepth 1 -name "*.jsonl" -type f | wc -l)
echo "[rotate_shadow_out] $(date -Iseconds) — avant=$before après=$after purgés=$deleted (rétention=${RETENTION_DAYS}j, dir=$SHADOW_DIR)"
