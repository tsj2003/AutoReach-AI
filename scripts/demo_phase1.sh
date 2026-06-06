#!/bin/bash
# Smoke test for the Phase 1 engine + CLI.
# Usage: bash scripts/demo_phase1.sh
set -e
DB="sqlite:////tmp/autoreach_demo.db"
PY=.venv/bin/python
rm -f /tmp/autoreach_demo.db

echo "--- init ---"
$PY -m engine --db "$DB" init

echo "--- engagement-create ---"
$PY -m engine --db "$DB" engagement-create \
  --id self \
  --customer "AutoReach (self)" \
  --offer "AI sales infra. 500/qualified meeting." \
  --icp "B2B SaaS founders, US/EU" \
  --target 20 --price 50000 --budget 100000

echo "--- agent-create ---"
$PY -m engine --db "$DB" agent-create \
  --id agent_self --engagement self --runner outbound.v1 \
  --hitl-threshold 2 --send-gap-seconds 0

echo "--- prospect 1 ---"
$PY -m engine --db "$DB" prospect-add --engagement self --email "alice@a.com" --name "Alice" --company "A"
echo "--- prospect 2 ---"
$PY -m engine --db "$DB" prospect-add --engagement self --email "bob@b.com"   --name "Bob"   --company "B"
echo "--- prospect 3 ---"
$PY -m engine --db "$DB" prospect-add --engagement self --email "carol@c.com" --name "Carol" --company "C"

echo "--- prospect count ---"
$PY -c "
from engine import open_storage
store,_,_ = open_storage('$DB')
ps = list(store.list_prospects('self', limit=100))
print('count:', len(ps))
for p in ps: print(' ', p.id, p.email, p.full_name)
"

echo "--- tick ---"
$PY -m engine --db "$DB" tick

echo "--- jobs after tick ---"
$PY -c "
from engine import open_storage
store,events,ledger = open_storage('$DB')
for state in ['pending','awaiting_approval','approved','running','succeeded','failed','dead_lettered','rejected']:
    js = list(store.list_jobs_by_state(state, engagement_id='self', limit=50))
    if js:
        print(f'  state={state}: {len(js)}')
        for j in js: print(f'    {j.id}  err={j.last_error}')
print('  cost spent:', ledger.total_spent_cents('self'))
"

echo "--- approve all awaiting jobs ---"
$PY -c "
from engine import open_storage, EngineRuntime, AdapterRegistry, ConsoleEmailAdapter, OutboundAgentV1
store,events,ledger = open_storage('$DB')
console = ConsoleEmailAdapter()
rt = EngineRuntime(store=store, events=events, ledger=ledger,
                   adapters=AdapterRegistry([console]),
                   agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()})
for j in list(store.list_jobs_by_state('awaiting_approval', engagement_id='self')):
    rt.approve_job(j.id)
    print('approved', j.id)
"

echo "--- drain ---"
$PY -m engine --db "$DB" drain

echo "--- final state ---"
$PY -c "
from engine import open_storage
store,events,ledger = open_storage('$DB')
print('jobs by state:')
for state in ['pending','awaiting_approval','approved','running','succeeded','failed','dead_lettered','rejected']:
    js = list(store.list_jobs_by_state(state, engagement_id='self', limit=50))
    if js: print(f'  {state}: {len(js)}')
print('cost spent:', ledger.total_spent_cents('self'), 'cents (email_send only:', ledger.total_spent_cents('self', category='email_send'), ')')
print('event tail:')
for ev in list(events.list_recent(engagement_id='self', limit=8))[::-1]:
    print(f'  {ev.kind.value}  job={ev.job_id}')
"
