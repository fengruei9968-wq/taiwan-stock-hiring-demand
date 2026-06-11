#!/bin/bash
# =============================================================================
# Copy-only backup for hiring demand daily artifacts.
# - Runs monthly via launchd.
# - Copies artifacts older than HIRING_ARTIFACT_BACKUP_RETENTION_DAYS.
# - Never deletes or moves source files.
# =============================================================================

set -euo pipefail

HIRING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${HIRING_PROJECT_ROOT:-$(cd "$HIRING_DIR/.." && pwd -P)}"
BACKUP_ROOT="${HIRING_ARTIFACT_BACKUP_ROOT:-/Volumes/Extreme SSD/Backup/徵人需求度每日產物Backup}"
RETENTION_DAYS="${HIRING_ARTIFACT_BACKUP_RETENTION_DAYS:-30}"
LOG_FILE="$HIRING_DIR/logs/hiring_daily_artifacts_backup.log"

mkdir -p "$HIRING_DIR/logs"
echo "========================================" >> "$LOG_FILE"
echo "執行時間: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "BACKUP_ROOT=$BACKUP_ROOT" >> "$LOG_FILE"
echo "RETENTION_DAYS=$RETENTION_DAYS" >> "$LOG_FILE"

if [ ! -d "$HIRING_DIR" ]; then
    echo "錯誤: 徵人需求度資料夾不存在：$HIRING_DIR" >> "$LOG_FILE"
    exit 1
fi
if [ ! -d "$BACKUP_ROOT" ]; then
    echo "錯誤: backup root 不存在：$BACKUP_ROOT" >> "$LOG_FILE"
    exit 1
fi
if [ ! -w "$BACKUP_ROOT" ]; then
    echo "錯誤: backup root 不可寫入：$BACKUP_ROOT" >> "$LOG_FILE"
    exit 1
fi

CUTOFF_DATE="$(date -v-"${RETENTION_DAYS}"d '+%Y%m%d')"
RUN_ID="$(date '+%Y%m%d_%H%M%S')"
MONTH_KEY="$(date '+%Y%m')"
RUN_DIR="$BACKUP_ROOT/$MONTH_KEY/backup_run_$RUN_ID"
CANDIDATE_FILE="$RUN_DIR/candidates_before_or_on_${CUTOFF_DATE}.txt"
COPIED_FILE="$RUN_DIR/copied_paths.txt"
MANIFEST="$RUN_DIR/backup_manifest_${RUN_ID}.txt"

mkdir -p "$RUN_DIR"
: > "$CANDIDATE_FILE"
: > "$COPIED_FILE"

cd "$HIRING_DIR"

find data/reports -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' 2>/dev/null |
while IFS= read -r relpath; do
    artifact_date="$(basename "$relpath")"
    [ "$artifact_date" -le "$CUTOFF_DATE" ] && printf '%s\n' "$relpath"
done >> "$CANDIDATE_FILE" || true

find data/stock_monthly_revenue_raw -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' 2>/dev/null |
while IFS= read -r relpath; do
    artifact_date="$(basename "$relpath")"
    [ "$artifact_date" -le "$CUTOFF_DATE" ] && printf '%s\n' "$relpath"
done >> "$CANDIDATE_FILE" || true

find data/runs -maxdepth 1 -mindepth 1 -type d 2>/dev/null |
while IFS= read -r relpath; do
    artifact_name="$(basename "$relpath")"
    artifact_date="$(printf '%s' "$artifact_name" | sed -n 's/^.*\([0-9]\{8\}\).*$/\1/p')"
    [ -n "$artifact_date" ] && [ "$artifact_date" -le "$CUTOFF_DATE" ] && printf '%s\n' "$relpath"
done >> "$CANDIDATE_FILE" || true

find data/revenue_snapshots -maxdepth 1 -type f \( -name 'monthly_revenue_summary_*.csv' -o -name 'monthly_revenue_snapshot_manifest_*.json' \) 2>/dev/null |
while IFS= read -r relpath; do
    artifact_name="$(basename "$relpath")"
    artifact_date="$(printf '%s' "$artifact_name" | sed -n 's/^.*_\([0-9]\{8\}\)\..*$/\1/p')"
    [ -n "$artifact_date" ] && [ "$artifact_date" -le "$CUTOFF_DATE" ] && printf '%s\n' "$relpath"
done >> "$CANDIDATE_FILE" || true

sort -u "$CANDIDATE_FILE" -o "$CANDIDATE_FILE"
CANDIDATE_COUNT="$(wc -l < "$CANDIDATE_FILE" | tr -d ' ')"

if [ "$CANDIDATE_COUNT" -gt 0 ]; then
    while IFS= read -r relpath; do
        [ -z "$relpath" ] && continue
        mkdir -p "$RUN_DIR/$(dirname "$relpath")"
        rsync -a "$relpath" "$RUN_DIR/$(dirname "$relpath")/"
        printf '%s\n' "$relpath" >> "$COPIED_FILE"
    done < "$CANDIDATE_FILE"
fi

COPIED_COUNT="$(wc -l < "$COPIED_FILE" | tr -d ' ')"
{
    echo "backup_type=hiring_daily_artifacts_copy_only"
    echo "generated_at=$(date '+%Y-%m-%d %H:%M:%S')"
    echo "source_root=$HIRING_DIR"
    echo "backup_root=$BACKUP_ROOT"
    echo "run_dir=$RUN_DIR"
    echo "retention_days=$RETENTION_DAYS"
    echo "cutoff_date=$CUTOFF_DATE"
    echo "candidate_count=$CANDIDATE_COUNT"
    echo "copied_count=$COPIED_COUNT"
    echo "delete_source=false"
    echo "move_source=false"
    echo "restore_tracked_files=false"
    echo "stage3_web_touched=false"
} > "$MANIFEST"

echo "candidate_count=$CANDIDATE_COUNT copied_count=$COPIED_COUNT manifest=$MANIFEST" >> "$LOG_FILE"
echo "完成" >> "$LOG_FILE"
printf 'manifest=%s\ncandidate_count=%s\ncopied_count=%s\n' "$MANIFEST" "$CANDIDATE_COUNT" "$COPIED_COUNT"
