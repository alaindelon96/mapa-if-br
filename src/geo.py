"""Operações geoespaciais: geometrias, projeções e junções espaciais."""

from pathlib import Path

import geopandas as gpd
import pandas as pd

from src import config


def para_geodataframe(
    df: pd.DataFrame,
    *,
    col_lat: str = "latitude",
    col_lon: str = "longitude",
    crs: str = config.CRS_GEOGRAFICO,
) -> gpd.GeoDataFrame:
    """Converte um DataFrame com colunas de lat/lon em GeoDataFrame de pontos."""
    geometria = gpd.points_from_xy(df[col_lon], df[col_lat])
    return gpd.GeoDataFrame(df.copy(), geometry=geometria, crs=crs)


def reprojetar(gdf: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    """Reprojeta o GeoDataFrame para o CRS informado.

    Volte a `config.CRS_GEOGRAFICO` antes de plotar no folium: o Leaflet só
    entende lat/lon em graus.

    Para medir distância ou área, passe um CRS MÉTRICO explícito. O projeto não
    define constante para ele porque nenhuma etapa mede geometria — a agregação
    junta os pontos à malha pelo código IBGE do município, não espacialmente
    (ver o cabeçalho de `src.agregacao`).

    Args:
        gdf: as feições a reprojetar.
        crs: o CRS de destino, ex.: ``"EPSG:4326"``.

    Returns:
        Uma cópia reprojetada.
    """
    return gdf.to_crs(crs)


def carregar_malha(caminho: Path) -> gpd.GeoDataFrame:
    """Lê um arquivo vetorial (shapefile, GeoPackage, GeoJSON) de `data/raw/`.

    Deve validar o CRS de origem — malhas do IBGE costumam vir em SIRGAS 2000
    sem o CRS declarado no arquivo.
    """
    raise NotImplementedError


def juntar_por_municipio(
    pontos: gpd.GeoDataFrame,
    malha: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Associa cada ponto ao polígono do município que o contém.

    Ambas as camadas precisam estar no mesmo CRS antes da junção.
    """
    raise NotImplementedError
