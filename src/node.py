"""UDP heartbeat monitoring and a Bully coordinator election."""

import json
import os
import random
import re
import socket
import threading
import time
import uuid
import zlib

NODE_ID = os.environ["NODE_ID"]
PEERS = [peer for peer in os.environ["PEERS"].split(",") if peer and peer != NODE_ID]
PORT = int(os.environ.get("PORT", 5000))
INTERVAL = float(os.environ.get("HB_INTERVAL", 0.5))
TIMEOUT = float(os.environ.get("HB_TIMEOUT", 2.0))
LOSS = float(os.environ.get("LOSS_RATE", 0))
SEED = int(os.environ.get("SEED", 0))
ELECTION_TIMEOUT = max(TIMEOUT, INTERVAL * 3)
START_GRACE = float(os.environ.get("START_GRACE", 8.0))


def node_rank(node_id):
    """Order node1, node2, ... numerically; fall back to lexical IDs."""
    match = re.fullmatch(r"(.*?)(\d+)", node_id)
    return (match.group(1), int(match.group(2))) if match else (node_id, -1)


if len(set([NODE_ID, *PEERS])) != len(PEERS) + 1:
    raise ValueError("NODE_ID and PEERS must contain unique node IDs")

HIGHER_PEERS = sorted((peer for peer in PEERS if node_rank(peer) > node_rank(NODE_ID)), key=node_rank)
rng = random.Random(SEED + zlib.crc32(NODE_ID.encode()))
lock = threading.RLock()
last_seen = {peer: time.time() for peer in PEERS}
suspected = set()
coordinator = None
active_election = None
ok_received = set()
election_condition = threading.Condition(lock)
addresses = {} 


def log(event, **fields):
    print(json.dumps({"ts": time.time(), "node": NODE_ID, "event": event, **fields}), flush=True)


def send_message(sock, peer, msg):
    """Log every outbound application message, including failed sends."""
    packet = {**msg, "from": NODE_ID, "to": peer}
    address = addresses.get(peer)
    if address is None:
        log("message_send_error", message=packet, error="peer address not resolved")
        return
    try:
        sock.sendto(json.dumps(packet).encode(), (address, PORT))
        log("message_sent", message=packet)
    except OSError as error:
        log("message_send_error", message=packet, error=str(error))


def broadcast(sock, msg, peers=None):
    for peer in (PEERS if peers is None else peers):
        send_message(sock, peer, msg)


def resolve_peer(peer):
    """Resolve one peer name, retrying until it exists. A failed lookup can
    block for seconds, so each peer has its own thread and the send path
    never calls DNS."""
    while peer not in addresses:
        try:
            addresses[peer] = socket.gethostbyname(peer)
        except OSError:
            time.sleep(0.2)


def wait_for_peers():
    for peer in PEERS:
        threading.Thread(target=resolve_peer, args=(peer,), daemon=True).start()
    while len(addresses) < len(PEERS):
        time.sleep(0.05)
    now = time.time()
    with lock:
        for peer in PEERS:
            last_seen[peer] = now + START_GRACE
    log("peers_resolved", addresses=dict(addresses))

def start_election(reason):
    """Run a Bully round off the receiver/checker threads."""
    global active_election
    with lock:
        if active_election is not None:
            log("election_already_running", election_id=active_election, reason=reason)
            return
        election_id = f"{NODE_ID}:{uuid.uuid4().hex[:8]}"
        active_election = election_id
        ok_received.clear()
        log("election_started", election_id=election_id, reason=reason,
            higher_peers=HIGHER_PEERS)
    threading.Thread(target=run_election, args=(election_id,), daemon=True).start()


def run_election(election_id):
    global coordinator, active_election
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        broadcast(sock, {"type": "ELECTION", "election_id": election_id}, HIGHER_PEERS)
        deadline = time.monotonic() + ELECTION_TIMEOUT
        with election_condition:
            while active_election == election_id and not ok_received:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                election_condition.wait(remaining)
            if active_election != election_id:
                return
            received_ok = bool(ok_received)

        if received_ok:
            log("election_yielded", election_id=election_id, reason="higher_node_replied")
            # A higher node should finish its own round and announce. If it
            # crashes after replying, retry so the group can make progress.
            with election_condition:
                deadline = time.monotonic() + ELECTION_TIMEOUT
                while active_election == election_id and coordinator is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    election_condition.wait(remaining)
                if active_election != election_id:
                    return
                timed_out = coordinator is None
                active_election = None
            if timed_out:
                log("election_retry", election_id=election_id, reason="coordinator_announcement_timeout")
                start_election("higher_node_did_not_announce")
            return

        with lock:
            if active_election != election_id:
                return
            coordinator = NODE_ID
            active_election = None
            election_condition.notify_all()
        broadcast(sock, {"type": "COORDINATOR", "coordinator": NODE_ID,
                         "election_id": election_id})
        log("coordinator_elected", coordinator=NODE_ID, election_id=election_id)
    finally:
        sock.close()


def sender():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq = 0
    while True:
        broadcast(sock, {"type": "HEARTBEAT", "seq": seq})
        seq += 1
        time.sleep(INTERVAL)


def handle_message(msg, address):
    global coordinator, active_election
    sender_id = msg.get("from")
    kind = msg.get("type")
    if sender_id not in PEERS:
        log("message_rejected", message=msg, reason="unknown_sender", address=address[0])
        return

    log("message_received", message=msg, address=address[0])
    if rng.random() < LOSS:
        log("message_dropped", message=msg, reason="simulated_loss")
        return

    if kind == "HEARTBEAT":
        with lock:
            last_seen[sender_id] = time.time()
            if sender_id in suspected:
                suspected.remove(sender_id)
                log("restore", peer=sender_id)
        return

    if kind == "ELECTION":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_message(sock, sender_id, {"type": "OK", "election_id": msg.get("election_id")})
        sock.close()
        log("election_request_received", peer=sender_id, election_id=msg.get("election_id"))
        if node_rank(NODE_ID) > node_rank(sender_id):
            start_election(f"election_request_from_{sender_id}")
        return

    if kind == "OK":
        with election_condition:
            if active_election == msg.get("election_id"):
                ok_received.add(sender_id)
                election_condition.notify_all()
                log("election_ok_received", peer=sender_id, election_id=active_election)
            else:
                log("stale_ok_ignored", peer=sender_id, election_id=msg.get("election_id"))
        return

    if kind == "COORDINATOR":
        announced = msg.get("coordinator")
        if announced != sender_id:
            log("message_rejected", message=msg, reason="coordinator_sender_mismatch")
            return
        if node_rank(announced) < node_rank(NODE_ID):
            log("lower_coordinator_ignored", peer=sender_id, announced=announced)
            with lock:
                should_elect = coordinator is None or node_rank(coordinator) < node_rank(NODE_ID)
            if should_elect:
                start_election("lower_priority_coordinator_announcement")
            return
        with election_condition:
            if coordinator is None or node_rank(announced) >= node_rank(coordinator):
                coordinator = announced
                active_election = None
                election_condition.notify_all()
                log("coordinator_changed", coordinator=coordinator,
                    peer=sender_id, election_id=msg.get("election_id"))
            else:
                log("stale_coordinator_ignored", peer=sender_id, announced=announced,
                    current=coordinator)
        return

    log("message_rejected", message=msg, reason="unknown_message_type")


def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    while True:
        data, address = sock.recvfrom(4096)
        try:
            msg = json.loads(data)
            if not isinstance(msg, dict):
                raise ValueError("message must be a JSON object")
            handle_message(msg, address)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            log("message_rejected", raw=data.decode(errors="replace"), reason=str(error))


def checker():
    global coordinator
    while True:
        now = time.time()
        with lock:
            for peer, seen_at in last_seen.items():
                if now - seen_at > TIMEOUT and peer not in suspected:
                    suspected.add(peer)
                    log("suspect", peer=peer, silence=round(now - seen_at, 3))
            current_coordinator = coordinator
            should_elect = (current_coordinator in suspected or
                            (current_coordinator is None and active_election is None))
            if current_coordinator in suspected:
                coordinator = None
        if should_elect:
            start_election("coordinator_suspected" if current_coordinator else "no_coordinator")
        time.sleep(max(INTERVAL / 4, 0.05))


if __name__ == "__main__":
    log("start", peers=PEERS, interval=INTERVAL, timeout=TIMEOUT,
        election_timeout=ELECTION_TIMEOUT, loss=LOSS, seed=SEED)
    threading.Thread(target=receiver, daemon=True).start()  
    wait_for_peers()
    for target in (sender, checker):
        threading.Thread(target=target, daemon=True).start()
    while True:
        time.sleep(3600)
