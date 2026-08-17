"""Gravação dos artefatos gerados em `data/processed/` e `output/`."""

from pathlib import Path

import folium
import pandas as pd

from src import config


def salvar_mapa(mapa: folium.Map, nome_arquivo: str = "mapa.html") -> Path:
    """Grava o mapa como HTML em `output/` e devolve o caminho."""
    config.garantir_diretorios()
    destino = config.OUTPUT_DIR / nome_arquivo
    mapa.save(str(destino))
    return destino


def salvar_processado(df: pd.DataFrame, nome_arquivo: str) -> Path:
    """Grava um DataFrame tratado em `data/processed/` (CSV ou Parquet)."""
    config.garantir_diretorios()
    destino = config.PROCESSED_DIR / nome_arquivo
    if destino.suffix == ".parquet":
        df.to_parquet(destino, index=False)
    else:
        df.to_csv(destino, index=False, encoding="utf-8")
    return destino
