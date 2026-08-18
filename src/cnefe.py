"""Geocodificação dos pontos de atendimento pelo CNEFE do IBGE.

Dá a cada linha de ``data/processed/if_sul_categorizado.parquet`` uma
coordenada (`latitude`, `longitude`) e o rótulo honesto do quanto ela vale
(`precisao`), gravando ``data/processed/pontos_geocodificados.parquet``.

Uso (a partir da raiz do projeto, com o venv ativo)::

    python -m src.cnefe

--------------------------------------------------------------------------
Por que o CNEFE, e não um serviço de geocodificação
--------------------------------------------------------------------------

A primeira versão do mapa punha todos os pontos de um município na mesma
coordenada — o ponto representativo do polígono —, e a alternativa examinada na
época foi geocodificar os 7.600 endereços no Nominatim/OSM. Foi descartada por
custo (1 req/s = ~2h por execução fria) e, principalmente, por qualidade: o
endereço publicado pelo BACEN vem abreviado e sem separador
("PCA.TIRADENTES,410"), o que rende acerto parcial e um mapa de precisão mista
sem o leitor saber qual ponto é qual.

O que mudou não foi a conclusão sobre o Nominatim, e sim o que se sabe da
fonte: o ETL passou a carregar três colunas que as planilhas do BACEN já
publicavam e que estavam sendo descartadas — **CEP (preenchido em 100% das
linhas)**, NÚMERO e BAIRRO (ver `etl_bacen.COLUNAS_ENDERECO_BACEN`). Com CEP em
mãos, o problema deixa de ser "interpretar um texto de endereço" e vira uma
junção por chave contra um cadastro que o IBGE publica inteiro:

* o **CNEFE do Censo 2022** traz TODOS os endereços do país com CEP,
  logradouro, número e LAT/LON medidas em campo;
* é distribuído em arquivo por UF — 580 MB para RS/SC/PR, baixados **uma vez**
  e reaproveitados de ``data/raw/cnefe/``;
* depois disso a geocodificação é uma junção local, sem limite de requisição,
  sem rede e sem variar de uma execução para outra;
* é o mesmo produtor da malha municipal que o projeto já usa, então o código de
  município casa exatamente, sem de-para.

--------------------------------------------------------------------------
Cadeia de precisão
--------------------------------------------------------------------------

Cada ponto é resolvido pela primeira regra que casar, da mais específica para a
mais frouxa. O nível que resolveu fica gravado em `precisao` e é mostrado no
popup — é ele que responde à objeção de "precisão mista": a mistura continua
existindo, mas deixa de ser invisível.

===========================  ==============================================
`precisao`                   Como foi resolvido
===========================  ==============================================
``PRECISAO_ENDERECO``        CEP específico + número, ou logradouro + número.
                             É o endereço do imóvel, medido no Censo.
``PRECISAO_LOGRADOURO``      CEP específico sem número (no Brasil urbano um
                             CEP costuma ser uma face de quadra), ou o
                             logradouro inteiro. Erro típico de dezenas a
                             poucas centenas de metros.
``PRECISAO_LOCALIDADE``      CEP geral do município (terminado em ``-000``,
                             ~58% das linhas) sem logradouro reconhecido:
                             mediana dos endereços daquele CEP, que cai no
                             miolo urbano por ser onde eles se concentram.
``PRECISAO_MUNICIPIO``       Nada casou: ponto representativo do polígono,
                             que é o comportamento antigo, agora restrito a
                             uma minoria explicitamente rotulada.
===========================  ==============================================

Medido na safra 202606 (ver o resumo impresso ao final da execução): a grande
maioria dos pontos fica em nível de logradouro ou melhor, e o fallback de
município fica na casa de poucos por cento.

--------------------------------------------------------------------------
Por que o casamento é por chave normalizada, e não por texto igual
--------------------------------------------------------------------------

As duas fontes escrevem o mesmo logradouro de formas diferentes: o BACEN grava
"R.GAL.SAMPAIO" e o CNEFE grava, em três colunas, ``RUA`` + ``GENERAL`` +
``SAMPAIO``. `chave_logradouro` reduz os dois lados à mesma forma canônica —
sem acento, sem pontuação, com as abreviaturas de patente e título expandidas
(`ABREVIATURAS`), sem o tipo do logradouro e sem artigos. O tipo sai de
propósito: o BACEN erra a classificação com frequência (grava ``RUA`` onde o
CNEFE tem ``AVENIDA``), e mantê-lo custaria mais casamentos perdidos do que os
raros pares "Rua XV" / "Avenida XV" que ele desambiguaria.

Nenhuma regra aqui é aproximada: ou a chave é idêntica, ou o ponto desce um
nível na cadeia. Não há casamento por similaridade — um "quase igual" que
acertasse 90% das vezes colocaria o ponto restante na rua errada sem deixar
rastro, e o nível de precisão registrado passaria a mentir.

--------------------------------------------------------------------------
Conferência espacial
--------------------------------------------------------------------------

Toda coordenada resolvida é conferida contra o polígono do próprio município
(`conferir_dentro_do_municipio`). Um CEP digitado errado na fonte pode casar
com um endereço do outro lado do estado, e esse é justamente o erro que passa
despercebido — o ponto fica plausível, só que na cidade errada. Quem cai fora
do próprio polígono é rebaixado para `PRECISAO_MUNICIPIO` e contabilizado no
resumo.
"""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.csv as pv
import requests
from unidecode import unidecode

from src import config, rede

_LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Níveis de precisão
# --------------------------------------------------------------------------- #

PRECISAO_ENDERECO = "endereço"
PRECISAO_LOGRADOURO = "logradouro"
PRECISAO_LOCALIDADE = "localidade"
PRECISAO_MUNICIPIO = "município"

#: Níveis do mais preciso para o mais frouxo — a ordem em que a cadeia de
#: casamento é tentada e a ordem em que o resumo é impresso.
ORDEM_PRECISAO = [
    PRECISAO_ENDERECO,
    PRECISAO_LOGRADOURO,
    PRECISAO_LOCALIDADE,
    PRECISAO_MUNICIPIO,
]

#: Texto mostrado ao leitor no popup de cada ponto, por nível.
DESCRICAO_PRECISAO = {
    PRECISAO_ENDERECO: "endereço do imóvel (CNEFE/IBGE, Censo 2022)",
    PRECISAO_LOGRADOURO: "logradouro — posição aproximada dentro da rua",
    PRECISAO_LOCALIDADE: "área urbana do município — logradouro não localizado",
    PRECISAO_MUNICIPIO: "município — endereço não localizado no CNEFE",
}

# --------------------------------------------------------------------------- #
# Normalização de logradouro
# --------------------------------------------------------------------------- #

#: Tipos de logradouro removidos do início da chave. Ver o cabeçalho do módulo
#: para o porquê de o tipo não participar do casamento.
TIPOS_LOGRADOURO = {
    "RUA", "AVENIDA", "PRACA", "RODOVIA", "ESTRADA", "TRAVESSA", "ALAMEDA",
    "LARGO", "LINHA", "BECO", "PASSAGEM", "VIELA", "SERVIDAO", "ACESSO",
    "CAMINHO", "MARGINAL", "VIA", "VIADUTO", "LOTEAMENTO", "CONDOMINIO",
}

#: Abreviaturas expandidas token a token antes da comparação.
#:
#: Cobre dois grupos: o tipo do logradouro ("R" -> "RUA"), que em seguida é
#: descartado, e — o que realmente importa — os títulos e patentes que o BACEN
#: abrevia dentro do nome e o CNEFE publica por extenso na coluna
#: ``NOM_TITULO_SEGLOGR``: "R.GAL.SAMPAIO" só encontra ``RUA GENERAL SAMPAIO``
#: porque "GAL" está aqui.
ABREVIATURAS = {
    # --- tipo do logradouro --------------------------------------------- #
    "R": "RUA", "RU": "RUA", "AV": "AVENIDA", "AVE": "AVENIDA",
    "AVEN": "AVENIDA", "PCA": "PRACA", "PC": "PRACA", "PRC": "PRACA",
    "ROD": "RODOVIA", "EST": "ESTRADA", "ESTR": "ESTRADA", "TV": "TRAVESSA",
    "TRAV": "TRAVESSA", "AL": "ALAMEDA", "LGO": "LARGO", "SERV": "SERVIDAO",
    "LOT": "LOTEAMENTO",
    # --- patentes e títulos --------------------------------------------- #
    "GAL": "GENERAL", "GEN": "GENERAL", "CEL": "CORONEL", "CAP": "CAPITAO",
    "MAL": "MARECHAL", "MAR": "MARECHAL", "ALM": "ALMIRANTE",
    "TEN": "TENENTE", "SGT": "SARGENTO", "BRIG": "BRIGADEIRO",
    "DR": "DOUTOR", "DRA": "DOUTORA", "PROF": "PROFESSOR",
    "PROFA": "PROFESSORA", "ENG": "ENGENHEIRO", "PE": "PADRE",
    "MON": "MONSENHOR", "SEN": "SENADOR", "DEP": "DEPUTADO",
    "VER": "VEREADOR", "PRES": "PRESIDENTE", "GOV": "GOVERNADOR",
    "PREF": "PREFEITO", "MIN": "MINISTRO", "CONS": "CONSELHEIRO",
    "DES": "DESEMBARGADOR", "BAR": "BARAO", "VISC": "VISCONDE",
    "CDE": "CONDE", "STA": "SANTA", "STO": "SANTO", "NSA": "NOSSA",
    "NS": "NOSSA", "EXP": "EXPEDICIONARIO", "IRM": "IRMAO", "JR": "JUNIOR",
}

#: Números escritos em algarismo romano pelo BACEN e por extenso pelo CNEFE.
#: "AV XV DE NOVEMBRO" vs. "AVENIDA QUINZE DE NOVEMBRO" é o caso mais comum de
#: logradouro central de cidade do Sul, então vale a tabelinha.
ROMANOS = {
    "II": "DOIS", "III": "TRES", "IV": "QUATRO", "V": "CINCO", "VI": "SEIS",
    "VII": "SETE", "VIII": "OITO", "IX": "NOVE", "X": "DEZ", "XI": "ONZE",
    "XII": "DOZE", "XIII": "TREZE", "XIV": "QUATORZE", "XV": "QUINZE",
    "XVI": "DEZESSEIS", "XVII": "DEZESSETE", "XVIII": "DEZOITO",
    "XIX": "DEZENOVE", "XX": "VINTE", "XXI": "VINTE E UM",
    "XXV": "VINTE E CINCO", "XXX": "TRINTA",
}

#: Artigos e preposições descartados: as duas fontes discordam livremente entre
#: "AVENIDA DA VINDIMA" e "AVENIDA VINDIMA".
ARTIGOS = {"DE", "DA", "DO", "DAS", "DOS", "E", "DEL", "D"}


def chave_logradouro(texto: object) -> str:
    """Reduz um nome de logradouro à forma canônica usada no casamento.

    Aplica, nesta ordem: remoção de acentos e caixa alta; troca de tudo que não
    é letra ou dígito por espaço; expansão de romanos e abreviaturas token a
    token; remoção do tipo do logradouro no início; remoção de artigos.

    Args:
        texto: o logradouro como veio da fonte, de qualquer um dos dois lados.

    Returns:
        A chave canônica, ex.: ``"GENERAL SAMPAIO"`` tanto para
        ``"R.GAL.SAMPAIO"`` (BACEN) quanto para ``"RUA GENERAL SAMPAIO"``
        (CNEFE). String vazia quando não sobra nada aproveitável.
    """
    if texto is None or (isinstance(texto, float) and np.isnan(texto)):
        return ""

    sem_acento = unidecode(str(texto)).upper()
    tokens = re.sub(r"[^A-Z0-9]+", " ", sem_acento).split()

    expandidos: list[str] = []
    for token in tokens:
        token = ROMANOS.get(token, token)
        token = ABREVIATURAS.get(token, token)
        # A expansão pode devolver mais de uma palavra ("XXI" -> "VINTE E UM").
        expandidos.extend(token.split())

    # Só o tipo no INÍCIO é descartado: "RUA DA PRACA" mantém o "PRACA".
    inicio = 0
    while inicio < len(expandidos) and expandidos[inicio] in TIPOS_LOGRADOURO:
        inicio += 1

    return " ".join(t for t in expandidos[inicio:] if t not in ARTIGOS)


def _chaves_de_serie(serie: pd.Series) -> pd.Series:
    """Aplica `chave_logradouro` a uma Series, calculando só os valores únicos.

    O CNEFE do Sul tem ~12 milhões de linhas e algumas centenas de milhares de
    nomes de logradouro distintos. Rodar a normalização por linha custaria
    minutos em laço Python; rodá-la sobre os únicos e reindexar custa segundos.

    Args:
        serie: coluna de nomes de logradouro.

    Returns:
        Series de chaves canônicas, alinhada com a entrada.
    """
    codigos, unicos = pd.factorize(serie, use_na_sentinel=False)
    tabela = np.array([chave_logradouro(valor) for valor in unicos], dtype=object)
    return pd.Series(tabela[codigos], index=serie.index)


def _somente_digitos(serie: pd.Series) -> pd.Series:
    """Devolve a Series como texto contendo apenas os dígitos de cada valor."""
    return serie.astype("string").fillna("").str.replace(r"\D", "", regex=True)


# --------------------------------------------------------------------------- #
# 1. Download do CNEFE
# --------------------------------------------------------------------------- #


def baixar_uf(uf: str, usar_cache: bool = True) -> Path:
    """Baixa (ou reaproveita) o ZIP do CNEFE de uma UF.

    Args:
        uf: sigla da UF, ex.: ``"SC"``.
        usar_cache: quando ``True``, devolve o arquivo já baixado sem
            reconsultar o IBGE. É o padrão porque o CNEFE é um produto do Censo
            2022 — ele não muda entre execuções.

    Returns:
        O caminho do ZIP em ``data/raw/cnefe/``.

    Raises:
        requests.HTTPError: se o FTP do IBGE recusar a requisição.
        requests.exceptions.SSLError: em máquina com antivírus/proxy que
            inspeciona HTTPS. É a mesma causa descrita em `pipeline._DICA_TLS`;
            a saída é apontar ``REQUESTS_CA_BUNDLE`` para o certificado raiz
            dessa ferramenta.
    """
    codigo_uf = config.CODIGO_UF_SUL[uf]
    nome = f"{codigo_uf}_{uf}.zip"
    destino = config.DIR_CNEFE / nome

    if usar_cache and destino.exists() and destino.stat().st_size > 0:
        tamanho_mb = destino.stat().st_size / 1024 / 1024
        _LOGGER.info("CNEFE %s: reaproveitando %s (%.0f MB).", uf, nome, tamanho_mb)
        return destino

    rede.usar_certificados_do_sistema()
    destino.parent.mkdir(parents=True, exist_ok=True)
    url = f"{config.URL_IBGE_CNEFE}/{nome}"
    _LOGGER.info("CNEFE %s: baixando %s ...", uf, url)

    # Gravação em arquivo temporário e rename ao final: interromper o download
    # no meio (Ctrl+C, queda de rede) deixaria um ZIP truncado no cache, e a
    # execução seguinte o aceitaria como bom.
    parcial = destino.with_suffix(".zip.parcial")
    with requests.get(url, stream=True, timeout=config.TIMEOUT_CNEFE) as resposta:
        resposta.raise_for_status()
        with parcial.open("wb") as arquivo:
            for pedaco in resposta.iter_content(chunk_size=1 << 20):
                arquivo.write(pedaco)
    parcial.replace(destino)

    _LOGGER.info(
        "CNEFE %s: %.0f MB gravados em %s.",
        uf,
        destino.stat().st_size / 1024 / 1024,
        destino,
    )
    return destino


# --------------------------------------------------------------------------- #
# 2. Preparo das chaves do lado BACEN
# --------------------------------------------------------------------------- #

#: CEP que a fonte usa como "não informado".
CEP_NULO = "00000000"


def preparar_alvo(pontos: pd.DataFrame) -> pd.DataFrame:
    """Extrai de cada ponto de atendimento as chaves de casamento.

    Colunas acrescentadas:

    * ``cep8`` — os 8 dígitos do CEP, ou vazio se ausente/inválido;
    * ``cep_generico`` — ``True`` quando o CEP termina em ``000``, isto é,
      quando ele identifica o município inteiro e não uma face de quadra;
    * ``numero_imovel`` — o número, vindo da coluna ``numero`` ou, quando ela
      está vazia, do que houver depois da vírgula em ``endereco`` (as agências
      trazem "PCA.TIRADENTES,410" com a coluna própria vazia em 2 de cada 3
      linhas);
    * ``logradouro`` — o `endereco` sem a parte do número;
    * ``chave_logr`` — `chave_logradouro` aplicada a `logradouro`.

    Args:
        pontos: dataset categorizado de `src.etl_bacen`.

    Returns:
        Uma CÓPIA de `pontos` com as cinco colunas acima.
    """
    alvo = pontos.copy()

    cep = _somente_digitos(alvo["cep"])
    valido = cep.str.fullmatch(r"\d{8}") & (cep != CEP_NULO)
    alvo["cep8"] = cep.where(valido, "")
    alvo["cep_generico"] = alvo["cep8"].str.endswith("000") & (alvo["cep8"] != "")

    endereco = alvo["endereco"].astype("string").fillna("")
    partes = endereco.str.split(",", n=1, expand=True)
    alvo["logradouro"] = partes[0].str.strip()
    resto = partes[1] if partes.shape[1] > 1 else pd.Series("", index=alvo.index)

    numero_coluna = _somente_digitos(alvo["numero"])
    numero_endereco = resto.astype("string").fillna("").str.extract(r"(\d+)")[0]
    numero = numero_coluna.where(numero_coluna != "", numero_endereco.fillna(""))
    alvo["numero_imovel"] = pd.to_numeric(numero, errors="coerce").astype("Int64")

    alvo["chave_logr"] = _chaves_de_serie(alvo["logradouro"])
    return alvo


# --------------------------------------------------------------------------- #
# 3. Varredura do CNEFE
# --------------------------------------------------------------------------- #

#: Colunas lidas do CSV do CNEFE. O arquivo tem 34; ler as 8 necessárias é o
#: que mantém a varredura na casa de dezenas de segundos por UF.
COLUNAS_CNEFE = [
    "COD_MUNICIPIO",
    "CEP",
    "NOM_TIPO_SEGLOGR",
    "NOM_TITULO_SEGLOGR",
    "NOM_SEGLOGR",
    "NUM_ENDERECO",
    "LATITUDE",
    "LONGITUDE",
]

#: Tamanho do bloco lido por vez do CSV, em bytes (64 MiB).
#:
#: O CSV de uma UF chega a ~1,6 GB descompactado e é lido em streaming de
#: dentro do ZIP, sem nunca existir inteiro em disco nem em memória.
BLOCO_LEITURA = 1 << 26


def _varrer_uf(
    caminho_zip: Path,
    chaves_cep: set[tuple[str, str]],
    chaves_logr: set[tuple[str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Lê um ZIP do CNEFE e retém só os endereços que interessam.

    A retenção é o ponto central do desempenho e da memória: o CNEFE de RS/SC/PR
    soma ~12 milhões de endereços, mas o mapa só precisa dos que estão num CEP
    ou num logradouro onde existe ponto de atendimento. O filtro é aplicado
    lote a lote, ainda durante a leitura, e o que sobra são duas tabelas
    puramente numéricas.

    Args:
        caminho_zip: ZIP de uma UF, como devolvido por `baixar_uf`.
        chaves_cep: pares ``(código do município, CEP de 8 dígitos)`` buscados.
        chaves_logr: pares ``(código do município, chave de logradouro)``.

    Returns:
        ``(por_cep, por_logr, lidos)``: os endereços retidos por cada critério
        — com ``mun``, a chave, ``num``, ``lat`` e ``lon`` — e o total de linhas
        lidas do arquivo.
    """
    retidos_cep: list[pd.DataFrame] = []
    retidos_logr: list[pd.DataFrame] = []
    lidos = 0

    with zipfile.ZipFile(caminho_zip) as pacote:
        csvs = [n for n in pacote.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            raise ValueError(f"{caminho_zip.name} não contém CSV: {pacote.namelist()!r}")

        for nome in csvs:
            with pacote.open(nome) as fluxo:
                leitor = pv.open_csv(
                    fluxo,
                    read_options=pv.ReadOptions(block_size=BLOCO_LEITURA),
                    parse_options=pv.ParseOptions(delimiter=";"),
                    convert_options=pv.ConvertOptions(
                        include_columns=COLUNAS_CNEFE,
                        # Tudo como texto: CEP e código de município são chaves
                        # com zero à esquerda, e o número do imóvel traz valores
                        # não numéricos ("S/N") que quebrariam a inferência.
                        column_types={c: "string" for c in COLUNAS_CNEFE},
                    ),
                )
                for lote in leitor:
                    lidos += lote.num_rows
                    retidos_cep, retidos_logr = _reter_do_lote(
                        lote.to_pandas(), chaves_cep, chaves_logr,
                        retidos_cep, retidos_logr,
                    )

    vazio = pd.DataFrame(columns=["mun", "chave", "num", "lat", "lon"])
    por_cep = pd.concat(retidos_cep, ignore_index=True) if retidos_cep else vazio
    por_logr = pd.concat(retidos_logr, ignore_index=True) if retidos_logr else vazio
    return por_cep, por_logr, lidos


def _reter_do_lote(
    lote: pd.DataFrame,
    chaves_cep: set[tuple[str, str]],
    chaves_logr: set[tuple[str, str]],
    retidos_cep: list[pd.DataFrame],
    retidos_logr: list[pd.DataFrame],
) -> tuple[list[pd.DataFrame], list[pd.DataFrame]]:
    """Filtra um lote do CNEFE e acumula as linhas de interesse.

    Args:
        lote: um bloco do CSV já em DataFrame, com `COLUNAS_CNEFE`.
        chaves_cep: pares ``(município, CEP)`` buscados.
        chaves_logr: pares ``(município, chave de logradouro)`` buscados.
        retidos_cep: acumulador das linhas que casaram por CEP.
        retidos_logr: acumulador das linhas que casaram por logradouro.

    Returns:
        Os dois acumuladores, com o que este lote acrescentou.
    """
    lote = lote.dropna(subset=["LATITUDE", "LONGITUDE"])
    if lote.empty:
        return retidos_cep, retidos_logr

    municipio = lote["COD_MUNICIPIO"].astype("string").fillna("")
    latitude = pd.to_numeric(lote["LATITUDE"], errors="coerce").astype("float32")
    longitude = pd.to_numeric(lote["LONGITUDE"], errors="coerce").astype("float32")
    numero = pd.to_numeric(lote["NUM_ENDERECO"], errors="coerce")

    cep = _somente_digitos(lote["CEP"])
    par_cep = list(zip(municipio, cep))
    marca_cep = np.fromiter(
        (par in chaves_cep for par in par_cep), dtype=bool, count=len(lote)
    )

    nome_completo = (
        lote["NOM_TIPO_SEGLOGR"].astype("string").fillna("") + " "
        + lote["NOM_TITULO_SEGLOGR"].astype("string").fillna("") + " "
        + lote["NOM_SEGLOGR"].astype("string").fillna("")
    )
    chave = _chaves_de_serie(nome_completo)
    par_logr = list(zip(municipio, chave))
    marca_logr = np.fromiter(
        (par in chaves_logr for par in par_logr), dtype=bool, count=len(lote)
    )

    if marca_cep.any():
        retidos_cep.append(
            pd.DataFrame(
                {
                    "mun": municipio[marca_cep].to_numpy(),
                    "chave": cep[marca_cep].to_numpy(),
                    "num": numero[marca_cep].to_numpy(),
                    "lat": latitude[marca_cep].to_numpy(),
                    "lon": longitude[marca_cep].to_numpy(),
                }
            )
        )
    if marca_logr.any():
        retidos_logr.append(
            pd.DataFrame(
                {
                    "mun": municipio[marca_logr].to_numpy(),
                    "chave": chave[marca_logr].to_numpy(),
                    "num": numero[marca_logr].to_numpy(),
                    "lat": latitude[marca_logr].to_numpy(),
                    "lon": longitude[marca_logr].to_numpy(),
                }
            )
        )
    return retidos_cep, retidos_logr


def _consolidar(retidos: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Resume os endereços retidos em duas tabelas de consulta.

    Args:
        retidos: saída de `_varrer_uf` para um dos dois critérios.

    Returns:
        ``(com_numero, sem_numero)``: a mediana de lat/lon por
        ``(município, chave, número)`` e por ``(município, chave)``.

    A mediana, e não a média: um único endereço com coordenada errada — que
    existe em cadastro desse porte — desloca a média do logradouro inteiro,
    enquanto a mediana o ignora.
    """
    if retidos.empty:
        indice = pd.MultiIndex.from_arrays([[], [], []], names=["mun", "chave", "num"])
        vazio_3 = pd.DataFrame(index=indice, columns=["lat", "lon"], dtype="float64")
        indice_2 = pd.MultiIndex.from_arrays([[], []], names=["mun", "chave"])
        vazio_2 = pd.DataFrame(index=indice_2, columns=["lat", "lon"], dtype="float64")
        return vazio_3, vazio_2

    com_numero = (
        retidos.dropna(subset=["num"])
        .groupby(["mun", "chave", "num"], sort=False)[["lat", "lon"]]
        .median()
    )
    sem_numero = retidos.groupby(["mun", "chave"], sort=False)[["lat", "lon"]].median()
    return com_numero, sem_numero


def construir_indice(
    alvo: pd.DataFrame,
    usar_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """Monta as quatro tabelas de consulta do CNEFE para as UFs do Sul.

    Percorre uma UF por vez e consolida antes de passar à próxima: como as
    chaves são sempre prefixadas pelo código do município, e município não
    atravessa UF, consolidar por partes dá exatamente o mesmo resultado de
    consolidar tudo junto — com uma fração da memória.

    Args:
        alvo: saída de `preparar_alvo`.
        usar_cache: repassado a `baixar_uf`.

    Returns:
        ``{"cep_num", "cep", "logr_num", "logr"}`` -> tabela indexada pelas
        chaves correspondentes, com colunas ``lat`` e ``lon``.
    """
    com_cep = alvo[alvo["cep8"] != ""]
    chaves_cep = set(zip(com_cep["municipio_ibge"], com_cep["cep8"]))
    com_logr = alvo[alvo["chave_logr"] != ""]
    chaves_logr = set(zip(com_logr["municipio_ibge"], com_logr["chave_logr"]))

    _LOGGER.info(
        "Buscando %d chave(s) de CEP e %d de logradouro no CNEFE.",
        len(chaves_cep),
        len(chaves_logr),
    )

    partes: dict[str, list[pd.DataFrame]] = {
        "cep_num": [], "cep": [], "logr_num": [], "logr": [],
    }
    for uf in config.SIGLAS_SUL:
        caminho = baixar_uf(uf, usar_cache=usar_cache)
        por_cep, por_logr, lidos = _varrer_uf(caminho, chaves_cep, chaves_logr)
        _LOGGER.info(
            "CNEFE %s: %s endereços lidos, %s retidos por CEP e %s por logradouro.",
            uf, f"{lidos:,}", f"{len(por_cep):,}", f"{len(por_logr):,}",
        )

        cep_num, cep = _consolidar(por_cep)
        logr_num, logr = _consolidar(por_logr)
        partes["cep_num"].append(cep_num)
        partes["cep"].append(cep)
        partes["logr_num"].append(logr_num)
        partes["logr"].append(logr)

    return {nome: pd.concat(lista) for nome, lista in partes.items()}


# --------------------------------------------------------------------------- #
# 4. Casamento
# --------------------------------------------------------------------------- #


def _consultar(
    indice: pd.DataFrame,
    chaves: pd.MultiIndex,
) -> tuple[np.ndarray, np.ndarray]:
    """Consulta um índice do CNEFE de uma vez para todos os pontos.

    Args:
        indice: uma das tabelas de `construir_indice`.
        chaves: as chaves de consulta, uma por ponto, na ordem dos pontos.

    Returns:
        ``(lat, lon)`` como vetores do tamanho de `chaves`, com ``NaN`` onde a
        chave não existe no índice.
    """
    if indice.empty:
        vazio = np.full(len(chaves), np.nan)
        return vazio, vazio
    encontrado = indice.reindex(chaves)
    return encontrado["lat"].to_numpy(), encontrado["lon"].to_numpy()


def casar_com_cnefe(
    alvo: pd.DataFrame,
    indice: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Resolve a coordenada de cada ponto pela cadeia de precisão.

    Aplica as quatro regras do CNEFE na ordem descrita no cabeçalho do módulo,
    da mais específica para a mais frouxa, e só escreve em quem ainda não foi
    resolvido. Quem não casa em nenhuma fica com coordenada nula, para o
    fallback de município tratar em `posicionar_no_municipio`.

    Args:
        alvo: saída de `preparar_alvo`.
        indice: saída de `construir_indice`.

    Returns:
        Uma CÓPIA de `alvo` com `latitude`, `longitude` e `precisao`.
    """
    resultado = alvo.copy()
    n = len(resultado)
    latitude = np.full(n, np.nan)
    longitude = np.full(n, np.nan)
    precisao = np.array([""] * n, dtype=object)

    municipio = resultado["municipio_ibge"].astype(str).to_numpy()
    numero = resultado["numero_imovel"].astype("float64").to_numpy()
    chave_logr = resultado["chave_logr"].astype(str).to_numpy()
    # O CEP genérico não identifica logradouro: ele só entra na última regra.
    cep_especifico = np.where(
        resultado["cep_generico"].to_numpy(), "", resultado["cep8"].astype(str)
    )
    cep_qualquer = resultado["cep8"].astype(str).to_numpy()

    regras = [
        ("cep_num", [municipio, cep_especifico, numero], PRECISAO_ENDERECO),
        ("logr_num", [municipio, chave_logr, numero], PRECISAO_ENDERECO),
        ("cep", [municipio, cep_especifico], PRECISAO_LOGRADOURO),
        ("logr", [municipio, chave_logr], PRECISAO_LOGRADOURO),
        ("cep", [municipio, cep_qualquer], PRECISAO_LOCALIDADE),
    ]

    for nome_indice, partes_chave, nivel in regras:
        pendente = np.isnan(latitude)
        if not pendente.any():
            break
        # Chave vazia ou número ausente nunca casa; excluí-las aqui evita
        # consultar o índice com lixo e barateia o reindex.
        valida = pendente.copy()
        for parte in partes_chave:
            if parte.dtype == object or parte.dtype.kind in "US":
                valida &= parte != ""
            else:
                valida &= ~np.isnan(parte)
        if not valida.any():
            continue

        chaves = pd.MultiIndex.from_arrays([parte[valida] for parte in partes_chave])
        lat, lon = _consultar(indice[nome_indice], chaves)

        posicoes = np.flatnonzero(valida)
        casou = ~np.isnan(lat)
        latitude[posicoes[casou]] = lat[casou]
        longitude[posicoes[casou]] = lon[casou]
        precisao[posicoes[casou]] = nivel

        _LOGGER.info(
            "Regra %-8s (%s): %d ponto(s) resolvidos.",
            nome_indice, nivel, int(casou.sum()),
        )

    resultado["latitude"] = latitude
    resultado["longitude"] = longitude
    resultado["precisao"] = precisao
    return resultado


# --------------------------------------------------------------------------- #
# 5. Conferência espacial e fallback de município
# --------------------------------------------------------------------------- #


def _pontos_representativos(malha: gpd.GeoDataFrame) -> pd.DataFrame:
    """Ponto representativo do polígono de cada município.

    Usa `representative_point()`, e não `centroid`: em município de forma
    irregular ou recortado pela costa o centroide pode cair FORA do próprio
    polígono, e o marcador apareceria no mar ou na cidade vizinha.

    Args:
        malha: agregado/malha com `municipio_ibge` e geometria.

    Returns:
        DataFrame com ``municipio_ibge``, ``lat_municipio`` e ``lon_municipio``.
    """
    representativos = malha.geometry.representative_point()
    return pd.DataFrame(
        {
            "municipio_ibge": malha["municipio_ibge"].to_numpy(),
            "lat_municipio": representativos.y.to_numpy(),
            "lon_municipio": representativos.x.to_numpy(),
        }
    )


def conferir_dentro_do_municipio(
    pontos: pd.DataFrame,
    malha: gpd.GeoDataFrame,
) -> pd.Series:
    """Diz, para cada ponto com coordenada, se ela caiu no município correto.

    É a única conferência possível contra a fonte: se o CEP publicado pelo
    BACEN estiver errado, o casamento pode devolver um endereço real e
    plausível em outra cidade, e nada no texto denunciaria. O polígono
    denuncia.

    Args:
        pontos: saída de `casar_com_cnefe`.
        malha: agregado com `municipio_ibge` e geometria em
            `config.CRS_GEOGRAFICO`.

    Returns:
        Series booleana alinhada com `pontos`: ``True`` quando a coordenada
        está dentro do polígono do seu `municipio_ibge`. Ponto sem coordenada
        vale ``False``.
    """
    com_coordenada = pontos["latitude"].notna() & pontos["longitude"].notna()
    dentro = pd.Series(False, index=pontos.index)
    if not com_coordenada.any():
        return dentro

    candidatos = pontos.loc[com_coordenada]
    geometria = gpd.GeoDataFrame(
        candidatos[["municipio_ibge"]],
        geometry=gpd.points_from_xy(candidatos["longitude"], candidatos["latitude"]),
        crs=config.CRS_GEOGRAFICO,
    )
    juncao = gpd.sjoin(
        geometria,
        malha[["municipio_ibge", "geometry"]].rename(
            columns={"municipio_ibge": "municipio_malha"}
        ),
        how="left",
        predicate="within",
    )
    # sjoin pode devolver mais de uma linha por ponto em fronteira compartilhada;
    # basta que UMA delas seja o município certo.
    bate = juncao["municipio_ibge"] == juncao["municipio_malha"]
    dentro.loc[com_coordenada] = bate.groupby(level=0).any().reindex(candidatos.index, fill_value=False)
    return dentro


def posicionar_no_municipio(
    pontos: pd.DataFrame,
    malha: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Completa quem não casou, e rebaixa quem casou fora do próprio município.

    Args:
        pontos: saída de `casar_com_cnefe`.
        malha: agregado com geometria.

    Returns:
        Uma CÓPIA de `pontos` sem coordenada nula, exceto para os pontos cujo
        `municipio_ibge` sequer existe na malha — esses são descartados e
        reportados no log, como já fazia o mapa.
    """
    resultado = pontos.copy()

    fora = resultado["latitude"].notna() & ~conferir_dentro_do_municipio(resultado, malha)
    if int(fora.sum()):
        _LOGGER.warning(
            "%d ponto(s) casaram no CNEFE mas caíram FORA do polígono do próprio "
            "município (CEP provavelmente incorreto na fonte); rebaixados para "
            "posição de município.",
            int(fora.sum()),
        )
        resultado.loc[fora, ["latitude", "longitude"]] = np.nan
        resultado.loc[fora, "precisao"] = ""

    resultado = resultado.merge(_pontos_representativos(malha), on="municipio_ibge", how="left")

    sem_municipio = resultado["lat_municipio"].isna() & resultado["latitude"].isna()
    if int(sem_municipio.sum()):
        _LOGGER.warning(
            "%d ponto(s) com `municipio_ibge` fora da malha ficaram FORA do mapa. "
            "Códigos: %r",
            int(sem_municipio.sum()),
            sorted(resultado.loc[sem_municipio, "municipio_ibge"].unique())[:10],
        )
        resultado = resultado[~sem_municipio]

    pendente = resultado["latitude"].isna()
    resultado.loc[pendente, "latitude"] = resultado.loc[pendente, "lat_municipio"]
    resultado.loc[pendente, "longitude"] = resultado.loc[pendente, "lon_municipio"]
    resultado.loc[pendente, "precisao"] = PRECISAO_MUNICIPIO

    return resultado.drop(columns=["lat_municipio", "lon_municipio"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 6. Desempate de coordenadas coincidentes
# --------------------------------------------------------------------------- #

#: Raio, em metros, do leque aberto entre pontos que ficaram na MESMA
#: coordenada, por nível de precisão.
#:
#: Sem cluster no mapa, dois marcadores exatamente sobrepostos viram um só: o de
#: baixo não é clicável e nem sequer se sabe que existe. O deslocamento aqui não
#: inventa precisão — ele é sempre menor que a incerteza do nível que o ponto já
#: declara. Dois pontos no mesmo endereço (uma agência e um posto no mesmo
#: prédio, caso real da base) abrem 8 m; os que só se sabe estarem no mesmo
#: município abrem 120 m, o que continua irrelevante diante de um município.
RAIO_DESEMPATE_M = {
    PRECISAO_ENDERECO: 8.0,
    PRECISAO_LOGRADOURO: 20.0,
    PRECISAO_LOCALIDADE: 60.0,
    PRECISAO_MUNICIPIO: 120.0,
}

#: Metros por grau de latitude (WGS84, valor médio). A longitude é corrigida
#: pelo cosseno da latitude no próprio cálculo.
METROS_POR_GRAU = 111_320.0


def desempatar_coincidentes(pontos: pd.DataFrame) -> pd.DataFrame:
    """Abre em leque os pontos que ficaram na mesma coordenada exata.

    O leque é uma espiral de Vogel (ângulo áureo), que distribui os pontos de
    forma regular num disco em vez de enfileirá-los; e é DETERMINÍSTICO — a
    posição depende só da ordem do ponto dentro do seu grupo, então duas
    execuções do pipeline produzem o mesmo mapa.

    O primeiro ponto de cada grupo fica exatamente onde estava.

    Args:
        pontos: saída de `posicionar_no_municipio`.

    Returns:
        Uma CÓPIA de `pontos` com `latitude`/`longitude` ajustadas.
    """
    resultado = pontos.copy()
    grupo = resultado.groupby(["latitude", "longitude"], sort=False).cumcount()
    tamanho = resultado.groupby(["latitude", "longitude"], sort=False)["latitude"].transform("size")

    precisa = (tamanho > 1) & (grupo > 0)
    if not precisa.any():
        return resultado

    raio_m = resultado["precisao"].map(RAIO_DESEMPATE_M).fillna(0.0).to_numpy()
    indice = grupo.to_numpy().astype(float)
    total = tamanho.to_numpy().astype(float)

    # Vogel: raio ~ sqrt(i/n) preenche o disco com densidade uniforme.
    angulo = indice * np.pi * (3.0 - np.sqrt(5.0))
    distancia = raio_m * np.sqrt(indice / np.maximum(total - 1.0, 1.0))

    latitude = resultado["latitude"].to_numpy()
    delta_lat = distancia * np.cos(angulo) / METROS_POR_GRAU
    delta_lon = (
        distancia * np.sin(angulo)
        / (METROS_POR_GRAU * np.cos(np.radians(latitude)))
    )

    marca = precisa.to_numpy()
    resultado.loc[marca, "latitude"] = latitude[marca] + delta_lat[marca]
    resultado.loc[marca, "longitude"] = (
        resultado["longitude"].to_numpy()[marca] + delta_lon[marca]
    )
    _LOGGER.info("%d ponto(s) coincidentes abertos em leque.", int(marca.sum()))
    return resultado


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #


def executar(
    caminho_pontos: Path = config.ARQUIVO_IF_SUL_CATEGORIZADO,
    caminho_agregado: Path = config.ARQUIVO_AGREGADO_MUNICIPIO,
    destino: Path = config.ARQUIVO_PONTOS_GEOCODIFICADOS,
    usar_cache: bool = True,
) -> pd.DataFrame:
    """Geocodifica os pontos de atendimento e grava o Parquet.

    Args:
        caminho_pontos: dataset categorizado de `src.etl_bacen`.
        caminho_agregado: GeoParquet de `src.agregacao`, usado para o fallback
            de município e para a conferência espacial.
        destino: caminho do Parquet de saída.
        usar_cache: reaproveita os ZIP do CNEFE já baixados.

    Returns:
        Os pontos com `latitude`, `longitude` e `precisao`.

    Raises:
        FileNotFoundError: se algum dos dois Parquet de entrada não existir.
    """
    if not caminho_pontos.exists():
        raise FileNotFoundError(
            f"Dataset não encontrado: {caminho_pontos}. "
            "Rode `python -m src.etl_bacen` para gerá-lo."
        )
    if not caminho_agregado.exists():
        raise FileNotFoundError(
            f"Agregado não encontrado: {caminho_agregado}. "
            "Rode `python -m src.agregacao` para gerá-lo."
        )

    pontos = pd.read_parquet(caminho_pontos)
    malha = gpd.read_parquet(caminho_agregado)
    if malha.crs is not None and not malha.crs.equals(config.CRS_GEOGRAFICO):
        malha = malha.to_crs(config.CRS_GEOGRAFICO)

    alvo = preparar_alvo(pontos)
    indice = construir_indice(alvo, usar_cache=usar_cache)
    casados = casar_com_cnefe(alvo, indice)
    posicionados = posicionar_no_municipio(casados, malha)
    final = desempatar_coincidentes(posicionados)

    destino.parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(destino, index=False)

    imprimir_resumo(final, destino)
    return final


def imprimir_resumo(pontos: pd.DataFrame, destino: Path) -> None:
    """Imprime a cobertura da geocodificação por nível de precisão.

    Args:
        pontos: saída de `executar`.
        destino: caminho do Parquet gravado.
    """
    print("=" * 78)
    print("GEOCODIFICAÇÃO — CNEFE 2022 (IBGE)")
    print("=" * 78)

    total = len(pontos)
    contagem = pontos["precisao"].value_counts()
    acumulado = 0
    for nivel in ORDEM_PRECISAO:
        quantos = int(contagem.get(nivel, 0))
        acumulado += quantos
        print(
            f"   {nivel:<12} {quantos:>6}  {quantos/total:>6.1%}   "
            f"(acumulado {acumulado/total:>5.1%})  {DESCRICAO_PRECISAO[nivel]}"
        )

    melhor_que_municipio = total - int(contagem.get(PRECISAO_MUNICIPIO, 0))
    print(
        f"\n   {melhor_que_municipio} de {total} pontos ({melhor_que_municipio/total:.1%}) "
        "têm posição própria; o restante usa o ponto do município."
    )
    print(f"   Coordenadas distintas: {pontos.groupby(['latitude','longitude']).ngroups}")
    print(f"\nGravado em: {destino}\n")


def main() -> None:
    """Ponto de entrada para ``python -m src.cnefe``."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s %(name)s: %(message)s"
    )
    executar()


if __name__ == "__main__":
    main()
