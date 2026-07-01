# 程序结构说明

这个目录现在包含两条工作流：

1. 数据挖掘与本地 AI 分析：从案例库和历史对话中挖出 `case-dialogue pair`，再总结用户如何提问。
2. 用户模拟器 MVP：基于分析结果、评测场景和 persona 生成多轮模拟用户。
3. Case-only 分析：只给一个 case，不看历史对话，也推断可模拟的用户提问字段。

## 一、整体运行链路

```text
原始案例库 + 原始对话记录
        ↓
data_loader.py
        ↓
case_dialogue_matcher.py
        ↓
case_dialogue_pairs.jsonl
        ↓
analyzer.py + prompt_templates.py + local_ai_client.py
        ↓
question_patterns.jsonl
  ├─ dialogue_level_patterns：每条真实对话各自的提问结果
  └─ case-level summary：该 case 的聚合总结
        ↓
simulate_from_patterns.py + persona_bank.py
        ↓
simulated_dialogues.*.jsonl / *.readable.md
```

## 二、程序调用关系

### 1. 数据挖掘与 AI 分析调用链

运行命令：

```bash
python main.py --config config.yaml
```

实际调用关系：

```text
main.py
  ├─ 读取 config.yaml
  │
  ├─ data_loader.py
  │    ├─ load_cases(...)
  │    │    └─ load_raw_records(...)
  │    └─ load_dialogues(...)
  │         └─ load_raw_records(...)
  │
  ├─ case_dialogue_matcher.py
  │    └─ match_cases_and_dialogues(cases, dialogues)
  │
  ├─ analyzer.py
  │    └─ analyze_pairs(pairs, ai_client, ...)
  │         ├─ prompt_templates.py
  │         │    └─ build_case_question_pattern_prompt(pair)
  │         ├─ local_ai_client.py
  │         │    ├─ MockLocalAIClient.generate(prompt)
  │         │    └─ OpenAI-compatible LocalAIClient.generate(prompt)
  │         └─ utils.py
  │              └─ write_jsonl(...)  # partial checkpoint
  │
  └─ output_writer.py
       └─ write_outputs(...)
            ├─ write_jsonl(...)
            ├─ write_pair_summary(...)
            └─ readable review writer
```

这个流程的产物是：

```text
outputs/case_dialogue_pairs.jsonl
outputs/question_patterns.jsonl
outputs/analysis_errors.jsonl
outputs/summary_report.md
outputs/question_patterns.readable.md
```

### 2. 只做 pair mining、不调用 AI 的调用链

运行命令：

```bash
python main.py --config config.yaml --skip-analysis
```

实际调用关系：

```text
main.py
  ├─ data_loader.py
  ├─ case_dialogue_matcher.py
  └─ output_writer.py
```

不会调用：

```text
analyzer.py
prompt_templates.py
local_ai_client.py
```

适合用于快速验证路径、字段映射、case_id 匹配数量。

### 3. 审阅导出调用链

运行命令：

```bash
python review_export.py --input outputs/question_patterns.jsonl --limit 30
```

实际调用关系：

```text
review_export.py
  ├─ utils.py
  │    ├─ read_jsonl(...)
  │    └─ write_jsonl(...)
  └─ 内部 Markdown writer / mask functions
```

这个流程不重新分析数据，只是把已有 `question_patterns.jsonl` 变得更适合人工检查。

### 4. Case-only 分析调用链

运行命令：

```bash
python analyze_cases_only.py --config config.yaml --max-cases 20
```

实际调用关系：

```text
analyze_cases_only.py
  ├─ data_loader.py
  │    └─ load_cases(...)
  │
  ├─ prompt_templates.py
  │    └─ build_case_only_question_pattern_prompt(case)
  │
  ├─ local_ai_client.py
  │    └─ 调用本地 Qwen / OpenAI-compatible endpoint
  │
  ├─ analyzer.py
  │    └─ parse_pattern(...)
  │
  └─ output_writer.py
       └─ build_readable_patterns_report(...)
```

这个流程不读取历史对话，输出的是：

```text
outputs_case_only/question_patterns.case_only.jsonl
outputs_case_only/question_patterns.case_only.readable.md
outputs_case_only/analysis_errors.case_only.jsonl
```

它的作用是服务最终目标：

```text
只给一个新 case
        ↓
AI 推断 surface_problem / initial_question / hidden_facts / slot_reveal_plan
        ↓
用户模拟器直接生成对话
```

注意：

- `observed_from_dialogue` 必须为空；
- `dialogue_level_patterns` 里使用 `synthetic_1`、`synthetic_2`、`synthetic_3`；
- `inferred_from_case` 记录推断依据；
- `slot_reveal_plan.source` 只能是 `case` 或 `inferred`。

### 5. 用户模拟器调用链

运行命令：

```bash
python simulate_from_patterns.py \
  --scenario difficult_user \
  --persona low_tech_confused \
  --limit 20
```

实际调用关系：

```text
simulate_from_patterns.py
  ├─ utils.py
  │    ├─ read_jsonl(outputs/question_patterns.jsonl)
  │    └─ write_jsonl(simulated_dialogues.*.jsonl)
  │
  ├─ persona_bank.py
  │    ├─ load_personas(...)
  │    ├─ choose_persona(...)
  │    └─ persona_summary(...)
  │
  ├─ build_initial_state(pattern, scenario, persona)
  │    └─ normalize_slots(pattern)
  │
  ├─ next_user_utterance(...)
  │    ├─ choose_opening(...)
  │    ├─ apply_scenario_style(...)
  │    └─ apply_persona_style(...)
  │
  ├─ mock_agent_step(...)
  │    └─ 当前临时模拟客服 AI
  │
  ├─ rewrite_user_utterance(...)
  │    ├─ build_rewrite_prompt(...)
  │    └─ local_ai_client.py  # 只有 --llm-rewrite 时调用
  │
  └─ build_readable_report(...)
       └─ 写出 simulated_dialogues.*.readable.md
```

如果不开 `--llm-rewrite`：

```text
simulate_from_patterns.py
  └─ MockLocalAIClient
```

如果开 `--llm-rewrite`：

```text
simulate_from_patterns.py
  └─ local_ai_client.py
       └─ 调用本地 Qwen / OpenAI-compatible endpoint
```

### 5. 接真实客服 AI 后的预期调用链

当前：

```text
simulate_from_patterns.py
  └─ mock_agent_step(...)
```

未来：

```text
simulate_from_patterns.py
  ├─ real_agent_client.py     # 建议新增
  │    └─ call_real_agent(...)
  └─ real_agent_step(...)
       ├─ 发送用户话语和 history
       ├─ 获取客服 AI 回复
       ├─ 解析 recommended_case_id
       └─ 返回给用户模拟器继续下一轮
```

接入后，模拟器主循环会变成：

```text
用户模拟器生成用户话语
        ↓
真实客服 AI 返回回复和 case_id
        ↓
用户模拟器根据回复继续透露/追问/接受/放弃
        ↓
记录 case_hit、turns_to_hit、clarification_count
```

## 三、文件依赖关系简表

| 文件 | 被谁调用 | 调用谁 | 备注 |
|---|---|---|---|
| `main.py` | 命令行 | `data_loader.py`, `case_dialogue_matcher.py`, `analyzer.py`, `output_writer.py`, `local_ai_client.py` | 数据挖掘主入口 |
| `analyze_cases_only.py` | 命令行 | `data_loader.py`, `prompt_templates.py`, `local_ai_client.py`, `analyzer.py`, `output_writer.py` | 只看 case 的分析入口 |
| `data_loader.py` | `main.py` | `schemas.py`, `utils.py` | 统一原始数据格式 |
| `case_dialogue_matcher.py` | `main.py` | `schemas.py` | case-dialogue 匹配 |
| `analyzer.py` | `main.py` | `prompt_templates.py`, `local_ai_client.py`, `utils.py` | LLM 分析用户提问方式 |
| `prompt_templates.py` | `analyzer.py` | 无 | 构造分析 prompt |
| `local_ai_client.py` | `main.py`, `analyzer.py`, `simulate_from_patterns.py` | 外部 LLM endpoint | 本地 Qwen / mock 客户端 |
| `output_writer.py` | `main.py` | `utils.py` | 写结果和报告 |
| `review_export.py` | 命令行 | `utils.py` | 人工审阅导出 |
| `simulate_from_patterns.py` | 命令行 | `persona_bank.py`, `local_ai_client.py`, `utils.py` | 用户模拟器主入口 |
| `persona_bank.py` | `simulate_from_patterns.py` | 无 | persona 库 |
| `schemas.py` | `data_loader.py`, `case_dialogue_matcher.py`, `output_writer.py`, `prompt_templates.py` | 无 | 数据结构 |
| `utils.py` | 多数文件 | 无 | JSONL 和路径工具 |

---

## 四、入口程序

### `main.py`

数据挖掘与 AI 分析的主入口。

常用命令：

```bash
python main.py --config config.yaml
python main.py --config config.yaml --max-cases 5
python main.py --config config.yaml --skip-analysis
python main.py --config config.yaml --resume-analysis
```

主要职责：

- 读取配置文件
- 加载案例库和对话数据
- 匹配 case 与 dialogue
- 调用本地 AI 分析用户提问方式
- 写出中间结果和汇总报告

主要输出：

- `outputs/case_dialogue_pairs.jsonl`
- `outputs/question_patterns.jsonl`
- `outputs/analysis_errors.jsonl`
- `outputs/summary_report.md`
- `outputs/question_patterns.readable.md`

### `analyze_cases_only.py`

只看案例库、不看历史对话的分析入口。

常用命令：

```bash
python analyze_cases_only.py --config config.yaml --max-cases 20
python analyze_cases_only.py --config config.yaml --case-id KT00267383
python analyze_cases_only.py --config config.yaml --resume
```

主要职责：

- 读取案例库
- 对每个 case 构造 case-only prompt
- 推断用户侧提问字段
- 输出和 `question_patterns.jsonl` 兼容的结构

主要输出：

- `outputs_case_only/question_patterns.case_only.jsonl`
- `outputs_case_only/question_patterns.case_only.readable.md`
- `outputs_case_only/analysis_errors.case_only.jsonl`

### `simulate_from_patterns.py`

用户模拟器主入口。

常用命令：

```bash
python simulate_from_patterns.py --scenario replay_like --limit 20
python simulate_from_patterns.py --scenario vague_user --persona vague_low_context --limit 20
python simulate_from_patterns.py --scenario difficult_user --persona low_tech_confused --limit 20 --llm-rewrite
python simulate_from_patterns.py --list-personas
```

主要职责：

- 读取 `question_patterns.jsonl`
- 选择评测场景 `scenario`
- 选择或自动分配 persona
- 根据 case 主线控制目标、槽位和透露节奏
- 根据 persona 主线控制用户表达风格和行为倾向
- 可选调用本地 LLM 改写用户话语
- 当前仍使用 `mock_agent_step` 模拟客服回复

主要输出：

- `outputs/simulated_dialogues.<scenario>.jsonl`
- `outputs/simulated_dialogues.<scenario>.readable.md`

## 五、数据读取与结构层

### `data_loader.py`

负责读取原始 JSON / JSONL，并转换成统一结构。

主要处理：

- 普通 list JSON
- keyed JSON，例如 `{case_id: {...}}`
- 公司案例库字段：`case_name`、`text`
- 公司对话字段：`caseId`、role 前缀字符串

如果原始数据格式变了，优先看这个文件。

### `schemas.py`

定义内部数据结构。

包含：

- `CaseRecord`
- `DialogueTurn`
- `DialogueRecord`
- `CaseDialoguePair`

它只是结构定义，不负责业务逻辑。

### `utils.py`

通用工具函数。

包含：

- `read_jsonl`
- `write_jsonl`
- `get_path`

一般不需要改。

## 六、case-dialogue pair 挖掘层

### `case_dialogue_matcher.py`

负责把案例库和对话记录按 `case_id` 匹配起来。

输入：

- `List[CaseRecord]`
- `List[DialogueRecord]`

输出：

- `List[CaseDialoguePair]`

当前匹配方式比较直接：

```text
dialogue.case_id == case.case_id
```

如果后面要做模糊匹配、一个对话多个 case、case_id 清洗，这里会变重要。

### `output_writer.py`

负责写出挖掘和分析结果。

主要输出：

- pair 明细
- question pattern 明细
- analysis error
- summary report
- readable review 文件

如果只是改分析逻辑，一般不改这里。

## 七、本地 AI 分析层

### `analyzer.py`

负责对每个 case-dialogue pair 调用本地 AI，抽取用户提问模式。

主要职责：

- 拼 prompt
- 调用 `LocalAIClient`
- 解析 JSON
- 记录错误
- 写 partial checkpoint
- 支持 resume

如果 AI 分析结果质量不好，通常改这里或 `prompt_templates.py`。

### `prompt_templates.py`

负责生成分析 prompt。

当前目标是让 LLM 输出：

- `dialogue_level_patterns`
  - 每条真实历史对话各自的提问结果
  - 包括 surface_problem、initial_question、known_facts、hidden_facts、missing_slots、reveal_path、expression_style
- `case_understanding`
- `behavior_model`
- `simulation_plan`

这里不抽 persona。persona 由 `persona_bank.py` 单独控制；prompt 只抽该 case 下的提问方式和表达规律。

当前包含两个核心 prompt：

- `build_case_question_pattern_prompt`
  - 输入 case + 历史对话；
  - 输出真实对话支撑的用户提问模式；
  - 用来学习和校准。

- `build_case_only_question_pattern_prompt`
  - 只输入 case；
  - 输出从 case 推断出的用户提问模式；
  - 用来支持最终“给一个新 case 直接模拟用户”的目标。

### `local_ai_client.py`

本地 AI 客户端。

支持：

- `mock`
- OpenAI-compatible endpoint，例如 Qwen 本地服务

如果本地模型接口、鉴权方式、请求参数变了，改这里。

## 八、审阅与导出层

### `review_export.py`

把 `question_patterns.jsonl` 转成人能读的 Markdown / masked JSONL。

常用命令：

```bash
python review_export.py --input outputs/question_patterns.jsonl --limit 30
```

用途：

- 人工检查 LLM 分析质量
- 做汇报截图
- 轻度脱敏后导出样例

## 九、用户模拟器层

### `simulate_from_patterns.py`

当前最核心的模拟器文件。

内部核心函数：

- `build_initial_state`
  - 根据 case pattern、scenario、persona 初始化用户状态

- `next_user_utterance`
  - 根据上一轮客服回复决定用户下一句话

- `choose_opening`
  - 选择用户开场

- `mock_agent_step`
  - 临时 mock 客服 AI
  - 后面接真实客服 AI 时主要替换这里

- `rewrite_user_utterance`
  - 可选调用 LLM 改写用户话语

- `build_rewrite_prompt`
  - 把 case 主线和 persona 主线写入 LLM 改写 prompt

当前推荐概念：

```text
scenario = 评测场景 / 测试强度
persona  = 用户画像 / 行为风格
```

可选 scenario：

- `replay_like`
- `vague_user`
- `difficult_user`

### `persona_bank.py`

内置 persona 库。

当前 persona：

- `cooperative_normal`
- `vague_low_context`
- `low_tech_confused`
- `impatient_user`
- `tried_and_failed`
- `screenshot_dependent`

主要职责：

- 保存默认 persona
- 支持从外部 JSON 加载 persona bank
- 根据 case_id 和 scenario 自动稳定选择 persona
- 输出 persona summary

如果后续从真实历史对话中聚类用户画像，可以把结果接到这里。

## 十、配置文件

### `config.yaml`

公司服务器真实路径和本地 Qwen 配置。

当前适配：

```text
/mnt/nas1/users/CuhkszTeam/RUNTIME/raw_data/格式化案例库/uniknow-full-text.json
/mnt/nas1/users/CuhkszTeam/RUNTIME/raw_data/格式化对话记录/用户和坐席交互09-proceed-full.json
```

### `config.sample.yaml`

本地样例数据配置。

适合开发和 smoke test。

### `config.keyed_sample.yaml`

用于验证 keyed JSON 格式。

## 十一、接真实客服 AI 时主要改哪里

优先新增或修改：

```text
simulate_from_patterns.py
```

需要做的事：

1. 新增 `--agent real`
2. 新增真实客服 AI endpoint 参数
3. 新增 `real_agent_step`
4. 把 `mock_agent_step` 替换成真实接口调用
5. 在输出里记录：
   - `target_case_id`
   - `recommended_case_id`
   - `case_hit`
   - `turns_to_hit`
   - `raw_agent_response`

如果真实客服 AI 接口复杂，可以单独拆一个：

```text
real_agent_client.py
```

## 十二、哪些文件一般不用动

一般稳定后不太需要改：

- `schemas.py`
- `utils.py`
- `case_dialogue_matcher.py`

经常会改：

- `prompt_templates.py`
- `analyzer.py`
- `simulate_from_patterns.py`
- `persona_bank.py`
- `config.yaml`

## 十三、Question Pattern Schema 设计

当前 `question_patterns.jsonl` 只保留三层主结构，不再输出旧版顶层兼容字段。

```text
case_understanding
behavior_model
simulation_plan
```

### `case_understanding`

回答“目标 case 是什么，用户真正想解决什么”。这一层来自案例库本身，对应传统任务型对话里的 user goal / target task。

主要字段：

- `target_case_id`
- `user_visible_problem`
- `likely_user_goal`
- `required_slots`
- `case_to_question_summary`
- `evidence_from_case`

### `behavior_model`

回答“用户会怎么问、知道什么、隐藏什么、怎样逐步透露”。这一层从历史对话学习；case-only 场景下则由 case 推断。

主要字段：

- `dialogue_level_patterns`
- `surface_problem_patterns`
- `initial_question_patterns`
- `known_facts`
- `hidden_facts`
- `reveal_patterns`
- `expression_style_patterns`
- `common_missing_slots`

### `simulation_plan`

回答“模拟器实际怎么跑”。这一层直接服务后续用户模拟。

主要字段：

- `opening_question_templates`
- `slot_reveal_plan`
- `simulator_actions`
- `simulation_suggestions`
- `evaluation_focus`
- `stop_conditions`

后续分析、review 和模拟器都直接读取这三层结构。
