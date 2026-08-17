"""Normalização e limpeza dos dados tabulares."""

import pandas as pd
from unidecode import unidecode


def normalizar_texto(valor: str) -> str:
    """Remove acentos, espaços nas pontas e uniformiza para maiúsculas.

    Usado para comparar nomes de municípios/campi vindos de fontes distintas,
    onde a grafia varia ("Bagé", "BAGE ", "bage").
    """
    if not isinstance(valor, str):
        return valor
    return unidecode(valor).strip().upper()


def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza os nomes das colunas para snake_case sem acentos."""
    renomeadas = {
        coluna: unidecode(str(coluna)).strip().lower().replace(" ", "_")
        for coluna in df.columns
    }
    return df.rename(columns=renomeadas)


def limpar_registros(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica as regras de limpeza específicas do domínio.

    Depende do schema da planilha de origem: colunas obrigatórias, remoção de
    duplicatas, descarte de linhas sem coordenadas, tipos esperados.
    """
    raise NotImplementedError
