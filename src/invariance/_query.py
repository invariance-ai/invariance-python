from __future__ import annotations

from urllib.parse import urlencode


def with_query(path: str, **params: object) -> str:
    query = {key: str(value) for key, value in params.items() if value is not None}
    if not query:
        return path
    return f"{path}?{urlencode(query)}"
