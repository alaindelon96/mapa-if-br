"""Construção do mapa interativo com folium."""

import folium
import geopandas as gpd

from src import config


def criar_mapa(
    centro: tuple[float, float] = config.CENTRO_MAPA,
    zoom: int = config.ZOOM_INICIAL,
    tiles: str = config.URL_TILES_PADRAO,
    atribuicao: str = config.ATRIBUICAO_TILES,
) -> folium.Map:
    """Cria o mapa base, sem camadas de dados.

    `tiles` é a URL crua dos ladrilhos, e não um alias do folium, porque é nela
    que mora a chave de API da CARTO (ver `config.URL_TILES_PADRAO`). Como o
    folium só embute atribuição nos aliases que conhece, ela vem junto em
    `atribuicao` — sem isso o construtor recusa a URL.
    """
    return folium.Map(
        location=list(centro),
        zoom_start=zoom,
        tiles=tiles,
        attr=atribuicao,
        subdomains=config.SUBDOMINIOS_TILES,
        max_zoom=config.ZOOM_MAXIMO_TILES,
    )


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
