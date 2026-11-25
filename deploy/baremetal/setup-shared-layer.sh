#!/usr/bin/env bash
# Create the shared read database on the server's own MariaDB, its three accounts, its tables, grants and views (once; safe to repeat).
# This is what `deploy/scripts/shared.sh prepare` does with Docker, done with the NXERP virtualenv instead.
#
#   deploy/baremetal/setup-shared-layer.sh <file holding the MariaDB root password>
#
# Needs /etc/nxerp-shared/shared.env (from deploy/baremetal/shared.env.example, filled). The root password is read from the file you name,
# is put in this script's environment only for the account step, and is never printed. Run as the `deploy` user.
set -euo pipefail

root_file="${1:?usage: $0 <file holding the MariaDB root password>}"
env_file=/etc/nxerp-shared/shared.env
bench=/srv/apps/nxerp/frappe-bench
[ -r "$root_file" ] || { echo "cannot read $root_file" >&2; exit 1; }
[ -r "$env_file" ] || { echo "missing $env_file: copy deploy/baremetal/shared.env.example and fill it in" >&2; exit 1; }
if grep -Eq '^[^#]*=CHANGE_ME' "$env_file"; then echo "$env_file still contains CHANGE_ME" >&2; exit 1; fi

set -a
# shellcheck disable=SC1090
. "$env_file"
set +a
export PYTHONDONTWRITEBYTECODE=1
py="$bench/env/bin/python"
cd "$bench"

echo "1/4 create the database and the accounts (uses the root password once)"
SHARED_DB_ROOT_PASSWORD="$(tr -d '\r\n' <"$root_file")" "$py" -m nxerp.shared_service create-accounts
echo "2/4 apply the migrations"
SHARED_MIGRATE_USER=shared_migrate "$py" -m nxerp.shared_service migrate
echo "3/4 grants from the data contracts"
SHARED_MIGRATE_USER=shared_migrate "$py" -m nxerp.shared_service grants sync
echo "4/4 views"
SHARED_MIGRATE_USER=shared_migrate "$py" -m nxerp.shared_service views
echo
echo "Done. Next: write /etc/nxerp-shared/sources.json (deploy/baremetal/sources.example.json), then install and start the three units (deploy/baremetal/README.md, step 5)."
