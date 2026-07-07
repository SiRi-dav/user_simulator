from main import load_behavior_taxonomy, load_employee_personas
from src.llm.mock_llm_client import MockLLMClient
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.runtime.blind_user import BlindUser
from src.runtime.simulator import Simulator
from src.schemas import BlindUserInstruction, Case


class PromptCaptureLLMClient(MockLLMClient):
    def __init__(self):
        self.last_user_prompt = ""

    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        self.last_user_prompt = user_prompt
        if schema_name == "BlindUserReply":
            return {"reply": "好的。"}
        return super().generate_json(system_prompt, user_prompt, schema_name, temperature)


def test_runtime_step_solved_sets_should_stop():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    roadmap = RoadmapBuilder(llm).build_roadmap(target, [], [])
    simulator = Simulator(roadmap, {"name": "low_tech"}, llm)
    simulator.start()
    result = simulator.step("你可以先结束 Outlook 的残留进程再重新打开。")
    assert result["state"]["solution_status"] == "solved"
    assert result["state"]["should_stop"] is True
    assert result["user_reply"]


def test_runtime_loads_manual_seed_behavior_assets_when_outputs_missing(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()

    personas = load_employee_personas(output_dir / "employee_personas.jsonl")
    taxonomy = load_behavior_taxonomy(output_dir / "user_behavior_taxonomy.jsonl")

    assert personas[0].persona_id == "persona_real_problem_low_tech"
    assert {item.behavior_name for item in taxonomy} >= {
        "陈述或继续澄清问题",
        "回答客服并释放信息",
        "询问具体操作办法",
    }


def test_blind_user_reply_prompt_hides_specific_forbidden_solution_text():
    llm = PromptCaptureLLMClient()
    instruction = BlindUserInstruction(
        user_intent="确认方案",
        allowed_content="好的，我试一下。",
        forbidden_content=["结束 Outlook 残留进程后重新打开", "CASE_001"],
        tone="low_tech",
    )

    BlindUser(llm).render_reply(instruction, {"name": "low_tech"}, None, [], "Outlook 打不开", [])

    assert "结束 Outlook 残留进程后重新打开" not in llm.last_user_prompt
    assert "CASE_001" not in llm.last_user_prompt
    assert "hidden_solution_or_case_details" in llm.last_user_prompt
