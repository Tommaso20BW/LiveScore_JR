# Execution ledger — manual_graphics/PLAN.md

Base: main 16be63c; work branch feat/manual-graphics.
Pre-existing Canva working-tree entries preserved in stash before switching;
no old feature implementation was carried onto this branch.

## Binding update from user

Manual workflow_dispatch only. 1,800 seconds listening. NO successor,
schedule, cron recovery, automatic dispatch or restart workflow. Cleanup only
old completed runs of this workflow after exit. This supersedes all relay and
four-hour requirements in the earlier design/plan.

## Rulings

- A temporary service cannot own Telegram/Canva permanently. Use an explicit
  handoff for Telegram: manual announces its run, waits for live acknowledgement,
  then polls and forwards kit callbacks. At exit live resumes polling; if a
  manual runner dies, live verifies its GitHub completion before resuming.
  No two independent offsets against Telegram. Cost: manual startup can wait
  for the live to reach its polling boundary; an old unintegrated live blocks
  startup safely rather than losing its callbacks.
- Canva tokens use shared private Gist state and a Git fast-forward CAS mutex
  only during refresh. Either live or manual can renew while the other is off.
  No secrets in Git: lock commits contain only owner run metadata. Cost: brief
  GitHub API dependency when a token needs renewal, no ongoing listener needed.
- Preserve the existing checkout via a dedicated feature branch and named
  stash; no reset, overwrite or merge of the abandoned feature branch.

## Verification

- Existing suite initially: 152 tests, 3 environment errors (PyMuPDF missing).
  Installed PyMuPDF and PyYAML for local verification; no requirements change.
- First new contract tests: RED, new conversation module missing.
- Final local verification: 152 existing tests and 41 manual-generator tests
  pass; compileall passes. Real kick-off renderer checked for PNG dimensions;
  Telegram/Canva remote calls covered with test doubles, not a production run.
- Independent review found stale handoff acknowledgements on rerun and stale
  Canva lock ownership. Added unique handoff request UUIDs, run-attempt lock
  metadata, and deleted-run detection requiring verified Actions read access.
  Regression tests observed RED before the fixes, then GREEN.
- Valid cached Canva tokens avoid Git mutex writes. Prompt outbox retries
  failed questions without advancing the form twice.
- Completed PNGs remain buffered through temporary state-read failures;
  ambiguous deliveries never trigger an automatic duplicate.

## Status

Implementation verified locally; publishing to main as explicitly requested.
The generator is not dispatched as part of installation.
