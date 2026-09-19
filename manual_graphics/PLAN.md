# Manual graphics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution, or superpowers:subagent-driven-development if the user chooses delegation. Steps use checkbox syntax for tracking.

**Goal:** Generate original PNG graphics through an authorized Telegram conversation, with a four-hour receiver relay and no disruption of live kit controls.

**Architecture:** One Telegram receiver owns the update offset and forwards kit callbacks through separate Gist files. A pure conversation state machine queues renderer requests. A render worker reuses existing assets and renderers; a shared Canva broker owns token refresh. A dedicated Actions workflow runs the service, while a separate recovery workflow checks for a missing successor.

**Tech Stack:** Existing Python 3.14, requests, Pillow, PyMuPDF, Playwright, unittest, Telegram Bot API, GitHub Actions and Gist API. No additional hosted service.

**Spec:** [DESIGN.md](DESIGN.md). User approved proceeding after the impact review of main 16be63c.

## Global Constraints

- All new Python, tests, and documentation live in `manual_graphics/`; new YAML files live in `.github/workflows/`.
- Listening budget: 14,400 seconds. Session inactivity: 1,800 seconds.
- Original PNG via sendDocument to TELEGRAM_TO_BOT only. No public-channel sends, message replacement, or social publishing.
- Only the authorized user in the configured private chat can operate the wizard.
- Reuse current renderers; preserve current logo alignment and every approved visual decision.
- A fresh Canva page-one PDF for every manual phase that needs it; no stale PDF fallback.
- Exactly one Telegram poller per token and one Canva refresh owner.
- Preserve incomplete requests between runs. Do not blindly retry an uncertain document delivery.
- Purge only completed historical runs of the manual workflow, never other workflows or active runs.
- Never expose secrets in Git history, logs, exceptions, artifacts, or diagnostic output.
- Show the exact individual GitHub job page when running Actions; do not substitute CLI logs.

## Review Focus

1. A valid kit callback arrives while an image render is slow: the live must still receive it.
2. A runner dies after Telegram accepted a document but before persistence: recovery must not silently duplicate it.
3. An old callback or unrelated Telegram user targets the current session: no state change.
4. Live and manual request Canva while the token expires: only the broker refreshes, retaining the rotated token.
5. A queued successor and watchdog overlap: do not dispatch a storm or run two pollers.

## Execution baseline and isolation

The local checkout is on an abandoned feature branch with two pre-existing
working-tree entries. Do not merge that branch or overwrite those files.
At execution, obtain worktree consent if none exists, use the native worktree
tool against the latest origin/main, and bring across only these two documents.
Read any applicable AGENTS.md before edits. Run the existing suite before changes:

```powershell
python -m unittest discover -s tests -q
```

Report baseline failures rather than treating them as introduced regressions.
Do not run the production bot or send Telegram messages during unit tests.

## File map

| New file | Responsibility |
|---|---|
| `manual_graphics/__init__.py` | Package marker, no side effects |
| `manual_graphics/config.py` | Validated environment and private-chat identity |
| `manual_graphics/store.py` | Namespaced Gist files, durable offset and state |
| `manual_graphics/telegram.py` | Restricted polling, prompts and original-document delivery |
| `manual_graphics/catalog.py` | Existing player/team catalog and unambiguous choices |
| `manual_graphics/conversation.py` | Pure, JSON-serializable wizard transitions |
| `manual_graphics/render.py` | Adapters to existing renderers |
| `manual_graphics/canva.py` | Broker and read-only live token client |
| `manual_graphics/live_bridge.py` | Kit inbox consumption, no Telegram polling |
| `manual_graphics/service.py` | Single receiver plus one independent render worker |
| `manual_graphics/lifecycle.py` | Dispatch, recovery, disabled state and cleanup |
| `manual_graphics/tests/` | New unit/integration tests and test-only HTTP fixtures |
| `manual_graphics/README.md` | Setup, start/stop, recovery and secrets documentation |
| `.github/workflows/manual_graphics.yml` | Four-hour service and controlled successor |
| `.github/workflows/manual_graphics_recovery.yml` | Recovery check, dispatchable by cron-job |

Existing-file edits are restricted to the agreed integrations in
`dynamic_kit_runtime.py`, `livescore_runner.py`, `.github/workflows/main_espn.yml`,
and adding the new suite to `.github/workflows/tests.yml`.

## Task 1 — Durable state and Telegram boundary

**Files:** config.py, store.py, telegram.py, tests/test_transport.py,
tests/http_fixture.py, package markers.

**Interfaces:**

```python
Config.from_env(env: dict) -> Config
GistStore.read(name: str) -> dict
GistStore.write(name: str, value: dict) -> None
Telegram.poll(offset: int, timeout: int = 20) -> list[dict]
Telegram.prompt(text: str, keyboard: dict | None = None) -> int
Telegram.document(png: bytes, filename: str) -> int
authorized(update: dict, owner_id: int, chat_id: int) -> bool
```

- [ ] Write failing tests for wrong sender, group chat, malformed updates,
  Telegram `ok:false`, private-Gist validation, failed persistence, and PNG
  delivery retaining original bytes. Use a local HTTP server fixture; inspect
  received requests at the external boundary, not mock existence.

```python
def test_wrong_sender_cannot_operate_private_chat(self):
    update = {'message': {'from': {'id': 8}, 'chat': {'id': 7, 'type': 'private'}, 'text': '/grafica'}}
    self.assertFalse(authorized(update, owner_id=7, chat_id=7))

def test_group_chat_is_rejected_even_for_owner(self):
    update = {'message': {'from': {'id': 7}, 'chat': {'id': 7, 'type': 'group'}, 'text': '/grafica'}}
    self.assertFalse(authorized(update, owner_id=7, chat_id=7))
```

- [ ] Run `python -m unittest discover -s manual_graphics/tests -p test_transport.py -v` and observe the missing-behavior failures.
- [ ] Implement explicit-file Gist PATCH; never GET/modify/PATCH all files.
  Read API `content`, handling truncated content via authenticated retrieval
  without forwarding the token to arbitrary URLs. Reject a public Gist before
  any write. File names are constants, never supplied by Telegram.
  Use these ownership boundaries:

```python
FILES = {
    'receiver': 'manual_receiver.json',
    'kit_inbox': 'manual_kit_inbox.json',
    'kit_ack': 'manual_kit_ack.json',
    'canva': 'manual_canva.json',
    'control': 'manual_control.json',
}
```

  Receiver is the sole writer of receiver/inbox/control; live writes only ack;
  the serialized broker writes Canva state. Threads communicate through a
  queue: workers never independently overwrite receiver state.
  Bound inbox by acknowledged IDs; refuse to acknowledge new updates if a
  full inbox cannot be persisted. Do not discard unacknowledged kit changes.
  For errors log category/status, not raw HTTP bodies or token-bearing URLs.
- [ ] Run the task suite and the existing suite. Commit only this deliverable.

## Task 2 — Guided form and catalog

**Files:** catalog.py, conversation.py, tests/test_conversation.py.

**Interfaces:**

```python
Catalog.players(role: str | None = None) -> list[dict]
Catalog.teams(query: str) -> list[dict]
transition(state: dict, update: dict, catalog: Catalog, now: float) -> tuple[dict, list[dict]]
parse_minute(text: str) -> str
parse_score(text: str) -> tuple[int, int]
parse_stat_pair(text: str) -> tuple[str, str] | None
```

- [ ] Write failing literal-input tests for all seven kinds, away Juventus,
  unknown/ambiguous teams, goalkeeper-only SAVED, callback session/revision
  validation, cancellation, inactivity expiry, and correction of a field.

```python
def test_added_time_is_preserved(self):
    self.assertEqual(parse_minute("90+12'"), '90+12')

def test_zero_is_not_missing(self):
    self.assertEqual(parse_stat_pair('0-0'), ('0', '0'))
    self.assertIsNone(parse_stat_pair('-'))

def test_negative_score_is_invalid(self):
    with self.assertRaises(ValueError):
        parse_score('-1-0')
```

- [ ] Observe failures with `python -m unittest discover -s manual_graphics/tests -p test_conversation.py -v`.
- [ ] Implement steps: kind, competition, kit, Juventus side, opponent,
  player/minute where relevant, score, optional shootout, stats phase/rows,
  confirmation. Enumerate valid kinds and kits; do not dispatch on user code.
  Validate score integers 0–99; minutes 0–120 plus recovery 0–99; strip a final
  minute apostrophe. Stats accept finite nonnegative numbers, percentages
  within 0–100, and `-` for missing. Reject tied final shootout totals.
  STATS rows follow stats_graphics.ORDER and ask xG immediately after possession.
  Each action returns a JSON effect (`prompt`, `answer_callback`, `enqueue`);
  transition itself performs no network calls.
  Derive players from goal_players.json and team choices from existing
  registries/FCLogo aliases; use ESPN IDs only when mapped, never guessed.
  Every callback includes a short session ID plus revision and option index;
  compare them before applying changes. Page large catalogs within Telegram
  callback/keyboard limits. Escape preview text.
- [ ] Exercise a full wizard through real transitions to `enqueue`, serialize
  and reload halfway, and verify the same completed render parameters.
  Run both suites and commit.

## Task 3 — Canva ownership and rendering adapters

**Files:** canva.py, render.py, tests/test_render.py, tests/test_canva_broker.py.

**Interfaces:**

```python
CanvaBroker.ensure_token(now: float) -> str
CanvaClient.valid_token(now: float) -> str | None
Renderer.render(request: dict) -> bytes
```

- [ ] Write failing tests for every renderer dispatch, fresh phase export,
  no export for kick, missing assets, PNG signature, xG omission, concurrent
  broker clients, expired token, refresh rotation, and failed secret updates.
  Mock only HTTP, not the broker state machine or renderer validation.

```python
def test_expired_broker_record_is_not_returned(self):
    store = MemoryStore({'canva': {'access_token': 'expired', 'expires_at': 10}})
    self.assertIsNone(CanvaClient(store).valid_token(now=11))
```

  Define MemoryStore in test utilities with real read/write copies. Add a local
  OAuth fixture which records refresh calls and returns token pairs; two
  concurrent ensure_token calls must return the same unexpired token with
  one recorded refresh request. Rotation must be durable before returning.
- [ ] Run task tests, verify missing behavior, then implement a broker lock,
  epoch expiry with a 60-second safety margin, and persistence of rotated
  refresh token before repository-secret synchronization. The latest private
  record wins over startup environment. On loss of persistence after rotation,
  retain token in memory, retry the write and notify without logging token data;
  do not pretend the successor is safe until persistence succeeds.
  Broker checks refresh at most once per minute when Canva is configured;
  receiver polling and kit forwarding must continue on OAuth errors.
- [ ] Implement adapter dispatch with current signatures:

```python
if kind == 'goal':
    return goal_graphics.render_goal_card(**event_args).png
if kind == 'saved':
    return goal_graphics.render_saved_card(**saved_args).png
if kind in {'kick', 'half', 'full', 'end_of_90'}:
    layers = None
    if kind != 'kick':
        layers = export_page_one(session, token_provider(), design_id, request_cache)
    return portrait_graphics.phase(**phase_args, layers=layers)
if kind == 'stats':
    html = stats_graphics.build_html(**stats_args)
    return Path(stats_graphics.render(html, hd_output=True)).read_bytes()
raise ValueError('Tipo grafica non valido')
```

  Build allowlisted argument dictionaries, no arbitrary kwargs from Telegram.
  `phase_args` uses kind/home_name/away_name/home_id/away_id/home_goals/
  away_goals/kit/competition/shootout. `shootout` is a pair or None.
  Stats maps phases to HT/2H_END/FT and passes rows, kit, competition,
  league_name, momento and team names/IDs. Event adapters supply their
  existing scorer_name or goalkeeper_name fields plus team/kit/minute/score.
  Request cache paths use generated IDs only and stay under the job temp root.
- [ ] Run real asset render tests for home and each UEFA theme, inspecting
  resulting PNGs without editing visuals. Confirm no sendMessage/sendPhoto
  side effects of rendering. Run full suites and commit.

## Task 4 — Single receiver, rendering worker and live bridge

**Files:** service.py, live_bridge.py, tests/test_service.py,
tests/test_live_bridge.py. Modify dynamic_kit_runtime.py and livescore_runner.py.

**Interfaces:**

```python
Service.tick(now: float) -> None
Service.run(duration: int = 14400) -> None
KitInbox.pending() -> list[dict]
KitInbox.acknowledge(update_id: int) -> None
install_live_bridge(bot, kit_runtime, store) -> None
```

- [ ] Write failing tests for offset durability, duplicated updates, slow render
  plus kit callback, cancelled sessions, uncertain send, and four-hour restart.
  Use threading.Event to hold the render worker while exercising real receiver
  ticks; the inbox must contain the kit update before releasing the render.
  Seed an unacknowledged inbox item, restart the bridge, and verify it is
  consumed once after successful live handling, not merely after retrieval.
- [ ] Run tests red. Implement one main-loop state owner, queue.Queue for
  worker results, and a single render executor. Poll messages/callbacks;
  persist state/inbox before advancing offset. Deduplicate persisted update
  IDs. A failed write causes backoff without advancing Telegram confirmation.
  The live bridge replaces only the source of callbacks, retaining existing
  event validation, kit update, recap update and media refresh behavior.
  No draining Telegram in centralized mode and no fallback competing poller.
  Legacy mode remains unchanged until the integration flag is enabled.
- [ ] Persist delivery status before making sendDocument; set delivered only
  after recording Telegram's message ID. On restart, `sending` becomes
  `uncertain`; offer explicit reinvio instead of automatic duplicate delivery.
  Render failures return an actionable prompt and leave the receiver running.
  At the deadline, stop accepting work, snapshot form state, shut down the
  worker within a bounded grace period and let unfinished rendering resume.
- [ ] Wire CanvaClient at live startup only in centralized mode; expired or
  missing access token returns None through the existing phase fallback.
  Preserve standalone live behavior when the integration is disabled.
- [ ] Test resetta_gist does not delete the generator files, and no manual
  operation writes match_state.json or uses the production destination.
  Run both suites and commit.

## Task 5 — Four-hour workflow, recovery and cleanup

**Files:** lifecycle.py, tests/test_lifecycle.py, both new workflow YAML files,
README.md. Modify main_espn.yml and tests.yml only as listed below.

**Interfaces:**

```python
ensure_successor(api, repository: str, ref: str, current_run_id: int) -> bool
cleanup_completed(api, repository: str, workflow_id: int, current_run_id: int) -> list[int]
recovery_check(api, store, now: float) -> bool
```

- [ ] Write failing tests using actual lifecycle logic and HTTP fixtures for:
  existing queued successor, pagination, failed run, active other workflow,
  disabled service, dispatch error, and repeated configuration failures.

```python
def test_cleanup_excludes_active_and_foreign_runs(self):
    # HTTP fixture serves completed run 11 for the target workflow,
    # active run 12, and completed run 13 belonging to another workflow.
    removed = cleanup_completed(self.api, 'owner/repo', 5, 12)
    self.assertEqual(removed, [11])
    self.assertEqual(self.http.deleted_run_ids, [11])
```

- [ ] Run tests red; implement REST dispatch and paginated run listing with
  allowlisted workflow identifiers. Skip current and non-completed runs.
  Keep a persistent enabled flag; `/ferma_generatore` requires confirmation
  and suppresses handoff/recovery. Explicit start clears disabled state.
  Limit uncontrolled restarts after three failures in fifteen minutes;
  record the reason without secrets. Recovery skips active/queued/pending
  manual runs. Dispatcher serialization is separate from service serialization.
- [ ] Implement workflow structure:

```yaml
name: Bot JR manual graphics
on:
  workflow_dispatch:
    inputs:
      test_mode:
        type: boolean
        default: true
permissions:
  contents: read
  actions: write
concurrency:
  group: jr-manual-graphics-service
  cancel-in-progress: false
jobs:
  receiver:
    runs-on: ubuntu-latest
    timeout-minutes: 280
```

  Checkout approved main, setup Python 3.14, reuse dependency/browser caches,
  install the existing requirements and Chromium dependencies. Pass secrets
  through env, not command arguments. The service chooses 14,400 seconds in
  normal mode, 900 seconds in test mode. Successor dispatch runs after receiver
  exit on controlled success/failure, not cancellation and not test mode.
  A hard timeout is recovered externally; do not rely on a killed runner.
  Cleanup uses the typed lifecycle helper, scoped to this workflow only.
  Recovery YAML has its own concurrency group and no rendering dependencies;
  workflow_dispatch allows cron-job to trigger its check. Add a GitHub schedule
  as best-effort fallback but document queue/delay limitations.
- [ ] Add centralized integration env flag to main_espn.yml with default off;
  rollout switches it only with no old live run active. Add the new test suite
  as a checked step in tests.yml and include it in final failure status, not
  an ignored continue-on-error step.
- [ ] Document required TELEGRAM_TOKEN, TELEGRAM_TO_BOT, owner ID, GH_PAT,
  GIST_ID and Canva secrets; use a private positive-ID chat as owner default
  only after getChat validation. No new public storage. Document start/stop,
  restart limiter, optional cron-job POST setup, consumption, and no SLA.
  Run lifecycle suite, workflow structural validation, and both full suites.
  Commit this independently testable deliverable.

## Task 6 — End-to-end verification and controlled rollout

**Files:** tests/test_end_to_end.py, README.md verification record.

- [ ] Write failing integration coverage that drives `/grafica` through real
  conversation, durable store, renderer adapter and document transport against
  local external-service fixtures. Repeat for interrupted form and slow render
  while the live bridge processes a kit callback. Verify rendered PNG bytes,
  destination and delivery state, not just handler call counts.
- [ ] Run and fix only integration defects exposed by these tests; leave all
  unrelated visuals/logic untouched. Run:

```powershell
python -m unittest discover -s tests -q
python -m unittest discover -s manual_graphics/tests -q
git diff --check
```

- [ ] Review complete diff against DESIGN.md and global constraints. Record
  failures honestly. Do not claim runtime availability from unit tests alone.
- [ ] Verify repository visibility, allowance and required secrets without
  printing secret values. Ensure old polling live jobs have finished. If not,
  defer activation rather than cancelling them without permission.
- [ ] Run one test-mode job with no successor. Show the exact live job page.
  Ask user to exercise a GOAL and a Canva phase on Bot JR, then verify original
  PNG delivery and resume behavior. Do not publish to the public channel.
- [ ] Only after successful validation, activate normal four-hour mode and
  the centralized live integration together. Configure recovery if authorized
  and available; otherwise report it as not configured, not silently complete.
  Show first active job and tell user how to stop the staffetta.

## Self-review

All planned new artifacts are in the dedicated package or workflow directory.
No renderer/layout edits are planned. Each of the five review risks is assigned
to tests in tasks 1–6. The execution base must be latest main, not the old local
feature branch. This document is a plan, not an implemented service.
