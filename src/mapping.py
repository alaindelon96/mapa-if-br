"""Construção do mapa interativo com folium."""

import folium
import geopandas as gpd

from src import config


def criar_mapa(
    centro: tuple[float, float] = config.CENTRO_MAPA,
    zoom: int = config.ZOOM_INICIAL,
    tiles: str = config.TILES_PADRAO,
) -> folium.Map:
    """Cria o mapa base, sem camadas de dados."""
    return folium.Map(location=list(centro), zoom_start=zoom, tiles=tiles)


def adicionar_marcadores(
    mapa: folium.Map,
    gdf: gpd.GeoDataFrame,
    *,
    coluna_rotulo: str,
    nome_camada: str = "Pontos",
) -> folium.Map:
    """Adiciona um marcador por feição, com popup montado a partir do GeoDataFrame.

    O conteúdo do popup e o ícone dependem dos campos do dataset final.
    """
    raise NotImplementedError


def adicionar_camada_malha(
    mapa: folium.Map,
    gdf: gpd.GeoDataFrame,
    *,
    nome_camada: str = "Municípios",
) -> folium.Map:
    """Adiciona a malha territorial como camada GeoJSON, com estilo e tooltip."""
    raise NotImplementedError


def finalizar(mapa: folium.Map) -> folium.Map:
    """Aplica os controles finais (seletor de camadas, escala)."""
    folium.LayerControl().add_to(mapa)
    return mapa
