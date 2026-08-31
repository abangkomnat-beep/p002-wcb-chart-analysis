# Style M v6 — Predeclared strategy-variant diagnostics

ใช้ snapshot เดียวกับ QA 180 วัน; grid ถูกกำหนดก่อนดูผล และเลือกได้จาก IS เท่านั้น (OOS มีไว้ทานสอบ).

| Variant | IS TP1 after-cost R | IS TP2 after-cost R | OOS TP1 after-cost R | OOS TP2 after-cost R | IS gate |
|---|---:|---:|---:|---:|---|
| baseline | -0.640516 | -0.624779 | -0.69064 | -0.667538 | FAIL |
| adx20 | -0.720903 | -0.775246 | -0.642395 | -0.543919 | FAIL |
| adx25 | -0.739728 | -0.653238 | -0.701506 | -0.539534 | FAIL |
| adx20_reclaim | -0.584638 | -0.663476 | -0.423914 | -0.343351 | FAIL |
| adx25_reclaim | -0.648237 | -0.555926 | -0.501133 | -0.336562 | FAIL |
| adx20_limit | -0.664575 | -0.700261 | -0.455255 | -0.4228 | FAIL |
| adx20_reclaim_12h | -0.374429 | -0.70139 | -0.257894 | -0.008715 | FAIL |

## Interpretation

- ADX filter trades less often; it may reduce noise but can discard profitable transitions.
- Reclaim-close improves confirmation but delays entry and can miss fast continuations.
- Trigger-limit geometry improves nominal RR but requires a deeper pullback and is more sensitive to non-fill and execution assumptions.
- 12-hour expiry reduces stale plans but lowers the sample and can remove valid late-session setups.
- No variant is promoted by this grid. Only variants passing the predeclared IS gate may proceed to a fresh, untouched OOS validation window.
