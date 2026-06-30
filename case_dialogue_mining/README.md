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
  max_tokens: 2048
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
