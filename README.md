# Enterprise User Simulator

Phase-1 implementation for an enterprise knowledge-QA user simulator.

The first phase is intentionally lightweight:

- normalize historical customer-service dialogues into turn lists;
- extract a goal/profile/state seed from each dialogue;
- simulate multi-turn user behavior with a controllable state machine;
- run automatic conversations against a mock or real QA system;
- export structured metrics for debugging retrieval, clarification, and answer failures.

No third-party dependency is required for the local MVP.

## Quick Start

```bash
python3 -m src.pipelines.build_goal_bank \
  --input data/samples/dialogues.sample.jsonl \
  --cases data/samples/cases.sample.jsonl \
  --output outputs/goal_bank.sample.jsonl

python3 -m src.pipelines.run_simulation \
  --goal-bank outputs/goal_bank.sample.jsonl \
  --output outputs/simulation.sample.jsonl
```

## Enable LLM Extraction and Rewriting

By default the project uses deterministic mock/rule logic, so no API key is required.

For an OpenAI-compatible internal model service, set an API key and pass the endpoint:

```bash
export LLM_API_KEY="your-key"

python3 -m src.pipelines.build_goal_bank \
  --input data/samples/dialogues.sample.jsonl \
  --cases data/samples/cases.sample.jsonl \
  --output outputs/goal_bank.llm.jsonl \
  --llm-provider openai-compatible \
  --llm-base-url https://your-llm-host \
  --llm-model your-model-name

python3 -m src.pipelines.run_simulation \
  --goal-bank outputs/goal_bank.llm.jsonl \
  --output outputs/simulation.llm.jsonl \
  --llm-provider openai-compatible \
  --llm-base-url https://your-llm-host \
  --llm-model your-model-name
```

The state machine still decides what information the user should reveal. The LLM only improves:

- goal/profile extraction from historical dialogues;
- natural rewriting of each user utterance.

## Case-Grounded Route

The recommended input is:

- `cases.jsonl`: the answer seed, including `case_id`, `title`, `phenomenon`, and `solution`;
- `dialogues.jsonl`: real historical conversations whose `resolution.case_id` points to the target case.

`build_goal_bank` joins them by `case_id`:

```bash
python3 -m src.pipelines.build_goal_bank \
  --input data/processed/dialogues.normalized.jsonl \
  --cases data/processed/cases.normalized.jsonl \
  --output outputs/goal_bank.case_grounded.jsonl
```

This route learns how users ask questions for a known answer seed instead of replaying the answer itself.

## Run Original V1 Simulator on Current Roadmaps

To compare the original V1 simulator with the newer simulator using the same evaluation system, keep V1 changes in this main-branch code path and feed it the current `knowledge_roadmaps.jsonl`.

The V1 runner converts each roadmap into the original `UserGoalSeed` shape, runs `src.simulator.runtime.EnterpriseUserSimulator`, calls the real assistant API, and writes an evaluator-compatible `simulation_logs.jsonl`.

```bash
python3 -m src.pipelines.run_roadmap_api_simulation \
  --roadmaps outputs_v1/knowledge_roadmaps.jsonl \
  --output outputs_v1/v1_roadmap_api_simulation.jsonl \
  --simulation-log-output outputs_v1/simulation_logs.jsonl \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --assistant-config assistant_config.yaml \
  --max-turns 15
```

Use the same assistant API settings as the newer simulator config. `assistant_config.yaml` is a local copy of the newer simulator's `assistant:` section, so the V1 runner does not need to read files from the newer simulator directory. Command-line API flags are still available as temporary overrides.

Optional LLM rewriting for V1 user utterances:

```bash
python3 -m src.pipelines.run_roadmap_api_simulation \
  --roadmaps outputs_v1/knowledge_roadmaps.jsonl \
  --output outputs_v1/v1_roadmap_api_simulation.jsonl \
  --simulation-log-output outputs_v1/simulation_logs.jsonl \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --assistant-config assistant_config.yaml \
  --llm-provider openai-compatible \
  --llm-base-url https://your-llm-host \
  --llm-model your-model-name \
  --max-turns 15
```

The compatible log uses `module = "Simulator.step"` and `simulator_variant = "v1_enterprise_user_simulator"`, so the current evaluator can read it as long as the output directory also contains the same `knowledge_roadmaps.jsonl`.

Evaluate the V1 output from the original simulator repo root:

```bash
python3 scripts/evaluate_llm_primary_simulator.py \
  --config case_dialogue_mining/config.yaml \
  --llm-config judge_config.yaml \
  --output-dir outputs_v1 \
  --dialogues data/processed/dialogues.normalized.jsonl \
  --case-ids-file outputs/real_dialogue_case_ids.txt \
  --session-policy latest
```

The root script reuses the current LLM-primary evaluator implementation under
`User_simulator2.0/`, but it reads the V1 files in the old repo layout.
`--config` should point to the old data/path config. `--llm-config` points to
the copied current judge-service config in this repo, so V1 and the newer
simulator use the same LLM judge. You can also set `LLM_BASE_URL`, `LLM_MODEL`,
and optionally `LLM_API_KEY` in the environment.
Use `--case-ids KT001 KT002` instead of `--case-ids-file ...` when you only
want to evaluate a small subset.

## Run LLM-Primary User-Conditioned Evaluation

This newer evaluator does not overwrite the existing `simulator_eval/` outputs. It writes to `simulator_eval_llm_primary/` and treats rule checks as evidence only. Final scores come from the LLM judge.

The evaluator focuses on the simulated user rather than the assistant:

- conditional user behavior given each assistant reply
- goal alignment
- anti-overcooperation
- RealSim-style user behavior
- user-only C2ST/discriminability using user messages only
- solution-conditioned leakage-aware response, with assistant failure marked as confounding instead of directly penalizing the simulator

```bash
python3 scripts/evaluate_llm_primary_simulator.py \
  --config case_dialogue_mining/config.yaml \
  --output-dir output714 \
  --dialogues data/processed/dialogues.normalized.jsonl \
  --case-ids-file output714/real_dialogue_case_ids.txt \
  --session-policy latest
```

If the config already contains `paths.output_dir` and `paths.dialogues`,
`--output-dir` and `--dialogues` can be omitted. You can also pass
`--dialogues <real_dialogue_file>` directly when evaluating an exported output
folder. The command is intentionally run from the repo root so the same entry
point works for V1 outputs and newer exported outputs.
