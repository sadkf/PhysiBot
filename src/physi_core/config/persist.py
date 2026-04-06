"""Read/write config.yaml for the Monitor 设置页与首次启动向导."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from physi_core.config.settings import Settings, load_settings

_PLACEHOLDER_API_KEYS = frozenset(
    {
        "",
        "your-api-key-here",
        "changeme",
        "sk-your-api-key-here",
    }
)


def needs_initial_setup(config_path: Path) -> bool:
    """True when config 缺失或尚未填写有效 API Key。"""
    if not config_path.exists():
        return True
    s = load_settings(config_path)
    k = (s.llm.api_key or "").strip()
    if not k or k.lower() in {x.lower() for x in _PLACEHOLDER_API_KEYS}:
        return True
    return False


def load_raw_config(config_path: Path, example_path: Path) -> dict[str, Any]:
    """加载当前 YAML 为 dict；若无则自 example 拷贝逻辑由调用方处理。"""
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    if example_path.exists():
        with example_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """递归合并 patch 到 base（浅层键覆盖，嵌套 dict 递归）。"""
    out: dict[str, Any] = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def mask_config_for_ui(raw: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """返回可安全发给前端的副本（脱敏 api_key），以及是否已配置过非占位 Key。"""
    import copy

    cfg = copy.deepcopy(raw)
    llm = cfg.get("llm")
    has_key = False
    if isinstance(llm, dict):
        ak = (llm.get("api_key") or "").strip()
        has_key = bool(ak and ak.lower() not in {x.lower() for x in _PLACEHOLDER_API_KEYS})
        llm["api_key"] = ""
    return cfg, has_key


def apply_config_patch(
    current: dict[str, Any],
    patch: dict[str, Any],
    *,
    keep_llm_api_key: bool,
    previous_api_key: str,
) -> dict[str, Any]:
    """合并前端提交的 patch；若 keep_llm_api_key 且未填新 key，则保留 previous_api_key。"""
    merged = deep_merge(current, patch)
    llm = merged.get("llm")
    if isinstance(llm, dict):
        # 内定 MiniMax：即便前端不传 provider/model，也补齐默认值
        llm.setdefault("provider", "minimax")
        llm.setdefault("model", "MiniMax-M2.7")
        new_key = (llm.get("api_key") or "").strip()
        if keep_llm_api_key and not new_key:
            llm["api_key"] = previous_api_key
        elif (
            new_key
            and new_key.lower() in {x.lower() for x in _PLACEHOLDER_API_KEYS}
            and previous_api_key
        ):
            llm["api_key"] = previous_api_key
    return merged


def validate_config_dict(path: Path) -> tuple[bool, str]:
    """写入后校验能否加载为 Settings。"""
    try:
        load_settings(path)
    except Exception as e:
        return False, str(e)
    s = load_settings(path)
    # ── 必填：LLM（内定 MiniMax，仅要求 API Key）──────────────────────────
    if not (s.llm.api_key or "").strip():
        return False, "请填写 LLM API Key"
    if (s.llm.api_key or "").strip().lower() in {x.lower() for x in _PLACEHOLDER_API_KEYS}:
        return False, "请填写真实的 LLM API Key（不要使用占位符）"

    # ── 必填：感知（Screenpipe / ActivityWatch）──────────────────────────
    if not getattr(s.perception.screenpipe, "enabled", False):
        return False, "请启用 Screenpipe（感知是必填能力）"
    if not (getattr(s.perception.screenpipe, "api_url", "") or "").strip():
        return False, "请填写 Screenpipe API URL"
    if not getattr(s.perception.activitywatch, "enabled", False):
        return False, "请启用 ActivityWatch（感知是必填能力）"
    if not (getattr(s.perception.activitywatch, "api_url", "") or "").strip():
        return False, "请填写 ActivityWatch API URL"

    # ── 必填：QQ（NapCat）───────────────────────────────────────────────
    if not (s.qq.ws_url or "").strip():
        return False, "请填写 QQ ws_url（NapCat WebSocket 地址）"
    owner_raw = getattr(s.qq, "owner_qq", None)
    if owner_raw is None:
        return False, "请填写 owner_qq（NapCat 登录 QQ）"
    # Settings.QQConfig.owner_qq 的类型是 list[str]（兼容旧格式会归一化）
    owner_str = ""
    if isinstance(owner_raw, list):
        owner_str = (str(owner_raw[0]).strip() if owner_raw else "")
    else:
        owner_str = str(owner_raw).strip()
    if not owner_str or not owner_str.isdigit():
        return False, "owner_qq 必须是纯数字 QQ 号"
    talk = getattr(s.qq, "talk_qq", None)
    talk_list = talk if isinstance(talk, list) else []
    talk_list = [str(x).strip() for x in talk_list if str(x).strip()]
    if not talk_list:
        return False, "请填写 talk_qq（允许私聊的 QQ 列表，至少 1 个）"
    return True, ""


def parse_talk_qq_list(text: str) -> list[str]:
    """逗号/空格/换行分隔的 QQ 列表。"""
    parts: list[str] = []
    for chunk in text.replace("\n", ",").split(","):
        for p in chunk.split():
            p = p.strip()
            if p:
                parts.append(p)
    return parts
