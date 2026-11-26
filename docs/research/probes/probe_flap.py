"""Flap probe — does the vendor kline resubscribe survive REPEATED partitions?

The 2026-11-26 soak measured production behavior the single-cycle smoke probe
(live-smoke §8a) never reproduced: websocket clients logging successful
reconnects for hours while the kline stream never delivered another closed
bar — recovery only by REST backfill. Vendor-code reading points at
`BinanceWebSocketClient._handle_reconnect`: the resubscribe is one
fire-and-forget task, no retry, exceptions never logged. Whether the failure
is probabilistic (race into a non-active connection state) or systematic
(cumulative stream-table corruption) is exactly what repetition answers.

Method: one production-wired desk (BTCUSDT 1m, the density tape) behind a
killable local CONNECT proxy. Killing the proxy is a real network partition
for the websocket clients — TCP dies, the Rust controller reconnects when the
proxy returns. Per cycle we measure:

  partition_open    proxy killed
  partition_close   proxy restarted (SAME port — the desk's pinned URL)
  quotes_resumed_at first post-reconnect quote beat
  bar_resumed_at    first post-reconnect closed bar processed
  verdict           RESUMED (bar after reconnect),
                    DIED (quotes flowing 150s+ with no bar — the vendor
                          failure shape),
                    STILL_PARTITIONED (no quote flow either)

REST stays up throughout (the backfill client does not use the ws proxy —
matches production, where REST never died either). Bars arrive at most once
a minute, so DIED needs 150s of quote flow before it is honest to call.

Usage:
    cd backend && uv run python ../docs/research/probes/probe_flap.py [cycles]

The probe is read-only against everything but its own throwaway sqlite file
in /tmp — never the owner's data.db, never the soak databases.
"""

import asyncio
import json
import socket
import sys
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------- CONNECT proxy
# Minimal HTTP CONNECT tunnel: enough for the websocket clients, deliberately
# without any of the cleverness a real proxy needs. Kill = listener closed and
# tunnels cancelled; the TCP connections die with it.


class ConnectProxy:
    def __init__(self, host="127.0.0.1", port=0, mode="hard"):
        """mode 'hard': killing the proxy severs TCP — the flap-probe shape.
        mode 'blackhole': 'killing' stops forwarding bytes but keeps every
        socket open — writes succeed into a void, no RST, no FIN. That is
        the heartbeat-timeout path, a different controller state than
        write-failure, and the 2026-11-26 soak's more plausible killer."""
        self._host = host
        self._port = port
        self.mode = mode
        self._server = None
        self._loop = None
        self._thread = None
        self._tunnels = []
        self._dropping = False  # blackhole: pipes alive, bytes swallowed
    @property
    def url(self):
        return f"http://{self._host}:{self._port}"

    async def _pipe(self, reader, writer):
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                if self._dropping:
                    # blackhole partition: the byte stream vanishes into the
                    # void — the socket stays open, nothing ever answers
                    continue
                writer.write(data)
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError, OSError):
            pass
        finally:
            try:
                writer.close()
            except OSError:
                pass

    def blackhole(self, on: bool):
        """Open/close the silent void. Only meaningful in blackhole mode."""
        self._dropping = on

    async def _handle(self, client_reader, client_writer):
        try:
            head = await asyncio.wait_for(client_reader.readuntil(b"\r\n\r\n"), timeout=10)
            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            method, target, _ = line.split(" ", 2)
            if method != "CONNECT":
                client_writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                await client_writer.drain()
                client_writer.close()
                return
            host, port = target.rsplit(":", 1)
            remote_reader, remote_writer = await asyncio.open_connection(host, int(port))
            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
            t1 = asyncio.ensure_future(self._pipe(client_reader, remote_writer))
            t2 = asyncio.ensure_future(self._pipe(remote_reader, client_writer))
            self._tunnels.extend([t1, t2])
            await asyncio.gather(t1, t2, return_exceptions=True)
        except (asyncio.IncompleteReadError, ConnectionResetError, TimeoutError, OSError):
            try:
                client_writer.close()
            except OSError:
                pass

    def _listen_socket(self):
        """SO_REUSEADDR listener: restart-after-kill must rebind the SAME
        port, because the desk's data config pinned the original proxy URL —
        a proxy on a fresh port is a proxy the desk never finds."""
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._port))
        self._port = sock.getsockname()[1]
        return sock

    def start(self):
        sock = None
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                sock = self._listen_socket()
                break
            except OSError:
                time.sleep(0.2)  # TIME_WAIT of the killed instance draining
        if sock is None:
            raise OSError(f"proxy cannot bind {self._host}:{self._port}")

        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def serve():
                self._server = await asyncio.start_server(self._handle, sock=sock)
                async with self._server:
                    await self._server.serve_forever()

            try:
                self._loop.run_until_complete(serve())
            except asyncio.CancelledError:
                pass
            finally:
                self._loop.close()

        self._server = None
        self._thread = threading.Thread(target=run, daemon=True, name="flap-proxy")
        self._thread.start()
        deadline = time.time() + 5
        while self._server is None and time.time() < deadline:
            time.sleep(0.05)

    def stop(self):
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._hard_stop)
            if self._thread is not None:
                self._thread.join(timeout=5)

    def _hard_stop(self):
        for t in self._tunnels:
            t.cancel()
        if self._server is not None:
            self._server.close()
        for task in asyncio.all_tasks(self._loop):
            task.cancel()


# ---------------------------------------------------------------- desk boot

def boot_desk(proxy_url: str):
    """The production twin through the flap proxy. Throwaway sqlite in /tmp —
    the probe measures a live data path, it does not trade anyone's book."""
    from trading.desk.live import build_production_desk, seed_drop_forming_bar
    from trading.desk.node import DeskSpec
    from trading.models import init_schema, make_engine, make_session_factory
    from trading.research import STRATEGIES

    db_path = Path(f"/tmp/flap-probe-{int(time.time())}.db")
    engine = make_engine(f"sqlite:///{db_path}")
    init_schema(engine)
    session_factory = make_session_factory(engine)

    catalog = STRATEGIES["scalp"]
    spec = DeskSpec(
        bot="scalp",
        symbol="BTCUSDT",
        timeframe="1m",
        strategy_cls=catalog["cls"],
    )
    desk = build_production_desk(
        specs=[spec],
        session_factory=session_factory,
        seed_history=seed_drop_forming_bar,
        proxy_url=proxy_url,
        feed_stale_after_s=180.0,
    )
    return desk


def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    mode = sys.argv[2] if len(sys.argv) > 2 else "hard"
    flap_s = 70.0
    observe_s = 150.0

    print(json.dumps({"event": "probe_start", "cycles": cycles, "flap_s": flap_s, "mode": mode}), flush=True)

    proxy = ConnectProxy(mode=mode)
    proxy.start()
    print(json.dumps({"event": "proxy_up", "url": proxy.url}), flush=True)

    desk = boot_desk(proxy.url)
    t = threading.Thread(target=desk.node.run, daemon=True, name="probe-desk")
    t.start()

    def bars():
        return desk._strategy_for("scalp")._k + 1

    def quotes_alive(window=10.0):
        beats = getattr(desk, "quote_beats", {}) or {}
        if not beats:
            return False
        now = time.monotonic()
        return any(now - b < window for b in beats.values())

    def partition(open_it: bool):
        """Open/close the partition in the probe's mode. Hard kills the
        proxy (TCP severs, write-failure path); blackhole only swallows
        bytes (heartbeat-timeout path) and the proxy never dies."""
        if mode == "blackhole":
            proxy.blackhole(open_it)
            return None
        if open_it:
            proxy.stop()
            return None
        fresh = ConnectProxy(port=proxy._port)
        fresh.start()
        return fresh

    results = []
    try:
        # warm-up: wait for the first live bar so the stream is proven working
        deadline = time.time() + 240
        base = bars()
        while time.time() < deadline and bars() == base:
            time.sleep(2)
        print(json.dumps({"event": "warmup_done", "bars": bars()}), flush=True)

        for cycle in range(cycles):
            rec = {"cycle": cycle}
            # --- partition
            partition(True)
            rec["partition_open"] = round(time.time(), 1)
            time.sleep(flap_s)
            fresh = partition(False)
            if fresh is not None:
                proxy = fresh
            rec["partition_close"] = round(time.time(), 1)

            # --- observe: quotes resume? bars resume?
            bars_at_close = bars()
            deadline = time.time() + observe_s + 90
            quotes_at = None
            bar_at = None
            while time.time() < deadline:
                if quotes_at is None and quotes_alive(window=8):
                    quotes_at = time.time()
                if bars() > bars_at_close:
                    bar_at = time.time()
                    break
                # honest DIED: quotes flowing for observe_s, no bar
                if quotes_at is not None and time.time() - quotes_at > observe_s:
                    break
                time.sleep(2)

            if quotes_at is not None:
                rec["quotes_resumed_s"] = round(quotes_at - rec["partition_close"], 1)
            if bar_at is not None:
                rec["verdict"] = "RESUMED"
                rec["recovery_s"] = round(bar_at - rec["partition_close"], 1)
            elif quotes_at is not None:
                rec["verdict"] = "DIED"
            else:
                rec["verdict"] = "STILL_PARTITIONED"
            results.append(rec)
            print(json.dumps({"event": "cycle", **rec}), flush=True)

            if rec["verdict"] == "DIED":
                print(json.dumps({
                    "event": "terminal",
                    "reason": "kline stream dead behind live quotes — the vendor failure shape reproduced",
                }), flush=True)
                break

    finally:
        try:
            desk.node.stop()
        except Exception as exc:
            print(json.dumps({"event": "stop_error", "detail": str(exc)}), flush=True)
        proxy.stop()

    died = sum(1 for r in results if r["verdict"] == "DIED")
    resumed = sum(1 for r in results if r["verdict"] == "RESUMED")
    print(json.dumps({
        "event": "summary",
        "cycles": len(results),
        "resumed": resumed,
        "died": died,
        "still_partitioned": len(results) - resumed - died,
        "recoveries_s": [r.get("recovery_s") for r in results if r["verdict"] == "RESUMED"],
    }), flush=True)


if __name__ == "__main__":
    main()
