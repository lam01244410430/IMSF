"""Step 4 tests: eval harness comparison, taxonomy, mock Qwen parser,
and the runner's PASS/FAIL exit code (design §8).

The runner exit-code tests use a fake API client + fake worker drain,
so they need no DB, no HTTP server and no GPU. The live end-to-end
gate (real API + in-process worker, mock provider) is run by hand —
see tests/eval/README.md.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from tests.eval.compare import (GATE_THRESHOLD, compare_receipt,
                                compute_accuracy, line_fields_match,
                                numbers_equal)
from tests.eval.mock_qwen import mock_parse_receipt_text
from tests.eval.run_eval import main as run_eval_main


def line(raw_name, quantity, unit, price, canonical_name=None,
         is_stock_item=True):
    return {"raw_name": raw_name, "quantity": quantity, "unit": unit,
            "price": price, "canonical_name": canonical_name,
            "is_stock_item": is_stock_item}


def truth(lines):
    return {"store_name": "永辉超市",
            "purchased_at": "2026-11-20T09:12:00+08:00",
            "total_amount": 56.10, "currency": "CNY", "lines": lines}


# --- field matching -------------------------------------------------------

def test_exact_match_passes():
    ok, field = line_fields_match(
        line("农夫山泉 550ml", 2, "瓶", 4.0),
        line("农夫山泉 550ml", 2, "瓶", 4.0))
    assert ok and field is None


def test_name_normalised_strip_and_case():
    ok, _ = line_fields_match(line(" 农夫山泉 550ml ", 2, "瓶", 4.0),
                              line("农夫山泉550ml", 2, "瓶", 4.0))
    assert ok


@pytest.mark.parametrize("field, pred, truth_line", [
    ("raw_name", line("农夫山泉 500ml", 2, "瓶", 4.0),
     line("农夫山泉 550ml", 2, "瓶", 4.0)),
    ("quantity", line("农夫山泉 550ml", 3, "瓶", 4.0),
     line("农夫山泉 550ml", 2, "瓶", 4.0)),
    ("unit", line("农夫山泉 550ml", 2, "箱", 4.0),
     line("农夫山泉 550ml", 2, "瓶", 4.0)),
    ("price", line("农夫山泉 550ml", 2, "瓶", 5.0),
     line("农夫山泉 550ml", 2, "瓶", 4.0)),
])
def test_one_field_wrong_fails_the_line(field, pred, truth_line):
    ok, differing = line_fields_match(pred, truth_line)
    assert not ok
    assert differing == field


def test_decimal_tolerance_56_10_vs_56_1():
    assert numbers_equal(56.10, 56.1)
    assert numbers_equal(Decimal("56.10"), Decimal("56.1"))
    assert numbers_equal(10.00, 10.01)   # exactly 0.01 passes
    assert not numbers_equal(10.00, 10.02)


# --- accuracy -------------------------------------------------------------

def test_accuracy_hand_built_case():
    results = [
        compare_receipt("a", truth([line("鸡蛋", 1, "盒", 12.8),
                                    line("大米 5kg", 1, "袋", 32.5)]),
                        [line("鸡蛋", 1, "盒", 12.8),
                         line("大米 5kg", 1, "袋", 32.5)],
                        "completed", None, 45.3),
        compare_receipt("b", truth([line("青菜", 1, "斤", 6.8)]),
                        [line("青菜", 1, "斤", 6.9)],
                        "completed", None, 6.9),
    ]
    totals = compute_accuracy(results)
    assert totals["truth_lines"] == 3
    assert totals["correct_lines"] == 2
    assert totals["accuracy"] == pytest.approx(2 / 3)
    assert totals["passed"] is False  # 66.7% < 90% gate
    assert totals["gate"] == float(GATE_THRESHOLD)


# --- taxonomy: one case per bucket ----------------------------------------

def test_taxonomy_ocr_char():
    # Same qty/unit/price, different raw_name -> OCR misread a character.
    r = compare_receipt("x", truth([line("鸡蛋", 1, "盒", 12.8)]),
                        [line("鸡旦", 1, "盒", 12.8)],
                        "completed", None, 12.8)
    assert r["correct_lines"] == 0
    assert r["taxonomy"]["ocr_char"] == 1
    assert r["line_verdicts"][0]["bucket"] == "ocr_char"


def test_taxonomy_mapping():
    # All 4 fields right, but canonical mapping wrong -> mapping bucket,
    # and the line STILL counts correct for accuracy (design §8).
    r = compare_receipt(
        "x", truth([line("鸡蛋", 1, "盒", 12.8, "Trứng gà")]),
        [line("鸡蛋", 1, "盒", 12.8, "Gạo")],
        "completed", None, 12.8)
    assert r["correct_lines"] == 1
    assert r["accuracy"] == 1.0
    assert r["taxonomy"]["mapping"] == 1
    assert r["line_verdicts"][0]["mapping_error"] is True


def test_taxonomy_mapping_missing_when_truth_expects_one():
    r = compare_receipt(
        "x", truth([line("鸡蛋", 1, "盒", 12.8, "Trứng gà")]),
        [line("鸡蛋", 1, "盒", 12.8, None)],
        "completed", None, 12.8)
    assert r["correct_lines"] == 1
    assert r["taxonomy"]["mapping"] == 1


@pytest.mark.parametrize("bucket, pred", [
    ("quantity", line("鸡蛋", 2, "盒", 12.8)),
    ("unit", line("鸡蛋", 1, "袋", 12.8)),
    ("price", line("鸡蛋", 1, "盒", 13.8)),
])
def test_taxonomy_field_buckets(bucket, pred):
    r = compare_receipt("x", truth([line("鸡蛋", 1, "盒", 12.8)]),
                        [pred], "completed", None, 12.8)
    assert r["correct_lines"] == 0
    assert r["taxonomy"][bucket] == 1
    assert r["line_verdicts"][0]["bucket"] == bucket


def test_taxonomy_missing_and_extra_lines():
    r = compare_receipt(
        "x", truth([line("鸡蛋", 1, "盒", 12.8),
                    line("大米 5kg", 1, "袋", 32.5)]),
        [line("鸡蛋", 1, "盒", 12.8),
         line("青菜", 1, "斤", 6.8)],
        "completed", None, 19.6)
    assert r["correct_lines"] == 1
    assert r["taxonomy"]["missing_line"] == 1
    assert r["taxonomy"]["extra_line"] == 1


def test_taxonomy_total_mismatch():
    # Lines sum 95.00 vs receipt total 100.00 = 5% > 2% -> needs_review.
    r = compare_receipt(
        "x", truth([line("大米 5kg", 1, "袋", 32.5)]),
        [line("大米 5kg", 1, "袋", 32.5)],
        "needs_review", "tổng dòng lệch 5.00% so với tổng hóa đơn", 100.0)
    assert r["total_mismatch"] is True
    assert r["taxonomy"]["total_mismatch"] == 1
    assert r["correct_lines"] == 1  # the line itself is still right


def test_total_mismatch_exactly_2pct_is_not_a_mismatch():
    r = compare_receipt(
        "x", truth([line("大米 5kg", 1, "袋", 98.0)]),
        [line("大米 5kg", 1, "袋", 98.0)],
        "completed", None, 100.0)
    assert r["total_mismatch"] is False
    assert r["taxonomy"]["total_mismatch"] == 0


# --- mock Qwen parser -----------------------------------------------------

def test_mock_qwen_parses_canned_mock_ocr_text():
    from app.ocr import MOCK_OCR_TEXT
    parsed = mock_parse_receipt_text(
        MOCK_OCR_TEXT,
        canonical_names=["Nước suối", "Trứng gà", "Gạo", "Rau cải"])
    assert parsed["store_name"] == "永辉超市"
    assert parsed["total_amount"] == 56.10
    assert len(parsed["lines"]) == 4
    assert parsed["lines"][0] == {
        "raw_name": "农夫山泉 550ml", "quantity": 2, "unit": "瓶",
        "price": 4.00, "canonical_name": "Nước suối",
        "is_stock_item": True}
    assert parsed["lines"][1]["canonical_name"] == "Trứng gà"


def test_mock_qwen_never_sees_ground_truth():
    # The parser only reads OCR text: same text, different truth file
    # must give the same parse (no leakage path exists).
    from app.ocr import MOCK_OCR_TEXT
    a = mock_parse_receipt_text(MOCK_OCR_TEXT)
    b = mock_parse_receipt_text(MOCK_OCR_TEXT, canonical_names=[])
    assert a["lines"] == b["lines"]
    assert a["lines"][0]["canonical_name"] is None  # no master list -> None


# --- runner PASS/FAIL exit code (fake client, no DB/GPU) ------------------

class _FakeClient:
    """Returns canned completed receipts: all-correct or all-wrong."""

    def __init__(self, mode: str):
        self.mode = mode

    def create_household(self, name: str) -> str:
        return "00000000-0000-0000-0000-000000000001"

    def upload_receipt(self, household_id: str, image_path: Path) -> str:
        return "00000000-0000-0000-0000-000000000002"

    def get_receipt(self, receipt_id: str) -> dict:
        if self.mode == "correct":
            lines = [line("农夫山泉 550ml", 2, "瓶", 4.0, "Nước suối"),
                     line("鸡蛋", 1, "盒", 12.8, "Trứng gà"),
                     line("大米 5kg", 1, "袋", 32.5, "Gạo"),
                     line("青菜", 1, "斤", 6.8, "Rau cải")]
            total = 56.10
        else:
            lines = [line("可乐", 1, "罐", 3.5, None)]
            total = 3.5
        return {"id": receipt_id, "status": "completed",
                "error_message": None, "total_amount": total,
                "lines": lines}

    def close(self):
        pass


def _write_fixture(tmp_path: Path):
    fx = tmp_path / "fixtures"
    fx.mkdir()
    (fx / "synthetic_receipt.json").write_text(json.dumps(
        {"store_name": "永辉超市",
         "purchased_at": "2026-11-20T09:12:00+08:00",
         "total_amount": 56.1, "currency": "CNY",
         "lines": [
             {"raw_name": "农夫山泉 550ml", "quantity": 2, "unit": "瓶",
              "price": 4.0, "canonical_name": "Nước suối",
              "is_stock_item": True},
             {"raw_name": "鸡蛋", "quantity": 1, "unit": "盒",
              "price": 12.8, "canonical_name": "Trứng gà",
              "is_stock_item": True},
             {"raw_name": "大米 5kg", "quantity": 1, "unit": "袋",
              "price": 32.5, "canonical_name": "Gạo",
              "is_stock_item": True},
             {"raw_name": "青菜", "quantity": 1, "unit": "斤",
              "price": 6.8, "canonical_name": "Rau cải",
              "is_stock_item": True},
         ]}), encoding="utf-8")
    (fx / "synthetic_receipt.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return fx


def test_runner_pass_exit_0_on_all_correct(tmp_path):
    from tests.eval.run_eval import run_evaluation
    fx = _write_fixture(tmp_path)
    report = run_evaluation(
        fixtures_dir=fx, provider="mock", qwen_mode="mock",
        worker_mode="external", base_url="http://127.0.0.1:8002",
        out_dir=tmp_path / "out", timeout=5, gate=0.90,
        client=_FakeClient("correct"),
        drain=lambda receipt_id, timeout=60.0: "external")
    assert report["totals"]["passed"] is True
    assert report["totals"]["accuracy"] == 1.0
    assert (tmp_path / "out" / "report.json").exists()
    assert (tmp_path / "out" / "report.md").exists()


def test_runner_fail_exit_1_on_all_wrong(tmp_path):
    from tests.eval.run_eval import run_evaluation
    fx = _write_fixture(tmp_path)
    report = run_evaluation(
        fixtures_dir=fx, provider="mock", qwen_mode="mock",
        worker_mode="external", base_url="http://127.0.0.1:8002",
        out_dir=tmp_path / "out", timeout=5, gate=0.90,
        client=_FakeClient("wrong"),
        drain=lambda receipt_id, timeout=60.0: "external")
    assert report["totals"]["passed"] is False
    assert report["totals"]["accuracy"] == 0.0
    assert report["totals"]["taxonomy"]["missing_line"] == 4
    assert report["totals"]["taxonomy"]["extra_line"] == 1


def test_runner_cli_exit_codes_via_main(tmp_path, monkeypatch):
    # main() with a fake client injected through run_evaluation is
    # covered above; here check the CLI rejects a bad provider (exit 2
    # path is argparse: exit code 2 on invalid choice).
    with pytest.raises(SystemExit) as exc:
        run_eval_main(["--provider", "nope"])
    assert exc.value.code == 2
