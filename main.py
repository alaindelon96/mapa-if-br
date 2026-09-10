"""Ponto de entrada do projeto mapa-if-br.

Roda o pipeline completo — planilhas do BACEN -> mapa interativo — e é a camada
que conversa com quem está no terminal: monta a linha de comando, liga os logs
e traduz uma falha em diagnóstico acionável, em vez de despejar um traceback.

A ordem das etapas e o que cada uma grava ficam em `src.pipeline`, que é quem
de fato as encadeia. A divisão é essa de propósito: `src.pipeline` sabe o que
rodar, `main` sabe como reportar.

Uso::

    python main.py                    # o Brasil inteiro (padrão), 27 UFs
    python main.py --ufs Sul          # só a Região Sul, bem mais rápido
    python main.py --ufs SP,RJ,MG     # um recorte qualquer
    python main.py --sem-cache-malha  # rebaixa a malha da API do IBGE
    python main.py -v                 # inclui o log de nível DEBUG

Códigos de saída: 0 sucesso, 1 falha de execução, 2 erro de uso (do argparse),
130 interrompido com Ctrl+C — os valores que um agendador ou um script de CI
espera encontrar.
"""

from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from pathlib import Path

import requests

from src import config, pipeline

_LOGGER = logging.getLogger("main")

# --------------------------------------------------------------------------- #
# Códigos de saída
# --------------------------------------------------------------------------- #

#: Tudo certo, mapa gravado.
SAIDA_OK = 0

#: Alguma etapa falhou — vale para erro previsto e não previsto.
SAIDA_ERRO = 1

#: Interrompido com Ctrl+C. 128 + SIGINT(2), a convenção de shell: um agendador
#: distingue "eu mandei parar" de "quebrou sozinho".
SAIDA_INTERROMPIDO = 130


# --------------------------------------------------------------------------- #
# Diagnósticos
# --------------------------------------------------------------------------- #

#: O que fazer quando o TLS recusa o certificado do IBGE.
#:
#: É de longe a falha de rede mais comum aqui, e a única cuja causa não é o
#: IBGE: antivírus e proxy corporativo reemitem os certificados com uma
#: autoridade raiz própria, instalada no repositório do Windows, onde o
#: `certifi` não olha. Ver `src.rede`.
_ACAO_TLS = (
    "A verificação do certificado falhou — quase sempre antivírus ou proxy\n"
    "  que inspeciona HTTPS, e não o IBGE fora do ar. O que fazer:\n"
    "    1. `pip install truststore` (já está no requirements.txt); ou\n"
    "    2. aponte REQUESTS_CA_BUNDLE para o certificado raiz dessa ferramenta."
)

#: Saída comum a toda falha do lado do IBGE, seja silêncio ou status de erro.
#:
#: Fica separada da frase que descreve o sintoma porque as duas situações
#: pedem o mesmo remédio mas não admitem a mesma descrição: dizer "não
#: respondeu" depois de exibir um HTTP 503 é contradizer a linha anterior.
_ACAO_IBGE_TENTE_DEPOIS = (
    "O que fazer:\n"
    "    1. confira a conexão e tente de novo em alguns minutos;\n"
    "    2. se a malha já estiver em data/raw/, rode SEM --sem-cache-malha para\n"
    "       reaproveitá-la e não depender da API nesta execução."
)

#: O que fazer quando o IBGE não responde.
_ACAO_IBGE_FORA = (
    "O servidor do IBGE não respondeu. Ele costuma ficar lento ou indisponível\n"
    f"  em horário comercial. {_ACAO_IBGE_TENTE_DEPOIS}"
)


def _causa_de_rede(erro: BaseException) -> requests.RequestException | None:
    """Procura uma falha de rede na cadeia de causas de `erro`.

    Percorrer a cadeia, em vez de olhar só o tipo de cima, é o que permite
    reconhecer a falha depois que um módulo a reembrulhou: `ibge_malha`
    converte `requests.exceptions.SSLError` em `RuntimeError` com uma mensagem
    melhor, e `src.pipeline` embrulha tudo de novo em `EtapaFalhou`. Sem a
    varredura, essas duas camadas apagariam a informação de que a falha foi de
    rede, e o erro cairia no diagnóstico genérico.

    Args:
        erro: a exceção capturada no topo.

    Returns:
        A primeira exceção do `requests` encontrada na cadeia, ou ``None`` se a
        falha não for de rede.
    """
    vistas: set[int] = set()
    atual: BaseException | None = erro
    while atual is not None and id(atual) not in vistas:
        vistas.add(id(atual))
        if isinstance(atual, requests.RequestException):
            return atual
        # `__cause__` é o `raise ... from ...` explícito; `__context__` pega o
        # reembrulho feito dentro de um `except` sem `from`.
        atual = atual.__cause__ or atual.__context__
    return None


def _diagnosticar(erro: Exception) -> str:
    """Traduz a causa de uma falha na instrução de como sair dela.

    Cobre as quatro classes que aparecem na prática — rede do IBGE, planilha de
    entrada ausente, cache do CNEFE corrompido e malha degradada. O resto cai no
    ramo genérico, que assume não saber e diz como obter o traceback.

    Args:
        erro: a exceção que interrompeu o pipeline (normalmente uma
            `src.pipeline.EtapaFalhou`).

    Returns:
        O texto do bloco "O QUE FAZER", já formatado.
    """
    de_rede = _causa_de_rede(erro)
    if de_rede is not None:
        if isinstance(de_rede, requests.exceptions.SSLError):
            return _ACAO_TLS
        if isinstance(de_rede, requests.exceptions.HTTPError):
            resposta = de_rede.response
            status = (
                "um status de erro"
                if resposta is None
                else f"HTTP {resposta.status_code}"
            )
            return (
                f"O IBGE respondeu {status} em vez do dado pedido.\n"
                f"  {_ACAO_IBGE_TENTE_DEPOIS}"
            )
        # ConnectionError, ReadTimeout, ConnectTimeout e o resto da família.
        return _ACAO_IBGE_FORA

    causa = erro.__cause__ or erro

    if isinstance(causa, FileNotFoundError):
        return (
            f"Falta um arquivo de entrada: {causa}\n"
            f"  As duas planilhas do BACEN não são baixadas pelo pipeline; elas\n"
            f"  precisam estar em data/raw/ com os nomes\n"
            f"  {config.ARQUIVO_AGENCIAS.name} e {config.ARQUIVO_POSTOS.name}.\n"
            "  Baixe-as em\n"
            "  https://www.bcb.gov.br/estabilidadefinanceira/agenciasconsorcio"
        )

    if isinstance(causa, zipfile.BadZipFile):
        return (
            "Um ZIP do CNEFE em data/raw/cnefe/ está corrompido — em geral,\n"
            "  download interrompido. Rode `python main.py --sem-cache-cnefe`\n"
            "  para baixá-lo de novo (um arquivo por UF do recorte)."
        )

    if isinstance(causa, ValueError):
        # As barreiras de `pipeline._obter_malha` e as conferências de
        # `agregacao` já dizem o que houve E o que fazer, na própria mensagem
        # exibida em CAUSA. Repeti-la aqui só faria a tela mostrar o mesmo
        # parágrafo duas vezes seguidas.
        return (
            "Uma conferência de integridade barrou a execução — a mensagem em\n"
            "  CAUSA, acima, traz o que divergiu e como corrigir. A barreira é\n"
            "  proposital: seguir adiante sobrescreveria os artefatos bons por\n"
            "  uma versão degradada, sem nenhuma etapa falhando."
        )

    return (
        f"Erro não previsto ({type(causa).__name__}): {causa}\n"
        "  Rode de novo com `python main.py -v` para ver o traceback completo."
    )


def _relatar_falha(erro: Exception) -> None:
    """Imprime o bloco de falha: onde quebrou, por quê e o que fazer.

    Vai no `stderr` para não se misturar ao relatório das etapas, que sai no
    `stdout` — quem redireciona a saída para um arquivo continua vendo o erro
    na tela.

    Args:
        erro: a exceção que interrompeu o pipeline.
    """
    onde = (
        f"ETAPA {erro.numero}/{pipeline.TOTAL_ETAPAS} — {erro.titulo}"
        if isinstance(erro, pipeline.EtapaFalhou)
        else "Pipeline"
    )
    causa = erro.__cause__ or erro

    print(file=sys.stderr)
    print("!" * 78, file=sys.stderr)
    print(f"! PIPELINE INTERROMPIDO em {onde}", file=sys.stderr)
    print("!" * 78, file=sys.stderr)
    print(f"\nCAUSA: {type(causa).__name__}: {causa}\n", file=sys.stderr)
    print(f"O QUE FAZER:\n  {_diagnosticar(erro)}\n", file=sys.stderr)
    print(
        "Os artefatos das etapas anteriores continuam em data/processed/: o\n"
        "pipeline não apaga o que já gravou, então recomeçar não perde trabalho.",
        file=sys.stderr,
    )


# --------------------------------------------------------------------------- #
# Linha de comando
# --------------------------------------------------------------------------- #


def _recorte_do_argumento(texto: str) -> list[str]:
    """Adapta `config.interpretar_recorte` ao contrato de tipo do argparse.

    A leitura do texto é do `config`, que é quem conhece as regiões e as
    siglas. O que se acrescenta aqui é só a conversão da exceção: com
    `argparse.ArgumentTypeError` o argparse imprime o uso e sai com código 2,
    enquanto um `ValueError` cru viraria traceback na tela.

    Args:
        texto: o valor cru vindo da linha de comando.

    Returns:
        A lista de siglas, ainda não normalizada.

    Raises:
        argparse.ArgumentTypeError: se o texto não render nenhuma sigla.
    """
    try:
        return config.interpretar_recorte(texto)
    except ValueError as erro:
        raise argparse.ArgumentTypeError(str(erro)) from erro


def montar_parser() -> argparse.ArgumentParser:
    """Monta o parser da linha de comando.

    Returns:
        O parser, com o recorte territorial, as duas chaves de cache e o
        `--verbose`.
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Gera o mapa de cobertura de cooperativas de crédito e dos cinco "
            "maiores bancos. O recorte territorial padrão é o Brasil inteiro "
            "(27 UFs); use --ufs para recortá-lo."
        ),
        epilog=(
            "Sem argumentos, tudo que já foi baixado é reaproveitado de data/raw/ "
            "e só o processamento roda de novo. Cada recorte grava os artefatos "
            "com nome próprio, então trocar de recorte não sobrescreve o cache "
            "do anterior."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ufs",
        type=_recorte_do_argumento,
        default=list(config.RECORTE_PADRAO),
        metavar="RECORTE",
        help=(
            "recorte territorial: BR para as 27 UFs, o nome de uma região "
            "(Norte, Nordeste, Centro-Oeste, Sudeste, Sul) ou siglas separadas "
            "por vírgula (ex.: RS,SC,PR). Padrão: o Brasil inteiro. Um recorte "
            "menor baixa menos CNEFE e roda em uma fração do tempo."
        ),
    )
    parser.add_argument(
        "--sem-cache-malha",
        action="store_true",
        help=(
            "rebaixa a malha municipal da API do IBGE em vez de reaproveitar o "
            "GeoJSON de data/raw/. Necessário só quando a divisão territorial muda."
        ),
    )
    parser.add_argument(
        "--sem-cache-cnefe",
        action="store_true",
        help=(
            "rebaixa os ZIP do CNEFE (um por UF do recorte) em vez de "
            "reaproveitar os de data/raw/cnefe/. Necessário só para se "
            "recuperar de cache corrompido."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="inclui o log de nível DEBUG e o traceback completo em caso de falha.",
    )
    return parser


def configurar_logs(verbose: bool) -> None:
    """Liga o logging para que os avisos das etapas cheguem ao terminal.

    Os módulos do pipeline reportam por `logging` o que não interrompe a
    execução mas muda o resultado — ponto sem código IBGE, bandeira fora do
    de-para, município sem população, malha reprojetada. Sem esta chamada o
    nível INFO não é emitido, e esses avisos somem justamente na execução de
    ponta a ponta, que é onde mais importam.

    O destino é o `stdout`, e não o `stderr` padrão do `logging`, para que os
    avisos apareçam intercalados com o relatório das etapas na ordem em que
    aconteceram; o `stderr` fica reservado para o bloco de falha.

    Args:
        verbose: quando ``True``, desce o nível para DEBUG.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _anunciar_inicio(args: argparse.Namespace) -> None:
    """Imprime o cabeçalho da execução, com as decisões que valem para ela.

    O que está em cache decide se a execução leva um minuto ou vinte, e se ela
    depende ou não da rede. Deixar isso no topo responde de antemão à dúvida
    mais comum de quem acompanha a saída: "travou ou está baixando?".

    Args:
        args: os argumentos já processados.
    """
    malha = "rebaixar da API" if args.sem_cache_malha else "usar cache de data/raw/"

    # Quantos ZIP do CNEFE faltam, e o que isso custa. Deixar essa conta na
    # tela ANTES de começar passou a importar quando o padrão virou o país
    # inteiro: quem roda `python main.py` pela primeira vez dispara ~3,9 GB de
    # download sem ter pedido nada, e merece saber disso enquanto ainda dá
    # tempo de interromper e pedir um recorte menor.
    faltando = [
        uf
        for uf in config.SIGLAS_UF
        if not (config.DIR_CNEFE / f"{config.CODIGO_UF[uf]}_{uf}.zip").exists()
    ]
    if args.sem_cache_cnefe:
        cnefe = f"rebaixar TODAS as {len(config.SIGLAS_UF)} UF(s)"
    elif faltando:
        cnefe = (
            f"baixar {len(faltando)} de {len(config.SIGLAS_UF)} UF(s) "
            f"[{', '.join(faltando)}]"
        )
    else:
        cnefe = "usar cache de data/raw/cnefe/"
    print("=" * 78)
    print("mapa-if-br — cobertura de cooperativas de crédito e dos 5 maiores bancos")
    print(
        f"{config.nome_do_recorte()} — dados do BACEN de {config.DATA_DADOS}"
    )
    print("=" * 78)
    print(f"  Recorte       : {len(config.SIGLAS_UF)} UF(s) "
          f"[{', '.join(config.SIGLAS_UF)}]")
    print(f"  Malha do IBGE : {malha}")
    print(f"  CNEFE         : {cnefe}")
    print(f"  Log           : {'DEBUG' if args.verbose else 'INFO'}")
    if faltando and not args.sem_cache_cnefe:
        print(
            f"\n  ATENÇÃO: faltam {len(faltando)} arquivo(s) do CNEFE em cache. "
            "São centenas de MB\n"
            "  a alguns GB de download, uma vez só. Para um recorte menor e "
            "bem mais rápido,\n"
            "  interrompa e rode `python main.py --ufs Sul` (3 UFs, ~580 MB)."
        )


def _anunciar_fim(destino: Path) -> None:
    """Imprime o encerramento, com todos os artefatos gravados.

    Args:
        destino: o caminho do HTML gerado pela última etapa.
    """
    print("=" * 78)
    print("PIPELINE CONCLUÍDO")
    print("=" * 78)
    for rotulo, caminho in (
        ("Dataset categorizado", config.arquivo_if_categorizado()),
        ("Agregado por município", config.arquivo_agregado_municipio()),
        ("Pontos geocodificados", config.arquivo_pontos_geocodificados()),
        ("Mapa interativo", destino),
    ):
        print(f"  {rotulo:<24} {caminho}")
    print(f"\nAbra o mapa no navegador: {destino}")


def main(argv: list[str] | None = None) -> int:
    """Roda o pipeline completo e devolve o código de saída do processo.

    Args:
        argv: argumentos da linha de comando; ``None`` usa `sys.argv`.

    Returns:
        `SAIDA_OK`, `SAIDA_ERRO` ou `SAIDA_INTERROMPIDO`.
    """
    parser = montar_parser()
    args = parser.parse_args(argv)

    # O recorte é fixado ANTES de qualquer etapa, e antes até do anúncio de
    # início: é dele que saem os nomes dos artefatos e as UFs que cada módulo
    # enxerga. Ver `config.SIGLAS_UF`.
    try:
        config.definir_recorte(args.ufs)
    except ValueError as erro:
        parser.error(str(erro))

    configurar_logs(args.verbose)
    _anunciar_inicio(args)

    try:
        destino = pipeline.executar(
            usar_cache_malha=not args.sem_cache_malha,
            usar_cache_cnefe=not args.sem_cache_cnefe,
        )
    except KeyboardInterrupt:
        # Não é falha: alguém apertou Ctrl+C. Sem este ramo o traceback do
        # KeyboardInterrupt vaza na tela como se algo tivesse quebrado.
        print("\nInterrompido pelo usuário.", file=sys.stderr)
        return SAIDA_INTERROMPIDO
    except Exception as erro:
        _relatar_falha(erro)
        if args.verbose:
            # O diagnóstico acima cobre o caso conhecido; o traceback é para o
            # desconhecido, e só sob pedido, para não enterrar a instrução.
            _LOGGER.exception("Traceback completo:")
        return SAIDA_ERRO

    _anunciar_fim(destino)
    return SAIDA_OK


if __name__ == "__main__":
    sys.exit(main())
