"""Ponto de entrada do projeto mapa-if-sul."""

from src import pipeline


def main() -> None:
    destino = pipeline.executar()
    print(f"Mapa gerado em: {destino}")


if __name__ == "__main__":
    main()
