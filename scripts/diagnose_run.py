#!/usr/bin/env python3
"""Diagnose false suspicions in ONE run: startup skew, heartbeat gaps, send errors.

Usage: python scripts/diagnose_run.py results/experiments/<batch>/run-001-normal-n5-loss0-seed1
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run", help="run directory or raw.jsonl")
parser.add_argument("--top", type=int, default=6, help="how many suspicions to list")
args = parser.parse_args()
src = Path(args.run)
log_path = src / "raw.jsonl" if src.is_dir() else src

events = []
for line in log_path.read_text(errors="replace").splitlines():
    try:
        e = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(e, dict) and "event" in e:
        events.append(e)
events.sort(key=lambda e: e.get("ts", 0))

starts = {e["node"]: e["ts"] for e in events if e["event"] == "start"}
t0 = min(starts.values())
print("== Startup skew (s after first node started) ==")
for node, ts in sorted(starts.items(), key=lambda kv: kv[1]):
    print(f"  {node}: +{ts - t0:.2f}s")

# First send time of each heartbeat round (seq) per node -> gaps between rounds.
rounds = defaultdict(dict)
errors = defaultdict(list)
for e in events:
    if e["event"] == "message_sent" and e["message"].get("type") == "HEARTBEAT":
        rounds[e["node"]].setdefault(e["message"]["seq"], e["ts"])
    elif e["event"] == "message_send_error":
        errors[e["node"]].append((e["ts"] - t0, e.get("error", "")))

print("\n== Heartbeat rounds: largest gap between consecutive rounds (expected ~interval) ==")
for node in sorted(rounds):
    seqs = sorted(rounds[node])
    gaps = [(rounds[node][b] - rounds[node][a], rounds[node][a] - t0)
            for a, b in zip(seqs, seqs[1:])]
    if gaps:
        g, at = max(gaps)
        print(f"  {node}: {len(seqs)} rounds, max gap {g:.2f}s (starting at +{at:.2f}s)")

print("\n== Barrier: when each node finished resolving peers and sent its first heartbeat ==")
resolved = {e["node"]: e["ts"] for e in events if e["event"] == "peers_resolved"}
for node in sorted(starts, key=lambda n: starts[n]):
    first_hb = min(rounds[node].values()) - t0 if rounds.get(node) else None
    r = f"+{resolved[node] - t0:.2f}s" if node in resolved else "n/a (old node.py?)"
    f = f"+{first_hb:.2f}s" if first_hb is not None else "none"
    print(f"  {node}: peers_resolved {r}, first heartbeat {f}")

print("\n== Send errors (e.g. DNS failures) ==")
if not errors:
    print("  none")
for node in sorted(errors):
    first_t, first_msg = errors[node][0]
    print(f"  {node}: {len(errors[node])} errors, first at +{first_t:.2f}s: {first_msg}")

print(f"\n== First {args.top} suspicions ==")
suspects = [e for e in events if e["event"] == "suspect"]
for e in suspects[:args.top]:
    print(f"  +{e['ts'] - t0:.2f}s {e['node']} suspects {e['peer']} (silence {e['silence']}s)")
print(f"  total suspicion events: {len(suspects)}")