"""Ensaio de crash-stop: sobe os nós, mata um e mede o tempo de detecção.
 
Uso (qualquer terminal):
  python scripts\run_kill_powershell.sh node3 --timeout 2 --loss 0.1 --seed 1 --out results/run1.json
"""
import argparse, json, os, subprocess, sys, time
 
ap = argparse.ArgumentParser()
ap.add_argument("victim", nargs="?", default="node3")
ap.add_argument("--interval", type=float, default=0.5)
ap.add_argument("--timeout", type=float, default=2.0)
ap.add_argument("--loss", type=float, default=0.0)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--warmup", type=float, default=5.0)
ap.add_argument("--out", default=None)
a = ap.parse_args()
 
env = {**os.environ, "HB_INTERVAL": str(a.interval), "HB_TIMEOUT": str(a.timeout),
       "LOSS_RATE": str(a.loss), "SEED": str(a.seed)}
 
def dc(*args, capture=False):
    return subprocess.run(["docker", "compose", *args], env=env, check=True,
                          capture_output=capture, text=True, encoding="utf-8")
 
try:
    dc("up", "-d", "--build")
    time.sleep(a.warmup)                       # aquecimento
    kill_ts = time.time()
    dc("kill", a.victim)                       # crash-stop
    time.sleep(a.timeout * 3)                  # tempo para todos detectarem
    logs = dc("logs", "--no-log-prefix", "--no-color", capture=True).stdout
finally:
    subprocess.run(["docker", "compose", "down"], env=env)
 
ev = [json.loads(l) for l in logs.splitlines() if l.startswith("{")]
detection = {e["node"]: round(e["ts"] - kill_ts, 3) for e in ev
             if e["event"] == "suspect" and e["peer"] == a.victim and e["ts"] >= kill_ts}
false_susp = sum(1 for e in ev if e["event"] == "suspect" and e["peer"] != a.victim)
 
result = {"victim": a.victim, "interval": a.interval, "timeout": a.timeout,
          "loss": a.loss, "seed": a.seed, "detection_s": detection,
          "max_detection_s": max(detection.values()) if detection else None,
          "false_suspicions": false_susp}
 
text = json.dumps(result, indent=2)
if a.out:
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "w").write(text)
print(text)