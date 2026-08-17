"""Orquestração das etapas do projeto.

Ordem prevista:

1. `ingest`    — carrega a planilha de origem (e baixa a malha, se remota)
2. `normalize` — padroniza colunas, limpa registros
3. `geo`       — monta as geometrias, reprojeta, junta com a malha
4. `mapping`   — monta o mapa base e as camadas
5. `export`    — grava `data/processed/` e `output/mapa.html`
"""

from pathlib import Path


def executar() -> Path:
    """Roda o pipeline completo e devolve o caminho do mapa gerado."""
    raise NotImplementedError
