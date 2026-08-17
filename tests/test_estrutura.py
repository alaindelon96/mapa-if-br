"""Testes de fumaça: garantem que o esqueleto carrega e que os caminhos batem."""

import pandas as pd

from src import config, export, geo, ingest, mapping, normalize, pipeline


def test_modulos_importam():
    for modulo in (config, ingest, normalize, geo, mapping, export, pipeline):
        assert modulo is not None


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
