"""Verificação de links externos (sites oficiais e fontes das normas)."""

import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .verificacoes import Relatorio

URL_PATTERN = re.compile(r"https?://[^\s|)<>\"'`]+")
TRAILING_PUNCTUATION = ".,;:"
# Navegador genérico: vários sites públicos recusam clientes sem User-Agent de navegador.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
REQUEST_TIMEOUT_SECONDS = 30
MAX_PARALLEL_REQUESTS = 8
BLOCKED_FOR_BOTS_STATUSES = {401, 403, 429}


@dataclass
class LinkResult:
    url: str
    status: int | None
    final_url: str | None = None
    error: str | None = None


def extract_urls(markdown_files: list[Path]) -> list[str]:
    urls = set()
    for markdown_file in markdown_files:
        for url in URL_PATTERN.findall(markdown_file.read_text(encoding="utf-8")):
            urls.add(url.rstrip(TRAILING_PUNCTUATION))
    return sorted(urls)


def verificar_links(markdown_files: list[Path]) -> Relatorio:
    nomes = ", ".join(path.name for path in markdown_files)
    relatorio = Relatorio(f"Links externos ({nomes})")
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as executor:
        results = list(executor.map(check_url, extract_urls(markdown_files)))
    for result in results:
        classify(result, relatorio)
    return relatorio


def check_url(url: str) -> LinkResult:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return LinkResult(url, response.status, response.geturl())
    except urllib.error.HTTPError as http_error:
        return LinkResult(url, http_error.code, error=str(http_error.reason))
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as network_error:
        return LinkResult(url, None, error=str(getattr(network_error, "reason", network_error)))


def classify(result: LinkResult, relatorio: Relatorio) -> None:
    if result.status is None:
        relatorio.erros.append(f"sem resposta: {result.url} ({result.error})")
    elif result.status in BLOCKED_FOR_BOTS_STATUSES:
        relatorio.avisos.append(f"HTTP {result.status} (bloqueia automação? abrir no navegador): {result.url}")
    elif result.status >= 400:
        relatorio.erros.append(f"HTTP {result.status}: {result.url}")
    elif result.final_url and result.final_url.rstrip("/") != result.url.rstrip("/"):
        relatorio.avisos.append(f"redireciona: {result.url} -> {result.final_url}")
