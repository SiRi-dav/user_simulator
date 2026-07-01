# Case Dialogue Mining

This tool mines case-dialogue pairs and asks a local AI model to summarize how real users ask questions for each case.

The first-stage goal is data mining and analysis, not user simulation runtime.

For a file-by-file code map, see [`PROGRAM_STRUCTURE.md`](PROGRAM_STRUCTURE.md).

## Run With Sample Data

```bash
cd case_dialogue_mining
python3 main.py --config config.sample.yaml
```

Outputs:

- `outputs/case_dialogue_pairs.jsonl`
- `outputs/question_patterns.jsonl`
- `outputs/analysis_errors.jsonl`
- `outputs/summary_report.md`
- `outputs/question_patterns.readable.md`

The upgraded analysis writes a three-block schema:

- `case_understanding`: target case, user-visible problem, likely user goal, required slots, and case-side evidence
- `behavior_model`: user question patterns, known/hidden facts, missing slots, reveal rhythm, and user style
- `simulation_plan`: opening templates, slot reveal plan, simulator actions, stop conditions, and evaluation focus

## Input Contract

Cases should contain answer-side information:

```json
{"case_id":"CASE_001","title":"问题标题","phenomenon":"问题现象","solution":"解决方案"}
```

Dialogues should contain real user-service conversations and a target `case_id`:

```json
{
  "dialogue_id": "DIALOGUE_001",
  "case_id": "CASE_001",
  "turns": [
    {"role": "user", "text": "..."},
    {"role": "agent", "text": "..."}
  ]
}
```

Field names are configured in `config.yaml`.

## Run With CUHKSZTEAM Data

For the current server layout:

```text
/mnt/nas1/users/CuhkszTeam/
  RUNTIME/raw_data/格式化案例库/uniknow-full-text.json
  RUNTIME/raw_data/格式化对话记录/用户和坐席交互09-proceed-full.json
  xirui/case_dialogue_mining/
```

run:

```bash
cd /mnt/nas1/users/CuhkszTeam/xirui/case_dialogue_mining
export LOCAL_AI_API_KEY="EMPTY"
python main.py --config config.yaml
```

`config.yaml` is set for the real keyed JSON format:

- case id is the outer JSON key, for example `KT00412544`;
- case title is `case_name`;
- case text is `text`;
- dialogue id is the outer JSON key;
- dialogue target case is `caseId`;
- dialogue turns are role-prefixed strings in `text`, for example `用户: ...` and `客服: ...`.

The default local AI config uses the Qwen endpoint shown in the server example:

```yaml
local_ai:
  provider: "openai-compatible"
  endpoint: "http://localhost:8850/v1/chat/completions"
  model: "qwen3-32b"
  api_key_env: "LOCAL_AI_API_KEY"
  temperature: 0.3
  max_tokens: 4096
  top_p: 0.5
  presence_penalty: 1.5
  top_k: 1
  enable_thinking: false
```

To avoid sending thousands of requests at once, `analysis.max_cases` limits AI analysis to the top cases by dialogue count:

```yaml
analysis:
  max_cases: 100
```

Set `max_cases: 0` to analyze all matched cases.

For a quick smoke test, override the case count without editing `config.yaml`:

```bash
python main.py --config config.yaml --max-cases 5
```

During AI analysis the script writes checkpoints after every case:

- `outputs/question_patterns.partial.jsonl`
- `outputs/analysis_errors.partial.jsonl`

If a long run is interrupted, resume it with:

```bash
python main.py --config config.yaml --resume-analysis
```

You can inspect partial results before the full run finishes:

```bash
python review_export.py \
  --input outputs/question_patterns.partial.jsonl \
  --output outputs/question_patterns.partial.review.md \
  --jsonl-output outputs/question_patterns.partial.review.masked.jsonl \
  --limit 20
```

If you only want to rebuild pair matching outputs without calling the model, run:

```bash
python main.py --config config.yaml --skip-analysis
```

To create a readable and lightly masked review file from existing AI output:

```bash
python review_export.py --input outputs/question_patterns.jsonl --limit 30
```

This writes:

- `outputs/question_patterns.review.md`
- `outputs/question_patterns.review.masked.jsonl`

## Case-Only Analysis

The long-term simulator should also work for a new case without dialogue history. For that, run case-only analysis:

```bash
python analyze_cases_only.py \
  --config config.yaml \
  --max-cases 20
```

If a few local-model calls time out, rerun with resume enabled. Successful cases are kept and only unfinished cases are retried:

```bash
python analyze_cases_only.py \
  --config config.yaml \
  --max-cases 20 \
  --resume
```

Case-only analysis retries each failed local AI request twice by default. You can tune it:

```bash
python analyze_cases_only.py \
  --config config.yaml \
  --max-cases 20 \
  --resume \
  --retries 4 \
  --retry-delay 10
```

This only reads the case library and asks the local model to infer likely user-side patterns from the case title, phenomenon, and solution.

Outputs:

- `outputs_case_only/question_patterns.case_only.jsonl`
- `outputs_case_only/question_patterns.case_only.readable.md`
- `outputs_case_only/analysis_errors.case_only.jsonl`

The case-only prompt outputs the same three-block schema as `question_patterns.jsonl`, but:

- `behavior_model.observed_from_dialogue` is empty;
- `behavior_model.inferred_from_case` contains the main reasoning basis;
- `behavior_model.dialogue_level_patterns` contains synthetic seeds such as `synthetic_1`, `synthetic_2`, `synthetic_3`;
- `simulation_plan.slot_reveal_plan[].source` uses `case` or `inferred`, not `dialogue`.

## Lightweight Simulator MVP

After `outputs_case_only/question_patterns.case_only.jsonl` is generated, run a first simulator version directly from the case-only patterns:

```bash
python simulate_from_patterns.py \
  --scenario replay_like \
  --limit 20
```

The simulator now defaults to:

```text
outputs_case_only/question_patterns.case_only.jsonl
```

To switch back to case-dialogue mining results, pass:

```bash
python simulate_from_patterns.py \
  --patterns outputs/question_patterns.jsonl \
  --scenario replay_like \
  --limit 20
```

Available evaluation scenarios:

- `replay_like`: baseline scenario close to historical user reveal rhythm
- `vague_user`: sparse-information scenario that forces clarification
- `difficult_user`: stress-test scenario with more confusion and post-solution friction

The simulator now follows two lines:

- `case-dialogue pair grounding`: controls the target `case_id`, known facts, hidden slots, and reveal plan
- `persona / behavior`: controls how the user speaks, how cooperative they are, and how quickly they reveal information

By default the simulator picks a stable persona automatically for each case. To inspect built-in personas:

```bash
python simulate_from_patterns.py --list-personas
```

To force one persona:

```bash
python simulate_from_patterns.py \
  --scenario replay_like \
  --persona low_tech_confused \
  --limit 20
```

Built-in persona ids:

- `cooperative_normal`
- `vague_low_context`
- `low_tech_confused`
- `impatient_user`
- `tried_and_failed`
- `high_tech_diagnostic`
- `screenshot_dependent`

The MVP uses a deterministic mock QA opponent by default. It is meant to validate user behavior and data shape first; later the mock QA can be replaced by the real客服 AI endpoint.

To replay historical客服 turns one by one instead of generating rule-based mock replies, use `--agent replay`. This reads the historical dialogue file from `--config` and selects the first matched dialogue for each `case_id`:

```bash
python simulate_from_patterns.py \
  --config config.yaml \
  --patterns outputs/question_patterns.jsonl \
  --agent replay \
  --scenario replay_like \
  --persona low_tech_confused \
  --limit 20 \
  --llm-policy
```

Replay mode keeps the simulated user active, but the客服 side is copied from the historical dialogue's agent turns in order. If no historical dialogue is found for a case, it falls back to the deterministic mock QA opponent.

Simulator output masks URLs, emails, phone numbers, and long numeric IDs by default. Use `--no-mask` only for internal debugging on approved machines.

The simulator writes both machine-readable JSONL and a human-readable Markdown file. For example:

- `outputs/simulated_dialogues.hard.jsonl`
- `outputs/simulated_dialogues.hard.readable.md`

By default, user turns are generated by a deterministic rule policy. To let the local model control dialogue strategy, including when to reveal hidden slots from the case-only candidate set, enable `--llm-policy`:

```bash
python simulate_from_patterns.py \
  --scenario replay_like \
  --persona high_tech_diagnostic \
  --limit 20 \
  --llm-policy
```

The policy LLM can choose the next user action and `reveal_slot_indices`, but it is constrained to the existing `slot_reveal_plan`, `hidden_facts`, and `common_missing_slots`. It should answer a clarification only when the asked information matches available hidden slots; if the user persona would not know the requested information, it should reply with `unknown_info` and leave `reveal_slot_indices` empty. If the policy call fails, the simulator falls back to the deterministic rule policy.

To let the local model only rewrite user wording while keeping the rule policy in charge of facts and timing:

```bash
python simulate_from_patterns.py \
  --scenario difficult_user \
  --persona low_tech_confused \
  --limit 20 \
  --llm-rewrite
```

`--llm-rewrite` alone does not let the model decide which slot to reveal; it only rewrites the already selected user sentence. Use `--llm-policy` when the model should decide the reveal timing. The two flags can be combined.

The local NAS-style endpoint uses `api_key="EMPTY"` by default. If the server later requires a real key, set `LOCAL_AI_API_KEY` and it will override the default.

To emit only the user plan/opening without mock QA:

```bash
python simulate_from_patterns.py --agent none
```

`--mode` is still accepted as a deprecated alias for old commands, but new runs should use `--scenario`.

For local keyed sample validation:

```bash
python3 main.py --config config.keyed_sample.yaml
```

## Local AI

Default mode is `mock`, which makes the whole pipeline runnable without a model.

To use an OpenAI-compatible local endpoint:

```yaml
local_ai:
  provider: "openai-compatible"
  endpoint: "http://localhost:8000/v1/chat/completions"
  model: "your-local-model"
  api_key_env: "LOCAL_AI_API_KEY"
```
