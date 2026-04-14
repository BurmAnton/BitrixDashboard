"""
Единый источник документации гида API: Markdown в api/docs/guide/<key>.md.
Скачивание и HTML-страница используют одни и те же файлы.
"""
from __future__ import annotations

import re
from pathlib import Path

GUIDE_DOCS_DIR = Path(__file__).resolve().parent / "docs" / "guide"


def get_guide_doc_path(guide_key: str) -> Path:
    """Путь к .md для ключа шаблона гида (organization, contact, …)."""
    return GUIDE_DOCS_DIR / f"{guide_key}.md"


def guide_markdown_to_html(md_text: str) -> str:
    import markdown

    html = markdown.markdown(
        md_text,
        extensions=[
            "markdown.extensions.tables",
            "markdown.extensions.fenced_code",
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
        ],
        output_format="html5",
    )
    html = re.sub(
        r"<table>",
        '<table class="table table-bordered table-striped table-sm">',
        html,
    )
    return html


def render_guide_html_for_key(guide_key: str) -> str:
    """Читает Markdown и возвращает безопасный для |safe HTML (контент из репозитория)."""
    path = get_guide_doc_path(guide_key)
    if not path.is_file():
        return (
            '<p class="text-muted">Документация не найдена '
            f"(ожидался файл <code>{path.name}</code>).</p>"
        )
    text = path.read_text(encoding="utf-8")
    return guide_markdown_to_html(text)
