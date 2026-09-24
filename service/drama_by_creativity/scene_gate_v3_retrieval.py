"""Scene-aware retrieval helpers for the next conservative scene gate."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .structured_state_memory import flatten_state, retrieve_state


TERMINAL_PATTERN = re.compile(
    r"确认死亡|已经死亡|已死亡|死亡状态|身亡|牺牲|毙命|无生命迹象|"
    r"永久失去|彻底终止|彻底切断|彻底销毁|已经销毁|已销毁|"
    r"彻底损毁|已损毁|焚毁|摧毁|粉碎|报废|失效|永久遗留|"
    r"被捕|被羁押|被拘留|被监禁|被收押|终身监禁|"
    r"耗尽|用尽|归零|仅剩0|无剩余|不再.{0,12}持有|永久移交|已遗失|已丢失"
)
NEGATED_TERMINAL_PATTERN = re.compile(
    r"(?:未|没有|并未|尚未|并没有).{0,6}"
    r"(?:死亡|身亡|牺牲|销毁|损毁|焚毁|摧毁|被捕|羁押|拘留|监禁|耗尽|用尽|遗失|丢失)"
)
AMBIGUOUS_PATTERN = re.compile(
    r"可能|或许|疑似|推测|似乎|据称|大概|暂记|尚不确定|无法确认|未明确"
)
QUANTITY_PATTERN = re.compile(
    r"(?:剩余|仅剩|只剩)\s*[零〇一二两三四五六七八九十百\d]+\s*"
    r"(?:个|枚|发|张|份|件|瓶|颗|把|支|套|单位)?|"
    r"耗尽|用尽|无剩余|归零|"
    r"数量(?:为|：|:)?\s*[零〇一二两三四五六七八九十百\d]+"
)
ASSET_QUALIFIER_PATTERN = re.compile(
    r"^(?:临时|备用|伪造|仿制|复制|原始|旧版|新版|损坏的|烧毁的|被盗的|遗失的|真实的|虚假的)+"
)


def _tokens(text: str) -> List[str]:
    lowered = str(text or "").lower()
    result = re.findall(r"[a-z0-9_]+", lowered)
    for block in re.findall(r"[\u4e00-\u9fff]+", lowered):
        result.extend(block if len(block) == 1 else [block[index:index + 2] for index in range(len(block) - 1)])
    return result


def scene_text(scenes: Iterable[Dict[str, Any]]) -> str:
    return json.dumps(list(scenes), ensure_ascii=False, sort_keys=True)


def asset_core(name: str) -> str:
    """Normalize generic qualifiers without story- or object-specific vocabularies."""
    text = re.sub(r"[\s\-_/·•]+", "", str(name or ""))
    normalized = ASSET_QUALIFIER_PATTERN.sub("", text)
    return normalized if len(normalized) >= 2 else text


def _asset_query_terms(name: str) -> List[str]:
    text = re.sub(r"[\s\-_/·•]+", "", str(name or ""))
    core = asset_core(text)
    terms = {term for term in (text, core) if len(term) >= 2}
    if len(core) > 2:
        terms.add(core[-2:])
    return sorted(terms, key=lambda term: (-len(term), term))


def _asset_alias_groups(records: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Group aliases by normalized names derived only from the current story state."""
    groups = defaultdict(set)
    for record in records:
        if record.get("category") != "assets":
            continue
        entity = str(record.get("entity", "")).strip()
        core = asset_core(entity)
        if entity and core:
            groups[core].add(entity)
    return {core: sorted(names) for core, names in groups.items() if len(names) > 1}


def risk_labels(record: Dict[str, Any]) -> List[str]:
    labels = []
    value = str(record.get("value", ""))
    ambiguous = bool(AMBIGUOUS_PATTERN.search(value))
    if ambiguous:
        labels.append("ambiguous")
    if TERMINAL_PATTERN.search(value) and not NEGATED_TERMINAL_PATTERN.search(value) and not ambiguous:
        labels.append("terminal")
    return labels


def _canonical_sentences(assets: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for source in ("world_view", "role_info", "story_outline"):
        value = assets.get(source, "")
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        narrative_heading = re.search(
            r"(?m)^#{2,}\s*(?:故事框架|开端|第一幕|第\s*\d+\s*[集幕章])",
            value,
        )
        index = 0
        for match in re.finditer(r"[^。！？；\n]+[。！？；]?", value):
            quote = re.sub(r"\s+", " ", match.group()).strip()
            if not quote:
                continue
            index += 1
            rows.append({
                "category": "canon",
                "entity": source,
                "attribute": f"{source}_{index:04d}",
                "value": quote,
                "participants": [],
                "kind": "canonical_fact",
                "last_changed_episode": -1,
                "source": "generation_assets",
                "canonical": True,
                "static_canon": (
                    source in {"world_view", "role_info"}
                    or narrative_heading is None
                    or match.start() < narrative_heading.start()
                ),
            })
    return rows


def _rank_canonical(
    assets: Dict[str, Any],
    query: str,
    limit: int = 8,
    entities: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    records = _canonical_sentences(assets)
    query_tokens = Counter(_tokens(query))
    names = set(re.findall(r"[\u4e00-\u9fff·]{2,20}", query))
    entity_names = set()
    for name in entities or []:
        if not name:
            continue
        entity_names.add(name)
        for separator in ("·", "•"):
            if separator in name:
                entity_names.update(part for part in name.split(separator) if len(part) >= 2)
    scored = []
    for record in records:
        value = record["value"]
        counts = Counter(_tokens(value))
        overlap = sum(min(counts[token], count) for token, count in query_tokens.items())
        name_hits = sum(name in value for name in names)
        entity_hits = sum(name in value for name in entity_names)
        kinship = 50 if re.search(r"父亲|母亲|父子|母子|父女|母女|兄弟|姐妹|丈夫|妻子|女儿|儿子|哥哥|弟弟|姐姐|妹妹", value) else 0
        static_fact = 100 if record.get("static_canon") else 0
        score = overlap + 5 * name_hits + 20 * entity_hits + kinship + static_fact
        if score > 0:
            scored.append((score, len(value), record))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]["attribute"]))
    return [{**record, "score": score, "matched": True, "reasons": {"canonical": score}}
            for score, _, record in scored[:limit]]


def _scene_entities(scenes: Iterable[Dict[str, Any]]) -> set[str]:
    entities = set()
    for scene in scenes:
        for name in scene.get("出场人物", []):
            if isinstance(name, str) and name.strip():
                entities.add(name.strip())
    return entities


def _record_key(record: Dict[str, Any]) -> Tuple[str, str, str]:
    return record["category"], record["entity"], record["attribute"]


def _query_mentions_record(record: Dict[str, Any], query: str) -> bool:
    entity = str(record.get("entity", ""))
    value = str(record.get("value", ""))
    participants = record.get("participants", [])
    if entity and entity in query:
        return True
    if any(str(name) in query for name in participants):
        return True
    if record.get("category") != "assets":
        return False
    return any(term in query for term in _asset_query_terms(entity))


def _historical_terminal_records(
    history: Optional[List[Dict[str, Any]]],
    metadata: Dict[str, int],
    query: str,
) -> List[Dict[str, Any]]:
    if not history:
        return []
    candidates = []
    seen = set()
    query_tokens = Counter(_tokens(query))
    for snapshot in reversed(history):
        snapshot_episode = int(snapshot.get("episode_id", -1))
        for record in flatten_state(snapshot.get("state", {}), metadata):
            key = (*_record_key(record), record.get("value", ""))
            if key in seen or "terminal" not in risk_labels(record):
                continue
            if not _query_mentions_record(record, query):
                continue
            seen.add(key)
            record_tokens = Counter(_tokens(f"{record['entity']} {record['value']}"))
            overlap = sum(min(record_tokens[token], count) for token, count in query_tokens.items())
            alias_bonus = 0
            if record["category"] == "assets" and any(
                term in query for term in _asset_query_terms(record["entity"])
            ):
                alias_bonus = 20
            candidates.append({
                **record,
                "score": 1000 + alias_bonus + overlap,
                "matched": True,
                "risk_labels": risk_labels(record),
                "pinned_reason": "terminal_history",
                "source": "structured_state_terminal_history",
                "history_episode": snapshot_episode,
                "history_relevance": alias_bonus + overlap,
            })
    candidates.sort(key=lambda record: (
        -record.get("history_relevance", 0),
        -record.get("history_episode", -1),
        _record_key(record),
    ))
    per_attribute = Counter()
    selected = []
    for record in candidates:
        key = _record_key(record)
        if per_attribute[key] >= 3:
            continue
        selected.append(record)
        per_attribute[key] += 1
        if len(selected) >= 12:
            break
    return selected


def _limited_scene_entity_records(
    records: List[Dict[str, Any]],
    actors: set[str],
    query: str,
    per_entity: int = 3,
) -> List[Dict[str, Any]]:
    preferred_attributes = {
        "身份与立场": 0,
        "身体状态": 1,
        "位置与处境": 2,
        "持有物品": 3,
        "知情状态": 4,
        "心理与目标": 5,
    }
    grouped = defaultdict(list)
    for record in records:
        if record["entity"] not in actors or not _query_mentions_record(record, query):
            continue
        labels = risk_labels(record)
        if "terminal" in labels:
            continue
        grouped[record["entity"]].append(record)
    selected = []
    for entity in sorted(grouped):
        ranked = sorted(
            grouped[entity],
            key=lambda record: (
                preferred_attributes.get(record["attribute"], 99),
                -int(record.get("last_changed_episode", -1)),
                record["attribute"],
            ),
        )
        for record in ranked[:per_entity]:
            selected.append({
                **record,
                "score": math.inf,
                "matched": True,
                "risk_labels": risk_labels(record),
                "pinned_reason": "scene_entity_limited",
            })
    return selected


def _limited_scene_asset_records(
    records: List[Dict[str, Any]],
    query: str,
    per_entity: int = 3,
    max_entities: int = 6,
) -> List[Dict[str, Any]]:
    preferred_attributes = {
        "持有与控制": 0,
        "持有者": 0,
        "位置": 1,
        "完好程度": 2,
        "物理状态": 2,
        "数量": 3,
        "剩余数量": 3,
        "效力": 4,
        "开放/封锁状态": 5,
    }
    query_tokens = Counter(_tokens(query))
    asset_records = [record for record in records if record["category"] == "assets"]
    document_frequency = Counter()
    for record in asset_records:
        document_frequency.update(set(_tokens(f"{record['entity']} {record['value']}")))
    grouped = defaultdict(list)
    relevance = {}
    for record in asset_records:
        entity = record["entity"]
        direct_name = any(term in query for term in _asset_query_terms(entity))
        record_tokens = Counter(_tokens(f"{entity} {record['value']}"))
        overlap_tokens = set(record_tokens) & set(query_tokens)
        if not direct_name and not overlap_tokens:
            continue
        rarity = sum(1 / document_frequency[token] for token in overlap_tokens)
        quantity_bonus = 50 if overlap_tokens and QUANTITY_PATTERN.search(record["value"]) else 0
        score = (100 if direct_name else 0) + quantity_bonus + rarity
        grouped[entity].append(record)
        relevance[entity] = max(relevance.get(entity, 0), score)
    selected = []
    for entity in sorted(grouped, key=lambda name: (-relevance[name], name))[:max_entities]:
        ranked = sorted(
            grouped[entity],
            key=lambda record: (
                preferred_attributes.get(record["attribute"], 99),
                -int(record.get("last_changed_episode", -1)),
                record["attribute"],
            ),
        )
        for record in ranked[:per_entity]:
            selected.append({
                **record,
                "score": math.inf,
                "matched": True,
                "risk_labels": risk_labels(record),
                "pinned_reason": "scene_asset_limited",
            })
    return selected


def _limited_quantity_records(
    records: List[Dict[str, Any]],
    query: str,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    query_tokens = Counter(_tokens(query))
    candidates = []
    for record in records:
        if record["category"] != "assets" or not QUANTITY_PATTERN.search(record["value"]):
            continue
        record_tokens = Counter(_tokens(f"{record['entity']} {record['value']}"))
        overlap = sum(min(record_tokens[token], count) for token, count in query_tokens.items())
        if overlap <= 0:
            continue
        candidates.append((overlap, int(record.get("last_changed_episode", -1)), record))
    candidates.sort(key=lambda item: (-item[0], -item[1], _record_key(item[2])))
    return [{
        **record,
        "score": math.inf,
        "matched": True,
        "risk_labels": risk_labels(record),
        "pinned_reason": "scene_quantity_limited",
    } for _, _, record in candidates[:limit]]


def retrieve_for_scene_gate(
    state: Dict[str, Any],
    metadata: Dict[str, int],
    assets: Dict[str, Any],
    episode_outline: str,
    scenes: List[Dict[str, Any]],
    episode_id: int,
    budget: int = 10000,
    max_records: int = 40,
    history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any]]:
    query = f"{episode_outline}\n{scene_text(scenes)}"
    _, baseline = retrieve_state(state, query, episode_id, metadata, budget=budget, max_records=max_records)
    records = flatten_state(state, metadata)
    actors = _scene_entities(scenes)
    query_text = query
    alias_groups = _asset_alias_groups(records)

    critical = _historical_terminal_records(history, metadata, query_text)
    alias_pinned = []
    for record in records:
        labels = risk_labels(record)
        exact_entity = _query_mentions_record(record, query_text)
        alias_match = False
        if record["category"] == "assets":
            core = asset_core(record["entity"])
            alias_match = any(term in query_text for term in _asset_query_terms(record["entity"]))
        if exact_entity and "terminal" in labels:
            critical.append({**record, "score": math.inf, "matched": True,
                             "risk_labels": labels, "pinned_reason": "current_terminal"})
        elif alias_match and ("terminal" in labels or core in alias_groups):
            alias_pinned.append({**record, "score": math.inf, "matched": True,
                                 "risk_labels": labels, "pinned_reason": "asset_alias_or_terminal"})

    selected = []
    seen = set()
    canonical = _rank_canonical(assets, query, limit=min(8, max_records), entities=actors)
    quantity_records = _limited_quantity_records(records, query_text)
    scene_assets = _limited_scene_asset_records(records, query_text)
    scene_entities = _limited_scene_entity_records(records, actors, query_text)
    candidates = critical + quantity_records + canonical + alias_pinned + scene_assets + scene_entities + baseline["selected"]
    used = 0
    for record in candidates:
        key = _record_key(record)
        if key in seen:
            continue
        enriched = dict(record)
        enriched.setdefault("source", "structured_state_hybrid")
        enriched.setdefault("risk_labels", risk_labels(enriched))
        line_size = len(enriched["entity"] + enriched["attribute"] + enriched["value"]) + 20
        mandatory = enriched.get("pinned_reason") in {"terminal_history", "current_terminal"}
        if len(selected) >= max_records:
            continue
        if selected and used + line_size > budget and not mandatory:
            continue
        selected.append(enriched)
        seen.add(key)
        used += line_size

    grouped = defaultdict(lambda: defaultdict(list))
    for record in selected:
        grouped[record["category"]][record["entity"]].append({record["attribute"]: record["value"]})
    labels = {
        "canon": "世界观与人物设定硬事实",
        "characters": "人物状态",
        "relationships": "人物关系状态",
        "assets": "资产、物品与环境状态",
    }
    lines = ["以下是根据实际候选场次二次检索的状态与设定证据："]
    for category in ("canon", "characters", "relationships", "assets"):
        lines.append(f"### {labels[category]}")
        for entity, attrs in grouped[category].items():
            lines.append(f"- {entity}")
            for pair in attrs:
                attribute, value = next(iter(pair.items()))
                lines.append(f"  - {attribute}：{value}")
        if not grouped[category]:
            lines.append("- 暂无高度相关证据")

    alias_summary = {
        core: names
        for core, names in alias_groups.items()
        if any(term in query_text for name in names for term in _asset_query_terms(name))
    }
    audit = {
        **{key: value for key, value in baseline.items() if key != "selected"},
        "query": query,
        "retrieval_stage": "scene_gate_v3",
        "selected": selected,
        "selected_chars": used,
        "selected_records": len(selected),
        "pinned_records": sum(bool(record.get("pinned_reason")) for record in selected),
        "terminal_history_records": sum(record.get("pinned_reason") == "terminal_history" for record in selected),
        "quantity_records": sum(record.get("pinned_reason") == "scene_quantity_limited" for record in selected),
        "canonical_records": sum(record["category"] == "canon" for record in selected),
        "alias_groups": alias_summary,
    }
    return "\n".join(lines), audit
