from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_PERSONAS: List[Dict[str, Any]] = [
    {
        "persona_id": "cooperative_normal",
        "name": "普通合作用户",
        "technical_level": "中等",
        "clarity": "较清楚",
        "cooperation": "愿意配合",
        "patience": "中等",
        "disclosure_style": "客服问到时会补充关键信息",
        "language_style": "简短、直接、偏口语",
        "behavior_rules": [
            "开场会描述主要现象，但不会一次说完全部背景",
            "客服追问后通常能补充信息",
            "看到明确方案后倾向于接受并尝试",
        ],
    },
    {
        "persona_id": "vague_low_context",
        "name": "模糊表达用户",
        "technical_level": "中低",
        "clarity": "模糊",
        "cooperation": "被动配合",
        "patience": "中等",
        "disclosure_style": "只说表面现象，需要客服持续追问",
        "language_style": "短句、泛化描述、常说不清楚",
        "behavior_rules": [
            "开场只说功能不好用或报错，不主动给版本、路径、错误码",
            "被问到细节时可能先表示不知道在哪里看",
            "适合测试客服 AI 的澄清追问能力",
        ],
    },
    {
        "persona_id": "low_tech_confused",
        "name": "低技术水平用户",
        "technical_level": "低",
        "clarity": "一般",
        "cooperation": "愿意配合但需要解释",
        "patience": "中等偏低",
        "disclosure_style": "需要把操作说得很具体才会继续",
        "language_style": "口语化、反复确认、容易说看不懂",
        "behavior_rules": [
            "不理解专业名词和路径描述",
            "即使拿到方案，也可能追问具体点哪里",
            "适合测试客服 AI 的步骤解释能力",
        ],
    },
    {
        "persona_id": "impatient_user",
        "name": "急躁用户",
        "technical_level": "中等",
        "clarity": "较清楚但不耐烦",
        "cooperation": "低到中等",
        "patience": "低",
        "disclosure_style": "希望快速解决，不愿反复提供信息",
        "language_style": "语气催促、句子短、会强调影响工作",
        "behavior_rules": [
            "开场会强调问题影响使用或工作",
            "如果客服连续追问，容易催促或反问为什么还需要",
            "适合测试客服 AI 的高效定位能力",
        ],
    },
    {
        "persona_id": "tried_and_failed",
        "name": "已尝试失败用户",
        "technical_level": "中等偏高",
        "clarity": "较清楚",
        "cooperation": "愿意配合",
        "patience": "中等偏低",
        "disclosure_style": "会在方案后补充自己已经试过但失败",
        "language_style": "带有排查经历，常说已经试过、还是不行",
        "behavior_rules": [
            "不一定开场就说已经尝试过",
            "客服给常规方案后，会反馈试过了或没有效果",
            "适合测试客服 AI 的二次排查能力",
        ],
    },
    {
        "persona_id": "high_tech_diagnostic",
        "name": "高技术排障用户",
        "technical_level": "高",
        "clarity": "很清楚",
        "cooperation": "主动配合",
        "patience": "中等",
        "disclosure_style": "会主动提供环境、版本、错误码、复现步骤和已尝试操作",
        "language_style": "结构化、直接、偏技术化",
        "behavior_rules": [
            "开场倾向于同时说明现象、环境和关键报错",
            "不需要客服多次追问就会主动补充定位信息",
            "适合测试客服 AI 对高信息密度用户输入的理解和快速命中能力",
        ],
    },
    {
        "persona_id": "screenshot_dependent",
        "name": "截图依赖用户",
        "technical_level": "中低",
        "clarity": "依赖截图",
        "cooperation": "愿意配合",
        "patience": "中等",
        "disclosure_style": "倾向于说有截图或让客服看现象",
        "language_style": "描述不完整，常用你看这个、如图、这个提示",
        "behavior_rules": [
            "开场可能只说报错并提到截图",
            "文字描述较少，需要客服引导提取关键信息",
            "适合测试客服 AI 面对不完整文本描述时的追问能力",
        ],
    },
]


def load_personas(path: str = "") -> List[Dict[str, Any]]:
    if not path:
        return DEFAULT_PERSONAS
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("persona bank must be a JSON list")
    result = []
    for record in records:
        if isinstance(record, dict) and record.get("persona_id"):
            result.append(record)
    if not result:
        raise ValueError("persona bank contains no valid persona records")
    return result


def choose_persona(
    personas: List[Dict[str, Any]],
    persona_id: str,
    case_id: str,
    mode: str,
) -> Dict[str, Any]:
    if persona_id and persona_id != "auto":
        for persona in personas:
            if persona.get("persona_id") == persona_id:
                return persona
        valid = ", ".join(str(item.get("persona_id")) for item in personas)
        raise ValueError(f"unknown persona_id: {persona_id}. valid personas: {valid}")

    key = f"{case_id}|{mode}".encode("utf-8")
    digest = hashlib.md5(key).hexdigest()
    index = int(digest[:8], 16) % len(personas)
    return personas[index]


def persona_summary(persona: Dict[str, Any]) -> str:
    fields = [
        ("name", "类型"),
        ("technical_level", "技术水平"),
        ("clarity", "表达清晰度"),
        ("cooperation", "配合程度"),
        ("patience", "耐心"),
        ("disclosure_style", "信息透露"),
        ("language_style", "语言风格"),
    ]
    parts = []
    for key, label in fields:
        value = str(persona.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    return "；".join(parts)
