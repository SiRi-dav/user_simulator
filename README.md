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
