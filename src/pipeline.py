"""Orquestração do pipeline completo: das planilhas do BACEN ao mapa.

Ordem das etapas, com o artefato que cada uma grava:

1. `etl_bacen`  — lê as duas planilhas do BACEN, recorta RS/SC/PR e as
   instituições-alvo, classifica `categoria_if` e `sub_categoria`
   -> ``data/processed/if_sul_categorizado.parquet``
2. `ibge_malha` — malha municipal do Sul pela API do IBGE, com nome oficial e
   população estimada
   -> ``data/raw/malha_municipios_sul.geojson`` (reaproveitada do cache)
3. `agregacao`  — junta os dois pelo código IBGE, uma linha por município
   -> ``data/processed/agregado_municipio.parquet``
4. `cnefe`      — resolve a coordenada de cada ponto de atendimento contra o
   Cadastro Nacional de Endereços do Censo 2022
   -> ``data/processed/pontos_geocodificados.parquet``
5. `mapa`       — coroplético por município + camadas de ponto em dois níveis
   -> ``output/mapa_if_sul.html``

Cada etapa também roda sozinha (``python -m src.etl_bacen``, ``-m src.agregacao``,
``-m src.cnefe``, ``-m src.mapa``), o que é o caminho normal durante o
desenvolvimento. Este módulo existe para a execução de ponta a ponta, via
``python main.py`` ou ``python -m src.pipeline``.

A etapa 4 depende de ~580 MB de arquivos do CNEFE em ``data/raw/cnefe/``. Eles
são baixados na primeira execução e reaproveitados em todas as seguintes — o
CNEFE é um produto do Censo 2022 e não muda.

Por que a malha é uma etapa explícita aqui, se `agregacao.executar` já sabe
buscá-la sozinha: assim ela é baixada/carregada UMA vez e passada adiante, o
resumo da malha aparece no lugar certo da saída, e a decisão de usar ou não o
cache fica visível no topo do pipeline em vez de escondida num parâmetro
default de outro módulo.

Nota sobre os módulos-esqueleto — `ingest`, `normalize`, `geo`, `mapping` e
`export` são o andaime genérico do início do projeto e NÃO fazem parte desta
cadeia: o que eles previam acabou implementado de forma específica em
`etl_bacen`, `ibge_malha`, `agregacao` e `mapa`. Continuam no repositório
porque `tests/test_estrutura.py` os cobre, mas ninguém em produção os importa.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

import geopandas as gpd

from src import agregacao, cnefe, config, etl_bacen, ibge_malha, mapa

_LOGGER = logging.getLogger(__name__)

#: Quantidade de etapas, só para numerar os cabeçalhos ("ETAPA 2/5").
TOTAL_ETAPAS = 5


def _abrir_etapa(numero: int, titulo: str) -> float:
    """Imprime o cabeçalho de uma etapa e devolve o instante de início.

    A saída das quatro etapas é longa (diagnósticos do ETL, cobertura da
    agregação, resumo do mapa). Sem uma marca visual entre elas, quem roda
    ``python main.py`` não distingue o relatório de uma do da seguinte.

    Args:
        numero: posição da etapa, de 1 a `TOTAL_ETAPAS`.
        titulo: nome da etapa.

    Returns:
        O valor de `time.perf_counter` no início da etapa.
    """
    print()
    print("#" * 78)
    print(f"# ETAPA {numero}/{TOTAL_ETAPAS} — {titulo}")
    print("#" * 78)
    return time.perf_counter()


class EtapaFalhou(RuntimeError):
    """Erro em uma etapa, carregando qual etapa foi.

    Existe para que `main` possa dizer "a ETAPA 2/5 falhou" sem manter uma
    cópia da lista de etapas: quem conhece a ordem é este módulo, e quem
    conversa com o usuário é o `main`. A causa original fica em `__cause__`
    intacta — `main` a inspeciona para escolher o diagnóstico (falha de rede
    no IBGE, planilha ausente, malha degradada).

    `KeyboardInterrupt` NÃO é embrulhada: ela deriva de `BaseException`, e o
    ``except Exception`` que produz esta exceção não a alcança. Ctrl+C
    continua subindo limpo até o `main`.

    Attributes:
        numero: posição da etapa, de 1 a `TOTAL_ETAPAS`.
        titulo: nome da etapa, como aparece no cabeçalho.
    """

    def __init__(self, numero: int, titulo: str, causa: Exception) -> None:
        super().__init__(f"ETAPA {numero}/{TOTAL_ETAPAS} ({titulo}) falhou: {causa}")
        self.numero = numero
        self.titulo = titulo


def _rodar_etapa[T](
    numero: int,
    titulo: str,
    rotulo: str,
    acao: Callable[[], T],
    duracoes: dict[str, float],
) -> T:
    """Roda uma etapa cronometrada, marcando de quem é a falha.

    Args:
        numero: posição da etapa, de 1 a `TOTAL_ETAPAS`.
        titulo: nome exibido no cabeçalho.
        rotulo: chave curta da etapa no relatório de tempos.
        acao: a chamada da etapa, já com seus argumentos.
        duracoes: acumulador ``{rótulo: segundos}``, escrito no lugar.

    Returns:
        O que `acao` devolveu.

    Raises:
        EtapaFalhou: qualquer erro da etapa, com a causa original em
            ``__cause__``.
    """
    marco = _abrir_etapa(numero, titulo)
    try:
        resultado = acao()
    except Exception as erro:
        raise EtapaFalhou(numero, titulo, erro) from erro
    duracoes[rotulo] = time.perf_counter() - marco
    return resultado


def _imprimir_tempos(duracoes: dict[str, float], total: float) -> None:
    """Imprime quanto cada etapa levou.

    Args:
        duracoes: ``{rótulo da etapa: segundos}``, na ordem de execução.
        total: duração total do pipeline, em segundos.
    """
    print("=" * 78)
    print("PIPELINE — tempo por etapa")
    print("=" * 78)
    for rotulo, segundos in duracoes.items():
        print(f"   {rotulo:<34} {segundos:>7.1f}s")
    print(f"   {'TOTAL':<34} {total:>7.1f}s\n")


def executar(usar_cache_malha: bool = True, usar_cache_cnefe: bool = True) -> Path:
    """Roda o pipeline completo e devolve o caminho do mapa gerado.

    Encadeia as cinco etapas descritas no topo do módulo, na ordem, imprimindo
    o relatório de cada uma. A cadeia é sequencial de verdade: cada etapa lê o
    artefato que a anterior gravou, então rodar tudo de uma vez é a única forma
    de garantir que os quatro arquivos são da mesma safra — é exatamente isso
    que `tests.test_pipeline.test_agregado_nao_e_mais_antigo_que_o_dataset`
    cobra comparando as datas de gravação.

    Args:
        usar_cache_malha: quando ``True`` (padrão), reaproveita o GeoJSON já
            baixado em ``data/raw/``. Passe ``False`` para forçar uma consulta
            nova à API de Malhas do IBGE — necessário só quando a divisão
            territorial muda, e caro: são os três estados em qualidade
            intermediária, com o servidor do IBGE lento em horário comercial.
        usar_cache_cnefe: quando ``True`` (padrão), reaproveita os ZIP do CNEFE
            de ``data/raw/cnefe/``. Passe ``False`` para baixar os 580 MB de
            novo — necessário se o IBGE publicar uma revisão do cadastro, ou
            para se recuperar de um arquivo corrompido em cache sem ter de
            apagá-lo à mão.

    Returns:
        O caminho do HTML gravado (``output/mapa_if_sul.html``).

    Raises:
        EtapaFalhou: se qualquer etapa falhar. A causa original — planilha do
            BACEN ausente, API do IBGE fora, malha degradada — fica em
            ``__cause__``, e é dela que `main` tira o diagnóstico.
    """
    inicio = time.perf_counter()
    duracoes: dict[str, float] = {}

    _rodar_etapa(
        1,
        "ETL BACEN — agências e postos de RS/SC/PR",
        "1. ETL BACEN",
        etl_bacen.executar,
        duracoes,
    )
    malha = _rodar_etapa(
        2,
        "Malha municipal do IBGE",
        "2. Malha do IBGE",
        lambda: _obter_malha(usar_cache=usar_cache_malha),
        duracoes,
    )
    _rodar_etapa(
        3,
        "Agregação por município",
        "3. Agregação",
        lambda: agregacao.executar(malha=malha),
        duracoes,
    )
    _rodar_etapa(
        4,
        "Geocodificação dos pontos pelo CNEFE",
        "4. Geocodificação",
        lambda: cnefe.executar(usar_cache=usar_cache_cnefe),
        duracoes,
    )
    destino = _rodar_etapa(
        5, "Mapa interativo", "5. Mapa", mapa.gera_mapa, duracoes
    )

    print()
    _imprimir_tempos(duracoes, time.perf_counter() - inicio)
    return destino


#: Instrução repetida nos erros de malha degradada.
#:
#: A causa de longe mais comum de a API do IBGE falhar aqui não é o IBGE estar
#: fora do ar: é antivírus ou proxy corporativo inspecionando HTTPS, o que
#: quebra a verificação do certificado e derruba TODAS as chamadas de uma vez.
_DICA_TLS = (
    "Causa mais provável: falha de TLS por antivírus/proxy que inspeciona "
    "HTTPS — nesse caso o log acima traz `CERTIFICATE_VERIFY_FAILED`. "
    "Aponte REQUESTS_CA_BUNDLE para o certificado raiz dessa ferramenta e "
    "rode de novo."
)


def _obter_malha(usar_cache: bool) -> gpd.GeoDataFrame:
    """Carrega a malha municipal do Sul e recusa uma malha degradada.

    As conferências são aqui, e não dentro de `ibge_malha`, porque a tolerância
    a falha daquele módulo é deliberada e correta para uso exploratório
    (``python -m src.ibge_malha`` devolve o que conseguiu buscar). O que não
    pode acontecer é uma execução de ponta a ponta SOBRESCREVER os artefatos
    bons com uma versão empobrecida: `enriquecer_malha` apenas registra um
    aviso quando a API não responde e devolve `municipio_nome` e `populacao`
    nulos, o pipeline seguiria em frente, e o resultado seria um mapa com
    "<NA>/PR" no título de cada popup e "dado indisponível" nos 1.191
    municípios — sem nenhuma etapa falhando. Daí a barreira ser antes da
    gravação, e não uma inspeção do resultado.

    Três conferências, da mais estrutural para a mais tolerante:

    1. cobertura por UF, contra `config.MUNICIPIOS_POR_UF_SUL` — malha faltando
       município vira buraco no coroplético;
    2. `municipio_nome`, que é exigido: sem ele o popup não identifica o
       município. A API de Localidades responde por UF, então um nome faltando
       significa uma UF inteira perdida, nunca uma lacuna do cadastro;
    3. `populacao`, que é opcional por natureza — o mapa já sabe mostrar
       "dado indisponível" caso a caso. Só falha se estiver nula em TODOS os
       municípios, que é assinatura de API fora, não de lacuna de dado.

    Args:
        usar_cache: reaproveita o GeoJSON de ``data/raw/``.

    Returns:
        A malha enriquecida.

    Raises:
        ValueError: se a malha estiver incompleta ou sem enriquecimento.
    """
    malha = ibge_malha.executar(usar_cache=usar_cache)

    por_uf = malha["uf"].value_counts().to_dict()
    if por_uf != config.MUNICIPIOS_POR_UF_SUL:
        raise ValueError(
            f"Malha incompleta: {por_uf} != {config.MUNICIPIOS_POR_UF_SUL}. "
            "Rode de novo com `usar_cache_malha=False` para baixar a malha "
            "outra vez da API do IBGE."
        )

    sem_nome = int(malha["municipio_nome"].isna().sum())
    if sem_nome:
        ufs_afetadas = sorted(malha.loc[malha["municipio_nome"].isna(), "uf"].unique())
        raise ValueError(
            f"{sem_nome} de {len(malha)} municípios sem `municipio_nome` "
            f"(UFs: {ufs_afetadas}). A API de Localidades do IBGE não "
            f"respondeu, e seguir daqui gravaria um agregado sem nome de "
            f"município por cima do atual. {_DICA_TLS}"
        )

    sem_populacao = int(malha["populacao"].isna().sum())
    if sem_populacao == len(malha):
        raise ValueError(
            f"Nenhum dos {len(malha)} municípios tem população: a API de "
            f"Agregados do IBGE não respondeu. Seguir daqui gravaria "
            f'"dado indisponível" em todos os popups do mapa. {_DICA_TLS}'
        )
    if sem_populacao:
        # Lacuna parcial é aceitável: o popup do mapa trata caso a caso.
        _LOGGER.warning(
            "%d de %d municípios sem população; o mapa mostrará "
            "'dado indisponível' neles.",
            sem_populacao,
            len(malha),
        )

    return malha


def main() -> None:
    """Ponto de entrada para ``python -m src.pipeline``."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s %(name)s: %(message)s"
    )
    destino = executar()
    print(f"Mapa gerado em: {destino}")


if __name__ == "__main__":
    main()
