"""Verificações de consistência do repositório. Cada função devolve um `Relatorio`."""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import repositorio as repo

REVOKED_LABELS = {"true": "sim", "false": "não"}
UNKNOWN_REVOKED_LABEL = "?"
REFERENCE_ID = r"(?:N|W)\d+[a-z]?"
MANUAL_CITATION_PATTERN = re.compile(rf"\[({REFERENCE_ID}(?:, {REFERENCE_ID})*)\]")
MANUAL_DEFINITION_PATTERN = re.compile(r"^\| ((?:N|W)\d+[a-z]?) \|", re.MULTILINE)
MARKDOWN_LINK_PATTERN = re.compile(r"\]\(([^)\s]+)\)")
MARKDOWN_HEADING_PATTERN = re.compile(r"^#{1,6} (.+)$", re.MULTILINE)
EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:")


@dataclass
class Relatorio:
    titulo: str
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.erros

    def imprimir(self) -> None:
        status = "OK" if self.ok else f"{len(self.erros)} erro(s)"
        print(f"\n== {self.titulo}: {status}, {len(self.avisos)} aviso(s)")
        for erro in self.erros:
            print(f"  ERRO  {erro}")
        for aviso in self.avisos:
            print(f"  aviso {aviso}")


def verificar_selecao() -> Relatorio:
    """_selecao.json, normas/ e INDICE.md descrevem o mesmo conjunto de normas?"""
    relatorio = Relatorio("Seleção x normas/ x INDICE.md")
    selection = repo.load_selection()
    selected_paths = [norm.path for norm in selection.norms]

    _check_selection_file(selection, selected_paths, relatorio)
    _check_copied_files(set(selected_paths), relatorio)
    _check_index(selection, relatorio)
    return relatorio


def _check_selection_file(selection, selected_paths, relatorio) -> None:
    if selection.total != len(selected_paths):
        relatorio.erros.append(f"_selecao.json: total={selection.total}, mas lista {len(selected_paths)} arquivos")
    for path, count in Counter(selected_paths).items():
        if count > 1:
            relatorio.erros.append(f"_selecao.json: {path} aparece {count} vezes")


def _check_copied_files(selected_paths: set[str], relatorio) -> None:
    copied = set(repo.copied_norm_files())
    for path in sorted(selected_paths - copied):
        relatorio.erros.append(f"selecionado mas ausente em normas/: {path}")
    for path in sorted(copied - selected_paths):
        relatorio.erros.append(f"arquivo em normas/ fora da seleção: {path}")


def _check_index(selection, relatorio) -> None:
    index = repo.parse_index()
    category_by_path = {norm.path: norm.category for norm in selection.norms}
    category_counts = Counter(category_by_path.values())

    if index.declared_total != selection.total:
        relatorio.erros.append(f"INDICE.md declara total {index.declared_total}, seleção tem {selection.total}")
    if index.summary_counts != dict(category_counts):
        for category in sorted(set(index.summary_counts) | set(category_counts)):
            declared, actual = index.summary_counts.get(category), category_counts.get(category)
            if declared != actual:
                relatorio.erros.append(f"INDICE.md, resumo: '{category}' declara {declared}, seleção tem {actual}")

    indexed_paths = Counter(row.path for row in index.rows)
    for path in sorted(set(category_by_path) - set(indexed_paths)):
        relatorio.erros.append(f"norma selecionada sem linha no INDICE.md: {path}")
    for path, count in indexed_paths.items():
        if path not in category_by_path:
            relatorio.erros.append(f"INDICE.md cita norma fora da seleção: {path}")
        elif count > 1:
            relatorio.avisos.append(f"INDICE.md lista {path} {count} vezes")

    for row in index.rows:
        _check_index_row(row, category_by_path, relatorio)


def _check_index_row(row, category_by_path, relatorio) -> None:
    expected_category = category_by_path.get(row.path)
    if expected_category and row.section != expected_category:
        relatorio.erros.append(f"{row.path}: na seção '{row.section}', categoria é '{expected_category}'")
    local_file = repo.NORMAS_DIR / row.path
    if not local_file.exists():
        return
    frontmatter = repo.read_frontmatter(local_file)
    expected_label = REVOKED_LABELS.get(frontmatter.get("revogada", ""), UNKNOWN_REVOKED_LABEL)
    if row.revoked_label != expected_label:
        relatorio.erros.append(
            f"{row.path}: coluna Revogada '{row.revoked_label}', frontmatter indica '{expected_label}'"
        )
    source = frontmatter.get("fonte", "")
    if source and source not in row.source_cell:
        relatorio.avisos.append(f"{row.path}: fonte do INDICE.md difere do frontmatter ({source})")


def verificar_integridade(acervo: Path) -> Relatorio:
    """As cópias em normas/ continuam idênticas, byte a byte, ao acervo de origem?"""
    relatorio = Relatorio(f"Integridade frente ao acervo ({acervo})")
    if not acervo.is_dir():
        relatorio.erros.append(f"acervo não encontrado: {acervo} (use --acervo ou ${repo.CORPUS_ENV_VAR})")
        return relatorio
    for norm in repo.load_selection().norms:
        corpus_file = acervo / norm.path
        if not corpus_file.exists():
            relatorio.erros.append(f"não existe mais no acervo: {norm.path}")
        elif not norm.local_file.exists():
            relatorio.erros.append(f"ausente em normas/: {norm.path}")
        elif corpus_file.read_bytes() != norm.local_file.read_bytes():
            relatorio.erros.append(f"difere do acervo (atualizar com `sincronizar`): {norm.path}")
    return relatorio


def arquivos_desatualizados(acervo: Path) -> list[repo.SelectedNorm]:
    return [
        norm
        for norm in repo.load_selection().norms
        if (acervo / norm.path).exists()
        and (not norm.local_file.exists() or (acervo / norm.path).read_bytes() != norm.local_file.read_bytes())
    ]


def verificar_manual() -> Relatorio:
    """Citações [N#]/[W#] do manual estão definidas e os links internos resolvem?"""
    relatorio = Relatorio("Manual (citações e links internos)")
    text = repo.MANUAL_FILE.read_text(encoding="utf-8")
    definitions = MANUAL_DEFINITION_PATTERN.findall(text)
    cited = {
        reference_id
        for citation in MANUAL_CITATION_PATTERN.findall(text)
        for reference_id in citation.split(", ")
    }

    for reference_id, count in Counter(definitions).items():
        if count > 1:
            relatorio.erros.append(f"referência definida {count} vezes: {reference_id}")
    for reference_id in sorted(cited - set(definitions)):
        relatorio.erros.append(f"citação sem definição na lista de referências: [{reference_id}]")
    for reference_id in sorted(set(definitions) - cited):
        relatorio.avisos.append(f"referência definida mas nunca citada no texto: {reference_id}")

    relatorio.erros.extend(broken_internal_links(repo.MANUAL_FILE, text))
    return relatorio


def broken_internal_links(markdown_file: Path, text: str) -> list[str]:
    anchors = {github_anchor(heading) for heading in MARKDOWN_HEADING_PATTERN.findall(text)}
    problems = []
    for target in MARKDOWN_LINK_PATTERN.findall(text):
        if target.startswith(EXTERNAL_LINK_PREFIXES):
            continue
        path_part, _, anchor = target.partition("#")
        if path_part and not (markdown_file.parent / path_part).exists():
            problems.append(f"link para arquivo inexistente: {target}")
        elif not path_part and anchor not in anchors:
            problems.append(f"âncora inexistente: #{anchor}")
    return problems


def github_anchor(heading: str) -> str:
    """Mesma regra de âncora do GitHub (usada também em manual/gerar_pdf.py)."""
    text = re.sub(r"[`*_]|\[([^\]]*)\]\([^)]*\)", r"\1", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def verificar_markdown_interno() -> Relatorio:
    """Links relativos de INDICE.md, REFERENCIAS.md e CLAUDE.md apontam para arquivos existentes?"""
    relatorio = Relatorio("Links internos dos .md da raiz")
    for markdown_file in (repo.INDEX_FILE, repo.REFERENCES_FILE, repo.REPO_ROOT / "CLAUDE.md"):
        text = markdown_file.read_text(encoding="utf-8")
        for problem in broken_internal_links(markdown_file, text):
            relatorio.erros.append(f"{markdown_file.name}: {problem}")
    return relatorio
