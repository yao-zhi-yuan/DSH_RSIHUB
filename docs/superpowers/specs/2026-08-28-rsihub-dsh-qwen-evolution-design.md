# RSIHub + DSH + Qwen First Evolution Design

## Goal

Run one auditable Hill Climb experiment over 16 synthetic coding tasks using
only local Ollama inference. DSH uses `qwen3:8b` as the evaluated agent,
`qwen3:14b` proposes bounded prompt-only candidates, and RSIHub records a
certified baseline, three generations, Gate decisions, baseline and final
Sealed evaluations, resource usage, and conclusions.

The experiment succeeds only when every required evaluation is scoreable and
the resulting report can be traced to immutable candidate, evaluator, dataset,
runtime, and model identities.

## Scope

The work includes:

- repairing and validating the 16-task synthetic dataset;
- making the DSH target configuration boot reliably;
- supplying useful, redacted DSH execution evidence to the mutator;
- recording target and mutator token and wall-time usage;
- validating the local Ollama daemon and exact model identities;
- initializing a fresh RSIHub workspace after all frozen inputs are ready;
- running baseline, three generations, and Sealed evaluations;
- producing a compact report with links and hashes for raw evidence.

Only `target/prompt.md` may evolve. The DSH adapter, Ollama route, task set,
verifiers, RSIHub operators, split manifest, and runtime limits remain frozen
within an experiment.

This first run does not attempt to evolve DSH source code, add multiple
children per generation, compare search algorithms, or generalize beyond the
16 synthetic tasks.

## Repository Boundaries

The outer repository owns reproducible experiment inputs:

- `config/`: pinned upstream and DSH configuration.
- `patches/`: auditable changes applied to pinned RSIHub.
- `recipes/`: the Hill Climb configuration.
- `scripts/`: dataset validation, Ollama probes, mutation, usage extraction,
  experiment orchestration, and report generation.
- `seed/`: the immutable starting adapter, DSH patch, and prompt.
- `tasks/synthetic-16/`: the complete benchmark source.
- `tests/`: local regression and contract tests for the experiment tooling.
- `docs/`: design, runbook, and final report.

`vendor/` remains a pinned source checkout and must be reproducible from
`config/upstream-lock.json` plus files under `patches/`. The published
`@deepseek-ai/dsh@0.1.1-rc.2` package remains the executed DSH runtime; the
vendored DSH checkout is reference source.

Initialized RSIHub workspaces and raw run directories remain generated state.
The final report records their identity, selected files, and SHA-256 manifest
without committing credentials or hundreds of megabytes of duplicated
workspaces.

## Experiment Contract

### Dataset

The dataset contains four task families with four tasks each:

- contract;
- verification;
- execution;
- artifact.

The fixed seed `17` partitions the tasks into eight Train, four Gate, and four
Sealed tasks. Task content is immutable after workspace initialization.

Before initialization, a dataset audit must:

1. parse every Python file;
2. parse every `task.toml`;
3. validate the required Harbor directory and executable layout;
4. execute visible tests against the intentionally broken seed and record the
   expected pass/fail result;
5. execute each verifier against both the broken seed and a generated
   known-good solution, requiring the former to score zero and the latter one;
6. reject inconsistent expected values, verifier crashes, and missing reward
   files;
7. write a machine-readable audit containing task hashes and results.

The known defects in `execution-safe-relative-path`,
`verification-jsonl-summary`, and `artifact-required-result` must be corrected
in the generator and regenerated task trees before freezing a new dataset.

### Models

- Evaluated target: local Ollama model `qwen3:8b`.
- Candidate generator: local Ollama model `qwen3:14b`.
- Both roles use Ollama's OpenAI-compatible endpoint at
  `http://127.0.0.1:11434/v1`.
- Before initialization, the runner verifies the Ollama daemon, records its
  version, confirms both exact tags are installed, captures each model digest
  and size, and probes the target tool-call and mutator JSON contracts.
- Returned model identifiers must match the configured tags.
- The `qwen3:8b` target must pass three consecutive read-edit-test, multi-turn
  tool-call canaries before its baseline is considered runnable.

There is no monetary or token quota in this experiment. Failures to connect to
Ollama, missing models, or local resource exhaustion are infrastructure
failures and stop the current stage without automatic retries.

There is no automatic model fallback. A failed target canary blocks this
experiment because changing the target changes the runtime identity. Any later
target change requires explicit approval and a new workspace; 7B and 30B
models are outside this experiment.

### Search

The method is single-frontier Hill Climb:

1. certify generation zero on Gate;
2. evaluate generation zero on Sealed as a non-selectable anchor;
3. for generations 1 through 3, select the current champion;
4. execute four Train rollouts;
5. analyze retained DSH behavior and verifier evidence;
6. ask Qwen Max for one general prompt change;
7. enforce the prompt-only mutation surface;
8. evaluate the candidate on the fixed Gate set;
9. accept a non-regression (`child_score >= parent_score`);
10. record accepted and rejected candidates;
11. evaluate the final champion on Sealed.

With one attempt and no early failure, this is 36 target task trials:
8 baseline trials, 24 generation trials, and 4 final Sealed trials. A rejected
candidate still consumes its Train and Gate trials. The final Sealed evaluation
is skipped only when the final champion is unchanged generation zero and its
existing Sealed anchor is still certified.

## Execution Boundary

The formal evaluator uses RSIHub's Docker backend. A pinned base image contains
Node 24, Python 3, and `@deepseek-ai/dsh@0.1.1-rc.2`; each task image contains
only its public environment during the agent phase. The container reaches the
host Ollama daemon through `host.docker.internal`.

- the target process receives an explicit allowlist of environment variables;
- no remote API credential is supplied to target or mutator processes;
- the sanitized `PATH` must resolve the pinned container Node 24 executable
  before DSH starts;
- task execution starts in the staged `/app` mapping;
- a canary proves DSH cannot read the sibling verifier directory or the source
  dataset through its file and shell tools;
- any failed isolation canary blocks the formal experiment.

The report records the evaluator image ID and describes both the container
boundary and DSH's nested write sandbox. A missing image, unavailable Docker
daemon, or failed confidentiality canary blocks formal scoring.

The recipe keeps `n_concurrent: 2`. Ollama must be started with
`OLLAMA_NUM_PARALLEL=2`; on macOS this server setting is applied before
restarting the Ollama app after model downloads. Preflight rejects a mismatch
instead of relying on queueing behavior.

## Evidence Flow

Each DSH trial retains:

- the exact instruction and task identity;
- DSH session JSONL;
- tool calls and tool results in order;
- final assistant response;
- target-model token usage;
- start, finish, and wall time;
- verifier output and binary reward;
- sanitized failure classification.

A deterministic adapter converts DSH session events into the event structure
consumed by RSIHub trace analysis. It must preserve event order and redact
credential values, authorization headers, endpoint URLs, and sensitive
environment values.

The analyze stage writes aggregate metrics, failure patterns, passing
behaviors, and selected evidence. The mutate stage receives the selected
evidence content directly; it must not depend on discovering an implicit path
inside a summary string.

Each mutation records:

- the exact evidence files and hashes used;
- the mutator request policy;
- hypothesis and expected effect;
- token usage and wall time;
- model output;
- candidate patch;
- surface-check result.

## Resource Accounting

Resource accounting is based on local Ollama and process evidence:

- target input, output, and cache tokens are summed from retained DSH session
  events;
- mutator prompt and completion tokens are parsed from its Ollama response;
- wall time is recorded per trial, operator, generation, and complete run;
- request counts and terminal Ollama statuses are counted by model role;
- Ollama version, model digests, model sizes, and processor placement are
  captured;
- host wall time and retained-artifact disk use are reported;
- monetary cost is fixed to zero because no remote paid endpoint is used.

## Environment And Identity

A repository launcher loads the outer `.env`, validates the local Ollama URL
and exact model tags, exports only the explicit target/mutator/runtime
allowlist, computes the runtime digest, and invokes RSIHub. The committed
`.env.example` contains local defaults and no credentials.

All frozen inputs must be clean before initialization:

- the repaired task dataset and its audit;
- the seed candidate including the DSH plugin fix;
- the Qwen mutator and evidence adapter;
- the RSIHub patches;
- the package and Python lockfiles;
- the exact model identifiers and execution policy.

The failed historical `experiment/` is preserved. The formal run uses a new
workspace directory and a new experiment ID so its archive mirror, tags,
runtime pin, and dataset pin cannot be confused with failed evidence.

## Failure Handling

- Dataset, syntax, contract, isolation, identity, or environment failures stop
  before model use.
- Ollama connection failures, missing model tags, malformed responses, and
  local resource exhaustion stop the experiment as infrastructure failures.
- Target process failures before a model response are infrastructure failures,
  never score zero.
- Verifier crashes are benchmark failures, never candidate failures.
- Missing or malformed usage records block the audit report.
- No failed model stage retries automatically.
- Existing run artifacts are immutable; reruns use a new attempt or workspace
  identity.

## Verification Strategy

Implementation follows test-first development:

1. regression tests reproduce every known dataset defect;
2. unit tests cover session event extraction, redaction, aggregation, and
   mutator usage parsing;
3. contract tests prove all 16 tasks have valid visible and hidden tests and a
   known-good solution scores one;
4. configuration tests prove only `target/prompt.md` can mutate and all resource
   limits are wired;
5. model-free RSIHub smoke proves baseline, Train, mutation stub, Gate, record,
   and Sealed transitions;
6. one live target and one live mutator Ollama probe validate model contracts;
7. one live end-to-end canary validates DSH boot, tool execution, verification,
   evidence extraction, and accounting;
8. the formal run proceeds only after all earlier gates pass.

## Deliverables

The final bundle contains:

- baseline Gate and Sealed scores;
- three generation records and parent-child decisions;
- exact prompt diffs for every candidate;
- per-task Gate and Sealed results;
- retained, redacted DSH trajectories;
- target and mutator token totals, request counts, wall time, and disk use;
- runtime, dataset, task-set, candidate, and artifact hashes;
- accepted and rejected candidate history;
- a limitations section covering synthetic-task scope, local execution, sample
  size, stochasticity, and host resource contention;
- one concise conclusion limited to what the frozen evidence supports.

The goal is complete only when RSIHub verification passes, all expected
generations are terminal, Gate and Sealed evidence is complete, and the report
can be regenerated from retained artifacts without making model calls.
