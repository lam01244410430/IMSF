"""Eval comparison logic for IMSF-v2 Phase 1 (design §8).

Pure functions — no DB, no HTTP, no GPU — so they are unit-testable
in isolation. A ground-truth line is correct only when all four
fields (raw_name, quantity, unit, price) match; accuracy is
correct lines / total ground-truth lines across all receipts, and
the Phase 1 gate is accuracy > 0.90 (strictly greater).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

GATE_THRESHOLD = Decimal("0.90")
TOLERANCE = Decimal("0.01")  # quantity / price comparison tolerance

BUCKETS = (
    "ocr_char",
    "mapping",
    "quantity",
    "unit",
    "price",
    "total_mismatch",
    "missing_line",
    "extra_line",
)

TERMINAL_STATUSES = ("completed", "failed", "needs_review")


def normalize_name(name) -> str:
    """Normalise a raw_name for comparison: strip all whitespace,
    case-insensitive. Same normalisation the worker uses for canonical
    mapping (app.reconcile.normalize_name)."""
    return "".join(str(name or "").split()).lower()


def to_decimal(value) -> Decimal | None:
    """Decimal(str(v)) so JSON floats (56.1) and strings compare sanely."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def numbers_equal(a, b, tolerance: Decimal = TOLERANCE) -> bool:
    """Decimal comparison with tolerance (56.10 vs 56.1 passes)."""
    da, db = to_decimal(a), to_decimal(b)
    if da is None or db is None:
        return False
    return abs(da - db) <= tolerance


def line_fields_match(predicted: dict, truth: dict) -> tuple[bool, str | None]:
    """Check the four §8 fields. Returns (match, first differing field
    or None). Field order for the differing-field report is
    quantity -> unit -> price (raw_name is checked first by the caller
    when pairing by name)."""
    if normalize_name(predicted.get("raw_name")) != normalize_name(
            truth.get("raw_name")):
        return False, "raw_name"
    if not numbers_equal(predicted.get("quantity"), truth.get("quantity")):
        return False, "quantity"
    if (str(predicted.get("unit") or "").strip().lower()
            != str(truth.get("unit") or "").strip().lower()):
        return False, "unit"
    if not numbers_equal(predicted.get("price"), truth.get("price")):
        return False, "price"
    return True, None


def _mapping_ok(predicted: dict, truth: dict) -> bool:
    """Canonical mapping check: the expected canonical_name from ground
    truth must equal the predicted canonical_name (normalised). A null
    expected canonical means the predicted line must be unmatched."""
    expected = truth.get("canonical_name")
    got = predicted.get("canonical_name")
    if expected is None:
        return got is None
    if got is None:
        return False
    return normalize_name(got) == normalize_name(expected)


def compare_receipt(fixture_id: str, truth: dict, predicted_lines: list[dict],
                    status: str, error_message: str | None = None,
                    total_amount=None) -> dict:
    """Compare one receipt's predicted lines against its ground truth.

    Pairing (greedy, one-to-one, in this order):
    1. exact 4-field matches;
    2. same normalised raw_name -> bucket = first differing field
       (quantity / unit / price);
    3. same (quantity, unit, price) triple but different raw_name ->
       ``ocr_char``;
    4. leftover truth lines -> ``missing_line``;
    5. leftover predicted lines -> ``extra_line``.

    A line whose four fields match counts CORRECT for accuracy even if
    its canonical mapping is wrong; that case is counted separately in
    the ``mapping`` bucket (see README — design §8 defines correctness
    by the four fields only). ``total_mismatch`` is counted once per
    receipt when the predicted line sum differs > 2% from the receipt
    total (design §6.4) or the worker's reconcile message says so.
    """
    truths = list(truth.get("lines") or [])
    preds = list(predicted_lines or [])
    used_pred: set[int] = set()
    verdicts: list[dict] = []
    taxonomy = {b: 0 for b in BUCKETS}

    def verdict(truth_idx, pred_idx, ok, bucket, detail,
                mapping_error=False):
        verdicts.append({
            "truth_index": truth_idx,
            "predicted_index": pred_idx,
            "verdict": "correct" if ok else "wrong",
            "bucket": bucket,
            "detail": detail,
            "mapping_error": mapping_error,
            "truth": truths[truth_idx] if truth_idx is not None else None,
            "predicted": preds[pred_idx] if pred_idx is not None else None,
        })

    # Pass 1: exact 4-field matches.
    remaining_truth = list(range(len(truths)))
    for ti in list(remaining_truth):
        for pi, pred in enumerate(preds):
            if pi in used_pred:
                continue
            ok, _ = line_fields_match(pred, truths[ti])
            if ok:
                used_pred.add(pi)
                remaining_truth.remove(ti)
                mapping_error = not _mapping_ok(pred, truths[ti])
                if mapping_error:
                    taxonomy["mapping"] += 1
                verdict(ti, pi, True, "mapping" if mapping_error else None,
                        "all 4 fields match"
                        + ("; canonical mapping wrong"
                           if mapping_error else ""),
                        mapping_error=mapping_error)
                break

    # Pass 2: same raw_name, one field differs.
    for ti in list(remaining_truth):
        for pi, pred in enumerate(preds):
            if pi in used_pred:
                continue
            if normalize_name(pred.get("raw_name")) == normalize_name(
                    truths[ti].get("raw_name")):
                used_pred.add(pi)
                remaining_truth.remove(ti)
                _, field = line_fields_match(pred, truths[ti])
                bucket = {"quantity": "quantity", "unit": "unit",
                          "price": "price"}.get(field, "quantity")
                taxonomy[bucket] += 1
                verdict(ti, pi, False, bucket,
                        f"raw_name matches but {field} differs: "
                        f"truth={truths[ti].get(field)!r} "
                        f"predicted={pred.get(field)!r}")
                break

    # Pass 3: same (quantity, unit, price), different raw_name -> OCR char.
    for ti in list(remaining_truth):
        for pi, pred in enumerate(preds):
            if pi in used_pred:
                continue
            if (numbers_equal(pred.get("quantity"), truths[ti].get("quantity"))
                    and str(pred.get("unit") or "").strip().lower()
                    == str(truths[ti].get("unit") or "").strip().lower()
                    and numbers_equal(pred.get("price"),
                                      truths[ti].get("price"))):
                used_pred.add(pi)
                remaining_truth.remove(ti)
                taxonomy["ocr_char"] += 1
                verdict(ti, pi, False, "ocr_char",
                        f"quantity/unit/price match but raw_name differs: "
                        f"truth={truths[ti].get('raw_name')!r} "
                        f"predicted={pred.get('raw_name')!r}")
                break

    # Pass 4: leftover truth lines are missing.
    for ti in remaining_truth:
        taxonomy["missing_line"] += 1
        verdict(ti, None, False, "missing_line",
                "no predicted line for this ground-truth line")

    # Pass 5: leftover predicted lines are extra.
    for pi, pred in enumerate(preds):
        if pi not in used_pred:
            taxonomy["extra_line"] += 1
            verdicts.append({
                "truth_index": None,
                "predicted_index": pi,
                "verdict": "wrong",
                "bucket": "extra_line",
                "detail": "predicted line has no ground-truth counterpart",
                "mapping_error": False,
                "truth": None,
                "predicted": pred,
            })

    # Receipt-level total check (design §6.4): > 2% line-sum vs total.
    total_mismatch = False
    total_dec = to_decimal(total_amount)
    if total_dec is not None and total_dec > 0 and preds:
        line_sum = sum((to_decimal(p.get("price")) or Decimal("0")
                        for p in preds), Decimal("0"))
        if abs(line_sum - total_dec) / total_dec > Decimal("0.02"):
            total_mismatch = True
    if error_message and "lệch" in error_message:
        total_mismatch = True
    if total_mismatch:
        taxonomy["total_mismatch"] += 1

    correct = sum(1 for v in verdicts if v["verdict"] == "correct")
    truth_count = len(truths)
    return {
        "fixture_id": fixture_id,
        "status": status,
        "error_message": error_message,
        "truth_lines": truth_count,
        "predicted_lines": len(preds),
        "correct_lines": correct,
        "accuracy": (correct / truth_count) if truth_count else 0.0,
        "taxonomy": taxonomy,
        "total_mismatch": total_mismatch,
        "line_verdicts": verdicts,
    }


def compute_accuracy(results: list[dict]) -> dict:
    """Overall accuracy = total correct lines / total ground-truth lines."""
    truth_total = sum(r["truth_lines"] for r in results)
    correct_total = sum(r["correct_lines"] for r in results)
    taxonomy_total = {b: 0 for b in BUCKETS}
    for r in results:
        for b in BUCKETS:
            taxonomy_total[b] += r["taxonomy"].get(b, 0)
    accuracy = (correct_total / truth_total) if truth_total else 0.0
    return {
        "receipts_evaluated": len(results),
        "truth_lines": truth_total,
        "predicted_lines": sum(r["predicted_lines"] for r in results),
        "correct_lines": correct_total,
        "accuracy": accuracy,
        "gate": float(GATE_THRESHOLD),
        "passed": accuracy > float(GATE_THRESHOLD),
        "taxonomy": taxonomy_total,
    }
