"""Medição do classificador numa amostra salva (item 1.4 do backlog).

Responde três perguntas, sem acessar portal nenhum:

1. **Como o classificador atual distribui a amostra?** (por faixa, por portal e
   pelos motivos mais comuns de a vaga não ser "Mais compatível").
2. **O que mudou?** Contra os rótulos gravados na própria amostra ou contra uma
   execução anterior salva com ``--salvar`` (o "antes × depois" de cada PR).
3. **Acertou?** Só com gabarito humano: um CSV em que a pessoa escreve a faixa
   que ela esperava para cada vaga. Sem gabarito, a ferramenta mede *mudança*,
   não *acerto* — o classificador não pode ser juiz de si mesmo.
"""

from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from job_radar.fit import FIT_NAMES, fit_reasons, fit_state, is_off_topic
from job_radar.models import SearchProfile
from job_radar.reclassify import reclassify_payloads

OFF_TOPIC = "OFF_TOPIC"
CATEGORY_NAMES = {**FIT_NAMES, OFF_TOPIC: "Fora da área de tecnologia"}
# Ordem de exibição das faixas no relatório.
CATEGORY_ORDER = ("READY", "CONDITIONAL", "AMBIGUOUS", "EXCLUDE", OFF_TOPIC)
MAX_EXAMPLES = 15


def category(job_or_labels: Mapping[str, Any] | Iterable[Any]) -> str:
    """Faixa para medir: fora da área vale mais que o FIT (some do painel)."""

    return OFF_TOPIC if is_off_topic(job_or_labels) else fit_state(job_or_labels)


def load_sample(path: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}, linha {number}: JSON invalido ({exc.msg}).") from exc
        if isinstance(item, dict):
            payloads.append(item)
    return payloads


def load_gold(path: Path) -> dict[str, str]:
    """Gabarito: CSV com ``url`` e ``esperado`` (``;`` ou ``,``). Vazio = sem resposta."""

    text = path.read_text(encoding="utf-8-sig")
    delimiter = ";" if text.splitlines()[0].count(";") >= text.splitlines()[0].count(",") else ","
    gold: dict[str, str] = {}
    for row in csv.DictReader(text.splitlines(), delimiter=delimiter):
        url = (row.get("url") or "").strip()
        expected = (row.get("esperado") or "").strip().upper()
        if not url or not expected:
            continue
        if expected not in CATEGORY_NAMES:
            raise ValueError(
                f"Gabarito: '{expected}' nao e uma faixa valida "
                f"(use {', '.join(CATEGORY_ORDER)})."
            )
        gold[url] = expected
    return gold


def _ordered(counter: Mapping[str, int]) -> dict[str, int]:
    known = [name for name in CATEGORY_ORDER if counter.get(name)]
    others = sorted(name for name in counter if name not in CATEGORY_ORDER and counter[name])
    return {name: counter[name] for name in (*known, *others)}


def evaluate(
    payloads: Iterable[Mapping[str, Any]],
    profile: SearchProfile,
    default_countries: Mapping[str, str | None] | None = None,
    *,
    gold: Mapping[str, str] | None = None,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    original = [dict(payload) for payload in payloads]
    updated = reclassify_payloads(original, profile, default_countries)

    jobs: dict[str, str] = {}
    titles: dict[str, str] = {}
    distribution: Counter[str] = Counter()
    saved: Counter[str] = Counter()
    by_source: dict[str, Counter[str]] = {}
    reasons: Counter[str] = Counter()
    for before, after in zip(original, updated):
        url = str(after.get("canonical_url"))
        current = category(after)
        jobs[url] = current
        titles[url] = str(after.get("title") or "Cargo não informado")
        distribution[current] += 1
        saved[category(before)] += 1
        by_source.setdefault(str(after.get("source") or "?"), Counter())[current] += 1
        if current not in {"READY", OFF_TOPIC}:
            reasons.update(fit_reasons(after))

    if base is not None:
        previous = {str(url): str(value) for url, value in (base.get("jobs") or {}).items()}
        against = "base"
    else:
        previous = {
            str(payload.get("canonical_url")): category(payload) for payload in original
        }
        against = "amostra"
    transitions: Counter[str] = Counter()
    examples: list[dict[str, str]] = []
    for url, current in jobs.items():
        old = previous.get(url)
        if old is None or old == current:
            continue
        transitions[f"{old} -> {current}"] += 1
        if len(examples) < MAX_EXAMPLES:
            examples.append({"title": titles[url], "from": old, "to": current, "url": url})

    gold_result = None
    if gold:
        labeled = [url for url in gold if url in jobs]
        correct = [url for url in labeled if gold[url] == jobs[url]]
        confusion = Counter(
            f"{gold[url]} -> {jobs[url]}" for url in labeled if gold[url] != jobs[url]
        )
        gold_result = {
            "labeled": len(labeled),
            "correct": len(correct),
            "accuracy": len(correct) / len(labeled) if labeled else 0.0,
            "confusion": dict(confusion.most_common()),
            "mistakes": [
                {"title": titles[url], "expected": gold[url], "got": jobs[url], "url": url}
                for url in labeled
                if gold[url] != jobs[url]
            ],
        }

    return {
        "total": len(updated),
        "distribution": _ordered(distribution),
        "saved_distribution": _ordered(saved),
        "by_source": {
            source: _ordered(counts)
            for source, counts in sorted(by_source.items(), key=lambda item: -sum(item[1].values()))
        },
        "reasons": reasons.most_common(),
        "changes": {
            "against": against,
            "count": sum(transitions.values()),
            "transitions": dict(transitions.most_common()),
            "examples": examples,
        },
        "gold": gold_result,
        "jobs": jobs,
    }


def _percent(part: int, total: int) -> str:
    return f"{(100 * part / total):.0f}%" if total else "0%"


def format_report(result: Mapping[str, Any]) -> str:
    total = int(result["total"])
    lines = [f"Vagas avaliadas: {total}", "", "Faixas (classificador atual):"]
    for name, count in result["distribution"].items():
        lines.append(
            f"  {CATEGORY_NAMES.get(name, name):<28} {name:<12} {count:>4}  {_percent(count, total)}"
        )

    changes = result["changes"]
    label = "à base" if changes["against"] == "base" else "aos rótulos gravados na amostra"
    lines += ["", f"Mudaram de faixa em relação {label}: {changes['count']}"]
    for transition, count in changes["transitions"].items():
        lines.append(f"  {transition:<28} {count:>4}")
    for example in changes["examples"]:
        lines.append(f"    - {example['title']} ({example['from']} -> {example['to']})")

    if result["reasons"]:
        lines += ["", "Motivos mais comuns (fora as 'Mais compatível'):"]
        for reason, count in result["reasons"][:10]:
            lines.append(f"  {reason:<40} {count:>4}")

    lines += ["", "Por portal:"]
    for source, counts in result["by_source"].items():
        detail = ", ".join(f"{name} {count}" for name, count in counts.items())
        lines.append(f"  {source:<20} {sum(counts.values()):>4}  ({detail})")

    gold = result.get("gold")
    lines.append("")
    if gold:
        lines.append(
            f"Gabarito humano: {gold['correct']}/{gold['labeled']} certas "
            f"({_percent(gold['correct'], gold['labeled'])})"
        )
        for transition, count in gold["confusion"].items():
            lines.append(f"  esperado -> obtido  {transition:<28} {count:>4}")
        for mistake in gold["mistakes"][:MAX_EXAMPLES]:
            lines.append(
                f"    - {mistake['title']} (esperado {mistake['expected']}, saiu {mistake['got']})"
            )
    else:
        lines.append(
            "Sem gabarito humano: isto mede mudança, não acerto. Preencha a coluna "
            "'esperado' do gabarito para medir a taxa de acerto."
        )
    return "\n".join(lines) + "\n"
