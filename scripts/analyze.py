#!/usr/bin/env python3
"""Summarize experiment JSONL logs and write per-run and grouped CSV/JSON."""

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

MESSAGE_TYPES = ("HEARTBEAT", "ELECTION", "OK", "COORDINATOR")


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def load_events(path):
    events = []
    with path.open() as log_file:
        for line_number, line in enumerate(log_file, start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # Docker may add a non-JSON diagnostic line.
            if isinstance(event, dict) and "event" in event:
                events.append(event)
    return events


def summarize(run_dir):
    metadata_path = run_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    events = load_events(run_dir / "raw.jsonl")
    victim = metadata.get("victim")
    kill_ts = metadata.get("kill_ts")
    start_ts = metadata["start_ts"]
    dead_at = kill_ts if kill_ts is not None else start_ts
    participants = [f"node{i}" for i in range(1, metadata["nodes"] + 1)
                    if f"node{i}" != victim]

    detections = {}
    target_coordinator = (f"node{metadata['nodes'] - 1}" if victim
                          else f"node{metadata['nodes']}")
    convergence = {}
    message_counts = {kind: 0 for kind in MESSAGE_TYPES}
    false_suspicions = 0
    for event in events:
        timestamp = event.get("ts", 0)
        if event.get("event") == "suspect":
            peer = event.get("peer")
            if victim and peer == victim and timestamp >= dead_at:
                detections.setdefault(event.get("node"), timestamp - kill_ts)
            elif peer != victim:
                false_suspicions += 1

        if event.get("event") == "message_sent" and timestamp >= dead_at:
            kind = event.get("message", {}).get("type")
            if kind in message_counts:
                message_counts[kind] += 1

        if timestamp >= dead_at:
            adopted = None
            if event.get("event") == "coordinator_changed":
                adopted = event.get("coordinator")
            elif event.get("event") == "coordinator_elected":
                adopted = event.get("coordinator")
            if adopted == target_coordinator and event.get("node") in participants:
                convergence.setdefault(event["node"], timestamp - dead_at)

    expected = set(participants)
    return {
        **metadata,
        "raw_log": str((run_dir / "raw.jsonl").resolve()),
        "event_count": len(events),
        "detection_count": len(detections),
        "detection_latency_max_s": max(detections.values()) if detections else None,
        "detection_latency_mean_s": statistics.mean(detections.values()) if detections else None,
        "coordinator_convergence_count": len(convergence),
        "coordinator_convergence_s": (max(convergence.values())
                                      if expected and expected.issubset(convergence) else None),
        "false_suspicions": false_suspicions,
        "heartbeat_messages": message_counts["HEARTBEAT"],
        "election_messages": sum(message_counts[k] for k in ("ELECTION", "OK", "COORDINATOR")),
        "election_requests": message_counts["ELECTION"],
        "ok_messages": message_counts["OK"],
        "coordinator_announcements": message_counts["COORDINATOR"],
    }


def stats(values):
    values = [value for value in values if value is not None]
    if not values:
        return {"n": 0, "mean": None, "stdev": None, "p50": None, "p95": None}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="?", default="results/experiments",
                        help="experiment output root (default: results/experiments)")
    args = parser.parse_args()
    root = Path(args.results)
    runs = [summarize(path) for path in sorted(root.glob("run-*/"))
            if (path / "metadata.json").exists() and (path / "raw.jsonl").exists()]
    if not runs:
        parser.error(f"no completed runs found under {root}")

    columns = ["run_id", "scenario", "nodes", "loss_rate", "seed", "victim",
               "detection_count", "detection_latency_max_s", "detection_latency_mean_s",
               "coordinator_convergence_count", "coordinator_convergence_s",
               "false_suspicions", "election_messages", "election_requests",
               "ok_messages", "coordinator_announcements", "heartbeat_messages", "event_count"]
    with (root / "metrics.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(runs)

    grouped = defaultdict(list)
    for run in runs:
        key = (run["scenario"], run["nodes"], run["loss_rate"])
        grouped[key].append(run)
    aggregates = []
    for (scenario, nodes, loss_rate), values in sorted(grouped.items()):
        aggregates.append({
            "scenario": scenario, "nodes": nodes, "loss_rate": loss_rate,
            "runs": len(values),
            "detection_latency_max_s": stats([r["detection_latency_max_s"] for r in values]),
            "coordinator_convergence_s": stats([r["coordinator_convergence_s"] for r in values]),
            "election_messages": stats([r["election_messages"] for r in values]),
            "false_suspicions": stats([r["false_suspicions"] for r in values]),
        })
    (root / "summary.json").write_text(json.dumps(aggregates, indent=2) + "\n")
    print(f"Analyzed {len(runs)} runs")
    print(f"Per-run metrics: {root / 'metrics.csv'}")
    print(f"Grouped summary: {root / 'summary.json'}")


if __name__ == "__main__":
    main()
