"""Entrada de dados: leitura de planilhas/CSV e download de fontes remotas."""

from pathlib import Path

import pandas as pd


def carregar_planilha(caminho: Path, aba: str | int = 0) -> pd.DataFrame:
    """Lê uma planilha `.xlsx` e devolve o conteúdo bruto, sem tratamento.

    Args:
        caminho: arquivo em `data/raw/`.
        aba: nome ou índice da aba a ser lida.
    """
    raise NotImplementedError


def carregar_csv(caminho: Path, **kwargs) -> pd.DataFrame:
    """Lê um CSV e devolve o conteúdo bruto, sem tratamento."""
    raise NotImplementedError


def baixar_arquivo(url: str, destino: Path, *, sobrescrever: bool = False) -> Path:
    """Baixa `url` para `destino` e devolve o caminho gravado.

    Deve pular o download quando o arquivo já existir e `sobrescrever` for
    False, para não repetir requisições a cada execução do pipeline.
    """
    raise NotImplementedError
