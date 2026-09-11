# v2.3.2 local implementation evidence

No independent security verdict is asserted. No owner approval pins/digests were
issued. Mandatory prior reviews were read before changes and retained unchanged.
The revised scope retires schema-2 runtime auto deployment and restores schema 1
from da7395e436563774a29f7694b258bd85987bed2f plus root state fix and Jump denial.

## Commands and observed results

All test commands ran via the existing OS isolation harness. Its probes verified
host sentinel/home/installed-gate invisibility, blocked external network, zero
effective capabilities and NoNewPrivs. Supplementary IDs in this unprivileged
harness are partly unmapped; this is not proof of a real production privilege drop.

Focused command:

```
python3 hermes-dev-v2/regression_health.py python3 -m unittest discover -s tests/hermes_autopilot -p test_foundation_v232.py -v
```

- 01-red.log: exit 1. Real harmless fsmonitor executed; protected add/remove history
  was accepted; root quarantine rejected the functional entry assertion. The first
  schema-2 test used an invalid empty manifest and already succeeded; it alone was
  not evidence for feature retirement. Valid former targets are now tested separately.
- 02-green.log: exit 0, four tests after the initial fixes.
- 03-boundaries.log: exit 0, six tests including real sanitized object export and
  protected history/pin rejection. These additional boundary tests were added
  after their implementation; not every assertion in this task was strict TDD.
- 07-bootstrap-red.log: exit 1, bootstrap input followed a symlink.
- 08-bootstrap-green.log: exit 0 after no-follow/nonblocking regular-file reads.

Complete suite commands:

```
python3 hermes-dev-v2/regression_health.py python3 -m unittest discover -s tests/hermes_autopilot -q
python3 hermes-dev-v2/regression_health.py python3 -m unittest discover -s tests/hermes_autopilot -v
```

- 04-suite-integration-red.log: exit 1; 162 tests, 19 errors and two failures,
  principally old positive schema-2 assertions and obsolete quarantine assertions.
- 05-owner-suite.log: exit 1; 147 tests, one failure. Workflow fixture still imported
  from the candidate path after workflow switched to independently extracted code.
- 06-owner-suite.log: exit 0; 150 tests after adapting that extraction fixture.
- 09-complete-owner-security.log: exit 1; 156 tests, one fixture setup error. The new
  installer-race fixture inherited suite umask and lacked explicitly safe directory
  modes; installer correctly rejected it. Fixture directory modes were corrected.
- **10-complete-owner-security.log: exit 0; 156 tests, all completed successfully.**
  This is the final complete available owner/security suite. No missing dependencies
  blocked it; no system installation was needed. Successful per-test rows from the
  intermediate 05/06/09 logs were omitted to avoid duplicate evidence; their diagnostic
  sections and summaries remain. The final full log is retained.

Final static checks: `git diff --check` exited 0; AST parsing of the five owner
Python sources succeeded; tracked/untracked paths were confined to authorized
owner directories and protected workflows. RESULTS.json contains a local source
inventory, not approved installation hashes. No commit or bundle was made.

## Actual adversarial coverage and its limits

The foundation tests execute real harmless fsmonitor/hooks, included executable
Git config, hostile Git environment values, export/index-pack, HEAD mutation,
bootstrap digest rejection, adjacent malicious Python module isolation and
verified-buffer replacement. They also exercise actual fixture installation
functions after the final prepare buffer was captured. No --apply command or
production installation was invoked.

A subprocess spy checks that root caller-Git launch requests the invoking UID,
primary GID and empty supplementary groups with a stripped environment. A
transport spy sees the exact captured SHA refspec after caller HEAD/config changes.
Those tests do not execute a real privileged transition or network push.

Release history/CI probes use synthetic authenticated API responses to test
protected intermediate commits, pin changes, missing jobs despite green runs,
and a valid approved history. Local Git tests exercise actual add/remove commits.
API authentication, live workflow execution, key/known-host access and actual
production-root functionality remain untested. No installed source was imported
or executed. Full feature/runtime acceptance is outside the revised user scope.

The obsolete schema-2 positive tests were replaced with explicit retirement tests.
Existing schema-1/v2.2 approval, rollback, signal, concurrency, immutable-source and
metadata suites remain in discovery. This intentionally changes the test count;
it does not claim the retired runtime feature still works.

## Outstanding limitations

Independent review and external authentication remain pending. The implementation
has not received an approved v2.3.2 immutable base, installed owner manifest,
workflow base-variable rollout or authenticated bootstrap/payload digest. These
must come from the owner/reviewer, not this candidate. The code implements those
contracts but this local task cannot provision them without violating its scope.
The installer intentionally does not invent or install owner authorization.

The requested strict RED-before-GREEN discipline was achieved for the initial
regressions and bootstrap path finding, but additional boundary coverage was
written after implementation. This procedural shortfall is recorded explicitly.
No claim of comprehensive race/DoS, OS crash durability, supply-chain or whole
repository security coverage is made. See OWNER-HANDOFF.md for trust assumptions,
rollout prerequisites and the retained v2.2 bearer-approval limitation.
