# mapa-if-sul

Mapa interativo dos pontos de atendimento financeiro (agências e postos de
bancos e cooperativas de crédito) do RS, SC e PR, a partir das planilhas do
BACEN e das bases territoriais do IBGE.

## Pipeline

`python main.py` roda as cinco etapas em sequência; cada uma também roda
sozinha durante o desenvolvimento.

| # | Módulo | O que faz | Artefato |
|---|---|---|---|
| 1 | `src.etl_bacen` | recorta RS/SC/PR e as instituições-alvo, classifica bandeira | `data/processed/if_sul_categorizado.parquet` |
| 2 | `src.ibge_malha` | malha municipal do Sul + nome oficial e população | `data/raw/malha_municipios_sul.geojson` |
| 3 | `src.agregacao` | junta os dois pelo código IBGE, uma linha por município | `data/processed/agregado_municipio.parquet` |
| 4 | `src.cnefe` | resolve a coordenada de cada ponto contra o Cadastro Nacional de Endereços do Censo 2022 | `data/processed/pontos_geocodificados.parquet` |
| 5 | `src.mapa` | coroplético reativo, camadas de ponto em dois níveis, busca de município e recorte por UF | `output/mapa_if_sul.html` |

A etapa 4 baixa ~580 MB do CNEFE (um arquivo por UF) para `data/raw/cnefe/` na
primeira execução e os reaproveita nas seguintes — o CNEFE é um produto do
Censo 2022 e não muda.

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
| truststore | 0.10.4 | valida TLS pelos certificados do sistema (ver abaixo) |
| pytest | 9.1.1 | testes automatizados |

### Falha de TLS ao chamar o IBGE

Em máquina com antivírus ou proxy que inspeciona HTTPS, todas as chamadas ao
IBGE falham com `CERTIFICATE_VERIFY_FAILED`: essas ferramentas reemitem os
certificados com uma autoridade raiz própria, instalada no repositório do
Windows, onde o `certifi` não olha. O `truststore` resolve isso fazendo o
Python validar pelo repositório do sistema (ver `src/rede.py`); ele é uma
dependência opcional — sem ele o projeto roda normalmente onde não há
inspeção de HTTPS.
