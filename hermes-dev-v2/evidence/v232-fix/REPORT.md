# L1/L2 local rework — pending independent review — DO NOT INSTALL

Base: afd44df10909f365b39216e7676498d48c59870a. No commit or push.
Mandatory SECURITY-REVIEW-V232.md and evidence/v232/INDEPENDENT-REVIEW.json
were read before changes and remain unchanged. This is implementation evidence,
not an independent PASS or externally issued owner authorization.

## Narrow changes

L1: corrected only the two stale exact VERSION literals in the protected v2
workflow; release assertion and every security assertion remain intact. Tests
execute all three actual exact version commands and all three static blocks
(including workflow-contract and release-gate), extracted from workflow bytes.

L2: both doctors call their existing production owner_manifest contract and
report boolean owner_authorized; overall ok additionally requires that status.
Manifest objects and pins must be dictionaries, avoiding an uncaught exception
for a list containing the pin names. Gate and doctor use this same validation.
No external pins are generated or installed as authority. Raw transport output
was replaced by fixed status text to avoid propagating arbitrary diagnostic data.

## Strict RED before implementation

All new regression test bytes were written and executed before implementation
changes. 01-red.log reproduced L1 and missing doctor checks. 02-red-contract.log
added direct gate parity before doctor checks; it also exposed a test fixture
mistake (release head equaled base). That fixture was corrected before any fix.
03-red.log is the final pre-implementation run: 4 tests, 47 failing subtests and
3 errors (missing owner_authorized plus two malformed pins-list exceptions).
No failed run is represented as a pass. No tests were weakened after RED.
04-green.log: the same final tests pass after fixes (4 tests).

## Actual verification

Every test/workflow execution below used the existing unchanged
regression_health.py harness: disposable clone with working owner files overlaid,
bwrap mount/PID/network/user namespaces, cleared environment, zero capabilities,
no_new_privs; isolation probes passed. No production gate imports or execution.

- 01–04: `python3 hermes-dev-v2/regression_health.py python3 -m unittest discover -s tests/hermes_autopilot -p test_v232_blockers.py -v`
- 05-full-owner-suite.log: `python3 hermes-dev-v2/regression_health.py python3 -m unittest discover -s tests/hermes_autopilot -v` — exit 0, 160 test executions, 6.767 seconds.
- 06-actual-workflow.log: harness command and all exact executed shell blocks are in the log; all three blocks exit 0. This includes syntax/static security, generic branch workflow assertions, and release root/Git surface assertions. No assertion was weakened or skipped within those blocks.
- INVENTORY.json: computed by inventory.py, cross-checking Git blob hashing against `git hash-object --no-filters`, and computing the installer composite digest without candidate imports.

L2 matrix: valid, missing, malformed JSON, file/ancestor symlinks, unsafe file
mode/UID/GID, unsafe ancestor mode/UID/GID, hardlink, FIFO, oversized input,
duplicate fields, wrong version/schema, invalid base, missing/invalid pin,
pins list, null and extra field. Both doctors and actual gate pin/history
validators see the same fixtures. Valid authorization passes with other fixture
prerequisites satisfied; unavailable tools/key still fail overall. Controller
aggregation rejects either failed gate. Canary text/base/pins are not returned.
Fixture filesystem entry metadata is compared before/after doctors and checks.

Owner metadata is modeled with fstat spies because isolation is unprivileged;
real file opens/reads, nofollow behavior, modes and link counts are exercised.
Root entry checks, transport/key authorization and remote trees/API are fixture
substitutions. These tests do not prove real owner identity, transport, installed
OS trust or live GitHub CI. Counts include inherited tests and parameterized
subtests, not independent end-to-end security properties.

## Delivery boundary

No installation/preparation workflow step or --apply was invoked. The static
workflow checks inspect the inherited installer script but do not execute it.
The full existing owner suite includes disposable fixture install/rollback
functions; these are not production installation. Legacy v2.1 installer smoke
is not current bootstrap acceptance. No live doctor, production writes/imports,
sudo, keys/secrets/sudoers access, dependency installation, friend edits or
unrelated edits. Trusted runtime auto OFF; Manual/server approval; Jump DENY.

Exact inventory is candidate identity only. Independent review and independently
authenticated owner pins/digests and immutable base are still required. Handoff
and bootstrap metadata point to this inventory; no self approval is implied.
