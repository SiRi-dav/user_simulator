from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from src.llm.llm_client import LLMClient
from src.runtime.blind_user import BlindUser
from src.runtime.knowledge_module import KnowledgeModule
from src.schemas import BlindUserRuntimeView, DialogueState, RuntimeRoadmap, SimulationTurnLog, model_to_dict
from src.utils.logging import OutputLogger


class Simulator:
    def __init__(
        self,
        blind_view: BlindUserRuntimeView,
        roadmap: RuntimeRoadmap,
        persona: Dict[str, Any],
        llm_client: LLMClient,
        logger: OutputLogger | None = None,
        employee_persona: Dict[str, Any] | None = None,
        behavior_taxonomy: List[Dict[str, Any]] | None = None,
    ):
        self.blind_view = blind_view
        self.roadmap = roadmap
        self.persona = persona
        self.employee_persona = employee_persona or {}
        self.behavior_taxonomy = behavior_taxonomy or []
        self.llm_client = llm_client
        self.blind_user = BlindUser(llm_client)
        self.knowledge_module = KnowledgeModule(llm_client)
        self.state = DialogueState()
        self.dialogue_history: List[Dict[str, str]] = []
        self.logger = logger or OutputLogger(Path("outputs"))

    def start(self) -> str:
        reply = self.blind_user.initial_reply(
            self.blind_view.surface_problem,
            self.blind_view.opening_intent,
            self.persona,
            self.employee_persona,
        )
        self.dialogue_history.append({"role": "user", "content": reply})
        return reply

    def step(self, assistant_text: str) -> Dict[str, Any]:
        self.dialogue_history.append({"role": "assistant", "content": assistant_text})
        assistant_act = self.blind_user.parse_assistant_act(assistant_text, self.dialogue_history)
        assessment = self.knowledge_module.assess(
            assistant_text,
            assistant_act,
            self.roadmap,
            self.state,
            self.dialogue_history,
        )
        action = self.blind_user.choose_action_and_reply(
            assessment,
            self.persona,
            self.employee_persona,
            self.behavior_taxonomy,
            self.blind_view.surface_problem,
            self.dialogue_history,
            self.state,
        )
        self._apply_state_update(assessment.state_update)
        self._apply_state_update(action.state_update)
        self.state.turn_count += 1
        user_reply = action.reply
        self.dialogue_history.append({"role": "user", "content": user_reply})
        turn_log = SimulationTurnLog(
            turn=self.state.turn_count,
            assistant_text=assistant_text,
            assistant_act=assistant_act,
            knowledge_assessment=assessment,
            user_action=action,
            user_reply=user_reply,
            state=self.state,
        )
        self.logger.log(
            "simulation_logs.jsonl",
            self.roadmap.target_case_id,
            "Simulator.step",
            {"assistant_text": assistant_text, "history_before_reply": self.dialogue_history[:-1]},
            turn_log,
        )
        return model_to_dict(turn_log)

    def _apply_state_update(self, update: Dict[str, Any]) -> None:
        for point_id in update.get("exposed_point_ids_add", []) or []:
            if point_id not in self.state.exposed_point_ids:
                self.state.exposed_point_ids.append(str(point_id))
        for point_id in update.get("rejected_external_point_ids_add", []) or []:
            if point_id not in self.state.rejected_external_point_ids:
                self.state.rejected_external_point_ids.append(str(point_id))
        self.state.action_request_count += int(update.get("action_request_count_delta") or 0)
        self.state.how_to_check_count += int(update.get("how_to_check_count_delta") or 0)
        if "pending_action_result" in update:
            self.state.pending_action_result = bool(update.get("pending_action_result"))
        if "last_action_summary" in update:
            value = update.get("last_action_summary")
            self.state.last_action_summary = str(value) if value else None
        if update.get("solution_status"):
            self.state.solution_status = str(update["solution_status"])
        if update.get("should_stop") is not None:
            self.state.should_stop = bool(update["should_stop"])
        if "stop_reason" in update:
            self.state.stop_reason = update.get("stop_reason")
