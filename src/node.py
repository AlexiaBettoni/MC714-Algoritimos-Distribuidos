import json, os, random, socket, threading, time, zlib

NODE_ID = os.environ["NODE_ID"]
PEERS = [p for p in os.environ["PEERS"].split(",") if p != NODE_ID]
PORT = int(os.environ.get("PORT", 5000))
INTERVAL = float(os.environ.get("HB_INTERVAL", 0.5))
TIMEOUT = float(os.environ.get("HB_TIMEOUT", 0.5))
LOSS = float(os.environ.get("LOSS_RATE", 0.5))
SEED = int(os.environ.get("SEED", 0.5))

rng = random.Random(SEED + zlib.crc32(NODE_ID.encode()))
lock = threading.Lock()
last_seen = {p: time.time() for p in PEERS}
suspected = set()


def log(event, **kw):
    print(json.dumps({"ts": time.time(), "node": NODE_ID, "event": event, **kw}), flush=True)
    
def sender():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq = 0
    while True:
        msg = json.dumps({"from": NODE_ID, "seq": seq}).encode()
        for p in PEERS:
            try:
                sock.sendto(msg, (p, PORT))
            except OSError:
                pass
        seq +=1
        time.sleep(INTERVAL)
        
def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    while True:
        data, _ = sock.recvfrom(1024)
        if rng.random() < LOSS:
            continue
        src = json.loads(data)["from"]
        with lock:
            last_seen[src] = time.time()
            if src in suspected:
                suspected.discard(src)
                log("restore", peer=src)
                
def checker():
    while True:
        now = time.time()
        with lock:
            for p, t in last_seen.items():
                if now-t > TIMEOUT and p not in suspected:
                    suspected.add(p)
                    log("Suspect", peer=p, silence = round(now-t,3))
        time.sleep(INTERVAL /4)
        
if __name__=="__main__":
    log("start", peers = PEERS, interval=INTERVAL, timeout=TIMEOUT, loss=LOSS, seed=SEED)
    for f in (receiver, sender, checker):
        threading.Thread(target=f, daemon=True).start()
    while True:
        time.sleep(3600)