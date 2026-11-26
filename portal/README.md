# Research portal — the evidence room

Static site rendering the research program's evidence: every document in
`docs/research/` plus the append-only search ledger, voids included.

- Build: `python3 portal/build.py` → `portal/dist/`
- Data: reads `backend/data/ledger_snapshot.json` (committed, refreshed by
  every sweep) or falls back to the local `research.db` ledger table.
- Privacy contract: nothing from `data.db`, no positions, no keys. The
  portal fails closed if evidence is missing rather than fabricating rows.
- Void rows: measurements invalidated by a documented engine defect render
  as `VOID*` — published, never deleted (incident doctrine).

Deploys to Vercel on every push to main.
