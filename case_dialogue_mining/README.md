# Case Dialogue Mining

This tool mines case-dialogue pairs and asks a local AI model to summarize how real users ask questions for each case.

The first-stage goal is data mining and analysis, not user simulation runtime.

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

The upgraded analysis separates:

- `observed_from_dialogue`: behavior or facts supported by real conversations
- `inferred_from_case`: likely user-side facts inferred from the case answer
- `uncertain_points`: assumptions that need more data
- `slot_reveal_plan`: when hidden slots should be revealed in a later simulator
- `simulator_actions`: reusable user behavior actions by turn stage
- `evaluation_focus`: what the客服 AI should be tested on for this case

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

## Lightweight Simulator MVP

After `question_patterns.jsonl` is generated, run a first simulator version directly from the mined patterns:

```bash
python simulate_from_patterns.py \
  --mode replay_like \
  --limit 20
```

Available user modes:

- `replay_like`: close to historical user reveal rhythm
- `vague_user`: starts vague and forces clarification
- `difficult_user`: confused, less satisfied, asks for more concrete guidance

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
  --mode replay_like \
  --persona low_tech_confused \
  --limit 20
```

Built-in persona ids:

- `cooperative_normal`
- `vague_low_context`
- `low_tech_confused`
- `impatient_user`
- `tried_and_failed`
- `screenshot_dependent`

The MVP uses a deterministic mock QA opponent by default. It is meant to validate user behavior and data shape first; later the mock QA can be replaced by the real客服 AI endpoint.

Simulator output masks URLs, emails, phone numbers, and long numeric IDs by default. Use `--no-mask` only for internal debugging on approved machines.

The simulator writes both machine-readable JSONL and a human-readable Markdown file. For example:

- `outputs/simulated_dialogues.hard.jsonl`
- `outputs/simulated_dialogues.hard.readable.md`

By default, user utterances are rule-generated. To let the local model only rewrite user wording while the rule state machine still controls what facts are revealed:

```bash
python simulate_from_patterns.py \
  --mode difficult_user \
  --persona low_tech_confused \
  --limit 20 \
  --llm-rewrite
```

This does not let the model decide which slot to reveal; it only rewrites the already selected user sentence. The rewrite prompt contains both the case-grounding line and the persona/behavior line.

The local NAS-style endpoint uses `api_key="EMPTY"` by default. If the server later requires a real key, set `LOCAL_AI_API_KEY` and it will override the default.

To emit only the user plan/opening without mock QA:

```bash
python simulate_from_patterns.py --agent none
```

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
