# User Simulator 2.0 项目结构说明

这份文档说明新版用户模拟器的目录结构、核心模块职责、主要产物，以及旧版模拟器在哪里运行。具体“先跑什么命令、后跑什么命令”请看：

```text
docs/how_user_simulator_works_and_run_order.md
```

公司 Windows 电脑上的约定：

```text
新版目录：xirui_up1
旧版目录：xirui_test
```

所有新版命令默认在 `xirui_up1` 目录下执行：

```bash
cd xirui_up1
```

公司电脑上统一使用：

```bash
python
```

不要使用带版本后缀的 Python 命令。

## 1. 项目定位

`xirui_up1` 是当前新版 user simulator。它的目标不是单独生成客服回复，而是模拟企业员工用户，与真实 assistant API 对话，然后用真实历史对话作为参照评测模拟质量。

核心思路：

```text
案例库提供“这个用户知道什么”
历史对话提供“真实用户通常怎么反应”
路书控制“哪些信息可以说、什么时候能说”
KnowledgeAssessment 判断“assistant 这一轮是否解决、用户还能说什么”
BlindUserAction 决定“用户这一轮怎么自然回应”
评测系统对比真实对话和模拟对话
```

新版尽量使用 LLM judge 做抽取、判断、打分；规则主要作为断点保护、文件组织、统计辅助和运行控制。

## 2. 顶层文件

### `main.py`

新版主入口。主线命令都从这里进入：

```text
mine-behavior
select-real-cases
analyze-cases
simulate
simulate-batch
evaluate-simulator
export-review
export-transcripts
export-metrics
```

正式评测更推荐使用单独脚本：

```text
scripts/evaluate_llm_primary_simulator.py
```

### `config.yaml`

配置 LLM、案例库、真实对话和输出目录。

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

建议每次实验复制一个配置文件，例如：

```bash
copy config.yaml config714.yaml
```

然后把 `paths.output_dir` 改成独立目录，例如：

```yaml
paths:
  output_dir: "output714"
```

### `README.md`

项目总览和简短命令说明。交接时以 `docs/how_user_simulator_works_and_run_order.md` 为主。

### `requirements.txt`

Python 依赖。

## 3. `src/` 核心模块

### `src/schemas.py`

所有结构化数据和 LLM 输出 schema 的中心。重要对象包括：

```text
Case
RetrievalQuery
Point
Roadmap
BlindUserCaseView
BlindUserRuntimeView
KnowledgeAssessment
BlindUserAction
SimulationLogRecord
```

如果 LLM 返回字段缺失或格式不对，通常会在这里的 Pydantic 校验阶段报错。

### `src/data_loader.py`

读取案例库，并把原始字段映射成统一的 `Case`。

配置字段来自：

```yaml
case_fields:
  case_id: "__key__"
  title: "case_name"
  phenomenon: "text"
  solution: "text"
```

### `src/behavior_mining/`

负责分析真实历史对话，生成用户行为先验。

主要文件：

```text
dialogue_loader.py
behavior_miner.py
persona_miner.py
behavior_taxonomy_miner.py
prompt_templates.py
```

主要输出：

```text
<output_dir>/dialogue_behavior_summaries.jsonl
<output_dir>/employee_personas.jsonl
<output_dir>/user_behavior_taxonomy.jsonl
```

### `src/retrieval/`

负责 related case 召回和排序。

当前做法：

```text
多路 query 生成
本地候选召回
混合检索
LLM 排序打分
```

主要文件：

```text
query_generator.py
local_candidate_recall.py
related_case_retriever.py
prompt_templates.py
```

### `src/extraction/`

负责从目标 case 和 related cases 中抽取知识点。

主要文件：

```text
point_extractor.py
point_verifier.py
prompt_templates.py
```

知识点类型：

```text
user_facing: 用户表层可见信息
diagnostic: 被追问后可释放的诊断信息
solution: 只用于判断是否解决，不直接泄漏给用户
external: related case 里的外部或混淆方向
```

### `src/roadmap/`

负责把知识点组织成路书。

主要文件：

```text
relation_builder.py
roadmap_builder.py
prompt_templates.py
```

路书里最关键的是：

```text
surface_problem
opening_intent
user_facing_points
diagnostic_points
solution_points
external_points
target_route
external_routes
forbidden_content
```

### `src/runtime/`

负责真正的用户模拟。

主要文件：

```text
simulator.py
knowledge_module.py
blind_user.py
dialogue_state.py
prompt_templates.py
```

运行时分工：

```text
KnowledgeAssessment:
  判断 assistant 是否命中目标方案
  判断用户是否还有可回答事实
  判断是否进入无新信息状态
  给 BlindUserAction 提供“允许说什么”

BlindUserAction:
  决定是否接受方案并结束
  决定是否执行动作、追问步骤、反馈动作结果
  决定在无新信息时继续求助、表达困惑或停止
```

### `src/assistant/`

真实 assistant API 接入。

主要文件：

```text
real_assistant_client.py
```

正式批量模拟时使用：

```bash
python main.py --config config714.yaml simulate-batch \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --assistant_mode api \
  --max_turns 15
```

### `src/llm/`

LLM 客户端封装。

主要文件：

```text
openai_compatible_client.py
mock_llm_client.py
llm_client.py
```

如果 judge 服务或路书生成服务报错，优先检查：

```text
config.yaml / config714.yaml 里的 llm.base_url
config.yaml / config714.yaml 里的 llm.model
网络是否能访问公司 LLM 服务
```

### `src/simulator_evaluator.py`

旧版 `main.py evaluate-simulator` 使用的评测器。

保留用于兼容和对照实验，但当前更推荐 LLM-primary 评测。

### `src/llm_primary_simulator_evaluator.py`

新版主评测器。入口脚本是：

```text
scripts/evaluate_llm_primary_simulator.py
```

评测维度：

```text
conditional
goal
anti-overcoop
realism
user-c2st
leakage-response
overall
```

### `src/tau2_evaluator.py`

额外的 tau2-style 评测模块，用于对照实验。

## 4. `scripts/` 工具脚本

### `scripts/evaluate_llm_primary_simulator.py`

推荐的新评测入口。

```bash
python scripts/evaluate_llm_primary_simulator.py \
  --config config714.yaml \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt \
  --session-policy latest
```

### `scripts/export_combined_transcripts.py`

把多个模拟对话合并成一个可读文档。

```bash
python scripts/export_combined_transcripts.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

### `scripts/export_combined_roadmaps.py`

把多个路书合并成一个可读文档。

```bash
python scripts/export_combined_roadmaps.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

### `scripts/export_combined_llm_primary_eval.py`

把 LLM-primary 的 summary 和每个 case 的 md 合并成一个文档。

```bash
python scripts/export_combined_llm_primary_eval.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

### `scripts/export_combined_eval.py`

整理旧版 `evaluate-simulator` 的结果。

```bash
python scripts/export_combined_eval.py \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt
```

## 5. `data/` 种子文件

```text
data/manual_seed_employee_personas.jsonl
data/manual_seed_user_behavior_taxonomy.jsonl
```

如果没有跑 `mine-behavior`，runtime 会使用这些内置种子作为用户行为先验。

## 6. `docs/` 文档

重点看两份：

```text
docs/how_user_simulator_works_and_run_order.md
docs/project_structure_and_run_guide.md
```

其他评测相关文档主要记录历史设计和实验解释：

```text
docs/evaluation_improvement_summary.md
docs/evaluation_metrics_enhancement.md
docs/evaluation_metrics_example.md
docs/llm_judge_refactor_summary.md
```

## 7. `tests/` 测试

运行测试：

```bash
python -m pytest tests
```

编译检查：

```bash
python -m compileall .
```

常用重点测试：

```bash
python -m pytest tests/test_runtime.py
python -m pytest tests/test_simulate_batch.py
python -m pytest tests/test_llm_primary_simulator_evaluator.py
python -m pytest tests/test_combined_export_scripts.py
```

## 8. 输出目录结构

假设本次实验输出目录是 `output714`，常见文件如下：

```text
output714/
  real_dialogue_case_ids.txt
  dialogue_behavior_summaries.jsonl
  employee_personas.jsonl
  user_behavior_taxonomy.jsonl
  blind_user_case_views.jsonl
  blind_user_runtime_views.jsonl
  knowledge_roadmaps.jsonl
  case_analysis_debug.jsonl
  case_analysis_errors.jsonl
  simulation_logs.jsonl
  simulate_batch_status.jsonl
  review/
  transcripts/
  simulator_eval/
  simulator_eval_llm_primary/
```

主线产物：

```text
real_dialogue_case_ids.txt: 有真实对话的 case 列表
knowledge_roadmaps.jsonl: 模拟和评测需要的路书
blind_user_runtime_views.jsonl: Blind User 运行时读取的安全视图
simulation_logs.jsonl: 模拟对话原始记录
simulator_eval_llm_primary/: 新版 LLM-primary 评测结果
```

## 9. 新版运行入口

新版在 `xirui_up1` 下运行：

```bash
cd xirui_up1
```

主线命令顺序：

```bash
python main.py --config config714.yaml mine-behavior --max_dialogues 50
```

```bash
python main.py --config config714.yaml select-real-cases \
  --limit 500 \
  --offset 0 \
  --output output714/real_dialogue_case_ids.txt
```

```bash
python main.py --config config714.yaml analyze-cases \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --workers 4
```

```bash
python main.py --config config714.yaml simulate-batch \
  --case_ids_file output714/real_dialogue_case_ids.txt \
  --assistant_mode api \
  --max_turns 15
```

```bash
python scripts/evaluate_llm_primary_simulator.py \
  --config config714.yaml \
  --output-dir output714 \
  --case-ids-file output714/real_dialogue_case_ids.txt \
  --session-policy latest
```

## 10. 旧版运行入口

旧版模拟器在 `xirui_test` 下运行：

```bash
cd xirui_test
```

旧版本身不重新生成新版路书，通常复用新版已经生成好的：

```text
outputs_v1/knowledge_roadmaps.jsonl
```

如果要跑旧版模拟器，使用旧版目录里的 roadmap API simulation 脚本。命令模板如下：

```bash
python -m src.pipelines.run_roadmap_api_simulation \
  --roadmaps outputs_v1/knowledge_roadmaps.jsonl \
  --output outputs_v1/roadmap_api_simulation.jsonl \
  --simulation-log-output outputs_v1/simulation_logs.jsonl \
  --case_ids_file outputs_v1/real_dialogue_case_ids.txt \
  --assistant-config assistant_config.yaml \
  --max-turns 15
```

如果只想先跑一小批，加：

```bash
--limit 20
```

旧版评测使用复制到 `xirui_test` 里的 LLM-primary 评测脚本：

```bash
python scripts/evaluate_llm_primary_simulator.py \
  --config config.yaml \
  --llm-config judge_config.yaml \
  --output-dir outputs_v1 \
  --dialogues <historical_dialogue_path> \
  --case-ids-file outputs_v1/real_dialogue_case_ids.txt \
  --session-policy latest
```

旧版评测结果整理：

```bash
python scripts/export_combined_llm_primary_eval.py \
  --output-dir outputs_v1 \
  --case-ids-file outputs_v1/real_dialogue_case_ids.txt
```

注意：

- 旧版命令一定在 `xirui_test` 下执行。
- 新版命令一定在 `xirui_up1` 下执行。
- 两边可以使用同一批 `real_dialogue_case_ids.txt`，这样评测结果才可对比。
- 两边评测系统尽量保持一致，区别只在被评测的模拟器不同。

## 11. 常见排错

### 找不到文件

先确认当前目录：

```bash
pwd
```

新版应该在：

```text
xirui_up1
```

旧版应该在：

```text
xirui_test
```

### 评测全是 failed 或 0

优先检查 judge 配置：

```text
config.yaml / judge_config.yaml
llm.base_url
llm.model
llm.api_key
```

还要确认评测输入存在：

```text
<output_dir>/simulation_logs.jsonl
<output_dir>/knowledge_roadmaps.jsonl
<output_dir>/real_dialogue_case_ids.txt
```

### 模拟被跳过

检查：

```text
<output_dir>/simulate_batch_status.jsonl
```

如果要强制重跑，加：

```bash
--rerun_completed
```

### case 分析被跳过

`analyze-cases` 默认断点续跑。一个 case 同时出现在下面三个文件里才算完成：

```text
knowledge_roadmaps.jsonl
blind_user_runtime_views.jsonl
case_analysis_debug.jsonl
```

强制重跑加：

```bash
--rerun_completed
```
