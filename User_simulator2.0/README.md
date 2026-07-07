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
- historical dialogue behavior mining

The current priority is not perfect prompt accuracy. The priority is validating that a fully LLM-driven modular pipeline can run end to end with JSON outputs, Pydantic validation, and saved intermediate artifacts.

## Configure LLM

Edit `config.yaml` or set environment variables. The default config follows the mentor-provided OpenAI SDK-compatible qwen3 API:

```bash
export LLM_BASE_URL=http://10.67.43.7:12345/v1
export LLM_API_KEY=sk-1234
export LLM_MODEL=qwen3
```

The client uses the OpenAI SDK style:

```python
from openai import OpenAI

client = OpenAI(api_key="sk-1234", base_url="http://10.67.43.7:12345/v1")
completion = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "..."}],
)
```

Install dependencies if needed:

```bash
pip install -r requirements.txt
```

## Run Demo

The recommended workflow is staged. Do not run the full case-analysis pipeline every time you want one simulation.

```bash
cd User_simulator2.0
python main.py mine-behavior --max_dialogues 20
python main.py analyze-cases --limit 20
python main.py simulate --case_id <真实案例ID> --persona low_tech
```

Case data is loaded from the configured real case library path in `config.yaml`. `case_id` is only the target-case selector inside that library, not a replacement for the case library path.

To inspect available case ids first:

```bash
python main.py simulate --list_cases 20
```

Legacy direct invocation is still supported:

```bash
python main.py --case_id <真实案例ID> --persona low_tech
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

## Historical Dialogue Behavior Mining

Historical dialogues are used to learn user behavior, not to generate case knowledge or replace the roadmap.

Run:

```bash
python main.py mine-behavior
```

By default, the command reads the real historical dialogue path from `config.yaml`:

```yaml
paths:
  dialogues: "../../RUNTIME/raw_data/格式化对话记录/用户和坐席交互09-proceed-full.json"
```

You can override the path:

```bash
python main.py mine-behavior --dialogues /path/to/dialogues.jsonl --max_dialogues 50
```

It writes:

- `outputs/dialogue_behavior_summaries.jsonl`
- `outputs/employee_personas.jsonl`
- `outputs/user_behavior_taxonomy.jsonl`

Runtime priority:

1. Roadmap and Knowledge Module factual constraints decide what content is allowed.
2. Dialogue state decides repetition, patience, and stop state.
3. Behavior taxonomy decides reaction type.
4. Employee persona shapes natural wording.

Simulation can use mined personas:

```bash
python main.py simulate --case_id <真实案例ID> --persona_id persona_xxx
```

If `--persona_id` is omitted and `outputs/employee_personas.jsonl` exists, the first mined persona is used. If no mined persona exists, the simulator falls back to the manual seed persona in `data/manual_seed_employee_personas.jsonl`.

To force the manual seed persona:

```bash
python main.py simulate --case_id <真实案例ID> --persona_id persona_real_problem_low_tech
```

## Batch Case Analysis

Case analysis is an offline preprocessing step. It builds reusable artifacts for each target case:

```bash
python main.py analyze-cases --limit 20
```

Analyze a different sequential batch:

```bash
python main.py analyze-cases --limit 20 --offset 20
```

Randomly sample cases:

```bash
python main.py analyze-cases --limit 20 --random --seed 42
```

Or select exact cases:

```bash
python main.py analyze-cases --case_ids <CASE_ID_1> <CASE_ID_2>
```

It writes:

- `outputs/blind_user_case_views.jsonl`
- `outputs/knowledge_roadmaps.jsonl`

These two final artifact files are upserted by `case_id`: newly analyzed cases are added, repeated cases are replaced, and unrelated old cases are preserved.

`blind_user_case_views.jsonl` is the only case-analysis file that should be considered visible to Blind User. It contains:

- case id
- surface problem
- opening intent
- user-facing points
- forbidden content

`knowledge_roadmaps.jsonl` is for Knowledge Module and runtime control. It contains:

- retrieval queries
- related cases
- verified points
- relations
- roadmap

`simulate` reads `knowledge_roadmaps.jsonl`. If the selected case has not been analyzed yet, `simulate` stops and tells you to run `analyze-cases` first.

## Export Human-Readable Review

JSONL outputs are optimized for code, not manual review. Export Markdown review files with:

```bash
python main.py export-review --case_id <真实案例ID>
```

Or export all analyzed cases:

```bash
python main.py export-review --all
```

Files are written to:

```text
outputs/review/
```

The export includes Blind User visible content, knowledge roadmap, diagnostic/solution/external points, related cases, retrieval queries, warnings, and behavior assets.

## Related Case Retrieval

The case library can be very large, so `analyze-cases` does not send the full library to the LLM.

Current flow:

```text
full case library
  -> local fast candidate recall top 50
  -> LLM selects final related cases top 5
```

The local recall step is only candidate narrowing. It does not make the final related-case decision. The final selection is still made by the LLM.

This is close to a reverse-RAG shape: each case is treated as a retrieval document, the target case is converted into several retrieval directions by the LLM, local retrieval recalls likely candidate documents, and the LLM then reranks/selects useful related cases.

## Outputs

All intermediate results are saved as JSONL records under `outputs/`.

- `generated_queries.jsonl`: reverse RAG retrieval queries
- `related_cases.jsonl`: locally recalled candidates and LLM selected related cases
- `points.jsonl`: extracted knowledge points
- `verified_points.jsonl`: verified and dropped points
- `relations.jsonl`: point relations
- `roadmaps.jsonl`: assembled roadmaps
- `blind_user_case_views.jsonl`: safe per-case view for Blind User
- `knowledge_roadmaps.jsonl`: complete per-case roadmap for Knowledge Module/runtime
- `simulation_logs.jsonl`: runtime turn logs
- `dialogue_behavior_summaries.jsonl`: per-dialogue behavior summaries
- `employee_personas.jsonl`: mined employee persona library
- `user_behavior_taxonomy.jsonl`: mined user behavior taxonomy

Each record contains `case_id`, `module`, `input`, `output`, and `timestamp`.

## Tests

Tests use `MockLLMClient` only as a deterministic test double:

```bash
python -m pytest tests
```

Historical behavior outputs are product files rather than wrapped step logs, so each JSONL line is a persona, taxonomy item, or dialogue summary.
