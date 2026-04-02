from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from deep_research.cli import run
from deep_research.state import Configuration

ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "test_artifacts"
RUNS_DIR = ARTIFACTS_DIR / "runs"
SUMMARY_PATH = ARTIFACTS_DIR / "summary.json"
SAMPLE_INTERVAL_SECONDS = 1.0


@dataclass
class ResourceSample:
    timestamp: str
    cpu_percent_total: float
    rss_mb: float
    vms_mb: float
    num_threads: int
    read_bytes: int
    write_bytes: int
    net_bytes_sent: int
    net_bytes_recv: int


def sanitize_name(value: str) -> str:
    sanitized = re.sub(r"[^\w\s-]", "", value).strip()
    sanitized = re.sub(r"\s+", "_", sanitized)
    return sanitized[:60]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sample_process_tree(root_proc: psutil.Process) -> tuple[float, float, float, int, int, int]:
    processes = [root_proc]
    try:
        processes.extend(root_proc.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    cpu_percent_total = 0.0
    rss_bytes = 0
    vms_bytes = 0
    num_threads = 0
    read_bytes = 0
    write_bytes = 0

    for proc in processes:
        try:
            cpu_percent_total += proc.cpu_percent(interval=None)
            mem = proc.memory_info()
            rss_bytes += mem.rss
            vms_bytes += mem.vms
            num_threads += proc.num_threads()
            io_method = getattr(proc, "io_counters", None)
            if callable(io_method):
                io_counters = io_method()
                read_bytes += getattr(io_counters, "read_bytes", 0)
                write_bytes += getattr(io_counters, "write_bytes", 0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return (
        cpu_percent_total,
        rss_bytes / (1024 * 1024),
        vms_bytes / (1024 * 1024),
        num_threads,
        read_bytes,
        write_bytes,
    )


def monitor_process(pid: int, stop_event: threading.Event, samples: list[ResourceSample]) -> None:
    process = psutil.Process(pid)
    baseline_net = psutil.net_io_counters()
    process.cpu_percent(interval=None)

    while not stop_event.is_set():
        try:
            cpu_percent_total, rss_mb, vms_mb, num_threads, read_bytes, write_bytes = sample_process_tree(
                process
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break

        net = psutil.net_io_counters()
        samples.append(
            ResourceSample(
                timestamp=iso_now(),
                cpu_percent_total=round(cpu_percent_total, 2),
                rss_mb=round(rss_mb, 2),
                vms_mb=round(vms_mb, 2),
                num_threads=num_threads,
                read_bytes=read_bytes,
                write_bytes=write_bytes,
                net_bytes_sent=max(0, net.bytes_sent - baseline_net.bytes_sent),
                net_bytes_recv=max(0, net.bytes_recv - baseline_net.bytes_recv),
            )
        )
        time.sleep(SAMPLE_INTERVAL_SECONDS)


def summarize_samples(samples: list[ResourceSample]) -> dict[str, Any]:
    if not samples:
        return {
            "sample_count": 0,
            "peak_cpu_percent_total": 0.0,
            "avg_cpu_percent_total": 0.0,
            "peak_rss_mb": 0.0,
            "avg_rss_mb": 0.0,
            "peak_vms_mb": 0.0,
            "peak_threads": 0,
            "final_read_bytes": 0,
            "final_write_bytes": 0,
            "final_net_bytes_sent": 0,
            "final_net_bytes_recv": 0,
        }

    return {
        "sample_count": len(samples),
        "peak_cpu_percent_total": round(max(s.cpu_percent_total for s in samples), 2),
        "avg_cpu_percent_total": round(sum(s.cpu_percent_total for s in samples) / len(samples), 2),
        "peak_rss_mb": round(max(s.rss_mb for s in samples), 2),
        "avg_rss_mb": round(sum(s.rss_mb for s in samples) / len(samples), 2),
        "peak_vms_mb": round(max(s.vms_mb for s in samples), 2),
        "peak_threads": max(s.num_threads for s in samples),
        "final_read_bytes": samples[-1].read_bytes,
        "final_write_bytes": samples[-1].write_bytes,
        "final_net_bytes_sent": samples[-1].net_bytes_sent,
        "final_net_bytes_recv": samples[-1].net_bytes_recv,
    }


def run_topic(index: int, topic: str, lang: str = "ja", max_loops: int = 1) -> dict[str, Any]:
    topic_slug = sanitize_name(topic)
    run_dir = RUNS_DIR / f"{index:02d}_{topic_slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    predicted_report_path = str((ROOT / f"report_{topic_slug}.md").resolve())
    command = [sys.executable, "-m", "deep_research", topic, "--lang", lang, "--max-loops", str(max_loops)]
    ctx = Configuration(language=lang, max_loops=max_loops)

    started_at = iso_now()
    started_monotonic = time.monotonic()
    stop_event = threading.Event()
    samples: list[ResourceSample] = []
    monitor_thread = threading.Thread(
        target=monitor_process,
        args=(os.getpid(), stop_event, samples),
        daemon=True,
    )
    monitor_thread.start()

    return_code = 0
    report_path_from_run: str | None = None
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w",
        encoding="utf-8",
    ) as stderr_file, redirect_stdout(stdout_file), redirect_stderr(stderr_file):
        try:
            report_path_from_run = run(topic, ctx)
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}", file=sys.stderr, flush=True)
            return_code = 1

    stop_event.set()
    monitor_thread.join(timeout=5)

    completed_at = iso_now()
    elapsed_seconds = round(time.monotonic() - started_monotonic, 2)
    resolved_report_path = report_path_from_run or predicted_report_path

    (run_dir / "samples.json").write_text(
        json.dumps([asdict(sample) for sample in samples], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = {
        "index": index,
        "topic": topic,
        "command": command,
        "started_at": started_at,
        "completed_at": completed_at,
        "elapsed_seconds": elapsed_seconds,
        "return_code": return_code,
        "report_path": resolved_report_path if Path(resolved_report_path).exists() else None,
        "run_dir": str(run_dir),
        "resource_summary": summarize_samples(samples),
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deep research with performance monitoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with a single topic:
  python test_runner.py "Impact of AI on healthcare in 2026"
  
  # Run with multiple topics:
  python test_runner.py "Topic 1" "Topic 2" "Topic 3"
  
  # Change language to English:
  python test_runner.py --lang en "Your research topic"
  
  # Control research depth (default: 1 follow-up search):
  python test_runner.py --max-loops 0 "Quick research topic"
  python test_runner.py --max-loops 3 "Deep research topic"
        """,
    )
    parser.add_argument(
        "topics",
        nargs="+",
        help="Research topic(s) to run (required, one or more)",
    )
    parser.add_argument(
        "--lang",
        choices=["ja", "en"],
        default="ja",
        help="Language for the report (default: ja)",
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=1,
        help="Max follow-up research iterations per subtopic (default: 1)",
    )
    args = parser.parse_args()

    topics = args.topics

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Running {len(topics)} topic(s) with language: {args.lang}, max-loops: {args.max_loops}")
    print(f"{'='*60}\n")

    all_results = []
    for index, topic in enumerate(topics, start=1):
        print(f"\n=== Running topic {index}/{len(topics)} ===", flush=True)
        print(topic, flush=True)
        result = run_topic(index, topic, args.lang, args.max_loops)
        all_results.append(result)
        print(f"Finished with code {result['return_code']} in {result['elapsed_seconds']}s", flush=True)
        if result["report_path"]:
            print(f"Report: {result['report_path']}", flush=True)

    SUMMARY_PATH.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failed = [result for result in all_results if result["return_code"] != 0]
    if failed:
        print(f"\n{len(failed)} run(s) failed. See test_artifacts for details.", flush=True)
        return 1

    print("\nAll runs completed successfully.", flush=True)
    print(f"Summary: {SUMMARY_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
