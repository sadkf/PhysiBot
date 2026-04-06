"""Jinja2 template loader for centralized prompt management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# The directory where .j2 files are stored
TEMPLATE_DIR = Path(__file__).resolve().parent

# Set up Jinja environment
_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, **kwargs: Any) -> str:
    """Render a jinja2 template with the given context variables.
    
    Example: render('segment_summarize.j2', data=raw_data, ...)
    """
    try:
        template = _env.get_template(template_name)
        return template.render(**kwargs).strip()
    except Exception:
        logger.exception("Failed to render prompt template: %s", template_name)
        return ""
