"""Acesso aos arquivos do repositório: seleção, normas copiadas, índice e acervo de origem."""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NORMAS_DIR = REPO_ROOT / "normas"
SELECTION_FILE = REPO_ROOT / "_selecao.json"
INDEX_FILE = REPO_ROOT / "INDICE.md"
REFERENCES_FILE = REPO_ROOT / "REFERENCIAS.md"
MANUAL_FILE = REPO_ROOT / "manual" / "manual-clinica-psicologia-sjc.md"

CORPUS_ENV_VAR = "LEIS_ACERVO"
DEFAULT_CORPUS_DIR = REPO_ROOT.parent / "leis"

FRONTMATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
FRONTMATTER_LINE_PATTERN = re.compile(r"^([A-Za-z_]+):\s*(.*)$")
INDEX_LINK_PATTERN = re.compile(r"\[[^\]]*\]\((normas/[^)]+)\)")
INDEX_SECTION_PATTERN = re.compile(r"^## (.+)$")
INDEX_SUMMARY_ROW_PATTERN = re.compile(r"^\| (.+?) \| (\d+) \|$")
INDEX_TOTAL_PATTERN = re.compile(r"\*\*Total: (\d+) normas\.\*\*")
INDEX_SECTIONS_WITHOUT_NORMS = {"Não encontradas no acervo"}


@dataclass
class SelectedNorm:
    path: str
    category: str

    @property
    def local_file(self) -> Path:
        return NORMAS_DIR / self.path


@dataclass
class Selection:
    total: int
    missing: list
    norms: list[SelectedNorm]


@dataclass
class IndexRow:
    section: str
    path: str
    revoked_label: str
    source_cell: str


@dataclass
class IndexContents:
    declared_total: int | None
    summary_counts: dict[str, int] = field(default_factory=dict)
    rows: list[IndexRow] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)


def corpus_dir(override: str | None = None) -> Path:
    """Diretório do acervo ctresb/leis: opção da linha de comando, variável de ambiente ou ../leis."""
    configured = override or os.environ.get(CORPUS_ENV_VAR)
    return Path(configured).expanduser().resolve() if configured else DEFAULT_CORPUS_DIR


def load_selection() -> Selection:
    data = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
    norms = [SelectedNorm(item["path"], item["category"]) for item in data["files"]]
    return Selection(total=data["total"], missing=data["missing"], norms=norms)


def save_selection(selection: Selection) -> None:
    data = {
        "total": selection.total,
        "missing": selection.missing,
        "files": [{"path": norm.path, "category": norm.category} for norm in selection.norms],
    }
    SELECTION_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_frontmatter(markdown_file: Path) -> dict[str, str]:
    """Lê o frontmatter simples (chave: valor) das normas, sem depender de PyYAML."""
    match = FRONTMATTER_PATTERN.match(markdown_file.read_text(encoding="utf-8"))
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        line_match = FRONTMATTER_LINE_PATTERN.match(line)
        if line_match:
            fields[line_match.group(1)] = line_match.group(2).strip().strip('"')
    return fields


def parse_index() -> IndexContents:
    text = INDEX_FILE.read_text(encoding="utf-8")
    total_match = INDEX_TOTAL_PATTERN.search(text)
    contents = IndexContents(declared_total=int(total_match.group(1)) if total_match else None)

    current_section = None
    for line in text.splitlines():
        section_match = INDEX_SECTION_PATTERN.match(line)
        if section_match:
            current_section = section_match.group(1).strip()
            contents.sections.append(current_section)
            continue
        if current_section is None:
            summary_match = INDEX_SUMMARY_ROW_PATTERN.match(line)
            if summary_match:
                contents.summary_counts[summary_match.group(1)] = int(summary_match.group(2))
            continue
        row = parse_index_row(current_section, line)
        if row:
            contents.rows.append(row)
    return contents


def parse_index_row(section: str, line: str) -> IndexRow | None:
    """Linha de norma: | [título](normas/...) | data | ementa | revogada | fonte |."""
    link_match = INDEX_LINK_PATTERN.search(line)
    if not line.startswith("|") or not link_match:
        return None
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return IndexRow(section, link_match.group(1).removeprefix("normas/"), cells[-2], cells[-1])


def copied_norm_files() -> list[str]:
    return sorted(str(path.relative_to(NORMAS_DIR)) for path in NORMAS_DIR.rglob("*") if path.is_file())
