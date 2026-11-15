"""Operações que alteram ou consultam as normas: sincronizar com o acervo e buscar."""

import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import repositorio as repo
from .verificacoes import arquivos_desatualizados


@dataclass
class SearchHit:
    norm: repo.SelectedNorm
    title: str
    revoked: str
    occurrences: int


def sincronizar(acervo: Path, aplicar: bool) -> list[repo.SelectedNorm]:
    """Copia do acervo as normas selecionadas que mudaram lá. Sem `aplicar`, só lista."""
    outdated = arquivos_desatualizados(acervo)
    if aplicar:
        for norm in outdated:
            norm.local_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(acervo / norm.path, norm.local_file)
    return outdated


def buscar(term: str, category_filter: str | None = None) -> list[SearchHit]:
    """Busca o termo (sem diferenciar acentos e caixa) nas normas selecionadas."""
    normalized_term = normalize(term)
    hits = []
    for norm in repo.load_selection().norms:
        if category_filter and normalize(category_filter) not in normalize(norm.category):
            continue
        text = norm.local_file.read_text(encoding="utf-8")
        occurrences = normalize(text).count(normalized_term)
        if occurrences:
            frontmatter = repo.read_frontmatter(norm.local_file)
            hits.append(
                SearchHit(norm, frontmatter.get("titulo", norm.path), frontmatter.get("revogada", "?"), occurrences)
            )
    return sorted(hits, key=lambda hit: hit.occurrences, reverse=True)


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))
