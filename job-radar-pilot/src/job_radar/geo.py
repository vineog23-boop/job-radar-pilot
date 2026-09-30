"""Estados brasileiros: converte as localidades do perfil em nomes de estado.

Usado para filtrar buscas de portais que aceitam estado (ex.: API do Gupy) sem
deixar de fora quem procura vaga presencial/híbrida perto de casa.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# Nome oficial com acentos, como os portais o exibem.
STATE_NAMES: dict[str, str] = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}


def _plain(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[-_,/]+", " ", text).split())


_BY_PLAIN_NAME = {_plain(name): uf for uf, name in STATE_NAMES.items()}
_UFS = {uf.casefold(): uf for uf in STATE_NAMES}


def uf_from_scope(scope: str) -> str | None:
    """UF de uma localidade do perfil ("sao-carlos-sp", "sc", "santa-catarina")."""

    text = _plain(scope)
    if not text or text in {"brasil", "brazil", "remoto brasil"}:
        return None
    if text in _UFS:
        return _UFS[text]
    if text in _BY_PLAIN_NAME:
        return _BY_PLAIN_NAME[text]
    # "cidade uf" no fim; "cidade estado por extenso" também.
    last = text.rsplit(" ", 1)[-1]
    if " " in text and last in _UFS:
        return _UFS[last]
    for plain_name, uf in sorted(_BY_PLAIN_NAME.items(), key=lambda item: -len(item[0])):
        if text.endswith(" " + plain_name):
            return uf
    return None


def state_names_from_scopes(scopes: Iterable[str], *, limit: int = 5) -> list[str]:
    """Nomes de estado (sem repetição) das localidades que apontam para um estado."""

    names: list[str] = []
    for scope in scopes:
        uf = uf_from_scope(scope)
        if uf and STATE_NAMES[uf] not in names:
            names.append(STATE_NAMES[uf])
        if len(names) >= limit:
            break
    return names
