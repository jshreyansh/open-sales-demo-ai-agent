"""Synthetic concurrent-call load test for bot.py's voice pipeline.

Part of the concurrent-calls plan's Phase 3: opens K simultaneous plain
WebSocket connections to bot.py's /ws-client endpoint, each one speaking
Pipecat's own protobuf wire protocol and looping a short real recorded
phrase + a silence tail (long enough for VAD's stop_secs to close the
turn) for the whole test duration -- so every simulated caller drives a
real STT -> LLM -> TTS round trip repeatedly, not just idle audio.

Deliberately run against bot.py directly (127.0.0.1:7860 on the box, not
through server.py's voice-lock or any reverse proxy): bot.py has no
admission control of its own today (the lock is enforced one layer up, by
the frontend calling server.py before it ever opens this connection), so
this measures the voice process's own raw concurrent capacity, independent
of whatever _MAX_CONCURRENT_CALLS happens to be set to right now.

Not part of the app -- standalone throwaway tooling, run manually:

    .venv/bin/python3 scripts/load_test_voice.py --k 5 --duration 180 \
        --phrase /tmp/loadtest_phrase.wav

Reads nothing back itself beyond draining the socket (no client-side
transcription/latency logic) -- the actual per-turn timing numbers this
test is judged against (llm_ttft_ms, turn_commit_latency_ms, ttfc_ms) are
already logged by the app's own turn_telemetry.py; pull those from
journalctl for the visitor_ids this script used, tagged
loadtest-<run_id>-<n>, once the run finishes.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import time
import wave

import pipecat.frames.protobufs.frames_pb2 as frame_protos
import websockets

SAMPLE_RATE = 16000
NUM_CHANNELS = 1
CHUNK_MS = 20
SILENCE_TAIL_SECS = 2.5


def _load_phrase_pcm(path: str) -> bytes:
    with wave.open(path, "rb") as wav:
        if wav.getframerate() != SAMPLE_RATE or wav.getnchannels() != NUM_CHANNELS or wav.getsampwidth() != 2:
            raise ValueError(
                f"{path} must be {SAMPLE_RATE}Hz mono 16-bit PCM, "
                f"got {wav.getframerate()}Hz {wav.getnchannels()}ch {wav.getsampwidth() * 8}bit"
            )
        return wav.readframes(wav.getnframes())


def _chunk_bytes() -> int:
    # 16-bit samples -> 2 bytes/frame, mono.
    return int(SAMPLE_RATE * (CHUNK_MS / 1000) * 2)


async def _caller(
    ws_url: str,
    visitor_id: str,
    phrase_pcm: bytes,
    duration_secs: float,
    results: dict,
) -> None:
    chunk_size = _chunk_bytes()
    silence_chunk = b"\x00" * chunk_size
    cycle_pcm = phrase_pcm + silence_chunk * int(SILENCE_TAIL_SECS * 1000 / CHUNK_MS)

    stats = {"chunks_sent": 0, "bytes_recv": 0, "connect_error": None, "send_error": None}
    results[visitor_id] = stats

    try:
        async with websockets.connect(f"{ws_url}?visitorId={visitor_id}", max_size=None) as ws:

            async def _drain():
                try:
                    async for msg in ws:
                        stats["bytes_recv"] += len(msg) if isinstance(msg, (bytes, bytearray)) else 0
                except Exception:
                    pass

            drain_task = asyncio.create_task(_drain())

            deadline = time.monotonic() + duration_secs
            offset = 0
            while time.monotonic() < deadline:
                chunk = cycle_pcm[offset : offset + chunk_size]
                if len(chunk) < chunk_size:
                    offset = 0
                    continue
                offset += chunk_size

                frame = frame_protos.Frame()
                frame.audio.audio = chunk
                frame.audio.sample_rate = SAMPLE_RATE
                frame.audio.num_channels = NUM_CHANNELS
                await ws.send(frame.SerializeToString())
                stats["chunks_sent"] += 1
                await asyncio.sleep(CHUNK_MS / 1000)

            drain_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await drain_task
    except Exception as e:
        stats["connect_error"] = repr(e)


async def run(k: int, duration: float, ws_url: str, phrase_path: str, run_id: str) -> None:
    phrase_pcm = _load_phrase_pcm(phrase_path)
    results: dict = {}
    tasks = [
        asyncio.create_task(_caller(ws_url, f"loadtest-{run_id}-{i}", phrase_pcm, duration, results))
        for i in range(k)
    ]
    start = time.monotonic()
    await asyncio.gather(*tasks)
    elapsed = time.monotonic() - start

    print(f"\n=== load_test_voice: K={k} run_id={run_id} elapsed={elapsed:.1f}s ===")
    for visitor_id, stats in results.items():
        print(f"  {visitor_id}: chunks_sent={stats['chunks_sent']} bytes_recv={stats['bytes_recv']} "
              f"connect_error={stats['connect_error']}")
    failures = [vid for vid, s in results.items() if s["connect_error"]]
    if failures:
        print(f"  FAILED connections: {failures}")
    else:
        print("  all connections completed without a client-side error")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, required=True, help="number of simultaneous simulated callers")
    parser.add_argument("--duration", type=float, default=180, help="seconds each caller stays connected")
    parser.add_argument("--ws-url", default="ws://127.0.0.1:7860/ws-client")
    parser.add_argument("--phrase", required=True, help="path to a 16kHz mono 16-bit PCM WAV file")
    parser.add_argument("--run-id", default=str(int(time.time())), help="tag for this run's visitor_ids")
    args = parser.parse_args()
    asyncio.run(run(args.k, args.duration, args.ws_url, args.phrase, args.run_id))


if __name__ == "__main__":
    main()
