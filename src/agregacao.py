"""Agregação dos pontos de atendimento por município.

Junta o dataset categorizado do BACEN
(``data/processed/if_<recorte>_categorizado.parquet``) à malha municipal do IBGE
e produz uma linha por município do recorte, com a contagem de pontos por
`categoria_if` e por `sub_categoria`, mais a população.

O join é DIRETO pelo código IBGE do município — não é *spatial join*. Os dois
motivos: (a) o BACEN já publica o código IBGE de cada ponto de atendimento, que
é a informação oficial de localização; (b) as planilhas do BACEN não trazem
lat/lon, então não há ponto para localizar dentro de um polígono. Um *spatial
join* aqui só acrescentaria erro de fronteira sem ganho de informação.

Uso (a partir da raiz do projeto, com o venv ativo)::

    python -m src.agregacao

Saída: ``data/processed/agregado_municipio_<recorte>.parquet``.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src import config, ibge_malha
from src.etl_bacen import (
    CATEGORIA_BANCO,
    CATEGORIA_COOPERATIVA,
    SUB_CATEGORIA_COOP_INDEFINIDA,
)

_LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# De-para sub_categoria -> sufixo da coluna
# --------------------------------------------------------------------------- #

#: `sub_categoria` do ETL -> sufixo usado no nome da coluna wide.
#:
#: Cobre TODAS as sub_categorias produzidas por `etl_bacen` na safra 202606,
#: não só as bandeiras principais. Isso é deliberado: com o conjunto completo,
#: a soma das colunas por bandeira reconcilia exatamente com `total_geral`, o
#: que é verificado em `_conferir_totais`. Se ficassem de fora, a diferença
#: entre o total e a soma das partes seria silenciosa.
#:
#: Sub_categorias novas (uma bandeira que apareça em safra futura) NÃO quebram
#: a agregação: `_sufixo_coluna` gera um sufixo a partir do próprio rótulo e o
#: caso é registrado no log, para que este de-para seja atualizado.
SUFIXO_POR_SUB_CATEGORIA = {
    # Cooperativas
    "Sicredi": "sicredi",
    "Sicoob": "sicoob",
    "Cresol": "cresol",
    "Ailos": "ailos",
    "Unicred": "unicred",
    "Uniprime": "uniprime",
    "Sulcredi": "sulcredi",
    "Credicoamo": "credicoamo",
    "Outra Cooperativa": "outra_coop",
    # Bancos
    "Banco do Brasil": "bb",
    "Bradesco": "bradesco",
    "Itaú": "itau",
    "Caixa": "caixa",
    "Santander": "santander",
}

#: Ordem das colunas de bandeira na tabela final: cooperativas primeiro (na
#: ordem em que aparecem no de-para), depois os cinco bancos.
ORDEM_SUB_CATEGORIAS = list(SUFIXO_POR_SUB_CATEGORIA)

#: Colunas de identificação do município, antes das contagens.
#:
#: `regiao` vem junto de `uf`, derivada uma vez em `ibge_malha` — ela é o que
#: permite ao mapa recortar por região no navegador sem uma segunda tabela
#: UF -> região embarcada no HTML.
COLUNAS_IDENTIFICACAO = [
    "municipio_ibge",
    "municipio_nome",
    "uf",
    "regiao",
    "populacao",
    "populacao_ano",
]

#: Colunas de totalização, logo após a identificação.
COLUNAS_TOTAIS = ["total_geral", "total_cooperativas", "total_bancos"]


def _sufixo_coluna(sub_categoria: str) -> str:
    """Devolve o sufixo de coluna para uma `sub_categoria`.

    Usa `SUFIXO_POR_SUB_CATEGORIA` quando a sub_categoria é conhecida. Para
    rótulos novos, deriva um sufixo do próprio texto (minúsculas, sem acentos,
    espaços viram ``_``) — assim uma bandeira inédita vira uma coluna em vez de
    sumir da tabela.

    Args:
        sub_categoria: rótulo produzido por `etl_bacen.classificar_sub_categoria`.

    Returns:
        O sufixo, sem o prefixo ``total_``.
    """
    conhecido = SUFIXO_POR_SUB_CATEGORIA.get(sub_categoria)
    if conhecido is not None:
        return conhecido

    decomposto = unicodedata.normalize("NFKD", str(sub_categoria))
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


# --------------------------------------------------------------------------- #
# 1. Carregamento
# --------------------------------------------------------------------------- #


def carregar_pontos(caminho: Path | None = None) -> pd.DataFrame:
    """Lê o dataset categorizado do BACEN.

    Args:
        caminho: caminho do ``.parquet`` produzido por `etl_bacen`; ``None``
            deriva do recorte ativo.

    Returns:
        DataFrame com uma linha por ponto de atendimento.

    Raises:
        FileNotFoundError: se o arquivo não existir — rode `python -m src.etl_bacen`.
        KeyError: se faltar alguma coluna exigida pela agregação.
    """
    caminho = caminho or config.arquivo_if_categorizado()
    if not caminho.exists():
        raise FileNotFoundError(
            f"Dataset não encontrado: {caminho}. "
            "Rode `python -m src.etl_bacen` para gerá-lo."
        )

    pontos = pd.read_parquet(caminho)

    exigidas = {"municipio_ibge", "categoria_if", "sub_categoria"}
    faltantes = exigidas - set(pontos.columns)
    if faltantes:
        raise KeyError(
            f"Colunas ausentes em {caminho.name}: {sorted(faltantes)!r}. "
            f"Disponíveis: {sorted(pontos.columns)!r}"
        )

    sem_codigo = int(pontos["municipio_ibge"].isna().sum())
    if sem_codigo:
        _LOGGER.warning(
            "%d ponto(s) sem `municipio_ibge` foram descartados da agregação — "
            "sem código não há como atribuí-los a um município.",
            sem_codigo,
        )
        pontos = pontos[pontos["municipio_ibge"].notna()]

    _LOGGER.info(
        "%d pontos de atendimento carregados, em %d municípios distintos.",
        len(pontos),
        pontos["municipio_ibge"].nunique(),
    )
    return pontos.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 2. Contagem por município x categoria x sub_categoria
# --------------------------------------------------------------------------- #


def contar_pontos(pontos: pd.DataFrame) -> pd.DataFrame:
    """Conta os pontos por município, `categoria_if` e `sub_categoria`.

    Formato longo, uma linha por combinação existente — é a tabela intermediária
    que alimenta a pivotagem e serve para conferir a contagem sem depender do
    layout wide.

    Args:
        pontos: saída de `carregar_pontos`.

    Returns:
        DataFrame com `municipio_ibge`, `categoria_if`, `sub_categoria` e
        `pontos` (``int64``).
    """
    contagem = (
        pontos.groupby(
            ["municipio_ibge", "categoria_if", "sub_categoria"], dropna=False
        )
        .size()
        .reset_index(name="pontos")
    )
    contagem["pontos"] = contagem["pontos"].astype("int64")
    return contagem


def pivotar_contagens(contagem: pd.DataFrame) -> pd.DataFrame:
    """Converte a contagem longa na tabela wide de totais por município.

    Gera, para cada município presente na contagem:

    * ``total_cooperativas`` e ``total_bancos`` — a partir de `categoria_if`;
    * ``total_geral`` — a soma das duas;
    * uma coluna ``total_<bandeira>`` por `sub_categoria` (ver
      `SUFIXO_POR_SUB_CATEGORIA`).

    As colunas de bandeira são emitidas para TODAS as sub_categorias do de-para,
    mesmo as que não aparecem em nenhum município da safra: um esquema de saída
    estável evita que o mapa e as análises quebrem entre safras por causa de uma
    coluna que sumiu.

    Args:
        contagem: saída de `contar_pontos`.

    Returns:
        DataFrame indexado por posição, com `municipio_ibge` e as colunas de
        contagem em ``int64``.
    """
    desconhecidas = sorted(
        set(contagem["sub_categoria"].dropna().unique()) - set(SUFIXO_POR_SUB_CATEGORIA)
    )
    if desconhecidas:
        _LOGGER.warning(
            "sub_categoria(s) fora de SUFIXO_POR_SUB_CATEGORIA: %r. "
            "Colunas foram geradas automaticamente; atualize o de-para.",
            desconhecidas,
        )

    # --- Totais por categoria_if ------------------------------------------- #
    por_categoria = (
        contagem.pivot_table(
            index="municipio_ibge",
            columns="categoria_if",
            values="pontos",
            aggfunc="sum",
            fill_value=0,
            observed=False,
        )
        .rename(
            columns={
                CATEGORIA_COOPERATIVA: "total_cooperativas",
                CATEGORIA_BANCO: "total_bancos",
            }
        )
        .rename_axis(columns=None)
    )
    for coluna in ("total_cooperativas", "total_bancos"):
        if coluna not in por_categoria.columns:
            por_categoria[coluna] = 0

    por_categoria = por_categoria[["total_cooperativas", "total_bancos"]]
    por_categoria.insert(0, "total_geral", por_categoria.sum(axis=1))

    # --- Totais por sub_categoria ------------------------------------------ #
    por_sub = (
        contagem.pivot_table(
            index="municipio_ibge",
            columns="sub_categoria",
            values="pontos",
            aggfunc="sum",
            fill_value=0,
            observed=False,
        )
        .rename_axis(columns=None)
    )

    ordem = ORDEM_SUB_CATEGORIAS + [
        sub for sub in desconhecidas if sub not in ORDEM_SUB_CATEGORIAS
    ]
    por_sub = por_sub.reindex(columns=ordem, fill_value=0)
    por_sub.columns = [f"total_{_sufixo_coluna(sub)}" for sub in ordem]

    wide = por_categoria.join(por_sub, how="outer").fillna(0)
    wide = wide.astype("int64").reset_index()
    wide["municipio_ibge"] = wide["municipio_ibge"].astype("string")
    return wide


# --------------------------------------------------------------------------- #
# 3. Merge com a malha
# --------------------------------------------------------------------------- #


def juntar_com_malha(
    malha: gpd.GeoDataFrame,
    wide: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Junta as contagens à malha por `municipio_ibge`, mantendo todos os municípios.

    O merge é ``left`` COM A MALHA À ESQUERDA, e não o contrário: o resultado
    precisa ter uma linha para cada um dos municípios do Sul, inclusive os que
    não têm nenhum ponto no escopo filtrado, senão o mapa coroplético ficaria
    com buracos onde deveria mostrar zero. Os municípios sem ponto recebem 0 em
    todas as colunas de contagem.

    Args:
        malha: saída de `ibge_malha.obter_malha`.
        wide: saída de `pivotar_contagens`.

    Returns:
        GeoDataFrame com uma linha por município da malha, colunas na ordem
        `COLUNAS_IDENTIFICACAO` + `COLUNAS_TOTAIS` + bandeiras + ``geometry``.

    Raises:
        ValueError: se o merge alterar a quantidade de linhas da malha, o que
            indicaria chave duplicada em algum dos lados.
    """
    colunas_contagem = [c for c in wide.columns if c != "municipio_ibge"]

    agregado = malha.merge(wide, on="municipio_ibge", how="left")
    if len(agregado) != len(malha):
        raise ValueError(
            f"O merge alterou a contagem de linhas ({len(malha)} -> {len(agregado)}). "
            "Há código de município duplicado na malha ou nas contagens."
        )

    agregado[colunas_contagem] = (
        agregado[colunas_contagem].fillna(0).astype("int64")
    )

    ordenadas = COLUNAS_IDENTIFICACAO + COLUNAS_TOTAIS + [
        coluna for coluna in colunas_contagem if coluna not in COLUNAS_TOTAIS
    ]
    return agregado[ordenadas + ["geometry"]]


#: Nome da coluna que carrega, por município, quais marcas compõem a contagem
#: de "Outra Cooperativa".
COLUNA_DETALHE_OUTRAS = "outras_coops_detalhe"

#: Separador entre as marcas dentro da célula de detalhe.
SEPARADOR_DETALHE = " · "


def detalhar_outras_cooperativas(pontos: pd.DataFrame) -> pd.DataFrame:
    """Resume, por município, quais marcas formam a coluna "Outra Cooperativa".

    A contagem agregada diz que um município tem N pontos de "Outra
    Cooperativa", mas não diz de quem — e o rótulo, sozinho, sugere que a
    informação não existe. Ela existe: cada uma dessas linhas traz a marca
    escrita, capturada por `etl_bacen` em `marca_exibicao`. Esta função a traz
    para o nível do município, onde o popup consegue exibi-la.

    O resultado é TEXTO já formatado (``"Sisprime 3 · Credisis 1"``) e não uma
    coluna por marca: são 16 marcas, quase todas ausentes em quase todos os
    1.191 municípios, e uma coluna para cada encheria o agregado de zeros sem
    responder melhor a pergunta que o popup faz — "quais estão aqui".

    As marcas saem ordenadas da mais frequente para a menos, e o desempate é
    alfabético, para que a mesma composição gere sempre o mesmo texto.

    Args:
        pontos: dataset categorizado, com `marca_exibicao`.

    Returns:
        DataFrame com `municipio_ibge` e `outras_coops_detalhe`, uma linha por
        município que tenha ao menos um ponto de "Outra Cooperativa". Municípios
        sem nenhum ficam de fora — `juntar_detalhe_outras` os preenche com "".
    """
    if "marca_exibicao" not in pontos.columns:
        _LOGGER.warning(
            "`marca_exibicao` ausente no dataset categorizado; o popup do "
            "município não vai nomear as marcas de %r. Rode `python -m "
            "src.etl_bacen` para regerar o arquivo.",
            SUB_CATEGORIA_COOP_INDEFINIDA,
        )
        return pd.DataFrame(
            {"municipio_ibge": pd.Series(dtype="string"),
             COLUNA_DETALHE_OUTRAS: pd.Series(dtype="string")}
        )

    do_balde = pontos[pontos["sub_categoria"] == SUB_CATEGORIA_COOP_INDEFINIDA]
    if do_balde.empty:
        return pd.DataFrame(
            {"municipio_ibge": pd.Series(dtype="string"),
             COLUNA_DETALHE_OUTRAS: pd.Series(dtype="string")}
        )

    contagem = (
        do_balde.groupby(["municipio_ibge", "marca_exibicao"])
        .size()
        .rename("n")
        .reset_index()
    )
    contagem = contagem.sort_values(
        ["municipio_ibge", "n", "marca_exibicao"], ascending=[True, False, True]
    )

    def _juntar(grupo: pd.DataFrame) -> str:
        return SEPARADOR_DETALHE.join(
            f"{marca} {int(n)}" for marca, n in zip(grupo["marca_exibicao"], grupo["n"])
        )

    detalhe = (
        contagem.groupby("municipio_ibge", sort=False)
        .apply(_juntar, include_groups=False)
        .rename(COLUNA_DETALHE_OUTRAS)
        .reset_index()
    )
    _LOGGER.info(
        "Detalhamento de %r montado para %d municípios.",
        SUB_CATEGORIA_COOP_INDEFINIDA,
        len(detalhe),
    )
    return detalhe


def juntar_detalhe_outras(
    agregado: gpd.GeoDataFrame,
    detalhe: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Acrescenta ao agregado a coluna de detalhe de "Outra Cooperativa".

    Fica separada de `juntar_com_malha` porque aquela função converte TODAS as
    colunas trazidas do merge para ``int64`` — o detalhe é texto e seria
    quebrado por essa conversão.

    Args:
        agregado: saída de `juntar_com_malha`.
        detalhe: saída de `detalhar_outras_cooperativas`.

    Returns:
        O agregado com `outras_coops_detalhe` preenchida; municípios sem nenhum
        ponto de "Outra Cooperativa" recebem string vazia, nunca nulo, para que
        o popup não precise testar `NaN`.

    Raises:
        ValueError: se o merge alterar a quantidade de municípios.
    """
    antes = len(agregado)
    com_detalhe = agregado.merge(detalhe, on="municipio_ibge", how="left")
    if len(com_detalhe) != antes:
        raise ValueError(
            f"O merge do detalhe alterou a contagem de municípios "
            f"({antes} -> {len(com_detalhe)}). Há código duplicado no detalhe."
        )
    com_detalhe[COLUNA_DETALHE_OUTRAS] = (
        com_detalhe[COLUNA_DETALHE_OUTRAS].fillna("").astype("string")
    )
    return com_detalhe


def _conferir_totais(agregado: gpd.GeoDataFrame) -> None:
    """Valida a coerência aritmética da tabela wide.

    Confere que ``total_geral`` é igual à soma de cooperativas e bancos, e
    também à soma de todas as colunas de bandeira. A segunda igualdade só vale
    porque `SUFIXO_POR_SUB_CATEGORIA` cobre todas as sub_categorias; se alguém
    remover uma entrada do de-para, o erro aparece aqui em vez de virar um total
    silenciosamente errado no mapa.

    Args:
        agregado: saída de `juntar_com_malha`.

    Raises:
        ValueError: se alguma das duas somas divergir.
    """
    soma_categorias = agregado["total_cooperativas"] + agregado["total_bancos"]
    divergentes = agregado.loc[soma_categorias != agregado["total_geral"]]
    if len(divergentes):
        raise ValueError(
            f"{len(divergentes)} município(s) com total_geral != cooperativas + "
            f"bancos. Exemplos: {divergentes['municipio_ibge'].head().tolist()!r}"
        )

    colunas_bandeira = [
        coluna
        for coluna in agregado.columns
        if coluna.startswith("total_") and coluna not in COLUNAS_TOTAIS
    ]
    soma_bandeiras = agregado[colunas_bandeira].sum(axis=1)
    divergentes = agregado.loc[soma_bandeiras != agregado["total_geral"]]
    if len(divergentes):
        raise ValueError(
            f"{len(divergentes)} município(s) com total_geral != soma das colunas "
            f"por bandeira. Exemplos: "
            f"{divergentes['municipio_ibge'].head().tolist()!r}"
        )


# --------------------------------------------------------------------------- #
# 4. Cobertura: municípios sem nenhum ponto no escopo
# --------------------------------------------------------------------------- #


def relatar_cobertura(
    agregado: gpd.GeoDataFrame,
    pontos: pd.DataFrame,
    top_sem_atendimento: int = 10,
) -> dict[str, int]:
    """Reporta quantos municípios ficaram sem nenhum ponto no escopo filtrado.

    "Escopo filtrado" = cooperativas de crédito + os cinco bancos-alvo de
    `config.BANCOS_ALVO`. Um município contado aqui como "sem atendimento" pode
    perfeitamente ter agência de outra instituição: o zero é do recorte, não do
    sistema financeiro.

    Também verifica o caminho inverso — pontos cujo `municipio_ibge` não existe
    na malha. Isso não deveria acontecer (ambos os lados usam o código oficial
    do IBGE) e, se acontecer, significa ponto perdido na agregação, então é
    reportado como aviso destacado.

    Args:
        agregado: saída de `juntar_com_malha`.
        pontos: saída de `carregar_pontos`, para o cruzamento inverso.
        top_sem_atendimento: quantos municípios sem atendimento listar por UF.

    Returns:
        Dicionário com `municipios_malha`, `municipios_com_atendimento`,
        `municipios_sem_atendimento` e `pontos_fora_da_malha`.
    """
    sem_atendimento = agregado[agregado["total_geral"] == 0]
    codigos_malha = set(agregado["municipio_ibge"])
    fora_da_malha = pontos[~pontos["municipio_ibge"].isin(codigos_malha)]

    total = len(agregado)
    n_sem = len(sem_atendimento)
    pct = (n_sem / total * 100) if total else 0.0

    print("=" * 78)
    print("COBERTURA — municípios sem nenhum ponto no escopo filtrado")
    print("=" * 78)
    print(
        "Escopo: cooperativas de crédito + "
        f"{len(config.BANCOS_ALVO)} bancos-alvo (BB, Bradesco, Itaú, Caixa, "
        "Santander).\n"
    )
    print(f"Municípios na malha do recorte:    {total:>6}")
    print(f"Com ao menos 1 ponto:              {total - n_sem:>6}")
    print(f"SEM nenhum ponto no escopo:        {n_sem:>6}  ({pct:.1f}%)\n")

    if n_sem:
        print("-- sem atendimento, por UF --")
        resumo_uf = pd.DataFrame(
            {
                "municipios": agregado.groupby("uf", observed=False).size(),
                "sem_atendimento": sem_atendimento.groupby("uf", observed=False).size(),
            }
        ).fillna(0)
        resumo_uf["sem_atendimento"] = resumo_uf["sem_atendimento"].astype(int)
        resumo_uf["pct"] = (
            resumo_uf["sem_atendimento"] / resumo_uf["municipios"] * 100
        ).round(1)
        print(resumo_uf.to_string(), "\n")

        if sem_atendimento["populacao"].notna().any():
            populacao_sem = sem_atendimento["populacao"].dropna()
            print(
                f"População somada desses municípios: {int(populacao_sem.sum()):,}"
                .replace(",", ".")
                + f" (mediana de {int(populacao_sem.median()):,}".replace(",", ".")
                + " hab. por município)\n"
            )
            print(f"-- {top_sem_atendimento} maiores (por população), sem atendimento --")
            print(
                sem_atendimento.nlargest(top_sem_atendimento, "populacao")[
                    ["municipio_ibge", "municipio_nome", "uf", "populacao"]
                ].to_string(index=False),
                "\n",
            )

    if len(fora_da_malha):
        # Não é falha esperada: indicaria código IBGE do BACEN inexistente na
        # divisão territorial vigente (município novo, extinto ou digitado errado).
        _LOGGER.warning(
            "%d ponto(s) têm `municipio_ibge` que não existe na malha e ficaram "
            "FORA da agregação. Códigos: %r",
            len(fora_da_malha),
            sorted(fora_da_malha["municipio_ibge"].unique())[:10],
        )
        print(
            f"ATENÇÃO: {len(fora_da_malha)} ponto(s) não casaram com nenhum "
            "município da malha (ver log).\n"
        )
    else:
        print("Todos os pontos casaram com um município da malha.\n")

    return {
        "municipios_malha": total,
        "municipios_com_atendimento": total - n_sem,
        "municipios_sem_atendimento": n_sem,
        "pontos_fora_da_malha": len(fora_da_malha),
    }


# --------------------------------------------------------------------------- #
# 5. Persistência
# --------------------------------------------------------------------------- #


def salvar_parquet(
    agregado: gpd.GeoDataFrame,
    caminho: Path | None = None,
) -> Path:
    """Grava o agregado em Parquet, criando o diretório se necessário.

    A geometria do município vai junto (GeoParquet), para que a etapa de mapa
    leia um arquivo só. O arquivo continua legível por `pandas.read_parquet`,
    caso se queira apenas a tabela.

    Args:
        agregado: saída de `juntar_com_malha`.
        caminho: destino do ``.parquet``; ``None`` deriva do recorte ativo.

    Returns:
        O caminho gravado.
    """
    caminho = caminho or config.arquivo_agregado_municipio()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    agregado.to_parquet(caminho, index=False)
    return caminho


# --------------------------------------------------------------------------- #
# Resumo
# --------------------------------------------------------------------------- #


def imprimir_resumo(agregado: gpd.GeoDataFrame) -> None:
    """Imprime o resumo do agregado para conferência manual.

    Args:
        agregado: saída de `juntar_com_malha`.
    """
    colunas_totais = [c for c in agregado.columns if c.startswith("total_")]

    print("=" * 78)
    print(
        "RESUMO — "
        f"{config.arquivo_agregado_municipio().relative_to(config.BASE_DIR)}"
    )
    print("=" * 78)
    print(f"Recorte: {config.nome_do_recorte()}")
    print(f"Municípios: {len(agregado)}\n")

    print("-- soma de pontos por coluna --")
    print(agregado[colunas_totais].sum().to_string(), "\n")

    print("-- municípios com ao menos 1 ponto, por coluna --")
    print((agregado[colunas_totais] > 0).sum().to_string(), "\n")

    print("-- 10 municípios com mais pontos --")
    print(
        agregado.nlargest(10, "total_geral")[
            [
                "municipio_nome",
                "uf",
                "populacao",
                "total_geral",
                "total_cooperativas",
                "total_bancos",
            ]
        ].to_string(index=False),
        "\n",
    )


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #


def executar(
    caminho_pontos: Path | None = None,
    destino: Path | None = None,
    malha: gpd.GeoDataFrame | None = None,
    usar_cache_malha: bool = True,
) -> gpd.GeoDataFrame:
    """Roda a agregação completa, grava o Parquet e imprime os diagnósticos.

    Etapas: leitura do dataset categorizado -> contagem por município x
    categoria x sub_categoria -> pivotagem para o layout wide -> merge com a
    malha do IBGE (join direto por código, não espacial) -> conferência
    aritmética -> detalhe das marcas de "Outra Cooperativa" -> relatório de
    cobertura -> gravação.

    Args:
        caminho_pontos: ``.parquet`` produzido por `etl_bacen`; ``None`` deriva
            do recorte ativo.
        destino: destino do agregado; ``None`` deriva do recorte ativo.
        malha: malha já carregada; se ``None``, chama `ibge_malha.obter_malha`.
        usar_cache_malha: repassado a `ibge_malha.obter_malha` quando a malha
            não é fornecida.

    Returns:
        O agregado por município.
    """
    caminho_pontos = caminho_pontos or config.arquivo_if_categorizado()
    destino = destino or config.arquivo_agregado_municipio()

    pontos = carregar_pontos(caminho_pontos)

    if malha is None:
        malha = ibge_malha.obter_malha(usar_cache=usar_cache_malha)

    contagem = contar_pontos(pontos)
    wide = pivotar_contagens(contagem)
    agregado = juntar_com_malha(malha, wide)
    _conferir_totais(agregado)

    # Depois da conferência aritmética, de propósito: o detalhe é texto e não
    # participa de nenhuma soma, então entra quando os números já foram
    # validados e não há risco de ele interferir na checagem.
    agregado = juntar_detalhe_outras(
        agregado, detalhar_outras_cooperativas(pontos)
    )

    relatar_cobertura(agregado, pontos)
    imprimir_resumo(agregado)

    gravado = salvar_parquet(agregado, destino)
    print(f"Agregado gravado em: {gravado}")

    return agregado


def main() -> None:
    """Ponto de entrada para ``python -m src.agregacao``."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s %(name)s: %(message)s"
    )
    executar()


if __name__ == "__main__":
    main()
