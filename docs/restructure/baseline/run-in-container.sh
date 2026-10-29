#!/usr/bin/env bash
# Baseline runner (inside the bench container). Each step logs to its own file and records rc and seconds.
L=/home/frappe/baseline-logs; rm -rf $L; mkdir -p $L
cd /home/frappe/frappe-bench
step() { local name=$1; shift; echo "### $name :: $*" >> $L/summary.txt; local s=$(date +%s); bash -lc "$*" > $L/$name.log 2>&1; local rc=$?; echo "### $name rc=$rc secs=$(( $(date +%s)-s ))" >> $L/summary.txt; }
echo "apps: helpdesk=$(git -C apps/helpdesk rev-parse --short=10 HEAD) nxerp=$(git -C /workspace rev-parse --short=10 HEAD) frappe=$(git -C apps/frappe rev-parse --short=10 HEAD) erpnext=$(git -C apps/erpnext rev-parse --short=10 HEAD)" >> $L/summary.txt
step theme_check   "cd apps/helpdesk/desk && NXERP_PUBLIC=/workspace/nxerp/public/css yarn theme:check"
step theme_audit   "cd apps/helpdesk/desk && yarn theme:audit"
step frontend_build "cd /home/frappe/frappe-bench && bench build --app helpdesk"
step tests_nxerp    "cd /home/frappe/frappe-bench && bench --site nxerp.localhost run-tests --app nxerp"
step tests_helpdesk "cd /home/frappe/frappe-bench && bench --site nxerp.localhost run-tests --app helpdesk"
echo "ALL DONE" >> $L/summary.txt
