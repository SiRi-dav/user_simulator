from pathlib import Path

from src.behavior_mining.behavior_miner import DialogueBehaviorMiner
from src.behavior_mining.dialogue_loader import load_dialogues
from src.llm.mock_llm_client import MockLLMClient


def test_dialogue_behavior_miner_outputs_three_artifacts(tmp_path: Path):
    dialogue_file = tmp_path / "dialogues.jsonl"
    dialogue_file.write_text(
        '{"dialogue_id":"DIALOG_001","case_id":"CASE_001","turns":[{"speaker":"user","text":"我这边 Outlook 打不开，一点开就退出来了。"},{"speaker":"assistant","text":"是登录不上还是打开就退出？"},{"speaker":"user","text":"是打开以后就直接退出来了，还没到登录那一步。"}],"resolved":true}\n',
        encoding="utf-8",
    )
    dialogues = load_dialogues(dialogue_file)
    result = DialogueBehaviorMiner(MockLLMClient(), tmp_path).mine(dialogues)
    assert result["summaries"]
    assert result["personas"][0].persona_id == "persona_low_tech_cooperative"
    assert result["behavior_taxonomy"]
    assert (tmp_path / "dialogue_behavior_summaries.jsonl").exists()
    assert (tmp_path / "employee_personas.jsonl").exists()
    assert (tmp_path / "user_behavior_taxonomy.jsonl").exists()


def test_dialogue_loader_accepts_uppercase_case_id_list(tmp_path: Path):
    dialogue_file = tmp_path / "dialogues.json"
    dialogue_file.write_text(
        '{"220061420":{"text":[{"用户":"windows升级到版本11后，历史邮件内容不显示了。"},{"客服":"请问outlook里面的存档文件夹打开可以正常查看吗？"}],"CaseID":["KT00229838"]}}',
        encoding="utf-8",
    )

    dialogues = load_dialogues(dialogue_file)

    assert len(dialogues) == 1
    assert dialogues[0].dialogue_id == "220061420"
    assert dialogues[0].case_id == "KT00229838"
