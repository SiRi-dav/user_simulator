# LLM Judge 重构完成报告

## 执行摘要

✅ **已完成**：将用户模拟器的评测体系从"规则+LLM混合"模式重构为"纯LLM Judge"模式，专注于三个核心评测维度。

## 重构内容

### 核心变化：从分散指标到三个核心维度

**之前的评测维度（分散）**：
- 8+个独立指标（answer_alignment、information_progress、user_knowledge_boundary、interaction_realism、surface_semantic_similarity、opening_naturalness、opening_info_leak_risk、opening_realism_score）

**现在的评测维度（聚焦）**：
1. **行为真实度** - 主要关注初始提问像不像真实用户
2. **目标对齐** - 主要关注后续对话的信息输出是否忠实于初始目标
3. **过度合作** - 整体关注是否过于配合，缺少真实用户的阻力

## 修改的文件

### 1. `src/simulator_evaluator.py`

**修改的函数**：
- `SIMULATOR_EVAL_JUDGE_USER` - 完全重写LLM Judge Prompt
  - 专注于三个核心维度
  - 每个维度有详细的评分标准和说明
  - 返回格式简化，包含analysis字段

- `normalize_eval_judge_payload()` - 简化payload解析
  ```python
  返回格式:
  {
    "behavioral_realism_score": float,
    "goal_alignment_score": float,
    "anti_overcooperation_score": float,
    "overall_score": float,
    "analysis": {
      "behavioral_realism_analysis": str,
      "goal_alignment_analysis": str,
      "overcooperation_analysis": str
    },
    "reasons": [str, ...]
  }
  ```

- `apply_behavior_judge()`, `apply_goal_judge()`, `apply_cooperation_judge()` - 简化为直接使用LLM judge评分
  - 之前：混合规则评分和LLM评分
  - 现在：直接使用LLM judge评分

### 2. `src/metrics_exporter.py`

**修改的函数**：
- `SIMULATOR_JUDGE_USER` - 完全重写LLM Judge Prompt（与simulator_evaluator一致）
- `normalize_judge_payload()` - 简化payload解析（与simulator_evaluator一致）

### 3. `tests/test_simulator_evaluator.py`

**修改的测试用例**：
- `test_evaluate_case_can_use_llm_judge()` - 更新断言以适配新的返回格式
  - `llm_behavioral_realism_score` → `llm_judge_score`
  - `llm_goal_alignment_score` → `llm_judge_score`
  - `llm_anti_overcooperation_score` → `llm_judge_score`

## LLM Judge Prompt 详解

### 三个核心维度的评分标准

#### 1. 行为真实度
**重点关注**：初始提问像不像真实用户

**评分标准**：
- **0.8-1.0**：非常真实
  - 初始提问自然且准确
  - 整体交流风格与真实用户高度一致
- **0.5-0.7**：基本真实
  - 初始提问合理但有一些不自然之处
- **0.2-0.4**：不够真实
  - 初始提问过于正式或过于简略
  - 交流风格有明显差异
- **0.0-0.1**：完全不真实
  - 初始提问像机器生成
  - 明显违背真实用户行为

#### 2. 目标对齐
**重点关注**：后续对话的信息输出是否忠实于初始目标

**评分标准**：
- **0.8-1.0**：高度对齐
  - 始终围绕目标，信息输出时机准确
  - 能够走到解决
- **0.5-0.7**：基本对齐
  - 大部分时间围绕目标
  - 信息输出基本合理
- **0.2-0.4**：对齐度低
  - 容易跑题或信息输出节奏混乱
- **0.0-0.1**：完全不对齐
  - 严重偏离目标
  - 信息输出完全不合理

#### 3. 过度合作
**重点关注**：整体是否过于配合，缺少真实用户的阻力

**评分标准**：
- **0.8-1.0**：逼真
  - 表现出合理的困惑、犹豫、追问
  - 不会过于配合
- **0.5-0.7**：基本逼真
  - 有一些真实用户的阻力表现
- **0.2-0.4**：过度配合
  - 缺少真实的困惑和质疑
- **0.0-0.1**：严重过度配合
  - 完全不像真实用户的行为

## 使用方法

### 运行评测时使用LLM Judge
```bash
# 单个case，使用LLM judge
python3 main.py evaluate-simulator --case_id KT001 --judge

# 多个case，使用LLM judge
python3 main.py evaluate-simulator --case_ids KT001 KT002 KT003 --judge

# 导出指标，使用LLM judge
python3 main.py export-metrics --case_id KT001 --judge
```

### 输出格式

**LLM Judge返回的分析报告**：
```json
{
  "behavioral_realism_score": 0.82,
  "goal_alignment_score": 0.90,
  "anti_overcooperation_score": 0.70,
  "overall_score": 0.80,
  "analysis": {
    "behavioral_realism_analysis": "初始提问自然且准确，交流风格与真实用户高度一致...",
    "goal_alignment_analysis": "始终围绕目标问题，信息输出时机合理，能够走到解决...",
    "overcooperation_analysis": "表现出合理的困惑和追问，配合度适中..."
  },
  "reasons": ["...", "..."]
}
```

## 测试结果

```
============================= test session starts ==============================
tests/test_simulator_evaluator.py::test_select_real_dialogues_matches_case_id_inside_joined_list PASSED
tests/test_simulator_evaluator.py::test_collect_real_case_ids_keeps_unique_ids PASSED
tests/test_simulator_evaluator.py::test_split_logs_into_sessions_uses_turn_restart PASSED
tests/test_simulator_evaluator.py::test_behavioral_realism_returns_bounded_score PASSED
tests/test_simulator_evaluator.py::test_evaluate_case_can_use_llm_judge PASSED
tests/test_metrics_exporter.py::test_calculate_rule_metrics_scores_core_dimensions PASSED
tests/test_metrics_exporter.py::test_metrics_exporter_writes_jsonl_and_summary_with_optional_judge PASSED

============================== 7 passed in 0.09s ===============================
```

## 总结

本次重构成功将用户模拟器的评测体系从"多指标分散模式"重构为"三核心维度聚焦模式"，所有评测现在都通过LLM Judge完成，确保了评测的准确性和一致性。

### 核心改进
1. **简化**：从8+个指标简化为3个核心维度
2. **聚焦**：每个维度都有明确的关注重点和评分标准
3. **统一**：所有评测都使用LLM Judge，确保语义理解的一致性
4. **可解释**：新增analysis字段，提供详细的评测理由

### 后续工作
- 根据实际使用情况调整评分标准
- 收集评测数据，优化LLM Judge Prompt
- 考虑增加更多维度的细粒度分析（如需要）
