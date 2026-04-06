"""定点修改 work_projects.md：按二级标题 `## 项目名` 增删改，不整文件替换。"""

from __future__ import annotations


def _parse_sections(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """拆成「## 之前的前言」与 [(标题, 正文行列表), ...]。"""
    lines = text.splitlines()
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## ") and not line.startswith("###"):
            title = line[3:].strip()
            i += 1
            body: list[str] = []
            while i < len(lines) and not (
                lines[i].startswith("## ") and not lines[i].startswith("###")
            ):
                body.append(lines[i])
                i += 1
            sections.append((title, body))
        else:
            preamble.append(line)
            i += 1
    return preamble, sections


def _join_sections(preamble: list[str], sections: list[tuple[str, list[str]]]) -> str:
    out: list[str] = []
    if preamble:
        out.extend(preamble)
    for title, body in sections:
        out.append(f"## {title}")
        out.extend(body)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def apply_work_project_patch(
    file_text: str,
    project_heading: str,
    action: str,
    body: str = "",
) -> str:
    """返回修改后的全文。非法时抛出 ValueError。"""
    h = project_heading.strip()
    if not h:
        raise ValueError("project_heading 不能为空")
    act = action.strip().lower()
    if act not in ("add", "update", "remove"):
        raise ValueError("action 须为 add / update / remove")

    preamble, sections = _parse_sections(file_text or "")
    key = h.lower()
    idx: int | None = None
    for i, (name, _) in enumerate(sections):
        if name.strip().lower() == key:
            idx = i
            break

    body_lines = [ln for ln in body.splitlines()]

    if act == "add":
        if idx is not None:
            raise ValueError(f"项目「{h}」已存在，请用 update")
        sections.append((h, body_lines))
    elif act == "update":
        if idx is None:
            raise ValueError(f"未找到项目「{h}」，请用 add")
        # 保留原文件中的标题写法（大小写等）
        old_title, _ = sections[idx]
        sections[idx] = (old_title, body_lines)
    else:  # remove
        if idx is None:
            raise ValueError(f"未找到项目「{h}」")
        sections.pop(idx)

    return _join_sections(preamble, sections)
