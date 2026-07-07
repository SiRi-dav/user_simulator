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
outputs/blind_user_case_views.jsonl
outputs/knowledge_roadmaps.jsonl
```

每个 case 会提前生成两份文件：

```text
blind_user_case_views.jsonl: 给 Blind User 看的用户问题、开场意图、可见事实
knowledge_roadmaps.jsonl: 给 Knowledge Module 看的完整知识 roadmap
```

这里说的 roadmap，不是给 Blind User 看的材料。它是 Knowledge Module 用来控制对话的信息范围：

```text
哪些 fact 允许透露；
哪些 fact 需要被问到才透露；
哪些 solution 内容只能用于判断，不能提前泄露；
assistant 的方案是否命中 target solution。
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
4. 批量运行案例分析，提前生成多个 case 的路书
5. 选择一个已经分析过的 case 运行模拟
6. 人工输入 assistant 回复
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
  base_url: "http://10.67.43.7:12345/v1"
  api_key: "sk-1234"
  model: "qwen3"

paths:
  cases: "../../RUNTIME/raw_data/格式化案例库/uniknow-full-text.json"
  dialogues: "../../RUNTIME/raw_data/格式化对话记录/用户和坐席交互09-proceed-full.json"
  output_dir: "outputs"
```

含义：

- `cases`: 真实案例库路径
- `dialogues`: 历史客服对话记录路径
- `output_dir`: 中间结果输出目录
- `llm`: 公司 qwen3/OpenAI SDK-compatible 接入方式

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

在运行模拟前，先批量生成 case 分析结果。

例如预处理前 20 个 case：

```bash
python3 main.py analyze-cases --limit 20
```

换下一批 20 个 case：

```bash
python3 main.py analyze-cases --limit 20 --offset 20
```

随机抽 20 个 case：

```bash
python3 main.py analyze-cases --limit 20 --random --seed 42
```

或者只预处理指定 case：

```bash
python3 main.py analyze-cases --case_ids <真实案例ID_1> <真实案例ID_2>
```

这一步会输出：

```text
outputs/blind_user_case_views.jsonl
outputs/knowledge_roadmaps.jsonl
```

这两个最终 artifact 文件按 `case_id` upsert：

```text
新 case 会追加
重复 case 会替换
旧的其他 case 会保留
```

因此可以分批运行：

```bash
python3 main.py analyze-cases --limit 20 --offset 0
python3 main.py analyze-cases --limit 20 --offset 20
python3 main.py analyze-cases --limit 20 --offset 40
```

最终 `knowledge_roadmaps.jsonl` 会累计这些批次中成功分析完成的 case。

`blind_user_case_views.jsonl` 每一行是一个安全视图，只包含：

```text
case_id
surface_problem
opening_intent
user_facing_points
forbidden_content
```

`knowledge_roadmaps.jsonl` 每一行是给 Knowledge Module 的完整路书，包括：

```text
retrieval queries
related cases
verified points
relations
roadmap
```

后续 `simulate` 只读取 `knowledge_roadmaps.jsonl` 中对应 case 的 roadmap，不再现场重新跑 retrieval / extraction / roadmap。

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

## 9.5 导出人工可读 Review

JSONL 文件适合程序读，不适合人工检查。分析完 case 后，可以把关键输出导出成 Markdown：

```bash
python3 main.py export-review --case_id <真实案例ID>
```

或者导出所有已经完成分析的 case：

```bash
python3 main.py export-review --all
```

输出目录：

```text
outputs/review/
```

单个 case 的 review 文件会整理：

```text
Blind User 能看到什么
Knowledge Roadmap
Diagnostic Points
Solution Points
External / Confusing Points
Related Cases
Retrieval Queries
Warnings
```

同时会生成：

```text
outputs/review/index.md
outputs/review/behavior_assets.md
```

建议人工检查时优先看 `outputs/review/index.md`，再打开具体 case 的 Markdown。

## 10. analyze-cases 内部做了什么

当运行：

```bash
python3 main.py analyze-cases --limit 20
```

或：

```bash
python3 main.py analyze-cases --case_ids <真实案例ID>
```

内部会按顺序为每个选中的 case 执行以下步骤。

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
先从全案例库本地快速召回 top 50 candidate cases，
再把 target case、queries、top 50 candidates 交给 LLM，
让 LLM 选择最终 related cases。
```

注意：

```text
本地快速召回不是最终判断。
它只负责把 300 万行级别的案例库缩小到几十条候选。
最终哪些 case 算 related cases，仍然由 LLM 决定。
```

这一步可以理解成轻量版“反向 RAG”：

```text
target case
  -> LLM 生成多个检索方向
  -> 本地检索从全案例库召回 top 50
  -> LLM 从 top 50 里精选 related cases
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

### 10.4 人工种子用户行为版本

为了避免只分析 20 条历史对话时行为模式不稳定，项目内置了一版人工种子行为资产：

```text
data/manual_seed_employee_personas.jsonl
data/manual_seed_user_behavior_taxonomy.jsonl
```

这版 persona 的核心设定是：

```text
真实想解决问题
低技术熟练度
愿意配合
不主动泄露诊断原因和解决方案
被问到才逐步释放信息
需要具体操作步骤
方向不对时会纠正
解决后会确认，没解决会继续求助
```

这版 behavior taxonomy 包含 6 类：

```text
1. 陈述或继续澄清问题
2. 回答客服并释放信息
3. 询问具体操作办法
4. 尝试操作并反馈结果
5. 方向不符时纠正或拉回问题
6. 确认解决或继续求助
```

runtime 读取顺序：

```text
优先读取 outputs/employee_personas.jsonl
如果不存在，则读取 data/manual_seed_employee_personas.jsonl

优先读取 outputs/user_behavior_taxonomy.jsonl
如果不存在，则读取 data/manual_seed_user_behavior_taxonomy.jsonl
```

也就是说，如果已经跑过 `mine-behavior`，`simulate` 会优先用挖掘结果；如果没跑过或删除了 outputs 里的行为文件，`simulate` 会自动使用人工种子版本。

如果想强制使用人工种子 persona，可以运行：

```bash
python3 main.py simulate --case_id <真实案例ID> --persona_id persona_real_problem_low_tech --max_turns 8
```

### 10.5 PointExtractor

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

同时写入总 artifact：

```text
outputs/blind_user_case_views.jsonl
outputs/knowledge_roadmaps.jsonl
```

`blind_user_case_views.jsonl` 用于人工检查 Blind User 能看到什么；`knowledge_roadmaps.jsonl` 是后续 `simulate` 的主要输入。这样在线模拟不需要每次重新跑 case analysis，也避免把完整 roadmap 混进 Blind User 视图。

## 11. simulate 内部做了什么

当运行：

```bash
python3 main.py simulate --case_id <真实案例ID>
```

simulate 只做 runtime 对话，不再现场执行 QueryGenerator / PointExtractor / RoadmapBuilder。

它会先读取：

```text
outputs/knowledge_roadmaps.jsonl
```

找到对应 `case_id` 的预生成 Knowledge Module 路书，并从里面拿到完整 roadmap。

Blind User 不读取这个完整文件。Blind User 在 runtime 里只通过 Knowledge Module 的 `allowed_content` 和开场用的 `surface_problem/opening_intent` 说话。

如果你想人工检查 Blind User 可见内容，看：

```text
outputs/blind_user_case_views.jsonl
```

如果找不到该 case 的 artifact，程序会停止并提示你先运行：

```bash
python3 main.py analyze-cases --case_ids <真实案例ID>
```

### 11.1 Simulator.start

文件：

```text
src/runtime/simulator.py
```

作用：

```text
Blind User 用 LLM 根据 surface_problem、opening_intent、employee persona 生成第一句用户开场。
```

### 11.2 Simulator.step

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

## 12. behavior mining 的结果如何进入 runtime

`mine-behavior` 产出的结果会在 simulate 时被读取：

```text
outputs/employee_personas.jsonl
outputs/user_behavior_taxonomy.jsonl
```

### 12.1 进入 Knowledge Module

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

### 12.2 进入 Blind User

Blind User prompt 会看到 employee persona。

它负责把 Knowledge Module 给出的 `allowed_content` 改写成自然表达。

这里的 Blind User 不是机械复读 allowed_content。prompt 里已经明确写了：

```text
用户是真的想解决这个影响工作的 IT 问题；
用户希望 assistant 帮忙诊断、给下一步、恢复工作；
用户会配合相关追问，但不会编造事实；
用户会根据 persona 表现出低技术、配合、急躁或模糊等风格。
```

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

## 13. runtime 优先级

runtime 中优先级是：

```text
1. Roadmap / Knowledge Module factual constraint
2. Dialogue State
3. Behavior Taxonomy
4. Employee Persona
```

含义：

- roadmap 决定允许透露/禁止透露的信息范围；
- state 决定已经说过什么、是否该停；
- taxonomy 决定面对不同 assistant act 怎么反应；
- persona 决定怎么自然表达。

因此：

```text
不能因为 persona 很配合，就主动泄露 solution。
不能因为历史对话里用户经常补充很多信息，就说出 roadmap 不允许的 fact。
```

## 14. 最推荐的完整命令顺序

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

批量分析前 20 个 case，生成可复用路书：

```bash
python3 main.py analyze-cases --limit 20
```

或者只分析指定 case：

```bash
python3 main.py analyze-cases --case_ids <真实案例ID>
```

选择一个已经分析过的 case 跑模拟：

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

## 15. 关键边界

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
