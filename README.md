# mapa-if-sul

Projeto Python para geração de mapas a partir de dados tabulares e geoespaciais.

> Estrutura inicial — ainda sem lógica de negócio implementada.

## Estrutura

```
mapa-if-sul/
├── data/
│   ├── raw/          # dados de entrada originais (não versionados)
│   └── processed/    # dados tratados, prontos para uso
├── src/              # código-fonte do projeto
├── output/           # artefatos gerados (mapas .html, imagens)
├── tests/            # testes automatizados (pytest)
├── requirements.txt
├── README.md
└── main.py           # ponto de entrada
```

## Requisitos

- Python 3.12+

## Instalação

Criar e ativar o ambiente virtual:

```bash
python -m venv venv
```

Ativar no Windows (PowerShell):

```bash
.\venv\Scripts\Activate.ps1
```

Ativar no Linux/macOS:

```bash
source venv/bin/activate
```

Instalar as dependências:

```bash
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

## Testes

```bash
pytest
```

## Dependências principais

| Biblioteca | Versão | Uso |
|---|---|---|
| pandas | 3.0.5 | manipulação de dados tabulares |
| openpyxl | 3.1.5 | leitura/escrita de arquivos `.xlsx` |
| geopandas | 1.1.4 | dados geoespaciais em DataFrames |
| shapely | 2.1.2 | geometrias e operações espaciais |
| pyproj | 3.7.2 | projeções e transformação de coordenadas |
| folium | 0.20.0 | mapas interativos em HTML |
| requests | 2.34.2 | requisições HTTP |
| Unidecode | 1.4.0 | normalização de texto acentuado |
| pytest | 9.1.1 | testes automatizados |
