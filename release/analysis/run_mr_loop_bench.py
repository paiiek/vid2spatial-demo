"""Software-in-the-loop motion-to-sound benchmark for the OSC -> MR runtime path.

A virtual head-worn runtime emits head-pose over UDP/OSC at a fixed rate. The
Vid2Spatial OSC consumer receives each pose, composes it with the authored
source azimuth from traj.json (head-relative re-anchoring), and emits the updated
spatial bundle back. We timestamp both ends on the same monotonic clock and
report the loop latency, its jitter, ordering integrity, and the geometric
anchoring error of the re-anchored azimuth.

No HMD hardware is involved: this measures the software path (pose ingest ->
re-anchor -> parameter emit) and deliberately EXCLUDES headset display/wireless
transport and the HRTF convolution block, which are reported separately.

Usage:  python3 test/run_mr_loop_bench.py [--rate 90] [--seconds 60]
"""

import argparse
import json
import math
import socket
import statistics
import threading
import time
from pathlib import Path

from pythonosc import dispatcher as osc_dispatcher
from pythonosc import osc_server, udp_client

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- source track

def load_source_azimuth(traj_path: Path | None):
    """Return a list of source azimuths (deg) from an authored traj.json.

    Falls back to a synthetic sweep when no authored trajectory is available, so
    the benchmark measures the same code path either way.
    """
    if traj_path is not None:
        traj_path = traj_path if traj_path.is_absolute() else (REPO / traj_path)
    if traj_path is not None and traj_path.exists():
        data = json.loads(traj_path.read_text())
        frames = data["frames"] if isinstance(data, dict) and "frames" in data else data
        az = []
        for f in frames:
            v = f.get("az", f.get("azimuth", 0.0))
            # traj.json stores degrees; tolerate radian-scaled files
            az.append(float(v) if abs(float(v)) > math.pi else math.degrees(float(v)))
        if az:
            return az, str(traj_path.relative_to(REPO))
    # synthetic: 30 s at 30 fps, +-45 deg sweep (matches evaluation stimuli range)
    az = [45.0 * math.sin(2 * math.pi * (i / 30.0) / 6.0) for i in range(900)]
    return az, "synthetic sweep (+-45 deg, 6 s period)"


def head_yaw(t):
    """Simulated head yaw (deg): 0.25 Hz sweep, +-60 deg -- a deliberate scan."""
    return 60.0 * math.sin(2 * math.pi * 0.25 * t)


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------- the two ends

class Vid2SpatialConsumer(threading.Thread):
    """The Vid2Spatial OSC consumer: ingest head pose, re-anchor, emit bundle."""

    def __init__(self, in_port, out_port, source_az, fps):
        super().__init__(daemon=True)
        self.source_az = source_az
        self.fps = fps
        self.client = udp_client.SimpleUDPClient("127.0.0.1", out_port)
        disp = osc_dispatcher.Dispatcher()
        disp.map("/hmd/pose", self._on_pose)
        self.server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", in_port), disp)
        self.t0 = None

    def _on_pose(self, _addr, seq, yaw_deg, t_emit):
        # world-anchored source, re-expressed head-relative
        elapsed = time.perf_counter() - self.t0
        idx = min(int(elapsed * self.fps), len(self.source_az) - 1)
        az_rel = wrap180(self.source_az[idx] - yaw_deg)
        # atomic bundle back to the runtime, carrying the originating timestamp
        self.client.send_message(
            "/vid2spatial/spatial",
            [int(seq), float(az_rel), 0.0, 2.0, float(t_emit), float(self.source_az[idx])],
        )

    def run(self):
        self.t0 = time.perf_counter()
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()


class RuntimeReceiver(threading.Thread):
    """The virtual head-worn runtime: emits pose, timestamps returning bundles."""

    def __init__(self, port):
        super().__init__(daemon=True)
        disp = osc_dispatcher.Dispatcher()
        disp.map("/vid2spatial/spatial", self._on_bundle)
        self.server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", port), disp)
        self.samples = []  # (seq, latency_ms, az_rel, az_world)
        self.lock = threading.Lock()

    def _on_bundle(self, _addr, seq, az_rel, _el, _dist, t_emit, az_world):
        lat_ms = (time.perf_counter() - t_emit) * 1000.0
        with self.lock:
            self.samples.append((int(seq), lat_ms, float(az_rel), float(az_world)))

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()


# ---------------------------------------------------------------------- driver

def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def percentile(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=90.0, help="head-pose rate (Hz)")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--fps", type=float, default=30.0, help="authored stream fps")
    ap.add_argument("--traj", type=str, default=None)
    ap.add_argument("--out", type=str, default="results/mr_loop_bench.json")
    args = ap.parse_args()

    source_az, src_name = load_source_azimuth(Path(args.traj) if args.traj else None)

    port_consumer, port_runtime = free_port(), free_port()
    runtime = RuntimeReceiver(port_runtime)
    consumer = Vid2SpatialConsumer(port_consumer, port_runtime, source_az, args.fps)
    runtime.start()
    consumer.start()
    time.sleep(0.3)  # let both servers bind

    pose_client = udp_client.SimpleUDPClient("127.0.0.1", port_consumer)
    n = int(args.rate * args.seconds)
    period = 1.0 / args.rate
    t_start = time.perf_counter()
    sent_yaw = {}
    print(f"[bench] emitting {n} poses at {args.rate:g} Hz ({args.seconds:g} s)...")
    for seq in range(n):
        target = t_start + seq * period
        while True:
            remaining = target - time.perf_counter()
            if remaining <= 0:
                break
            # sleep the bulk, yield the tail -- never spin holding the GIL, which
            # would starve the receiving server threads and inflate the measurement
            time.sleep(remaining * 0.8 if remaining > 5e-4 else 0)
        t_emit = time.perf_counter()
        yaw = head_yaw(t_emit - t_start)
        sent_yaw[seq] = yaw
        pose_client.send_message("/hmd/pose", [seq, float(yaw), float(t_emit)])

    time.sleep(1.0)  # drain in-flight bundles
    consumer.stop()
    runtime.stop()

    with runtime.lock:
        samples = list(runtime.samples)

    lat = [s[1] for s in samples]
    seqs = [s[0] for s in samples]
    received = len(samples)
    dropped = n - received
    out_of_order = sum(1 for a, b in zip(seqs, seqs[1:]) if b < a)

    # geometric anchoring error: does the returned head-relative azimuth equal
    # the exact composition of the authored source azimuth and the emitted yaw?
    anchor_err = [abs(wrap180(s[3] - sent_yaw[s[0]] - s[2])) for s in samples if s[0] in sent_yaw]

    res = {
        "config": {
            "pose_rate_hz": args.rate,
            "duration_s": args.seconds,
            "authored_fps": args.fps,
            "source": src_name,
            "poses_emitted": n,
        },
        "latency_ms": {
            "mean": statistics.fmean(lat),
            "median": statistics.median(lat),
            "p95": percentile(lat, 0.95),
            "p99": percentile(lat, 0.99),
            "max": max(lat),
            "sd": statistics.pstdev(lat),
        },
        "integrity": {
            "received": received,
            "dropped": dropped,
            "drop_rate": dropped / n,
            "out_of_order": out_of_order,
        },
        "anchoring_error_deg": {
            "mean": statistics.fmean(anchor_err),
            "max": max(anchor_err),
        },
        "excluded_from_measurement": [
            "headset display / wireless transport (no HMD hardware in loop)",
            "HRTF convolution block latency (reported separately)",
        ],
    }

    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2))

    L = res["latency_ms"]
    print(f"\n  source           : {src_name}")
    print(f"  latency (ms)     : median {L['median']:.3f}  mean {L['mean']:.3f}  "
          f"p95 {L['p95']:.3f}  p99 {L['p99']:.3f}  max {L['max']:.3f}  sd {L['sd']:.3f}")
    print(f"  integrity        : {received}/{n} received, {dropped} dropped, "
          f"{out_of_order} out-of-order")
    print(f"  anchoring error  : mean {res['anchoring_error_deg']['mean']:.2e} deg, "
          f"max {res['anchoring_error_deg']['max']:.2e} deg")
    print(f"\n  -> {out_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
