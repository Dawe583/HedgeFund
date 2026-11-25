# Deployment and Remote Access — Design Addendum

Status: accepted as direction, unbuilt. Companion to `hedge-fund-os.md`;
where they disagree, measured reality wins and both files get updated.
Date: 2026-11-25. Audience: the owner-developer.

`hedge-fund-os.md` §4 fixes the process topology — `web` + `engine` +
research CLI, one machine, one SQLite WAL file — but does not say which
machine, how the owner reaches it away from home, or what happens when
it dies. This addendum decides that as **M6 — private online**: the fund
runs 24/7 on hardware in the owner's home, reachable from anywhere,
without a trading control ever exposed publicly. Nothing here optimizes
for a second user; all of it would be wrong for ten.

---

## 1. Facts on the ground, measured 2026-11-25

**The ScalpFX Pi precedent.** ScalpFX's paper desk ran 24/7 on the
owner's Raspberry Pi 4 for months: worker + FastAPI + static dashboard
against one SQLite WAL file, systemd-supervised (`Restart=always`),
deployed by `scripts/deploy-pi.sh` (push → ssh → pull → restart → health
check). The ops report (`ScalpFX/docs/TEAM/ops.md`, 2026-09-09) recorded
the failure modes that matter here:

- **The Pi died on 2026-09-30: SD-card corruption** — a risk the report
  itself had flagged three weeks earlier. Paper state is cheap; the same
  failure against `backend/data.db` (the owner's real wealth records) is
  a different order of loss.
- Host reachability was fragile: LAN IP hardcoded in the deploy script,
  tailnet path intermittently dead, hotspot fallback — three paths, none
  authoritative. Deploys embedded an expiring `gh auth token` in the
  Pi's git remote and rewrote it every time.
- Log-only monitoring means nobody reads WARNs at 3 AM. Accepted: in-app
  alerts are the designed surface; push alerting stays out of scope.

**Wheel availability, verified on PyPI 2026-11-25:** nautilus_trader
`1.231.0` publishes `cp312`–`cp314` wheels for `manylinux_2_35_aarch64` —
the kernel installs on a Pi 4 from the pin, no source build. Hard
requirement: a **64-bit OS** with **glibc ≥ 2.35** (Raspberry Pi OS
bookworm / Ubuntu 22.04+). A 32-bit install cannot run the kernel at
all — verifying the Pi's OS is M6's first task.

**Already in-tree:** `backend/app/database.py` implements a correct
SQLite online-backup copy (`_sqlite_copy` — the backup API in one step,
read-only source, bounded lock waits) for pre-migration copies; §7
reuses exactly this mechanism. And the web app has **no authentication
at all** today: the trading router is read-only by design, but the
wealth routers write freely — fine on localhost, not fine the moment a
port listens on a network interface.

---

## 2. Deployment target — the Pi, with eyes open

**Decision: the Raspberry Pi 4 is the primary host for `web` + `engine`.
The owner's Mac is the development machine, the verification gate, and
the documented degradation host.**

**A. The Pi 4 (chosen).** It exists, it is paid for, it ran this exact
workload shape for months, and the kernel installs on it from wheels
(§1). Power draw is single-digit watts; the 10 s tick is a rounding
error on its CPU, and the validation gate runs in minutes on daily/4h
bars by the main document's measurement. Cost: the SD-card failure mode
that already killed it once (§8), ARM occasionalism, slow research.

**B. A cheap VPS (rejected).** €5/month buys the owner's real financial
records on someone else's disk, a public IP to firewall forever, and a
bill for a problem the Pi already solves. Its one genuine advantage —
datacenter uptime — is irrelevant while every position is paper. Revisit
only if the M5 audit concludes live trading is viable.

**C. The owner's Mac (rejected as primary, kept as degradation).** A
laptop sleeps, travels, updates, gets closed — a 24/7 engine cannot live
on hardware whose availability is a lifestyle function. But it is the
correct degradation host: the restore drill (§7) targets it first when
the Pi dies, and the engine can run there within an hour while
replacement hardware ships.

**Research placement** (the main document already says research is not
a daemon): the weekly auto-retrain — numpy logistic regression on a few
thousand rows, seconds of CPU — runs in the engine process on the Pi as
today. Validation gates and heavy backtests are invoked *on the Pi over
SSH* so verdict rows land in the one database by construction; running
them on the Mac against a copy would fork provenance, which the data
model exists to prevent. A gate taking 8 minutes on the Pi instead of
2 on the Mac is the correct price. Exception: ingestion backfills may
run anywhere against `backend/data/research.db` — replaceable market
data, not records.

**Reversibility:** high. One repo, one venv, one database file; moving
the host is rsync plus the restore drill.

---

## 3. Remote access — Tailscale, and nothing public

**Decision: primary remote access is Tailscale. No port is ever
forwarded on the router; no tunnel exposes any port to the public
internet. SSH remains as the maintenance path and break-glass fallback.**

The rule that drives this: **no trading control endpoint ever sits on
the public internet without authentication — and the simplest
authentication is the one that does not exist, because there is nothing
public to authenticate against.** A private mesh network is exactly
that: the network itself is the boundary, enrollment is the credential,
and the application stays as simple as on localhost.

**A. Tailscale (chosen).** Already in the owner's life — ScalpFX's
revive script dialed a tailnet IP. It is WireGuard with the boring parts
automated: key distribution, NAT traversal, MagicDNS, a phone app. The
owner checks the dashboard from a phone on cellular with zero extra
infrastructure; tailnet ACLs can restrict which devices reach the web
port — a second, network-level fence costing no application code. Cost:
dependence on Tailscale's coordination servers — control plane only,
traffic is direct WireGuard where possible; if the company vanishes,
LAN and SSH are unaffected and the tailnet degrades, not the fund. One
requirement, learned from ScalpFX's dead-tailnet episode: **key expiry
must be disabled for the Pi node**, and the Pi's tailnet *name* — not a
hardcoded IP — goes in every script.

**B. Cloudflare Tunnel (rejected).** Its purpose is exposing services to
the public internet — precisely what the rule refuses. Access adds real
authentication, but then the fund's control plane depends on a third
party's edge, policy engine and continued free tier, solving a problem
the mesh solves by not existing publicly.

**C. Raw WireGuard (rejected).** Tailscale *is* WireGuard; doing it by
hand means manual key exchange, no NAT traversal without a public
endpoint, phone configs that rot. More moving parts, less capability —
the opposite of boring.

**D. SSH port-forward only (kept as fallback, rejected as primary).**
`ssh -L 8000:localhost:8000 pi` authenticates with keys that already
exist — the correct emergency path, a terrible daily-driver dashboard
experience, especially from a phone.

**Reversibility:** total. Removing Tailscale is `tailscale down`; the
LAN never changes. Only the §4 middleware knows any of this exists.

---

## 4. Access control — the network is the authentication

**Decision, as policy now and implementation in M6: writes are LAN-only;
the tailnet is read-only, with exactly one exception — tripping the
kill-switch. Real HTTP authentication is an M5-audit item, not
retrofitted ad hoc.**

The app has no auth because localhost was the boundary. Once the service
binds to interfaces, policy classifies the client by the network it
arrived on — which, because of §3, is itself a statement about identity:

| client arrives via | GET/HEAD | writes | kill-switch trip |
|---|---|---|---|
| localhost / LAN (RFC1918) | yes | yes | yes |
| tailnet (100.64.0.0/10) | yes | **no — 403** | **yes** |
| anything else | no | no | no |

Three load-bearing properties:

1. **The exception fails safe.** Tripping the kill-switch can only
   *stop* trading. What the tailnet must never reach is everything
   moving state the other way: kill-switch *reset*, lifecycle approval
   cards, mandate writes, all wealth-ledger writes — LAN-only until real
   authentication exists.
2. **Enforcement is one boring middleware** — client IP against three
   CIDR ranges, a method check, 403 otherwise; ~thirty lines, no
   sessions, cookies or cryptography, unit-tested. Honest about what it
   is: network-policy enforcement, not authentication.
3. **It does not pretend to be enough for live money.** The M5 audit
   includes an access-control review before any live capability exists;
   the boring floor there is one long bearer token in the env file,
   checked in constant time, passkeys the comfortable ceiling. The
   invariant the audit inherits is decided now: *authentication is added
   before live control leaves the LAN, never after.*

Why not LAN-only, no tailnet? Because the vision is a fund the owner can
*see* from anywhere — a dashboard he cannot open on a train fails the
point of M6 — and the read-only tailnet carries little risk: the worst
case is disclosure to whoever compromises the tailnet, mitigated by
ACLs. Writes are the attack surface that matters; they stay home.

**Reversibility:** additive middleware; tightening is a policy-table
line plus tests, loosening a deliberate act — correctly.

---

## 5. Process supervision — systemd, copied from what already ran

Two services, two timers. Skeletons for M6 installation at
`deploy/systemd/`, modeled on ScalpFX's units with the fat trimmed:

```ini
# hedgefund-web.service — FastAPI/uvicorn, serves the built frontend.
# Stateless: free to restart; a restart is invisible to the engine.
[Unit]
Description=HedgeFund web (uvicorn, Aurelio+trading API)
After=network-online.target
Wants=network-online.target

[Service]
User=dawe
WorkingDirectory=/home/dawe/HedgeFund/backend
EnvironmentFile=/home/dawe/HedgeFund/backend/.env
ExecStart=/home/dawe/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```ini
# hedgefund-engine.service — the paper engine. Restart=always: the
# engine must outlive crashes, deploys, reboots; restart-safety mid-tick
# is M3 acceptance, not hope. The flock guard makes a duplicate start
# exit, so an aggressive restart policy can do no harm.
[Unit]
Description=HedgeFund trading engine (paper, 24/7)
After=network-online.target
Wants=network-online.target

[Service]
User=dawe
WorkingDirectory=/home/dawe/HedgeFund/backend
EnvironmentFile=/home/dawe/HedgeFund/backend/.env
ExecStart=/home/dawe/.local/bin/uv run python -m trading.paper
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Design notes, each inherited from a ScalpFX scar:

- **No watchdog timer.** ScalpFX ran a per-minute watchdog restarting
  stopped services — a second restarter fighting the first. systemd's
  `Restart=always` *is* the watchdog; what it actually covered (a
  service in `failed` state past restart limits) is covered by
  `StartLimitBurst` tuning plus the ops check noticing. One restarter.
- **The ops-check timer is installed in M6** — not "deferred to a
  maintenance window" again, which is how ScalpFX's never got installed.
  `hedgefund-ops-check.service` (Type=oneshot) + `.timer`
  (`OnBootSec=10min`, `OnUnitActiveSec=1h`, `Persistent=true`):
  read-only, log-only, the discipline of ScalpFX's `ops_audit.sh` —
  service states, `/api/health`, DB freshness, disk, temperature. It
  never restarts anything.
- **Health is freshness, not process existence.** Web is healthy when
  `/api/health` answers; the engine — no HTTP, by design — is healthy
  when heartbeat/equity rows are fresh for its tick cadence. The
  dashboard already renders engine-offline as a first-class state.
- **Log rotation is journald, capped.** stdout goes to the journal; the
  Pi gets `SystemMaxUse=100M` in `/etc/systemd/journald.conf` —
  persistent but bounded, and the first SD-write-reduction measure (§8).
- **Node is not a service.** The frontend is a static build served by
  uvicorn (the Aurelio model — one port, no CORS). ScalpFX's Next.js
  server unit has no successor.

---

## 6. Secrets — one env file, boring permissions

**Decision: secrets stay in `backend/.env` on the Pi, `chmod 600`, owned
by the service user, loaded through systemd `EnvironmentFile=`.**

The inventory today is one OpenRouter key (two if the trading agents get
their own). A secrets manager, vault, sops or age-in-git scheme each
cost more operational surface than the secret is worth — and each
eventually writes plaintext into exactly such a file anyway. Rules that
carry over unchanged:

- `.env` is gitignored, never committed; `.env.example` documents keys,
  never values.
- The file is not in database backups — it is backed up by being
  recorded in the owner's password manager, and recovery is trivial
  regardless: the key regenerates at openrouter.ai in a minute. It is a
  low-value secret (free-tier quota, no billing), treated exactly as
  seriously as it is.
- When live venue keys ever enter the picture (post-M5-audit only), this
  section is wrong by design and rewritten inside the audit: venue keys
  are a different order of secret, and plaintext env is not their floor.
  Deciding that now is speculation; noting the boundary is not.

---

## 7. Backup and restore — the copy mechanism already exists

**Decision: the SQLite online-backup API — the `_sqlite_copy` mechanism
production-proven by pre-migration copies — runs on a systemd timer
every 15 minutes into a rotated local directory, and copies sync off-Pi
to the owner's Mac whenever it is reachable. Litestream and plain `cp`
are both rejected, for opposite reasons.**

- **Plain `cp` of a live WAL database can copy a torn state** — it takes
  no lock and would copy a crashed file without its journal. Never.
- **Litestream is the correct tool for a system whose writes are
  precious per-second.** Ours are not: engine writes are reproducible
  paper bookkeeping; wealth writes are rare, human-paced entries the
  owner remembers making. Fifteen minutes of worst-case loss does not
  buy back a second always-on replication daemon, its config,
  destination and failure modes. The day live money is involved,
  Litestream is the first upgrade evaluated — recorded, not built.
- **The backup API is already in the tree, tested, correct**: one read
  transaction, always a state some commit left. M6 work is a thin CLI
  wrapper plus `hedgefund-backup.timer` — the entire mechanism.
  Rotation: hourly-for-a-day, daily-for-a-month, pruned; pre-migration
  copies stay exempt per the never-delete rule in `database.py`.
- **Off-Pi sync is the part that actually matters**, because the failure
  mode is the card dying and taking local copies with it. The Pi pushes
  with rsync to the Mac when it answers SSH. Imperfect — the Mac sleeps
  too — but the requirement is *recent*, not *continuous*: even a
  day-old wealth database loses almost nothing that was not
  human-entered and remembered.

**The restore drill** is a section, not a sentence, because ScalpFX's
report recommended documenting it and nobody did. Target: **running
engine + dashboard within one hour on fresh hardware, executed once in
M6.**

1. Flash 64-bit Raspberry Pi OS bookworm — or use the Mac, the
   degradation host (same steps, launchd instead of systemd).
2. Install uv, Node 22, tailscale; `tailscale up`; disable key expiry.
3. `git clone` the repo; `uv sync`.
4. Restore `data.db` from the newest off-Pi copy. Alembic brings an
   older backup forward on first start; the pre-migration copy
   discipline protects that step as always.
5. Write `.env` from the password manager.
6. Install and enable the units; verify `/api/health`, engine heartbeat
   rows advancing, dashboard reachable over LAN and tailnet.
7. Engine state resumes from the database — positions are a cache of
   fills, peak equity and kill-switch state are rows. M3's
   restart-safety acceptance is what makes this drill short.

---

## 8. Risks — the ones that already happened once

**SD-card corruption (happened 2026-09-30; the reason this file
exists).** The highest-value hardware fix is cheap and boring: **boot
the Pi from a USB SSD instead of the SD card.** Pi 4 boots USB natively;
a small SSD costs less than an hour of the owner's time and removes the
failure class rather than mitigating it — SD cards die of write
amplification at this scale, SSDs mostly don't. If deferred:
high-endurance card, capped journald (§5), `noatime`, swap off or zram —
measures, not a fix. Either way §7 is the real insurance; hardware only
sets how often it pays out.

**Single point of failure, accepted consciously.** One Pi, one database,
one home — correct for actual stakes: every position is paper, total
loss means rebuilding replaceable paper state and restoring wealth
records from backup. Redundancy, replication, failover are networking
problems purchased with a single user's money. **This acceptance expires
at the M5 audit** — the day live money is designed in, host failure
analysis is part of the audit, because then an offline server is not a
missed paper tick.

**Engine positions while the server is offline.** Power or network
drops; the engine holds open paper positions it cannot manage; stops
blow through unmanaged; the market writes the state in its absence. In
paper this is a data-quality event, not a loss event — recorded (the
equity curve shows the gap) and covered by the divergence budgets that
treat paper as evidence, not proof. Audit note: a live venue's
server-side stops change this calculus — one more line for the M5
capital/venue chapter.

**Reachability drift.** ScalpFX's real failure: three network paths
(LAN, tailnet, hotspot), none authoritative, a hardcoded LAN IP in the
deploy script. M6 rules: the tailnet *name* is the canonical address
everywhere — scripts, docs, bookmarks; LAN IPs are conveniences, never
written down; if the tailnet is down, SSH by LAN IP is the documented
break-glass. One path primary, one fallback, zero ambiguity.

**Deploy-time corruption.** A bad deploy can wedge the web process; it
must never wedge the engine. The topology enforces the structural half
(separate processes, database as interface); §9 adds the behavioral
half — nothing deploys that failed workstation verification. The engine
restarts last, and even the worst deploy is a rollback away.

---

## 9. Deploy pipeline — verification local, deploy is sync + restart

**Decision: one script, `scripts/deploy-pi.sh`, evolved from ScalpFX's.
GitHub is the canonical remote and backup — but the deploy path is
git-over-SSH to a bare repository on the Pi with a post-receive hook,
removing GitHub and its expiring tokens from the critical path. Tests
run on the workstation before anything moves; the Pi never runs the
suite and never rebuilds what the workstation already built.**

Flow, in order:

1. **Verify on the workstation, or nothing happens.** The script runs
   `cd backend && uv run pytest`, `cd frontend && npm test`,
   `cd frontend && npm run build`; any failure stops the deploy before
   the first byte moves. The owner's standing constraint — no CI
   service, verification local — applied as a gate. It is also simply
   correct: a Pi is a terrible place to discover a type error.
2. **Push twice.** `git push origin main` (canonical record, backup),
   then `git push pi main` where `pi` is a bare repository at
   `pi:HedgeFund-deploy.git`. Git-over-SSH authenticates with the
   owner's existing keys — the `gh auth token` rewrite hack dies here,
   unmourned. Deploys work with GitHub down, anywhere SSH reaches the
   Pi.
3. **The post-receive hook does the Pi-side work:** checkout the pushed
   ref into `~/HedgeFund` (`git --work-tree … checkout -f main` —
   tracked files come from the remote; local edits are never
   authoritative) and `uv sync` the backend. It restarts nothing and
   builds no frontend.
4. **The frontend artifact travels; it is not rebuilt.** Step 1 already
   built the verified `frontend/dist` on the workstation, so the script
   rsyncs it to the Pi. Rebuilding on the Pi (ScalpFX's pattern, forced
   by Next.js) costs minutes of Pi CPU for a worse property: the Pi
   build is not the build that was verified. `dist/` stays gitignored;
   the pipeline is its transport.
5. **Restart in the safe order, then verify.** Web first (stateless),
   engine second (restart-safe per M3 acceptance); the script polls
   `/api/health` and confirms the engine heartbeat resumes — ScalpFX's
   closing verification, kept. A failed check prints the rollback
   command; rollback is a force-push of the previous ref, not a
   procedure.

Deliberately absent: containers (a second kernel of things to debug),
blue/green or canary machinery (one user; the verification gate *is* the
canary), deploys triggered by a push hook upstream — deploys are acts of
the owner, never side effects.

---

## 10. M6 — private online (milestone addendum)

Inserted after M4, overlapping M5 — depends on **M3** (an engine running
24/7 exists to be hosted) and **M4** (a dashboard worth reaching
remotely exists), independent of M5's mandate machinery. Effort 3-5
days, most of it the drill and the pipeline, not invention — nearly
every mechanism has a running precedent in ScalpFX or in-tree.

**Scope:**

- Pi re-provisioned per §7 steps 1-2 (64-bit bookworm verified first —
  §1's hard requirement; USB SSD boot per §8 unless consciously
  deferred).
- systemd units, ops-check and backup timers installed and enabled (§5,
  §7); journald capped; key expiry disabled on the tailnet node.
- The network-policy middleware of §4 implemented and tested, plus
  tailnet ACLs limiting which devices reach the web port.
- `scripts/deploy-pi.sh` per §9: verification gate, dual push, hook,
  dist rsync, ordered restart, health verification.
- Backup timer live; off-Pi sync landing; **the §7 restore drill
  executed end-to-end once** onto the Mac as degradation host, timed.
- ScalpFX's Pi deployment formally retired by this point (per M0's
  decision record): one Pi runs one fund, not two lineages.

**Acceptance:**

- The owner opens the dashboard on a phone over cellular — read-only —
  and on the LAN laptop — full writes; both verified by attempting the
  operations, not by reading the middleware. The kill-switch trips from
  the tailnet; its reset does not (403).
- `scripts/deploy-pi.sh` takes a committed change from push to live
  services in one command; refuses a red tree (demonstrated once with a
  deliberately broken test); a failed health check prints the rollback.
- The Pi is hard-rebooted once: both services return without human
  intervention, engine state consistent (heartbeat, positions cache,
  peak equity).
- The restore drill's measured time is recorded in the successor status
  note; target under one hour.
- A backup younger than 15 minutes exists on the Pi and an off-Pi copy
  younger than a day exists, demonstrated.

**Out of scope, explicitly:** multi-user anything; public exposure of
any endpoint; mobile apps (the dashboard is responsive or it is not);
live trading controls of any kind; real HTTP authentication beyond the
network policy (the M5 audit's obligation, §4); push alerting beyond the
in-app alerts rail; Litestream or continuous replication (§7 records
when it becomes the right answer).

---

## 11. Decision registry additions

Numbering continues the main document's registry.

| # | Decision | Chosen | Alternative | Why | Reversibility |
|---|---|---|---|---|---|
| D16 | Deployment host | owner's Pi 4 (64-bit bookworm+, USB SSD boot) | VPS; the Mac | owned, proven shape, aarch64 wheels verified; a laptop can't be 24/7; a VPS sells the owner's records for uptime paper doesn't need | high: repo+venv+one file, host-agnostic |
| D17 | Remote access | Tailscale mesh, nothing public, SSH fallback | Cloudflare Tunnel; raw WireGuard; SSH-only | the simplest auth is the one that doesn't exist publicly; ACLs are a free second fence | total: `tailscale down` |
| D18 | Access policy | tailnet read-only + kill-trip exception; writes LAN-only; real auth deferred to M5 audit | full auth now; LAN-only always | vision requires remote visibility; writes are the real attack surface; the exception fails safe; inventing auth before the audit is speculation | cheap to tighten, correctly expensive to loosen |
| D19 | Backup | SQLite online-backup API on a 15-min timer (reusing `_sqlite_copy`), rotated, rsynced off-Pi | Litestream; plain cp | correct mechanism in-tree and production-proven; write cadence doesn't buy back a replication daemon; cp of a live WAL is a torn copy | high: swap the timer for Litestream when writes are precious per-second |
| D20 | Deploy path | local verification gate → push origin + bare repo on Pi → post-receive hook; frontend artifact rsynced, not rebuilt | ssh+pull via GitHub with embedded token; CI service | owner's constraint applied as a gate; tokens leave the critical path; the Pi runs the artifact that was verified | high: the script is the mechanism |
| D21 | Supervision | systemd units, no watchdog, ops-check timer installed in M6 | watchdog timer; containers | one restarter, not two; ScalpFX's watchdog duplicated systemd; the ops-check lesson is *install it this time* | high |
| D22 | Restore posture | documented drill, degradation to the Mac, executed and timed once in M6 | redundancy/failover; hope | single point of failure accepted at paper stakes — acceptance expires at the M5 audit, in writing | n/a — a practice, not a component |

---

*This document is a design, not a status. The drill, the pipeline and
the middleware are the status. Where they disagree with this file, this
file loses and gets updated — same rule as the parent document.*
