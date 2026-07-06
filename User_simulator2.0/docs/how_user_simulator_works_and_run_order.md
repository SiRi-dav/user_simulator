# User Simulator 2.0 工作原理与运行顺序

这份文档用比较直白的方式说明当前用户模拟器是怎么做的，以及先后应该运行哪些程序。

## 1. 一句话总结

当前用户模拟器是：

```text
案例库负责“用户知道什么”
历史对话负责“用户像什么人、怎么反应”
Knowledge Module 负责“本轮允许说什么”
Blind User 负责“把允许说的内容自然说出来”
LLM 负责所有抽取、分类、匹配、决策和生成
```

它不是泛聊天机器人，而是围绕一个目标 case 模拟真实员工用户和企业 IT 客服 assistant 的多轮对话。

## 2. 两条主线

这个系统由两条线组成：

```text
Case Knowledge Line
Dialogue Behavior Line
```

### 2.1 Case Knowledge Line

这条线只看案例库，不看历史对话。

它负责回答：

```text
这个目标 case 里，用户到底知道什么？
哪些事实可以开场说？
哪些事实必须被追问后才说？
哪些内容是 solution，不能提前泄露？
assistant 给什么方案才算 solved？
哪些 related cases 是容易问偏的方向？
```

流程是：

```text
target case
→ related case retrieval
→ point extraction
→ point verification
→ relation building
→ roadmap assembly
```

最终产物是：

```text
roadmap
```

roadmap 决定事实边界，也就是：

```text
用户能说什么，不能说什么。
```

### 2.2 Dialogue Behavior Line

这条线只看历史客服对话，不参与案例知识抽取。

它负责回答：

```text
真实公司员工一般怎么开场？
被客服追问时是直接回答，还是只给部分信息？
被要求操作时会不会问“怎么做”？
遇到客服问偏时会不会纠正？
方案具体时会不会接受？
用户会不会不耐烦？
```

流程是：

```text
historical dialogues
→ dialogue behavior summaries
→ employee persona library
→ user behavior taxonomy
```

最终产物是：

```text
outputs/dialogue_behavior_summaries.jsonl
outputs/employee_personas.jsonl
outputs/user_behavior_taxonomy.jsonl
```

这条线决定行为风格，也就是：

```text
用户怎么反应，怎么说。
```

但它不能突破 roadmap 的事实约束。

## 3. 正确运行顺序

推荐顺序是：

```text
1. 确认配置
2. 先运行历史对话行为挖掘
3. 查看真实案例库里的 case id
4. 选择一个 target case 运行模拟
5. 人工输入 assistant 回复
```

## 4. 第一步：进入项目目录

如果使用 GitHub 分支里的版本：

```bash
cd /Users/srdluo/Desktop/华为实习/enterprise_user_simulator/User_simulator2.0
```

如果使用桌面外层同步版本：

```bash
cd /Users/srdluo/Desktop/华为实习/User_simulator2.0
```

建议以后以 Git 仓库里的版本为准：

```text
enterprise_user_simulator/User_simulator2.0
```

## 5. 第二步：确认配置

查看：

```text
config.yaml
```

里面最重要的是：

```yaml
llm:
  endpoint: "http://localhost:8850/v1/chat/completions"
  model: "qwen3-32b"

paths:
  cases: "../../RUNTIME/raw_data/格式化案例库/uniknow-full-text.json"
  dialogues: "../../RUNTIME/raw_data/格式化对话记录/用户和坐席交互09-proceed-full.json"
  output_dir: "outputs"
```

含义：

- `cases`: 真实案例库路径
- `dialogues`: 历史客服对话记录路径
- `output_dir`: 中间结果输出目录
- `llm`: 公司 qwen32b 接入方式

如果真实数据文件不在这个位置，需要改 `config.yaml`。

## 6. 第三步：运行历史对话行为挖掘

运行：

```bash
python3 main.py mine-behavior
```

这一步读取：

```text
paths.dialogues
```

然后通过 LLM 分析历史对话，输出：

```text
outputs/dialogue_behavior_summaries.jsonl
outputs/employee_personas.jsonl
outputs/user_behavior_taxonomy.jsonl
```

如果想先少跑一点，例如前 20 条：

```bash
python3 main.py mine-behavior --max_dialogues 20
```

如果历史对话文件不在配置路径里，可以手动指定：

```bash
python3 main.py mine-behavior --dialogues /path/to/dialogues.jsonl --max_dialogues 20
```

## 7. 第四步：查看真实案例库里的 case id

运行：

```bash
python3 main.py simulate --list_cases 20
```

它会打印真实案例库前 20 条：

```text
CASE_xxx    某个案例标题
CASE_yyy    另一个案例标题
```

这里的 `case_id` 只是用来从真实案例库中选择 target case，不是替代案例库路径。

## 8. 第五步：选择一个 case 运行模拟

基础命令：

```bash
python3 main.py simulate --case_id <真实案例ID>
```

指定内置 persona：

```bash
python3 main.py simulate --case_id <真实案例ID> --persona low_tech
```

如果已经跑过 `mine-behavior`，并且有挖掘出的 persona，可以指定：

```bash
python3 main.py simulate --case_id <真实案例ID> --persona_id <persona_id>
```

如果不传 `persona_id`，程序会：

1. 优先读取 `outputs/employee_personas.jsonl` 里的第一个 persona；
2. 如果没有挖掘结果，再使用内置 persona，例如 `low_tech`。

指定最大轮数：

```bash
python3 main.py simulate --case_id <真实案例ID> --max_turns 8
```

## 9. 第六步：人工输入 assistant 回复

simulate 启动后，程序会先生成用户开场：

```text
User: 我这边 Outlook 一打开就退出来了，帮我看一下。
Assistant>
```

你在 `Assistant>` 后手动输入客服回复：

```text
Assistant> 是登录不上还是打开就退出？
```

程序会生成下一句用户回复：

```text
User: 是打开以后就直接退出来了，还没到登录那一步。
```

继续输入 assistant 回复，直到：

- LLM 判断 assistant 命中目标 solution；
- 或达到最大轮数。

## 10. simulate 内部做了什么

当运行：

```bash
python3 main.py simulate --case_id <真实案例ID>
```

内部会按顺序执行以下步骤。

### 10.1 读取真实案例库

程序读取 `config.yaml` 里的：

```yaml
paths.cases
```

然后用：

```bash
--case_id <真实案例ID>
```

选择目标 case。

### 10.2 QueryGenerator

文件：

```text
src/retrieval/query_generator.py
```

作用：

```text
用 LLM 根据 target case 生成 related case 检索 query。
```

输出：

```text
outputs/generated_queries.jsonl
```

### 10.3 RelatedCaseRetriever

文件：

```text
src/retrieval/related_case_retriever.py
```

作用：

```text
把 target case、queries、candidate cases 交给 LLM，让 LLM 选择 related cases。
```

related cases 用来构造混淆知识空间，例如：

```text
表面症状类似但原因不同的 case
solution 操作类似的 case
容易问偏的 case
```

输出：

```text
outputs/related_cases.jsonl
```

### 10.4 PointExtractor

文件：

```text
src/extraction/point_extractor.py
```

作用：

```text
用 LLM 从 target case 和 related cases 中抽取 points。
```

point 分四类：

```text
user_facing: 用户开场能说的表面问题
diagnostic: 被追问后才说的隐藏诊断事实
solution: 只用于判断是否解决，不能泄露
external: related case 中的混淆方向
```

输出：

```text
outputs/points.jsonl
```

### 10.5 PointVerifier

文件：

```text
src/extraction/point_verifier.py
```

作用：

```text
用 LLM 校验 points 是否有依据、是否幻觉、是否泄露 solution。
```

输出：

```text
outputs/verified_points.jsonl
```

### 10.6 RelationBuilder

文件：

```text
src/roadmap/relation_builder.py
```

作用：

```text
用 LLM 建立 point 之间的关系。
```

关系包括：

```text
specifies
supports_target
solution_addresses
similar_but_wrong
rules_out
```

输出：

```text
outputs/relations.jsonl
```

### 10.7 RoadmapBuilder

文件：

```text
src/roadmap/roadmap_builder.py
```

作用：

```text
用 LLM 组装最终 roadmap。
```

roadmap 包含：

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

输出：

```text
outputs/roadmaps.jsonl
```

roadmap 是后续对话的事实边界。

### 10.8 Simulator.start

文件：

```text
src/runtime/simulator.py
```

作用：

```text
Blind User 用 LLM 根据 surface_problem、opening_intent、employee persona 生成第一句用户开场。
```

### 10.9 Simulator.step

每输入一轮 assistant 回复，都会执行：

```text
assistant_text
→ BlindUser.parse_assistant_act
→ KnowledgeModule.decide
→ BlindUser.render_reply
→ update DialogueState
→ write simulation log
```

`BlindUser.parse_assistant_act` 判断 assistant 回复类型：

```text
clarification_question
action_request
solution_output
generic_advice
irrelevant
unknown
```

`KnowledgeModule.decide` 决定：

```text
assistant 命中 case_internal / case_external / out_of_knowledge / target_solution？
本轮允许用户说什么？
是否停止？
state 怎么更新？
```

`BlindUser.render_reply` 把 `allowed_content` 改写成自然用户话术。

每轮日志输出：

```text
outputs/simulation_logs.jsonl
```

## 11. behavior mining 的结果如何进入 runtime

`mine-behavior` 产出的结果会在 simulate 时被读取：

```text
outputs/employee_personas.jsonl
outputs/user_behavior_taxonomy.jsonl
```

### 11.1 进入 Knowledge Module

Knowledge Module prompt 会看到 behavior taxonomy。

它会参考真实用户行为分类决定反应类型，例如：

```text
assistant 要求用户操作时，低技术用户可能会先问怎么做
assistant 问偏时，用户会纠正并拉回原问题
assistant 给具体方案时，用户会接受并表示尝试
```

但它不能突破 roadmap。

也就是说：

```text
taxonomy 决定怎么反应
roadmap 决定能说什么事实
```

### 11.2 进入 Blind User

Blind User prompt 会看到 employee persona。

它负责把 Knowledge Module 给出的 `allowed_content` 改写成自然表达。

例如同样的 allowed content：

```text
是打开以后就直接退出来了，还没到登录那一步。
```

不同 persona 可能表达为：

```text
低技术用户：我也不太懂，就是点开以后自己退了，还没看到登录的地方。
配合型用户：是打开后直接退出，还没有进入登录页面。
急躁型用户：就是一点开就退了，还没到登录，这个挺急的。
```

但 Blind User 不能新增 allowed_content 之外的事实。

## 12. runtime 优先级

runtime 中优先级是：

```text
1. Roadmap / Knowledge Module factual constraint
2. Dialogue State
3. Behavior Taxonomy
4. Employee Persona
```

含义：

- roadmap 决定事实边界；
- state 决定已经说过什么、是否该停；
- taxonomy 决定面对不同 assistant act 怎么反应；
- persona 决定怎么自然表达。

因此：

```text
不能因为 persona 很配合，就主动泄露 solution。
不能因为历史对话里用户经常补充很多信息，就说出 roadmap 不允许的 fact。
```

## 13. 最推荐的完整命令顺序

进入项目：

```bash
cd /Users/srdluo/Desktop/华为实习/enterprise_user_simulator/User_simulator2.0
```

先挖历史行为：

```bash
python3 main.py mine-behavior --max_dialogues 20
```

看有哪些 case：

```bash
python3 main.py simulate --list_cases 20
```

选择一个 case 跑模拟：

```bash
python3 main.py simulate --case_id <真实案例ID> --max_turns 8
```

如果想指定挖掘出的 persona：

```bash
python3 main.py simulate --case_id <真实案例ID> --persona_id <persona_id> --max_turns 8
```

运行测试：

```bash
python3 -m pytest tests
```

编译检查：

```bash
python3 -m compileall .
```

## 14. 关键边界

最重要的边界是：

```text
历史对话用于学习行为，不用于决定答案。
case knowledge 用于决定答案，不用于模仿真实用户行为。
```

换句话说：

```text
Knowledge Module 解决“说什么是对的”
Behavior Miner 解决“真实用户会怎么反应”
Blind User 解决“怎么自然地说出来”
```
