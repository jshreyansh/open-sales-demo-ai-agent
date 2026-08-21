#!/usr/bin/env python3
"""Turns TURN_TELEMETRY log lines into the before/after table.

Usage:
    ssh <box> 'sudo journalctl -u contentiq-voicebot --since "2 hours ago" -o cat' \
      | python3 scripts/latency-report.py --label baseline --save baseline.json

    python3 scripts/latency-report.py --label "phase 2" --compare baseline.json < after.log

Every metric keeps the name it was measured under. In particular
llm_to_tts_enqueue is OUR aggregation gap and tts_acoustic_latency is the
vendor's -- they are never summed into a single "TTS" number, because that
would send anyone optimising it to the wrong place.
"""
import argparse, json, statistics, sys

# (key, label, whose problem it is when the number is bad)
METRICS = [
    ("turn_commit_latency_ms",      "Turn commit",            "ours"),
    ("llm_ttft_ms",                 "LLM first token",        "model"),
    ("llm_to_tts_enqueue_ms",       "LLM -> TTS enqueue",     "ours"),
    ("tts_acoustic_latency_ms",     "TTS acoustic",           "vendor"),
    ("time_to_first_sound_ms",      "-> first SOUND (bridge)", "sum"),
    ("time_to_reply_enqueue_ms",    "-> reply enqueued",       "sum"),
    ("acoustic_ttfa_ms",            "ACOUSTIC TTFA",          "what they feel"),
    ("ttfc_ms",                     "Reply complete (TTFC)",  "completion"),
]

def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo))

def load(stream):
    turns = []
    for line in stream:
        if "TURN_TELEMETRY " not in line:
            continue
        try:
            turns.append(json.loads(line.split("TURN_TELEMETRY ", 1)[1].strip()))
        except (ValueError, IndexError):
            continue
    return turns

def summarise(turns):
    out = {"n_turns": len(turns)}
    for key, _, _ in METRICS:
        vals = [t[key] for t in turns if t.get(key) is not None]
        out[key] = {"n": len(vals), "p50": pct(vals, 50), "p95": pct(vals, 95)}
    out["released_by"] = {}
    out["smart_turn"] = {}
    for t in turns:
        for field, bucket in (("released_by", "released_by"), ("smart_turn_verdict", "smart_turn")):
            v = t.get(field) or "unknown"
            out[bucket][v] = out[bucket].get(v, 0) + 1
    n = max(len(turns), 1)
    out["early_commit_followups"] = sum(1 for t in turns if t.get("early_commit_followup"))
    out["interruptions"] = sum(1 for t in turns if t.get("interrupted"))
    out["backchannels_total"] = sum(t.get("backchannel_count", 0) for t in turns)
    out["backchannels_per_turn"] = round(out["backchannels_total"] / n, 2)
    out["max_consecutive_auto_beats"] = max((t.get("consecutive_auto_beats", 0) for t in turns), default=0)
    return out

def cell(v):
    return "  --  " if v is None else f"{v:>5}"

def report(label, cur, base=None):
    print(f"\n=== {label} — {cur['n_turns']} turns ===\n")
    if base:
        print(f"{'metric':<24}{'whose':<15}{'before p50':>11}{'after p50':>11}"
              f"{'before p95':>12}{'after p95':>11}")
        print("-" * 84)
    else:
        print(f"{'metric':<24}{'whose':<15}{'p50':>8}{'p95':>8}")
        print("-" * 55)
    for key, name, whose in METRICS:
        c = cur[key]
        if base:
            b = base[key]
            print(f"{name:<24}{whose:<15}{cell(b['p50']):>11}{cell(c['p50']):>11}"
                  f"{cell(b['p95']):>12}{cell(c['p95']):>11}")
        else:
            print(f"{name:<24}{whose:<15}{cell(c['p50']):>8}{cell(c['p95']):>8}")
        if c["n"] == 0:
            print(f"{'':<24}(never measured — the stage produced no timestamp)")

    def counts(d):
        return ", ".join(f"{k}={v}" for k, v in sorted(d.items(), key=lambda kv: -kv[1])) or "none"
    print()
    for name, key in [("released by", "released_by"), ("Smart Turn", "smart_turn")]:
        line = f"{name:<24}{counts(cur[key])}"
        if base:
            line += f"\n{'  (before)':<24}{counts(base[key])}"
        print(line)
    print()
    for name, key in [("early-followups", "early_commit_followups"),
                      ("interruptions", "interruptions"),
                      ("backchannels/turn", "backchannels_per_turn"),
                      ("max consecutive beats", "max_consecutive_auto_beats")]:
        line = f"{name:<24}{cur[key]}"
        if base:
            line += f"   (before: {base[key]})"
        print(line)

def traces(turns, n=3):
    """A few real timelines. Averages hide the shape of a turn."""
    print(f"\n=== {min(n, len(turns))} representative traces ===")
    for t in turns[:n]:
        print(f"\nturn {t.get('turn_id')}  verdict={t.get('smart_turn_verdict')} "
              f"released_by={t.get('released_by')} fragments={t.get('fragments')}")
        prev = 0
        for key, name, _ in METRICS[:4]:
            v = t.get(key)
            if v is None:
                print(f"    {name:<22} --")
                continue
            prev += v
            print(f"    {name:<22}{v:>6}ms   (cumulative {prev}ms)")
        print(f"    {'ACOUSTIC TTFA':<22}{cell(t.get('acoustic_ttfa_ms'))}ms  <- felt latency")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="run")
    ap.add_argument("--save")
    ap.add_argument("--compare")
    ap.add_argument("--traces", type=int, default=3)
    a = ap.parse_args()

    turns = load(sys.stdin)
    if not turns:
        sys.exit("No TURN_TELEMETRY lines found. Has a call happened on this build?")
    cur = summarise(turns)
    base = json.load(open(a.compare)) if a.compare else None
    report(a.label, cur, base)
    if a.traces:
        traces(turns, a.traces)
    if a.save:
        json.dump(cur, open(a.save, "w"), indent=2)
        print(f"\nsaved -> {a.save}")
