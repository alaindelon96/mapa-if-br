"""Malha territorial dos municípios do recorte, via APIs do IBGE.

Baixa a malha das UFs de `config.SIGLAS_UF` pela API de Malhas
(https://servicodados.ibge.gov.br/api/docs/malhas), grava o GeoJSON em
``data/raw/malha_municipios_<recorte>.geojson`` e devolve um GeoDataFrame em
EPSG:4326 com o código do município já padronizado como string de 7 dígitos —
o mesmo formato de `municipio_ibge` produzido pelo ETL do BACEN, para que o
join entre as duas bases seja direto.

A API responde POR UF, então o recorte não é um filtro aplicado depois: ele
decide quantas chamadas são feitas. Um recorte nacional são 27 respostas
concatenadas num só ``FeatureCollection``.

Opcionalmente enriquece a malha com o nome oficial do município (API de
Localidades) e a população estimada mais recente (agregado SIDRA 6579).

Uso (a partir da raiz do projeto, com o venv ativo)::

    python -m src.ibge_malha

Saída: ``data/raw/malha_municipios_<recorte>.geojson``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src import config, rede
from src.etl_bacen import padronizar_municipio_ibge

_LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Nomes de coluna
# --------------------------------------------------------------------------- #

#: Nomes já vistos para a coluna de código do município em malhas do IBGE, em
#: ordem de preferência.
#:
#: A API v3 de Malhas devolve hoje uma única propriedade por feição,
#: ``codarea`` (verificado nas três UFs). Os demais nomes cobrem as malhas
#: distribuídas em shapefile/GeoPackage pelo portal de downloads do IBGE, que
#: usam ``CD_MUN`` (a partir de 2020) ou ``CD_GEOCMU`` (censos anteriores) — a
#: função aceita as duas origens sem alteração de código.
CANDIDATOS_CODIGO_MUNICIPIO = [
    "codarea",
    "CD_MUN",
    "CD_GEOCMU",
    "GEOCODIGO",
    "geocodigo",
    "CD_MUNICIPIO",
]

#: Colunas do GeoDataFrame devolvido por `obter_malha`, nesta ordem.
COLUNAS_MALHA = [
    "municipio_ibge",
    "municipio_nome",
    "uf",
    "regiao",
    "populacao",
    "populacao_ano",
    "geometry",
]

#: Código IBGE da UF (dois primeiros dígitos do código de município) -> sigla.
#:
#: A tabela é a das 27 UFs, e não a do recorte: ela serve para LER o código de
#: qualquer feição que chegue, inclusive uma que não devesse estar ali. Restringi-la
#: ao recorte faria um município fora dele virar `uf` nula em silêncio, em vez de
#: aparecer no aviso de `padronizar_codigo_malha`.
_UF_POR_CODIGO = {str(codigo): sigla for sigla, codigo in config.CODIGO_UF.items()}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def criar_sessao_http(tentativas: int = 4, backoff: float = 1.5) -> requests.Session:
    """Monta uma `requests.Session` com retentativa automática.

    As APIs do IBGE respondem 429/502/503 sob carga com alguma frequência, e a
    malha é um download grande o bastante para não valer a pena refazer o
    pipeline inteiro por causa de uma falha transitória.

    Args:
        tentativas: número total de tentativas por requisição (a primeira mais
            as retentativas).
        backoff: fator de espera exponencial entre tentativas, em segundos.

    Returns:
        Sessão HTTP configurada; use como *context manager* para fechá-la.
    """
    rede.usar_certificados_do_sistema()
    politica = Retry(
        total=tentativas,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    sessao = requests.Session()
    sessao.mount("https://", HTTPAdapter(max_retries=politica))
    return sessao


def _obter_json(
    sessao: requests.Session,
    url: str,
    params: dict[str, str] | None = None,
    timeout: int = config.TIMEOUT_IBGE,
) -> object:
    """Faz um GET e devolve o JSON, traduzindo erros comuns de ambiente.

    Args:
        sessao: sessão criada por `criar_sessao_http`.
        url: URL completa do recurso.
        params: parâmetros de query string.
        timeout: timeout em segundos.

    Returns:
        O corpo da resposta já desserializado.

    Raises:
        RuntimeError: se a verificação TLS falhar. Em máquinas com antivírus ou
            proxy corporativo que interceptam HTTPS, o certificado apresentado
            não está no bundle do `certifi` e o erro cru do `ssl` não deixa
            claro o que fazer; a mensagem aponta a variável de ambiente que
            resolve.
        requests.HTTPError: se a resposta trouxer status de erro.
    """
    try:
        resposta = sessao.get(url, params=params, timeout=timeout)
    except requests.exceptions.SSLError as erro:
        raise RuntimeError(
            f"Falha na verificação TLS ao acessar {url}. Se esta máquina usa "
            "antivírus ou proxy que inspeciona HTTPS, aponte REQUESTS_CA_BUNDLE "
            "para o certificado raiz dele antes de rodar o pipeline."
        ) from erro

    resposta.raise_for_status()
    return resposta.json()


# --------------------------------------------------------------------------- #
# 1. Download da malha
# --------------------------------------------------------------------------- #


def baixar_malha_uf(
    uf: str,
    sessao: requests.Session,
    qualidade: str = config.QUALIDADE_MALHA,
) -> dict:
    """Baixa a malha municipal de uma UF como GeoJSON.

    Chama ``/api/v3/malhas/estados/{UF}`` com ``intrarregiao=municipio``, que
    devolve um polígono por município da UF em vez do contorno único do estado.

    Args:
        uf: sigla da unidade da federação (ex.: ``"RS"``).
        sessao: sessão criada por `criar_sessao_http`.
        qualidade: nível de generalização (``"minima"``, ``"intermediaria"`` ou
            ``"maxima"``).

    Returns:
        O ``FeatureCollection`` devolvido pela API.

    Raises:
        ValueError: se a resposta não for um ``FeatureCollection``, ou se vier
            sem feições — indicaria mudança de contrato da API.
    """
    colecao = _obter_json(
        sessao,
        f"{config.URL_IBGE_MALHAS}/estados/{uf}",
        params={
            "formato": "application/vnd.geo+json",
            "intrarregiao": "municipio",
            "qualidade": qualidade,
        },
    )

    if not isinstance(colecao, dict) or colecao.get("type") != "FeatureCollection":
        raise ValueError(
            f"Resposta inesperada da API de Malhas para {uf}: "
            f"esperado FeatureCollection, veio {type(colecao).__name__}."
        )

    feicoes = colecao.get("features") or []
    if not feicoes:
        raise ValueError(f"A API de Malhas devolveu 0 municípios para {uf}.")

    esperado = config.MUNICIPIOS_POR_UF.get(uf)
    if esperado is not None and len(feicoes) != esperado:
        # Não interrompe: a divisão territorial muda (raro, mas acontece). O
        # aviso existe para que a divergência apareça antes de virar buraco no mapa.
        _LOGGER.warning(
            "%s: a malha veio com %d municípios, mas MUNICIPIOS_POR_UF "
            "esperava %d. Confira se a divisão territorial mudou.",
            uf,
            len(feicoes),
            esperado,
        )
    else:
        _LOGGER.info("%s: %d municípios baixados.", uf, len(feicoes))

    return colecao


def baixar_malha(
    destino: Path | None = None,
    ufs: list[str] | None = None,
    qualidade: str = config.QUALIDADE_MALHA,
    usar_cache: bool = True,
) -> Path:
    """Baixa a malha do recorte e grava um único GeoJSON em ``data/raw/``.

    Uma resposta da API por UF, todas concatenadas em um só
    ``FeatureCollection``. As feições são gravadas exatamente como o IBGE as
    devolve (única propriedade: ``codarea``) — qualquer atributo derivado é
    acrescentado depois, no carregamento, para que o arquivo em ``data/raw/``
    continue sendo cópia fiel da fonte.

    O nome do arquivo carrega o slug do recorte, então a malha nacional e a do
    Sul convivem em cache sem uma sobrescrever a outra.

    Args:
        destino: caminho do ``.geojson`` de saída; ``None`` deriva do recorte.
        ufs: siglas a baixar; ``None`` usa o recorte ativo (`config.SIGLAS_UF`).
        qualidade: nível de generalização das geometrias.
        usar_cache: se ``True`` e o arquivo já existir, não rebaixa nada. Passe
            ``False`` para forçar a atualização da malha.

    Returns:
        O caminho do arquivo gravado (ou do cache reaproveitado).
    """
    ufs = config.recorte(ufs)
    destino = destino or config.arquivo_malha(ufs)

    if usar_cache and destino.exists():
        _LOGGER.info("Malha já existe em %s; download ignorado.", destino)
        return destino

    feicoes: list[dict] = []
    with criar_sessao_http() as sessao:
        for uf in ufs:
            colecao = baixar_malha_uf(uf, sessao=sessao, qualidade=qualidade)
            feicoes.extend(colecao["features"])

    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as arquivo:
        json.dump(
            {"type": "FeatureCollection", "features": feicoes},
            arquivo,
            ensure_ascii=False,
        )

    _LOGGER.info(
        "Malha de %s gravada em %s (%d municípios, %.1f MB, qualidade=%s).",
        config.nome_do_recorte(ufs),
        destino,
        len(feicoes),
        destino.stat().st_size / 1e6,
        qualidade,
    )
    return destino


# --------------------------------------------------------------------------- #
# 2. Carregamento como GeoDataFrame em EPSG:4326
# --------------------------------------------------------------------------- #


def carregar_malha(caminho: Path | None = None) -> gpd.GeoDataFrame:
    """Lê o GeoJSON da malha como GeoDataFrame em `config.CRS_GEOGRAFICO`.

    A API de Malhas devolve o GeoJSON sem membro ``crs``, o que pela RFC 7946
    significa CRS84 — lon/lat em WGS 84, equivalente ao EPSG:4326 usado no
    resto do projeto. Como o arquivo não declara isso explicitamente, o CRS é
    atribuído aqui quando vier vazio; se vier declarado e for outro, o
    GeoDataFrame é reprojetado em vez de ter o CRS sobrescrito.

    Args:
        caminho: caminho do ``.geojson``; ``None`` deriva do recorte ativo.

    Returns:
        GeoDataFrame em EPSG:4326.

    Raises:
        FileNotFoundError: se o arquivo não existir — rode `baixar_malha`.
    """
    caminho = caminho or config.arquivo_malha()
    if not caminho.exists():
        raise FileNotFoundError(
            f"Malha não encontrada: {caminho}. "
            "Rode `python -m src.ibge_malha` para baixá-la."
        )

    gdf = gpd.read_file(caminho)

    if gdf.crs is None:
        _LOGGER.debug("GeoJSON sem CRS declarado; assumindo CRS84/EPSG:4326.")
        gdf = gdf.set_crs(config.CRS_GEOGRAFICO)
    elif gdf.crs.to_string() != config.CRS_GEOGRAFICO:
        _LOGGER.info(
            "Reprojetando a malha de %s para %s.",
            gdf.crs.to_string(),
            config.CRS_GEOGRAFICO,
        )
        gdf = gdf.to_crs(config.CRS_GEOGRAFICO)

    return gdf


# --------------------------------------------------------------------------- #
# 3. Código do município como string de 7 dígitos
# --------------------------------------------------------------------------- #


def padronizar_codigo_malha(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Renomeia a coluna de código para `municipio_ibge` e a normaliza.

    Localiza a coluna de código entre `CANDIDATOS_CODIGO_MUNICIPIO` (a API v3
    entrega ``codarea``; os arquivos do portal de downloads, ``CD_MUN``),
    renomeia para ``municipio_ibge`` e delega a normalização a
    `etl_bacen.padronizar_municipio_ibge` — a MESMA função aplicada ao dataset
    do BACEN. É essa reutilização, e não uma segunda implementação equivalente,
    que garante que os dois lados do join tenham exatamente o mesmo formato:
    somente dígitos, com zeros à esquerda, 7 caracteres.

    Também deriva `uf` dos dois primeiros dígitos do código, evitando uma ida à
    API de Localidades só para saber a que estado cada polígono pertence.

    Args:
        gdf: malha lida por `carregar_malha`.

    Returns:
        Cópia do GeoDataFrame com `municipio_ibge` (string de 7 dígitos) e `uf`.

    Raises:
        KeyError: se nenhuma coluna candidata existir no arquivo.
        ValueError: se algum código não resultar em 7 dígitos, se houver código
            nulo, ou se houver município repetido — a malha é a chave do join e
            precisa ser unívoca.
    """
    origem = next(
        (coluna for coluna in CANDIDATOS_CODIGO_MUNICIPIO if coluna in gdf.columns),
        None,
    )
    if origem is None:
        raise KeyError(
            f"Nenhuma coluna de código de município encontrada. "
            f"Candidatas: {CANDIDATOS_CODIGO_MUNICIPIO!r}. "
            f"Colunas disponíveis: {sorted(gdf.columns)!r}"
        )

    resultado = gdf.rename(columns={origem: "municipio_ibge"}).copy()
    resultado = padronizar_municipio_ibge(resultado)

    nulos = int(resultado["municipio_ibge"].isna().sum())
    if nulos:
        raise ValueError(f"{nulos} feição(ões) da malha sem código de município.")

    duplicados = resultado["municipio_ibge"].duplicated()
    if duplicados.any():
        exemplos = resultado.loc[duplicados, "municipio_ibge"].unique()[:5].tolist()
        raise ValueError(
            f"{int(duplicados.sum())} código(s) de município repetido(s) na malha: "
            f"{exemplos!r}. O join por município exige chave única."
        )

    resultado["uf"] = (
        resultado["municipio_ibge"].str.slice(0, 2).map(_UF_POR_CODIGO).astype("string")
    )
    sem_uf = int(resultado["uf"].isna().sum())
    if sem_uf:
        _LOGGER.warning(
            "%d município(s) da malha têm código de UF desconhecido — `uf` "
            "ficou nula.",
            sem_uf,
        )

    # A região é derivada da UF, e aqui, porque este é o único lugar do projeto
    # em que a UF nasce. Deriva-la de novo mais adiante (na agregação, no mapa)
    # criaria duas tabelas UF -> região para manter em acordo.
    resultado["regiao"] = (
        resultado["uf"].map(config.REGIAO_POR_UF).astype("string")
    )

    return resultado


# --------------------------------------------------------------------------- #
# 4. Enriquecimento: nome oficial e população estimada
# --------------------------------------------------------------------------- #


def buscar_nomes_municipios(
    ufs: list[str] | None = None,
    sessao: requests.Session | None = None,
) -> pd.DataFrame:
    """Busca o nome oficial dos municípios na API de Localidades.

    Endpoint: ``/api/v1/localidades/estados/{UF}/municipios``.

    Args:
        ufs: siglas a consultar; ``None`` usa o recorte ativo.
        sessao: sessão HTTP a reutilizar; se omitida, uma é criada e fechada
            internamente.

    Returns:
        DataFrame com `municipio_ibge` (string de 7 dígitos) e `municipio_nome`.
        Vazio, com as colunas corretas, se a API falhar — a falha é registrada
        no log e o pipeline segue com o campo nulo.
    """
    ufs = config.recorte(ufs)
    propria = sessao is None
    sessao = sessao or criar_sessao_http()

    registros: list[dict[str, str]] = []
    try:
        for uf in ufs:
            try:
                municipios = _obter_json(
                    sessao, f"{config.URL_IBGE_LOCALIDADES}/estados/{uf}/municipios"
                )
            except (requests.RequestException, RuntimeError, ValueError) as erro:
                _LOGGER.warning(
                    "Nomes de municípios de %s indisponíveis (%s). "
                    "O campo `municipio_nome` ficará nulo nessa UF.",
                    uf,
                    erro,
                )
                continue

            registros.extend(
                {
                    "municipio_ibge": str(item["id"]).zfill(7),
                    "municipio_nome": item["nome"],
                }
                for item in municipios
            )
    finally:
        if propria:
            sessao.close()

    nomes = pd.DataFrame(registros, columns=["municipio_ibge", "municipio_nome"])
    nomes["municipio_ibge"] = nomes["municipio_ibge"].astype("string")
    nomes["municipio_nome"] = nomes["municipio_nome"].astype("string")

    _LOGGER.info("Nomes oficiais obtidos para %d municípios.", len(nomes))
    return nomes


def _para_inteiro_sidra(valor: object) -> int | None:
    """Converte um valor de série do SIDRA em inteiro, ou ``None``.

    O SIDRA sinaliza ausência de dado com códigos textuais no lugar do número:
    ``"-"`` (zero não significativo), ``".."`` (não se aplica), ``"..."`` (dado
    não disponível) e ``"X"`` (omitido por sigilo). Nenhum deles é população, e
    nenhum vira 0 aqui: viram nulo, para que o município apareça como "sem
    população informada" em vez de "população zero".

    Args:
        valor: valor cru da série.

    Returns:
        A população como ``int``, ou ``None`` se o valor não for numérico.
    """
    texto = str(valor).strip()
    return int(texto) if texto.isdigit() else None


def buscar_populacao_municipios(
    ufs: list[str] | None = None,
    sessao: requests.Session | None = None,
) -> pd.DataFrame:
    """Busca a população estimada mais recente por município (SIDRA 6579).

    Endpoint: ``/api/v3/agregados/6579/periodos/-1/variaveis/9324``, filtrado
    por ``localidades=N6[N3[<código da UF>]]`` — ou seja, todos os municípios
    (nível N6) dentro da UF (nível N3). O período ``-1`` pede sempre a última
    posição publicada, de modo que o ano não fica congelado no código; o ano
    efetivamente devolvido volta na coluna `populacao_ano`.

    Nenhum valor é estimado, interpolado ou preenchido localmente: o que a API
    não devolver fica nulo.

    Args:
        ufs: siglas a consultar; ``None`` usa o recorte ativo.
        sessao: sessão HTTP a reutilizar; se omitida, uma é criada e fechada
            internamente.

    Returns:
        DataFrame com `municipio_ibge`, `populacao` (``Int64``, nulo quando
        indisponível) e `populacao_ano` (``string``). Vazio, com as colunas
        corretas, se a API falhar.
    """
    ufs = config.recorte(ufs)
    propria = sessao is None
    sessao = sessao or criar_sessao_http()

    url = (
        f"{config.URL_IBGE_AGREGADOS}/{config.AGREGADO_IBGE_POPULACAO}"
        f"/periodos/-1/variaveis/{config.VARIAVEL_IBGE_POPULACAO}"
    )

    registros: list[dict[str, object]] = []
    try:
        for uf in ufs:
            codigo_uf = config.CODIGO_UF[uf]
            try:
                variaveis = _obter_json(
                    sessao, url, params={"localidades": f"N6[N3[{codigo_uf}]]"}
                )
            except (requests.RequestException, RuntimeError, ValueError) as erro:
                _LOGGER.warning(
                    "População de %s indisponível (%s). "
                    "O campo `populacao` ficará nulo nessa UF.",
                    uf,
                    erro,
                )
                continue

            for variavel in variaveis:
                for resultado in variavel.get("resultados", []):
                    for serie in resultado.get("series", []):
                        codigo = str(serie["localidade"]["id"]).zfill(7)
                        # A série vem como {"2025": "4251"}; com periodos/-1 há
                        # no máximo um par, mas o `max` deixa a escolha do ano
                        # explícita caso a API passe a devolver mais de um.
                        valores = serie.get("serie", {})
                        if not valores:
                            continue
                        ano = max(valores)
                        registros.append(
                            {
                                "municipio_ibge": codigo,
                                "populacao": _para_inteiro_sidra(valores[ano]),
                                "populacao_ano": ano,
                            }
                        )
    finally:
        if propria:
            sessao.close()

    populacao = pd.DataFrame(
        registros, columns=["municipio_ibge", "populacao", "populacao_ano"]
    )
    populacao["municipio_ibge"] = populacao["municipio_ibge"].astype("string")
    populacao["populacao"] = populacao["populacao"].astype("Int64")
    populacao["populacao_ano"] = populacao["populacao_ano"].astype("string")

    if len(populacao):
        anos = sorted(populacao["populacao_ano"].dropna().unique().tolist())
        _LOGGER.info(
            "População obtida para %d municípios (referência: %s).",
            int(populacao["populacao"].notna().sum()),
            ", ".join(anos),
        )
    return populacao


def enriquecer_malha(
    gdf: gpd.GeoDataFrame,
    nomes: pd.DataFrame | None = None,
    populacao: pd.DataFrame | None = None,
) -> gpd.GeoDataFrame:
    """Acrescenta nome oficial e população à malha, por `municipio_ibge`.

    Os merges são ``left`` sobre a malha: nenhum município some por falta de
    nome ou de população, e nenhum município entra que não exista na malha.

    Args:
        gdf: malha com `municipio_ibge` já padronizado.
        nomes: saída de `buscar_nomes_municipios`; ``None`` deixa
            `municipio_nome` nula.
        populacao: saída de `buscar_populacao_municipios`; ``None`` deixa
            `populacao` e `populacao_ano` nulas.

    Returns:
        GeoDataFrame com as colunas de `COLUNAS_MALHA`.
    """
    resultado = gdf.copy()

    if nomes is not None and len(nomes):
        resultado = resultado.merge(nomes, on="municipio_ibge", how="left")
    else:
        resultado["municipio_nome"] = pd.Series(
            pd.NA, index=resultado.index, dtype="string"
        )

    if populacao is not None and len(populacao):
        resultado = resultado.merge(populacao, on="municipio_ibge", how="left")
    else:
        resultado["populacao"] = pd.Series(
            pd.NA, index=resultado.index, dtype="Int64"
        )
        resultado["populacao_ano"] = pd.Series(
            pd.NA, index=resultado.index, dtype="string"
        )

    sem_nome = int(resultado["municipio_nome"].isna().sum())
    sem_populacao = int(resultado["populacao"].isna().sum())

    if sem_nome:
        _LOGGER.warning(
            "%d de %d municípios ficaram SEM nome oficial da API de Localidades.",
            sem_nome,
            len(resultado),
        )
    if sem_populacao:
        _LOGGER.warning(
            "%d de %d municípios ficaram SEM população informada pelo IBGE "
            "(campo nulo — nenhum valor foi estimado localmente).",
            sem_populacao,
            len(resultado),
        )
    else:
        _LOGGER.info("Todos os %d municípios têm população.", len(resultado))

    return resultado[COLUNAS_MALHA]


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #


def obter_malha(
    caminho: Path | None = None,
    qualidade: str = config.QUALIDADE_MALHA,
    usar_cache: bool = True,
    com_atributos: bool = True,
    ufs: list[str] | None = None,
) -> gpd.GeoDataFrame:
    """Devolve a malha municipal do recorte, pronta para o join com o BACEN.

    Encadeia as quatro etapas do módulo:

    1. baixa a malha de cada UF do recorte pela API de Malhas do IBGE e grava
       ``data/raw/malha_municipios_<recorte>.geojson`` (`baixar_malha`);
    2. carrega o GeoJSON como GeoDataFrame em EPSG:4326 (`carregar_malha`);
    3. padroniza o código do município como string de 7 dígitos, com a mesma
       função usada no ETL do BACEN (`padronizar_codigo_malha`);
    4. opcionalmente busca nome oficial e população estimada mais recente nas
       APIs de Localidades e de Agregados (`enriquecer_malha`).

    A etapa 4 é tolerante a falha: se a API não responder ou não trouxer o
    valor de um município, o campo fica nulo e o total de municípios sem
    população é registrado como aviso no log — nenhum número é inventado.

    Args:
        caminho: destino/origem do GeoJSON em ``data/raw/``; ``None`` deriva do
            recorte.
        qualidade: nível de generalização das geometrias (``"minima"``,
            ``"intermediaria"``, ``"maxima"``).
        usar_cache: reaproveita o GeoJSON já baixado; ``False`` força novo
            download.
        com_atributos: se ``False``, pula as chamadas às APIs de Localidades e
            Agregados e devolve `municipio_nome`, `populacao` e
            `populacao_ano` nulas — útil para rodar sem rede.
        ufs: recorte explícito; ``None`` usa o ativo (`config.SIGLAS_UF`).

    Returns:
        GeoDataFrame em EPSG:4326 com as colunas de `COLUNAS_MALHA`, ordenado
        por `municipio_ibge`.
    """
    ufs = config.recorte(ufs)
    caminho = caminho or config.arquivo_malha(ufs)

    baixar_malha(
        destino=caminho, ufs=ufs, qualidade=qualidade, usar_cache=usar_cache
    )

    gdf = carregar_malha(caminho)
    gdf = padronizar_codigo_malha(gdf)

    nomes = populacao = None
    if com_atributos:
        with criar_sessao_http() as sessao:
            nomes = buscar_nomes_municipios(ufs=ufs, sessao=sessao)
            populacao = buscar_populacao_municipios(ufs=ufs, sessao=sessao)

    malha = enriquecer_malha(gdf, nomes=nomes, populacao=populacao)
    return malha.sort_values("municipio_ibge").reset_index(drop=True)


def imprimir_resumo(malha: gpd.GeoDataFrame) -> None:
    """Imprime o resumo da malha para conferência manual.

    Args:
        malha: saída de `obter_malha`.
    """
    print("=" * 78)
    print(f"RESUMO — {config.arquivo_malha().relative_to(config.BASE_DIR)}")
    print("=" * 78)
    print(f"Recorte: {config.nome_do_recorte()}")
    print(f"Municípios: {len(malha)}")
    print(f"CRS: {malha.crs.to_string()}\n")

    print("-- municípios por região --")
    print(malha["regiao"].value_counts().to_string(), "\n")

    print("-- municípios por UF --")
    print(malha["uf"].value_counts().to_string(), "\n")

    sem_populacao = int(malha["populacao"].isna().sum())
    anos = sorted(malha["populacao_ano"].dropna().unique().tolist())
    print("-- população --")
    print(f"Referência IBGE: {', '.join(anos) if anos else 'indisponível'}")
    print(f"Sem população informada: {sem_populacao} município(s)")
    if not sem_populacao:
        total = f"{int(malha['populacao'].sum()):,}".replace(",", ".")
        print(f"População total do recorte: {total}")
    print()


def executar(usar_cache: bool = True) -> gpd.GeoDataFrame:
    """Roda o fluxo completo do módulo e imprime o resumo.

    Args:
        usar_cache: reaproveita o GeoJSON já presente em ``data/raw/``.

    Returns:
        A malha enriquecida.
    """
    malha = obter_malha(usar_cache=usar_cache)
    imprimir_resumo(malha)
    return malha


def main() -> None:
    """Ponto de entrada para ``python -m src.ibge_malha``."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s %(name)s: %(message)s"
    )
    executar()


if __name__ == "__main__":
    main()
