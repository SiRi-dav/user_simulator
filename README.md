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
  --assistant-config User_simulator2.0/config.yaml \
  --max-turns 15
```

Use the same assistant API settings as the newer simulator config. `--assistant-config` reads the `assistant:` section, including `base_url`, `policy_base_url`, `response_base_url`, and custom endpoint paths. Command-line API flags are still available as temporary overrides.

Optional LLM rewriting for V1 user utterances:

```bash
python3 -m src.pipelines.run_roadmap_api_simulation \
  --roadmaps outputs_v1/knowledge_roadmaps.jsonl \
  --output outputs_v1/v1_roadmap_api_simulation.jsonl \
  --simulation-log-output outputs_v1/simulation_logs.jsonl \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --assistant-config User_simulator2.0/config.yaml \
  --llm-provider openai-compatible \
  --llm-base-url https://your-llm-host \
  --llm-model your-model-name \
  --max-turns 15
```

The compatible log uses `module = "Simulator.step"` and `simulator_variant = "v1_enterprise_user_simulator"`, so the current evaluator can read it as long as the output directory also contains the same `knowledge_roadmaps.jsonl`.

Evaluate the V1 output with the copied current evaluator:

```bash
cd User_simulator2.0

python3 scripts/evaluate_current_simulator.py \
  --output-dir ../outputs_v1 \
  --dialogues ../data/processed/dialogues.normalized.jsonl \
  --case-ids-file ../outputs/real_dialogue_case_ids.txt \
  --session-policy latest \
  --judge
```

Without `--judge`, the evaluator runs diagnostic rule metrics only. With `--judge`, it uses the current LLM-judge-primary scoring system.
