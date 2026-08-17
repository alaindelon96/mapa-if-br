"""Ponto de entrada do projeto mapa-if-sul.

Roda o pipeline completo — planilhas do BACEN -> mapa interativo. Ver
`src.pipeline` para as etapas e os artefatos que cada uma grava.
"""

import logging

from src import pipeline


def main() -> None:
    # Os módulos do pipeline reportam avisos por `logging` (ponto sem código
    # IBGE, bandeira fora do de-para, malha reprojetada). Sem esta configuração
    # o nível INFO não chega ao terminal e esses avisos somem justamente na
    # execução de ponta a ponta, que é onde mais importam.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s %(name)s: %(message)s"
    )
    destino = pipeline.executar()
    print(f"Mapa gerado em: {destino}")


if __name__ == "__main__":
    main()
