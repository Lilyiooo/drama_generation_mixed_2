import json

import pytest

from service.drama_by_creativity.structured_state_memory import (
    StructuredStateMemory,
    apply_patch,
    empty_state,
    retrieve_state,
    validate_extraction,
)


def extraction(patch, summary="本集发生了足以供后续理解的关键变化。"):
    base = {
        "characters": {}, "relationships": {}, "assets": {},
        "delete_characters": [], "delete_relationships": [], "delete_assets": [],
    }
    base.update(patch)
    return {"patch": base, "summary": summary}


def test_patch_preserves_untouched_and_overwrites_only_affected_state():
    previous = {
        "characters": {
            "沈青辞": {"身份与立场": "她是暗中查案的医女。", "身体状态": "左臂有伤。"},
            "萧凛": {"位置与处境": "他被困在将军府。"},
        },
        "relationships": {
            "沈青辞|萧凛": {"participants": ["沈青辞", "萧凛"], "states": {"信任状态": "彼此仍有戒心。"}}
        },
        "assets": {
            "黑色令牌": {"kind": "object", "states": {"持有与控制": "令牌在沈青辞手中。", "状态与效力": "令牌完好。"}}
        },
    }
    result, changes = apply_patch(previous, extraction({
        "characters": {"沈青辞": {"set": {"身体状态": "左臂伤口已经包扎。"}, "delete": []}},
        "relationships": {},
        "assets": {"黑色令牌": {"kind": "object", "set": {"持有与控制": "令牌被萧凛夺走。"}, "delete": []}},
    }))
    assert result["characters"]["沈青辞"]["身份与立场"] == "她是暗中查案的医女。"
    assert result["characters"]["沈青辞"]["身体状态"] == "左臂伤口已经包扎。"
    assert result["characters"]["萧凛"] == previous["characters"]["萧凛"]
    assert result["relationships"] == previous["relationships"]
    assert result["assets"]["黑色令牌"]["states"]["状态与效力"] == "令牌完好。"
    assert len(changes["changed"]) == 2


def test_first_relationship_patch_infers_participants_when_omitted():
    result, changes = apply_patch(empty_state(), extraction({
        "relationships": {
            "沈青辞|萧凛": {
                "set": {"信任状态": "二人暂时合作但仍互相戒备。"},
                "delete": [],
            }
        }
    }))
    relationship = result["relationships"]["沈青辞|萧凛"]
    assert relationship["participants"] == ["沈青辞", "萧凛"]
    assert relationship["states"]["信任状态"] == "二人暂时合作但仍互相戒备。"
    assert len(changes["changed"]) == 1


def test_existing_relationship_reuses_first_participants():
    previous = {
        "characters": {},
        "relationships": {
            "沈青辞|萧凛": {
                "participants": ["沈青辞", "萧凛"],
                "states": {"信任状态": "二人暂时合作但仍互相戒备。"},
            }
        },
        "assets": {},
    }
    result, _ = apply_patch(previous, extraction({
        "relationships": {
            "沈青辞|萧凛": {
                "participants": ["错误人物甲", "错误人物乙"],
                "set": {"信任状态": "二人的信任有所加深。"},
                "delete": [],
            }
        }
    }))
    relationship = result["relationships"]["沈青辞|萧凛"]
    assert relationship["participants"] == ["沈青辞", "萧凛"]
    assert relationship["states"]["信任状态"] == "二人的信任有所加深。"


def test_asset_kind_is_not_restricted_by_validator():
    value = extraction({
        "assets": {
            "特殊叙事资产": {
                "kind": "custom_kind",
                "set": {"状态": "该资产当前仍然有效。"},
                "delete": [],
            }
        }
    })
    assert validate_extraction(value) is value


def test_missing_entity_delete_is_normalized_to_empty_list():
    value = extraction({
        "characters": {
            "谢辞": {"set": {"身体状态": "谢辞本集结束时仍然清醒。"}},
        },
        "relationships": {
            "苏九歌|谢辞": {"set": {"信任状态": "二人的信任有所加深。"}},
        },
        "assets": {
            "兵符": {"kind": "object", "set": {"持有与控制": "兵符由谢辞持有。"}},
        },
    })

    assert validate_extraction(value) is value
    assert value["patch"]["characters"]["谢辞"]["delete"] == []
    assert value["patch"]["relationships"]["苏九歌|谢辞"]["delete"] == []
    assert value["patch"]["assets"]["兵符"]["delete"] == []


def test_explicit_invalid_entity_delete_type_still_fails():
    value = extraction({
        "characters": {
            "谢辞": {
                "set": {"身体状态": "谢辞本集结束时仍然清醒。"},
                "delete": "身体状态",
            },
        },
    })

    with pytest.raises(ValueError, match=r"谢辞\.delete必须是文字列表"):
        validate_extraction(value)


def test_retrieval_selects_named_character_relationship_and_asset():
    state = {
        "characters": {
            "沈青辞": {"身体状态": "左臂伤口已经包扎。", "知情状态": "她知道令牌可开启地牢。"},
            "无关路人": {"位置与处境": "他在遥远市集卖茶。"},
        },
        "relationships": {
            "沈青辞|萧凛": {"participants": ["沈青辞", "萧凛"], "states": {"信任状态": "二人暂时结盟但仍互相试探。"}}
        },
        "assets": {
            "黑色令牌": {"kind": "object", "states": {"持有与控制": "令牌被萧凛握在手中。"}},
            "茶摊": {"kind": "environment", "states": {"开放状态": "茶摊正常营业。"}},
        },
    }
    context, audit = retrieve_state(state, "沈青辞追上萧凛，争夺黑色令牌并质问二人的结盟。", 8, budget=1000)
    assert "沈青辞" in context and "萧凛" in context and "黑色令牌" in context
    assert "无关路人" not in context and "茶摊" not in context
    assert audit["selected_records"] >= 3


def test_retrieval_obeys_record_limit_independently_of_character_budget():
    state = {
        "characters": {
            "沈青辞": {f"相关状态{i:02d}": f"沈青辞正在处理令牌线索{i:02d}。" for i in range(30)},
        },
        "relationships": {},
        "assets": {},
    }
    context, audit = retrieve_state(
        state, "沈青辞继续调查令牌线索。", 8, budget=6000, max_records=20
    )
    assert audit["max_records"] == 20
    assert audit["selected_records"] == 20
    assert len(audit["selected"]) == 20
    assert all(record["attribute"].startswith("相关状态") for record in audit["selected"])


def test_persistence_supports_resume_and_episode_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("DRAMA_OUTPUT_DIR", str(tmp_path))
    memory = StructuredStateMemory("story")
    first = extraction({"characters": {"甲": {"set": {"位置": "甲在城门。"}, "delete": []}}}, "第一集摘要")
    memory.commit(0, first)
    reloaded = StructuredStateMemory("story")
    assert reloaded.data["state"]["characters"]["甲"]["位置"] == "甲在城门。"
    second = extraction({"characters": {"甲": {"set": {"位置": "甲已进入王府。"}, "delete": []}}}, "重跑后的第一集摘要")
    reloaded.commit(0, second)
    final = json.loads(reloaded.path and open(reloaded.path, encoding="utf-8").read())
    assert final["state"]["characters"]["甲"]["位置"] == "甲已进入王府。"
    assert len(final["history"]) == 1
