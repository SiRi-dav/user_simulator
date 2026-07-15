# User Simulator 2.0 运行顺序与命令手册

这份文档只保留交接和复现实验最需要的内容：先跑什么、再跑什么、每一步会生成什么文件。默认所有命令都在 `User_simulator2.0` 目录下执行。

```bash
cd <repo_root>/User_simulator2.0
```

不要在命令里写某台机器的绝对路径。真实数据路径、输出目录、LLM API 都放到 `config.yaml` 或单独复制出的实验配置文件里。

## 0. 主线流程

主线操作按这个顺序跑：

```text
1. 分析历史对话数据
2. 找到有历史对话的 case id
3. 分析 case，生成路书和 blind user view
4. 与 assistant 批量模拟对话
5. 评测 user simulator
6. 整理路书、模拟记录、评测结果
```

其中第 1 步是行为先验，第 2-5 步是一次完整实验链路。第 6 步是为了人工审查和汇报。

## 1. 配置文件

默认配置文件是：

```text
config.yaml
```

关键字段：

```yaml
llm:
  provider: "openai-compatible"
  base_url: "<llm_base_url>"
  api_key: "<api_key>"
  model: "<model_name>"

paths:
  cases: "<case_library_path>"
  dialogues: "<historical_dialogue_path>"
  output_dir: "outputs"
```

含义：

- `paths.cases`: 案例库文件。
- `paths.dialogues`: 真实历史对话文件。
- `paths.output_dir`: 本次实验输出目录。
- `llm`: 路书生成、行为判断、评测 judge 使用的 LLM 服务。

如果要把新一轮实验放进新目录，例如 `output714`，推荐复制一个配置：

```bash
cp config.yaml config714.yaml
```

然后把 `config714.yaml` 里的 `paths.output_dir` 改成：

```yaml
paths:
  output_dir: "output714"
```

后续命令统一加：

```bash
--config config714.yaml
```

## 2. 第一步：分析历史对话数据

目的：从真实客服对话里挖掘用户行为风格，生成 persona 和 behavior taxonomy。

命令：

```bash
python3 main.py --config config714.yaml mine-behavior \
  --max_dialogues 50
```

如果想直接指定真实对话文件：

```bash
python3 main.py --config config714.yaml mine-behavior \
  --dialogues <historical_dialogue_path> \
  --max_dialogues 50
```

主要输出：

```text
output714/dialogue_behavior_summaries.jsonl
output714/employee_personas.jsonl
output714/user_behavior_taxonomy.jsonl
```

说明：

- 这一步不是必须每次都跑。如果输出目录里没有这些文件，系统会使用内置 manual seed。
- 如果你修改了行为 prompt 或想重新挖掘真实用户风格，再跑这一步。

## 3. 第二步：找到有真实历史对话的 case id

目的：从真实对话文件里筛出有真实对话可对比的 case。评测 user simulator 时必须有真实对话作为参照。

命令：

```bash
python3 main.py --config config714.yaml select-real-cases \
  --limit 500 \
  --offset 0 \
  --output output714/real_dialogue_case_ids.txt
```

如果只想先跑 20 个：

```bash
python3 main.py --config config714.yaml select-real-cases \
  --limit 20 \
  --offset 0 \
  --output output714/real_dialogue_case_ids.txt
```

主要输出：

```text
output714/real_dialogue_case_ids.txt
```

说明：

- `--offset 0 --limit 20` 是前 20 个。
- `--offset 20 --limit 20` 是第 21-40 个。
- 这个文件后面会被 `analyze-cases`、`simulate-batch`、`evaluate` 反复复用。

## 4. 第三步：分析 case，生成路书

目的：为每个目标 case 生成模拟时需要的知识结构，包括用户可见事实、诊断点、solution 判断点和 debug 信息。

推荐命令：

```bash
python3 main.py --config config714.yaml analyze-cases \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --workers 4
```

`--concurrency 4` 和 `--workers 4` 等价：

```bash
python3 main.py --config config714.yaml analyze-cases \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --concurrency 4
```

主要输出：

```text
output714/blind_user_case_views.jsonl
output714/blind_user_runtime_views.jsonl
output714/knowledge_roadmaps.jsonl
output714/case_analysis_debug.jsonl
output714/case_analysis_errors.jsonl
```

这些文件的作用：

- `blind_user_case_views.jsonl`: 给人工审查的 blind user 视图。
- `blind_user_runtime_views.jsonl`: 模拟运行时给 Blind User 读取的最小安全视图。
- `knowledge_roadmaps.jsonl`: KnowledgeAssessment/runtime 使用的路书。
- `case_analysis_debug.jsonl`: 每个 case 的检索、抽点、验证、建路书过程，适合排查路书质量。
- `case_analysis_errors.jsonl`: 失败 case 的错误记录。

断点续跑：

- `analyze-cases` 默认会跳过已经完整分析过的 case。
- 只有同一个 case 同时存在于 `knowledge_roadmaps.jsonl`、`blind_user_runtime_views.jsonl`、`case_analysis_debug.jsonl` 时才算完成。
- 中断后重复执行同一条命令即可。

强制重跑：

```bash
python3 main.py --config config714.yaml analyze-cases \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --workers 4 \
  --rerun_completed
```

## 5. 第四步：与 assistant 批量模拟对话

目的：让 user simulator 读取路书，和真实 assistant API 进行多轮对话。

推荐命令：

```bash
python3 main.py --config config714.yaml simulate-batch \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --assistant_mode api \
  --max_turns 15
```

主要输出：

```text
output714/simulation_logs.jsonl
output714/simulate_batch_status.jsonl
```

说明：

- `--assistant_mode api` 表示调用真实 assistant API，不是手动输入客服回复。
- `--max_turns 15` 是每个 case 最多对话轮数。
- `simulate-batch` 有断点保护，已经 `completed` 的 case 默认跳过。

强制重跑已经完成的模拟：

```bash
python3 main.py --config config714.yaml simulate-batch \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --assistant_mode api \
  --max_turns 15 \
  --rerun_completed
```

## 6. 第五步：评测 user simulator

当前推荐使用 LLM-primary 评测脚本。它不会覆盖旧版 `evaluate-simulator` 的结果，会单独输出到 `simulator_eval_llm_primary`。

推荐命令：

```bash
python3 scripts/evaluate_llm_primary_simulator.py \
  --config config714.yaml \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt \
  --session-policy latest
```

如果不想依赖 `config714.yaml` 里的真实对话路径，也可以显式传入：

```bash
python3 scripts/evaluate_llm_primary_simulator.py \
  --config config714.yaml \
  --output-dir output714 \
  --dialogues <historical_dialogue_path> \
  --case-ids-file output714/real_dialogue_case_ids.txt \
  --session-policy latest
```

主要输出：

```text
output714/simulator_eval_llm_primary/summary.md
output714/simulator_eval_llm_primary/simulator_eval_llm_primary.jsonl
output714/simulator_eval_llm_primary/<case_id>.md
```

`--session-policy` 可选：

- `latest`: 每个 case 只评最后一次模拟，最适合多次重跑后的正式评测。
- `first`: 每个 case 只评第一次模拟。
- `all`: 每个 case 的所有模拟 session 都评。

评测维度：

- `conditional`: 条件行为真实度，重点看用户是否根据 assistant 的追问、动作要求、无效方案做合理反应。
- `goal`: 目标一致性，重点看用户后续信息输出是否围绕原始问题，不乱改目标。
- `anti-overcoop`: 反过度合作，重点看用户是否没有无条件接受、没有替 assistant 补全答案。
- `realism`: 用户侧对话分布真实性参考。
- `user-c2st`: 用户对话可区分性参考，越高表示真实用户和模拟用户越难区分。
- `leakage-response`: 是否对疑似信息泄漏有合理惩罚和解释。
- `overall`: 综合分，LLM judge 为主，规则和分布信号为辅助证据。

注意：

- `real` 和 `simulated` 列是找到的真实对话数量和模拟对话数量，不是分数。
- 如果 assistant 本身没有命中 solution，不应该把责任全部算到 user simulator，评测会更关注用户是否合理反应。

## 7. 第六步：整理路书、模拟记录、评测结果

### 7.1 整理模拟对话记录

```bash
python3 scripts/export_combined_transcripts.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

输出：

```text
output714/transcripts/all_simulation_transcripts.md
output714/transcripts/all_simulation_transcripts.json
```

### 7.2 整理路书

```bash
python3 scripts/export_combined_roadmaps.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

输出：

```text
output714/review/all_knowledge_roadmaps.md
output714/review/all_knowledge_roadmaps.json
```

### 7.3 整理 LLM-primary 评测结果

```bash
python3 scripts/export_combined_llm_primary_eval.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

输出：

```text
output714/simulator_eval_llm_primary/all_llm_primary_eval.md
output714/simulator_eval_llm_primary/all_llm_primary_eval.json
```

### 7.4 整理旧版 evaluate-simulator 结果

如果你跑的是旧的 `main.py evaluate-simulator`，整理命令是：

```bash
python3 scripts/export_combined_eval.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

输出：

```text
output714/simulator_eval/all_simulator_eval.md
output714/simulator_eval/all_simulator_eval.json
```

## 8. 一套完整命令

下面是一套从头到尾的主线命令。正式实验时只需要替换配置文件和输出目录。

```bash
cd <repo_root>/User_simulator2.0
```

```bash
python3 main.py --config config714.yaml mine-behavior \
  --max_dialogues 50
```

```bash
python3 main.py --config config714.yaml select-real-cases \
  --limit 500 \
  --offset 0 \
  --output output714/real_dialogue_case_ids.txt
```

```bash
python3 main.py --config config714.yaml analyze-cases \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --workers 4
```

```bash
python3 main.py --config config714.yaml simulate-batch \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --assistant_mode api \
  --max_turns 15
```

```bash
python3 scripts/evaluate_llm_primary_simulator.py \
  --config config714.yaml \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt \
  --session-policy latest
```

```bash
python3 scripts/export_combined_transcripts.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

```bash
python3 scripts/export_combined_roadmaps.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

```bash
python3 scripts/export_combined_llm_primary_eval.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

## 9. 辅助功能

### 9.1 只分析指定 case

```bash
python3 main.py --config config714.yaml analyze-cases \
  --case_ids KT001 KT002 \
  --workers 2
```

### 9.2 按 offset 分批分析

```bash
python3 main.py --config config714.yaml analyze-cases \
  --limit 20 \
  --offset 40 \
  --workers 4
```

### 9.3 随机抽样 case

```bash
python3 main.py --config config714.yaml analyze-cases \
  --limit 20 \
  --random \
  --seed 42 \
  --workers 4
```

### 9.4 单 case 模拟

```bash
python3 main.py --config config714.yaml simulate \
  --case_id KT001 \
  --assistant_mode api \
  --max_turns 15
```

### 9.5 旧版评测命令

旧版评测仍然保留，但现在正式分析更推荐 LLM-primary 评测。

```bash
python3 main.py --config config714.yaml evaluate-simulator \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --session_policy latest \
  --judge
```

输出：

```text
output714/simulator_eval/
```

## 10. 常见问题

### 10.1 为什么模拟被跳过？

`simulate-batch` 会读取：

```text
output714/simulate_batch_status.jsonl
```

如果某个 case 已经是 `completed`，默认会跳过。需要重跑时加：

```bash
--rerun_completed
```

### 10.2 为什么分析 case 被跳过？

`analyze-cases` 默认断点续跑。只有三类产物都存在才跳过：

```text
knowledge_roadmaps.jsonl
blind_user_runtime_views.jsonl
case_analysis_debug.jsonl
```

如果需要强制重新生成路书，加：

```bash
--rerun_completed
```

### 10.3 为什么评测找不到真实对话？

检查 `config714.yaml`：

```yaml
paths:
  dialogues: "<historical_dialogue_path>"
```

或者在评测命令里显式加：

```bash
--dialogues <historical_dialogue_path>
```

### 10.4 为什么评测找不到模拟对话？

检查：

```text
output714/simulation_logs.jsonl
```

LLM-primary 评测读取的是 `--output-dir` 下的：

```text
simulation_logs.jsonl
knowledge_roadmaps.jsonl
```

所以如果模拟结果在 `output714`，评测时必须加：

```bash
--output-dir output714
```

### 10.5 `--assistant_mode api` 是否必须？

批量模拟正式评测时建议必须加：

```bash
--assistant_mode api
```

这样才是调用真实 assistant。手动模式更适合调试单个 case。

### 10.6 `--workers` 开多少合适？

一般先用：

```text
--workers 4
```

如果 LLM 服务稳定、限流不明显，可以试：

```text
--workers 8
```

如果出现连接错误、超时或服务限流，降到：

```text
--workers 2
```

## 11. 主线产物对照表

| 步骤 | 命令 | 关键输出 |
|---|---|---|
| 历史对话行为分析 | `mine-behavior` | `employee_personas.jsonl`, `user_behavior_taxonomy.jsonl` |
| 选择真实 case | `select-real-cases` | `real_dialogue_case_ids.txt` |
| case 分析 | `analyze-cases` | `knowledge_roadmaps.jsonl`, `blind_user_runtime_views.jsonl`, `case_analysis_debug.jsonl` |
| 批量模拟 | `simulate-batch` | `simulation_logs.jsonl`, `simulate_batch_status.jsonl` |
| LLM-primary 评测 | `scripts/evaluate_llm_primary_simulator.py` | `simulator_eval_llm_primary/summary.md`, per-case md |
| 整理导出 | `export_combined_*` | 合并后的 `.md` 和 `.json` |
