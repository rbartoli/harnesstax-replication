# harnesstax-replication

> Berkeley's HarnessTax study, rerun on 30 Terminal-Bench 2.0 tasks, plus what a lived-in coding agent config costs on top of the bare harness.

[HarnessTax](https://harnesstax.github.io/) (Berkeley Sky Lab, September 2026) found that the harness barely moves a coding agent's success, but moves its cost a lot. This repo reruns their protocol on a different task sample, on ChatGPT Plus and Claude Max subscriptions instead of API keys, and adds what the study left out: the same harness with my own config loaded (CLAUDE.md or AGENTS.md, rules, skills, agents, commands, plugins and hooks).

The write-up: [What My Coding Agent Config Costs on Every Call](https://rblab.com/what-my-coding-agent-config-costs-on-every-call/).

## Results

Same model, same 30 tasks, three runs each, paired by task. The cost ratio is the geometric mean of the per-task ratios.

| Pair | Success, A − B | Cost, A ÷ B (95% CI) | A costs more on |
|---|---|---|---|
| Codex CLI vs Pi, out of the box, GPT-5.6 Sol (published: 1.81×) | −6.7 points | **1.72×** (1.32–2.10) | 27 of 30 tasks |
| Pi, my config vs out of the box | −6.7 points | **1.67×** (1.53–1.83) | 30 of 30 |
| Claude Code, my config vs out of the box (Sonnet 4.6) | 0.0 points | **1.35×** (1.12–1.64) | 26 of 30 |
| Codex CLI, my config vs out of the box | +7.8 points | 1.06× (0.97–1.16) | 15 of 30 |

The config tax follows how many tokens the config adds to the first call: 9.9k on Pi's 1.3k, 8.8k on Claude Code's 22.2k, 1.8k on Codex's 13.3k. It is paid again on every call, through cache reads and a larger cache write. The Claude Code cells leave out my MCP servers, which add about 22k more tokens, so 1.35× is a floor.

Every cell, with intervals, pass^3, timeouts and the calibration against the paper's per-task costs, is in [`data/stage4/summary.md`](data/stage4/summary.md). One row per trial, 540 rows: [`data/stage4/ledger.tsv`](data/stage4/ledger.tsv).

## Measure your own first call

You don't need the benchmark to see your own config tax. Ask for a one-word reply with your config loaded and without it, and compare the size of the first call: uncached input, plus cache writes, plus cache reads. For Claude Code, run this from an empty folder, so no project CLAUDE.md loads:

```sh
claude -p "Reply with exactly: OK" --output-format json \
  | jq '.usage | .input_tokens + .cache_creation_input_tokens + .cache_read_input_tokens'
```

For the bare figure, run it again with an empty config directory, logged in with a token from `claude setup-token`:

```sh
CLAUDE_CONFIG_DIR=$(mktemp -d) CLAUDE_CODE_OAUTH_TOKEN=<token> \
  claude -p "Reply with exactly: OK" --output-format json \
  | jq '.usage | .input_tokens + .cache_creation_input_tokens + .cache_read_input_tokens'
```

The difference, times the model calls in a typical task, is roughly what your config adds to each task.

## What's here

```
agents/    Harbor agent subclasses: config injection for the custom cells, Pi on ChatGPT, Pi's turn cap
scripts/
  cells.sh            runs one cell on a set of tasks
  stage3.sh           the driver: 30 tasks × 3 runs × 6 cells, paced to subscription limits, resumable
  first_call.py       one ledger row per trial: tokens by kind, first-call size, turns, wall time
  stage4.py           the analysis: ledger.tsv and summary.md
  snapshot-config.sh  freezes the configs under test
tasks/     the 30-task sample and its seed, the exclusions, a smoke-test task
data/
  stage4/        ledger.tsv and summary.md
  logs/s3.log    the driver's log for the 540 runs
```

Not here: the per-trial transcripts (647 MB) and the config snapshot. The transcripts quote the config, and the config is mine, so the write-up describes it by shape, in counts and token sizes. `stage4.py` shows how the ledger and the summary come from the transcripts. The scripts are as run, with one change: `cells.sh` reads the Claude token from the environment instead of my password manager. In `s3.log`, my home directory reads `~`.

## Method

- Terminal-Bench 2.0 through Harbor 0.23.0. 30 tasks drawn with `random.Random(20261001)` from the 85 whose reference solutions pass (`tasks/stage3-tasks.txt`), three runs per task in each cell, all of run 1 before run 2. The number of runs was fixed before the start: no early stop, no extra runs.
- Six cells, at the paper's harness versions and high effort: Codex CLI 0.146.0 and Pi 0.85.1 on GPT-5.6 Sol (ChatGPT Plus), and Claude Code 2.1.224 on Sonnet 4.6 (Claude Max), each out of the box and with my config.
- Out of the box: Harbor's stock adapter in a fresh container, with only the login passed in. With my config: one frozen snapshot (`snapshot-config.sh`, 1 October 2026) placed where each harness reads it, minus MCP servers, model pins, the status line, every credential file and files over 1 MiB.
- Limits: Terminal-Bench's own time limit for each task, and 100 agent turns (`--max-turns` in Claude Code, `agents/turn_cap.ts.tmpl` in Pi, and after the fact in Codex, where six trials ran past 100 calls and count as failures at call 100). A trial that hits either limit is a failure, with its tokens kept, and so is one that hits Claude Code's 32k output cap or a prompt that is too long.
- Redone: three trials killed by API-side errors (capacity, usage limit). One trial in which the agent and the verifier both timed out has no reward and counts as a failure.
- Cost: tokens times the providers' direct API prices in force on 1 September 2026; the table is in `summary.md`. The paper's price schedule is unpublished. On the 11 tasks both samples share, my out-of-the-box costs per task come out at 0.94× (Pi) and 0.87× (Codex) theirs.
- Statistics as published: the mean over a task's three runs, then over tasks; 95% intervals from 10,000 bootstrap resamples of the 30 task means (seed 20261007); the paired cost effect is the geometric mean of the per-task ratios. Added: a bootstrap over tasks and then runs (within a point or two of the task intervals), and pass^3, solved in all three runs. Like the paper's, these figures are descriptive at n = 30, with no confirmatory test.

## Run it

You need Docker, Harbor 0.23.0, and a login for each harness: Codex's and Pi's `auth.json` on the host, and a token from `claude setup-token` for Claude Code. Run one driver at a time: Codex and Pi refresh tokens are single-use.

```sh
export HARNESSTAX_JOBS=~/harnesstax-runs/jobs                # where Harbor writes trials (the default)
export CLAUDE_CODE_OAUTH_TOKEN=<token>                       # Claude Code cells only
scripts/cells.sh oob-pi -p tasks/calib-ok --job-name smoke   # one cell on the smoke-test task

scripts/snapshot-config.sh 2026-10-01                        # freeze your config for the custom cells
export HARNESSTAX_SNAPSHOT=~/harnesstax-runs/snapshot/2026-10-01
scripts/stage3.sh s3                                         # all 540 trials, paced to your limits
python3 scripts/stage4.py "$HARNESSTAX_JOBS" data/stage4     # the ledger and the summary
```

The analysis is pure Python 3, with no dependencies.

## License

[MIT](LICENSE)
