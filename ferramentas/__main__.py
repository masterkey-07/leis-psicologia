"""Linha de comando: python3 -m ferramentas <comando>."""

import argparse
import sys

from . import repositorio as repo
from . import verificacoes

DEFAULT_SEARCH_LIMIT = 30


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m ferramentas", description=__doc__)
    commands = parser.add_subparsers(required=True, metavar="comando")

    verify = commands.add_parser("verificar", help="checa seleção, INDICE.md, manual e (se houver) o acervo")
    add_corpus_option(verify)
    verify.add_argument("--sem-acervo", action="store_true", help="pula a comparação com o acervo de origem")
    verify.set_defaults(handler=run_verify)

    links = commands.add_parser("links", help="testa os links externos de REFERENCIAS.md e do manual")
    links.add_argument("--indice", action="store_true", help="inclui as ~700 fontes do INDICE.md (lento)")
    links.set_defaults(handler=run_links)

    sync = commands.add_parser("sincronizar", help="atualiza normas/ com as versões novas do acervo")
    add_corpus_option(sync)
    sync.add_argument("--aplicar", action="store_true", help="copia os arquivos (sem isso, só lista)")
    sync.set_defaults(handler=run_sync)

    search = commands.add_parser("buscar", help="procura um termo nas normas selecionadas")
    search.add_argument("termo")
    search.add_argument("--categoria", help="filtra por parte do nome da categoria")
    search.add_argument("--limite", type=int, default=DEFAULT_SEARCH_LIMIT)
    search.set_defaults(handler=run_search)

    pdf = commands.add_parser("pdf", help="gera manual/manual-clinica-psicologia-sjc.pdf")
    pdf.set_defaults(handler=run_pdf)

    capture = commands.add_parser("capturar", help="baixa o conteúdo dos sites de REFERENCIAS.md para referencias/")
    capture.add_argument("--so", metavar="TRECHO", help="captura só as referências cujo nome ou URL contém TRECHO")
    capture.set_defaults(handler=run_capture)
    return parser


def add_corpus_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--acervo",
        help=f"caminho do clone de ctresb/leis (padrão: ${repo.CORPUS_ENV_VAR} ou {repo.DEFAULT_CORPUS_DIR})",
    )


def run_verify(args) -> int:
    relatorios = [
        verificacoes.verificar_selecao(),
        verificacoes.verificar_manual(),
        verificacoes.verificar_markdown_interno(),
    ]
    if not args.sem_acervo:
        relatorios.append(verificacoes.verificar_integridade(repo.corpus_dir(args.acervo)))
    return print_reports(relatorios)


def run_links(args) -> int:
    from .links import verificar_links

    files = [repo.REFERENCES_FILE, repo.MANUAL_FILE] + ([repo.INDEX_FILE] if args.indice else [])
    return print_reports([verificar_links(files)])


def run_sync(args) -> int:
    from .manutencao import sincronizar

    acervo = repo.corpus_dir(args.acervo)
    if not acervo.is_dir():
        print(f"Acervo não encontrado: {acervo}", file=sys.stderr)
        return 1
    outdated = sincronizar(acervo, args.aplicar)
    verb = "Atualizado" if args.aplicar else "Desatualizado"
    for norm in outdated:
        print(f"{verb}: {norm.path}")
    if not outdated:
        print("normas/ já está idêntico ao acervo.")
    elif args.aplicar:
        print("Rode `python3 -m ferramentas verificar` e ajuste INDICE.md (ex.: coluna Revogada).")
    else:
        print("Use --aplicar para copiar.")
    return 0


def run_search(args) -> int:
    from .manutencao import buscar

    hits = buscar(args.termo, args.categoria)
    for hit in hits[: args.limite]:
        print(f"{hit.occurrences:4d}  [{hit.norm.category}] {hit.title} (revogada: {hit.revoked})")
        print(f"      normas/{hit.norm.path}")
    print(f"\n{len(hits)} norma(s) contêm '{args.termo}'.")
    return 0


def run_pdf(_args) -> int:
    from .pdf import gerar_pdf

    print(f"PDF gerado: {gerar_pdf()}")
    return 0


def run_capture(args) -> int:
    from .capturar import capturar_referencias

    captures = capturar_referencias(args.so)
    failures = [capture for capture in captures if not capture.ok]
    print(f"\n{len(captures) - len(failures)} capturada(s), {len(failures)} falha(s).")
    return 0


def print_reports(relatorios: list[verificacoes.Relatorio]) -> int:
    for relatorio in relatorios:
        relatorio.imprimir()
    return 0 if all(relatorio.ok for relatorio in relatorios) else 1


if __name__ == "__main__":
    sys.exit(main())
