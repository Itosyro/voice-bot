# Reproducible verification

Run from the existing managed worktree. No production credentials, API mutations,
DB reads, sudo, or network model call is needed. Tests launch the pinned server
on ephemeral localhost ports with temporary state and synthetic identities.

```bash
bash minimal-ui-v1/health-recovery-v1/tests/run.sh
```

Local defaults:

- Chromium: `/home/exedev/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`
- Playwright: `/home/exedev/.hermes/dev/dvizh/browser-tools-sync-stability/node_modules/playwright` (installed version 1.63.0)
- Python 3 with zoneinfo; Node with built-in test dependencies only. jsdom is not needed.

Other environments can set `CHROMIUM_PATH` and `PLAYWRIGHT_MODULE`. The supplied
`.github/workflows/dvizh-health-recovery.yml` installs isolated pinned browser
tools on the CI runner and runs the same acceptance entry point.

Individual commands:

```bash
python3 minimal-ui-v1/health-recovery-v1/build.py
python3 -m unittest discover -s minimal-ui-v1/health-recovery-v1/tests -p 'test_*.py'
node --test minimal-ui-v1/health-recovery-v1/tests/findings.cjs minimal-ui-v1/health-recovery-v1/tests/sync-round2.cjs
node --check minimal-ui-v1/health-recovery-v1/dist/app.js
node minimal-ui-v1/health-recovery-v1/tests/browser.cjs
node minimal-ui-v1/health-recovery-v1/tests/mixed-cache.cjs
node minimal-ui-v1/health-recovery-v1/tests/approval-browser.cjs
node minimal-ui-v1/health-recovery-v1/tests/sync-concurrent-browser.cjs
git diff --check
```

`build.py` verifies snapshot hashes before emitting self-contained helper sources,
frontend output, and separate manifests. It only reads this worktree. Do not run
older frontend patchers/installers to generate this release: their repository base
lags production. Generated output under `dist/` is intentionally not ignored.

Installed gate validation already performed (pure validation, no release proposal):

```bash
python3 - <<'PY'
import json, runpy
from pathlib import Path
gate = runpy.run_path('/usr/local/sbin/dvizhrelease', run_name='manifest_validation')
for path in sorted(Path('.autopilot').glob('health-recovery-*.json')):
    result = gate['validate_manifest']({'mode': 'safe'}, json.loads(path.read_text()))
    print(path.name, result['risk'], result['approval_required'])
PY
```

Expected: AI Home `approval True`, frontend `approval True`, privileged helpers
`ai-integration-privileged True`. This command does not create a release proposal.

Independent findings and legacy profile validation (tests only):

```bash
dvizhautopilot test-auto 20260909-115201-e37585
```

The feature suite includes recursive prototype-key rejection, own-property-safe
remote merges, malformed/redacted context, partial confirmation identities,
midnight day/zone binding, strict Python/JS values, and legacy helper contracts.
The installed `hermes-control` profile checks syntax; behavioral coverage lives
in the feature suite. Historical voice isolation uses the immutable voice release;
the current contract protects exact existing files and pinned generated assets.

Final review regressions: `tests/round2-red.log` records pre-fix failures, including
real concurrent browser HTTP saves using `sync-concurrent-browser.cjs --baseline-sync`.
`tests/round2-green.log` is the complete rebuilt feature suite;
`tests/round2-test-auto-green.log` records the authorized installed test profile.

Additional cycle 1 evidence: `tests/cycle1-red.log`, `tests/cycle1-green.log`,
`tests/cycle1-full-green.log`, `tests/cycle1-test-auto-green.log`. Round-3 inference
and offline review use preserved copies `semantic-live-round3-alternative.py`
and `semantic-live-round3-alternative-review.py`; running the inference again
would overwrite round-3 evidence and requires a fresh namespace and authorization.
Do not rerun these immutable-evidence outputs as ordinary offline tests.
