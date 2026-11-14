#!/usr/bin/env python3
"""Run repeatable normal, coordinator-crash, and packet-loss experiments."""

import argparse
import datetime as dt
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "mc714-bully-experiment:local"


def compose_text(nodes, interval, timeout, loss_rate, seed):
    ids = [f"node{i}" for i in range(1, nodes + 1)]
    lines = ["services:"]
    for node in ids:
        peers = ",".join(peer for peer in ids if peer != node)
        lines.extend([
            f"  {node}:",
            f"    image: {IMAGE}",
            "    environment:",
            f"      NODE_ID: {json.dumps(node)}",
            f"      PEERS: {json.dumps(peers)}",
            f"      HB_INTERVAL: {interval}",
            f"      HB_TIMEOUT: {timeout}",
            f"      LOSS_RATE: {loss_rate}",
            f"      SEED: {seed}",
        ])
    return "\n".join(lines) + "\n"


def compose(project, config, *args, check=True, capture=False):
    command = ["docker", "compose", "-p", project, "-f", str(config), *args]
    return subprocess.run(command, cwd=ROOT, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)


def parse_csv(value, converter, label):
    try:
        result = [converter(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid {label}: {error}") from error
    if not result:
        raise argparse.ArgumentTypeError(f"{label} must not be empty")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["all", "normal", "coordinator_crash"],
                        default="all")
    parser.add_argument("--nodes", default="5",
                        help="node counts (default: 5; pass 3,5,7 to add a size sweep)")
    parser.add_argument("--loss-rates", default="0,0.05,0.15",
                        help="loss levels for each selected scenario (default: 0,0.05,0.15)")
    parser.add_argument("--repetitions", type=int, default=2,
                        help="independent seeds per configuration (minimum default: 2)")
    parser.add_argument("--seed", type=int, default=1, help="first random seed")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--warmup", type=float, default=6.0,
                        help="seconds before injecting a crash")
    parser.add_argument("--observe", type=float, default=8.0,
                        help="seconds to observe a normal run")
    parser.add_argument("--results", default="results/experiments")
    parser.add_argument("--skip-build", action="store_true",
                        help="reuse the already-built experiment image")
    args = parser.parse_args()

    try:
        node_counts = parse_csv(args.nodes, int, "node counts")
        loss_rates = parse_csv(args.loss_rates, float, "loss rates")
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))
    if args.repetitions < 1 or any(count < 3 for count in node_counts):
        parser.error("repetitions must be positive and every node count must be at least 3")
    if not 0 <= min(loss_rates) <= max(loss_rates) < 1:
        parser.error("loss rates must be in [0, 1)")
    if args.timeout <= 0 or args.interval <= 0 or args.warmup <= 0 or args.observe <= 0:
        parser.error("timeouts, intervals, warmup, and observation duration must be positive")

    result_root = Path(args.results).expanduser().resolve()
    batch_name = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    batch = result_root / batch_name
    batch.mkdir(parents=True, exist_ok=False)
    scenarios = ["normal", "coordinator_crash"] if args.scenario == "all" else [args.scenario]
    configurations = [
        (scenario, count, rate)
        for scenario in scenarios
        for count in node_counts
        for rate in loss_rates
    ]

    manifest = {
        "created_at": dt.datetime.now().astimezone().isoformat(),
        "nodes": node_counts, "loss_rates": loss_rates,
        "repetitions": args.repetitions, "first_seed": args.seed,
        "timeout_s": args.timeout, "heartbeat_interval_s": args.interval,
        "warmup_s": args.warmup, "observation_s": args.observe,
        "scenarios": scenarios, "runs": len(configurations) * args.repetitions,
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "python": sys.version.split()[0],
        },
    }
    for label, command in (("docker_version", ["docker", "--version"]),
                           ("compose_version", ["docker", "compose", "version"])):
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        manifest[label] = (result.stdout or result.stderr).strip() if result.returncode == 0 else "unavailable"
    (batch / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    if not args.skip_build:
        subprocess.run(["docker", "build", "-t", IMAGE, "."], cwd=ROOT, check=True)

    run_number = 0
    for scenario, count, loss_rate in configurations:
        for repetition in range(args.repetitions):
            run_number += 1
            seed = args.seed + repetition
            run_id = f"run-{run_number:03d}-{scenario}-n{count}-loss{loss_rate:g}-seed{seed}"
            run_dir = batch / run_id
            run_dir.mkdir()
            victim = f"node{count}" if scenario == "coordinator_crash" else None
            project = re.sub(r"[^a-z0-9_-]", "-", f"mc714-{batch_name}-{run_number}").lower()
            compose_file = run_dir / "compose.yaml"
            compose_file.write_text(compose_text(count, args.interval, args.timeout, loss_rate, seed))
            metadata = {
                "run_id": run_id, "scenario": scenario, "nodes": count,
                "loss_rate": loss_rate, "seed": seed, "victim": victim,
                "timeout_s": args.timeout, "heartbeat_interval_s": args.interval,
                "warmup_s": args.warmup, "observation_s": args.observe,
                "start_ts": time.time(), "kill_ts": None,
            }
            (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
            print(f"[{run_number}/{manifest['runs']}] {run_id}", flush=True)
            try:
                compose(project, compose_file, "up", "-d")
                time.sleep(args.warmup)
                if victim:
                    metadata["kill_ts"] = time.time()
                    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
                    compose(project, compose_file, "kill", victim)
                    time.sleep(max(args.observe, 3 * args.timeout))
                else:
                    time.sleep(args.observe)
                log_result = compose(project, compose_file, "logs", "--no-color", "--no-log-prefix",
                                     capture=True, check=False)
                (run_dir / "raw.jsonl").write_text(log_result.stdout or "")
                metadata["end_ts"] = time.time()
                metadata["duration_s"] = metadata["end_ts"] - metadata["start_ts"]
                metadata["completed_at"] = dt.datetime.now().astimezone().isoformat()
                metadata["compose_exit_code"] = log_result.returncode
                (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
                if log_result.returncode:
                    print(f"Warning: docker compose logs returned {log_result.returncode}", file=sys.stderr)
            except Exception as error:
                metadata["error"] = str(error)
                (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
                raise
            finally:
                compose(project, compose_file, "down", check=False, capture=True)

    print(f"Run analysis: python3 scripts/analyze.py {batch}")
    print(f"Results saved under: {batch}")


if __name__ == "__main__":
    main()
