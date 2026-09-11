# v2.3.1 actual evidence — INCOMPLETE, DO NOT INSTALL

Base/HEAD: `fbbfad02e61882c174660a3ef7db384546d80e6a` (unchanged).
No independent review, commit, push, installation, production imports or sudo.
Only allowed workspace paths changed; scope-audit.log records Git status/diff check.
No live skill access or edits. No live-file checksum audit was performed.

## Five-cycle ledger

1. RED `01-red.log`: 1 harness contract failure (old source rewriting).
   GREEN `01-green.log`: 1 PASS with actual namespace isolation probes.
2. RED `02-red.log`: Jump policy failure and candidate-helper invocation error.
   GREEN `02-green.log`: 3 PASS; direct helper execution removed and Jump denied.
3. RED `03-red.log`: adjacent candidate import failure; race fixture also failed.
   Standalone/bootstrap and buffered-install fix: existing installer suite 4 PASS
   (`03-installer-suite.log`). `03-attempt-failed.log`: new race fixture still
   failed because its directories inherited group-writable modes. NOT GREEN.
4. Correct only the new fixture's directories to required 0755. `04-green.log`:
   5 PASS. This is explicitly counted as a correction cycle, not hidden as a retry.
   Race coverage exercises replacement after buffering; it did not independently
   reproduce the original digest-before-read exploit. Broader race TDD remains due.
5. RED `05-red.log`: both privileged entry points failed to reject incomplete
   hardening. GREEN `05-green.log`: 6 PASS after root entry rejection. This only
   quarantines unfinished paths; it does not implement the missing boundaries.

No implementation/test fixes after cycle five. Documentation/status updated to
reflect incomplete work. Existing owner tests were not weakened or edited.

## Exact commands and results

Run from `/home/exedev/.hermes/dev/dvizh/owner-maintenance-v2.3.1`.
Commands execute test bytes only in temporary clones under namespace containment.
The initial RED used `/tmp/v231-sandbox-run.py` (preserved as
`bootstrap-harness.py`); subsequent runs use the repository harness.

```sh
python3 /tmp/v231-sandbox-run.py python3 -m unittest discover -s tests/hermes_autopilot -p test_hardening_v231.py -v
# Cycle 1 RED: exit 1, 1 failure.

python3 hermes-dev-v2/regression_health.py python3 -m unittest discover -s tests/hermes_autopilot -p test_hardening_v231.py -v
# Repeated at each recorded RED/GREEN state; see ledger/logs.
# Final cycle 5: exit 0, 6 tests PASS.

python3 hermes-dev-v2/regression_health.py python3 -m unittest discover -s tests/hermes_autopilot -p 'test_*install*.py' -v
# Exit 0: 4 tests PASS.

python3 hermes-dev-v2/regression_health.py
# Exit 0: 154 owner tests PASS, including existing rollback/adversarial tests.

python3 hermes-dev-v2/regression_health.py --health bash minimal-ui-v1/health-recovery-v1/tests/run.sh
# Exit 1: 41 Python PASS, 6 Node PASS; browser cannot find Playwright.

python3 hermes-dev-v2/regression_health.py --health bash -c 'node --test tests/ai-home-v2/*.test.cjs'
# Exit 1: 100 tests, 99 PASS, 1 FAIL; routing diagnostic cannot find awk.

python3 hermes-dev-v2/regression_health.py --health python3 tests/ai-home-v2/bridge_contract_test.py
# Exit 0: 2 PASS.

python3 hermes-dev-v2/regression_health.py python3 -m pytest
# Exit 1: /usr/bin/python3: No module named pytest. No full-repo tests collected.

git diff --check
# Exit 0.
```

Health/AI Home runs use complete history at
`9d492693de2c7cf66350293afcf42b74edeebaef`; the earlier missing-archive-history
mistake is avoided. Logs contain actual command/exit records and isolation probes.
The shell used output redirection into the corresponding evidence logs; outer
inspection commands may exit zero even where COMMAND_EXIT records a test failure.

## Remaining blockers, not waivers

- Fixed production component sandbox/service API with stripped environment/groups,
  no new privileges, and binding candidate-byte behavioral tests: absent.
  dvizh account membership is not confinement from secrets/friend/control-plane.
- Caller-repo read privilege separation and sanitized immutable root Git object
  boundary: absent. Malicious config/hooks/includes/SSH/credential/env adversarial
  export tests are not implemented. Root entry rejection is containment only.
- Independently enforced owner workflow/validator SHA pins and protected path
  history: absent. CI-PINS-v231.json is observed inventory, NOT approved/enforced.
  No workflow substitution or always-green workaround was introduced.
- Installer bootstrap independent authentication and broader immutable staging
  concurrency/race regression proof: pending. Do not install the quarantined gates.
- Health browser dependency absent inside isolation; no installation authorized.
  awk symlink needs its alternatives target in a reviewed minimal runtime image;
  exposing host /etc wholesale is not an acceptable shortcut. No sixth fix made.
- Full-repo pytest/dependencies absent inside isolation. Other exhaustive domain
  suites, browser/device voice, actual restart/recovery and live CI remain unverified.
- v2.2 orchestration approval provenance remains the explicitly allowed limitation;
  the bearer phrase does not attest Telegram identity.

Owner readiness is NOT established. Independent review must follow completion;
this implementation run does not count as independent review.
