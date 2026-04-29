from __future__ import annotations

from typing import Any

from ._query import with_query
from ._types import (
    AskContentBlock,
    AskRole,
    KbMessage,
    KbPage,
    KbPageKind,
    KbPageList,
    KbSession,
    KbSessionList,
)
from .client import HttpClient


class KbResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    # ── pages ──────────────────────────────────────────────────────────────

    def create_page(
        self,
        *,
        path: str,
        title: str,
        body: str,
        summary: str | None = None,
        kind: KbPageKind | None = None,
    ) -> KbPage:
        payload: dict[str, Any] = {"path": path, "title": title, "body": body}
        if summary is not None:
            payload["summary"] = summary
        if kind is not None:
            payload["kind"] = kind
        res = self._http.post("/v1/kb/pages", json=payload)
        return res["page"]

    def list_pages(
        self,
        *,
        kind: KbPageKind | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> KbPageList:
        return self._http.get(
            with_query("/v1/kb/pages", kind=kind, search=search, cursor=cursor, limit=limit)
        )

    def get_page(self, id: str) -> KbPage:
        res = self._http.get(f"/v1/kb/pages/{id}")
        return res["page"]

    def update_page(
        self,
        id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        summary: str | None = None,
        kind: KbPageKind | None = None,
    ) -> KbPage:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if summary is not None:
            payload["summary"] = summary
        if kind is not None:
            payload["kind"] = kind
        res = self._http.patch(f"/v1/kb/pages/{id}", json=payload)
        return res["page"]

    def delete_page(self, id: str) -> None:
        self._http.delete(f"/v1/kb/pages/{id}")

    # ── sessions ───────────────────────────────────────────────────────────

    def create_session(
        self,
        *,
        title: str | None = None,
        model: str | None = None,
    ) -> KbSession:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if model is not None:
            payload["model"] = model
        res = self._http.post("/v1/kb/sessions", json=payload)
        return res["session"]

    def list_sessions(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> KbSessionList:
        return self._http.get(with_query("/v1/kb/sessions", cursor=cursor, limit=limit))

    def get_session(self, id: str) -> KbSession:
        res = self._http.get(f"/v1/kb/sessions/{id}")
        return res["session"]

    def delete_session(self, id: str) -> None:
        self._http.delete(f"/v1/kb/sessions/{id}")

    def list_messages(self, id: str) -> list[KbMessage]:
        res = self._http.get(f"/v1/kb/sessions/{id}/messages")
        return res["messages"]

    def append_message(
        self,
        id: str,
        *,
        content: str | list[AskContentBlock],
        role: AskRole | None = None,
    ) -> KbMessage:
        payload: dict[str, Any] = {"content": content}
        if role is not None:
            payload["role"] = role
        res = self._http.post(f"/v1/kb/sessions/{id}/messages", json=payload)
        return res["message"]
