from src.data_loader import load_cases


def test_load_cases_supports_keyed_company_case_format(tmp_path):
    case_file = tmp_path / "cases.json"
    case_file.write_text(
        """
{
  "KT00141862": {
    "case_name": "在门店无法正常录单，提交单子，就会显示不在物流专员分组",
    "text": [
      "在门店无法正常录单，提交单子，就会显示不在物流专员分组",
      "首先确认用户权限是否到期，在管理人员功能下查询",
      "如果确认权限都正常，又是新账号数据的情况的话，需要等待第一天才能正常集成"
    ]
  }
}
""",
        encoding="utf-8",
    )

    cases = load_cases(
        case_file,
        {
            "case_id": "__key__",
            "title": "case_name",
            "phenomenon": "text",
            "solution": "text",
        },
    )

    assert cases[0].case_id == "KT00141862"
    assert cases[0].title == "在门店无法正常录单，提交单子，就会显示不在物流专员分组"
    assert "首先确认用户权限是否到期" in cases[0].phenomenon
    assert "需要等待第一天才能正常集成" in cases[0].solution
