# IMSF-v2 Phase 1 — eval harness (Step 4, design §8)

Measures receipt-pipeline accuracy against ground-truth JSONs and
classifies every error. Harness only: it does not change the API,
worker, or reconciliation code.

## Ground-truth format

One JSON per receipt, next to its image, same stem
(`tests/fixtures/<id>.json` + `tests/fixtures/<id>.png`):

```json
{
  "store_name": "永辉超市",
  "purchased_at": "2026-11-20T09:12:00+08:00",
  "total_amount": 56.10,
  "currency": "CNY",
  "lines": [
    {"raw_name": "农夫山泉 550ml", "quantity": 2, "unit": "瓶",
     "price": 4.00, "canonical_name": "Nước suối", "is_stock_item": true}
  ]
}
```

Same shape as design §5.3 / §8. `canonical_name` is the expected
canonical ingredient (or `null` when the line should stay unmatched);
it is used only for the `mapping` taxonomy bucket, never for the
accuracy count. `is_stock_item` is `false` for discounts / bag fees /
tax / service fees (negative price allowed only there).

**Privacy rule (from the plan):** real receipt images must not
contain personal info — cover names / people before committing.
Synthetic fixtures are exempt but must stay labelled SYNTHETIC
(the 6 fixtures in `tests/fixtures/` are all synthetic).

**Status: 6 SYNTHETIC fixtures only, 0 real receipts.** The full
50-receipt set needs real supermarket receipts (Chinese + Vietnamese,
including wrinkled / blurry / torn ones) — that collection is Lam's
step. Do not fabricate real receipts to fill the set.

## Accuracy

`accuracy = correct lines / total ground-truth lines` across all
receipts. A line is correct only if all 4 fields match — `raw_name`
(normalised: all whitespace removed, case-insensitive), `quantity`,
`unit`, `price` (Decimal, 0.01 tolerance, so 56.10 vs 56.1 passes).
**Gate: accuracy > 90%** (strictly greater). The runner prints
PASS/FAIL and exits 0 on PASS, 1 on FAIL, 2 on run error.

## Error taxonomy

Every wrong line lands in exactly one bucket:

| Bucket | Meaning |
|---|---|
| `ocr_char` | quantity/unit/price match but `raw_name` differs |
| `mapping` | 4 fields right but canonical mapping wrong/missing |
| `quantity` | `raw_name` matches but quantity differs |
| `unit` | `raw_name` matches but unit differs |
| `price` | `raw_name` matches but price differs |
| `total_mismatch` | receipt needs_review/failed, line sum > 2% off total (§6.4) |
| `missing_line` | ground-truth line with no predicted counterpart |
| `extra_line` | predicted line with no ground-truth counterpart |

Notes (literal readings, recorded where the design is silent):
- A `mapping`-wrong line still counts CORRECT for accuracy (§8
  defines correctness by the 4 fields only); mapping errors are
  reported separately in the taxonomy.
- `total_mismatch` is counted once per receipt, not per line.
- A line differing in 2+ fields takes the first differing field in
  the order quantity → unit → price (after a `raw_name` match).

## Running it

From the repo root on Oregon, env sourced (service token included):

```bash
set -a; . /home/ubuntu/imsf-v2.env; set +a
.venv/bin/python -m tests.eval.run_eval \
  --fixtures tests/fixtures --provider mock --out tests/eval/last-run
```

Flags: `--provider mock|baidu|qwen-vl` (sets OCR_PROVIDER for the
in-process worker), `--qwen mock|real` (default: mock when the
provider is mock, else real), `--worker in-process|external`
(default in-process — the runner drains the Redis job itself and
calls `worker.main.process_job`; a live worker must NOT be running
in this mode, the runner preflights for it), `--base-url`
(default `http://127.0.0.1:8002`), `--timeout` seconds per receipt
(default 300), `--gate` (default 0.90), `--out` (default
`tests/eval/last-run`, git-ignored).

Outputs in `--out`: `report.json` (machine-readable: metadata,
per-receipt verdicts, totals, taxonomy) and `report.md` (readable
summary: per-receipt table, taxonomy counts, worst receipts).
Run metadata in the report: date (Asia/Shanghai), provider, Qwen
mode, worker mode, commit hash, branch, receipts evaluated.

## Mock Qwen (no-GPU runs)

With `--provider mock --qwen mock` the worker's Qwen parse is
replaced by `tests/eval/mock_qwen.py`: a deterministic regex parser
of the OCR text (same `§6.3` output shape). It never sees ground
truth — it only reads the OCR text the real Qwen would receive.
**Limitation, stated plainly:** the mock OCR text is canned for one
receipt (`app.ocr.MOCK_OCR_TEXT`), so fixtures with different
content cannot match it and the mock-run accuracy number measures
the harness + mapping/reconciliation pipeline, NOT Qwen's real
accuracy. The real > 90% gate needs the real Qwen (or Baidu OCR)
path on real receipts.

## Tests

```bash
.venv/bin/python -m pytest tests/test_eval_harness.py -q
```

Covers: exact match, one-field-wrong for each of the 4 fields,
Decimal tolerance, hand-built accuracy, one taxonomy case per
bucket, the mock Qwen parser, and the runner's PASS/FAIL exit
codes (fake API client — no DB/GPU needed).
