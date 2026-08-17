"""Testes de integridade dos artefatos do pipeline.

Diferente de `test_estrutura.py`, que é fumaça sobre o código, aqui os testes
leem os dois Parquet já gravados em ``data/processed/`` e verificam invariantes
do RESULTADO:

* `if_sul_categorizado.parquet` — o recorte não deixou vazar nada que não fosse
  cooperativa de crédito ou um dos cinco bancos-alvo, e todo código IBGE está no
  padrão de 7 dígitos;
* `agregado_municipio.parquet` — foi gravado depois do dataset que o originou, a
  agregação não perdeu nenhum ponto no join com a malha, e não há município
  repetido.

Os arquivos são pré-requisito: rode ``python -m src.etl_bacen`` e
``python -m src.agregacao`` antes. Sem eles os testes falham com a instrução,
em vez de passarem silenciosamente sobre um dataset inexistente.
"""

import re
from datetime import datetime

import pandas as pd
import pytest

from src import config
from src.etl_bacen import (
    CATEGORIA_BANCO,
    CATEGORIA_COOPERATIVA,
    NOME_COMERCIAL_BANCO,
    _normalizar_espacos,
)

#: Padrão do código IBGE de município: exatamente 7 dígitos (UF + município +
#: dígito verificador). Sem `-`, sem `.0`, sem zero à esquerda faltando.
PADRAO_CODIGO_IBGE = re.compile(r"^\d{7}$")


def _exigir_arquivo(caminho, comando):
    if not caminho.exists():
        pytest.fail(
            f"{caminho} não existe. Rode `{comando}` a partir da raiz do projeto "
            "antes de executar os testes."
        )


@pytest.fixture(scope="module")
def pontos() -> pd.DataFrame:
    """Dataset categorizado do BACEN: uma linha por ponto de atendimento."""
    _exigir_arquivo(config.ARQUIVO_IF_SUL_CATEGORIZADO, "python -m src.etl_bacen")
    return pd.read_parquet(config.ARQUIVO_IF_SUL_CATEGORIZADO)


@pytest.fixture(scope="module")
def agregado() -> pd.DataFrame:
    """Agregado por município.

    Lido com `pandas` (e não `geopandas`) de propósito: os testes olham só as
    colunas de contagem, e a geometria não precisa ser desserializada.
    """
    _exigir_arquivo(config.ARQUIVO_AGREGADO_MUNICIPIO, "python -m src.agregacao")
    return pd.read_parquet(config.ARQUIVO_AGREGADO_MUNICIPIO)


# --------------------------------------------------------------------------- #
# 1. categoria_if só admite os dois rótulos previstos
# --------------------------------------------------------------------------- #


def test_categoria_if_so_tem_cooperativa_e_banco(pontos):
    """Nenhuma outra categoria vazou pelo filtro de instituições."""
    esperadas = {CATEGORIA_COOPERATIVA, CATEGORIA_BANCO}

    sem_categoria = int(pontos["categoria_if"].isna().sum())
    assert sem_categoria == 0, (
        f"{sem_categoria} linha(s) sem `categoria_if` — toda linha do dataset "
        "final tem de estar classificada."
    )

    encontradas = set(pontos["categoria_if"].dropna().unique())
    assert encontradas <= esperadas, (
        f"categoria_if fora do previsto: {sorted(encontradas - esperadas)!r}. "
        f"Esperado apenas {sorted(esperadas)!r}."
    )

    # O recorte territorial é parte do mesmo filtro: se caiu UF de fora, o
    # "dataset filtrado RS+SC+PR" não é o que o nome diz.
    ufs = set(pontos["uf"].dropna().unique())
    assert ufs <= set(config.SIGLAS_SUL), (
        f"UF fora da Região Sul no dataset: {sorted(ufs - set(config.SIGLAS_SUL))!r}."
    )


# --------------------------------------------------------------------------- #
# 2. Os bancos são exatamente os cinco alvos
# --------------------------------------------------------------------------- #


def test_sub_categoria_banco_so_tem_os_cinco_alvos(pontos):
    """Nenhum banco fora de `config.BANCOS_ALVO` passou pelo filtro."""
    bancos = pontos[pontos["categoria_if"] == CATEGORIA_BANCO]
    assert len(bancos) > 0, "Nenhuma linha de categoria_if == 'Banco' no dataset."

    esperadas = set(NOME_COMERCIAL_BANCO.values())

    encontradas = set(bancos["sub_categoria"].dropna().unique())
    assert encontradas <= esperadas, (
        f"sub_categoria de banco fora do de-para: {sorted(encontradas - esperadas)!r}. "
        f"Esperado apenas {sorted(esperadas)!r}."
    )
    assert encontradas == esperadas, (
        "Banco-alvo sem nenhum ponto no dataset: "
        f"{sorted(esperadas - encontradas)!r}. Os cinco deveriam ter rede no Sul — "
        "a ausência indica filtro ou de-para alterado."
    )

    # Checagem pela origem, não só pelo rótulo: o nome bruto da instituição tem
    # de ser um dos cinco nomes exatos de BANCOS_ALVO. Pega o caso em que uma
    # subsidiária ("BANCO BRADESCO FINANCIAMENTOS S.A.") entrasse no recorte e
    # recebesse por engano um nome comercial válido.
    permitidos = {_normalizar_espacos(nome) for nome in config.BANCOS_ALVO}
    instituicoes = set(bancos["nome_instituicao"].dropna().unique())
    assert instituicoes <= permitidos, (
        f"Instituição fora de BANCOS_ALVO classificada como Banco: "
        f"{sorted(instituicoes - permitidos)!r}."
    )


# --------------------------------------------------------------------------- #
# 3. Código IBGE no padrão de 7 dígitos
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fonte", ["pontos", "agregado"])
def test_codigo_municipio_tem_7_digitos(fonte, request):
    """Nos dois artefatos, `municipio_ibge` é sempre string de 7 dígitos.

    O join da agregação é feito por igualdade de string entre os dois lados —
    um código com formatação diferente (``4314902.0``, ``431490``) não casaria
    e o ponto sumiria da contagem sem erro.
    """
    df = request.getfixturevalue(fonte)
    codigo = df["municipio_ibge"]

    nulos = int(codigo.isna().sum())
    assert nulos == 0, (
        f"{nulos} linha(s) de `{fonte}` sem `municipio_ibge` — sem código não há "
        "como atribuir o registro a um município."
    )

    invalidos = codigo[
        ~codigo.astype("string").str.fullmatch(r"\d{7}").fillna(False)
    ]
    assert len(invalidos) == 0, (
        f"{len(invalidos)} código(s) fora do padrão de 7 dígitos em `{fonte}`. "
        f"Exemplos: {invalidos.unique()[:5].tolist()!r}"
    )

    # Redundante com o fullmatch acima, mas explicita a intenção do padrão.
    assert all(PADRAO_CODIGO_IBGE.match(str(c)) for c in codigo.unique())


def test_codigos_do_agregado_pertencem_as_ufs_do_sul(agregado):
    """Os dois primeiros dígitos do código têm de ser 41, 42 ou 43."""
    prefixos = set(agregado["municipio_ibge"].astype("string").str.slice(0, 2))
    esperados = {str(codigo) for codigo in config.CODIGO_UF_SUL.values()}
    assert prefixos <= esperados, (
        f"Município fora do Sul na malha: prefixos {sorted(prefixos - esperados)!r}."
    )


# --------------------------------------------------------------------------- #
# 4. Nenhum ponto perdido no join com a malha
# --------------------------------------------------------------------------- #


def test_agregado_nao_e_mais_antigo_que_o_dataset():
    """O agregado tem de ter sido gravado DEPOIS do dataset que o originou.

    É pré-condição de todas as comparações entre os dois arquivos daqui em
    diante: se o ETL foi rodado de novo sem reagregar, os dois Parquet são de
    safras diferentes e qualquer igualdade entre eles é coincidência — ou,
    pior, a divergência aponta para um bug que não existe.

    A comparação é por `mtime` do arquivo, não por conteúdo: é o único carimbo
    de tempo disponível: nenhum dos dois Parquet grava metadado de geração.
    Consequência prática: reescrever o agregado sem regerá-lo (um `touch`, uma
    cópia, um checkout) engana este teste. Ele pega o descuido comum — rodar
    `src.etl_bacen` e esquecer `src.agregacao` —, não adulteração deliberada.
    """
    _exigir_arquivo(config.ARQUIVO_IF_SUL_CATEGORIZADO, "python -m src.etl_bacen")
    _exigir_arquivo(config.ARQUIVO_AGREGADO_MUNICIPIO, "python -m src.agregacao")

    mtime_pontos = config.ARQUIVO_IF_SUL_CATEGORIZADO.stat().st_mtime
    mtime_agregado = config.ARQUIVO_AGREGADO_MUNICIPIO.stat().st_mtime

    def _quando(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    atraso = mtime_pontos - mtime_agregado
    assert mtime_agregado >= mtime_pontos, (
        f"{config.ARQUIVO_AGREGADO_MUNICIPIO.name} está DESATUALIZADO: gravado em "
        f"{_quando(mtime_agregado)}, {atraso:.0f}s ANTES de "
        f"{config.ARQUIVO_IF_SUL_CATEGORIZADO.name} ({_quando(mtime_pontos)}). "
        "Rode `python -m src.agregacao` para reagregar sobre o dataset atual."
    )


def test_soma_das_contagens_bate_com_o_total_de_pontos(pontos, agregado):
    """`total_cooperativas + total_bancos` somados = linhas do dataset filtrado.

    Se a soma for MENOR, algum ponto ficou fora do join — código IBGE do BACEN
    que não existe na malha do IBGE, ou nulo. Se for MAIOR, houve duplicação de
    linha no merge.
    """
    total_pontos = len(pontos)
    soma_agregado = int(
        agregado["total_cooperativas"].sum() + agregado["total_bancos"].sum()
    )

    if soma_agregado != total_pontos:
        codigos_malha = set(agregado["municipio_ibge"])
        perdidos = pontos[~pontos["municipio_ibge"].isin(codigos_malha)]
        pytest.fail(
            f"Soma das contagens do agregado ({soma_agregado}) != linhas do "
            f"dataset filtrado ({total_pontos}); diferença de "
            f"{total_pontos - soma_agregado}. "
            f"{len(perdidos)} ponto(s) têm `municipio_ibge` ausente da malha, "
            f"códigos: {sorted(perdidos['municipio_ibge'].dropna().unique())[:10]!r}"
        )


def test_total_por_categoria_bate_com_o_dataset(pontos, agregado):
    """A quebra por categoria também tem de fechar, não só o total."""
    esperado = {
        "total_cooperativas": int(
            (pontos["categoria_if"] == CATEGORIA_COOPERATIVA).sum()
        ),
        "total_bancos": int((pontos["categoria_if"] == CATEGORIA_BANCO).sum()),
    }
    obtido = {coluna: int(agregado[coluna].sum()) for coluna in esperado}
    assert obtido == esperado, (
        f"Contagem por categoria divergente entre os dois artefatos: "
        f"agregado={obtido}, dataset={esperado}."
    )


def test_total_geral_e_a_soma_das_duas_categorias(agregado):
    """`total_geral` é derivado; nenhum município pode divergir da soma."""
    soma = agregado["total_cooperativas"] + agregado["total_bancos"]
    divergentes = agregado.loc[soma != agregado["total_geral"], "municipio_ibge"]
    assert len(divergentes) == 0, (
        f"{len(divergentes)} município(s) com total_geral != cooperativas + bancos. "
        f"Exemplos: {divergentes.head().tolist()!r}"
    )


# --------------------------------------------------------------------------- #
# 5. Um município, uma linha
# --------------------------------------------------------------------------- #


def test_nao_ha_municipio_duplicado_no_agregado(agregado):
    """Chave duplicada aqui significaria contagem inflada no mapa."""
    duplicados = agregado.loc[
        agregado["municipio_ibge"].duplicated(keep=False), "municipio_ibge"
    ]
    assert len(duplicados) == 0, (
        f"{duplicados.nunique()} código(s) de município repetido(s) no agregado. "
        f"Exemplos: {sorted(duplicados.unique())[:5]!r}"
    )


def test_agregado_tem_todos_os_municipios_do_sul(agregado):
    """1.191 municípios — a malha completa, não só os que têm atendimento.

    Um município a menos aqui é um buraco no coroplético, não um zero.
    """
    esperado = sum(config.MUNICIPIOS_POR_UF_SUL.values())
    assert len(agregado) == esperado, (
        f"Agregado tem {len(agregado)} municípios; a divisão territorial vigente "
        f"tem {esperado} no Sul ({config.MUNICIPIOS_POR_UF_SUL})."
    )

    por_uf = agregado["uf"].value_counts().to_dict()
    assert por_uf == config.MUNICIPIOS_POR_UF_SUL, (
        f"Contagem de municípios por UF divergente: {por_uf} != "
        f"{config.MUNICIPIOS_POR_UF_SUL}."
    )
