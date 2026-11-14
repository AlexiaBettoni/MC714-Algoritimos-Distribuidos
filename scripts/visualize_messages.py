#!/usr/bin/env python3
"""Render a run's logged UDP traffic as a standalone SVG sequence diagram."""

import argparse
import bisect
import html
import json
from pathlib import Path

COLORS = {
    "HEARTBEAT": "#64748b",
    "ELECTION": "#2563eb",
    "OK": "#16a34a",
    "COORDINATOR": "#9333ea",
}
def read_events(path):
    result = []
    with path.open() as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                result.append(event)
    return result


def text(value):
    return html.escape(str(value), quote=True)


def make_svg(events, metadata, message_types, max_messages, spacing):
    nodes = sorted({event.get("node") for event in events if event.get("node")})
    if metadata:
        nodes = sorted(set(nodes) | {f"node{i}" for i in range(1, metadata.get("nodes", 0) + 1)})
    messages = []
    for event in events:
        if event.get("event") != "message_sent":
            continue
        packet = event.get("message", {})
        kind = packet.get("type")
        source, target = packet.get("from", event.get("node")), packet.get("to")
        if kind in message_types and source in nodes and target in nodes:
            messages.append({"ts": event.get("ts", 0), "from": source,
                             "to": target, "type": kind, "seq": packet.get("seq")})
    messages.sort(key=lambda item: item["ts"])
    omitted = max(0, len(messages) - max_messages)
    if omitted:
        # Keep both the beginning and end of the trace so startup and recovery
        # remain visible in a large heartbeat-inclusive diagram.
        first = max_messages // 2
        messages = messages[:first] + messages[-(max_messages - first):]

    if not nodes:
        raise ValueError("No node events found in this log")
    if not messages:
        raise ValueError("No matching message_sent events found; check the log and message filter")

    left, x_start = 210, 265
    messages_per_row = max(1, (len(messages) + 1) // 2)
    row_count = min(2, len(messages))
    width = x_start + (messages_per_row - 1) * spacing + 190
    width = max(760, width)
    lane_gap = 85
    row_height = 95 + lane_gap * (len(nodes) - 1) + 65
    row_gap = 55
    first_row_top = 80
    height = first_row_top + row_count * row_height + (row_count - 1) * row_gap + 55
    first_ts, last_ts = messages[0]["ts"], messages[-1]["ts"]
    timestamps = [message["ts"] for message in messages]

    def row_and_column(index):
        return divmod(index, messages_per_row)

    def row_top(row):
        return first_row_top + row * (row_height + row_gap)

    def node_y(row, node):
        return row_top(row) + 80 + nodes.index(node) * lane_gap

    def message_x(index):
        # Give every message its own time slot so bursts with nearly identical
        # timestamps remain readable. Timestamps above preserve real timing.
        return x_start + row_and_column(index)[1] * spacing

    title = "Distributed message sequence"
    if metadata:
        parameters = [
            metadata.get("scenario", "run"),
            f"N={metadata.get('nodes', len(nodes))}",
        ]
        if metadata.get("loss_rate") is not None:
            parameters.append(f"loss={metadata['loss_rate']:.0%}")
        if metadata.get("seed") is not None:
            parameters.append(f"seed={metadata['seed']}")
        if metadata.get("heartbeat_interval_s") is not None:
            parameters.append(f"heartbeat={metadata['heartbeat_interval_s']:g}s")
        if metadata.get("timeout_s") is not None:
            parameters.append(f"timeout={metadata['timeout_s']:g}s")
        if metadata.get("victim"):
            parameters.append(f"victim={metadata['victim']}")
        title = "Experiment: " + " · ".join(parameters)
    subtitle = (f"Showing {len(messages)} of {len(messages) + omitted} messages · "
                "time flows left to right across two rows")
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto">',
        '<polygon points="0 0, 9 3.5, 0 7" fill="context-stroke"/></marker>',
        '<marker id="time-arrow" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto">',
        '<polygon points="0 0, 9 3.5, 0 7" fill="context-stroke"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#172033}.small{font-size:12px}.label{font-size:13px;font-weight:600}.title{font-size:20px;font-weight:700}.muted{fill:#64748b}</style>',
        f'<text x="30" y="32" class="title">{text(title)}</text>',
        # f'<text x="30" y="54" class="small muted">{text(subtitle)}</text>',
    ]
    for row in range(row_count):
        axis_y = row_top(row) + 20
        out.append(f'<text x="28" y="{axis_y+4}" class="small muted">timeline {row+1}/{row_count}</text>')
        out.append(f'<line x1="{x_start-20}" y1="{axis_y}" x2="{width-35}" y2="{axis_y}" stroke="#475569" stroke-width="1.5" marker-end="url(#time-arrow)"/>')
        out.append(f'<text x="{width-32}" y="{axis_y-9}" text-anchor="end" class="small muted">time →</text>')
        for node in nodes:
            y = node_y(row, node)
            out.append(f'<rect x="28" y="{y-17}" width="112" height="34" rx="6" fill="#f1f5f9" stroke="#94a3b8"/>')
            out.append(f'<text x="84" y="{y+4}" text-anchor="middle" class="label">{text(node)}</text>')
            out.append(f'<line x1="{left}" y1="{y}" x2="{width-30}" y2="{y}" stroke="#cbd5e1" stroke-dasharray="4 5"/>')

    kill_ts = metadata.get("kill_ts") if metadata else None
    if kill_ts is not None and first_ts <= kill_ts <= last_ts:
        index = min(bisect.bisect_left(timestamps, kill_ts), len(messages) - 1)
        row, _ = row_and_column(index)
        x = message_x(index)
        out.append(f'<line x1="{x:.1f}" y1="{row_top(row)+43}" x2="{x:.1f}" y2="{row_top(row)+row_height-12}" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="7 5"/>')
        out.append(f'<rect x="{x-54:.1f}" y="{row_top(row)+row_height-16}" width="108" height="18" fill="#fff"/>')
        out.append(f'<text x="{x:.1f}" y="{row_top(row)+row_height-3}" text-anchor="middle" class="small" fill="#dc2626">crash injected</text>')

    for index, message in enumerate(messages):
        row, _ = row_and_column(index)
        x = message_x(index)
        y1, y2 = node_y(row, message["from"]), node_y(row, message["to"])
        color = COLORS.get(message["type"], "#475569")
        relative_time = message["ts"] - first_ts
        axis_y = row_top(row) + 20
        out.append(f'<line x1="{x:.1f}" y1="{axis_y-4}" x2="{x:.1f}" y2="{axis_y+8}" stroke="#94a3b8"/>')
        out.append(f'<text x="{x:.1f}" y="{axis_y+27}" text-anchor="middle" class="small muted">+{relative_time:.3f}s</text>')
        out.append(f'<line x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y2}" stroke="{color}" stroke-width="1.8" marker-end="url(#arrow)"/>')
    legend_y = height - 26
    x = 35
    for kind in ("ELECTION", "OK", "COORDINATOR", "HEARTBEAT"):
        if kind not in message_types:
            continue
        color = COLORS[kind]
        out.append(f'<line x1="{x}" y1="{legend_y-4}" x2="{x+26}" y2="{legend_y-4}" stroke="{color}" stroke-width="2"/>')
        out.append(f'<text x="{x+32}" y="{legend_y}" class="small">{kind}</text>')
        x += 150
    out.append('</svg>')
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", help="run directory or raw.jsonl path")
    parser.add_argument("--output", "-o", help="output SVG path")
    parser.add_argument("--include-heartbeats", action="store_true",
                        help="include periodic heartbeat traffic (can be very dense)")
    parser.add_argument("--max-messages", type=int, default=500,
                        help="maximum arrows drawn, retaining the beginning and end (default: 500)")
    parser.add_argument("--spacing", type=int, default=90,
                        help="horizontal pixels between message events (default: 90)")
    args = parser.parse_args()
    if args.max_messages < 1:
        parser.error("--max-messages must be positive")
    if args.spacing < 30:
        parser.error("--spacing must be at least 30 pixels")

    source = Path(args.run).expanduser()
    if source.is_dir():
        log_path = source / "raw.jsonl"
        metadata_path = source / "metadata.json"
        default_output = source / "messages.svg"
    else:
        log_path = source
        metadata_path = source.with_name("metadata.json")
        default_output = source.with_suffix(".svg")
    if not log_path.is_file():
        parser.error(f"log file not found: {log_path}")
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else None
    kinds = {"ELECTION", "OK", "COORDINATOR"}
    if args.include_heartbeats:
        kinds.add("HEARTBEAT")
    try:
        svg = make_svg(read_events(log_path), metadata, kinds, args.max_messages, args.spacing)
    except ValueError as error:
        parser.error(str(error))
    output = Path(args.output).expanduser() if args.output else default_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
