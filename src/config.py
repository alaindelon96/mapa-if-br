"""Caminhos, constantes e parâmetros de configuração do projeto."""

from pathlib import Path

# --- Diretórios -------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = BASE_DIR / "output"

# --- Sistemas de referência de coordenadas ----------------------------------

#: Coordenadas geográficas (lat/lon). É o CRS exigido pelo folium/Leaflet.
CRS_GEOGRAFICO = "EPSG:4326"

#: CRS métrico para cálculos de distância e área. SIRGAS 2000 / UTM 22S cobre
#: o Rio Grande do Sul; troque a zona se o recorte do projeto mudar.
CRS_METRICO = "EPSG:31982"

# --- Parâmetros padrão do mapa ----------------------------------------------

#: Centro aproximado do Rio Grande do Sul (lat, lon).
CENTRO_MAPA = (-30.0, -53.2)
ZOOM_INICIAL = 7
TILES_PADRAO = "OpenStreetMap"


def garantir_diretorios() -> None:
    """Cria os diretórios de dados e saída, caso ainda não existam."""
    for diretorio in (RAW_DIR, PROCESSED_DIR, OUTPUT_DIR):
        diretorio.mkdir(parents=True, exist_ok=True)
