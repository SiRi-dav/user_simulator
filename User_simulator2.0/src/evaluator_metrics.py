"""
Enhanced evaluation metrics for user simulator.

This module provides additional metrics for:
1. Opening Realism (Initial Question Quality) - semantic similarity with target case
2. Information Rhythm (Information Release Pattern) - timing, sequence, and accuracy
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from src.schemas import KnowledgeRoadmapArtifact, model_to_dict


# Chinese tokenization patterns
CJK_RE = re.compile(r"[一-鿿]")
ASCII_TOKEN_RE = re.compile(r"[a-zA-Z0-9_+#.-]+")


def opening_realism_stats(
    transcript: Dict[str, Any],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    """
    Evaluate the realism of the user's opening statement.

    Metrics:
    - surface_semantic_similarity: How similar the opening is to the target case surface problem
    - opening_naturalness_score: Whether the opening sounds like a real user's question
    - opening_info_leak_risk: Whether the opening prematurely reveals diagnostic information

    Args:
        transcript: The simulated dialogue transcript
        artifact: The knowledge roadmap artifact for the target case

    Returns:
        Dict containing opening realism metrics
    """
    messages = transcript.get("messages") or []
    if not messages:
        return {
            "has_opening": False,
            "surface_semantic_similarity": 0.0,
            "opening_naturalness_score": 0.0,
            "opening_info_leak_risk": 0.0,
            "opening_realism_score": 0.0,
            "opening_text": "",
        }

    # Extract the first user message as the opening
    opening_text = ""
    for message in messages:
        if message.get("role") == "user":
            opening_text = str(message.get("content") or "")
            break

    if not opening_text:
        return {
            "has_opening": False,
            "surface_semantic_similarity": 0.0,
            "opening_naturalness_score": 0.0,
            "opening_info_leak_risk": 0.0,
            "opening_realism_score": 0.0,
            "opening_text": "",
        }

    # Get target case surface problem
    surface_problem = ""
    if artifact:
        surface_problem = artifact.roadmap.surface_problem or ""

    # Calculate semantic similarity with surface problem
    surface_similarity = calculate_text_similarity(opening_text, surface_problem)

    # Calculate naturalness score
    naturalness = calculate_opening_naturalness(opening_text)

    # Check for information leak in opening
    leak_risk = calculate_opening_leak_risk(opening_text, artifact)

    # Combined score
    realism_score = round(
        (surface_similarity * 0.5 + naturalness * 0.3 + (1.0 - leak_risk) * 0.2), 3
    )

    return {
        "has_opening": True,
        "surface_semantic_similarity": round(surface_similarity, 3),
        "opening_naturalness_score": round(naturalness, 3),
        "opening_info_leak_risk": round(leak_risk, 3),
        "opening_realism_score": realism_score,
        "opening_text": opening_text[:200],  # Truncate for storage
    }


def information_rhythm_stats(
    transcript: Dict[str, Any],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    """
    Evaluate the rhythm and pattern of information release.

    Metrics:
    - premature_diagnostic_rate: Whether diagnostic info is revealed before being asked
    - info_release_timing_score: Whether information is released at appropriate times
    - info_sequence_rationality: Whether information follows a logical sequence
    - info_accuracy_score: Whether released information matches roadmap points

    Args:
        transcript: The simulated dialogue transcript
        artifact: The knowledge roadmap artifact for the target case

    Returns:
        Dict containing information rhythm metrics
    """
    if artifact is None:
        return {
            "premature_diagnostic_rate": 0.0,
            "info_release_timing_score": 0.0,
            "info_sequence_rationality": 0.0,
            "info_accuracy_score": 0.0,
            "information_rhythm_score": 0.0,
        }

    messages = transcript.get("messages") or []
    user_messages = [
        msg for msg in messages if msg.get("role") == "user"
    ]

    if not user_messages:
        return {
            "premature_diagnostic_rate": 0.0,
            "info_release_timing_score": 0.0,
            "info_sequence_rationality": 0.0,
            "info_accuracy_score": 0.0,
            "information_rhythm_score": 0.0,
        }

    roadmap = artifact.roadmap

    # Extract diagnostic point contents for comparison
    diagnostic_contents = [point.content for point in roadmap.diagnostic_points]
    solution_contents = [point.content for point in roadmap.solution_points]
    external_contents = [point.content for point in roadmap.external_points]

    # Analyze each user turn
    premature_count = 0
    timing_score = 0.0
    sequence_violations = 0
    accuracy_matches = 0

    prev_assistant_was_question = False
    released_diagnostic_info = set()

    for i, user_msg in enumerate(user_messages):
        user_text = str(user_msg.get("content") or "")

        # Get the previous assistant message to check if it was a question
        prev_assistant_text = ""
        if i > 0:
            for j in range(len(messages) - 1, -1, -1):
                if messages[j].get("role") == "assistant" and messages[j].get("turn") == user_msg.get("turn", i) - 1:
                    prev_assistant_text = str(messages[j].get("content") or "")
                    break

        prev_assistant_was_question = is_question(prev_assistant_text)

        # Check for premature diagnostic info release
        diagnostic_match = False
        for diag_content in diagnostic_contents:
            if text_contains_content(user_text, diag_content):
                diagnostic_match = True
                if not prev_assistant_was_question and i == 0:
                    # First message shouldn't contain diagnostic info
                    premature_count += 1
                elif not prev_assistant_was_question and diag_content not in released_diagnostic_info:
                    # Diagnostic info revealed without being asked
                    premature_count += 1
                released_diagnostic_info.add(diag_content)
                break

        # Evaluate timing: positive if info follows a question or clarification
        if diagnostic_match and prev_assistant_was_question:
            timing_score += 1.0
        elif not diagnostic_match and user_text and not prev_assistant_was_question:
            # User volunteering information without being asked
            timing_score += 0.5

        # Check sequence rationality
        if i > 0 and diagnostic_match:
            # Diagnostic info should come after initial problem description
            timing_score += 0.5

        # Check accuracy: match with roadmap points
        accuracy_matches += check_info_accuracy(user_text, roadmap)

    # Calculate normalized scores
    total_user_turns = len(user_messages)
    premature_rate = safe_rate(premature_count, total_user_turns, default=0.0)

    timing_score_norm = safe_rate(timing_score, total_user_turns, default=0.0)
    sequence_score = 1.0 - min(1.0, safe_rate(sequence_violations, total_user_turns, default=0.0))
    accuracy_score = safe_rate(accuracy_matches, total_user_turns, default=0.0)

    rhythm_score = round(
        (1.0 - premature_rate) * 0.4 + timing_score_norm * 0.3 + sequence_score * 0.15 + accuracy_score * 0.15,
        3
    )

    return {
        "premature_diagnostic_rate": round(premature_rate, 3),
        "info_release_timing_score": round(timing_score_norm, 3),
        "info_sequence_rationality": round(sequence_score, 3),
        "info_accuracy_score": round(accuracy_score, 3),
        "information_rhythm_score": rhythm_score,
    }


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate semantic similarity between two texts using token overlap.

    This is a simple similarity metric based on shared tokens.
    For production, consider using embeddings or more sophisticated NLP.
    """
    if not text1 or not text2:
        return 0.0

    tokens1 = set(tokenize_chinese(text1))
    tokens2 = set(tokenize_chinese(text2))

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    return len(intersection) / len(union) if union else 0.0


def tokenize_chinese(text: str) -> List[str]:
    """
    Tokenize Chinese text into bigrams and trigrams plus ASCII tokens.

    This is a simple tokenizer. For production, consider using jieba or similar.
    """
    text = str(text).lower()
    tokens = []

    # Extract ASCII tokens
    tokens.extend(ASCII_TOKEN_RE.findall(text))

    # Extract Chinese characters
    cjk_chars = CJK_RE.findall(text)

    # Generate bigrams and trigrams
    for i in range(len(cjk_chars) - 1):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1])
    for i in range(len(cjk_chars) - 2):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1] + cjk_chars[i + 2])

    return tokens


def calculate_opening_naturalness(opening_text: str) -> float:
    """
    Calculate how natural the opening sounds.

    A natural opening should:
    - Not be too long (real users are concise)
    - Not use overly formal language
    - Not include internal terminology
    - Sound like a problem description

    Returns a score between 0.0 and 1.0.
    """
    if not opening_text:
        return 0.0

    # Penalize very long openings
    length = len(opening_text)
    if length > 150:
        length_penalty = 0.3
    elif length > 80:
        length_penalty = 0.1
    else:
        length_penalty = 0.0

    # Penalize internal terminology
    internal_terms = ["user-facing", "diagnostic", "solution point", "external", "roadmap", "Knowledge Module"]
    has_internal = any(term.lower() in opening_text.lower() for term in internal_terms)
    internal_penalty = 0.5 if has_internal else 0.0

    # Reward natural language patterns
    natural_markers = ["我", "我这边", "帮我看", "怎么", "问题", "不行", "打不开", "进不去"]
    has_natural = any(marker in opening_text for marker in natural_markers)
    natural_bonus = 0.2 if has_natural else 0.0

    # Penalize overly formal language
    formal_markers = ["请您", "烦请", "恳请", "关于", "鉴于", "特此"]
    has_formal = any(marker in opening_text for marker in formal_markers)
    formal_penalty = 0.3 if has_formal else 0.0

    score = 1.0 - length_penalty - internal_penalty - formal_penalty + natural_bonus
    return round(max(0.0, min(1.0, score)), 3)


def calculate_opening_leak_risk(
    opening_text: str,
    artifact: KnowledgeRoadmapArtifact | None,
) -> float:
    """
    Calculate the risk of information leak in the opening.

    Returns a score between 0.0 (no leak) and 1.0 (high leak risk).
    """
    if not opening_text or artifact is None:
        return 0.0

    roadmap = artifact.roadmap

    # Check for diagnostic point content
    for point in roadmap.diagnostic_points:
        if text_contains_content(opening_text, point.content):
            return 1.0  # High risk: diagnostic info in opening

    # Check for solution content (this should never happen)
    for point in roadmap.solution_points:
        if text_contains_content(opening_text, point.content):
            return 1.0  # Critical risk: solution in opening

    # Check for external case content
    for point in roadmap.external_points:
        if text_contains_content(opening_text, point.content):
            return 0.8  # High risk: external info in opening

    # Check for forbidden content
    for forbidden in roadmap.forbidden_content:
        if text_contains_content(opening_text, forbidden):
            return 0.9  # High risk: forbidden content in opening

    return 0.0  # No leak detected


def text_contains_content(user_text: str, content: str) -> bool:
    """
    Check if user text contains the specified content.

    Uses character-level matching for Chinese text.
    """
    if not content or len(content) < 4:
        return False

    content_normalized = content.strip().lower()
    user_normalized = user_text.strip().lower()

    # Direct substring match
    if content_normalized in user_normalized:
        return True

    # Character-level overlap for Chinese
    content_chars = set(char for char in content_normalized if CJK_RE.match(char))
    user_chars = set(char for char in user_normalized if CJK_RE.match(char))

    if len(content_chars) < 3:
        return False

    overlap = content_chars & user_chars
    overlap_ratio = len(overlap) / len(content_chars) if content_chars else 0

    return overlap_ratio >= 0.6


def check_info_accuracy(user_text: str, roadmap: Any) -> float:
    """
    Check if user text accurately reflects roadmap points.

    Returns 1.0 if accurate, 0.0 if not.
    """
    # Collect all allowed point contents
    allowed_contents = []
    allowed_contents.extend([p.content for p in roadmap.user_facing_points])
    allowed_contents.extend([p.content for p in roadmap.diagnostic_points])

    # Check if user text matches any allowed content
    for content in allowed_contents:
        if text_contains_content(user_text, content):
            return 1.0

    return 0.0


def is_question(text: str) -> bool:
    """Check if text is a question."""
    if not text:
        return False
    question_markers = ("吗", "？", "?", "是否", "有没有", "是不是", "哪个", "什么", "能否", "可否")
    return any(marker in text for marker in question_markers)


def safe_rate(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely calculate a rate."""
    return float(numerator) / float(denominator) if denominator else default
