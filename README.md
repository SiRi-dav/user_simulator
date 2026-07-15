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
cd User_simulator2.0

python3 scripts/evaluate_llm_primary_simulator.py \
  --config config.yaml \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt \
  --session-policy latest
```

If the config already contains `paths.output_dir` and `paths.dialogues`, `--output-dir` can be omitted. You can also pass `--dialogues <real_dialogue_file>` directly when evaluating an exported output folder.
