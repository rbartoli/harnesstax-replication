# Stage 4 — results over 540 trials

Trials: Codex out-of-the-box 90, Codex custom 90, Pi out-of-the-box 90, Pi custom 90, Claude Code out-of-the-box 90, Claude Code custom 90.

## Price table (USD per million tokens)

| Model | Input | Cache read | Cache write 5m | Cache write 1h | Output |
|---|---|---|---|---|---|
| Sonnet 4.6 | 3.0 | 0.3 | 3.75 | 6.0 | 15.0 |
| GPT-5.6 Sol | 4.0 | 0.4 | 0.0 | 0.0 | 20.0 |

Claude Code writes to the 1-hour cache tier (`cache_creation.ephemeral_1h_input_tokens`); priced at $6, with the 5-minute tier at $3.75 for any remainder. OpenAI reports cached tokens inside `input_tokens` and reasoning inside `output_tokens`; the ledger splits cached input out and prices output once.

## Per cell (mean of task means; 95% CI from 10,000 task-bootstrap resamples, then tasks-then-runs)

| Cell | Success | CI (task) | CI (hier.) | pass^3 | Cost/attempt | CI (task) | CI (hier.) | Median cost | Timeouts | Turns (mean/max) | First-call ctx mean ± SD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex out-of-the-box | 76.7% | [62.2%, 88.9%] | [62.2%, 90.0%] | 20/30 | $0.841 | [$0.501, $1.259] | [$0.497, $1.273] | $0.385 | 2 | 27 / 129 | 13,342 ± 147 |
| Codex custom | 84.4% | [73.3%, 93.3%] | [73.3%, 94.4%] | 21/30 | $0.842 | [$0.517, $1.233] | [$0.513, $1.237] | $0.344 | 3 | 26 / 107 | 15,146 ± 146 |
| Pi out-of-the-box | 83.3% | [71.1%, 93.3%] | [71.1%, 94.4%] | 22/30 | $0.435 | [$0.283, $0.616] | [$0.277, $0.621] | $0.251 | 6 | 17 / 69 | 1,285 ± 146 |
| Pi custom | 76.7% | [62.2%, 88.9%] | [62.2%, 90.0%] | 21/30 | $0.633 | [$0.443, $0.857] | [$0.439, $0.862] | $0.468 | 8 | 19 / 68 | 11,179 ± 146 |
| Claude Code out-of-the-box | 57.8% | [40.0%, 74.4%] | [41.1%, 74.4%] | 16/30 | $0.892 | [$0.568, $1.294] | [$0.556, $1.362] | $0.411 | 16 | 18 / 73 | 22,188 ± 170 |
| Claude Code custom | 57.8% | [41.1%, 73.3%] | [41.1%, 73.3%] | 14/30 | $1.005 | [$0.746, $1.294] | [$0.732, $1.311] | $0.624 | 15 | 19 / 100 | 30,945 ± 170 |

Published Terminal-Bench 2.0 (HarnessTax, same method, their 30-task sample): Sol · Pi 83.3% / $0.421 (cost CI [$0.272, $0.612]); Sol · Codex 78.9% / $0.761 ([$0.463, $1.131]); Sonnet 4.6 · Claude Code 62.2% / $0.669 ([$0.447, $0.917]).

## Paired comparisons (A vs B, paired by task; cost ratio = geometric mean of per-task ratios of task-mean cost)

| Pair | n | Success diff A−B | CI (task) | CI (hier.) | A wins / B wins | Cost ratio A/B | CI (task) | CI (hier.) | Median ratio [Q1, Q3] | A costlier on |
|---|---|---|---|---|---|---|---|---|---|---|
| codex-oob vs pi-oob (replication of the published 1.81×) | 30 | -6.7% | [-14.4%, +0.0%] | [-16.7%, +2.2%] | 1 / 5 | 1.72× | [1.32, 2.10] | [1.33, 2.17] | 1.99 [1.46, 2.26] | 27/30 |
| codex-custom vs pi-custom | 30 | +7.8% | [-1.1%, +18.9%] | [-3.3%, +20.0%] | 5 / 2 | 1.09× | [0.90, 1.29] | [0.88, 1.30] | 1.04 [0.88, 1.53] | 15/30 |
| Codex: custom vs out-of-the-box | 30 | +7.8% | [+2.2%, +14.4%] | [-0.0%, +16.7%] | 6 / 0 | 1.06× | [0.97, 1.16] | [0.95, 1.18] | 1.02 [0.91, 1.26] | 15/30 |
| Pi: custom vs out-of-the-box | 30 | -6.7% | [-14.4%, +0.0%] | [-16.7%, +2.2%] | 1 / 5 | 1.67× | [1.53, 1.83] | [1.50, 1.92] | 1.64 [1.41, 1.85] | 30/30 |
| Claude Code: custom vs out-of-the-box | 30 | -0.0% | [-5.6%, +6.7%] | [-7.8%, +8.9%] | 2 / 3 | 1.35× | [1.12, 1.64] | [1.10, 1.80] | 1.29 [1.10, 1.57] | 26/30 |

Published Sol Codex vs Pi: cost ratio 1.81× [1.47, 2.27], costlier on 29/30 tasks, median 1.69; success diff -4.4% [-12.2%, +1.1%], wins 1/3, same 26 — labelled "descriptive … no confirmatory test".

## Per-task config effect (custom − out-of-the-box success; custom ÷ out-of-the-box cost)

| Task | Codex Δ | Codex × | Pi Δ | Pi × | Claude Code Δ | Claude Code × |
|---|---|---|---|---|---|---|
| `bn-fit-modify` | +0.00 | 0.99 | +0.00 | 2.32 | +0.00 | 1.10 |
| `cancel-async-tasks` | +0.00 | 1.54 | +0.00 | 2.50 | +0.00 | 1.46 |
| `compile-compcert` | +0.00 | 1.23 | +0.00 | 1.50 | +0.00 | 1.08 |
| `crack-7z-hash` | +0.00 | 0.96 | +0.00 | 1.25 | +0.00 | 1.49 |
| `custom-memory-heap-crash` | +0.00 | 0.94 | +0.00 | 1.63 | +0.00 | 0.91 |
| `db-wal-recovery` | +0.33 | 0.92 | -0.67 | 1.82 | +0.33 | 0.77 |
| `dna-assembly` | +0.33 | 1.64 | +0.00 | 1.57 | +0.00 | 2.89 |
| `extract-elf` | +0.33 | 0.87 | +0.00 | 1.71 | +0.67 | 1.30 |
| `extract-moves-from-video` | +0.67 | 1.17 | -0.33 | 1.48 | +0.00 | 0.24 |
| `filter-js-from-html` | +0.00 | 0.81 | +0.00 | 1.61 | +0.00 | 1.29 |
| `financial-document-processor` | +0.00 | 0.77 | -0.33 | 1.27 | -0.33 | 1.26 |
| `fix-ocaml-gc` | +0.00 | 1.04 | +0.00 | 2.45 | +0.00 | 1.01 |
| `git-multibranch` | +0.00 | 0.92 | +0.00 | 2.18 | +0.00 | 1.53 |
| `headless-terminal` | +0.00 | 1.34 | +0.00 | 1.66 | +0.00 | 1.58 |
| `install-windows-3.11` | +0.00 | 0.90 | +0.00 | 1.02 | +0.00 | 4.02 |
| `make-doom-for-mips` | +0.00 | 0.86 | -0.67 | 1.30 | +0.00 | 0.99 |
| `merge-diff-arc-agi-task` | +0.00 | 1.16 | +0.00 | 1.68 | +0.00 | 1.16 |
| `mteb-leaderboard` | +0.00 | 2.06 | +0.00 | 1.17 | -0.33 | 5.81 |
| `multi-source-data-merger` | +0.00 | 1.27 | +0.00 | 1.69 | +0.00 | 1.14 |
| `openssl-selfsigned-cert` | +0.00 | 1.16 | +0.00 | 3.06 | +0.00 | 1.64 |
| `overfull-hbox` | +0.00 | 0.59 | +0.33 | 1.85 | -0.33 | 1.38 |
| `polyglot-c-py` | +0.33 | 1.07 | +0.00 | 2.37 | +0.00 | 1.73 |
| `protein-assembly` | +0.00 | 0.99 | +0.00 | 1.32 | +0.00 | 1.42 |
| `prove-plus-comm` | +0.00 | 0.98 | +0.00 | 1.84 | +0.00 | 1.07 |
| `regex-chess` | +0.00 | 1.30 | +0.00 | 1.38 | +0.00 | 1.15 |
| `reshard-c4-data` | +0.00 | 1.28 | +0.00 | 1.49 | +0.00 | 1.18 |
| `sparql-university` | +0.00 | 0.78 | +0.00 | 2.08 | +0.00 | 1.48 |
| `sqlite-db-truncate` | +0.00 | 1.13 | +0.00 | 1.83 | +0.00 | 2.15 |
| `sqlite-with-gcov` | +0.00 | 1.34 | +0.00 | 1.52 | +0.00 | 1.61 |
| `train-fasttext` | +0.33 | 0.83 | -0.33 | 1.24 | +0.00 | 1.11 |

## Cost calibration — shared tasks, our task-mean cost vs HarnessTax's published per-task cost (Sol · Pi, Sol · Codex, out-of-the-box)

| Task | Pi ours | Pi theirs | Codex ours | Codex theirs | Pi pass ours | Codex pass ours |
|---|---|---|---|---|---|---|
| `compile-compcert` | $0.616 | $0.922 | $1.955 | $2.639 | 1.00 | 1.00 |
| `financial-document-processor` | $0.425 | $0.461 | $0.619 | $0.763 | 1.00 | 1.00 |
| `headless-terminal` | $0.254 | $0.171 | $0.240 | $0.248 | 1.00 | 1.00 |
| `make-doom-for-mips` | $2.148 | $2.465 | $5.049 | $4.223 | 0.67 | 0.67 |
| `merge-diff-arc-agi-task` | $0.170 | $0.151 | $0.218 | $0.307 | 1.00 | 1.00 |
| `multi-source-data-merger` | $0.067 | $0.068 | $0.137 | $0.136 | 1.00 | 1.00 |
| `openssl-selfsigned-cert` | $0.050 | $0.059 | $0.124 | $0.170 | 1.00 | 1.00 |
| `reshard-c4-data` | $0.348 | $0.376 | $0.509 | $0.600 | 1.00 | 1.00 |
| `sparql-university` | $0.107 | $0.105 | $0.242 | $0.271 | 1.00 | 1.00 |
| `sqlite-db-truncate` | $0.067 | $0.092 | $0.143 | $0.165 | 1.00 | 1.00 |
| `train-fasttext` | $0.655 | $0.634 | $2.295 | $3.062 | 0.67 | 0.33 |

Geometric mean of ours ÷ theirs over the 11 shared tasks: Pi 0.94×, Codex 0.86×. Same tasks, same model, same harness at the paper's version; differences are run variance, price schedule and our per-trial sampling.

## Trial accounting

| Cell | - | AgentTimeoutError | ApiRateLimitError | ApiUsageLimitError | OutputTokenExceededError | TurnCapTruncated |
|---|---|---|---|---|---|---|
| Codex out-of-the-box | 82 | 2 | 0 | 1 | 0 | 5 |
| Codex custom | 86 | 3 | 0 | 0 | 0 | 1 |
| Pi out-of-the-box | 84 | 6 | 0 | 0 | 0 | 0 |
| Pi custom | 82 | 8 | 0 | 0 | 0 | 0 |
| Claude Code out-of-the-box | 71 | 16 | 2 | 0 | 1 | 0 |
| Claude Code custom | 71 | 15 | 1 | 0 | 3 | 0 |
Sensitivity, Codex out-of-the-box without the post-hoc truncation (verifier verdicts as returned): success 82.2%.
Sensitivity, Codex custom without the post-hoc truncation (verifier verdicts as returned): success 85.6%.

Codex trials past 100 model calls, truncated there post hoc (tokens to call 100; counted as failures; verifier verdict on the full run shown): [('custom-codex', 'train-fasttext', 1, 107, 'solved'), ('oob-codex', 'extract-moves-from-video', 1, 115, 'solved'), ('oob-codex', 'train-fasttext', 1, 103, 'solved'), ('oob-codex', 'extract-moves-from-video', 2, 112, 'solved'), ('oob-codex', 'make-doom-for-mips', 3, 101, 'solved'), ('oob-codex', 'train-fasttext', 3, 129, 'solved')]. Claude Code trials ending exactly at the 100-turn cap: [('custom-cc', 'install-windows-3.11', 2, 100)].

Trials with a null reward (verifier returned no verdict), counted as failures: [('custom-pi', 'extract-moves-from-video', 3)].

