# Manual · Quiet Signal v2

Production artifact: `../release/manual.html`. This separate builder leaves the
existing minimal-UI patcher, installer and tests unchanged. It does not build AI
Home or read `/opt` at build/test time.

```sh
python minimal-ui-v1/quiet-signal/build_manual.py
python minimal-ui-v1/quiet-signal/build_manual.py --check
python -m unittest discover -s minimal-ui-v1/quiet-signal/tests -v
```

The final suite executes 12 tests, including both unchanged legacy component
tests through a unittest adapter (pytest is unavailable; nothing was installed).
`--check` is read-only and works from any current directory.

## Baseline and exact changes

The four public static source files were copied read-only from
`/opt/dvizh/static/` on 2026-09-08. No state, credentials, API responses or private
configuration were captured. Their SHA-256 hashes are pinned independently in
the builder and snapshot tests:

| File | SHA-256 |
| --- | --- |
| manual.html | `c0e5ea92c829807320db58e4ed015215f8cbea59b03c5d7ed3bdb80ecce3696f` |
| styles.css | `4fc9de09753daffb3dcacba770684b7f6a152c23a9956fb85a797beba068c8c5` |
| app.js | `392b49d5e28438a7cf9ca8753d3f3bbcd307b77417e8f2c39b11cd28682f71ba` |
| boot.js | `1c766410e239a8092de001d6450da6fabcdd552a91f7de593abb0d626fbb0500` |

The build inserts exactly one style block before `</head>` and one header after
`<body>`. Removing those additions reproduces every original byte. Tests assert
this exact transformation as well as old tags/attributes, script contents and
order, and the prior `data-nav` shortcut fix. Baseline drift fails closed.
CSS insertion rejects HTML breakouts, escapes, imports, URLs and expressions.
The new header has ordinary `/` and `/manual.html` links, an accessible mode-nav
name, current-page semantics, visible keyboard focus, 44px targets and safe-area
spacing. It adds no `data-nav`, event handlers, scripts, forms or data.

The CSS uses the approved prototype's near-black palette, mint buttons, soft
text, rounded borders and section accents. It overrides both existing minimal
mode states and preserves safety-state colors. All eight mobile routes are
visible. Secondary panels start closed in minimal mode; the first Details click expands
them and the second collapses them. Native `hidden` elements and inactive views
stay hidden. Existing emojis are retained without adding decorative emoji noise.

Infographics use existing outputs only: the focus ring's live `--progress`, proof
calendar counts and `has-proof` states, training/jump metric labels and values,
and six social pipeline stages with their live counts and cards. No proportions,
tasks, metrics or example datasets are introduced. Existing baseline defaults and
copy are intentionally unchanged.

## TDD evidence and limits

`evidence/` contains the observed failures before each implementation slice:

- `01-snapshot-red.txt`: missing pinned snapshot and builder.
- `02-additions-red.txt`: absent mode links and additive/safety interface.
- `03-visual-red.txt`: missing dark tokens, mobile/deep-section overrides and real-data styling.
- `04-release-red.txt`: stale release rejected by `--check` before regeneration.
- `05-proof-count-red.txt`: proof count styling did not target the actual live `strong` output.
- `full-green.txt`: all 12 component tests pass after the final build.
- `browser-blocked.txt`: Chromium launch denied by the managed sandbox.

`tests/browser.cjs` supplies six offline Playwright checks covering 320, 390, 760,
900 and 1440px navigation, shortcuts, mode-link focus/targets, persistent header,
deep panels, dark palette with minimal mode on/off and both tones, and timer
custom-property rendering. It serves only local source fixtures and an isolated
sync stub through request interception, with `script-src 'self'` and no API access.
The installed browser could not launch (`sandbox_host_linux.cc:41`, `Operation
not permitted`), so computed styles, rendered layout and live interactions are
**not browser-verified** in this environment. No escalation was attempted.
To run in a browser-capable environment with Playwright already present:

```sh
node minimal-ui-v1/quiet-signal/tests/browser.cjs
```

If Playwright is outside normal module lookup, set `NODE_PATH` to its existing
`node_modules`; `CHROMIUM_EXECUTABLE` optionally selects an existing browser.

This HTML expects the existing site assets beside `/manual.html`; the release
folder is not a standalone app. Script URLs/content remain unchanged and require
no CSP relaxation. The added style element requires a CSP that permits inline
styles; it introduces no inline JavaScript. External asset compatibility is
pinned to the recorded versions; no claim is made about future asset changes.
Real synchronization, authenticated APIs and deployment were not exercised.

## Files added

- `../release/manual.html`: deterministic production HTML.
- `build_manual.py`, `manual.css`, `mode_header.html`: build and additive sources.
- `baseline/{manual.html,styles.css,app.js,boot.js}`: immutable public snapshots.
- `tests/{test_build.py,test_styles.py,test_release.py,browser.cjs}`: regression suites.
- `evidence/*.txt`: RED, final GREEN and browser limitation records.
- `README.md`: provenance, commands, file inventory and caveats.

All authored changes are under `minimal-ui-v1/`. No commits, pushes, deployment,
installs, sudo or writes to the installed app were performed. Other agents' AI
Home, test and workflow edits were left alone.
