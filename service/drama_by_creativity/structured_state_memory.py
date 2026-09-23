"""Compact current-state memory for characters, relationships and assets."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple


STATE_UPDATE_PROMPT = r"""
你是连续剧的当前状态维护器。请只根据本集最终剧本，更新人物、人物关系和资产/环境的当前状态。

状态是“本集结束时仍成立的快照”，不是剧情流水账。每个主体下面用若干个短小、稳定的状态属性记录不同方面；每个属性值只用一句话概括。

## 当前集
第 {{EpisodeNumber}} 集

## 本集大纲
{{EpisodeOutline}}

## 当前集开始前的完整状态快照
{{PreviousState}}

## 本集最终剧本
{{EpisodeScript}}

## 更新规则
1. 只输出本集确实影响到的主体和属性。未输出的主体和属性由程序逐字保留，绝不能为了压缩而删除。
2. `set` 用于新增属性或覆盖已有属性；状态值必须描述本集结束时的当前事实，并且每项只写一句话。
3. `delete` 只用于本集明确使某个旧属性失效且没有新值替代时；有新值时直接放进 `set`。每个主体都必须输出 `delete`；没有要删除的属性时输出空数组 `[]`。
4. 只有主体从故事当前状态中彻底失去保留价值时，才能放入 `delete_characters`、`delete_relationships` 或 `delete_assets`。
5. 人物状态可按身份与立场、身体状态、位置与处境、心理与目标、能力与限制、知情状态等方面取舍；每人最多8项。
6. 关系状态可按关系性质、信任状态、冲突与亏欠、承诺与边界等方面取舍；每段关系最多6项。关系键必须使用全部参与者姓名以“|”连接。关系首次出现时可输出 `participants`；若省略，程序会从关系键补全。已有关系后续更新时可省略该字段。
7. 人物或角色相关的状态记忆不应放入资产状态，必须记录在 `characters` 中。资产状态主要记录具体物品、道具、证据、地点与环境、组织势力和世界规则，可按持有与控制、位置、完好程度、效力、开放/封锁状态等方面取舍；每项资产最多6项。
8. 不得把观众知道的事写成人物知道，不得把计划写成已经完成，不得从大纲补写剧本中没有发生的变化。
9. `summary` 用200～350字按因果顺序概括本集实际发生的关键行动、结果、人物/关系/资产变化和集末处境，供后续集阅读。

只输出合法 JSON 对象：
{
  "patch": {
    "characters": {
      "人物名": {"set": {"状态属性": "本集结束时的一句话状态。"}, "delete": []}
    },
    "relationships": {
      "人物甲|人物乙": {
        "participants": ["人物甲", "人物乙"],
        "set": {"关系属性": "本集结束时的一句话状态。"},
        "delete": []
      }
    },
    "assets": {
      "物品或环境名": {
        "kind": "object|environment|place|organization|rule|other",
        "set": {"状态属性": "本集结束时的一句话状态。"},
        "delete": []
      }
    },
    "delete_characters": [],
    "delete_relationships": [],
    "delete_assets": []
  },
  "summary": "本集摘要"
}
{% if ValidationFeedback %}
上次输出未通过校验：{{ValidationFeedback}}
{% endif %}
"""

MAX_ATTRS = {"characters": 8, "relationships": 6, "assets": 6}


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]+", "_", value or "story")[:120] or "story"


def _atomic_dump(path: str, value: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".state_", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def empty_state() -> Dict[str, Dict[str, Any]]:
    return {"characters": {}, "relationships": {}, "assets": {}}


def state_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sentence(value: Any, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        raise ValueError("状态值不能为空")
    if len(text) > limit:
        raise ValueError(f"状态值超过{limit}字：{text[:30]}")
    return text


def _string_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field}必须是文字列表")
    return [item.strip() for item in value]


def _relationship_key(value: str) -> str:
    names = _relationship_participants(value)
    return "|".join(sorted(dict.fromkeys(names))) if len(names) >= 2 else value.strip()


def _relationship_participants(value: str) -> List[str]:
    names = [name.strip() for name in re.split(r"[|｜/、]", value) if name.strip()]
    return list(dict.fromkeys(names))


def validate_extraction(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("patch"), dict):
        raise ValueError("缺少patch对象")
    patch = value["patch"]
    for category in ("characters", "relationships", "assets"):
        if not isinstance(patch.get(category), dict):
            raise ValueError(f"patch.{category}必须是对象")
        for entity, operation in patch[category].items():
            if not isinstance(entity, str) or not entity.strip() or not isinstance(operation, dict):
                raise ValueError(f"patch.{category}主体或操作无效")
            if not isinstance(operation.get("set"), dict):
                raise ValueError(f"{entity}.set必须是对象")
            # 模型常省略语义上为空的 delete。缺失与 [] 完全等价，可安全补齐；
            # 如果模型明确输出了错误类型，下面的严格校验仍会报错并触发重试。
            if "delete" not in operation:
                operation["delete"] = []
            _string_list(operation.get("delete"), f"{entity}.delete")
            if len(operation["set"]) > MAX_ATTRS[category]:
                raise ValueError(f"{entity}一次更新的属性过多")
            for attribute, state_value in operation["set"].items():
                if not isinstance(attribute, str) or not attribute.strip():
                    raise ValueError(f"{entity}含空属性名")
                _sentence(state_value)
            if category == "relationships":
                key_participants = _relationship_participants(entity)
                if len(key_participants) < 2:
                    raise ValueError(f"关系键 {entity} 必须以|连接至少两个参与者姓名")
                # participants 是可选字段；首次出现但省略时由 apply_patch 从关系键补全。
                if "participants" in operation:
                    participants = _string_list(operation["participants"], f"{entity}.participants")
                    if len(participants) < 2:
                        raise ValueError(f"{entity}.participants至少需要两个参与者")
    for field in ("delete_characters", "delete_relationships", "delete_assets"):
        _string_list(patch.get(field), f"patch.{field}")
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary必须是非空文字")
    return value


def apply_patch(previous: Dict[str, Any], extraction: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    validate_extraction(extraction)
    state = copy.deepcopy(previous or empty_state())
    for category in empty_state():
        state.setdefault(category, {})
    patch = extraction["patch"]
    changed: List[Dict[str, str]] = []
    deleted: List[Dict[str, str]] = []
    delete_fields = {
        "characters": "delete_characters",
        "relationships": "delete_relationships",
        "assets": "delete_assets",
    }
    for category, delete_field in delete_fields.items():
        for entity in patch[delete_field]:
            if category == "relationships":
                entity = _relationship_key(entity)
            if state[category].pop(entity, None) is not None:
                deleted.append({"category": category, "entity": entity, "attribute": "*"})
        for entity, operation in patch[category].items():
            if category == "relationships":
                entity = _relationship_key(entity)
            current = state[category].setdefault(entity, {})
            if category == "relationships":
                if "participants" not in current:
                    supplied = operation.get("participants")
                    current["participants"] = list(supplied) if supplied else _relationship_participants(entity)
                attrs = current.setdefault("states", {})
            elif category == "assets":
                current["kind"] = operation.get("kind", current.get("kind", "other"))
                attrs = current.setdefault("states", {})
            else:
                attrs = current
            for attribute in operation["delete"]:
                if attrs.pop(attribute, None) is not None:
                    deleted.append({"category": category, "entity": entity, "attribute": attribute})
            for attribute, state_value in operation["set"].items():
                attrs[attribute.strip()] = _sentence(state_value)
                changed.append({"category": category, "entity": entity, "attribute": attribute.strip()})
            if len(attrs) > MAX_ATTRS[category]:
                protected = {attribute.strip() for attribute in operation["set"]}
                removable = [attribute for attribute in attrs if attribute not in protected]
                overflow = len(attrs) - MAX_ATTRS[category]
                if len(removable) < overflow:
                    raise ValueError(f"{entity}更新后超过{MAX_ATTRS[category]}个状态属性")
                for attribute in removable[:overflow]:
                    attrs.pop(attribute)
                    deleted.append({"category": category, "entity": entity, "attribute": attribute})
    return state, {"changed": changed, "deleted": deleted}


def _tokens(text: str) -> List[str]:
    lowered = str(text or "").lower()
    latin = re.findall(r"[a-z0-9_]+", lowered)
    chinese_blocks = re.findall(r"[\u4e00-\u9fff]+", lowered)
    result = list(latin)
    for block in chinese_blocks:
        result.extend(block if len(block) == 1 else [block[i:i + 2] for i in range(len(block) - 1)])
    return result


def flatten_state(state: Dict[str, Any], metadata: Dict[str, int] | None = None) -> List[Dict[str, Any]]:
    metadata = metadata or {}
    records: List[Dict[str, Any]] = []
    for category in ("characters", "relationships", "assets"):
        for entity, raw in state.get(category, {}).items():
            if category == "characters":
                attrs, participants, kind = raw, [entity], "character"
            else:
                attrs = raw.get("states", {})
                participants = (
                    raw.get("participants") or _relationship_participants(entity)
                    if category == "relationships" else [entity]
                )
                kind = raw.get("kind", "relationship")
            for attribute, value in attrs.items():
                key = f"{category}\u001f{entity}\u001f{attribute}"
                records.append({
                    "category": category, "entity": entity, "attribute": attribute,
                    "value": value, "participants": participants, "kind": kind,
                    "last_changed_episode": int(metadata.get(key, -1)),
                })
    return records


def retrieve_state(state: Dict[str, Any], query: str, episode_id: int, metadata: Dict[str, int] | None = None,
                   budget: int = 6000, max_records: int = 20) -> Tuple[str, Dict[str, Any]]:
    records = flatten_state(state, metadata)
    query_tokens = _tokens(query)
    query_counts = Counter(query_tokens)
    document_tokens = [_tokens(f"{r['entity']} {r['attribute']} {r['value']}") for r in records]
    document_frequency = Counter(token for tokens in document_tokens for token in set(tokens))
    average_length = sum(map(len, document_tokens)) / max(len(document_tokens), 1)
    scored = []
    for record, tokens in zip(records, document_tokens):
        counts = Counter(tokens)
        bm25 = 0.0
        for token, qfreq in query_counts.items():
            if not counts[token]:
                continue
            idf = math.log(1 + (len(records) - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
            tf = counts[token] * 2.2 / (counts[token] + 1.2 * (0.25 + 0.75 * len(tokens) / max(average_length, 1)))
            bm25 += idf * tf * min(qfreq, 2)
        mentioned = record["entity"] in query
        participants = [name for name in record["participants"] if name]
        participant_hits = sum(name in query for name in participants)
        entity_boost = 2.4 if mentioned else (2.0 if len(participants) >= 2 and participant_hits == len(participants) else 0.75 * participant_hits)
        age = max(0, episode_id - record["last_changed_episode"])
        recency = 0.45 * math.exp(-age / 5) if record["last_changed_episode"] >= 0 else 0.0
        record = dict(record)
        record["score"] = round(bm25 + entity_boost + recency, 5)
        record["matched"] = bool(bm25 > 0 or entity_boost > 0)
        record["reasons"] = {"bm25": round(bm25, 5), "entity_boost": entity_boost, "recency": round(recency, 5)}
        scored.append(record)
    scored.sort(key=lambda item: (item["score"], item["last_changed_episode"]), reverse=True)
    selected, used = [], 0
    for record in scored:
        if len(selected) >= max_records:
            break
        # 当前大纲没有任何词面、实体或关系参与者交集时，不把无关状态塞进上下文。
        if not record["matched"]:
            continue
        line_size = len(record["entity"] + record["attribute"] + record["value"]) + 20
        if selected and used + line_size > budget:
            continue
        if not selected and line_size > budget:
            continue
        selected.append(record)
        used += line_size
    grouped: Dict[str, Dict[str, List[Dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for record in selected:
        grouped[record["category"]][record["entity"]].append({record["attribute"]: record["value"]})
    labels = {"characters": "人物状态", "relationships": "人物关系状态", "assets": "资产、物品与环境状态"}
    lines = ["以下是根据本集大纲检索到的当前状态快照；这些是截至本集开始前仍然成立的事实："]
    for category in ("characters", "relationships", "assets"):
        lines.append(f"### {labels[category]}")
        if not grouped[category]:
            lines.append("- 暂无高度相关状态")
        for entity, attrs in grouped[category].items():
            lines.append(f"- {entity}")
            for pair in attrs:
                attribute, value = next(iter(pair.items()))
                lines.append(f"  - {attribute}：{value}")
    return "\n".join(lines), {"query": query, "budget": budget, "max_records": max_records,
                                "selected_chars": used, "selected": selected,
                                "total_records": len(records), "selected_records": len(selected)}


class StructuredStateMemory:
    def __init__(self, story_id: str):
        output_root = os.path.abspath(os.environ.get("DRAMA_OUTPUT_DIR") or os.path.join(os.getcwd(), "output"))
        root = os.path.abspath(os.environ.get("DRAMA_STATE_MEMORY_DIR") or os.path.join(output_root, "structured_state"))
        self.story_id = story_id
        self.story_dir = os.path.join(root, _safe_name(story_id))
        self.path = os.path.join(self.story_dir, "state_memory.json")
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as stream:
                loaded = json.load(stream)
            if loaded.get("story_id") == self.story_id:
                return loaded
        return {"schema_version": 1, "story_id": self.story_id, "state": empty_state(), "metadata": {},
                "history": [], "episode_summaries": [], "last_updated_episode": -1}

    def retrieve(self, query: str, episode_id: int) -> Tuple[str, Dict[str, Any]]:
        budget = int(os.environ.get("DRAMA_STATE_MEMORY_BUDGET", "6000"))
        max_records = int(os.environ.get("DRAMA_STATE_MEMORY_LIMIT", "20"))
        context, audit = retrieve_state(
            self.data["state"], query, episode_id, self.data.get("metadata"), budget, max_records
        )
        audit.update({
            "schema_version": 1,
            "story_id": self.story_id,
            "episode_id": episode_id,
            "last_updated_episode": self.data.get("last_updated_episode", -1),
            "state_sha256": state_digest(self.data["state"]),
        })
        _atomic_dump(os.path.join(self.story_dir, "retrieval", f"episode_{episode_id + 1:03d}.json"), audit)
        return context, audit

    def previous_state_json(self) -> str:
        return json.dumps(self.data["state"], ensure_ascii=False, indent=2)

    def recent_summaries(self, episode_id: int, limit: int = 5) -> str:
        rows = [row for row in self.data.get("episode_summaries", []) if row["episode_id"] < episode_id][-limit:]
        return "\n".join(f"- 第{row['episode_id'] + 1}集：{row['summary']}" for row in rows) or "暂无前情摘要"

    def commit(self, episode_id: int, extraction: Dict[str, Any]) -> Dict[str, Any]:
        if episode_id > self.data.get("last_updated_episode", -1) + 1:
            raise ValueError("状态记忆不能跳集更新")
        if episode_id <= self.data.get("last_updated_episode", -1):
            history = [row for row in self.data["history"] if row["episode_id"] < episode_id]
            self.data["state"] = copy.deepcopy(history[-1]["state"] if history else empty_state())
            self.data["history"] = history
            self.data["episode_summaries"] = [row for row in self.data["episode_summaries"] if row["episode_id"] < episode_id]
            self.data["metadata"] = {k: v for k, v in self.data.get("metadata", {}).items() if v < episode_id}
        next_state, changes = apply_patch(self.data["state"], extraction)
        for item in changes["changed"]:
            key = f"{item['category']}\u001f{item['entity']}\u001f{item['attribute']}"
            self.data["metadata"][key] = episode_id
        for item in changes["deleted"]:
            prefix = f"{item['category']}\u001f{item['entity']}\u001f"
            if item["attribute"] == "*":
                self.data["metadata"] = {k: v for k, v in self.data["metadata"].items() if not k.startswith(prefix)}
            else:
                self.data["metadata"].pop(prefix + item["attribute"], None)
        self.data["state"] = next_state
        self.data["history"].append({"episode_id": episode_id, "state": copy.deepcopy(next_state), "changes": changes})
        summary = re.sub(r"\s+", " ", extraction["summary"]).strip()[:500]
        self.data["episode_summaries"].append({"episode_id": episode_id, "summary": summary})
        self.data["last_updated_episode"] = episode_id
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _atomic_dump(self.path, self.data)
        _atomic_dump(os.path.join(self.story_dir, "updates", f"episode_{episode_id + 1:03d}.json"),
                     {"episode_id": episode_id, "raw": extraction, "applied": changes, "state": next_state})
        return {"state": next_state, "summary": summary, **changes}
