from __future__ import annotations

from pathlib import Path
from typing import List

from src.behavior_mining.behavior_taxonomy_miner import BehaviorTaxonomyMiner
from src.behavior_mining.persona_miner import PersonaMiner
from src.behavior_mining.prompt_templates import DIALOGUE_SUMMARY_SYSTEM, DIALOGUE_SUMMARY_USER
from src.llm.llm_client import LLMClient
from src.schemas import BehaviorTaxonomy, DialogueBehaviorSummary, EmployeePersona, HistoricalDialogue, model_to_dict
from src.utils.json_utils import dumps_json
from src.utils.jsonl import write_jsonl
from src.utils.logging import OutputLogger


class DialogueBehaviorMiner:
    def __init__(self, llm_client: LLMClient, output_dir: Path, logger: OutputLogger | None = None):
        self.llm_client = llm_client
        self.output_dir = output_dir
        self.logger = logger or OutputLogger(output_dir)
        self.persona_miner = PersonaMiner(llm_client)
        self.taxonomy_miner = BehaviorTaxonomyMiner(llm_client)

    def summarize_dialogue(self, dialogue: HistoricalDialogue) -> DialogueBehaviorSummary:
        user_prompt = DIALOGUE_SUMMARY_USER.format(dialogue_json=dumps_json(model_to_dict(dialogue)))
        payload = self.llm_client.generate_json(
            DIALOGUE_SUMMARY_SYSTEM,
            user_prompt,
            schema_name="DialogueBehaviorSummary",
        )
        return DialogueBehaviorSummary(**payload)

    def mine(self, dialogues: List[HistoricalDialogue]) -> dict[str, list]:
        summaries = [self.summarize_dialogue(dialogue) for dialogue in dialogues]
        personas = self.persona_miner.mine_personas(summaries)
        taxonomy = self.taxonomy_miner.mine_taxonomy(summaries)
        self.save_outputs(summaries, personas, taxonomy)
        self.logger.log(
            "behavior_mining_run.jsonl",
            "behavior_mining",
            "DialogueBehaviorMiner",
            {"dialogue_count": len(dialogues)},
            {
                "summary_count": len(summaries),
                "persona_count": len(personas),
                "taxonomy_count": len(taxonomy),
            },
        )
        return {"summaries": summaries, "personas": personas, "behavior_taxonomy": taxonomy}

    def save_outputs(
        self,
        summaries: List[DialogueBehaviorSummary],
        personas: List[EmployeePersona],
        taxonomy: List[BehaviorTaxonomy],
    ) -> None:
        write_jsonl(self.output_dir / "dialogue_behavior_summaries.jsonl", [model_to_dict(item) for item in summaries])
        write_jsonl(self.output_dir / "employee_personas.jsonl", [model_to_dict(item) for item in personas])
        write_jsonl(self.output_dir / "user_behavior_taxonomy.jsonl", [model_to_dict(item) for item in taxonomy])
