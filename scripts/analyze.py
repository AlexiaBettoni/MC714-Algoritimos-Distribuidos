import json, sys
path, victim, kill_ts = sys.argv[1], sys.argv[2], float(sys.argv[3])
ev = [json.loads(l) for l in open(path) if l.startswith("{")]
det = {e["node"]: e["ts"] - kill_ts for e in ev
       if e["event"] == "suspect" and e["peer"] == victim and e["ts"] >= kill_ts}
false_pos = [e for e in ev if e["event"] == "suspect" and e["peer"] != victim]
print(json.dumps({"victim": victim, "detection_s": det,
                  "max_detection_s": max(det.values()) if det else None,
                  "false_suspicions": len(false_pos)}, indent=2))