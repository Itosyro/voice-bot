# Additional owner-authorized correction cycle 1 / maximum 5

Existing job: 20260909-115201-e37585. Only cycle 1 executed; no extra retry or correction cycle.

RED before source edits: `cycle1-red.log`, 2 tests with 37 failures (36 whitespace subcases and missing prompt contract). The previous round-2 feels-great semantic failure remains immutable evidence. GREEN: `cycle1-green.log`, both tests pass (198 differential cases across 30 whitespace and 3 non-whitespace code points, name/dose/note, empty and padded text). No existing tests/assertions weakened or removed.

Explicit text policy: trim only U+0009–000D, U+001C–0020, U+0085, U+00A0, U+1680, U+2000–200A, U+2028, U+2029, U+202F, U+205F, U+3000, U+FEFF at boundaries. Interior characters remain; name/dose must remain nonempty; empty notes are valid; pre-trim code-point length limits unchanged. This frozen Python/ECMAScript union is explicit in both helpers.

Prompt requires only user-changed fields, required identities, and note-only feels-great updates even when energy:3 already exists. Domain partial-update behavior and architecture are unchanged.

Rebuilt full health runner: 41 Python tests, 6 Node tests, 4 Chromium flows PASS, including temporary HTTP/CAS concurrency, generated-byte reproducibility over 16 artifacts and preservation checks. Existing job test-auto: quick, ai-home-v2, hermes-control PASS. See `cycle1-full-green.log` and `cycle1-test-auto-green.log`.

Real inference round 3: same guarded alternative harness (only output namespace changed), same route https://llm.int.exe.xyz/v1/responses, requested gpt-5.5, returned gpt-5.5-2026-04-23. 33 requests/responses, 20 synthetic tool calls, 8 pending synthetic proposals. Zero production tool/agent API calls. No source drift; all 8 returned payloads revalidated. No model retries.

Raw: 12/13 PASS, 1 FAIL (evening_schedule required_context=false). Separate established offline review: 13/13 PASS; clarification may ask missing dose/time/weekdays without reading context. Raw failure is retained, not rewritten. Independent offline inspection of all outputs is saved separately. Feels-great passes the original strict assertion and exact payload keys are day/timezone/note: `{"day":"2026-09-10","timezone":"Europe/Moscow","note":"Ранее: прогулка у реки. feels great"}`. No energy or other structured rating is repeated. Note-only scoring is unchanged.

Round-1/2 and other prior semantic files (32 files) plus ARCHITECTURE-AUDIT.md are hash-verified unchanged in `cycle1-preserved-evidence.json`. Round-3 raw/snapshot/review artifacts have their own SHA256 manifest. The audit stays unchanged.

Both requested local blockers are resolved in this cycle. This is bounded inference-only acceptance, not full production Hermes acceptance. Hosted CI, production smoke and release remain unperformed. No commit, push, deployment, production writes, sudo, credentials/config reads, other profiles, friend paths, control-plane changes, new job or architecture change was performed in this cycle. No next cycle started.
