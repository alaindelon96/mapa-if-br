"""Gravação dos artefatos gerados em `data/processed/` e `output/`."""

from pathlib import Path

import folium
import pandas as pd

from src import config


def salvar_mapa(mapa: folium.Map, nome_arquivo: str = "mapa.html") -> Path:
    """Grava o mapa como HTML em `output/` e devolve o caminho.

    Args:
        mapa: o mapa já montado.
        nome_arquivo: nome do arquivo dentro de `output/`.

    Returns:
        O caminho gravado.
    """
    destino = config.OUTPUT_DIR / nome_arquivo
    # O diretório é criado aqui, na hora de gravar, e não por uma rotina de
    # preparo chamada antes: é o mesmo padrão das cinco etapas do pipeline
    # (`etl_bacen.salvar_parquet`, `agregacao.salvar_parquet`, `cnefe.executar`,
    # `ibge_malha.baixar_malha_sul`, `mapa.gera_mapa`), e mantém cada função
    # responsável pelo próprio destino.
    destino.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(str(destino))
    return destino


def salvar_processado(df: pd.DataFrame, nome_arquivo: str) -> Path:
    """Grava um DataFrame tratado em `data/processed/` (CSV ou Parquet).

    O formato é escolhido pela extensão de `nome_arquivo`: ``.parquet`` grava
    em Parquet, qualquer outra grava CSV em UTF-8.

    Args:
        df: os dados já tratados.
        nome_arquivo: nome do arquivo dentro de `data/processed/`.

    Returns:
        O caminho gravado.
    """
    destino = config.PROCESSED_DIR / nome_arquivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.suffix == ".parquet":
        df.to_parquet(destino, index=False)
    else:
        df.to_csv(destino, index=False, encoding="utf-8")
    return destino
