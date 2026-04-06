"""Centralised LLM tool-schema definitions for Consolidator mini-loops.

All schema functions here follow the OpenAI/Anthropic function-calling format:
  {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

Consolidator imports these instead of defining its own ad-hoc dicts, giving a
single place to audit and modify every internal tool contract.
"""

from __future__ import annotations

from typing import Any


def write_segment_schema() -> dict[str, Any]:
    """Schema for the 30-minute activity-segment write tool."""
    return {
        "type": "function",
        "function": {
            "name": "write_segment",
            "description": "写入 30 分钟活动摘要和通知决策",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Markdown 格式的活动摘要",
                    },
                    "should_notify": {
                        "type": "boolean",
                        "description": "是否向用户发送通知",
                    },
                    "notify_message": {
                        "type": "string",
                        "description": "通知内容（自然语言）",
                    },
                    "active_projects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "当前活跃的项目名列表",
                    },
                    "learning_topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "当前学习/研究的主题列表",
                    },
                    "metadata_updates": {
                        "type": "array",
                        "description": "需存储为用户元信息的稳定事实",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["key", "value"],
                        },
                    },
                },
                "required": ["summary", "should_notify"],
            },
        },
    }


def write_daily_schema() -> dict[str, Any]:
    """Schema for the daily-summary merge tool."""
    return {
        "type": "function",
        "function": {
            "name": "write_daily_summary",
            "description": "写入日级摘要并标记可回收的片段文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Markdown 格式的日摘要",
                    },
                    "recyclable_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可安全删除的片段文件名列表",
                    },
                },
                "required": ["summary"],
            },
        },
    }


def work_project_patch_schema() -> dict[str, Any]:
    """Schema for section-level edit of memory/work_projects.md."""
    return {
        "type": "function",
        "function": {
            "name": "work_project_patch",
            "description": (
                "对 work_projects.md 中单个「## 项目名」区块定点增删改，不覆盖整文件。"
                "先 memory_read topic=work_projects 看清现有 ## 标题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_heading": {
                        "type": "string",
                        "description": "与文件中 ## 标题一致；新项目用新标题 + add",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["add", "update", "remove"],
                        "description": "add=新项目块 / update=替换某块正文 / remove=删除该块",
                    },
                    "body": {
                        "type": "string",
                        "description": "该块正文（不含 ##）；remove 可空",
                    },
                },
                "required": ["project_heading", "action"],
            },
        },
    }


def memory_write_schema() -> dict[str, Any]:
    """Schema for the long-term memory write tool (L3)."""
    return {
        "type": "function",
        "function": {
            "name": "memory_write",
            "description": "写入或追加长期记忆（L3）",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": (
                            "L3 主题：portrait/preferences/routines/skills_interests/social/"
                            "health/emotional_patterns/iot_preferences。"
                            "勿用本工具写 work_projects（用 work_project_patch）；"
                            "勿写 segment_activity（机器追加）。"
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown 格式的内容",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["append", "replace"],
                        "description": "append=追加 / replace=整体覆写",
                    },
                },
                "required": ["topic", "content"],
            },
        },
    }


def identity_set_schema() -> dict[str, Any]:
    """Schema for the structured identity (L0) write tool."""
    return {
        "type": "function",
        "function": {
            "name": "identity_set",
            "description": "写入用户稳定元信息（L0）",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "snake_case 格式的键名",
                    },
                    "value": {
                        "type": "string",
                        "description": "原始值，不脱敏",
                    },
                },
                "required": ["key", "value"],
            },
        },
    }


def write_weekly_schema() -> dict[str, Any]:
    """Schema for the weekly-review summary write tool."""
    return {
        "type": "function",
        "function": {
            "name": "write_weekly_summary",
            "description": "写入本周的周摘要文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Markdown 格式的周摘要",
                    },
                },
                "required": ["summary"],
            },
        },
    }
