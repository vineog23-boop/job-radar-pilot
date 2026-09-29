from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from scrapling.parser import Adaptor

from job_radar.fetching import page_html


_SAFE_CLASS = re.compile(r"^[A-Za-z_-][A-Za-z0-9_-]{0,127}$")


@dataclass(frozen=True, slots=True)
class CardSelection:
    cards: tuple[object, ...]
    method: str


def adaptive_db_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "JobRadar" / "adaptive" / "adaptive.db"


def _element(node: object) -> Any:
    return getattr(node, "_root", node)


def _classes(element: Any) -> tuple[str, ...]:
    value = str(getattr(element, "attrib", {}).get("class", ""))
    return tuple(sorted(token for token in value.split() if _SAFE_CLASS.fullmatch(token)))


def _safe_attributes(element: Any) -> dict[str, str]:
    classes = _classes(element)
    attributes: dict[str, str] = {}
    if classes:
        attributes["class"] = " ".join(classes)
    role = str(getattr(element, "attrib", {}).get("role", "")).strip()
    if _SAFE_CLASS.fullmatch(role):
        attributes["role"] = role
    return attributes


def _tag_path(element: Any) -> tuple[str, ...]:
    tags: list[str] = []
    current = element
    while current is not None:
        tag = getattr(current, "tag", None)
        if isinstance(tag, str):
            tags.append(tag)
        current = current.getparent()
    return tuple(reversed(tags))


def _fingerprint(node: object) -> dict[str, object]:
    element = _element(node)
    parent = element.getparent()
    siblings = (
        tuple(
            str(child.tag)
            for child in parent.iterchildren()
            if child is not element and isinstance(child.tag, str)
        )
        if parent is not None
        else ()
    )
    children = tuple(
        str(child.tag) for child in element.iterchildren() if isinstance(child.tag, str)
    )
    structural: dict[str, object] = {
        "tag": str(element.tag),
        "attributes": _safe_attributes(element),
        "path": _tag_path(element),
        "siblings": siblings,
        "children": children,
    }
    if parent is not None:
        structural["parent_name"] = str(parent.tag)
        structural["parent_attributes"] = _safe_attributes(parent)

    scope: list[dict[str, object]] = []
    ancestor = parent
    while ancestor is not None and len(scope) < 4:
        classes = _classes(ancestor)
        if classes:
            scope.append({"tag": str(ancestor.tag), "classes": classes})
        ancestor = ancestor.getparent()
    return {"element": structural, "scope": scope}


def _origin(page: object) -> str:
    parsed = urlsplit(str(getattr(page, "url", "")))
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), "", "", ""))


def _relocation_data(fingerprint: dict[str, object]) -> dict[str, object]:
    stored = dict(fingerprint["element"])  # type: ignore[arg-type]
    return {
        "tag": stored["tag"],
        "attributes": stored.get("attributes", {}),
        "text": None,
        "path": stored.get("path", ()),
        "parent_name": stored.get("parent_name"),
        "parent_attribs": stored.get("parent_attributes", {}),
        "parent_text": None,
        "siblings": stored.get("siblings", ()),
        "children": stored.get("children", ()),
    }


def _load_fingerprint(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, str):
        return None
    try:
        fingerprint = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(fingerprint, dict):
        return None
    element = fingerprint.get("element")
    if not isinstance(element, dict) or not isinstance(element.get("tag"), str):
        return None
    scope = fingerprint.get("scope", [])
    if not isinstance(scope, list):
        return None
    return fingerprint


def _matches_scope(node: object, fingerprint: dict[str, object]) -> bool:
    expected = fingerprint.get("scope", [])
    if not isinstance(expected, list) or not expected:
        return True
    expected_anchors = {
        (str(item.get("tag", "")), class_name)
        for item in expected
        if isinstance(item, dict)
        for class_name in item.get("classes", ())
    }
    current = _element(node).getparent()
    for _ in range(4):
        if current is None:
            break
        tag = str(getattr(current, "tag", ""))
        if any((tag, class_name) in expected_anchors for class_name in _classes(current)):
            return True
        current = current.getparent()
    return False


def _structural_identity(node: object) -> tuple[tuple[str, int], ...]:
    element = _element(node)
    path: list[tuple[str, int]] = []
    current = element
    while current is not None:
        tag = str(getattr(current, "tag", ""))
        index = 1
        sibling = current.getprevious()
        while sibling is not None:
            if str(getattr(sibling, "tag", "")) == tag:
                index += 1
            sibling = sibling.getprevious()
        path.append((tag, index))
        current = current.getparent()
    return tuple(reversed(path))


def _deduplicate_nodes(nodes: Iterable[object]) -> tuple[object, ...]:
    unique: list[object] = []
    seen: set[tuple[tuple[str, int], ...]] = set()
    for node in nodes:
        identity = _structural_identity(node)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(node)
    return tuple(unique)


class AdaptiveCardLocator:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or adaptive_db_path()
        self._lock = RLock()
        self._remembered: set[tuple[str, str, str]] = set()

    @staticmethod
    def _setup(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS adaptive_fingerprints (
                origin TEXT NOT NULL,
                source_code TEXT NOT NULL,
                selector TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                PRIMARY KEY (origin, source_code, selector)
            )
            """
        )

    def remember(
        self,
        page: object,
        source_code: str,
        selector: str,
        *,
        card: object | None = None,
    ) -> None:
        if card is None:
            cards = tuple(page.css(selector))  # type: ignore[attr-defined]
            if not cards:
                return
            card = cards[0]
        key = (_origin(page), source_code, selector)
        with self._lock:
            if key in self._remembered:
                return
            payload = json.dumps(
                _fingerprint(card),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(self.db_path)) as connection:
                    self._setup(connection)
                    connection.execute(
                        """
                        INSERT INTO adaptive_fingerprints
                            (origin, source_code, selector, fingerprint)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(origin, source_code, selector)
                        DO UPDATE SET fingerprint=excluded.fingerprint
                        """,
                        (*key, payload),
                    )
                    connection.commit()
            except (sqlite3.DatabaseError, OSError):
                return
            self._remembered.add(key)

    def relocate(
        self,
        page: object,
        source_code: str,
        selector: str,
    ) -> tuple[object, ...]:
        try:
            if not self.db_path.is_file():
                return ()
        except OSError:
            return ()
        key = (_origin(page), source_code, selector)
        with self._lock:
            try:
                with closing(sqlite3.connect(self.db_path)) as connection:
                    self._setup(connection)
                    row = connection.execute(
                        """
                        SELECT fingerprint FROM adaptive_fingerprints
                        WHERE origin = ? AND source_code = ? AND selector = ?
                        """,
                        key,
                    ).fetchone()
            except (sqlite3.DatabaseError, OSError):
                return ()
        if row is None:
            return ()
        fingerprint = _load_fingerprint(row[0])
        if fingerprint is None:
            return ()
        adaptive_page = Adaptor(
            page_html(page),
            url=str(getattr(page, "url", "")),
        )
        try:
            relocated = adaptive_page.relocate(
                _relocation_data(fingerprint),
                percentage=40,
                selector_type=True,
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            return ()
        return tuple(card for card in relocated if _matches_scope(card, fingerprint))


def select_cards(
    page: object,
    *,
    source_code: str,
    selector: str,
    locator: AdaptiveCardLocator,
) -> CardSelection:
    configured = _deduplicate_nodes(page.css(selector))  # type: ignore[attr-defined]
    if configured:
        return CardSelection(configured, "CONFIGURED")
    relocated = _deduplicate_nodes(locator.relocate(page, source_code, selector))
    if relocated:
        return CardSelection(relocated, "ADAPTIVE")
    return CardSelection((), "NONE")
