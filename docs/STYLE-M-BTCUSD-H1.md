# Style M — BTCUSD H1 Visual Daily

Style M is the default BTCUSD daily route from 2026-08-28. It produces one
short answer-first Markdown article (two analytical H2 sections) and one deterministic H1 WebP
from the latest closed Bangkok H1 candle at invocation time. For example, a
09:10 Bangkok run uses the candle that closed at 09:00 and excludes the
09:00-10:00 forming candle. There is no fixed daily cutoff hour. E+ remains
available only through its explicit manual pipeline; it is not a daily-route option.

## Daily command

`python -m tools.run_daily`

The default command invokes M for BTCUSD when `production=true` in
`config/article_styles.json`. Run M alone with:

`python -m tools.run_daily --style M --asset btcusd`

## Output contract

- Final: `output/<DD-MM-YYYY>/TH-Thailand/M/BTCUSD/`
- The selector verifies that country folder in place and writes its internal
  report under `work/selection/<DD-MM-YYYY>/`; it does not create a web-ready
  copy under `0-ขึ้นเว็บวันนี้`.
- Internal evidence: `work/build/<DD-MM-YYYY>/btcusd/internal/style-m/`
- Exactly one `btc.md` and one `btcusd-style-m-h1-<YYYY-MM-DD>.webp`
- Web frontmatter uses the registered `asset: btc`, `title`, `slug`, `excerpt`,
  `author_slug`, `timeframe`, `trend`, and `status: draft`,
  `country: thailand`, and `language: th`. Decision state codes such as
  `NO_PLAN` are internal evidence only; public copy uses reader-facing wording
  and never replaces the upload status.
- The image is 1920×1080 WebP on a white background with green/red candles.
- The left histogram uses 72 thin price-occupancy bins, not source volume.
- The decision badge stays inline with the title; the chart uses the remaining
  canvas without a duplicate bottom Entry/SL/RR strip or footer disclaimer.
- Internal v5 evidence stores `semantic-decision.json`,
  `article-visual-facts.json`, `writer-claim-report.json`,
  `renderer-claim-report.json`, `claim-parity-report.json`, and
  `index-policy.json` under `style-m-daily-manifest/v3`. The writer and
  renderer bind public text and visual geometry to the same typed claims; a
  value, label, unit, source, fragment, or trendline-anchor mismatch blocks the
  package before either public lane is moved.

The primary selector verifies country final files in place. It must not create,
remove, or rely on a legacy selection-copy folder.

## Decision states

- `NO_PLAN`: article and image are still produced, without Entry/SL/TP geometry.
- `WAIT_H1_CONFIRM`: conditional levels may be shown, but no active order is claimed.
- `PLAN_VALID`: the confirmed plan and risk levels are shown.
- `INVALIDATED`: article and image are produced without actionable trade geometry.
  These machine state codes stay in internal evidence; public copy uses reader-facing wording.

All decisions use closed H1 candles only. Source, freshness, article, image,
idempotency, and collision gates fail closed. A second write with identical hashes
is a no-op; a different package at the same destination is held for review and is
never silently overwritten. External publishing is not performed by this route.

## Semantic and claim contract (M-PROD/v5)

- `style-m-story/v1` remains the immutable decision oracle. The v5 semantic
  layer is a deterministic projection and cannot change state, side, or reason.
- Article and visual facts use `style-m-article-visual-facts/v2`; claim parity
  uses `style-m-claim-parity-report/v2`.
- Trendline anchors and breakout evaluation are selected once by the semantic
  layer. The writer and renderer may consume that canonical result but may not
  select another pair independently.
- A confirmed intermediate high above a descending candidate line invalidates
  that candidate. Selection continues deterministically to the next valid pair,
  otherwise the trendline is not shown.
- Legacy v1/v4 evidence is read-only. The
  `style-m-v1-prior-adapter/v1` records its source hash and marks it as not
  comparable to v5, so it cannot cause a duplicate hold by silent equivalence.

## Risk and execution geometry (M-PROD/v5)

- Entry zone width: 0.25 ATR14 from the latest confirmed structural anchor.
- Stop Loss: 0.75 ATR14 beyond that anchor.
- Worst-entry risk: 1.00 ATR14 from the adverse edge of Entry to Stop Loss.
- RR is calculated from the adverse Entry edge and excludes actual fees, spread,
  and slippage. The article must say that the stop level is not a guaranteed fill.
- Position size must be reduced proportionally when the stop distance is wider.
- H1 confirmation uses the closed price crossing the trigger boundary; candle
  colour is irrelevant.
- Confirmation does not authorize chasing price. Execution waits for a retest of
  the fixed Entry zone.
- Before execution, RR is recalculated from the expected fill. TP1 must remain at
  least 1.50 RR and TP2 at least 2.00 RR; the story carries the limiting fill price.
- Pre-trigger invalidation and post-entry Stop Loss are rendered as separate rules.
- Prior v4 evidence is read-only from `work/build`; the current local-date
  folder (including immutable 31-08-2026 evidence) is excluded. A repeated
  `NO_PLAN` is held when its semantic levels remain within `0.10 ATR14` and its
  reason/EMA relation are unchanged; it never enters the web-ready lane.
