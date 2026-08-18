#!/usr/bin/env bash
# Applies every migration in db/migrations/ in numeric order to the target
# database. Wraps each file in its own transaction (via psql -1) so a
# partial failure doesn't leave a half-applied file committed, and stops
# immediately on the first error rather than continuing past a broken
# migration.
set -euo pipefail

DSN="${1:-${DATABASE_DSN:-}}"
if [ -z "$DSN" ]; then
  echo "Usage: migrate.sh <postgres-connection-string>" >&2
  echo "   or: DATABASE_DSN=postgresql://... migrate.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="$SCRIPT_DIR/migrations"

echo "Applying migrations from $MIGRATIONS_DIR to target database..."
for f in $(ls "$MIGRATIONS_DIR"/*.sql | sort -V); do
  echo "  -> $(basename "$f")"
  psql "$DSN" -v ON_ERROR_STOP=1 -1 -q -f "$f"
done
echo "All migrations applied successfully."

# Migration 011 creates the app_runtime role with a hardcoded placeholder
# password ('CHANGE_ME_IN_ENV') — a real deployment that only runs the
# migrations and stops here would leave a database role whose password is
# sitting in plain text in this very repository. Set a real one now if
# provided; refuse to proceed silently with the placeholder otherwise.
# NOTE: Postgres roles are cluster-wide, not per-database — running this
# with APP_RUNTIME_PASSWORD against ANY database in a shared cluster
# changes the password for every database that role can connect to, not
# just the target database. Discovered the hard way while testing this
# script: setting a new password against a throwaway test database broke
# the separately-running dev database's connection until the password was
# reset. Harmless in a real deployment (one Postgres instance per
# environment is the normal shape), but worth knowing if you run this
# against a shared/multi-database cluster.
if [ -n "${APP_RUNTIME_PASSWORD:-}" ]; then
  echo "Setting app_runtime password from APP_RUNTIME_PASSWORD..."
  psql "$DSN" -v ON_ERROR_STOP=1 -q -c "alter role app_runtime password '${APP_RUNTIME_PASSWORD}';"
  echo "app_runtime password updated. Make sure DATABASE_DSN for the app matches this password."
else
  echo ""
  echo "WARNING: APP_RUNTIME_PASSWORD was not set — the app_runtime role still has"
  echo "the placeholder password from migration 011 ('CHANGE_ME_IN_ENV'), which is"
  echo "committed in plain text in this repository. Set APP_RUNTIME_PASSWORD and"
  echo "re-run this script, or run manually:"
  echo "  psql \"\$DSN\" -c \"alter role app_runtime password '<real-password>';\""
  echo "before using this database for anything beyond local testing."
fi
