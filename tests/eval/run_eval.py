"""Eval runner for IMSF Phase 1 (design §8, Step 4).

For each fixture (image + ground-truth JSON) in --fixtures:
upload the image through the real API (POST /api/v2/receipts, service
token from IMSF_SERVICE_TOKEN), process the queued job, poll GET
detail until a terminal status (completed / failed / needs_review),
then compare the predicted lines against ground truth.

Worker modes (--worker):
- in-process (default): the runner itself drains the job from Redis
  and calls worker.main.process_job in-process — the same pattern the
  Step 2 pytest uses. With --qwen mock, Qwen parsing is replaced by
  the deterministic tests.eval.mock_qwen parser, so the run needs NO
  GPU. No live worker may be running in this mode (preflight check).
- external: a live worker owns the queue; the runner only polls.
  Use this for the real Qwen/Baidu gate once the GPU is healthy.

Exit code: 0 = gate PASS (accuracy > --gate), 1 = gate FAIL,
2 = run error (bad flags, missing token, API unreachable, ...).
Reports (JSON + Markdown) go to --out (default tests/eval/last-run).

Usage (from the repo root, env sourced from /home/ubuntu/imsf.env):
  .venv/bin/python -m tests.eval.run_eval \
      --fixtures tests/fixtures --provider mock --out tests/eval/last-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.eval.compare import (GATE_THRESHOLD, TERMINAL_STATUSES,
                                compare_receipt, compute_accuracy)

SHANGHAI = ZoneInfo("Asia/Shanghai")
TERMINAL = set(TERMINAL_STATUSES)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


class EvalError(RuntimeError):
    """Run error (exit 2): setup / API / fixture problem, not a gate FAIL."""


# --- API client -----------------------------------------------------------

class HttpEvalClient:
    """Real API over HTTP (service token, design §5)."""

    def __init__(self, base_url: str, token: str):
        if not token:
            raise EvalError(
                "IMSF_SERVICE_TOKEN is not set (env). The eval runner "
                "authenticates with the service token only; it is never "
                "printed. Source /home/ubuntu/imsf.env (which holds "
                "it) or take it from the live uvicorn process env.")
        self._client = httpx.Client(base_url=base_url.rstrip("/"),
                                    timeout=30.0)
        self._headers = {"Authorization": f"Bearer {token}"}

    def create_household(self, name: str) -> str:
        resp = self._client.post("/api/v2/households", json={"name": name},
                                 headers=self._headers)
        if resp.status_code != 201:
            raise EvalError(f"create household failed: "
                            f"{resp.status_code} {resp.text[:300]}")
        return resp.json()["id"]

    def upload_receipt(self, household_id: str, image_path: Path) -> str:
        with open(image_path, "rb") as fh:
            content = fh.read()
        mime = {".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp"}[image_path.suffix.lower()]
        resp = self._client.post(
            "/api/v2/receipts",
            data={"household_id": household_id},
            files={"image": (image_path.name, content, mime)},
            headers=self._headers)
        if resp.status_code != 202:
            raise EvalError(f"upload {image_path.name} failed: "
                            f"{resp.status_code} {resp.text[:300]}")
        return resp.json()["id"]

    def get_receipt(self, receipt_id: str) -> dict:
        resp = self._client.get(f"/api/v2/receipts/{receipt_id}",
                                headers=self._headers)
        if resp.status_code != 200:
            raise EvalError(f"GET receipt {receipt_id} failed: "
                            f"{resp.status_code} {resp.text[:300]}")
        return resp.json()

    def close(self):
        self._client.close()


# --- worker drain ---------------------------------------------------------

def _no_live_worker() -> None:
    """Preflight for --worker in-process: a live worker would steal
    queued jobs and corrupt the run. Pattern built by concatenation so
    this shell's own cmdline never literally contains it."""
    pattern = "python -m work" "er.main"
    proc = subprocess.run(["pgrep", "-f", pattern],
                          capture_output=True, text=True)
    if proc.returncode == 0:
        raise EvalError(
            "a live worker process is running (pgrep matched) — stop it "
            "before an in-process eval run, or use --worker external. "
            f"PIDs: {proc.stdout.strip()}")


def make_in_process_drain(provider: str, qwen_mode: str):
    """Drain one job from Redis and process it in-process (Step 2 test
    pattern). With qwen_mode=mock the Qwen parse is the deterministic
    mock parser — no GPU needed. Returns drain(receipt_id) -> status."""
    _no_live_worker()
    import worker.main as worker_main
    from app.db import get_redis

    if qwen_mode == "mock":
        from tests.eval.mock_qwen import mock_parse_receipt_text
        worker_main.parse_receipt_text = mock_parse_receipt_text
    elif qwen_mode != "real":
        raise EvalError(f"unknown --qwen mode: {qwen_mode!r} "
                        "(expected mock | real)")
    os.environ["OCR_PROVIDER"] = provider

    def drain(receipt_id: str, timeout: float = 60.0) -> str:
        redis_client = get_redis()
        deadline = time.time() + timeout
        job = None
        while time.time() < deadline:
            raw = redis_client.lpop("imsf:receipt-jobs")
            if raw:
                candidate = json.loads(raw)
                if candidate.get("receipt_id") == receipt_id:
                    job = candidate
                    break
                # Stale job from another run: put it back and keep waiting.
                redis_client.lpush("imsf:receipt-jobs", raw)
            time.sleep(0.5)
        if job is None:
            return "no-job"
        return worker_main.process_job(job)

    return drain


# --- fixtures -------------------------------------------------------------

def load_fixtures(fixtures_dir: Path) -> list[dict]:
    """Every *.json in the dir must have a same-stem image next to it."""
    fixtures = []
    for json_path in sorted(fixtures_dir.glob("*.json")):
        truth = json.loads(json_path.read_text(encoding="utf-8"))
        image = None
        for ext in IMAGE_EXTS:
            candidate = json_path.with_suffix(ext)
            if candidate.exists():
                image = candidate
                break
        if image is None:
            raise EvalError(f"fixture {json_path.name} has no image "
                            f"(looked for {json_path.stem}.png/.jpg/.webp)")
        fixtures.append({"fixture_id": json_path.stem,
                         "json_path": json_path, "image_path": image,
                         "truth": truth})
    if not fixtures:
        raise EvalError(f"no fixtures (*.json) in {fixtures_dir}")
    return fixtures


# --- report ---------------------------------------------------------------

def _git_info() -> dict:
    def run(*args):
        try:
            return subprocess.run(
                ["git", *args], cwd=str(REPO_ROOT), capture_output=True,
                text=True, timeout=15).stdout.strip() or None
        except Exception:
            return None
    return {"commit": run("rev-parse", "HEAD"),
            "branch": run("branch", "--show-current")}


def build_report(results: list[dict], metadata: dict) -> dict:
    totals = compute_accuracy(results)
    worst = sorted(results, key=lambda r: (r["accuracy"],
                                           r["correct_lines"]))
    return {"metadata": metadata, "totals": totals,
            "per_receipt": results,
            "worst_receipts": [r["fixture_id"] for r in worst[:3]]}


def render_markdown(report: dict) -> str:
    meta, totals = report["metadata"], report["totals"]
    lines = [
        "# IMSF Phase 1 — eval report",
        "",
        f"- **Date (Asia/Shanghai):** {meta['date']}",
        f"- **Provider:** {meta['provider']} (OCR) / {meta['qwen_mode']} "
        f"(Qwen) / worker {meta['worker_mode']}",
        f"- **Commit:** {meta['git']['commit']} "
        f"(branch {meta['git']['branch']})",
        f"- **Receipts evaluated:** {totals['receipts_evaluated']} "
        f"({meta['receipts_note']})",
        f"- **Accuracy:** {totals['correct_lines']}/"
        f"{totals['truth_lines']} = {totals['accuracy']:.1%}",
        f"- **Gate (> {totals['gate']:.0%}):** "
        f"{'PASS' if totals['passed'] else 'FAIL'}",
        "",
        "## Per-receipt accuracy",
        "",
        "| Receipt | Status | Truth | Predicted | Correct | Accuracy |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["per_receipt"]:
        lines.append(
            f"| {r['fixture_id']} | {r['status']} | {r['truth_lines']} | "
            f"{r['predicted_lines']} | {r['correct_lines']} | "
            f"{r['accuracy']:.1%} |")
    lines += [
        "",
        "## Error taxonomy (counts)",
        "",
        "| Bucket | Count | Meaning |",
        "|---|---|---|",
    ]
    meanings = {
        "ocr_char": "quantity/unit/price match but raw_name differs",
        "mapping": "4 fields right but canonical mapping wrong/missing",
        "quantity": "raw_name matches but quantity differs",
        "unit": "raw_name matches but unit differs",
        "price": "raw_name matches but price differs",
        "total_mismatch": "receipt needs_review/failed, line sum > 2% off total",
        "missing_line": "ground-truth line with no predicted counterpart",
        "extra_line": "predicted line with no ground-truth counterpart",
    }
    for bucket, count in totals["taxonomy"].items():
        lines.append(f"| {bucket} | {count} | {meanings[bucket]} |")
    lines += [
        "",
        f"**Worst receipts:** "
        f"{', '.join(report['worst_receipts']) or '—'}",
        "",
        "## Notes",
        "",
        "- " + meta["receipts_note"],
        "- Mock-Qwen runs measure the harness + mapping/reconciliation "
        "pipeline, not Qwen's real accuracy: the mock OCR text is canned "
        "for one receipt, so fixtures with different content cannot "
        "match it. The real > 90% gate needs the real Qwen/Baidu path "
        "on real receipts.",
        "- A mapping-wrong line still counts CORRECT for accuracy "
        "(design §8: correctness = the 4 fields only); mapping errors "
        "are reported separately in the taxonomy.",
        "",
    ]
    return "\n".join(lines)


# --- main run -------------------------------------------------------------

def run_evaluation(*, fixtures_dir: Path, provider: str, qwen_mode: str,
                   worker_mode: str, base_url: str, out_dir: Path,
                   timeout: float, gate: float, client=None,
                   drain=None) -> dict:
    """Run the eval; returns the report dict. Raises EvalError on
    run errors. ``client`` / ``drain`` are injectable for tests."""
    fixtures = load_fixtures(fixtures_dir)
    own_client = client is None
    if own_client:
        client = HttpEvalClient(
            base_url, os.environ.get("IMSF_SERVICE_TOKEN", ""))
    if drain is None:
        if worker_mode == "in-process":
            drain = make_in_process_drain(provider, qwen_mode)
        elif worker_mode == "external":
            drain = lambda receipt_id, timeout=60.0: "external"  # noqa: E731
        else:
            raise EvalError(f"unknown --worker mode: {worker_mode!r} "
                            "(expected in-process | external)")
    try:
        household_id = client.create_household(
            f"Eval {datetime.now(SHANGHAI).strftime('%Y-%m-%d %H:%M')}")
        results = []
        for fx in fixtures:
            receipt_id = client.upload_receipt(household_id,
                                              fx["image_path"])
            drain_status = drain(receipt_id)
            detail = _poll_until_terminal(client, receipt_id, timeout)
            results.append(compare_receipt(
                fx["fixture_id"], fx["truth"],
                detail.get("lines") or [],
                detail.get("status") or "timeout",
                detail.get("error_message"),
                detail.get("total_amount")))
            r = results[-1]
            print(f"[{r['fixture_id']}] status={r['status']} "
                  f"(drain={drain_status}) "
                  f"correct={r['correct_lines']}/{r['truth_lines']} "
                  f"accuracy={r['accuracy']:.1%}", flush=True)
    finally:
        if own_client:
            client.close()

    metadata = {
        "date": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
        "provider": provider,
        "qwen_mode": qwen_mode,
        "worker_mode": worker_mode,
        "base_url": base_url,
        "gate": gate,
        "git": _git_info(),
        "receipts_note": (
            f"{len(fixtures)} SYNTHETIC fixtures only — no real receipts "
            "yet. The full 50-receipt set needs real supermarket "
            "receipts (Lam's step)."),
    }
    report = build_report(results, metadata)
    # Gate override: --gate replaces the default 0.90 in the verdict.
    report["totals"]["gate"] = gate
    report["totals"]["passed"] = (
        report["totals"]["accuracy"] > gate)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(report),
                                       encoding="utf-8")
    totals = report["totals"]
    print(f"Accuracy: {totals['correct_lines']}/{totals['truth_lines']} "
          f"= {totals['accuracy']:.1%}  gate > {gate:.0%}: "
          f"{'PASS' if totals['passed'] else 'FAIL'}")
    print(f"Report: {out_dir / 'report.json'}")
    print(f"Summary: {out_dir / 'report.md'}")
    return report


def _poll_until_terminal(client, receipt_id: str,
                         timeout: float) -> dict:
    deadline = time.time() + timeout
    last: dict = {"status": "timeout", "lines": [], "error_message": None,
                  "total_amount": None}
    while time.time() < deadline:
        last = client.get_receipt(receipt_id)
        if last.get("status") in TERMINAL:
            return last
        time.sleep(2)
    return last


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="IMSF Phase 1 eval runner (design §8).")
    parser.add_argument("--fixtures", default="tests/fixtures")
    parser.add_argument("--provider", default="mock",
                        choices=["mock", "baidu", "qwen-vl"])
    parser.add_argument("--qwen", default=None, choices=["mock", "real"],
                        help="Qwen parse mode (default: mock when "
                        "--provider mock, else real)")
    parser.add_argument("--worker", default="in-process",
                        choices=["in-process", "external"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--out", default="tests/eval/last-run")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="seconds to poll each receipt to terminal")
    parser.add_argument("--gate", type=float, default=float(GATE_THRESHOLD))
    args = parser.parse_args(argv)
    qwen_mode = args.qwen or ("mock" if args.provider == "mock" else "real")
    try:
        report = run_evaluation(
            fixtures_dir=REPO_ROOT / args.fixtures
            if not Path(args.fixtures).is_absolute()
            else Path(args.fixtures),
            provider=args.provider, qwen_mode=qwen_mode,
            worker_mode=args.worker, base_url=args.base_url,
            out_dir=REPO_ROOT / args.out
            if not Path(args.out).is_absolute() else Path(args.out),
            timeout=args.timeout, gate=args.gate)
    except EvalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0 if report["totals"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
