"""Testes de fumaça: garantem que o esqueleto carrega e que os caminhos batem."""

import pandas as pd
import pytest

from src import cnefe, config, export, geo, ingest, mapping, normalize, pipeline


def test_modulos_importam():
    for modulo in (config, ingest, normalize, geo, mapping, export, pipeline):
        assert modulo is not None


@pytest.mark.parametrize(
    ("bacen", "cnefe_fonte"),
    [
        # O caso que justifica a tabela de abreviaturas: o BACEN abrevia a
        # patente dentro do nome, o CNEFE publica o título por extenso.
        ("R.GAL.SAMPAIO", "RUA GENERAL SAMPAIO"),
        ("R CONS. LAURINDO", "RUA CONSELHEIRO LAURINDO"),
        ("PCA.QUINZE DE NOVEMBRO", "PRAÇA QUINZE DE NOVEMBRO"),
        # Romano de um lado, extenso do outro.
        ("AV XV DE NOVEMBRO", "AVENIDA QUINZE DE NOVEMBRO"),
        # Artigo presente em um lado só.
        ("AVENIDA DA VINDIMA", "AVENIDA VINDIMA"),
        # Tipo de logradouro divergente entre as fontes: sai da chave, então
        # não impede o casamento.
        ("RUA GETULIO VARGAS", "AVENIDA GETÚLIO VARGAS"),
    ],
)
def test_chave_logradouro_reconcilia_as_duas_fontes(bacen, cnefe_fonte):
    """As duas grafias do mesmo logradouro têm de gerar a mesma chave."""
    assert cnefe.chave_logradouro(bacen) == cnefe.chave_logradouro(cnefe_fonte)


def test_chave_logradouro_nao_converte_romano_de_uma_letra():
    """"Rua X" e "Rua Dez" são ruas diferentes e não podem virar a mesma chave.

    Nome de rua por letra é comum em loteamento; converter o romano de uma
    letra fundiria as duas e devolveria a mediana de um conjunto misturado.
    """
    assert cnefe.chave_logradouro("RUA X") != cnefe.chave_logradouro("RUA DEZ")
    assert cnefe.chave_logradouro("RUA V") != cnefe.chave_logradouro("AVENIDA CINCO")
    # Os romanos de duas letras ou mais continuam valendo — é o caso comum.
    assert cnefe.chave_logradouro("AV XV DE NOVEMBRO") == cnefe.chave_logradouro(
        "AVENIDA QUINZE DE NOVEMBRO"
    )


def test_chave_logradouro_trata_nulo_do_pandas():
    """`pd.NA` tem de virar chave vazia, e não a chave literal "NA"."""
    for nulo in (None, float("nan"), pd.NA):
        assert cnefe.chave_logradouro(nulo) == "", f"falhou para {nulo!r}"


def test_quilometragem_nao_vira_numero_de_imovel():
    """Em endereço de rodovia, o número após a vírgula é KM, não imóvel."""
    pontos = pd.DataFrame(
        {
            "endereco": ["ROD.SC-401,KM 5,4756", "R.URUGUAI,185"],
            "numero": ["", ""],
            "cep": ["88050-000", "90010-901"],
            "municipio_ibge": ["4205407", "4314902"],
        }
    )
    alvo = cnefe.preparar_alvo(pontos)
    assert pd.isna(alvo.loc[0, "numero_imovel"]), (
        "o KM 5 da rodovia virou número de imóvel e casaria com a casa nº 5"
    )
    assert alvo.loc[1, "numero_imovel"] == 185


def test_numero_zero_nao_e_numero_de_imovel():
    """Zero é o sentinela de "sem número" do CNEFE, não um imóvel."""
    pontos = pd.DataFrame(
        {
            "endereco": ["AV BRASIL,0"],
            "numero": ["0"],
            "cep": ["99999-000"],
            "municipio_ibge": ["4314902"],
        }
    )
    assert pd.isna(cnefe.preparar_alvo(pontos).loc[0, "numero_imovel"])


def test_chave_logradouro_nao_confunde_logradouros_distintos():
    """A normalização não pode ser tão agressiva a ponto de colidir nomes."""
    assert cnefe.chave_logradouro("RUA SAO PEDRO") != cnefe.chave_logradouro(
        "RUA SAO PAULO"
    )
    assert cnefe.chave_logradouro("") == ""


def test_caminhos_apontam_para_o_projeto():
    assert config.BASE_DIR.name == "mapa-if-sul"
    assert config.RAW_DIR == config.BASE_DIR / "data" / "raw"
    assert config.PROCESSED_DIR == config.BASE_DIR / "data" / "processed"
    assert config.OUTPUT_DIR == config.BASE_DIR / "output"


def test_normalizar_texto_remove_acentos_e_espacos():
    assert normalize.normalizar_texto(" Bagé ") == "BAGE"
    assert normalize.normalizar_texto("Passo Fundo") == "PASSO FUNDO"


def test_normalizar_colunas_gera_snake_case():
    df = pd.DataFrame(columns=["Município", "Nome do Campus"])
    assert list(normalize.normalizar_colunas(df).columns) == [
        "municipio",
        "nome_do_campus",
    ]


def test_para_geodataframe_cria_pontos_no_crs_geografico():
    df = pd.DataFrame({"latitude": [-31.33], "longitude": [-54.11]})
    gdf = geo.para_geodataframe(df)
    assert gdf.crs.to_string() == config.CRS_GEOGRAFICO
    assert gdf.geometry.iloc[0].x == -54.11


def test_criar_mapa_retorna_mapa_folium():
    assert mapping.criar_mapa()._name == "Map"
