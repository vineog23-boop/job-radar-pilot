from __future__ import annotations

from dataclasses import dataclass
from job_radar.adaptive import (
    _classes,
    _deduplicate_nodes,
    _structural_identity,
    structurally_similar_nodes,
)


@dataclass(frozen=True, slots=True)
class SelectorSuggestion:
    card: str
    title: str
    url: str
    cards_found: int
    title_matches: int
    url_matches: int


def _normalized(value: object) -> str:
    return " ".join(str(value).split()).casefold()


def _all_text(node: object) -> str:
    values = node.css("::text").getall()  # type: ignore[attr-defined]
    return " ".join(str(value) for value in values if str(value).strip())


def _depth(node: object) -> int:
    current = getattr(node, "_root", node)
    depth = 0
    while current is not None:
        depth += 1
        current = current.getparent()
    return depth


def _find_anchor(page: object, text: str) -> object | None:
    anchor = page.find_by_text(  # type: ignore[attr-defined]
        text,
        first_match=True,
        partial=True,
    )
    if anchor is not None and getattr(anchor, "tag", None) is not None:
        return anchor

    expected = _normalized(text)
    if not expected:
        return None
    matches = tuple(
        node
        for node in page.css("*")  # type: ignore[attr-defined]
        if expected in _normalized(_all_text(node))
    )
    return max(matches, key=_depth, default=None)


def _card_group(anchor: object) -> tuple[object, tuple[object, ...]] | None:
    current: object | None = anchor
    selected: tuple[object, tuple[object, ...]] | None = None
    while current is not None:
        similar = structurally_similar_nodes(
            current,
            require_card_contract=True,
        )
        if len(similar) >= 2:
            selected = (current, similar)
        elif selected is not None:
            break
        current = getattr(current, "parent", None)
    return selected


def _selector_matches_text(card: object, selector: str) -> bool:
    element_selector = selector.removesuffix("::all-text")
    matches = card.css(element_selector)  # type: ignore[attr-defined]
    return bool(matches and _normalized(_all_text(matches[0])))


def _selector_matches_url(card: object, selector: str) -> bool:
    if selector == "::attr(href)":
        return bool(str(getattr(card, "attrib", {}).get("href", "")).strip())
    return bool(card.css(selector).get())  # type: ignore[attr-defined]


def _title_selector(anchor: object, cards: tuple[object, ...]) -> str | None:
    tag = str(getattr(anchor, "tag", "")).casefold()
    classes = _classes(getattr(anchor, "_root", anchor))
    candidates = [
        *(f"{tag}.{class_name}::all-text" for class_name in classes),
        f"{tag}::all-text",
    ]
    return next(
        (
            selector
            for selector in candidates
            if all(_selector_matches_text(card, selector) for card in cards)
        ),
        None,
    )


def _url_selector(cards: tuple[object, ...]) -> str | None:
    first_tag = str(getattr(cards[0], "tag", "")).casefold()
    candidates = (
        ("::attr(href)", "a::attr(href)")
        if first_tag == "a"
        else ("a::attr(href)", "::attr(href)")
    )
    return next(
        (
            selector
            for selector in candidates
            if all(_selector_matches_url(card, selector) for card in cards)
        ),
        None,
    )


def _simple_selector(node: object, peers: tuple[object, ...] = ()) -> str:
    tag = str(getattr(node, "tag", "")).casefold()
    common_classes = set(_classes(getattr(node, "_root", node)))
    for peer in peers:
        common_classes.intersection_update(
            _classes(getattr(peer, "_root", peer))
        )
    return tag + "".join(f".{class_name}" for class_name in sorted(common_classes))


def _selector_is_exact(
    page: object,
    selector: str,
    cards: tuple[object, ...],
) -> bool:
    try:
        matches = _deduplicate_nodes(page.css(selector))  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return False
    return {
        _structural_identity(node) for node in matches
    } == {
        _structural_identity(node) for node in cards
    }


def _selector_with_exclusions(
    page: object,
    base: str,
    cards: tuple[object, ...],
) -> str | None:
    selected_identities = {_structural_identity(node) for node in cards}
    selected_classes = {
        class_name
        for node in cards
        for class_name in _classes(getattr(node, "_root", node))
    }
    try:
        matches = _deduplicate_nodes(page.css(base))  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return None
    extra_classes = sorted(
        {
            class_name
            for node in matches
            if _structural_identity(node) not in selected_identities
            for class_name in _classes(getattr(node, "_root", node))
            if class_name not in selected_classes
        }
    )
    candidate = base
    for class_name in extra_classes:
        candidate += f":not(.{class_name})"
        if _selector_is_exact(page, candidate, cards):
            return candidate
    return None


def _card_selector(
    page: object,
    cards: tuple[object, ...],
) -> str | None:
    base = _simple_selector(cards[0], cards[1:])
    if _selector_is_exact(page, base, cards):
        return base
    excluded = _selector_with_exclusions(page, base, cards)
    if excluded is not None:
        return excluded

    ancestors: list[str] = []
    current = getattr(cards[0], "parent", None)
    while current is not None and len(ancestors) < 3:
        ancestors.insert(0, _simple_selector(current))
        for target in (base, excluded):
            if target is None:
                continue
            scoped = " > ".join((*ancestors, target))
            if _selector_is_exact(page, scoped, cards):
                return scoped
        current = getattr(current, "parent", None)
    return None


def suggest_from_page(page: object, text: str) -> SelectorSuggestion | None:
    anchor = _find_anchor(page, text)
    if anchor is None:
        return None
    group = _card_group(anchor)
    if group is None:
        return None
    _, similar = group
    cards = _deduplicate_nodes((group[0], *similar))
    title = _title_selector(anchor, cards)
    url = _url_selector(cards)
    card = _card_selector(page, cards)
    if card is None or title is None or url is None:
        return None
    title_matches = sum(_selector_matches_text(card, title) for card in cards)
    url_matches = sum(_selector_matches_url(card, url) for card in cards)
    return SelectorSuggestion(
        card=card,
        title=title,
        url=url,
        cards_found=len(cards),
        title_matches=title_matches,
        url_matches=url_matches,
    )
