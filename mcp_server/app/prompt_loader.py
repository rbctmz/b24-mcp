from __future__ import annotations

from functools import lru_cache
from importlib import resources
import json
from typing import Any, Dict

PROMPTS_PACKAGE = "mcp_server.app.docs"
PROMPTS_TEMPLATE = "prompts_{locale}.md"
_MARKER_START = "<!-- prompts:data"
_MARKER_END = "-->"


class PromptDataError(RuntimeError):
    """Raised when подсказки не удалось загрузить или распарсить."""


def _read_prompts_file(locale: str) -> str:
    filename = PROMPTS_TEMPLATE.format(locale=locale)
    try:
        prompts_pkg = resources.files(PROMPTS_PACKAGE)
    except (AttributeError, ModuleNotFoundError) as exc:  # pragma: no cover - defensive
        raise PromptDataError(f"Не удалось найти пакет подсказок {PROMPTS_PACKAGE}") from exc
    try:
        with (prompts_pkg / filename).open("r", encoding="utf-8") as md_file:
            return md_file.read()
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise PromptDataError(f"Файл подсказок для локали '{locale}' не найден") from exc


@lru_cache(maxsize=None)
def load_prompt_bundle(locale: str = "ru") -> Dict[str, Any]:
    markdown = _read_prompts_file(locale)
    marker_pos = markdown.find(_MARKER_START)
    if marker_pos == -1:
        raise PromptDataError("Не найден блок данных подсказок в Markdown")
    json_start = markdown.find("{", marker_pos)
    if json_start == -1:
        raise PromptDataError("Отсутствует JSON после маркера подсказок")
    marker_end = markdown.find(_MARKER_END, json_start)
    if marker_end == -1:
        raise PromptDataError("Блок подсказок не закрыт `-->`")
    json_blob = markdown[json_start:marker_end].strip()
    try:
        data = json.loads(json_blob)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise PromptDataError(f"Ошибка чтения JSON из подсказок: {exc}") from exc
    return data


def get_initialize_prompts(locale: str = "ru") -> Dict[str, Any]:
    bundle = load_prompt_bundle(locale)
    return bundle.get("initialize", {})


def get_tool_docs(locale: str = "ru") -> Dict[str, Any]:
    bundle = load_prompt_bundle(locale)
    return bundle.get("tools", {})


def get_tool_warning_rules(locale: str = "ru") -> Dict[str, Any]:
    bundle = load_prompt_bundle(locale)
    return bundle.get("toolWarnings", {})


def get_resource_docs(locale: str = "ru") -> Dict[str, Any]:
    bundle = load_prompt_bundle(locale)
    return bundle.get("resources", {})
