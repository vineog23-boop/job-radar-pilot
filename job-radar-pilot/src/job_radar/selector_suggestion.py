from __future__ import annotations

from dataclasses import dataclass
from job_radar.adaptive import (
    _classes,
    _deduplicate_nodes,
    _structural_identity,
    adaptive_card_is_safe,
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
    while current is not None:
        similar = structurally_similar_nodes(
            current,
            require_card_contract=True,
        )
        if len(similar) >= 2:
            cards = _deduplicate_nodes((current, *similar))
            if any(not adaptive_card_is_safe(card) for card in cards):
                return None
            return current, similar
        current = getattr(current, "parent", None)
    return None


def _title_nodes(card: object, selector: str) -> tuple[object, ...]:
    element_selector = selector.removesuffix("::all-text")
    return tuple(card.css(element_selector))  # type: ignore[attr-defined]


def _url_nodes(card: object, selector: str) -> tuple[object, ...]:
    if selector == "::attr(href)":
        return (card,)
    element_selector = selector.removesuffix("::attr(href)")
    return tuple(card.css(element_selector))  # type: ignore[attr-defined]


def _selector_matches_text(card: object, selector: str) -> bool:
    matches = _title_nodes(card, selector)
    return len(matches) == 1 and bool(_normalized(_all_text(matches[0])))


def _selector_matches_url(card: object, selector: str) -> bool:
    matches = _url_nodes(card, selector)
    return len(matches) == 1 and bool(
        str(getattr(matches[0], "attrib", {}).get("href", "")).strip()
    )


def _contains(ancestor: object, descendant: object) -> bool:
    ancestor_identity = _structural_identity(ancestor)
    current = getattr(descendant, "_root", descendant)
    while current is not None:
        if _structural_identity(current) == ancestor_identity:
            return True
        current = current.getparent()
    return False


def _selectors_form_linked_record(
    card: object,
    title_selector: str,
    url_selector: str,
) -> bool:
    titles = _title_nodes(card, title_selector)
    links = _url_nodes(card, url_selector)
    if len(titles) != 1 or len(links) != 1:
        return False
    return _contains(links[0], titles[0]) or _contains(titles[0], links[0])


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
            if _structural_identity(_title_nodes(cards[0], selector)[0])
            == _structural_identity(anchor)
        ),
        None,
    )


def _url_selector(cards: tuple[object, ...], title: str) -> str | None:
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
            and all(
                _selectors_form_linked_record(card, title, selector)
                for card in cards
            )
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


def _has_mixed_class_modifiers(cards: tuple[object, ...]) -> bool:
    class_sets = [
        set(_classes(getattr(card, "_root", card)))
        for card in cards
    ]
    common = set.intersection(*class_sets) if class_sets else set()
    modifiers = [classes - common for classes in class_sets]
    return any(not item for item in modifiers) and any(item for item in modifiers)


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
    if _has_mixed_class_modifiers(cards):
        return None
    title = _title_selector(anchor, cards)
    if title is None:
        return None
    url = _url_selector(cards, title)
    card = _card_selector(page, cards)
    if card is None or url is None:
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
