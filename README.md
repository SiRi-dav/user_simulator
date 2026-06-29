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
python3 -m enterprise_user_simulator.src.pipelines.build_goal_bank \
  --input enterprise_user_simulator/data/samples/dialogues.sample.jsonl \
  --output enterprise_user_simulator/outputs/goal_bank.sample.jsonl

python3 -m enterprise_user_simulator.src.pipelines.run_simulation \
  --goal-bank enterprise_user_simulator/outputs/goal_bank.sample.jsonl \
  --output enterprise_user_simulator/outputs/simulation.sample.jsonl
```

