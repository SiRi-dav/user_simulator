# Case Dialogue Mining / User Simulator 汇报提纲

## 1. 当前目标

当前项目目标是构建企业客服场景下的用户模拟器，用于生成可控、多轮、贴近真实用户行为的模拟用户对话。

核心问题：

- 给定一个知识库 case，推断用户可能如何提问。
- 建模用户不会一次性提供全部信息的行为。
- 支持不同用户画像，如低技术用户、高技术用户、急躁用户、模糊表达用户。
- 生成多轮对话，用来测试客服 AI 的澄清追问、问题定位和回答能力。

## 2. 现在有两条分析链路

### 2.1 历史对话挖掘链路

入口：

```bash
python main.py --config config.yaml
```

输入：

- case 知识库
- 历史客服对话

流程：

```text
case 库 + 历史对话
  -> case_dialogue_matcher.py 匹配 case_id
  -> analyzer.py 调用本地 LLM
  -> outputs/question_patterns.jsonl
```

特点：

- 基于真实用户历史问法。
- 适合总结已有 case 的真实用户表达、隐藏信息、追问路径。
- `main.py --skip-analysis` 可以只验证 case-dialogue 匹配，不调用 LLM。

### 2.2 Case-only 分析链路

入口：

```bash
python analyze_cases_only.py --config config.yaml --max-cases 20 --resume
```

输入：

- 只使用 case 知识库
- 不读取历史对话

流程：

```text
case 库
  -> analyze_cases_only.py
  -> 本地 LLM 推断用户侧行为
  -> outputs_case_only/question_patterns.case_only.jsonl
```

特点：

- 不是“只选没有历史对话的 case”，而是“分析时不使用历史对话”。
- 当前会从 case 库前 N 条 case 里选，不限制是否有历史对话。
- 支持 `--resume`，已经成功的 case 不重复跑。
- 已加超时重试：默认每个 case 失败后重试 2 次。

推荐命令：

```bash
python analyze_cases_only.py \
  --config config.yaml \
  --max-cases 20 \
  --resume \
  --retries 4 \
  --retry-delay 10
```

## 3. 模拟器当前设计

入口：

```bash
python simulate_from_patterns.py
```

默认读取：

```text
outputs_case_only/question_patterns.case_only.jsonl
```

也就是说，当前默认模拟链路是 case-only。

如果要切回历史对话分析结果：

```bash
python simulate_from_patterns.py \
  --patterns outputs/question_patterns.jsonl \
  --scenario replay_like \
  --limit 20
```

## 4. 多轮对话机制

当前模拟器是多轮模拟，不是单轮。

默认：

```text
--max-turns 6
```

含义是最多 6 轮用户发言，中间穿插 mock 客服回复。

对话结构：

```text
用户 1
客服 1
用户 2
客服 2
...
```

如果只想生成单轮用户开场：

```bash
python simulate_from_patterns.py --agent none --limit 20
```

## 5. 用户画像 Persona

当前内置 persona：

- `cooperative_normal`：普通合作用户
- `vague_low_context`：模糊表达用户
- `low_tech_confused`：低技术水平用户
- `impatient_user`：急躁用户
- `tried_and_failed`：已尝试失败用户
- `high_tech_diagnostic`：高技术排障用户
- `screenshot_dependent`：截图依赖用户

查看命令：

```bash
python simulate_from_patterns.py --list-personas
```

低技术用户示例：

```bash
python simulate_from_patterns.py \
  --scenario replay_like \
  --persona low_tech_confused \
  --limit 20 \
  --llm-policy
```

高技术用户示例：

```bash
python simulate_from_patterns.py \
  --scenario replay_like \
  --persona high_tech_diagnostic \
  --limit 20 \
  --llm-policy
```

## 6. LLM 在模拟阶段的作用

现在分为两种 LLM 能力：

### 6.1 `--llm-policy`

让 LLM 控制用户对话策略。

它决定：

- 本轮用户动作是什么
- 是否透露隐藏信息
- 透露哪些 slot
- 客服问到的信息是否知道
- 不知道时是否说“不清楚/不会看”

但它受约束：

- 只能围绕当前 case
- 只能从已有候选 hidden slots 里选择
- 不能编造新的具体事实

策略 prompt 在：

```text
simulate_from_patterns.py -> build_policy_prompt(...)
```

### 6.2 `--llm-rewrite`

只负责润色用户话术。

它不决定透露什么，只改写表达方式。

改写 prompt 在：

```text
simulate_from_patterns.py -> build_rewrite_prompt(...)
```

推荐使用：

```bash
python simulate_from_patterns.py \
  --scenario replay_like \
  --persona low_tech_confused \
  --limit 20 \
  --llm-policy
```

如果想表达更自然：

```bash
python simulate_from_patterns.py \
  --scenario replay_like \
  --persona low_tech_confused \
  --limit 20 \
  --llm-policy \
  --llm-rewrite
```

## 7. Mock 客服当前状态

当前客服侧还是规则 mock，不是 LLM，也不是历史客服一比一回放。

逻辑在：

```text
simulate_from_patterns.py -> mock_agent_step(...)
```

规则：

- 第一轮如果还有缺失 slot，就问第一个 slot。
- 如果还有 slot 且追问次数少于 2，就继续追问。
- 否则返回一个基于 `case_id` 的答案。

我们曾讨论过“历史客服一比一 replay”，但已经先回退，没有保留在当前主线里。

## 8. 当前输出

case-only 分析输出：

```text
outputs_case_only/question_patterns.case_only.jsonl
outputs_case_only/question_patterns.case_only.readable.md
outputs_case_only/analysis_errors.case_only.jsonl
```

模拟器输出：

```text
outputs/simulated_dialogues.<scenario>.<persona>.policy.jsonl
outputs/simulated_dialogues.<scenario>.<persona>.policy.readable.md
```

主要看 readable 文件，方便人工检查。

## 9. 公司服务器运行顺序

```bash
cd /mnt/nas1/users/CuhkszTeam/xirui/case_dialogue_mining
git pull
```

先跑 case-only 分析：

```bash
python analyze_cases_only.py \
  --config config.yaml \
  --max-cases 20 \
  --resume \
  --retries 4 \
  --retry-delay 10
```

再跑模拟：

```bash
python simulate_from_patterns.py \
  --scenario replay_like \
  --persona low_tech_confused \
  --limit 20 \
  --llm-policy
```

查看输出：

```text
outputs/simulated_dialogues.replay_like.low_tech_confused.policy.readable.md
```

## 10. 当前阶段总结

已经完成：

- case-only 用户行为推断
- 历史对话挖掘链路
- 多轮用户模拟
- 多 persona 用户画像
- LLM policy 控制隐藏信息透露策略
- LLM rewrite 用户话术润色
- 本地 Qwen / OpenAI-compatible endpoint 接入
- timeout retry / resume

目前仍是 MVP 的部分：

- 客服侧还是规则 mock
- case-only hidden facts 来自 LLM 推断，不一定等同真实历史用户行为
- 对话质量需要通过 readable 文件人工抽查
- 后续可以接真实客服 AI，形成 user simulator vs QA agent 的闭环评测

## 11. 明天可以重点讲的亮点

1. 从“只抽 pattern”推进到“可控多轮用户模拟”。
2. 用户画像不只是改语气，而是影响信息透露策略。
3. LLM policy 可以判断客服追问是否命中 hidden fact。
4. case-only 模式支持没有历史对话的新 case。
5. 保留历史对话挖掘链路，后续可以对比 case-only 推断和真实用户行为。
