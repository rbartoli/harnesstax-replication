#!/usr/bin/env python3
"""Stage 4: ledger, per-cell summary and paired comparisons for the stage 3 runs.

Usage: stage4.py [JOBS_DIR] [OUT_DIR]   (defaults data/trials and data/stage4 in this repo)

Writes ledger.tsv (one row per trial) and summary.md.  Mirrors HarnessTax's published
method where it is published: cost and success averaged over each task's three attempts
then over the 30 tasks; 95% CIs from 10,000 bootstrap resamples drawing 30 task averages
with replacement; paired cost effect = geometric mean of per-task ratios of task-mean cost;
paired success effect = mean per-task difference.  Adds, as our own extension, a
hierarchical bootstrap (tasks, then runs within task) and pass^3 (solved in all three runs).
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import first_call  # noqa: E402

# Direct-API list prices, USD per million tokens, read 2026-10-07 from the vendors' pricing
# pages; both were already in force on 2026-09-01 (Sol's $4/$20 is promotional "at least
# through November 21, 2026").  HarnessTax's own schedule (agentbrane-research-2026-09-01-v3)
# is not published, so the per-task cost check against their traces below is the calibration.
PRICES = {
    "claude-code": {"in": 3.0, "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.0, "out": 15.0},
    "codex": {"in": 4.0, "cache_read": 0.40, "cache_write_5m": 0.0, "cache_write_1h": 0.0, "out": 20.0},
    "pi": {"in": 4.0, "cache_read": 0.40, "cache_write_5m": 0.0, "cache_write_1h": 0.0, "out": 20.0},
}
MODEL = {"claude-code": "Sonnet 4.6", "codex": "GPT-5.6 Sol", "pi": "GPT-5.6 Sol"}
CELLS = ["oob-codex", "custom-codex", "oob-pi", "custom-pi", "oob-cc", "custom-cc"]
LABEL = {
    "oob-codex": "Codex out-of-the-box", "custom-codex": "Codex custom",
    "oob-pi": "Pi out-of-the-box", "custom-pi": "Pi custom",
    "oob-cc": "Claude Code out-of-the-box", "custom-cc": "Claude Code custom",
}
RETRIED = {"ApiOverloadedError", "ApiUsageLimitError"}  # redone by the driver, not outcomes
B = 10_000
SEED = 20261007

# Published Terminal-Bench 2.0 figures (harnesstax.github.io chart data, generated 2026-09-22).
PUB = {
    "sol-pi": {"rate": 0.8333, "cost": 0.42052, "rate_ci": (0.711, 0.944), "cost_ci": (0.272, 0.612)},
    "sol-codex": {"rate": 0.7889, "cost": 0.76113, "rate_ci": (0.656, 0.911), "cost_ci": (0.463, 1.131)},
    "sonnet-cc": {"rate": 0.6222, "cost": 0.66874, "rate_ci": (0.467, 0.767), "cost_ci": (0.447, 0.917)},
    "sonnet-pi": {"rate": 0.6556, "cost": 0.61436, "rate_ci": (0.489, 0.822), "cost_ci": (0.391, 0.869)},
    "codex/pi cost ratio": (1.81, (1.4725, 2.274)),
    "codex-pi rate diff": (-0.0444, (-0.1222, 0.0111)),
}
# Their per-task mean cost (USD) on the tasks shared with our sample, Sol · Pi and Sol · Codex.
PUB_TASK_COST = {
    "compile-compcert": (0.922072, 2.639034), "financial-document-processor": (0.460697, 0.7631),
    "headless-terminal": (0.171177, 0.247775), "make-doom-for-mips": (2.464657, 4.22329),
    "merge-diff-arc-agi-task": (0.150521, 0.307245), "multi-source-data-merger": (0.067789, 0.136442),
    "openssl-selfsigned-cert": (0.059419, 0.170143), "reshard-c4-data": (0.375865, 0.599713),
    "sparql-university": (0.105115, 0.270509), "sqlite-db-truncate": (0.092419, 0.164914),
    "train-fasttext": (0.634039, 3.062199),
}


def cost_usd(h: str, r: dict) -> float:
    p = PRICES[h]
    cw1h = r.get("cache_write_1h", 0)
    cw5m = r["cache_write"] - cw1h
    return (
        r["uncached_in"] * p["in"] + r["cache_read"] * p["cache_read"]
        + cw5m * p["cache_write_5m"] + cw1h * p["cache_write_1h"] + r["out"] * p["out"]
    ) / 1e6


def load(jobs: Path) -> list[dict]:
    rows = []
    for job in sorted(jobs.glob("s3-r*")):
        if ".failed-" in job.name:
            continue
        m = re.match(r"s3-r(\d)-(oob|custom)-(codex|pi|cc)-(.+)$", job.name)
        if not m:
            continue
        run, cfg, hs, task = int(m[1]), m[2], m[3], m[4]
        trials = [p for p in job.iterdir() if (p / "result.json").exists()]
        if not trials:
            continue
        trial = trials[0]
        result = json.loads((trial / "result.json").read_text())
        exc = (result.get("exception_info") or {}).get("exception_type") or "-"
        reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        if exc in RETRIED and reward != 1.0:  # driver rule: a verified solve stands even if a quota error followed
            continue
        harness = first_call.harness_of(trial)
        tok = {"claude-code": first_call.claude, "codex": first_call.codex, "pi": first_call.pi}[harness](trial)
        row = {
            "run": run, "cell": f"{cfg}-{hs}", "config": cfg, "harness": harness, "task": task,
            "pass": 1 if reward == 1.0 else 0, "reward": reward, "exc": exc,
            "wall_s": first_call.wall_seconds(result),
        }
        if tok is None:  # no transcript (agent died before a call); cost 0, keep the outcome
            tok = dict(first_call_ctx=0, uncached_in=0, cache_read=0, cache_write=0, cache_write_1h=0, out=0, reasoning=0, turns=0)
        row.update(tok)
        if tok.get("capped"):  # Codex past 100 turns: stopped there post hoc, so not a solve
            row["pass"], row["exc"] = 0, "TurnCapTruncated"
        row["cost"] = cost_usd(harness, tok)
        rows.append(row)
    return rows


# ---------- statistics ----------

def task_means(rows: list[dict], key: str) -> dict[str, list[float]]:
    by = defaultdict(list)
    for r in rows:
        by[r["task"]].append(r[key])
    return by


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def pct(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return xs[f] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)


def boot_mean(by: dict[str, list[float]], rng, hier: bool):
    """Mean of task means; CI by task bootstrap (paper) or tasks-then-runs (ours)."""
    tasks = list(by)
    tm = {t: mean(v) for t, v in by.items()}
    point = mean(tm.values())
    out = []
    for _ in range(B):
        pick = rng.choices(tasks, k=len(tasks))
        if hier:
            out.append(mean(mean(rng.choices(by[t], k=len(by[t]))) for t in pick))
        else:
            out.append(mean(tm[t] for t in pick))
    return point, (pct(out, 0.025), pct(out, 0.975))


def boot_pair(a: dict, b: dict, rng, hier: bool):
    """Paired by task.  Returns rate diff (a-b) and cost ratio (a/b) with CIs."""
    tasks = sorted(set(a["pass"]) & set(b["pass"]))

    def stats(pick, resample):
        d, lr = [], []
        for t in pick:
            pa, pb = a["pass"][t], b["pass"][t]
            ca, cb = a["cost"][t], b["cost"][t]
            if resample:
                ia = [rng.randrange(len(pa)) for _ in pa]
                ib = [rng.randrange(len(pb)) for _ in pb]
                pa, ca = [pa[i] for i in ia], [ca[i] for i in ia]
                pb, cb = [pb[i] for i in ib], [cb[i] for i in ib]
            d.append(mean(pa) - mean(pb))
            ma, mb = mean(ca), mean(cb)
            if ma > 0 and mb > 0:
                lr.append(math.log(ma / mb))
        return mean(d), math.exp(mean(lr)) if lr else float("nan")

    diff, ratio = stats(tasks, False)
    bd, br = [], []
    for _ in range(B):
        x, y = stats(rng.choices(tasks, k=len(tasks)), hier)
        bd.append(x)
        br.append(y)
    per_task = []
    for t in tasks:
        ma, mb = mean(a["cost"][t]), mean(b["cost"][t])
        per_task.append((t, mean(a["pass"][t]) - mean(b["pass"][t]), ma / mb if mb else float("nan"), ma, mb))
    ratios = [r for _, _, r, _, _ in per_task if r == r]
    return {
        "n": len(tasks), "diff": diff, "diff_ci": (pct(bd, 0.025), pct(bd, 0.975)),
        "ratio": ratio, "ratio_ci": (pct(br, 0.025), pct(br, 0.975)),
        "wins_a": sum(1 for _, d, *_ in per_task if d > 0), "wins_b": sum(1 for _, d, *_ in per_task if d < 0),
        "costlier": sum(1 for r in ratios if r > 1), "median_ratio": statistics.median(ratios),
        "q1": pct(ratios, 0.25), "q3": pct(ratios, 0.75), "per_task": per_task,
    }


def fmt_ci(ci, f="{:.3f}"):
    return "[" + f.format(ci[0]) + ", " + f.format(ci[1]) + "]"


def main(argv):
    root = Path(__file__).resolve().parent.parent / "data"
    jobs = Path(argv[0]) if argv else root / "trials"
    out = Path(argv[1]) if len(argv) > 1 else root / "stage4"
    out.mkdir(parents=True, exist_ok=True)
    rows = load(jobs)

    cols = ["run", "cell", "config", "harness", "task", "pass", "reward", "exc", "first_call_ctx",
            "uncached_in", "cache_read", "cache_write", "cache_write_1h", "out", "reasoning", "turns", "wall_s", "cost"]
    with (out / "ledger.tsv").open("w") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in sorted(rows, key=lambda r: (r["cell"], r["task"], r["run"])):
            fh.write("\t".join("" if r.get(c) is None else (f"{r[c]:.6f}" if c == "cost" else str(r[c])) for c in cols) + "\n")

    by_cell = {c: [r for r in rows if r["cell"] == c] for c in CELLS}
    md = []
    md.append(f"# Stage 4 — results over {len(rows)} trials\n")
    md.append("Trials: " + ", ".join(f"{LABEL[c]} {len(by_cell[c])}" for c in CELLS) + ".\n")
    md.append("## Price table (USD per million tokens)\n")
    md.append("| Model | Input | Cache read | Cache write 5m | Cache write 1h | Output |\n|---|---|---|---|---|---|")
    for h in ("claude-code", "codex"):
        p = PRICES[h]
        md.append(f"| {MODEL[h]} | {p['in']} | {p['cache_read']} | {p['cache_write_5m']} | {p['cache_write_1h']} | {p['out']} |")
    md.append("\nClaude Code writes to the 1-hour cache tier (`cache_creation.ephemeral_1h_input_tokens`); priced at $6, with the 5-minute tier at $3.75 for any remainder. OpenAI reports cached tokens inside `input_tokens` and reasoning inside `output_tokens`; the ledger splits cached input out and prices output once.\n")

    # ---- per cell ----
    md.append("## Per cell (mean of task means; 95% CI from 10,000 task-bootstrap resamples, then tasks-then-runs)\n")
    md.append("| Cell | Success | CI (task) | CI (hier.) | pass^3 | Cost/attempt | CI (task) | CI (hier.) | Median cost | Timeouts | Turns (mean/max) | First-call ctx mean ± SD |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    summary = {}
    for c in CELLS:
        rs = by_cell[c]
        rng = random.Random(SEED)
        p_by, c_by = task_means(rs, "pass"), task_means(rs, "cost")
        sp, sci = boot_mean(p_by, rng, False)
        _, sci_h = boot_mean(p_by, rng, True)
        cp, cci = boot_mean(c_by, rng, False)
        _, cci_h = boot_mean(c_by, rng, True)
        pass3 = sum(1 for v in p_by.values() if len(v) == 3 and all(v))
        timeouts = sum(1 for r in rs if r["exc"] == "AgentTimeoutError")
        turns = [r["turns"] for r in rs]
        fc = [r["first_call_ctx"] for r in rs if r["first_call_ctx"] > 0]
        summary[c] = dict(rate=sp, cost=cp, pass3=pass3, p_by=p_by, c_by=c_by)
        md.append(
            f"| {LABEL[c]} | {sp:.1%} | {fmt_ci(sci, '{:.1%}')} | {fmt_ci(sci_h, '{:.1%}')} | {pass3}/30 "
            f"| ${cp:.3f} | {fmt_ci(cci, '${:.3f}')} | {fmt_ci(cci_h, '${:.3f}')} | ${statistics.median(r['cost'] for r in rs):.3f} "
            f"| {timeouts} | {mean(turns):.0f} / {max(turns)} | {mean(fc):,.0f} ± {statistics.pstdev(fc):,.0f} |"
        )
    md.append("")
    md.append("Published Terminal-Bench 2.0 (HarnessTax, same method, their 30-task sample): "
              f"Sol · Pi {PUB['sol-pi']['rate']:.1%} / ${PUB['sol-pi']['cost']:.3f} (cost CI {fmt_ci(PUB['sol-pi']['cost_ci'], '${:.3f}')}); "
              f"Sol · Codex {PUB['sol-codex']['rate']:.1%} / ${PUB['sol-codex']['cost']:.3f} ({fmt_ci(PUB['sol-codex']['cost_ci'], '${:.3f}')}); "
              f"Sonnet 4.6 · Claude Code {PUB['sonnet-cc']['rate']:.1%} / ${PUB['sonnet-cc']['cost']:.3f} ({fmt_ci(PUB['sonnet-cc']['cost_ci'], '${:.3f}')}).\n")

    # ---- pairs ----
    pairs = [
        ("codex-oob vs pi-oob (replication of the published 1.81×)", "oob-codex", "oob-pi"),
        ("codex-custom vs pi-custom", "custom-codex", "custom-pi"),
        ("Codex: custom vs out-of-the-box", "custom-codex", "oob-codex"),
        ("Pi: custom vs out-of-the-box", "custom-pi", "oob-pi"),
        ("Claude Code: custom vs out-of-the-box", "custom-cc", "oob-cc"),
    ]
    md.append("## Paired comparisons (A vs B, paired by task; cost ratio = geometric mean of per-task ratios of task-mean cost)\n")
    md.append("| Pair | n | Success diff A−B | CI (task) | CI (hier.) | A wins / B wins | Cost ratio A/B | CI (task) | CI (hier.) | Median ratio [Q1, Q3] | A costlier on |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    pair_out = {}
    for name, a, b in pairs:
        A = {"pass": summary[a]["p_by"], "cost": summary[a]["c_by"]}
        Bb = {"pass": summary[b]["p_by"], "cost": summary[b]["c_by"]}
        rng = random.Random(SEED)
        t = boot_pair(A, Bb, rng, False)
        h = boot_pair(A, Bb, random.Random(SEED), True)
        pair_out[name] = t
        md.append(
            f"| {name} | {t['n']} | {t['diff']:+.1%} | {fmt_ci(t['diff_ci'], '{:+.1%}')} | {fmt_ci(h['diff_ci'], '{:+.1%}')} "
            f"| {t['wins_a']} / {t['wins_b']} | {t['ratio']:.2f}× | {fmt_ci(t['ratio_ci'], '{:.2f}')} | {fmt_ci(h['ratio_ci'], '{:.2f}')} "
            f"| {t['median_ratio']:.2f} [{t['q1']:.2f}, {t['q3']:.2f}] | {t['costlier']}/{t['n']} |"
        )
    md.append("")
    r, ci = PUB["codex/pi cost ratio"]
    d, dci = PUB["codex-pi rate diff"]
    md.append(f"Published Sol Codex vs Pi: cost ratio {r:.2f}× {fmt_ci(ci, '{:.2f}')}, costlier on 29/30 tasks, median 1.69; success diff {d:+.1%} {fmt_ci(dci, '{:+.1%}')}, wins 1/3, same 26 — labelled \"descriptive … no confirmatory test\".\n")

    # per-task table for the three config pairs
    md.append("## Per-task config effect (custom − out-of-the-box success; custom ÷ out-of-the-box cost)\n")
    md.append("| Task | Codex Δ | Codex × | Pi Δ | Pi × | Claude Code Δ | Claude Code × |")
    md.append("|---|---|---|---|---|---|---|")
    pt = {n: {t: (d, r) for t, d, r, _, _ in pair_out[n]["per_task"]} for n in
          ("Codex: custom vs out-of-the-box", "Pi: custom vs out-of-the-box", "Claude Code: custom vs out-of-the-box")}
    for t in sorted(summary["oob-pi"]["p_by"]):
        cells = []
        for n in pt:
            d, r = pt[n].get(t, (float("nan"), float("nan")))
            cells.append(f"{d:+.2f}")
            cells.append(f"{r:.2f}" if r == r else "—")
        md.append(f"| `{t}` | " + " | ".join(cells) + " |")
    md.append("")

    # ---- calibration against published per-task costs ----
    md.append("## Cost calibration — shared tasks, our task-mean cost vs HarnessTax's published per-task cost (Sol · Pi, Sol · Codex, out-of-the-box)\n")
    md.append("| Task | Pi ours | Pi theirs | Codex ours | Codex theirs | Pi pass ours | Codex pass ours |")
    md.append("|---|---|---|---|---|---|---|")
    lp, lc = [], []
    for t, (tp, tc) in sorted(PUB_TASK_COST.items()):
        op = mean(summary["oob-pi"]["c_by"][t]) if t in summary["oob-pi"]["c_by"] else float("nan")
        oc = mean(summary["oob-codex"]["c_by"][t]) if t in summary["oob-codex"]["c_by"] else float("nan")
        pp = mean(summary["oob-pi"]["p_by"].get(t, [float("nan")]))
        pc = mean(summary["oob-codex"]["p_by"].get(t, [float("nan")]))
        if op == op and op > 0:
            lp.append(math.log(op / tp))
        if oc == oc and oc > 0:
            lc.append(math.log(oc / tc))
        md.append(f"| `{t}` | ${op:.3f} | ${tp:.3f} | ${oc:.3f} | ${tc:.3f} | {pp:.2f} | {pc:.2f} |")
    md.append(f"\nGeometric mean of ours ÷ theirs over the {len(lp)} shared tasks: Pi {math.exp(mean(lp)):.2f}×, Codex {math.exp(mean(lc)):.2f}×. "
              "Same tasks, same model, same harness at the paper's version; differences are run variance, price schedule and our per-trial sampling.\n")

    # ---- exceptions / caps ----
    md.append("## Trial accounting\n")
    exc = defaultdict(lambda: defaultdict(int))
    for r in rows:
        exc[r["cell"]][r["exc"]] += 1
    md.append("| Cell | " + " | ".join(sorted({e for v in exc.values() for e in v})) + " |")
    es = sorted({e for v in exc.values() for e in v})
    md.append("|---|" + "---|" * len(es))
    for c in CELLS:
        md.append(f"| {LABEL[c]} | " + " | ".join(str(exc[c].get(e, 0)) for e in es) + " |")
    over = [(r["cell"], r["task"], r["run"], r["turns"], "solved" if r["reward"] == 1.0 else "failed") for r in rows if r["turns"] > 100]
    cap_hits = [(r["cell"], r["task"], r["run"], r["turns"]) for r in rows if r["turns"] == 100 and r["harness"] == "claude-code"]
    unc = {c: [dict(r, pass_=1 if r["reward"] == 1.0 else 0) for r in by_cell[c]] for c in ("oob-codex", "custom-codex")}
    for c in unc:
        pb = task_means([dict(r, **{"pass": r["pass_"]}) for r in unc[c]], "pass")
        md.append(f"Sensitivity, {LABEL[c]} without the post-hoc truncation (verifier verdicts as returned): success {mean(mean(v) for v in pb.values()):.1%}.")
    md.append(f"\nCodex trials past 100 model calls, truncated there post hoc (tokens to call 100; counted as failures; verifier verdict on the full run shown): {over or 'none'}. Claude Code trials ending exactly at the 100-turn cap: {cap_hits or 'none'}.\n")
    null = [(r["cell"], r["task"], r["run"]) for r in rows if r["reward"] is None]
    md.append(f"Trials with a null reward (verifier returned no verdict), counted as failures: {null or 'none'}.\n")

    (out / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
