#!/bin/bash
export PATH="/usr/local/opt/libpq/bin:$PATH"

BACKUP_DIR=~/Projects/control-plane-3/backups
FILENAME="mtcp_backup_$(date +%Y%m%d_%H%M%S).sql"

DATABASE_URL=$(grep DATABASE_URL ~/Projects/control-plane-3/.env | cut -d= -f2-)

echo "Starting backup..."
pg_dump "$DATABASE_URL" -f "$BACKUP_DIR/$FILENAME"

if [ $? -eq 0 ]; then
  echo "✓ Backup saved: $FILENAME"
  ls -t "$BACKUP_DIR"/*.sql | tail -n +11 | xargs rm -f 2>/dev/null
  echo "✓ Old backups cleaned"
else
  echo "✗ Backup failed"
  exit 1
fi
