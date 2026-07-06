# User Simulator 2.0

This is an LLM-based Knowledge-grounded User Simulator MVP for enterprise IT support evaluation.

The goal is to simulate a real user around a target support case, interact with an assistant in multiple turns, and judge whether the assistant eventually gives a solution matching the target case.

## Architecture

Runtime has two modules:

- Blind User: talks to the assistant, parses assistant act with an LLM, and renders natural user replies from Knowledge Module instructions.
- Knowledge Module: reads the roadmap, points, relations, dialogue state, and solution points. It decides what the Blind User may reveal, deny, ask, or confirm.

Blind User does not directly read the full solution or full roadmap. It only sees `surface_problem`, `persona`, dialogue history, and `allowed_content` returned by the Knowledge Module.

## Why No Rule-Based MVP

This version intentionally avoids rule-based judging, extraction, matching, and dialogue decisions. All core decisions go through LLM calls:

- related case retrieval query generation
- related case selection
- point extraction
- point verification
- relation building
- roadmap assembly
- assistant act parsing
- knowledge matching and information release decision
- solution matching
- blind user natural language rendering
- initial user opening

The current priority is not perfect prompt accuracy. The priority is validating that a fully LLM-driven modular pipeline can run end to end with JSON outputs, Pydantic validation, and saved intermediate artifacts.

## Configure LLM

Edit `config.yaml` or set environment variables. The default config follows the previous project style and points to qwen32b through an OpenAI-compatible endpoint:

```bash
export LLM_ENDPOINT=http://localhost:8850/v1/chat/completions
export LLM_API_KEY=EMPTY
export LLM_MODEL=qwen3-32b
```

The client is OpenAI-compatible and calls `/chat/completions`.

## Run Demo

```bash
cd User_simulator2.0
python main.py --case_id <真实案例ID> --persona low_tech
```

Case data is loaded from the configured real case library path in `config.yaml`. `case_id` is only the target-case selector inside that library, not a replacement for the case library path.

To inspect available case ids first:

```bash
python main.py --list_cases 20
```

Assistant replies are entered manually for now. The intended real-assistant integration point is marked in `main.py` inside the runtime loop, where `assistant_text = input(...)` currently lives.

When the enterprise assistant is ready, replace that line with the real assistant call and pass `simulator.dialogue_history` plus the latest user message.

Example interaction:

```text
User: 我这边 Outlook 打不开，一点开就退出来了。
Assistant> 是登录不上还是打开就退出？
User: 是打开以后就直接退出来了，还没到登录那一步。
Assistant> 你可以先结束 Outlook 的残留进程再重新打开。
User: 好的，那我按这个方法试一下。
[STOP: solved]
```

## Outputs

All intermediate results are saved as JSONL records under `outputs/`.

- `generated_queries.jsonl`: reverse RAG retrieval queries
- `related_cases.jsonl`: LLM selected related cases
- `points.jsonl`: extracted knowledge points
- `verified_points.jsonl`: verified and dropped points
- `relations.jsonl`: point relations
- `roadmaps.jsonl`: assembled roadmaps
- `simulation_logs.jsonl`: runtime turn logs

Each record contains `case_id`, `module`, `input`, `output`, and `timestamp`.

## Tests

Tests use `MockLLMClient` only as a deterministic test double:

```bash
python -m pytest tests
```

## Future: Dialogue Behavior Miner

Historical dialogue mining is reserved for a later module named Dialogue Behavior Miner. It will analyze how real users open conversations, what they reveal proactively, what they reveal only after being asked, how they react to off-track questions, whether they ask for operation guidance, where low-tech users get stuck, and what they add after one, two, or three turns.

Those results will later affect surface problem prompts, information release prompts, action request policy, and persona behavior policy.
