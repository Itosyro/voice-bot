#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1
python3 minimal-ui-v1/health-recovery-v1/build.py
python3 -m unittest discover -s minimal-ui-v1/health-recovery-v1/tests -p 'test_*.py'
node --test minimal-ui-v1/health-recovery-v1/tests/findings.cjs minimal-ui-v1/health-recovery-v1/tests/sync-round2.cjs
node --check minimal-ui-v1/health-recovery-v1/dist/app.js
node minimal-ui-v1/health-recovery-v1/tests/browser.cjs
node minimal-ui-v1/health-recovery-v1/tests/mixed-cache.cjs
node minimal-ui-v1/health-recovery-v1/tests/approval-browser.cjs
node minimal-ui-v1/health-recovery-v1/tests/sync-concurrent-browser.cjs
