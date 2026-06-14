import html


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)
