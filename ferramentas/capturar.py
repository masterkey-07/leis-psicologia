"""Captura o conteúdo dos sites listados em REFERENCIAS.md para a pasta referencias/.

Cada link vira um Markdown com metadados (origem, data, método) e o texto principal da página,
sem menus, rodapés e avisos de cookies. PDFs são convertidos com `pdftotext`. Páginas que
dependem de JavaScript ou recusam clientes automatizados são tentadas de novo pelo Chrome
headless; o que mesmo assim falhar fica registrado no índice como não capturado.

Requer `beautifulsoup4`; para PDFs, `pdftotext` (poppler-utils); Chrome/Chromium é opcional.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from . import repositorio as repo
from .links import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from .pdf import find_chrome

OUTPUT_DIR = repo.REPO_ROOT / "referencias"
INDEX_NAME = "README.md"
MIN_USEFUL_TEXT_CHARS = 400
MAX_SLUG_LENGTH = 60
CHROME_RENDER_BUDGET_MS = "15000"
CHROME_TIMEOUT_SECONDS = 90

REFERENCE_SECTION_PATTERN = re.compile(r"^## (?:\d+\. )?(.+)$")
REFERENCE_ROW_PATTERN = re.compile(r"^\| (.+?) \| (.+?) \| (https?://\S+) \|$")
MARKDOWN_LINK_IN_CELL_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
BLANK_LINES_PATTERN = re.compile(r"\n{3,}")
TABLE_COLUMN_GAP_PATTERN = re.compile(r"(?<=\S) {3,}(?=\S)")
INLINE_SPACES_PATTERN = re.compile(r"[ \t ]+")

# <form> não entra: páginas ASP.NET (ex.: Portal do Simples) envolvem todo o conteúdo num form.
NOISE_TAGS = ("script", "style", "noscript", "svg", "nav", "header", "footer", "iframe",
              "aside", "button", "select", "template")
MAIN_CONTENT_SELECTORS = ("main", "article", "#content", "#conteudo", "#main-content",
                          "#content-core", ".content", ".conteudo", "#parent-fieldname-text")
# Linhas de interface que aparecem em quase todos os portais e não têm conteúdo.
BOILERPLATE_LINES = {
    "imprimir", "enviar por e-mail", "informar erro", "contraste", "aumentar", "regular", "×",
    "entendi e aceito", "compartilhar", "voltar", "menu", "ir para o conteúdo", "fechar",
    "copiar para área de transferência", "link copiado para a área de transferência",
    "compartilhe:", "facebook", "twitter", "whatsapp", "linkedin", "início do menu principal",
}
BOILERPLATE_FRAGMENTS = ("utiliza cookies", "políticas de uso de cookies", "aceitar cookies",
                         "políticas de privacidade e termos de uso")
BLOCK_TAGS = {"p", "div", "section", "article", "main", "ul", "ol", "dl", "dd", "dt",
              "blockquote", "figure", "figcaption", "center"}


@dataclass
class Reference:
    order: int
    section: str
    name: str
    purpose: str
    url: str

    @property
    def file_name(self) -> str:
        return f"{self.order:02d}-{slugify(self.name)}.md"


@dataclass
class Capture:
    reference: Reference
    method: str
    final_url: str | None
    markdown: str
    failure: str | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None


def capturar_referencias(only: str | None = None) -> list[Capture]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    references = parse_references()
    if only:
        references = [ref for ref in references if only.lower() in (ref.name + ref.url).lower()]
    else:
        remove_previous_captures()
    captures = []
    for reference in references:
        capture = capture_reference(reference)
        write_capture(capture)
        captures.append(capture)
        print(f"{'ok   ' if capture.ok else 'FALHA'} {reference.file_name} ({capture.method})")
    if not only:
        write_index(captures)
    return captures


def remove_previous_captures() -> None:
    """Numeração segue REFERENCIAS.md; arquivos de rodadas anteriores ficariam órfãos."""
    for old_file in OUTPUT_DIR.glob("*.md"):
        old_file.unlink()


def parse_references() -> list[Reference]:
    references, section = [], ""
    for line in repo.REFERENCES_FILE.read_text(encoding="utf-8").splitlines():
        section_match = REFERENCE_SECTION_PATTERN.match(line)
        if section_match:
            section = section_match.group(1).strip()
            continue
        row_match = REFERENCE_ROW_PATTERN.match(line)
        if row_match:
            name = MARKDOWN_LINK_IN_CELL_PATTERN.sub(r"\1", row_match.group(1)).replace("†", "").strip()
            references.append(Reference(len(references) + 1, section, name, row_match.group(2), row_match.group(3)))
    return references


def capture_reference(reference: Reference) -> Capture:
    try:
        body, content_type, final_url = fetch(reference.url)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as fetch_error:
        return capture_with_chrome(reference, f"HTTP: {fetch_error}")

    if is_pdf(body, content_type):
        return capture_pdf(reference, body, final_url)
    markdown = html_to_markdown(body, final_url)
    if len(markdown) >= MIN_USEFUL_TEXT_CHARS:
        return Capture(reference, "http", final_url, markdown)
    return capture_with_chrome(reference, "pouco texto no HTML estático (página depende de JavaScript?)")


def fetch(url: str) -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read(), response.headers.get("Content-Type", ""), response.geturl()


def is_pdf(body: bytes, content_type: str) -> bool:
    return "pdf" in content_type.lower() or body.startswith(b"%PDF")


def capture_pdf(reference: Reference, body: bytes, final_url: str) -> Capture:
    if not shutil.which("pdftotext"):
        return Capture(reference, "pdf", final_url, "", failure="pdftotext não instalado")
    with tempfile.TemporaryDirectory() as temporary_dir:
        pdf_path = Path(temporary_dir) / "documento.pdf"
        pdf_path.write_bytes(body)
        result = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
                                capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return Capture(reference, "pdf", final_url, "", failure=f"pdftotext: {result.stderr.strip()}")
    return Capture(reference, "pdf", final_url, clean_text(reflow_pdf_text(result.stdout)))


def capture_with_chrome(reference: Reference, previous_problem: str) -> Capture:
    try:
        chrome = find_chrome()
    except FileNotFoundError:
        return Capture(reference, "http", None, "", failure=previous_problem)
    with tempfile.TemporaryDirectory() as temporary_dir:
        try:
            result = subprocess.run(
                [chrome, "--headless", "--disable-gpu", f"--user-data-dir={temporary_dir}",
                 f"--user-agent={USER_AGENT}", f"--virtual-time-budget={CHROME_RENDER_BUDGET_MS}",
                 "--dump-dom", reference.url],
                capture_output=True, text=True, timeout=CHROME_TIMEOUT_SECONDS, check=False,
            )
        except subprocess.TimeoutExpired:
            return Capture(reference, "chrome", None, "", failure=f"{previous_problem}; Chrome excedeu o tempo")
    markdown = html_to_markdown(result.stdout.encode("utf-8"), reference.url)
    if len(markdown) >= MIN_USEFUL_TEXT_CHARS and "403 Forbidden" not in markdown:
        return Capture(reference, "chrome", reference.url, markdown)
    return Capture(reference, "chrome", None, "",
                   failure=f"{previous_problem}; nem o Chrome headless obteve o conteúdo")


def html_to_markdown(html: bytes, base_url: str) -> str:
    from bs4 import BeautifulSoup  # Import tardio: dependência só deste comando.

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    return clean_text(render_node(main_content(soup), base_url))


def main_content(soup):
    """Bloco principal: o candidato com mais texto, ou a página toda se nenhum tiver o suficiente.

    Escolher o primeiro seletor que casa não basta: `.content` às vezes é um widget minúsculo.
    """
    candidates = [found for selector in MAIN_CONTENT_SELECTORS for found in soup.select(selector)]
    best = max(candidates, key=lambda tag: len(tag.get_text(strip=True)), default=None)
    if best is not None and len(best.get_text(strip=True)) >= MIN_USEFUL_TEXT_CHARS:
        return best
    return soup.body or soup


def render_node(node, base_url: str) -> str:
    from bs4.element import NavigableString, PreformattedString, Tag

    if isinstance(node, PreformattedString):  # comentários HTML, CDATA, doctype
        return ""
    if isinstance(node, NavigableString):
        return INLINE_SPACES_PATTERN.sub(" ", str(node).replace("\n", " "))
    if not isinstance(node, Tag):
        return ""
    name = node.name
    if name == "table":
        return render_table(node)
    inner = "".join(render_node(child, base_url) for child in node.children)
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        heading_text = inner.strip()
        return f"\n\n{'#' * (int(name[1]) + 1)} {heading_text}\n\n" if heading_text else ""
    if name == "li":
        return f"\n- {inner.strip()}"
    if name == "br":
        return "\n"
    if name == "a":
        return render_link(node, inner, base_url)
    if name in ("strong", "b") and inner.strip():
        return f" **{inner.strip()}** "
    if name in BLOCK_TAGS:
        return f"\n\n{inner}\n\n"
    return inner


def render_link(node, inner: str, base_url: str) -> str:
    text, href = inner.strip(), node.get("href", "")
    if not text or not href or href.startswith(("#", "javascript:", "mailto:")):
        return inner
    url = urljoin(base_url, href)
    if "\n" in text or text.startswith("#"):
        # Link que envolve um cartão (títulos, parágrafos): vira um item com o primeiro título.
        first_line = next(line.strip(" #*") for line in text.splitlines() if line.strip(" #*"))
        return f"\n\n- [{first_line}]({url})\n\n"
    return f" [{text}]({url}) "


def render_table(table) -> str:
    rows = []
    for row in table.find_all("tr"):
        cells = [INLINE_SPACES_PATTERN.sub(" ", cell.get_text(" ", strip=True)).replace("|", "/")
                 for cell in row.find_all(["th", "td"])]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    lines = ["| " + " | ".join(row + [""] * (width - len(row))) + " |" for row in rows]
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return "\n\n" + "\n".join(lines) + "\n\n"


def reflow_pdf_text(text: str) -> str:
    """Junta em parágrafos a prosa quebrada pelo PDF; linhas de tabela viram itens de lista.

    O texto vem de `pdftotext -layout`, que preserva colunas com sequências de espaços; sem isso,
    tabelas (ex.: CNAE x atividade) saem com as colunas separadas e perdem a correspondência.
    """
    output, prose = [], []

    def flush_prose() -> None:
        if prose:
            output.append(re.sub(r"(\w)- (\w)", r"\1\2", " ".join(prose)))  # hifenização
            prose.clear()

    for raw_line in text.replace("\f", "\n\n").splitlines():
        line = raw_line.strip()
        if not line:
            flush_prose()
        elif TABLE_COLUMN_GAP_PATTERN.search(line):
            flush_prose()
            output.append("- " + TABLE_COLUMN_GAP_PATTERN.sub(" · ", line))
        else:
            prose.append(line)
    flush_prose()
    return "\n\n".join(output)


def clean_text(text: str) -> str:
    kept, previous = [], None
    for raw_line in text.splitlines():
        line = INLINE_SPACES_PATTERN.sub(" ", raw_line).strip()
        line = re.sub(r"\*\*\s*\*\*", "", line).replace("<br/>", "").strip()
        if is_boilerplate(line) or (line and line == previous):
            continue
        kept.append(line)
        if line:
            previous = line
    return BLANK_LINES_PATTERN.sub("\n\n", "\n".join(kept)).strip()


def is_boilerplate(line: str) -> bool:
    lowered = line.lower()
    return lowered in BOILERPLATE_LINES or any(fragment in lowered for fragment in BOILERPLATE_FRAGMENTS)


def write_capture(capture: Capture) -> None:
    ref = capture.reference
    metadata = {
        "titulo": ref.name,
        "secao": ref.section,
        "finalidade": ref.purpose,
        "url": ref.url,
        "url_final": capture.final_url or "",
        "capturado_em": date.today().isoformat(),
        "metodo": capture.method,
        "status": "capturado" if capture.ok else "falhou",
    }
    # json.dumps gera strings entre aspas com escape, que também são YAML válido.
    frontmatter = [
        "---",
        *(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items()),
        "---",
        "",
        f"# {ref.name}",
        "",
        f"> Cópia informativa de {ref.url}, capturada automaticamente em "
        f"{date.today().strftime('%d/%m/%Y')} (`python3 -m ferramentas capturar`). Pode estar "
        "incompleta ou desatualizada: confira sempre a página oficial.",
        "",
    ]
    body = capture.markdown if capture.ok else (
        f"**Conteúdo não capturado.** Motivo: {capture.failure}.\n\nAbra o link no navegador: {ref.url}"
    )
    (OUTPUT_DIR / ref.file_name).write_text("\n".join(frontmatter) + body + "\n", encoding="utf-8")


def write_index(captures: list[Capture]) -> None:
    lines = [
        "# Conteúdo dos sites de referência",
        "",
        f"Cópias do conteúdo dos links de [REFERENCIAS.md](../REFERENCIAS.md), capturadas em "
        f"{date.today().strftime('%d/%m/%Y')} com `python3 -m ferramentas capturar` (que regera esta "
        "pasta inteira). São cópias informativas para consulta offline: a fonte válida é sempre o site "
        "oficial. Normas completas do acervo estão em [../normas/](../normas/).",
        "",
        "| # | Referência | Seção | Status | Arquivo |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for capture in captures:
        ref = capture.reference
        status = f"capturado ({capture.method})" if capture.ok else "não capturado — abrir no navegador"
        lines.append(f"| {ref.order} | [{ref.name}]({ref.url}) | {ref.section} | {status} | "
                     f"[{ref.file_name}]({ref.file_name}) |")
    (OUTPUT_DIR / INDEX_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:MAX_SLUG_LENGTH].rstrip("-")
