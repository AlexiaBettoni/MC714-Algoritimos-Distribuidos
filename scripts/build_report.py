#!/usr/bin/env python3
"""Gera report.md, events.csv e metrics.csv de uma bateria de experimentos.

Substitui analyze.py e check_properties.py: calcula as métricas, verifica as
propriedades de correção (Bully + detector de falhas por heartbeat) e escreve
os três arquivos dentro da pasta da bateria.

Uso:
  python3 scripts/build_report.py results/experiments/<batch> [--tol 1.0] [--sep ,]

Código de saída: 1 se alguma propriedade ESTRITA falhar (útil como teste automatizado).
"""

import argparse
import csv
import datetime as dt
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

MESSAGE_TYPES = ("HEARTBEAT", "ELECTION", "OK", "COORDINATOR")

# chave interna -> rótulo da coluna no relatório
CHECKS = [
    ("no_false_suspicions", "Sem falsa susp."),
    ("completeness", "Completude"),
    ("bounded_detection", "Detecção limitada"),
    ("leader_agreement", "Acordo de líder"),
    ("single_leader", "Líder único"),
    ("election_convergence", "Convergência"),
]

METRIC_COLUMNS = [
    "run_id", "scenario", "nodes", "loss_rate", "seed", "victim", "expected_leader",
    "detection_max_s", "detection_mean_s", "convergence_s", "converged",
    "false_suspicions", "election_msgs", "election_requests", "ok_msgs",
    "coordinator_msgs", "heartbeat_msgs",
    "props_pass", "props_fail_strict", "props_info", "status",
]

EVENT_COLUMNS = ["run_id", "scenario", "t_start_s", "t_kill_s", "node", "event",
                 "affected_node", "detail"]


# --------------------------------------------------------------------------- utilidades

def rank(node):
    return int(re.search(r"(\d+)$", node).group(1))


def percentile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def fmt_stats(values, digits=2):
    """'média ± desvio · p50 · p95' ou '—' se não houver dados."""
    values = [v for v in values if v is not None]
    if not values:
        return "—"
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return (f"{mean:.{digits}f} ± {sd:.{digits}f} · p50 {percentile(values, .5):.{digits}f}"
            f" · p95 {percentile(values, .95):.{digits}f}")


def fmt_duration(seconds):
    if seconds is None:
        return "n/d"
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"


def num(value, digits=3):
    return "" if value is None else round(value, digits)


def load_events(path):
    events = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # o Docker pode inserir linhas de diagnóstico que não são JSON
        if isinstance(event, dict) and "event" in event:
            events.append(event)
    return sorted(events, key=lambda e: e.get("ts", 0))


# --------------------------------------------------------------------------- eventos principais

def key_events(meta, events):
    start, kill, victim = meta["start_ts"], meta.get("kill_ts"), meta.get("victim")
    rows = []

    def add(ts, node, event, affected="", detail=""):
        rows.append((ts, {
            "run_id": meta["run_id"], "scenario": meta["scenario"],
            "t_start_s": f"{ts - start:.3f}",
            "t_kill_s": f"{ts - kill:.3f}" if kill is not None else "",
            "node": node, "event": event, "affected_node": affected, "detail": detail,
        }))

    if kill is not None:
        add(kill, victim, "FALHA_INJETADA", victim, "docker compose kill")
    for e in events:
        node, ts, kind = e.get("node"), e.get("ts", 0), e["event"]
        if not node:
            continue
        if kind == "start":
            add(ts, node, "NO_INICIADO")
        elif kind == "suspect":
            add(ts, node, "SUSPEITA", e.get("peer", ""), f"silencio={e.get('silence')}s")
        elif kind == "restore":
            add(ts, node, "RESTAURADO", e.get("peer", ""), "falsa suspeita desfeita")
        elif kind == "election_started":
            add(ts, node, "ELEICAO_INICIADA", "", f"motivo={e.get('reason', '')}")
        elif kind == "election_yielded":
            add(ts, node, "ELEICAO_CEDEU", "", e.get("reason", ""))
        elif kind == "election_retry":
            add(ts, node, "ELEICAO_REPETIDA", "", f"motivo={e.get('reason', '')}")
        elif kind == "coordinator_elected":
            add(ts, node, "COORDENADOR_ELEITO", e.get("coordinator", ""))
        elif kind == "coordinator_changed":
            add(ts, node, "COORDENADOR_ADOTADO", e.get("coordinator", ""),
                f"anunciado_por={e.get('peer', '')}")
    rows.sort(key=lambda item: item[0])
    return [row for _, row in rows]


# --------------------------------------------------------------------------- métricas + propriedades

def summarize_run(run_dir, tol):
    """Retorna (linha de métricas, dict de checagens, linhas de eventos)."""
    meta = json.loads((run_dir / "metadata.json").read_text())
    base = {"run_id": meta["run_id"], "scenario": meta["scenario"], "nodes": meta["nodes"],
            "loss_rate": meta["loss_rate"], "seed": meta["seed"],
            "victim": meta.get("victim") or ""}
    raw = run_dir / "raw.jsonl"
    if "error" in meta or not raw.exists():
        return {**base, "status": "ERRO"}, {}, []

    events = load_events(raw)
    n, victim, kill_ts, start_ts = meta["nodes"], meta.get("victim"), meta.get("kill_ts"), meta["start_ts"]
    T, D = meta["timeout_s"], meta["heartbeat_interval_s"]
    election_timeout = max(T, 3 * D)
    lossless = meta["loss_rate"] == 0
    dead_at = kill_ts if kill_ts is not None else start_ts
    alive = [f"node{i}" for i in range(1, n + 1) if f"node{i}" != victim]
    expected = max(alive, key=rank)  # Bully: maior ID entre os nós vivos

    suspected = {a: set() for a in alive}
    first_detect, view, adopted_at = {}, {}, {}
    elected_after_kill = set()
    false_suspicions = 0
    counts = {kind: 0 for kind in MESSAGE_TYPES}

    for e in events:
        node, ts, kind = e.get("node"), e.get("ts", 0), e["event"]
        if kind == "message_sent":
            if ts >= dead_at:
                mtype = e.get("message", {}).get("type")
                if mtype in counts:
                    counts[mtype] += 1
        elif kind == "suspect":
            peer = e.get("peer")
            warranted = (victim is not None and kill_ts is not None
                         and peer == victim and ts >= kill_ts)
            if not warranted:
                false_suspicions += 1  # o par ainda estava vivo
            if node in suspected:
                suspected[node].add(peer)
                if warranted:
                    first_detect.setdefault(node, ts - kill_ts)
        elif kind == "restore":
            if node in suspected:
                suspected[node].discard(e.get("peer"))
        elif kind in ("coordinator_elected", "coordinator_changed") and node in suspected:
            view[node] = e["coordinator"]
            if kill_ts is not None and ts >= kill_ts:
                if e["coordinator"] == expected:
                    adopted_at.setdefault(node, ts - kill_ts)
                if kind == "coordinator_elected":
                    elected_after_kill.add(node)

    checks = {}

    def add(key, ok, detail, strict):
        checks[key] = {"ok": bool(ok), "strict": strict, "detail": detail}

    add("no_false_suspicions", false_suspicions == 0,
        f"{false_suspicions} suspeitas indevidas", lossless)

    if victim:
        missing = [a for a in alive if victim not in suspected[a]]
        add("completeness", not missing,
            f"todos os {len(alive)} nós vivos suspeitam de {victim}" if not missing
            else f"sem suspeita permanente de {victim} em: {missing}", True)
        # nó que já suspeitava antes da falha conta com latência 0
        latencies = [first_detect.get(a, 0.0) for a in alive if victim in suspected[a]]
        bound = T + D / 4 + tol
        worst = max(latencies) if latencies else None
        add("bounded_detection", worst is not None and worst <= bound,
            "nenhuma detecção" if worst is None else f"máx {worst:.3f}s, limite {bound:.3f}s", True)

    wrong = {a: view.get(a) for a in alive if view.get(a) != expected}
    add("leader_agreement", not wrong,
        f"todos os nós vivos terminam com líder {expected}" if not wrong
        else f"esperado {expected}, visões finais {wrong}", lossless)

    convergence = None
    if victim:
        add("single_leader", elected_after_kill == {expected},
            f"nós que se declararam líder após a falha: {sorted(elected_after_kill)}", lossless)
        conv_bound = T + D / 4 + 2 * election_timeout + tol
        done = all(a in adopted_at for a in alive)
        convergence = max(adopted_at.values()) if done else None
        add("election_convergence", done and convergence <= conv_bound,
            "nem todos os nós adotaram o novo líder" if not done
            else f"máx {convergence:.3f}s, limite {conv_bound:.3f}s", lossless)

    n_pass = sum(c["ok"] for c in checks.values())
    n_strict = sum((not c["ok"]) and c["strict"] for c in checks.values())
    n_info = sum((not c["ok"]) and not c["strict"] for c in checks.values())
    detections = list(first_detect.values())

    row = {
        **base, "expected_leader": expected,
        "detection_max_s": num(max(detections)) if detections else "",
        "detection_mean_s": num(statistics.mean(detections)) if detections else "",
        "convergence_s": num(convergence),
        "converged": "yes" if not wrong else "no",
        "false_suspicions": false_suspicions,
        "election_msgs": counts["ELECTION"] + counts["OK"] + counts["COORDINATOR"],
        "election_requests": counts["ELECTION"], "ok_msgs": counts["OK"],
        "coordinator_msgs": counts["COORDINATOR"], "heartbeat_msgs": counts["HEARTBEAT"],
        "props_pass": n_pass, "props_fail_strict": n_strict, "props_info": n_info,
        "status": "FALHA" if n_strict else ("INFO" if n_info else "OK"),
    }
    return row, checks, key_events(meta, events)


# --------------------------------------------------------------------------- relatório Markdown

def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def to_float(value):
    return None if value in ("", None) else float(value)


def write_report(batch, manifest, results, tol):
    host = manifest.get("host", {})
    scenarios = manifest.get("scenarios", sorted({r[0]["scenario"] for r in results}))
    first_seed, reps = manifest.get("first_seed"), manifest.get("repetitions")
    seeds = (f"{first_seed}–{first_seed + reps - 1}" if first_seed is not None and reps else "n/d")
    started = manifest.get("created_at", "n/d")
    env_rows = [
        ("Data/hora de início", started),
        ("Duração total", fmt_duration(manifest.get("duration_s"))),
        ("Sistema operacional", host.get("platform", "n/d")),
        ("Processador", host.get("processor") or "n/d"),
        ("CPUs lógicas", host.get("logical_cpu_count", "n/d")),
        ("Python", host.get("python", "n/d")),
        ("Docker", manifest.get("docker_version", "n/d")),
        ("Docker Compose", manifest.get("compose_version", "n/d")),
        ("Algoritmos", "Detector de falhas por heartbeat (UDP) + eleição Bully"),
        ("Cenários", ", ".join(scenarios)),
        ("Nº de nós", ", ".join(map(str, manifest.get("nodes", [])))),
        ("Taxas de perda", ", ".join(f"{x:g}" for x in manifest.get("loss_rates", []))),
        ("Repetições por configuração", f"{reps} (seeds {seeds})"),
        ("Heartbeat / Timeout", f"{manifest.get('heartbeat_interval_s')} s / {manifest.get('timeout_s')} s"),
        ("Warmup / Observação", f"{manifest.get('warmup_s')} s / {manifest.get('observation_s')} s"),
        ("Total de execuções", manifest.get("runs", len(results))),
        ("Tolerância usada nos limites de tempo", f"{tol:g} s (absorve a latência do `docker compose kill`)"),
    ]

    metrics = [r[0] for r in results]
    ok_runs = [m for m in metrics if m["status"] != "ERRO"]
    strict_runs = [m for m in metrics if m["status"] == "FALHA"]

    # propriedades: lossless x com perda
    prop_rows = []
    for key, label in CHECKS:
        cells = []
        for lossy in (False, True):
            applicable = [c[key] for m, c, _ in results
                          if m["status"] != "ERRO" and key in c and (m["loss_rate"] != 0) == lossy]
            cells.append(f"{sum(x['ok'] for x in applicable)}/{len(applicable)}" if applicable else "—")
        strict_note = "estrita" if key in ("completeness", "bounded_detection") else "estrita só sem perda"
        prop_rows.append((label, cells[0], cells[1], strict_note))

    # resumo por configuração
    groups = defaultdict(list)
    for m in metrics:
        groups[(m["scenario"], m["nodes"], m["loss_rate"])].append(m)
    summary_rows = []
    for (scenario, nodes, loss), rows in sorted(groups.items()):
        valid = [r for r in rows if r["status"] != "ERRO"]
        converged = sum(r.get("converged") == "yes" for r in valid)
        summary_rows.append((
            scenario, nodes, f"{loss:g}", len(rows), f"{converged}/{len(valid)}",
            fmt_stats([to_float(r.get("detection_max_s")) for r in valid]),
            fmt_stats([to_float(r.get("convergence_s")) for r in valid]),
            fmt_stats([r.get("election_msgs") for r in valid], 1),
            fmt_stats([r.get("false_suspicions") for r in valid], 1),
        ))

    # verificação por execução
    check_rows, failures = [], []
    for m, checks, _ in results:
        cells = []
        for key, _label in CHECKS:
            c = checks.get(key)
            if c is None:
                cells.append("—")
            else:
                tag = "PASS" if c["ok"] else ("FAIL" if c["strict"] else "INFO")
                cells.append(tag)
                if tag == "FAIL":
                    failures.append(f"- `{m['run_id']}` — {key}: {c['detail']}")
        check_rows.append((m["run_id"], *cells) if checks else (m["run_id"], *["ERRO"] * len(CHECKS)))

    out = [f"# Relatório da bateria {batch.name}", "",
           "## 1. Ambiente e configuração", "",
           md_table(("Item", "Valor"), env_rows), "",
           "## 2. Resumo geral", "",
           f"- Execuções: {len(metrics)} | Completas: {len(ok_runs)} | "
           f"Com falha estrita de propriedade: {len(strict_runs)}",
           f"- Execuções com erro/sem log: {len(metrics) - len(ok_runs)}", "",
           "Propriedades verificadas (aprovadas/aplicáveis):", "",
           md_table(("Propriedade", "Sem perda", "Com perda", "Natureza"), prop_rows), "",
           "Sob perda de mensagens, falhas não estritas são apenas informativas (INFO): "
           "o modelo de canal do detector não garante exatidão com perdas.", "",
           "## 3. Resumo por configuração", "",
           "Formato das células: média ± desvio · p50 · p95 (entre as repetições). "
           "Mensagens de eleição = ELECTION + OK + COORDINATOR enviadas após a falha "
           "(no cenário normal, desde o início, incluindo a eleição inicial).", "",
           md_table(("Cenário", "N", "Perda", "Reps", "Convergiu", "Detecção máx (s)",
                     "Convergência (s)", "Msgs eleição", "Falsas susp."), summary_rows), "",
           "## 4. Verificação de propriedades por execução", "",
           md_table(("Execução", *[label for _, label in CHECKS]), check_rows), "",
           "PASS = ok · FAIL = violação estrita · INFO = não estrita (esperado sob perda) · "
           "— = não se aplica", ""]
    if failures:
        out += ["### Detalhes das falhas estritas", "", *failures, ""]
    out += ["## 5. Arquivos", "",
            "- `events.csv` — eventos principais de cada execução (suspeita, falha, restauração, eleição…)",
            "- `metrics.csv` — métricas por execução",
            "- `manifest.json` — configuração da bateria",
            "- `run-XXX-*/raw.jsonl` — logs brutos; `run-XXX-*/metadata.json` — parâmetros da execução", ""]
    (batch / "report.md").write_text("\n".join(out), encoding="utf-8")


# --------------------------------------------------------------------------- ponto de entrada

def generate(batch, tol=1.0, sep=","):
    """Gera os três arquivos em `batch`. Retorna o número de execuções com falha estrita."""
    batch = Path(batch)
    manifest_path = batch / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    run_dirs = [p for p in sorted(batch.glob("run-*")) if (p / "metadata.json").exists()]
    if not run_dirs:
        raise ValueError(f"nenhuma execução encontrada em {batch}")

    results = [summarize_run(p, tol) for p in run_dirs]

    # utf-8-sig: o Excel reconhece os acentos
    with (batch / "metrics.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=METRIC_COLUMNS, delimiter=sep, extrasaction="ignore",
                                restval="")
        writer.writeheader()
        writer.writerows(m for m, _, _ in results)
    with (batch / "events.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_COLUMNS, delimiter=sep)
        writer.writeheader()
        for _, _, rows in results:
            writer.writerows(rows)

    write_report(batch, manifest, results, tol)
    return sum(m["status"] == "FALHA" for m, _, _ in results)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("batch", help="pasta da bateria (results/experiments/<batch>)")
    parser.add_argument("--tol", type=float, default=1.0,
                        help="tolerância (s) somada aos limites de tempo; absorve a latência "
                             "do 'docker compose kill' após kill_ts (padrão: 1.0)")
    parser.add_argument("--sep", default=",", help="separador dos CSVs (padrão: ','; use ';' no Excel pt-BR)")
    args = parser.parse_args()
    try:
        failures = generate(args.batch, args.tol, args.sep)
    except ValueError as error:
        parser.error(str(error))
    batch = Path(args.batch)
    print(f"Relatório: {batch / 'report.md'}")
    print(f"Eventos:   {batch / 'events.csv'}")
    print(f"Métricas:  {batch / 'metrics.csv'}")
    print(f"{failures} execuções com falha estrita de propriedade")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
