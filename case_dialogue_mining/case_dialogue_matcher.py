from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from schemas import CaseDialoguePair, CaseRecord, DialogueRecord, MiningStats


def match_cases_and_dialogues(
    cases: List[CaseRecord],
    dialogues: List[DialogueRecord],
) -> Tuple[List[CaseDialoguePair], MiningStats]:
    case_by_id: Dict[str, CaseRecord] = {case.case_id: case for case in cases}
    dialogues_by_case_id: Dict[str, List[DialogueRecord]] = defaultdict(list)

    stats = MiningStats(total_cases=len(cases), total_dialogues=len(dialogues))

    for dialogue in dialogues:
        if not dialogue.case_id:
            stats.missing_case_id_dialogues += 1
            continue
        if dialogue.case_id not in case_by_id:
            stats.unknown_case_id_dialogues += 1
            continue
        dialogues_by_case_id[dialogue.case_id].append(dialogue)

    pairs = [
        CaseDialoguePair(case=case_by_id[case_id], dialogues=case_dialogues)
        for case_id, case_dialogues in sorted(dialogues_by_case_id.items())
    ]
    stats.matched_cases = len(pairs)
    stats.matched_dialogues = sum(len(pair.dialogues) for pair in pairs)
    stats.unmatched_cases = stats.total_cases - stats.matched_cases
    return pairs, stats

