# Case Dialogue Mining

This tool mines case-dialogue pairs and asks a local AI model to summarize how real users ask questions for each case.

The first-stage goal is data mining and analysis, not user simulation runtime.

## Run With Sample Data

```bash
cd case_dialogue_mining
python3 main.py --config config.yaml
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

