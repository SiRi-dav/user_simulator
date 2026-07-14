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

## 1.1 当前版本交接重点

当前版本主要完成了这些工作：

```text
1. Case analysis 支持断点保护
   - analyze-cases 默认跳过已经完成分析的 case
   - 成功分析一个 case 后会立即 upsert 写入 blind view、runtime view、knowledge roadmap 和 debug artifact

2. Related case 检索改成多路召回
   - 不再把所有 query 混成一次检索
   - 按 surface / diagnostic / solution / confusion 多路召回
   - 本地混合检索 + LLM 排序打分

3. Runtime 行为层改为 feedback-aware
   - KnowledgeAssessment 负责判断本轮 assistant 是否命中 target、用户还有什么可说、是否无新信息
   - BlindUserAction 负责决定执行、追问步骤、反馈动作结果、接受方案或停止
   - solution 内容不再直接交给 Blind User 生成回复，避免信息泄漏

4. 评测系统重构
   - evaluate-simulator 输出 Behavioral Realism、Goal Alignment、Anti-overcooperation 三类主指标
   - Opening Similarity 被降为低权重辅助项，只占 Behavioral Realism 的 10%
   - 支持 --session_policy all/latest/first，只评最新一次模拟时用 latest

5. 增加独立 tau2-style 评测
   - scripts/evaluate_tau2_style.py
   - 用 knowledge_roadmaps、simulation_logs 和 runtime state 近似 τ²-bench 的 dual-control / assertion / action matching

6. 增加合并导出脚本
   - scripts/export_combined_transcripts.py
   - scripts/export_combined_roadmaps.py
   - scripts/export_combined_eval.py
```

最常用的交接运行链路在本文第 15 节。

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
assistant 给什么方案才算 solved 或 solution_accepted？
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
outputs/case_analysis_debug.jsonl
```

每个 case 会提前生成三类文件：

```text
blind_user_case_views.jsonl: 给 Blind User 看的用户问题、开场意图、可见事实
knowledge_roadmaps.jsonl: 给 Knowledge Module/runtime 用的紧凑 roadmap
case_analysis_debug.jsonl: 给人工审查/debug 用的完整分析材料
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
6. 人工输入 assistant 回复，或通过 `--assistant_mode api` 调用真实 assistant
```

## 4. 第一步：进入项目目录

先进入仓库中的 `User_simulator2.0` 目录。不要在命令或文档里固定某台机器的绝对路径，交接时统一使用项目相对路径：

```bash
cd <repo_root>/User_simulator2.0
```

后续命令默认都在这个目录下执行。

如果需要确认当前分支：

```bash
git status --short --branch
```

当前主要开发分支：

```text
user-simulator-action-result-feedback
```

## 5. 第二步：确认配置

查看：

```text
config.yaml
```

里面最重要的是：

```yaml
llm:
  provider: "openai-compatible"
  base_url: "<company_llm_base_url>"
  api_key: "<api_key>"
  model: "<model_name>"

paths:
  cases: "<relative_or_absolute_case_library_path>"
  dialogues: "<relative_or_absolute_historical_dialogue_path>"
  output_dir: "outputs"
```

含义：

- `cases`: 真实案例库路径
- `dialogues`: 历史客服对话记录路径
- `output_dir`: 中间结果输出目录
- `llm`: 公司 OpenAI SDK-compatible 接入方式

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

大批量分析时可以开 case 级并发。比如 500 条可以先从 4 或 8 开始试：

```bash
python3 main.py analyze-cases --case_ids_file outputs/real_dialogue_case_ids_500.txt --workers 8
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
```

它不包含 solution points、external case details，也不包含具体 forbidden solution 文本，避免 Blind User 作弊。

`knowledge_roadmaps.jsonl` 每一行是给 Knowledge Module 的紧凑路书，包括：

```text
case_id
title
roadmap.surface_problem
roadmap.opening_intent
roadmap.user_facing_points / diagnostic_points / solution_points / external_points
roadmap.target_route / external_routes
roadmap.forbidden_content
```

紧凑 point 只保留 `point_id`、`content`、`point_type`、`trigger`、`visibility`。它不保存 `source_quote`、`reason`、完整 related case 文本、warnings 等审查信息。

完整审查信息会写到：

```text
outputs/case_analysis_debug.jsonl
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

如果要接入真实 assistant，不需要手动输入 `Assistant>`，运行：

```bash
python3 main.py simulate --case_id <真实案例ID> --assistant_mode api --max_turns 8
```

程序会把当前完整 `dialogue_history` 依次发给：

```text
POST /query
POST /trigger
POST /policy
POST /response
```

并把 `/response` 的返回结果当作本轮 assistant 回复。

继续输入 assistant 回复，直到：

- LLM 判断 assistant 命中目标 solution；
- 或达到最大轮数。

## 9.1 批量运行模拟对话

如果要一次跑多个 case，并调用真实 assistant：

```bash
python3 main.py simulate-batch --case_ids KT001 KT002 KT003 --max_turns 8
```

也可以跑 `knowledge_roadmaps.jsonl` 里已有的全部 case：

```bash
python3 main.py simulate-batch --all --max_turns 8
```

限制数量：

```bash
python3 main.py simulate-batch --all --limit 10 --max_turns 8
```

批量模式目前默认使用真实 assistant API，相当于：

```text
assistant_mode = api
```

### 断电保护

批量模拟会写状态文件：

```text
outputs/simulate_batch_status.jsonl
```

每个 case 会记录：

```text
running
completed
failed
```

如果中途断电或程序中断，重新执行同一条 `simulate-batch` 命令时，已经标记为 `completed` 的 case 会自动跳过，`running` 或 `failed` 的 case 会重新尝试。

如果想强制重跑已经完成的 case：

```bash
python3 main.py simulate-batch --all --rerun_completed --max_turns 8
```

每个 case 结束后会自动尝试导出 transcript 到：

```text
outputs/transcripts/<case_id>.md
outputs/transcripts/<case_id>.json
```

## 9.4 导出真实对话 Transcript

`outputs/simulation_logs.jsonl` 保存的是逐轮调试日志，不适合直接人工阅读。跑完 `simulate` 后，可以导出完整对话 transcript：

```bash
python3 main.py export-transcripts --case_id <真实案例ID>
```

或者导出所有已经模拟过的 case：

```bash
python3 main.py export-transcripts --all
```

输出位置：

```text
outputs/transcripts/<case_id>.md
outputs/transcripts/<case_id>.json
```

Markdown 里会按顺序还原：

```text
User: ...
Assistant: ...
User: ...
Assistant: ...
```

JSON 版本方便后续自动化评估模块继续读取。

## 9.45 导出用户模拟器质量指标

跑完模拟对话后，可以离线评估用户模拟器质量：

```bash
python3 main.py export-metrics --case_id <真实案例ID>
```

或者评估所有已经模拟过的 case：

```bash
python3 main.py export-metrics --all
```

默认会使用规则统计，输出：

```text
outputs/metrics/simulation_metrics.jsonl
outputs/metrics/summary.md
```

核心指标包括：

```text
answer_alignment_score: 用户是否回答 assistant 当前问题
information_progress_score: 用户回复是否推动信息状态前进
user_knowledge_boundary_score: 用户是否遵守 blind user 的知识边界
interaction_realism_score: 用户回复是否简短自然、没有内部字段痕迹
```

如果要额外启用 LLM judge 复核语义质量：

```bash
python3 main.py export-metrics --case_id <真实案例ID> --judge
python3 main.py export-metrics --all --judge
```

建议用法是：

```text
规则统计用于全量快速筛查；
LLM judge 用于复核可疑样本或关键 case。
```

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
分别按 surface、diagnostic、solution、confusion 四路召回，
每路融合 BM25 和本地 n-gram 余弦分数，
合并去重后交给 LLM 做多维打分和排序，
最后按关系类型覆盖选择 related cases。
```

注意：

```text
各类 query 不会再混成一个 token 集合。
BM25 负责产品名、错误码和稀有关键词等精确相关性，
n-gram 余弦负责表达形式相近的软匹配，
LLM 对 surface、diagnostic、solution、confusion 和 overall 分别打分。
如果 LLM 返回空结果，程序会保留本地混合检索得分最高的候选作为 fallback。
```

这一步可以理解成轻量版“反向 RAG”：

```text
target case
  -> LLM 生成四类检索方向
  -> 四路 BM25 + n-gram cosine 混合召回
  -> RRF 融合并去重
  -> LLM 多维打分重排
  -> 类型覆盖 Top-K / 空结果 fallback
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

该日志会记录：

```text
每个候选的 route_scores / bm25_scores / semantic_scores
LLM ranked_cases 及五类分数
是否触发 fallback
all -> recall -> ranked -> selected -> final 的漏斗数量
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
outputs/case_analysis_debug.jsonl
```

`blind_user_case_views.jsonl` 用于检查 Blind User 能看到什么；`knowledge_roadmaps.jsonl` 是后续 `simulate` 的主要输入；`case_analysis_debug.jsonl` 用于人工审查和 debug。这样在线模拟不需要每次重新跑 case analysis，也不会把完整调试材料混进 runtime 输入。

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

找到对应 `case_id` 的预生成 Knowledge Module 路书，并从里面拿到紧凑 runtime roadmap。

Blind User 不直接读取完整 debug 材料。Blind User 在 runtime 里只通过 Knowledge Module 的 `allowed_facts`、`unknown_requested_facts` 和开场用的 `surface_problem/opening_intent` 说话。

当前结束策略：

```text
当前 simulate 是严格一问一答，Blind User 不会在 assistant 停止回复后主动补充“我试完了，问题解决/没解决”。
因此如果 assistant 给出命中 solution point 的可执行方案，Knowledge Module 会标记 `solution_match=target`，Blind User 再选择接受方案并结束。
这类结束不是 solved_confirmed，而是 solution_accepted，stop_reason 为 accepted_actionable_solution。
仍然不要新增用户主动反馈机制。
```

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
→ KnowledgeModule.assess
→ BlindUser.choose_action_and_reply
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

`KnowledgeModule.assess` 只负责知识判断：

```text
assistant 命中 case_internal / case_external / out_of_knowledge / target_solution？
允许释放哪些用户可见事实？
assistant 问到哪些用户不知道/不该知道的信息？
是否命中 target solution？
是否已经没有更多用户信息可补充？
point 曝光状态怎么更新？
```

`KnowledgeModule.assess` 不选择用户动作，也不生成用户回复。

`BlindUser.choose_action_and_reply` 才负责：

```text
根据 assistant act + knowledge assessment 选择用户动作
生成自然用户回复
决定是否接受可执行方案后结束
决定是否因 assistant 无法继续有效推进而结束
更新行为状态，例如 action_request_count / how_to_check_count / solution_status
```

当前可选用户动作包括：

```text
answer_question
say_unknown
ask_how_to_check
ask_how_to_perform
report_action_result
correct_or_redirect
accept_actionable_solution_and_stop
stop_no_effective_solution
continue
```

其中 `report_action_result` 用来处理“上一轮用户已经接受/尝试了一个操作方案”的情况。用户说过“好的，我去试试看”之后，系统会先把执行动作得到的世界反馈写入 `action_execution_feedback`，例如“试了还是一样”“没看到变化”“按这个操作后还是打不开”。行为层下一轮会优先考虑这份反馈，但不是固定强制选择 `report_action_result`：如果 assistant 最新回复已经命中 target solution、提出更具体的相关追问，或需要纠偏，用户会把执行反馈和新信息综合后选择更合适的回复。

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

### 12.1 进入 Blind User

behavior taxonomy 主要给 Blind User 使用，用来帮助它选择更像真实用户的动作和话术。

例如：

```text
assistant 要求用户操作时，低技术用户可能会先问怎么做
assistant 问偏时，用户会纠正并拉回原问题
assistant 给具体可执行方案时，用户可以接受并结束
assistant 反复要求用户无法提供的信息时，用户可以说明不知道
```

但它不能突破 Knowledge Module 给出的知识边界。

也就是说：

```text
Knowledge Module 决定能说什么事实
Blind User 决定怎么反应、怎么表达、是否结束
```

### 12.2 进入 Blind User 生成回复

Blind User prompt 会看到 employee persona。

它负责根据 Knowledge Module 给出的 `allowed_facts` / `unknown_requested_facts` / `solution_match` 选择用户动作，并生成自然表达。

这里的 Blind User 不是机械复读 allowed facts。prompt 里已经明确写了：

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

但 Blind User 不能新增 Knowledge Module 允许范围之外的事实。

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

## 14. 对照真实对话评测用户模拟器

这一步用于评估用户模拟器。它会读取同一批 case 的真实历史对话和模拟对话，并输出自动评分报告。

所有评分默认归一化到 `0.0` 到 `1.0`：

```text
1.0 = 最好
0.0 = 最差
```

summary 表里的字段含义：

```text
real: 该 case 在真实历史对话文件中匹配到的真实对话条数
simulated: 该 case 在 simulation_logs.jsonl 中拆出的模拟 session 数量
overall: 总分；加 --judge 时为 LLM judge 主分
behavioral: 行为真实度；加 --judge 时为 LLM judge 主分
opening_aux: 开头相似度辅助项，低权重，不代表整体质量
realsim: RealSim-style 八维行为分布；加 --judge 时由 LLM judge 参考规则诊断后给正式分
c2st: 分类器双样本检验 proxy；加 --judge 时由 LLM judge 参考规则诊断后给正式分
leak_adj_success: 去泄漏成功；加 --judge 时由 LLM judge 判断是否真实成功
goal: 任务导向与目标对齐；加 --judge 时为 LLM judge 主分
anti-overcoop: 反过度合作，越高表示越不过度配合；加 --judge 时为 LLM judge 主分
```

模拟日志来自：

```text
outputs/simulation_logs.jsonl
```

评测命令会从 `config.yaml` 的 `paths.dialogues` 中筛出同 case 的真实对话，再和对应 case 的模拟对话做对照。

评测单个 case：

```bash
python3 main.py evaluate-simulator --case_id <真实案例ID>
```

也可以一次评测多个 case：

```bash
python3 main.py evaluate-simulator --case_ids KT001 KT002 KT003
```

如果前面用 `select-real-cases` 生成了 20 个真实 case 列表，直接复用这个文件：

```bash
python3 main.py evaluate-simulator --case_ids_file outputs/real_dialogue_case_ids.txt
```

默认不加 `--judge` 时是 diagnostic-only 规则诊断版，只适合快速回归和筛 bad case。

正式测评建议加 `--judge`。此时最终主分由 LLM judge 给出，规则统计、分布检验和轨迹状态只作为 evidence：

```bash
python3 main.py evaluate-simulator --case_ids_file outputs/real_dialogue_case_ids.txt --judge
```

如果同一个 case 跑过多次模拟，可以控制评测哪些 session：

```bash
# 默认，评估该 case 的所有模拟 session
python3 main.py evaluate-simulator --case_ids_file outputs/real_dialogue_case_ids.txt --session_policy all

# 只评估每个 case 时间上最后一次模拟
python3 main.py evaluate-simulator --case_ids_file outputs/real_dialogue_case_ids.txt --session_policy latest

# 只评估每个 case 最早一次模拟
python3 main.py evaluate-simulator --case_ids_file outputs/real_dialogue_case_ids.txt --session_policy first
```

正式对比最新 prompt 效果时，建议用：

```bash
python3 main.py evaluate-simulator \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --session_policy latest \
  --judge
```

`latest` 的判定方式：

```text
先按 case_id 过滤日志；
再按 timestamp 排序，timestamp 缺失时用日志文件中的出现顺序兜底；
每次 turn 重新从 1 开始时拆成一个新 session；
latest 取最后拆出的那个 session。
```

如果真实对话文件不使用 `config.yaml` 里的 `paths.dialogues`，可以手动指定：

```bash
python3 main.py evaluate-simulator --case_id <真实案例ID> --dialogues <historical_dialogue_path>
```

输出位置：

```text
outputs/simulator_eval/summary.md
outputs/simulator_eval/simulator_eval.jsonl
outputs/simulator_eval/<case_id>.md
```

当前评估分为 LLM judge 主分和规则诊断证据两层：

```text
Behavioral Realism:
  满分 1.0。评估模拟用户是否像真实员工。
  正式评测加 --judge 时，该项由 LLM 参考真实对话、模拟对话、roadmap 和规则诊断后给分。
  不加 --judge 时，使用以下规则诊断权重生成 diagnostic score：
    - opening_similarity: 0.10
    - distribution_realism: 0.40
    - conditional_behavior_realism: 0.30
    - user_sim_index: 0.20

  opening_similarity 是低权重辅助项，不用于单独判断 simulator 好坏。
  它包含三组相似度：
    - real_sim_opening_similarity: 真实用户开头 vs 模拟用户开头
    - real_surface_similarity: 真实用户开头 vs roadmap.surface_problem
    - sim_surface_similarity: 模拟用户开头 vs roadmap.surface_problem

  distribution_realism 包括：
    - 用户轮数 Wasserstein 距离
    - 用户每轮话语长度 Wasserstein 距离
    - 用户 dialogue act 分布 Jensen-Shannon 散度

  conditional_behavior_realism 包括：
    - 被追问时是否逐步提供信息
    - 被要求动作时是否执行、追问步骤或反馈结果
    - 遇到无效建议时是否会困惑、拒绝或拉回目标

  User-Sim Index 包括：
    - 交流风格
    - 信息输出模式
    - 澄清行为
    - 错误/失败反应

RealSim-style Distribution:
  满分 1.0。
  正式评测加 --judge 时，LLM 会参考八维规则诊断并结合语义判断给 realsim 正式分。
  不加 --judge 时，它是规则诊断项，不直接替代 overall。
  按论文中“行为维度分布对齐”的思路，把企业 IT 咨询场景映射成八个维度：
    - user_intent: 接受、拒绝、澄清、困惑、动作反馈、信息提供等 intent 分布
    - feedback: 接受、拒绝、执行动作反馈等反馈信号
    - emotion: 困惑、挫败、着急等情绪信号
    - domain_specific_knowledge: Outlook、WeLink、iDesk、VPN、DNS、权限等领域词使用
    - personal_context_identity: 账号、邮箱、电脑、手机、部门、公司等个人/工作上下文
    - message_length: 用户话语长度
    - linguistic_attributes: 提问、不确定表达、第一人称表达等语言属性
    - errors: 报错、失败、异常、无法打开等错误反馈

C2ST Distribution Check:
  满分 1.0。C2ST 是 classifier two-sample test 的 proxy。
  正式评测加 --judge 时，LLM 会参考 C2ST 规则结果，并结合模板化、风格单一、语义自然度等因素给正式分。
  程序会把真实对话和模拟对话转成轻量行为特征向量，用一个简单近质心分类器区分 real vs simulated。
  - classifier_accuracy / balanced_accuracy 越高，说明越容易区分真实和模拟
  - c2st score 越高，说明越难区分，模拟分布越接近真实分布
  这个指标更适合在 50/150/500 条级别看整体趋势，单个 case 只作为辅助参考。

Goal Alignment:
  满分 1.0。评估模拟用户是否围绕目标 case 推进。
  - goal_persistence_score: 用户是否跑题
  - knowledge_boundary_score: 是否泄露 solution 或外部 case 信息
  - simulated_solved_rate: 模拟对话是否能围绕目标 case 走到解决/接受
  - trajectory_state_score: 是否命中 target solution、是否正确接受、是否出现知识泄漏
  - 开启 --judge 后，LLM 作为正式裁判，判断用户是否真的保持目标一致、是否像偷看答案

Overly Cooperative:
  满分 1.0。越高表示越不过度合作。
  - simulated_accept_rate 是否明显高于真实用户
  - simulated_resistance_rate 是否明显低于真实用户
  - resistance 包括拒绝、追问、困惑、不满等真实用户常见阻力
  - trajectory_overcooperation_penalty: 惩罚错误接受、重复说去试但没有反馈等过度配合轨迹
  - 开启 --judge 后，LLM 作为正式裁判，判断是否存在过度配合、过早接受、缺少真实阻力

Trajectory State:
  - target_solution_hit_rate: assistant 是否实际触达目标方案
  - accepted_target_rate: 用户是否在 target 命中后合理接受
  - wrong_acceptance_rate: 用户是否接受了非 target / 无效方案
  - knowledge_leakage_rate: 用户是否泄露 solution 或 forbidden content
  - action_feedback_use_rate: 用户是否使用了动作执行后的 observation
  - repeated_try_without_feedback_rate: 是否机械重复“我去试试”但没有反馈结果

Leakage-Aware Success:
  - raw_success_rate: target solution 被命中并被用户接受的比例
  - leakage_adjusted_success_rate: 去掉用户侧 solution / forbidden content 泄漏后的真实成功比例
  - false_success_rate: 错误接受或依赖泄漏导致的虚假成功比例
  - solution_leakage_rate: 用户侧知识泄漏比例
  - 开启 --judge 后，LLM 会结合轨迹和语义判断是否真实成功，而不是只看规则匹配
```

规则版只作为第一层自动回归和筛 bad case。`--judge` 版会调用配置里的 LLM，对 Behavioral Realism、Goal Alignment、Anti-overcooperation、RealSim-style Distribution、C2ST Distribution Check、Leakage-Aware Success 六项做语义评审；最终汇报分数以 LLM judge 为主，规则分只保留为 `diagnostic_rule_score` 用于解释和 ablation。

### 14.4 额外 τ²-bench-style 双控制评测

如果要单独跑一个更接近 τ²-bench 的评测，不走 `main.py`，用独立脚本：

```bash
python3 scripts/evaluate_tau2_style.py --case-ids-file outputs/real_dialogue_case_ids.txt
```

也可以只评一个 case：

```bash
python3 scripts/evaluate_tau2_style.py --case-id KT00116480
```

输出位置：

```text
outputs/tau2_eval/summary.md
outputs/tau2_eval/tau2_eval.jsonl
outputs/tau2_eval/<case_id>.md
```

这个模块照搬 τ²-bench 的评测结构做 proxy 映射：

```text
Dual-control setting:
  - assistant 通过语言指导用户动作
  - user 执行动作后产生 action_execution_feedback
  - 最终根据共享轨迹和 proxy state 判断任务是否成功

State / assertion:
  - assertion_pass: target solution 是否命中并被正确接受，且没有知识泄漏
  - action_matching_score: 轨迹中是否出现 target solution 对应的 action / point
  - communication_info_score: assistant 是否成功 elicited target route 所需用户信息
  - dual_control_coordination_score: assistant 要求用户执行动作后，用户是否反馈 observation

Reliability:
  - pass_hat_1: 同一 case 的模拟 session 成功率
  - pass_hat_k_all: 同一 case 的所有 session 是否都成功

Failure diagnosis:
  - assistant_reasoning_or_retrieval_failure
  - dual_control_coordination_failure
  - action_feedback_failure
  - false_success_or_overcooperation
  - user_simulator_leakage
  - termination_or_acceptance_failure
```

注意：我们没有 τ²-bench 那样的真实工具数据库，所以这里是 **tau2-style proxy evaluation**。它使用 `knowledge_roadmaps.jsonl`、`simulation_logs.jsonl`、Knowledge Module assessment 和 simulator state 来近似论文里的 world state、assertion functions 和 action matching。

## 15. 最推荐的完整命令顺序

进入项目：

```bash
cd <repo_root>/User_simulator2.0
```

确认配置：

```bash
python3 main.py --help
```

可选：先挖历史行为。如果已经有 `outputs/employee_personas.jsonl` 和 `outputs/user_behavior_taxonomy.jsonl`，这一步可以跳过。

```bash
python3 main.py mine-behavior --max_dialogues 20
```

选择有真实历史对话的 case：

```bash
python3 main.py select-real-cases \
  --limit 20 \
  --offset 0 \
  --output outputs/real_dialogue_case_ids.txt
```

分析这批 case，生成路书：

```bash
python3 main.py analyze-cases \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --workers 4
```

如果中断，重复执行同一条命令即可；已经完成分析的 case 会被跳过。强制重跑分析时加：

```bash
python3 main.py analyze-cases \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --workers 4 \
  --rerun_completed
```

批量模拟：

```bash
python3 main.py simulate-batch \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --assistant_mode api \
  --max_turns 15
```

如果只想重跑已经完成过的模拟，加：

```bash
python3 main.py simulate-batch \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --assistant_mode api \
  --max_turns 15 \
  --rerun_completed
```

评测最新一次模拟结果：

```bash
python3 main.py evaluate-simulator \
  --case_ids_file outputs/real_dialogue_case_ids.txt \
  --session_policy latest \
  --judge
```

导出合并后的模拟对话、路书和评测结果，方便离线交接：

```bash
python3 scripts/export_combined_transcripts.py \
  --case-ids-file outputs/real_dialogue_case_ids.txt \
  --output all_simulation_transcripts

python3 scripts/export_combined_roadmaps.py \
  --case-ids-file outputs/real_dialogue_case_ids.txt \
  --output all_knowledge_roadmaps

python3 scripts/export_combined_eval.py \
  --case-ids-file outputs/real_dialogue_case_ids.txt \
  --output all_simulator_eval
```

输出位置：

```text
outputs/transcripts/all_simulation_transcripts.md
outputs/transcripts/all_simulation_transcripts.json
outputs/review/all_knowledge_roadmaps.md
outputs/review/all_knowledge_roadmaps.json
outputs/simulator_eval/all_simulator_eval.md
outputs/simulator_eval/all_simulator_eval.json
```

运行测试：

```bash
python3 -m pytest
```

## 16. 关键边界

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
