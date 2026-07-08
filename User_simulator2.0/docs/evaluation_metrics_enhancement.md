# 用户模拟器评测指标改进总结

## 改进概述

本次改进针对用户模拟器的评测模块，新增了两个关键评测维度：
1. **初始提问真实度 (Opening Realism)** - 评估初始提问与真实案例的相似度和自然度
2. **信息输出节奏 (Information Rhythm)** - 评估信息输出的触发条件、顺序和准确性

## 改进背景

原有评测体系主要关注：
- 行为真实度：整体对话行为分布、话语长度、对话行为分布
- 目标对齐：知识边界遵守、目标持久度、解决率
- 过度合作：接受率、阻力率对比

**缺失的维度**：
- 初始提问的专项评测（开场白是否像真实用户的问题）
- 信息输出的节奏评测（是否在被追问时才透露诊断信息）

## 新增文件

### 1. `/src/evaluator_metrics.py`
新增的评测指标计算模块，包含：

#### 初始提问真实度指标 (`opening_realism_stats`)
```python
{
    "has_opening": bool,           # 是否有开场白
    "surface_semantic_similarity": float,  # 与目标案例表面问题的语义相似度
    "opening_naturalness_score": float,    # 开场白的自然度
    "opening_info_leak_risk": float,       # 开场白的信息泄露风险
    "opening_realism_score": float,        # 综合评分
}
```

**评分权重**：
- 语义相似度：50%
- 自然度：30%
- 无泄露风险：20%

#### 信息输出节奏指标 (`information_rhythm_stats`)
```python
{
    "premature_diagnostic_rate": float,    # 过早透露诊断信息的比例
    "info_release_timing_score": float,    # 信息释放时机评分
    "info_sequence_rationality": float,    # 信息顺序合理性
    "info_accuracy_score": float,          # 信息准确性
    "information_rhythm_score": float,     # 综合评分
}
```

**评分权重**：
- 无过早泄露：40%
- 释放时机：30%
- 顺序合理性：15%
- 准确性：15%

## 修改的文件

### 2. `/src/metrics_exporter.py`
- 导入新的评测指标函数
- 在 `calculate_rule_metrics()` 中集成新指标
- 更新 `render_metrics_summary()` 添加新的汇总表格

**新增输出表格**：
```markdown
## Enhanced Metrics
| case_id | opening_realism | surface_sim | opening_natural | leak_risk | info_rhythm | timing | sequence | accuracy |
```

### 3. `/src/simulator_evaluator.py`
- 导入新的评测指标函数
- 在 `evaluate_case()` 中调用 `enhanced_evaluation()`
- 更新 `render_case_report()` 展示新的评测指标
- 新增 `enhanced_evaluation()` 函数

### 4. `/tests/test_evaluator_metrics.py`
新增13个测试用例，验证：
- 初始提问真实度评测（正常开场、过于正式、信息泄露）
- 信息输出节奏评测（正常序列、过早泄露）
- 辅助函数的正确性

## 使用方法

### 导出指标时自动包含新指标
```bash
# 单个case
python3 main.py export-metrics --case_id KT001

# 所有case
python3 main.py export-metrics --all

# 使用LLM judge
python3 main.py export-metrics --case_id KT001 --judge
```

### 模拟器评测时自动包含新指标
```bash
# 单个case
python3 main.py evaluate-simulator --case_id KT001

# 多个case
python3 main.py evaluate-simulator --case_ids KT001 KT002 KT003

# 使用LLM judge
python3 main.py evaluate-simulator --case_id KT001 --judge
```

## 输出文件

### metrics目录
- `outputs/metrics/simulation_metrics.jsonl` - 包含新的评测指标
- `outputs/metrics/summary.md` - 更新的汇总表格

### simulator_eval目录
- `outputs/simulator_eval/simulator_eval.jsonl` - 包含新的评测指标
- `outputs/simulator_eval/summary.md` - 更新的汇总表格
- `outputs/simulator_eval/{case_id}.md` - 详细的case报告

## 技术实现细节

### 文本相似度计算
使用基于token重叠的简单方法：
- 中文：使用2-gram和3-gram
- ASCII：直接提取单词
- 计算 Jaccard 相似度

### 自然度评估
基于规则的启发式方法：
- 长度惩罚：超过150字符扣0.3分，超过80字符扣0.1分
- 内部术语惩罚：检测"roadmap"、"Knowledge Module"等
- 自然标记奖励：检测"我这边"、"帮我看一下"等自然表达
- 正式语言惩罚：检测"烦请"、"关于"等正式表达

### 信息泄露检测
基于内容匹配：
- 检查是否包含diagnostic_points的内容
- 检查是否包含solution_points的内容（严重）
- 检查是否包含external_points的内容
- 检查是否包含forbidden_content的内容

### 节奏评测
基于对话序列分析：
- 诊断信息是否在被追问后才透露
- 信息释放的时机是否合理
- 信息释放的顺序是否合理
- 释放的信息是否与roadmap一致

## 测试结果

所有13个新测试用例均通过：
- 初始提问真实度测试：4/4 通过
- 信息输出节奏测试：3/3 通过
- 辅助函数测试：6/6 通过

现有测试也全部通过，确保向后兼容。

## 未来改进方向

1. **语义相似度增强**：考虑使用embedding模型（如OpenAI embeddings）提升相似度计算精度
2. **LLM judge集成**：将新的评测维度纳入LLM judge的评测范围
3. **阈值调优**：根据实际数据调整各指标的评分阈值
4. **可视化增强**：添加指标趋势图表和对比分析

## 相关文档

- [how_user_simulator_works_and_run_order.md](how_user_simulator_works_and_run_order.md) - 用户模拟器工作原理
- [README.md](../README.md) - 项目总体说明
