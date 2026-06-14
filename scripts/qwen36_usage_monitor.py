#!/usr/bin/env python3
"""Collect and report Qwen3.6 GPU/cache/token usage.

Version: 20260609_usage_monitor_v1
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


VERSION = "20260609_usage_monitor_v1"
DEFAULT_METRICS_URL = "http://127.0.0.1:8000/metrics"
DEFAULT_LOG = "/base/home/lizhzh/log/qwen36_usage_samples.jsonl"


@dataclass
class Series:
    name: str
    values: List[Tuple[float, Optional[float]]]
    color: str
    unit: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_gpu_ids(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def run_nvidia_smi(gpu_ids: List[str]) -> List[Dict[str, object]]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    if gpu_ids:
        cmd.insert(1, f"--id={','.join(gpu_ids)}")
    output = subprocess.check_output(cmd, text=True, timeout=10)
    rows: List[Dict[str, object]] = []
    for row in csv.reader(output.splitlines()):
        if len(row) < 4:
            continue
        index, util, mem_used, mem_total = [cell.strip() for cell in row[:4]]
        total = float(mem_total) if mem_total else 0.0
        used = float(mem_used) if mem_used else 0.0
        rows.append(
            {
                "index": index,
                "gpu_util_pct": float(util) if util else None,
                "memory_used_mib": used,
                "memory_total_mib": total,
                "memory_used_pct": (used / total * 100.0) if total else None,
            }
        )
    return rows


METRIC_LINE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\\{[^}]*\\})?\\s+([-+0-9.eE]+)$")


def fetch_metrics(metrics_url: str) -> Dict[str, float]:
    try:
        with urllib.request.urlopen(metrics_url, timeout=5) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return {}

    totals: Dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = METRIC_LINE_RE.match(line.strip())
        if not match:
            continue
        name, raw_value = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            continue
        totals[name] = totals.get(name, 0.0) + value
    return totals


def pick_metric(metrics: Dict[str, float], candidates: Iterable[str]) -> Optional[float]:
    for name in candidates:
        if name in metrics:
            return metrics[name]
    return None


def collect_sample(gpu_ids: List[str], metrics_url: str) -> Dict[str, object]:
    metrics = fetch_metrics(metrics_url)
    return {
        "version": VERSION,
        "ts": time.time(),
        "ts_iso": now_iso(),
        "gpus": run_nvidia_smi(gpu_ids),
        "metrics_url": metrics_url,
        "cache_usage_pct": pick_metric(
            metrics,
            (
                "vllm:gpu_cache_usage_perc",
                "vllm_gpu_cache_usage_perc",
                "sglang:token_usage",
                "sglang_token_usage",
            ),
        ),
        "requests_running": pick_metric(
            metrics,
            (
                "vllm:num_requests_running",
                "vllm_num_requests_running",
                "sglang:num_running_reqs",
                "sglang_num_running_reqs",
            ),
        ),
        "requests_waiting": pick_metric(
            metrics,
            (
                "vllm:num_requests_waiting",
                "vllm_num_requests_waiting",
                "sglang:num_queue_reqs",
                "sglang_num_queue_reqs",
            ),
        ),
        "prompt_tokens_total": pick_metric(
            metrics,
            (
                "vllm:prompt_tokens_total",
                "vllm_prompt_tokens_total",
                "sglang:prompt_tokens_total",
                "sglang_prompt_tokens_total",
            ),
        ),
        "generation_tokens_total": pick_metric(
            metrics,
            (
                "vllm:generation_tokens_total",
                "vllm_generation_tokens_total",
                "sglang:generation_tokens_total",
                "sglang_generation_tokens_total",
            ),
        ),
    }


def append_jsonl(path: Path, sample: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")


def load_samples(path: Path, since_ts: float) -> List[Dict[str, object]]:
    samples: List[Dict[str, object]] = []
    if not path.exists():
        return samples
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = float(sample.get("ts") or 0)
            if ts >= since_ts:
                samples.append(sample)
    samples.sort(key=lambda item: float(item.get("ts") or 0))
    return samples


def average(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = [value for value in values if value is not None and math.isfinite(value)]
    if not nums:
        return None
    return sum(nums) / len(nums)


def max_value(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = [value for value in values if value is not None and math.isfinite(value)]
    return max(nums) if nums else None


def token_delta(samples: List[Dict[str, object]]) -> Optional[float]:
    totals: List[float] = []
    for sample in samples:
        prompt = sample.get("prompt_tokens_total")
        generation = sample.get("generation_tokens_total")
        if isinstance(prompt, (int, float)) and isinstance(generation, (int, float)):
            totals.append(float(prompt) + float(generation))
    if len(totals) < 2:
        return None
    return max(0.0, totals[-1] - totals[0])


def build_series(samples: List[Dict[str, object]]) -> List[Series]:
    def by_gpu(field: str, gpu_index: str) -> List[Tuple[float, Optional[float]]]:
        values: List[Tuple[float, Optional[float]]] = []
        for sample in samples:
            ts = float(sample.get("ts") or 0)
            found: Optional[float] = None
            for gpu in sample.get("gpus") or []:
                if isinstance(gpu, dict) and str(gpu.get("index")) == gpu_index:
                    raw = gpu.get(field)
                    found = float(raw) if isinstance(raw, (int, float)) else None
            values.append((ts, found))
        return values

    gpu_indexes = sorted(
        {
            str(gpu.get("index"))
            for sample in samples
            for gpu in (sample.get("gpus") or [])
            if isinstance(gpu, dict) and gpu.get("index") is not None
        }
    )
    palette = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]
    series: List[Series] = []
    for idx, gpu_index in enumerate(gpu_indexes):
        series.append(Series(f"GPU {gpu_index} util", by_gpu("gpu_util_pct", gpu_index), palette[idx % len(palette)], "%"))
    series.append(
        Series(
            "KV/cache",
            [(float(sample.get("ts") or 0), sample.get("cache_usage_pct")) for sample in samples],
            "#111827",
            "%",
        )
    )
    return series


def svg_polyline(points: List[Tuple[float, Optional[float]]], min_ts: float, max_ts: float, color: str) -> str:
    width, height = 1040, 420
    left, top, plot_w, plot_h = 70, 42, width - 110, height - 105
    coords: List[str] = []
    span = max(1.0, max_ts - min_ts)
    for ts, value in points:
        if value is None or not math.isfinite(value):
            continue
        x = left + (ts - min_ts) / span * plot_w
        y = top + (100.0 - max(0.0, min(100.0, value))) / 100.0 * plot_h
        coords.append(f"{x:.1f},{y:.1f}")
    if len(coords) < 2:
        return ""
    return f'<polyline fill="none" stroke="{color}" stroke-width="2.4" points="{" ".join(coords)}" />'


def write_svg(path: Path, samples: List[Dict[str, object]], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1040, 420
    min_ts = float(samples[0].get("ts") or time.time()) if samples else time.time()
    max_ts = float(samples[-1].get("ts") or min_ts) if samples else min_ts
    series = build_series(samples)
    lines = [svg_polyline(item.values, min_ts, max_ts, item.color) for item in series]
    legend = []
    for offset, item in enumerate(series):
        x = 75 + offset * 155
        legend.append(f'<rect x="{x}" y="365" width="12" height="12" fill="{item.color}" />')
        legend.append(f'<text x="{x + 18}" y="376" font-size="13">{escape_xml(item.name)}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff" />
  <text x="70" y="26" font-size="20" font-family="Arial, sans-serif" fill="#111827">{escape_xml(title)}</text>
  <line x1="70" y1="42" x2="70" y2="357" stroke="#9ca3af" />
  <line x1="70" y1="357" x2="1000" y2="357" stroke="#9ca3af" />
  <text x="28" y="51" font-size="12" fill="#6b7280">100%</text>
  <text x="36" y="203" font-size="12" fill="#6b7280">50%</text>
  <text x="44" y="361" font-size="12" fill="#6b7280">0%</text>
  <line x1="70" y1="199.5" x2="1000" y2="199.5" stroke="#e5e7eb" />
  {''.join(lines)}
  {''.join(legend)}
</svg>
'''
    path.write_text(svg, encoding="utf-8")


def escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_summary(path: Path, samples: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not samples:
        path.write_text("没有采样数据。\n", encoding="utf-8")
        return
    gpu_indexes = sorted(
        {
            str(gpu.get("index"))
            for sample in samples
            for gpu in (sample.get("gpus") or [])
            if isinstance(gpu, dict) and gpu.get("index") is not None
        }
    )
    rows = [
        f"版本: {VERSION}",
        f"采样数: {len(samples)}",
        f"范围: {samples[0].get('ts_iso')} 到 {samples[-1].get('ts_iso')}",
    ]
    for gpu_index in gpu_indexes:
        utils: List[Optional[float]] = []
        memory: List[Optional[float]] = []
        for sample in samples:
            for gpu in sample.get("gpus") or []:
                if isinstance(gpu, dict) and str(gpu.get("index")) == gpu_index:
                    utils.append(gpu.get("gpu_util_pct"))  # type: ignore[arg-type]
                    memory.append(gpu.get("memory_used_pct"))  # type: ignore[arg-type]
        rows.append(
            f"GPU {gpu_index}: 平均利用率 {fmt_pct(average(utils))}, 峰值利用率 {fmt_pct(max_value(utils))}, 平均显存 {fmt_pct(average(memory))}"
        )
    rows.append(f"KV/cache 平均占用: {fmt_pct(average(sample.get('cache_usage_pct') for sample in samples))}")
    rows.append(f"本时段 token 增量: {fmt_number(token_delta(samples))}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def fmt_pct(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:.1f}%"


def fmt_number(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:,.0f}"


def collect_loop(args: argparse.Namespace) -> int:
    gpu_ids = parse_gpu_ids(args.gpus)
    log_path = Path(args.output)
    while True:
        try:
            append_jsonl(log_path, collect_sample(gpu_ids, args.metrics_url))
        except Exception as exc:  # noqa: BLE001 - monitor must keep running.
            append_jsonl(
                log_path,
                {"version": VERSION, "ts": time.time(), "ts_iso": now_iso(), "error": str(exc)},
            )
        if args.once:
            return 0
        time.sleep(max(1, int(args.interval)))


def report(args: argparse.Namespace) -> int:
    since_ts = time.time() - int(args.minutes) * 60
    samples = load_samples(Path(args.input), since_ts)
    title = f"Qwen3.6 usage, last {args.minutes} minutes"
    write_svg(Path(args.svg), samples, title)
    write_summary(Path(args.summary), samples)
    print(args.svg)
    print(args.summary)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--output", default=os.environ.get("QWEN36_USAGE_LOG", DEFAULT_LOG))
    collect_parser.add_argument("--interval", type=int, default=int(os.environ.get("QWEN36_USAGE_INTERVAL", "10")))
    collect_parser.add_argument("--gpus", default=os.environ.get("QWEN36_GPUS", "6,7"))
    collect_parser.add_argument("--metrics-url", default=os.environ.get("QWEN36_METRICS_URL", DEFAULT_METRICS_URL))
    collect_parser.add_argument("--once", action="store_true")
    collect_parser.set_defaults(func=collect_loop)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--input", default=os.environ.get("QWEN36_USAGE_LOG", DEFAULT_LOG))
    report_parser.add_argument("--minutes", type=int, default=60)
    report_parser.add_argument("--svg", default="/base/home/lizhzh/log/qwen36_usage_latest.svg")
    report_parser.add_argument("--summary", default="/base/home/lizhzh/log/qwen36_usage_latest.txt")
    report_parser.set_defaults(func=report)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
