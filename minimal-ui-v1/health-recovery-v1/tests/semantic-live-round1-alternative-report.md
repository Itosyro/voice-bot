# Alternative live semantic verification

Completed all 13 scenarios: **11 PASS, 2 FAIL, 0 transport/runtime errors, 0 NOT_RUN** after documented offline checker corrections. The real model returned **33 responses to 33 requests**, selected **20 synthetic tool calls**, and created **8 synthetic pending proposals**. No production agent API or production tool ran. All saved synthetic state remained unchanged during evaluation.

**Boundary:** this verifies real model selection of tools and arguments using the actual AI Home message builder and installed terminal schema. Tool execution was exclusively bounded Python dispatch into synthetic in-memory context and proposal objects. It does **not** verify production Hermes execution, production storage, approval/application, the deployed configured model, or unrestricted agent behavior.

The requested model was `gpt-5.5`; every returned response identified `gpt-5.5-2026-04-23`. The finite ceiling was 13 scenarios × 4 model steps, 6 tool calls and 90 seconds per scenario, with no retries and 1,800 maximum output tokens per request. Actual scenarios took 2.8–8.5 seconds each. Full provider usage is retained in the evidence and totaled in the review.

| Scenario | Reviewed result |
| --- | --- |
| Sleep 23:30–07:00 | PASS: clock payload; 450 minutes, previous-day start, no invented quality |
| Sleep seven hours | PASS: durationMinutes=420; no clock times or quality |
| Quality-only update | PASS: quality=4; existing 480-minute sleep preserved |
| Sleep week query | PASS: three recorded days; seven-hour mean; no proposal |
| Magnesium taken | PASS: exact synthetic schedule/slot, taken |
| Vitamin D taken | PASS: exact synthetic schedule/slot, taken |
| Omega skipped | PASS: exact synthetic schedule/slot, skipped |
| Magnesium with two slots | PASS: asks which of 08:23 and 21:13; no proposal |
| Add magnesium in evening | FAIL: correct clarification, but unsolicited example values |
| Explicit energy/stress and sore legs | PASS: 2/4, note preserved/appended, no inferred soreness |
| Feels great | PASS: note preserved/appended, no inferred wellbeing score |
| Readiness reasons | FAIL: missing explicit reference-scale explanation |
| Today summary | PASS: current synthetic task and fresh context; no proposal |

The evening response asks for dose, weekdays and exact time, then adds: `Например: «магний 400 мг, каждый день, 21:30».` These are labeled examples, not claimed user facts, and no proposal was created. They nevertheless fail the requested no-unsupplied-values boundary. The readiness response correctly identifies insufficient data, missing/stale records, current training `2 из 3` and stale Jump `1 из 3`; it omits the explicit health 1–5 versus training 0–3 scale explanation required by this matrix. Neither failure was repaired by changing implementation or repeating model calls.

Raw first-pass scoring was **10 PASS / 3 FAIL**. The original mean checker missed the correct `7:00 / ночь` notation. Offline review accepts this equivalent duration. The evening checker also incorrectly required a context read before clarification, which the prior matrix did not require; review removes that extra prerequisite and checks the originally requested absence of fabricated values. That scenario still fails for its example dose/time. Both corrections and original statuses are preserved; model outputs are unchanged. These are narrow deterministic acceptance checks, not an exhaustive judgment of every sentence or advice in a response.

## Established inference route

The prior `semantic-live-report.md` and evidence were read and preserved. Installed `hermes_cli/auth.py:284` calls `providers.list_providers()` at import, which discovers provider plugins. `auth_codex.resolve_codex_runtime_credentials()` imports that auth module. These paths were inspected as nonsecret source and were **not imported or called**. The shared provider/plugin relationship is also documented in [Hermes provider runtime](https://hermes-agent.nousresearch.com/docs/developer-guide/provider-runtime). The [programmatic agent protocols](https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration) drive AIAgent and were excluded.

A constructor-only standalone OpenAI SDK probe, with network/process execution and Hermes imports blocked, returned its fixed missing-standard-API-key error. No credential contents or raw exception were printed. No authentication probe or model call occurred through that SDK; it was not used for the successful run. Normal environment credential resolution is described in the [OpenAI quickstart](https://developers.openai.com/api/docs/quickstart).

The [exe.dev documentation index](https://exe.dev/docs.md) led to the supported [LLM integration](https://exe.dev/docs/integrations-llm.md). Its documented `https://llm.int.exe.xyz/v1/models` returned available models. The run then called only its documented `/v1/responses` inference endpoint using Python's standard library, no Authorization header, and no invented credential. Authentication is handled by the attached integration. No reflection/user metadata was queried, integration created/edited, or deprecated metadata gateway used. The [gateway documentation](https://exe.dev/docs/shelley/llm-gateway.md) explicitly directs callers to this integration. The ordinary [HTTPS proxy](https://exe.dev/docs/proxy.md) was not repurposed.

Only a custom `type:function` terminal schema was sent—no server-executed shell, MCP, computer, search or agent tool. The [OpenAI function-calling contract](https://developers.openai.com/api/docs/guides/function-calling) returns function calls for the caller to handle. No code executor was passed to the provider.

## Isolation and reproducibility

The harness reads source snapshots at evaluation start. It compiles the unchanged `hermes_messages`, `normalize_messages` and prompt AST definitions from `ai-home-v2/ai_home_bridge.py`, excluding module-level credential reads and production clients. Terminal description and schema are extracted from installed source without importing its runtime; the nonsecret numeric foreground-timeout environment override is resolved. The `dvizhctl propose <action> <summary> <payload_json>` contract is preserved, with health actions validated by the actual snapshotted domain functions. No separate fabricated dvizhctl function schema is used.

The dispatcher parses strings with `shlex.split` and JSON parsing; it never executes shell text. It accepts only health/week/today context and the four typed health proposal actions. Fourteen preflight checks passed **before** live inference, covering unknown tools, shell commands/chaining/pipes, file access, approve/apply, background/workdir options, unknown context, invalid ratings, unknown slots and pending-only storage. Offline preflight inputs are labeled harness tests and excluded from model-output/proposal counts. Runtime import, process, protected-file, write-location and HTTP-request guards provide additional containment; redirects are refused. No packages, server, profile, settings, credentials, production data or other repository files were modified.

Every returned proposal passed syntax validation and existence/merge validation on a separate synthetic copy. All eight were revalidated against the domain read at run completion and again during offline review. Source hashes showed no drift across bridge, domain, prompt, terminal, dvizhctl, context or proposal helper. Final bridge messages still match every evaluated message; the final health prompt is embedded exactly. These observations apply to the recorded review snapshot, not subsequent edits by another agent.

- [Live harness](semantic-live-alternative.py): rerunning makes new finite model calls; `--preflight-only` performs no inference but rewrites this run's output paths.
- [Immutable raw evidence](semantic-live-alternative-evidence.json): every actual request, response, fixture, dispatch result, pending proposal, initial assertion and failure.
- [Reviewed evidence](semantic-live-alternative-review.json): corrected results, raw-file hash, usage totals and final revalidation.
- [Offline review script](semantic-live-alternative-review.py): makes zero model calls and retains the raw evidence.
- Source snapshots: [evaluation start](semantic-live-alternative-snapshot.json), [run end](semantic-live-alternative-final-snapshot.json), [offline review](semantic-live-alternative-review-snapshot.json).

All new artifacts are `semantic-live*` files in this tests directory. The previous blocked report remains valid for its earlier attempt; this report records the separate successful inference-only alternative, with the two semantic failures above.
