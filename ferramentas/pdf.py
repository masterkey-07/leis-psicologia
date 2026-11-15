"""Gera o PDF do manual a partir do Markdown (comando `python3 -m ferramentas pdf`).

Requer o pacote Python `markdown-it-py` e o Google Chrome (ou Chromium) para imprimir o HTML.
Links relativos para arquivos do repositório viram links do GitHub, para continuarem
funcionando quando o PDF for compartilhado fora do repositório.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .repositorio import MANUAL_FILE, FRONTMATTER_PATTERN
from .verificacoes import github_anchor

OUTPUT_PDF = MANUAL_FILE.with_suffix(".pdf")
REPOSITORY_BLOB_URL = "https://github.com/masterkey-07/leis-psicologia/blob/main/"
DOCUMENT_TITLE = "Manual da Clínica de Psicologia — São José dos Campos/SP"
CHROME_CANDIDATES = ("google-chrome", "chromium", "chromium-browser")

UNCHECKED_TASK_PATTERN = re.compile(r"<li>\[ \] ")
HEADING_PATTERN = re.compile(r"<h([1-4])>(.*?)</h\1>")
RELATIVE_REPO_LINK_PATTERN = re.compile(r'href="\.\./([^"#]+)"')
TAG_PATTERN = re.compile(r"<[^>]+>")

STYLESHEET = """
@page {
  size: A4;
  margin: 18mm 16mm 20mm 16mm;
  @bottom-center { content: counter(page) " / " counter(pages); font: 9pt sans-serif; color: #666; }
}
body { font-family: "Noto Sans", "DejaVu Sans", Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 22pt; color: #1f3a5f; margin: 0 0 6pt; }
h2 { font-size: 15pt; color: #1f3a5f; border-bottom: 2px solid #1f3a5f; padding-bottom: 3pt;
     margin-top: 20pt; break-before: page; }
h2:nth-of-type(-n+2) { break-before: auto; }
h3 { font-size: 12pt; color: #2c5282; margin-top: 14pt; }
h1 + p + p + blockquote, h2, h3 { break-after: avoid; }
a { color: #2c5282; text-decoration: none; word-break: break-word; }
blockquote { border-left: 4px solid #c05621; background: #fff7ed; margin: 10pt 0;
             padding: 6pt 10pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9pt; }
th, td { border: 1px solid #cbd5e0; padding: 4pt 5pt; vertical-align: top; text-align: left; }
th { background: #edf2f7; }
tr { break-inside: avoid; }
code { font-size: 9pt; background: #f1f5f9; padding: 0 2pt; }
hr { display: none; }
li.task { list-style: none; margin-left: -14pt; }
"""


def gerar_pdf() -> Path:
    markdown_text = FRONTMATTER_PATTERN.sub("", MANUAL_FILE.read_text(encoding="utf-8"))
    html_body = render_markdown(markdown_text)
    print_html_to_pdf(wrap_in_document(html_body), OUTPUT_PDF)
    return OUTPUT_PDF


def render_markdown(markdown_text: str) -> str:
    # Import tardio: markdown-it-py só é necessário para este comando.
    from markdown_it import MarkdownIt

    renderer = MarkdownIt("commonmark").enable("table")
    html = renderer.render(markdown_text)
    html = HEADING_PATTERN.sub(add_heading_anchor, html)
    html = UNCHECKED_TASK_PATTERN.sub('<li class="task">☐ ', html)
    return RELATIVE_REPO_LINK_PATTERN.sub(rf'href="{REPOSITORY_BLOB_URL}\1"', html)


def add_heading_anchor(match: re.Match) -> str:
    level, inner_html = match.group(1), match.group(2)
    heading_text = TAG_PATTERN.sub("", inner_html)
    return f'<h{level} id="{github_anchor(heading_text)}">{inner_html}</h{level}>'


def wrap_in_document(html_body: str) -> str:
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<title>{DOCUMENT_TITLE}</title><style>{STYLESHEET}</style></head>"
        f"<body>{html_body}</body></html>"
    )


def print_html_to_pdf(html_document: str, output_pdf: Path) -> None:
    chrome = find_chrome()
    with tempfile.TemporaryDirectory() as temporary_dir:
        html_path = Path(temporary_dir) / "manual.html"
        html_path.write_text(html_document, encoding="utf-8")
        subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--user-data-dir={temporary_dir}/chrome-profile",
                f"--print-to-pdf={output_pdf}",
                html_path.as_uri(),
            ],
            check=True,
            capture_output=True,
        )


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        chrome_path = shutil.which(candidate)
        if chrome_path:
            return chrome_path
    raise FileNotFoundError("Google Chrome ou Chromium não encontrado no PATH.")
