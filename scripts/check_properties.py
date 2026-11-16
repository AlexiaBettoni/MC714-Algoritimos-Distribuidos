#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path


def rank(node):
    return int(re.search(r"(\d+)$", node).group(1))


def load_events(path):
    events = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and "event" in event:
            events.append(event)
    return sorted(events, key=lambda e: e.get("ts", 0))


def check_run(run_dir, tol):
    meta = json.loads((run_dir / "metadata.json").read_text())
    events = load_events(run_dir / "raw.jsonl")
    n, victim, kill_ts = meta["nodes"], meta.get("victim"), meta.get("kill_ts")
    T, D = meta["timeout_s"], meta["heartbeat_interval_s"]
    election_timeout = max(T, 3 * D)
    lossless = meta["loss_rate"] == 0
    alive = [f"node{i}" for i in range(1, n + 1) if f"node{i}" != victim]
    expected = max(alive, key=rank)  # Bully: highest ID among the live nodes

    suspected = {a: set() for a in alive}
    first_detect, view, adopted_at = {}, {}, {}
    elected_after_kill = set()
    false_suspicions = 0
    for e in events:
        node, ts, kind = e.get("node"), e.get("ts", 0), e["event"]
        if node not in alive:
            continue
        if kind == "suspect":
            peer = e["peer"]
            suspected[node].add(peer)
            if peer == victim and kill_ts is not None and ts >= kill_ts:
                first_detect.setdefault(node, ts - kill_ts)
            else:
                false_suspicions += 1
        elif kind == "restore":
            suspected[node].discard(e["peer"])
        elif kind in ("coordinator_elected", "coordinator_changed"):
            view[node] = e["coordinator"]
            if kill_ts is not None and ts >= kill_ts:
                if e["coordinator"] == expected:
                    adopted_at.setdefault(node, ts - kill_ts)
                if kind == "coordinator_elected":
                    elected_after_kill.add(node)

    checks = []

    def add(name, ok, detail, strict):
        checks.append({"name": name, "ok": bool(ok), "strict": strict, "detail": detail})

    add("no false suspicions", false_suspicions == 0,
        f"{false_suspicions} unwarranted suspicion events", lossless)

    if victim:
        missing = [a for a in alive if victim not in suspected[a]]
        add("completeness", not missing,
            f"all {len(alive)} live nodes suspect {victim}" if not missing
            else f"no permanent suspicion of {victim} at: {missing}", True)
        # A node that already suspected the victim before the crash has latency 0.
        latencies = [first_detect.get(a, 0.0) for a in alive if victim in suspected[a]]
        bound = T + D / 4 + tol
        worst = max(latencies) if latencies else None
        add("bounded detection time", worst is not None and worst <= bound,
            "no detections" if worst is None else f"max {worst:.3f}s, limit {bound:.3f}s", True)

    wrong = {a: view.get(a) for a in alive if view.get(a) != expected}
    add("leader agreement", not wrong,
        f"all live nodes end with leader {expected}" if not wrong
        else f"expected {expected}, but final views are {wrong}", lossless)

    if victim:
        add("single leader announced", elected_after_kill == {expected},
            f"nodes that declared themselves leader after the crash: {sorted(elected_after_kill)}",
            lossless)
        conv_bound = T + D / 4 + 2 * election_timeout + tol
        done = all(a in adopted_at for a in alive)
        worst_conv = max(adopted_at.values()) if done else None
        add("election convergence", done and worst_conv <= conv_bound,
            "not all nodes adopted the new leader" if not done
            else f"max {worst_conv:.3f}s, limit {conv_bound:.3f}s", lossless)

    return {"run_id": meta["run_id"], "scenario": meta["scenario"], "nodes": n,
            "loss_rate": meta["loss_rate"], "seed": meta["seed"], "checks": checks}


def find_runs(root):
    if (root / "metadata.json").exists() and (root / "raw.jsonl").exists():
        return [root]
    return [p for p in sorted(root.rglob("run-*"))
            if p.is_dir() and (p / "metadata.json").exists() and (p / "raw.jsonl").exists()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", nargs="?", default="results/experiments")
    parser.add_argument("--tol", type=float, default=1.0,
                        help="tolerance in seconds added to the time bounds; it absorbs the "
                             "latency of 'docker compose kill' after kill_ts (default: 1.0)")
    args = parser.parse_args()
    root = Path(args.results)
    runs = find_runs(root)
    if not runs:
        parser.error(f"no completed runs found under {root}")

    results, strict_failures = [], 0
    for run_dir in runs:
        result = check_run(run_dir, args.tol)
        results.append(result)
        print(f"{result['run_id']}")
        for c in result["checks"]:
            tag = "PASS" if c["ok"] else ("FAIL" if c["strict"] else "INFO")
            strict_failures += (not c["ok"]) and c["strict"]
            print(f"  [{tag}] {c['name']}: {c['detail']}")
    out = (root if root.is_dir() else root.parent) / "checks.json"
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\n{len(results)} runs checked, {strict_failures} strict failures. Details: {out}")
    sys.exit(1 if strict_failures else 0)


if __name__ == "__main__":
    main()
