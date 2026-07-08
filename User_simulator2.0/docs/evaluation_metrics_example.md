"""
用户模拟器评测指标使用示例

演示新增的两个评测维度：
1. 初始提问真实度 (Opening Realism)
2. 信息输出节奏 (Information Rhythm)
"""

# 示例1：初始提问真实度评测

from src.evaluator_metrics import opening_realism_stats
from src.schemas import KnowledgeRoadmapArtifact, RuntimePoint, RuntimeRoadmap

# 构建测试roadmap
roadmap = RuntimeRoadmap(
    target_case_id="KT001",
    surface_problem="Outlook打开后自动退出",
    opening_intent="解决Outlook打开后退出的问题",
    user_facing_points=[
        RuntimePoint(
            point_id="P1",
            content="Outlook打开后自动退出",
            point_type="user_facing",
            visibility="opening_available",
        )
    ],
    diagnostic_points=[
        RuntimePoint(
            point_id="P2",
            content="没有显示错误提示",
            point_type="diagnostic",
            trigger=["问错误信息"],
            visibility="ask_triggered",
        )
    ],
    solution_points=[],
    external_points=[],
    relations=[],
    target_route=[],
    external_routes=[],
    forbidden_content=["重新安装", "修复模式"],
)

artifact = KnowledgeRoadmapArtifact(
    case_id="KT001",
    title="Outlook打开后退出",
    roadmap=roadmap,
)

# 示例对话
transcript = {
    "case_id": "KT001",
    "turn_count": 1,
    "stop_reason": "",
    "solution_status": "not_solved",
    "messages": [
        {"role": "user", "content": "我这边Outlook一打开就退出来了，帮我看一下。"},
    ],
}

# 计算初始提问真实度
metrics = opening_realism_stats(transcript, artifact)

print("=== 初始提问真实度评测 ===")
print(f"是否有开场白: {metrics['has_opening']}")
print(f"与目标案例相似度: {metrics['surface_semantic_similarity']:.3f}")
print(f"开场白自然度: {metrics['opening_naturalness_score']:.3f}")
print(f"信息泄露风险: {metrics['opening_info_leak_risk']:.3f}")
print(f"综合评分: {metrics['opening_realism_score']:.3f}")

# 预期输出:
# 是否有开场白: True
# 与目标案例相似度: 0.077 (取决于token重叠)
# 开场白自然度: 1.000 (自然表达)
# 信息泄露风险: 0.000 (无泄露)
# 综合评分: 0.388 (综合计算)


# 示例2：信息输出节奏评测

from src.evaluator_metrics import information_rhythm_stats

# 好的信息节奏示例
good_rhythm_transcript = {
    "case_id": "KT001",
    "turn_count": 3,
    "stop_reason": "",
    "solution_status": "not_solved",
    "messages": [
        {"role": "user", "content": "我这边Outlook一打开就退出来了，帮我看一下。", "turn": 1},
        {"role": "assistant", "content": "有显示错误提示吗？", "turn": 1},
        {"role": "user", "content": "没有显示错误提示。", "turn": 2},
        {"role": "assistant", "content": "是点击图标后就闪退吗？", "turn": 2},
        {"role": "user", "content": "是的，点击图标后就闪退。", "turn": 3},
    ],
}

rhythm_metrics = information_rhythm_stats(good_rhythm_transcript, artifact)

print("\n=== 信息输出节奏评测 ===")
print(f"过早透露诊断信息比例: {rhythm_metrics['premature_diagnostic_rate']:.3f}")
print(f"信息释放时机评分: {rhythm_metrics['info_release_timing_score']:.3f}")
print(f"信息顺序合理性: {rhythm_metrics['info_sequence_rationality']:.3f}")
print(f"信息准确性: {rhythm_metrics['info_accuracy_score']:.3f}")
print(f"综合评分: {rhythm_metrics['information_rhythm_score']:.3f}")

# 预期输出:
# 过早透露诊断信息比例: 0.000 (诊断信息在被问时才透露)
# 信息释放时机评分: 0.667 (合理的时机)
# 信息顺序合理性: 1.000 (合理的顺序)
# 信息准确性: 0.667 (信息与roadmap一致)
# 综合评分: 0.500 (综合计算)


# 示例3：不好的信息节奏（过早泄露）

bad_rhythm_transcript = {
    "case_id": "KT001",
    "turn_count": 1,
    "stop_reason": "",
    "solution_status": "not_solved",
    "messages": [
        {"role": "user", "content": "我这边Outlook打开后退出了，没有显示错误提示。", "turn": 1},
    ],
}

bad_rhythm_metrics = information_rhythm_stats(bad_rhythm_transcript, artifact)

print("\n=== 不好的信息节奏（过早泄露）===")
print(f"过早透露诊断信息比例: {bad_rhythm_metrics['premature_diagnostic_rate']:.3f}")
print(f"综合评分: {bad_rhythm_metrics['information_rhythm_score']:.3f}")

# 预期输出:
# 过早透露诊断信息比例: 1.000 (第一轮就透露了诊断信息)
# 综合评分: 0.400 (被惩罚)
