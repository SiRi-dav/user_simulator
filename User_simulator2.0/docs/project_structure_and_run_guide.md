# User Simulator 2.0 项目结构与运行指南

本文档说明 `User_simulator2.0` 当前版本的项目结构、各程序职责，以及如何运行 demo 和测试。

## 1. 项目定位

`User_simulator2.0` 是一个企业 IT 客服评测用的 LLM-based Knowledge-grounded User Simulator MVP。

当前版本的核心原则是：不要做 rule-based MVP。所有核心判断、抽取、分类、匹配、决策和回复生成都通过 LLM 完成。

目前 assistant 回复先由人工输入。User Simulator 侧仍然全流程走 LLM，包括：

- related case retrieval query generation
- related case selection
- point extraction
- point verification
- relation building
- roadmap assembly
- initial user opening
- assistant act parsing
- knowledge decision
- blind user reply rendering
- solution matching

## 2. 整体运行流程

主入口是 `main.py`。

当前流程拆成三个阶段，避免每次指定一个 case 都重新跑完整 pipeline。

第一阶段：历史对话行为挖掘

1. 读取 `config.yaml`
2. 按 `config.yaml` 中的真实历史对话路径加载 dialogue logs
3. 对每条 dialogue 用 LLM 生成 `DialogueBehaviorSummary`
4. 汇总 summaries 后用 LLM 挖掘 `EmployeePersona`
5. 汇总 summaries 后用 LLM 挖掘 `BehaviorTaxonomy`
6. 写入 `outputs/dialogue_behavior_summaries.jsonl`
7. 写入 `outputs/employee_personas.jsonl`
8. 写入 `outputs/user_behavior_taxonomy.jsonl`

第二阶段：批量案例分析与路书生成

1. 按 `config.yaml` 中的路径加载真实案例库
2. 选择前 N 个 case，或选择 `--case_ids` 指定的 case
3. `QueryGenerator` 用 LLM 生成 related case 检索 query
4. `RelatedCaseRetriever` 用 LLM 从候选 case 中选择 related cases
5. `PointExtractor` 用 LLM 抽取 knowledge points
6. `PointVerifier` 用 LLM 校验 points
7. `RelationBuilder` 用 LLM 建立 point relations
8. `RoadmapBuilder` 用 LLM 组装 roadmap
9. 写入 `outputs/blind_user_case_views.jsonl`
10. 写入 `outputs/knowledge_roadmaps.jsonl`

这两个文件刻意分开，避免 Blind User 误读完整 roadmap。

`blind_user_case_views.jsonl` 只包含用户问题、开场意图、用户可见 facts 和 forbidden content。

`knowledge_roadmaps.jsonl` 包含完整 roadmap，供 Knowledge Module 和 runtime 控制使用。

第三阶段：在线模拟

1. 根据 `--case_id` 从 `outputs/knowledge_roadmaps.jsonl` 读取预生成路书
2. 读取 `outputs/employee_personas.jsonl` 和 `outputs/user_behavior_taxonomy.jsonl`
3. `Simulator.start()` 用 LLM 生成初始用户发言
4. 人工在命令行输入 assistant 回复
5. `Simulator.step()` 串起：
    - Blind User 解析 assistant act
    - Knowledge Module 做知识决策
    - Blind User 生成自然用户回复
    - 更新 dialogue state
    - 写入 simulation log
6. 如果 LLM 判断已解决，或达到 `--max_turns`，对话结束

注意：历史对话只负责总结用户行为结构，不参与 target case 的知识点抽取，也不生成 roadmap。

## 3. 根目录文件

### `main.py`

命令行入口，负责三个阶段的 CLI。

主要职责：

- 解析命令行参数
- 读取配置
- 初始化 LLM client
- `mine-behavior`: 挖掘历史对话行为
- `analyze-cases`: 批量分析 case 并生成可复用路书
- `simulate`: 读取预生成路书并运行对话
- 打印用户模拟器回复
- 接收人工输入的 assistant 回复

真实 assistant 的未来接入点也在这里：

```python
assistant_text = input("Assistant> ").strip()
# Real assistant integration point:
# Replace the manual input above with a call to your enterprise assistant.
```

后续接入真实 assistant 时，可以把这一行替换为：

```python
assistant_text = call_real_assistant(
    user_text=simulator.dialogue_history[-1]["content"],
    dialogue_history=simulator.dialogue_history,
    config=config.get("assistant", {}),
)
print(f"Assistant> {assistant_text}")
```

### `config.yaml`

配置 LLM 和路径。

当前默认配置使用 mentor 提供的 OpenAI SDK-compatible 接入方式：

```yaml
llm:
  provider: "openai-compatible"
  base_url: "http://10.67.43.7:12345/v1"
  endpoint: ""
  api_key: "sk-1234"
  model: "qwen3"
  temperature: 0.2
  max_tokens: 4096
  timeout: 300
  top_p: 0.5
  presence_penalty: 1.5
  top_k: 1
  enable_thinking: false
```

路径配置默认指向之前版本使用的真实案例库：

```yaml
paths:
  cases: "../../RUNTIME/raw_data/格式化案例库/uniknow-full-text.json"
  output_dir: "outputs"

case_fields:
  case_id: "__key__"
  title: "case_name"
  phenomenon: "text"
  solution: "text"

dialogue_fields:
  dialogue_id: "__key__"
  case_id: "caseId"
  final_case_id: "final_case_id"
  resolved: "resolved"
  turns: "text"
  speaker: "speaker"
  text: "text"
```

这里的 `case_id` 不是替代案例库路径，而是在已经加载的案例库中选择目标案例。真实案例库通常是一个大文件，运行一次模拟必须指定“这次围绕哪个 target case”。

### 案例库数据

正式运行不使用项目内 sample case。案例库必须来自 `config.yaml` 的真实路径：

```yaml
paths:
  cases: "../../RUNTIME/raw_data/格式化案例库/uniknow-full-text.json"
```

如果这个文件不存在，程序会直接报错，不会回退到样例数据。

### `README.md`

项目简要说明、运行命令和 outputs 解释。

### `.gitignore`

忽略 Python 缓存、pytest 缓存和运行产物。

## 4. `src/schemas.py`

这是项目的数据结构中心。所有 LLM 输出最终都要被 Pydantic schema 校验。

主要 schema：

### `Case`

表示一个客服案例。

字段：

- `case_id`
- `title`
- `phenomenon`
- `solution`

### `RetrievalQuery`

表示 LLM 生成的 related case 检索 query。

字段：

- `query_type`: `surface_query` / `diagnostic_query` / `solution_query`
- `query`
- `reason`

### `Point`

表示从 target case 和 related cases 中抽取出来的知识点。

字段包括：

- `point_id`
- `source_case_id`
- `content`
- `source_field`
- `source_quote`
- `point_type`
- `grounding_type`
- `trigger`
- `visibility`
- `leakage_risk`
- `reason`

`point_type` 分四类：

- `user_facing`: 用户能直接看到的表面问题
- `diagnostic`: 被 assistant 追问后才释放的诊断信息
- `solution`: 只用于 Knowledge Module 判断是否 solved，不能直接泄露给 Blind User
- `external`: related cases 中的外部/混淆方向

### `PointVerificationResult`

表示 point 校验结果。

字段：

- `verified_points`
- `dropped_points`
- `warnings`

### `Relation`

表示 point 之间的关系。

支持的关系包括：

- `specifies`
- `asks_for`
- `supports_target`
- `solution_addresses`
- `similar_but_wrong`
- `rules_out`
- `out_of_scope`

### `Roadmap`

运行时使用的路线图。

字段：

- `target_case_id`
- `surface_problem`
- `opening_intent`
- `user_facing_points`
- `diagnostic_points`
- `solution_points`
- `external_points`
- `relations`
- `target_route`
- `external_routes`
- `forbidden_content`

Blind User 不直接读取完整 roadmap。roadmap 主要给 Knowledge Module 使用。

### `DialogueState`

记录对话状态。

字段：

- `turn_count`
- `exposed_point_ids`
- `rejected_external_point_ids`
- `action_request_count`
- `how_to_check_count`
- `max_how_to_check`
- `solution_status`
- `should_stop`
- `stop_reason`

注意：状态更新来自 LLM 返回的 `KnowledgeDecision.state_update`，不是程序用关键词规则判断出来的。

### `AssistantAct`

Blind User 对 assistant 回复类型的 LLM 分类结果。

可能类型：

- `clarification_question`
- `action_request`
- `solution_output`
- `generic_advice`
- `irrelevant`
- `unknown`

### `KnowledgeDecision`

Knowledge Module 的核心输出。

它决定：

- assistant 命中了什么 scope
- 是否匹配某个 point
- 本轮决策是什么
- Blind User 允许说什么
- dialogue state 如何更新

### `SimulationTurnLog`

单轮对话日志。

包含：

- turn
- assistant_text
- assistant_act
- knowledge_decision
- user_reply
- state

## 5. LLM 接入层：`src/llm/`

### `llm_client.py`

定义统一 LLM 接口：

```python
class LLMClient(ABC):
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_name: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        ...
```

所有模块都只依赖这个接口，因此后续替换公司 LLM 时，不需要改业务模块。

### `openai_compatible_client.py`

真实 LLM client。

职责：

- 从 `config.yaml` 或环境变量读取 LLM 配置
- 使用 `from openai import OpenAI` 的 SDK 形式请求公司 qwen3 服务
- 要求模型返回 JSON object
- 从返回文本中提取 JSON

支持环境变量：

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_TEMPERATURE`

### `mock_llm_client.py`

测试专用 mock client。

注意：正式运行不使用它。它只用于 `tests/`，保证测试可以在没有真实 qwen3 服务的情况下跑通。

## 6. 数据加载：`src/data_loader.py`

提供两个函数：

- `load_cases(path, case_fields)`: 读取 JSON / JSONL case 数据，并按字段映射转换为内部 `Case`
- `get_case(cases, case_id)`: 根据 case_id 找 target case

## 7. Retrieval 阶段：`src/retrieval/`

### `query_generator.py`

类：`QueryGenerator`

核心方法：

```python
generate_queries(target_case: Case) -> List[RetrievalQuery]
```

职责：

- 输入 target case
- 用 LLM 生成 3 到 6 个 related case 检索 query
- 输出 `RetrievalQuery`
- 写入 `outputs/generated_queries.jsonl`

### `related_case_retriever.py`

类：`RelatedCaseRetriever`

核心方法：

```python
retrieve(
    target_case: Case,
    queries: List[RetrievalQuery],
    all_cases: List[Case],
) -> List[Case]
```

职责：

- 输入 target case、queries、全量 case library
- 先用本地快速召回从全量案例库里筛出 `candidate_top_n` 个候选，默认 50
- 再让 LLM 只从这 50 个候选里选择最终 related cases，默认最多 5 个
- 本地召回只负责缩小候选范围，不负责最终 relatedness 判断
- 写入 `outputs/related_cases.jsonl`

为什么必须这样做：

```text
全案例库
  -> 本地快速召回 top 50
  -> LLM 精选 related cases top 5
```

如果案例库达到几百万行，不能把全库直接塞进 LLM prompt。否则会非常慢，并且很容易超过上下文长度。

这里的“反向 RAG”可以理解为：

```text
不是让 LLM 直接阅读全案例库
而是先把 target case 变成多个检索方向
再用这些方向从案例库里召回候选 case
最后让 LLM 对候选 case 做精选和解释
```

当前实现是轻量版反向 RAG：`QueryGenerator` 生成检索方向，`LocalCandidateRecall` 做本地候选召回，`RelatedCaseRetriever` 调 LLM 做最终选择。

### `prompt_templates.py`

放 retrieval 相关 prompt：

- query generation prompt
- related case selection prompt

## 8. Extraction 阶段：`src/extraction/`

### `point_extractor.py`

类：`PointExtractor`

核心方法：

```python
extract_points(
    target_case: Case,
    related_cases: List[Case],
) -> List[Point]
```

职责：

- 用 LLM 从 target case 和 related cases 中抽取 points
- 生成四类 point：
  - user_facing
  - diagnostic
  - solution
  - external
- 写入 `outputs/points.jsonl`

### `point_verifier.py`

类：`PointVerifier`

核心方法：

```python
verify_points(
    target_case: Case,
    related_cases: List[Case],
    points: List[Point],
) -> PointVerificationResult
```

职责：

- 用 LLM 检查 points 是否 grounded
- 检查 solution 是否可能泄露
- 检查 external point 是否覆盖 target point
- 输出 verified / dropped / warnings
- 写入 `outputs/verified_points.jsonl`

### `prompt_templates.py`

放 extraction 相关 prompt：

- point extraction prompt
- point verification prompt

## 9. Roadmap 阶段：`src/roadmap/`

### `relation_builder.py`

类：`RelationBuilder`

核心方法：

```python
build_relations(points: List[Point], case_id: str = "") -> List[Relation]
```

职责：

- 用 LLM 建立 point 之间的关系
- 输出最小但有用的 relation set
- 写入 `outputs/relations.jsonl`

### `roadmap_builder.py`

类：`RoadmapBuilder`

核心方法：

```python
build_roadmap(
    target_case: Case,
    points: List[Point],
    relations: List[Relation],
) -> Roadmap
```

职责：

- 用 LLM 将 verified points 和 relations 组装为 roadmap
- 生成 surface problem、opening intent、target route、external routes、forbidden content
- 写入 `outputs/roadmaps.jsonl`

### `prompt_templates.py`

放 roadmap 相关 prompt：

- relation building prompt
- roadmap assembly prompt

## 10. Runtime 阶段：`src/runtime/`

### `simulator.py`

类：`Simulator`

核心方法：

```python
start() -> str
step(assistant_text: str) -> Dict[str, Any]
```

职责：

- 保存 dialogue history
- 保存 dialogue state
- 调用 Blind User 和 Knowledge Module
- 每轮生成用户回复
- 写入 `outputs/simulation_logs.jsonl`

`step()` 内部流程：

1. 记录 assistant 最新回复
2. `BlindUser.parse_assistant_act()` 用 LLM 分类 assistant act
3. `KnowledgeModule.decide()` 用 LLM 做知识匹配和行为决策
4. `BlindUser.render_reply()` 用 LLM 生成自然用户回复
5. 应用 LLM 返回的 state update
6. 写 turn log

### `blind_user.py`

类：`BlindUser`

职责：

- `initial_reply()`: 用 LLM 生成初始用户开场
- `parse_assistant_act()`: 用 LLM 判断 assistant 回复类型
- `render_reply()`: 根据 Knowledge Module instruction 生成自然语言回复

Blind User prompt 会明确要求模拟用户带着真实解决问题的动机：

- 用户不是闲聊，而是工作被 IT 问题影响，想尽快恢复；
- 开场要体现“我希望你帮我解决/诊断/给下一步”；
- 被追问时，如果 roadmap 允许，就补充有助于排障的信息；
- 被要求操作时，如果 instruction 允许，就追问怎么做或表示会尝试；
- assistant 问偏时，用户会把对话拉回自己的问题；
- 但所有表达都不能突破 `allowed_content` 和 `forbidden_content`。

Blind User 的限制：

- 不直接看完整 solution
- 不直接判断 solution 是否正确
- 不决定释放哪个 fact
- 只使用 Knowledge Module 给的 `allowed_content`

### `knowledge_module.py`

类：`KnowledgeModule`

职责：

- 读取 roadmap、state、persona、dialogue history
- 用 LLM 判断 assistant 回复命中：
  - `case_internal`
  - `case_external`
  - `out_of_knowledge`
  - `target_solution`
  - `generic`
  - `unknown`
- 用 LLM 决定：
  - reveal fact
  - clarify or deny
  - ask how to perform
  - confirm and stop
  - continue
  - impatient stop
- 返回 `KnowledgeDecision`

### `dialogue_state.py`

导出 `DialogueState`。

### `prompt_templates.py`

放 runtime 相关 prompt：

- assistant act parsing
- knowledge decision
- blind user reply rendering
- initial user opening

## 11. 工具层：`src/utils/`

### `json_utils.py`

职责：

- 从 LLM 返回文本中提取 JSON object
- 提供 JSON dump 工具

### `jsonl.py`

职责：

- 读取 JSONL
- 写入 JSONL
- 追加 JSONL

### `logging.py`

类：`OutputLogger`

职责：

- 将每个模块的 input/output 统一写入 `outputs/*.jsonl`
- 每条记录包含：
  - `case_id`
  - `module`
  - `input`
  - `output`
  - `timestamp`

## 12. Assistant 接入预留：`src/assistant/`

当前 `src/assistant/` 只保留包结构，没有真实实现。

目前 assistant 回复由命令行人工输入：

```text
Assistant>
```

后续接入真实 assistant 时，推荐在 `src/assistant/` 下新增一个 client，例如：

```text
src/assistant/enterprise_assistant_client.py
```

然后在 `main.py` 的 runtime loop 中替换人工输入。

## 13. Behavior Mining 阶段：`src/behavior_mining/`

这个模块用于从历史对话中学习真实公司员工用户行为。

它不参与：

- target case 选择
- related case retrieval
- point extraction
- roadmap assembly
- solution 判断

它只产出行为侧资产：

- Employee Persona Library
- User Behavior Taxonomy
- Dialogue Behavior Summaries

### `dialogue_loader.py`

负责加载历史对话。

支持：

- JSONL，每行一个 dialogue
- JSON list
- keyed JSON dict
- 旧项目中类似 `text` 字段的角色前缀对话

输出内部 schema：

```python
HistoricalDialogue
```

字段包括：

- `dialogue_id`
- `case_id`
- `final_case_id`
- `resolved`
- `turns`

### `behavior_miner.py`

总控类：`DialogueBehaviorMiner`

核心流程：

1. `summarize_dialogue()` 对每条 dialogue 调 LLM，生成 `DialogueBehaviorSummary`
2. `PersonaMiner` 汇总 summaries，生成 `EmployeePersona`
3. `BehaviorTaxonomyMiner` 汇总 summaries，生成 `BehaviorTaxonomy`
4. 写入三个 outputs 文件

### `persona_miner.py`

类：`PersonaMiner`

职责：

- 从多个 dialogue summaries 中总结真实员工 persona
- 输出 3 到 6 类常见员工画像
- persona 必须有 dialogue evidence 支撑

输出 schema：

```python
EmployeePersona
```

### `behavior_taxonomy_miner.py`

类：`BehaviorTaxonomyMiner`

职责：

- 从历史对话中总结用户行为分类
- 关注用户面对不同 assistant act 时的反应

典型行为包括：

- answer_fact
- reveal_new_fact
- ask_how_to_perform
- attempt_action
- deny_or_correct
- say_unknown
- accept_solution
- reject_solution
- express_frustration
- repeat_surface_problem

输出 schema：

```python
BehaviorTaxonomy
```

### `prompt_templates.py`

放 behavior mining 相关 prompt：

- single dialogue behavior summary
- persona mining
- behavior taxonomy mining

## 14. Outputs

运行时会生成或追加以下文件：

### `outputs/generated_queries.jsonl`

保存 reverse RAG query generation 的输入输出。

### `outputs/related_cases.jsonl`

保存 related case selection 的输入输出。

### `outputs/points.jsonl`

保存 point extraction 的输入输出。

### `outputs/verified_points.jsonl`

保存 point verification 的输入输出。

### `outputs/relations.jsonl`

保存 relation building 的输入输出。

### `outputs/roadmaps.jsonl`

保存 roadmap assembly 的输入输出。

### `outputs/blind_user_case_views.jsonl`

保存每个 case 给 Blind User 的安全视图。这个文件不包含完整 roadmap，也不包含 solution points。

### `outputs/knowledge_roadmaps.jsonl`

保存每个 case 给 Knowledge Module/runtime 使用的完整路书。后续 `simulate` 默认读取这个文件，不再现场重新运行 retrieval、extraction、roadmap。

每条 knowledge roadmap 包含：

- target case
- retrieval queries
- related cases
- verified points
- relations
- roadmap

### `outputs/simulation_logs.jsonl`

保存每一轮 runtime 对话日志。

### `outputs/dialogue_behavior_summaries.jsonl`

保存每条历史对话的行为结构化总结。

### `outputs/employee_personas.jsonl`

保存从历史对话中挖掘出的真实员工 persona library。

如果这个文件不存在，runtime 会自动读取人工种子版本：

```text
data/manual_seed_employee_personas.jsonl
```

内置 persona id：

```text
persona_real_problem_low_tech
```

### `outputs/user_behavior_taxonomy.jsonl`

保存从历史对话中挖掘出的用户行为分类与 simulator policy hint。

如果这个文件不存在，runtime 会自动读取人工种子版本：

```text
data/manual_seed_user_behavior_taxonomy.jsonl
```

人工种子 taxonomy 包含：

```text
陈述或继续澄清问题
回答客服并释放信息
询问具体操作办法
尝试操作并反馈结果
方向不符时纠正或拉回问题
确认解决或继续求助
```

### `outputs/review/`

保存人工可读 Markdown review 文件。由下面命令生成：

```bash
python3 main.py export-review --case_id <真实案例ID>
python3 main.py export-review --all
```

包含：

```text
index.md
behavior_assets.md
<case_id>.md
```

用于人工检查 Blind User 可见信息、roadmap、solution point、external point、related cases 和 warnings。

## 15. Runtime 行为优先级

runtime 中不同信息源的优先级如下：

1. Roadmap / Knowledge Module factual constraint 最高，决定 allowed_content，防止泄露 solution。
2. Dialogue State 第二，决定是否已经说过、是否重复追问、是否超过 patience。
3. Behavior Taxonomy 第三，决定面对追问、动作要求、方案输出时采用哪类行为。
4. Employee Persona 第四，决定表达风格和自然语言难度。

因此：

- 不能因为 persona 是 cooperative，就泄露 roadmap 不允许的 fact。
- 不能因为 taxonomy 里用户会主动补充，就说出 forbidden content。
- case / related cases 负责知识结构。
- historical dialogues 只负责行为结构。

## 16. Tests

测试目录：

```text
tests/
  test_behavior_mining.py
  test_point_extraction.py
  test_roadmap_builder.py
  test_runtime.py
```

测试使用 `MockLLMClient`，不依赖真实 qwen3 服务。

测试覆盖：

- LLM 输出能被 Pydantic schema parse
- PointExtractor 返回四类 point
- PointVerifier 返回 verified points
- RoadmapBuilder 生成 surface problem 和 target route
- Simulator.step 能串起 assistant act、knowledge decision、blind user reply
- solved 状态下 `should_stop == true`
- DialogueBehaviorMiner 能产出 summaries、personas、taxonomy 三类文件

## 17. 如何运行

进入项目目录：

```bash
cd /Users/srdluo/Desktop/华为实习/User_simulator2.0
```

确认 qwen3 服务已经启动，并且 `config.yaml` 中 base_url 正确：

```yaml
base_url: "http://10.67.43.7:12345/v1"
model: "qwen3"
```

确认 `config.yaml` 中案例库路径正确：

```yaml
paths:
  cases: "../../RUNTIME/raw_data/格式化案例库/uniknow-full-text.json"
  dialogues: "../../RUNTIME/raw_data/格式化对话记录/用户和坐席交互09-proceed-full.json"
```

先运行历史对话行为挖掘：

```bash
python3 main.py mine-behavior --max_dialogues 20
```

如果要指定历史对话文件：

```bash
python3 main.py mine-behavior --dialogues /path/to/dialogues.jsonl --max_dialogues 50
```

如果不知道真实案例库里有哪些 ID，可以先列出前 20 条：

```bash
python3 main.py simulate --list_cases 20
```

批量分析前 20 个 case，提前生成路书：

```bash
python3 main.py analyze-cases --limit 20
```

换下一批 case：

```bash
python3 main.py analyze-cases --limit 20 --offset 20
```

随机抽样 case：

```bash
python3 main.py analyze-cases --limit 20 --random --seed 42
```

或者只分析指定 case：

```bash
python3 main.py analyze-cases --case_ids <真实案例ID_1> <真实案例ID_2>
```

注意：`blind_user_case_views.jsonl` 和 `knowledge_roadmaps.jsonl` 会按 `case_id` upsert，不会因为换一批分析就覆盖掉旧 case。

运行 demo，其中 `--case_id` 要换成已经分析过的真实案例 ID：

```bash
python3 main.py simulate --case_id <真实案例ID> --persona low_tech
```

可选 persona：

```text
low_tech
cooperative
impatient
vague
```

指定最大轮数：

```bash
python3 main.py simulate --case_id <真实案例ID> --persona low_tech --max_turns 8
```

如果已经挖掘出 employee personas，可以指定：

```bash
python3 main.py simulate --case_id <真实案例ID> --persona_id persona_xxx
```

运行后，程序会先生成用户开场：

```text
User: 我这边 Outlook 一打开就退出来了，帮我看一下。
Assistant>
```

你在 `Assistant>` 后人工输入 assistant 回复：

```text
Assistant> 是登录不上还是打开就退出？
```

程序会继续生成用户回复：

```text
User: 是打开以后就直接退出来了，还没到登录那一步。
```

如果 assistant 给出正确方案，Knowledge Module 判断 solved 后会结束：

```text
Assistant> 你可以先结束 Outlook 的残留进程再重新打开。
User: 好的，那我按这个方法试一下。
[STOP: solved]
```

## 18. 如何运行测试

进入项目目录：

```bash
cd /Users/srdluo/Desktop/华为实习/User_simulator2.0
```

运行：

```bash
python3 -m pytest tests
```

编译检查：

```bash
python3 -m compileall .
```

## 19. 常见问题

### 1. `python` 命令不存在

使用：

```bash
python3 main.py --case_id <真实案例ID> --persona low_tech
```

### 2. 连接不上 qwen3

检查：

- qwen3 服务是否启动
- `config.yaml` 里的 base_url 是否正确
- 是否需要设置 `LLM_BASE_URL`
- 端口是否是 `12345`

### 3. LLM 返回不是合法 JSON

当前所有模块都要求 LLM 返回 JSON。如果失败，优先检查对应模块的 `prompt_templates.py`。

也可以查看 `outputs/` 中前一步是否已经成功写入。

### 4. 用户回复泄露 solution

检查：

- extraction prompt 中 solution point 是否设为 `judge_only`
- verification prompt 是否给出 warning
- roadmap 的 `forbidden_content`
- runtime knowledge decision prompt 是否遵守 forbidden content

## 20. 后续扩展建议

### 接入真实 assistant

推荐新增：

```text
src/assistant/enterprise_assistant_client.py
```

并在 `main.py` 的 runtime loop 中替换人工输入。

### 修改真实 case 数据路径

在 `config.yaml` 中修改：

```yaml
paths:
  cases: "your_real_case_file.json_or_jsonl"
```

### 加入 Dialogue Behavior Miner

历史对话分析模块后续可以独立加入，用于分析：

- 真实用户通常怎么开场
- 真实用户主动说哪些信息
- 哪些信息通常被追问后才说
- 用户遇到问偏时怎么反应
- 用户是否追问操作方法
- low_tech 用户会卡在哪里
- 一轮、两轮、三轮后用户一般补充什么

这些结果未来可以影响：

- surface problem prompt
- information release prompt
- action request policy
- persona behavior policy
