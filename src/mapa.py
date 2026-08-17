"""Mapa interativo dos pontos de atendimento financeiro da Região Sul.

Monta, sobre um mapa Folium centrado em RS/SC/PR, duas leituras complementares
do mesmo recorte:

* um **coroplético** por município, colorido pelo total de pontos de
  atendimento (agências + postos), lido de
  ``data/processed/agregado_municipio.parquet``;
* uma **camada de pontos em dois níveis**, lida de
  ``data/processed/if_sul_categorizado.parquet``, com um ponto por atendimento.

O coroplético é **reativo**: ele mostra sempre o total das bandeiras marcadas no
painel de camadas, e se repinta a cada clique. Ver "Coroplético reativo" abaixo.

Saída: ``output/mapa_if_sul.html`` (ver `config.ARQUIVO_MAPA`).

Uso (a partir da raiz do projeto, com o venv ativo)::

    python -m src.mapa

--------------------------------------------------------------------------
Por que as camadas de ponto são hierárquicas (e não uma lista plana)
--------------------------------------------------------------------------

Uma lista plana de 14 camadas obrigaria 14 cliques para esconder "todos os
bancos". A estrutura aqui é de dois níveis, com
`folium.plugins.FeatureGroupSubGroup`:

* **Nível 1 — grupo pai**: um `MarkerCluster` por `categoria_if` ("Bancos" e
  "Cooperativas"). É o toggle principal: desmarcá-lo no `LayerControl` remove o
  grupo inteiro do mapa de uma vez, com todos os pontos que estão nele.
* **Nível 2 — subgrupo**: um `FeatureGroupSubGroup` por `sub_categoria`
  (Sicredi, Sicoob, ... / Banco do Brasil, Bradesco, ...), preso ao pai. Cada um
  aparece como um toggle próprio, indentado sob o pai, e liga/desliga só a sua
  bandeira.

O agrupamento (clustering) acontece no PAI, não no subgrupo. É o que o
`Leaflet.FeatureGroup.SubGroup` faz: o subgrupo não desenha nada por conta
própria, ele empresta seus marcadores ao grupo pai. A consequência é
justamente a desejada — os pontos de Sicredi e Sicoob que estão na mesma cidade
entram no MESMO balão de contagem, em vez de virarem dois balões sobrepostos no
mesmo pixel, que é o que sairia se cada bandeira tivesse o seu próprio
`MarkerCluster` independente.

--------------------------------------------------------------------------
Por que os marcadores ficam no polígono do município
--------------------------------------------------------------------------

DECISÃO (acordada antes da implementação): os marcadores são posicionados no
**ponto representativo do polígono do município**, não no endereço do ponto de
atendimento. As planilhas do BACEN não publicam lat/lon, e a alternativa —
geocodificar os 7.600 endereços via Nominatim/OSM — foi descartada por três
motivos, nesta ordem:

1. o endereço publicado não é geocodificável com confiança: vem abreviado e sem
   separador ("PCA.TIRADENTES,410", "R.GAL.SAMPAIO,99"), sem bairro e com CEP
   em 0% das linhas;
2. o acerto parcial seria pior que o acerto nenhum — parte dos pontos ficaria no
   endereço exato e parte cairia no fallback do município, produzindo um mapa de
   precisão MISTA, em que o leitor não tem como saber qual é qual;
3. 7.600 consultas a 1 req/s (limite do Nominatim) são ~2h07m por execução fria,
   para um dado que o resto do pipeline já trata em nível de município — o join
   de `src.agregacao` é por código IBGE, não espacial.

Consequências que o código assume explicitamente:

* usa-se `representative_point()`, e não `centroid`: em município de forma
  irregular ou recortado pela costa o centroide pode cair FORA do próprio
  polígono, e o marcador apareceria no mar ou na cidade vizinha;
* **não há jitter**: todos os pontos de um mesmo município ficam exatamente na
  mesma coordenada. É deliberado — um deslocamento aleatório inventaria uma
  precisão que o dado não tem. A sobreposição não atrapalha porque o
  `MarkerCluster` abre os coincidentes em leque (*spiderfy*) ao clique;
* todo popup de marcador carrega o aviso de posição aproximada. O endereço real
  vai no popup como TEXTO, que é o nível de precisão que a fonte permite.

--------------------------------------------------------------------------
Coroplético reativo
--------------------------------------------------------------------------

A cor de cada município NÃO é decidida em Python. O folium compila uma
`style_function` num ``switch(feature.id)`` estático em JavaScript, o que fixa
a cor no momento da geração — e o requisito aqui é o oposto: a cor tem de
responder ao que está marcado no painel. Então a malha vai para o HTML com as
14 colunas ``total_<bandeira>`` nas propriedades de cada feição, e um
controlador em JavaScript (`_JS_CONTROLADOR`) faz o resto:

* escuta ``overlayadd``/``overlayremove`` do Leaflet e mantém o conjunto de
  bandeiras ativas, respeitando os dois níveis — subgrupo de grupo desmarcado
  não conta;
* soma, por município, só as colunas das bandeiras ativas;
* recalcula as classes, repinta os 1.191 polígonos e reescreve a legenda;
* sincroniza o painel nos **dois sentidos**: marcar ou desmarcar uma categoria
  arrasta todas as bandeiras dela; e a categoria passa a valer "alguma bandeira
  minha está marcada", de modo que marcar uma bandeira liga a categoria dela
  sozinha (sem arrastar as irmãs) e desmarcar a última desliga a categoria. A
  caixa da categoria fica em estado "traço" quando só parte das bandeiras dela
  está marcada.

As classes são **recalculadas a cada seleção**, e não fixas. Isso contraria a
regra usual de manter cortes fixos para que a mesma cor signifique sempre a
mesma coisa, e a exceção tem motivo: a amplitude varia em duas ordens de
grandeza conforme a seleção — o total geral chega a 406 pontos num município,
enquanto Sulcredi inteiro tem máximo 3. Cortes fixos que sirvam ao total
jogariam toda bandeira pequena na classe mais clara, e o mapa não mostraria
nada justamente quando o usuário filtra. O risco de ambiguidade é aceitável
aqui porque a legenda é reescrita junto, na mesma ação e na mesma tela — ao
contrário da comparação entre safras, em que o leitor não vê as duas legendas.

Com UMA única bandeira marcada, a paleta troca para uma rampa na cor da marca
(ver `CORES_BANDEIRA`); com duas ou mais, volta para YlGnBu, porque não existe
"cor da marca" de um conjunto.
"""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
from branca.element import Element, MacroElement
from folium.plugins import FeatureGroupSubGroup, MarkerCluster
from jinja2 import Template

from src import agregacao, config
from src.etl_bacen import CATEGORIA_BANCO, CATEGORIA_COOPERATIVA

_LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Coroplético
# --------------------------------------------------------------------------- #

#: Coluna do agregado usada como base do coroplético quando TODAS as bandeiras
#: estão marcadas.
#:
#: `total_geral` = agências + postos de atendimento, de bancos e de
#: cooperativas. É o total de pontos de atendimento do recorte, não uma das
#: partes. Serve de referência para o resumo impresso; no HTML o valor é
#: recalculado no cliente a partir das bandeiras ativas, e só coincide com esta
#: coluna quando nenhuma foi desmarcada.
COLUNA_COROPLETICO = "total_geral"

#: Paleta sequencial YlGnBu de 6 classes (ColorBrewer).
#:
#: Sequencial porque a variável é uma contagem que só cresce, e YlGnBu porque é
#: uma das paletas do ColorBrewer marcadas como seguras para daltonismo: a
#: progressão é monotônica em luminosidade (claro -> escuro), então continua
#: legível em escala de cinza e para deuteranopia/protanopia, onde uma paleta
#: verde-vermelho colapsaria.
PALETA_COROPLETICO = [
    "#ffffcc",
    "#c7e9b4",
    "#7fcdbb",
    "#41b6c4",
    "#2c7fb8",
    "#253494",
]

#: Número máximo de classes do coroplético, incluindo a classe do zero.
#:
#: Seis é o teto usual de classes distinguíveis numa rampa sequencial; acima
#: disso o olho não separa os passos e a legenda vira decoração. O número
#: efetivo pode ser menor: com poucos valores distintos (Sulcredi vai só até 3)
#: o controlador emite uma classe por valor em vez de inventar faixas vazias.
MAX_CLASSES = 6

#: Cor de marca de cada bandeira, usada quando ela é a ÚNICA marcada.
#:
#: São as cores de identificação visual de cada instituição, não uma paleta
#: escolhida por critério cartográfico — o objetivo é que filtrar por "Caixa"
#: pinte o mapa de azul-Caixa. Cada uma vira uma rampa sequencial em
#: `_rampa_de_cor`, porque o coroplético continua mostrando magnitude: cor
#: chapada perderia a informação de quantidade.
#:
#: ATENÇÃO à confiabilidade destes valores. Os cinco bancos, Sicredi e Sicoob
#: usam cores muito conhecidas e conferidas. Já Cresol, Ailos, Unicred,
#: Uniprime, Sulcredi e Credicoamo são APROXIMAÇÕES pela identidade visual
#: dessas marcas — plausíveis, mas não extraídas de manual de marca. Corrigir
#: qualquer uma é editar uma linha aqui; nada mais no código depende do valor.
CORES_BANDEIRA = {
    # --- Bancos --------------------------------------------------------- #
    "Banco do Brasil": "#F9DD16",  # amarelo BB
    "Bradesco": "#CC092F",  # vermelho Bradesco
    "Itaú": "#EC7000",  # laranja Itaú
    "Caixa": "#0070AF",  # azul Caixa
    "Santander": "#EC0000",  # vermelho Santander
    # --- Cooperativas --------------------------------------------------- #
    "Sicredi": "#3FA110",  # verde Sicredi
    "Sicoob": "#00AE9D",  # turquesa Sicoob
    "Cresol": "#7AB800",  # verde-limão Cresol (aproximado)
    "Ailos": "#00A9E0",  # azul Ailos (aproximado)
    "Unicred": "#005CA9",  # azul Unicred (aproximado)
    "Uniprime": "#0B4DA2",  # azul Uniprime (aproximado)
    "Sulcredi": "#8CC63F",  # verde Sulcredi (aproximado)
    "Credicoamo": "#004B8D",  # azul Credicoamo (aproximado)
    "Outra Cooperativa": "#6A5ACD",  # roxo neutro: rótulo agregado, não é marca
}

#: Cor do município cujo total é zero na seleção atual.
#:
#: Cinza, e não o passo mais claro da rampa: "nenhum ponto da seleção" é uma
#: categoria à parte, não o piso de uma escala contínua. Sem essa separação,
#: filtrar por uma bandeira pequena pintaria quase todo o Sul com a cor mais
#: clara da marca e daria a impressão de presença difusa onde não há nenhuma.
COR_ZERO = "#eceff1"

#: Cor de município sem dado (valor nulo). Distinta de `COR_ZERO`.
COR_SEM_DADO = "#e6e6e6"

# --------------------------------------------------------------------------- #
# Camadas de ponto
# --------------------------------------------------------------------------- #

#: Rótulo de cada `categoria_if` no painel de camadas (nível 1).
ROTULO_GRUPO = {
    CATEGORIA_COOPERATIVA: "Cooperativas",
    CATEGORIA_BANCO: "Bancos",
}

#: `sub_categoria` de cada grupo, na ordem em que aparecem no painel (nível 2).
#:
#: Cobre as 14 sub_categorias da safra 202606 — incluindo Uniprime, Sulcredi e
#: Credicoamo, que somam 113 pontos. Elas ganham subgrupo próprio em vez de
#: entrar em "Outra Cooperativa" para que a soma dos subgrupos de cooperativa
#: reconcilie exatamente com `total_cooperativas` do coroplético, e para que o
#: subgrupo "Outra Cooperativa" continue significando a mesma coisa que a coluna
#: `total_outra_coop` do Parquet.
#:
#: Bandeira que apareça em safra futura e não esteja aqui NÃO é descartada
#: silenciosamente: `_ordenar_sub_categorias` a acrescenta ao fim do grupo e
#: registra o caso no log, para que esta lista seja atualizada.
ORDEM_SUB_CATEGORIAS = {
    CATEGORIA_COOPERATIVA: [
        "Sicredi",
        "Sicoob",
        "Cresol",
        "Ailos",
        "Unicred",
        "Uniprime",
        "Sulcredi",
        "Credicoamo",
        "Outra Cooperativa",
    ],
    CATEGORIA_BANCO: [
        "Banco do Brasil",
        "Bradesco",
        "Itaú",
        "Caixa",
        "Santander",
    ],
}

#: Cor do marcador por grupo — a cor codifica o NÍVEL 1, não a bandeira.
#:
#: Com 14 bandeiras, 14 cores distinguíveis não existem: o mapa viraria ruído e
#: nenhuma delas seria segura para daltonismo. Aqui a cor separa só as duas
#: categorias, e a bandeira é identificada pelo nome da camada ligada no painel
#: e pelo popup. Laranja e roxo foram escolhidos por serem os dois pares mais
#: distinguíveis (Colorbrewer Dark2) que ainda contrastam com o fundo
#: amarelo-verde-azul do coroplético.
COR_GRUPO = {
    CATEGORIA_COOPERATIVA: "#d95f02",
    CATEGORIA_BANCO: "#5e3c99",
}

#: Raio do marcador em pixels. Pequeno de propósito: são 7.600 pontos e o que
#: importa na leitura ampliada é a contagem do balão de cluster, não o disco.
RAIO_MARCADOR = 5

#: Opções do `MarkerCluster` de cada grupo pai.
#:
#: `spiderfyOnMaxZoom` é o que torna viável a decisão de não usar jitter: como
#: todos os pontos de um município estão na mesma coordenada, é o leque do
#: spiderfy que permite abrir e clicar em cada um. `showCoverageOnHover` fica
#: desligado porque o polígono de cobertura desenhado no hover se confunde com o
#: contorno dos municípios do coroplético.
OPCOES_CLUSTER = {
    "chunkedLoading": True,
    "spiderfyOnMaxZoom": True,
    "showCoverageOnHover": False,
    "zoomToBoundsOnClick": True,
    "maxClusterRadius": 45,
}

# --------------------------------------------------------------------------- #
# Aparência do painel de camadas
# --------------------------------------------------------------------------- #

#: CSS do `LayerControl` e da legenda.
#:
#: A indentação do nível 2 é resolvida aqui, e não no nome da camada, porque o
#: Leaflet monta cada linha do painel como ``<label><input><span>nome</span>``:
#: espaços no nome empurrariam só o texto, deixando a caixinha de seleção
#: alinhada com a do grupo pai e destruindo a leitura de hierarquia. Com
#: ``label:has(.camada-sub)`` a linha INTEIRA — caixinha e texto — desloca.
_CSS_PAINEL = """
<style>
.leaflet-control-layers-expanded {
    max-height: 78vh;
    overflow-y: auto;
    font: 12px/1.5 -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    padding: 8px 12px 8px 8px;
}
.leaflet-control-layers-overlays label {
    display: block;
    margin: 1px 0;
}
/* Nível 1 — grupo pai: negrito e respiro acima, para abrir bloco. */
.leaflet-control-layers-overlays label:has(.camada-grupo) {
    margin-top: 9px;
    font-weight: 600;
}
/* Nível 2 — subgrupo: linha inteira indentada, com fio-guia à esquerda. */
.leaflet-control-layers-overlays label:has(.camada-sub) {
    margin-left: 9px;
    padding-left: 9px;
    border-left: 2px solid #cbd5dd;
}
.camada-contagem {
    color: #6b7785;
    font-weight: 400;
}
.legenda-mapa {
    position: fixed;
    bottom: 22px;
    left: 12px;
    z-index: 9999;
    background: rgba(255, 255, 255, 0.94);
    border: 1px solid #b8c2cc;
    border-radius: 4px;
    padding: 10px 12px;
    font: 12px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
}
.legenda-mapa h4 {
    margin: 0 0 2px;
    font-size: 12px;
}
.legenda-mapa .legenda-sub {
    margin: 0 0 7px;
    color: #6b7785;
    font-size: 11px;
}
.legenda-mapa table {
    border-collapse: collapse;
}
.legenda-mapa td {
    padding: 1px 5px 1px 0;
    white-space: nowrap;
}
.legenda-mapa .amostra {
    display: inline-block;
    width: 22px;
    height: 12px;
    border: 1px solid #7d8894;
    vertical-align: -2px;
}
.legenda-mapa .n-municipios {
    color: #6b7785;
}
.popup-municipio {
    font: 12px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    max-height: 320px;
    overflow-y: auto;
}
.popup-municipio h4 {
    margin: 0 0 6px;
    font-size: 13px;
}
.popup-municipio table {
    border-collapse: collapse;
    width: 100%;
}
.popup-municipio th {
    text-align: left;
    font-weight: 600;
    padding: 1px 8px 1px 0;
}
.popup-municipio td {
    text-align: right;
    padding: 1px 0;
}
.popup-municipio .secao {
    padding-top: 5px;
    border-top: 1px solid #dfe4e9;
    font-weight: 600;
}
.popup-municipio .bandeira th {
    font-weight: 400;
    padding-left: 10px;
}
.popup-municipio .indisponivel,
.aviso-posicao {
    color: #8a6d1f;
    font-style: italic;
}
/* Cabeçalho que o controlador reativo insere no popup/tooltip do município,
   com o total da seleção atual. */
.selecao-atual {
    margin-bottom: 5px;
    padding-bottom: 4px;
    border-bottom: 1px solid #dfe4e9;
    font: 12px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    color: #33414e;
}
/* O folium embrulha o conteúdo do GeoJsonPopup/Tooltip numa <table>; sem isto
   a tabela interna do popup herda a borda e o padding dessa casca. */
.leaflet-popup-content table td,
.leaflet-tooltip table td {
    border: none;
    padding: 0;
}
</style>
"""


# --------------------------------------------------------------------------- #
# 1. Carregamento
# --------------------------------------------------------------------------- #


def carregar_agregado(
    caminho: Path = config.ARQUIVO_AGREGADO_MUNICIPIO,
) -> gpd.GeoDataFrame:
    """Lê o agregado por município, com a geometria.

    Args:
        caminho: caminho do GeoParquet produzido por `src.agregacao`.

    Returns:
        GeoDataFrame com uma linha por município do Sul, em `config.CRS_GEOGRAFICO`.

    Raises:
        FileNotFoundError: se o arquivo não existir — rode `python -m src.agregacao`.
        KeyError: se faltar alguma coluna exigida pelo mapa.
    """
    if not caminho.exists():
        raise FileNotFoundError(
            f"Agregado não encontrado: {caminho}. "
            "Rode `python -m src.agregacao` para gerá-lo."
        )

    agregado = gpd.read_parquet(caminho)

    exigidas = {
        "municipio_ibge",
        "municipio_nome",
        "uf",
        "populacao",
        "total_bancos",
        "total_cooperativas",
        COLUNA_COROPLETICO,
    }
    faltantes = exigidas - set(agregado.columns)
    if faltantes:
        raise KeyError(
            f"Colunas ausentes em {caminho.name}: {sorted(faltantes)!r}. "
            f"Disponíveis: {sorted(agregado.columns)!r}"
        )

    # O Leaflet só entende lat/lon em graus; um agregado gravado em CRS métrico
    # renderizaria o Sul do Brasil em algum lugar do Golfo da Guiné.
    if agregado.crs is None:
        raise ValueError(
            f"{caminho.name} não declara CRS. Esperado {config.CRS_GEOGRAFICO}."
        )
    if not agregado.crs.equals(config.CRS_GEOGRAFICO):
        _LOGGER.info(
            "Reprojetando a malha de %s para %s.", agregado.crs, config.CRS_GEOGRAFICO
        )
        agregado = agregado.to_crs(config.CRS_GEOGRAFICO)

    _LOGGER.info("%d municípios carregados de %s.", len(agregado), caminho.name)
    return agregado


# --------------------------------------------------------------------------- #
# 2. Textos de popup e tooltip do município
# --------------------------------------------------------------------------- #


def _formatar_inteiro(valor) -> str:
    """Formata um inteiro no padrão brasileiro (ponto como separador de milhar).

    Args:
        valor: número a formatar; ``None``/``NaN`` é tratado pelo chamador.

    Returns:
        A string formatada, ex.: ``"1.332.570"``.
    """
    return f"{int(valor):,}".replace(",", ".")


def _texto_populacao(linha: pd.Series) -> str:
    """Devolve a população formatada, ou o aviso de dado indisponível.

    O ``populacao`` do agregado é ``Int64`` (nullable): município que a API de
    agregados do IBGE não devolveu vem como ``pd.NA`` e NÃO pode virar 0 no
    popup — zero habitante é uma afirmação sobre o município, "indisponível" é
    uma afirmação sobre o dado.

    Args:
        linha: uma linha do agregado.

    Returns:
        Ex.: ``"1.332.570 hab. (2025)"`` ou
        ``"<span class='indisponivel'>dado indisponível</span>"``.
    """
    populacao = linha["populacao"]
    if pd.isna(populacao):
        return '<span class="indisponivel">dado indisponível</span>'

    texto = f"{_formatar_inteiro(populacao)} hab."
    ano = linha.get("populacao_ano")
    if not pd.isna(ano) and str(ano).strip():
        texto += f" ({html.escape(str(ano))})"
    return texto


def _linhas_por_bandeira(linha: pd.Series, categoria: str) -> str:
    """Monta as linhas de detalhamento por `sub_categoria` de um grupo.

    Só entram as bandeiras com ao menos 1 ponto no município: listar as 14 com
    zero em quase todas transformaria o popup numa tabela de zeros, em que a
    informação — quais bandeiras existem ali — fica escondida.

    Args:
        linha: uma linha do agregado.
        categoria: `CATEGORIA_COOPERATIVA` ou `CATEGORIA_BANCO`.

    Returns:
        As ``<tr>`` do detalhamento, ou uma linha de "nenhum ponto" se o
        município não tiver nada daquele grupo.
    """
    linhas = []
    for sub_categoria in ORDEM_SUB_CATEGORIAS[categoria]:
        coluna = f"total_{agregacao._sufixo_coluna(sub_categoria)}"
        total = linha.get(coluna, 0)
        if pd.isna(total) or int(total) == 0:
            continue
        linhas.append(
            f'<tr class="bandeira"><th>{html.escape(sub_categoria)}</th>'
            f"<td>{_formatar_inteiro(total)}</td></tr>"
        )

    if not linhas:
        return '<tr class="bandeira"><th>—</th><td>nenhum ponto</td></tr>'
    return "".join(linhas)


def preparar_textos_municipio(agregado: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Acrescenta ao agregado as colunas de HTML do popup e do tooltip.

    O HTML é montado aqui, em Python, e não no template JavaScript do folium:
    `GeoJsonPopup` só sabe despejar o valor bruto de um campo numa célula de
    tabela, e o popup pedido tem estrutura (seções, detalhamento por bandeira,
    aviso de dado indisponível). Como o folium insere o valor com ``innerHTML``,
    a marcação escrita aqui é renderizada como HTML — daí o `html.escape` em
    todo texto vindo do dado.

    Args:
        agregado: saída de `carregar_agregado`.

    Returns:
        Uma CÓPIA do agregado com as colunas ``popup_html`` e ``tooltip_html``.
    """
    com_textos = agregado.copy()

    def _popup(linha: pd.Series) -> str:
        nome = html.escape(str(linha["municipio_nome"]))
        uf = html.escape(str(linha["uf"]))
        return (
            '<div class="popup-municipio">'
            f"<h4>{nome}/{uf}</h4>"
            "<table>"
            f"<tr><th>População</th><td>{_texto_populacao(linha)}</td></tr>"
            '<tr class="secao"><th>Bancos (5 grandes)</th>'
            f"<td>{_formatar_inteiro(linha['total_bancos'])}</td></tr>"
            f"{_linhas_por_bandeira(linha, CATEGORIA_BANCO)}"
            '<tr class="secao"><th>Pontos de cooperativas</th>'
            f"<td>{_formatar_inteiro(linha['total_cooperativas'])}</td></tr>"
            f"{_linhas_por_bandeira(linha, CATEGORIA_COOPERATIVA)}"
            "</table></div>"
        )

    def _tooltip(linha: pd.Series) -> str:
        nome = html.escape(str(linha["municipio_nome"]))
        uf = html.escape(str(linha["uf"]))
        return (
            f"<b>{nome}/{uf}</b><br>"
            f"Cooperativas: {_formatar_inteiro(linha['total_cooperativas'])}"
            f" &nbsp;|&nbsp; Bancos: {_formatar_inteiro(linha['total_bancos'])}"
            "<br><span style='color:#6b7785'>clique para o detalhamento</span>"
        )

    com_textos["popup_html"] = com_textos.apply(_popup, axis=1)
    com_textos["tooltip_html"] = com_textos.apply(_tooltip, axis=1)
    return com_textos


# --------------------------------------------------------------------------- #
# 3. Coroplético
# --------------------------------------------------------------------------- #


def _hex_para_rgb(cor: str) -> tuple[int, int, int]:
    """Converte ``"#rrggbb"`` na tripla RGB correspondente."""
    limpa = cor.lstrip("#")
    return tuple(int(limpa[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _misturar(rgb: tuple[int, int, int], alvo: tuple[int, int, int], fracao: float) -> tuple[int, int, int]:
    """Mistura `rgb` com `alvo` na proporção `fracao` (0 = só rgb, 1 = só alvo)."""
    return tuple(  # type: ignore[return-value]
        round(canal + (destino - canal) * fracao)
        for canal, destino in zip(rgb, alvo)
    )


def _rampa_de_cor(cor_base: str, passos: int = MAX_CLASSES) -> list[str]:
    """Gera uma rampa sequencial clara -> escura a partir de uma cor de marca.

    Interpola em RGB entre uma tinta bem clara da cor (misturada com branco) e
    uma sombra dela (misturada com preto). Como os dois extremos derivam da
    mesma cor, o matiz se mantém em toda a rampa — é a cor da marca do começo ao
    fim — e a luminosidade cai monotonicamente, que é o requisito de uma escala
    sequencial legível (e o que a mantém interpretável em tons de cinza).

    Não se usa a cor de marca crua como extremo claro: cores de marca são
    saturadas, e uma rampa que começasse nelas não teria contraste no início.

    Args:
        cor_base: cor da marca em ``"#rrggbb"``.
        passos: quantidade de cores da rampa.

    Returns:
        Lista de cores ``"#rrggbb"``, da mais clara para a mais escura.
    """
    base = _hex_para_rgb(cor_base)
    clara = _misturar(base, (255, 255, 255), 0.88)
    escura = _misturar(base, (0, 0, 0), 0.35)

    rampa = []
    for indice in range(passos):
        fracao = indice / (passos - 1) if passos > 1 else 0.0
        r, g, b = _misturar(clara, escura, fracao)
        rampa.append(f"#{r:02x}{g:02x}{b:02x}")
    return rampa


def adicionar_coropletico(
    mapa: folium.Map,
    agregado: gpd.GeoDataFrame,
) -> folium.GeoJson:
    """Adiciona a camada coroplética dos municípios, com popup e tooltip.

    Usa `folium.GeoJson` com `style_function` em vez de `folium.Choropleth`:
    o `Choropleth` monta a cor a partir de um join interno e não expõe as
    propriedades da feição, o que obrigaria a sobrepor uma segunda camada
    invisível só para carregar o popup — duas cópias da mesma geometria no HTML.

    A camada entra com ``control=False``: ela é o fundo do mapa, não uma opção.
    Desligá-la deixaria os marcadores flutuando sobre o basemap sem contexto
    territorial, e o painel de camadas deve oferecer só o que faz sentido
    desligar. A cor definida aqui é apenas o estado inicial — o controlador em
    `adicionar_controle_reativo` a substitui assim que a página carrega.

    Args:
        mapa: mapa base.
        agregado: saída de `preparar_textos_municipio`.

    Returns:
        A camada adicionada.
    """
    # As 14 colunas por bandeira vão para as propriedades da feição porque é o
    # cliente que soma a seleção atual — sem elas, filtrar por bandeira no
    # navegador seria impossível. É o que permite o coroplético reativo.
    colunas = [
        "municipio_ibge",
        "municipio_nome",
        "uf",
        "total_geral",
        "total_bancos",
        "total_cooperativas",
        *_colunas_por_bandeira(),
        "popup_html",
        "tooltip_html",
        "geometry",
    ]

    camada = folium.GeoJson(
        agregado[colunas],
        name="Municípios",
        control=False,
        style_function=lambda _feicao: {
            "fillColor": COR_ZERO,
            "color": "#8c98a4",
            "weight": 0.4,
            "fillOpacity": 0.78,
        },
        highlight_function=lambda _feicao: {"weight": 2.2, "color": "#333333"},
        tooltip=folium.GeoJsonTooltip(fields=["tooltip_html"], labels=False, sticky=True),
        popup=folium.GeoJsonPopup(fields=["popup_html"], labels=False, max_width=340),
        smooth_factor=0.5,
    )
    camada.add_to(mapa)
    return camada


def _colunas_por_bandeira() -> list[str]:
    """Nomes das colunas ``total_<bandeira>``, na ordem do painel.

    Returns:
        Uma coluna por `sub_categoria` de `ORDEM_SUB_CATEGORIAS`.
    """
    return [
        f"total_{agregacao._sufixo_coluna(sub)}"
        for subs in ORDEM_SUB_CATEGORIAS.values()
        for sub in subs
    ]


def adicionar_legenda(mapa: folium.Map) -> None:
    """Adiciona o contêiner vazio da legenda do coroplético.

    O conteúdo é escrito pelo controlador em JavaScript, e reescrito a cada
    mudança de seleção: as classes mudam junto com as bandeiras marcadas, então
    uma legenda gerada em Python descreveria a seleção inicial e mentiria a
    partir do primeiro clique.

    Args:
        mapa: mapa base.
    """
    mapa.get_root().html.add_child(
        Element('<div class="legenda-mapa" id="legenda-coropletico"></div>')
    )


# --------------------------------------------------------------------------- #
# 4. Posicionamento dos pontos no município
# --------------------------------------------------------------------------- #


def localizar_pontos(
    pontos: pd.DataFrame,
    agregado: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Atribui a cada ponto de atendimento a coordenada do seu município.

    Ver o cabeçalho do módulo para a decisão por trás disto. Em resumo: a fonte
    não traz lat/lon e o endereço publicado não é geocodificável com confiança,
    então a posição é de NÍVEL MUNICÍPIO — o ponto representativo do polígono,
    sem jitter.

    `representative_point()` é calculado sobre a geometria em graus. A
    imprecisão que isso introduz é irrelevante aqui: o resultado só precisa cair
    dentro do polígono certo, e o método garante isso por construção — ao
    contrário do centroide, que em município recortado pela costa ou em forma de
    "C" pode cair fora da própria área.

    Args:
        pontos: saída de `agregacao.carregar_pontos`.
        agregado: saída de `carregar_agregado`.

    Returns:
        Cópia de `pontos` com `latitude` e `longitude`, sem as linhas cujo
        `municipio_ibge` não existe na malha (reportadas no log).
    """
    representativos = agregado.geometry.representative_point()
    coordenadas = pd.DataFrame(
        {
            "municipio_ibge": agregado["municipio_ibge"].to_numpy(),
            "latitude": representativos.y.to_numpy(),
            "longitude": representativos.x.to_numpy(),
        }
    )

    localizados = pontos.merge(coordenadas, on="municipio_ibge", how="left")

    sem_coordenada = localizados["latitude"].isna()
    if int(sem_coordenada.sum()):
        # Mesma condição que `agregacao.relatar_cobertura` já vigia do outro
        # lado: código IBGE do BACEN inexistente na divisão territorial vigente.
        _LOGGER.warning(
            "%d ponto(s) com `municipio_ibge` fora da malha ficaram FORA do mapa. "
            "Códigos: %r",
            int(sem_coordenada.sum()),
            sorted(localizados.loc[sem_coordenada, "municipio_ibge"].unique())[:10],
        )
        localizados = localizados[~sem_coordenada]

    return localizados.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 5. Camadas de ponto em dois níveis
# --------------------------------------------------------------------------- #


def _popup_ponto(linha: pd.Series) -> str:
    """Monta o HTML do popup de um ponto de atendimento.

    O aviso de posição aproximada é parte fixa do popup, não um detalhe de
    rodapé: o marcador está no município, não no endereço, e quem clica precisa
    saber disso sem ter de conhecer a decisão de implementação.

    Args:
        linha: uma linha de `localizar_pontos`.

    Returns:
        O HTML do popup.
    """
    nome = html.escape(str(linha["nome_instalacao"]))
    instituicao = html.escape(str(linha["nome_instituicao"]))
    sub_categoria = html.escape(str(linha["sub_categoria"]))
    tipo = html.escape(str(linha["tipo_instalacao"]))
    endereco = html.escape(str(linha["endereco"]))
    municipio = html.escape(str(linha["municipio"]))
    uf = html.escape(str(linha["uf"]))

    return (
        '<div class="popup-municipio">'
        f"<h4>{nome}</h4>"
        f"<div><b>{sub_categoria}</b> &middot; {tipo}</div>"
        f'<div style="color:#6b7785">{instituicao}</div>'
        f"<div style='padding-top:5px'>{endereco}<br>{municipio}/{uf}</div>"
        '<div class="aviso-posicao" style="padding-top:6px">'
        "Posição aproximada (nível município): o marcador está no município, "
        "não no endereço acima.</div>"
        "</div>"
    )


def _ordenar_sub_categorias(
    presentes: set[str],
    categoria: str,
) -> list[str]:
    """Ordena as sub_categorias de um grupo, sem descartar bandeira nova.

    Args:
        presentes: sub_categorias que aparecem no dado para esta categoria.
        categoria: `CATEGORIA_COOPERATIVA` ou `CATEGORIA_BANCO`.

    Returns:
        As sub_categorias presentes, na ordem de `ORDEM_SUB_CATEGORIAS`, com as
        desconhecidas em ordem alfabética ao fim.
    """
    previstas = ORDEM_SUB_CATEGORIAS[categoria]
    conhecidas = [sub for sub in previstas if sub in presentes]
    novas = sorted(presentes - set(previstas))
    if novas:
        _LOGGER.warning(
            "sub_categoria(s) de %r fora de ORDEM_SUB_CATEGORIAS: %r. "
            "Ganharam subgrupo ao fim do painel; atualize a constante.",
            categoria,
            novas,
        )
    return conhecidas + novas


def adicionar_camadas_de_pontos(
    mapa: folium.Map,
    localizados: pd.DataFrame,
) -> dict[str, list[str]]:
    """Monta a hierarquia de camadas de ponto: grupo pai -> subgrupo por bandeira.

    Nível 1: um `MarkerCluster` por `categoria_if`, que é o toggle "tudo de uma
    vez". Nível 2: um `FeatureGroupSubGroup` por `sub_categoria`, preso ao pai.

    Os dois níveis são adicionados AO MAPA (e não o subgrupo ao pai): é assim
    que o `Leaflet.FeatureGroup.SubGroup` funciona e é o que faz cada um
    aparecer como uma linha própria no `LayerControl`. O subgrupo não desenha
    nada sozinho — ele injeta os marcadores no cluster do pai —, então desmarcar
    o pai remove todos os pontos do grupo, e desmarcar um subgrupo remove só a
    sua bandeira, recontando os balões de cluster.

    Args:
        mapa: mapa base.
        localizados: saída de `localizar_pontos`.

    Returns:
        Um dicionário por grupo, com o rótulo, o objeto da camada-pai e a lista
        de subgrupos (rótulo, objeto da camada, coluna do agregado e contagem).
        O controlador reativo precisa dos OBJETOS, não só dos nomes: é por eles
        que o JavaScript identifica qual camada o usuário marcou.
    """
    estrutura: list[dict] = []

    for categoria, rotulo_grupo in ROTULO_GRUPO.items():
        do_grupo = localizados[localizados["categoria_if"] == categoria]
        if do_grupo.empty:
            _LOGGER.warning("Nenhum ponto na categoria %r; grupo omitido.", categoria)
            continue

        cor = COR_GRUPO[categoria]
        sub_categorias = _ordenar_sub_categorias(
            set(do_grupo["sub_categoria"].dropna().unique()), categoria
        )

        # --- Nível 1: o grupo pai ------------------------------------------ #
        grupo_pai = MarkerCluster(
            name=(
                f'<span class="camada-grupo">{html.escape(rotulo_grupo)}</span>'
                f'<span class="camada-contagem"> ({len(do_grupo)})</span>'
            ),
            options=OPCOES_CLUSTER,
            control=True,
            show=True,
        )
        grupo_pai.add_to(mapa)

        # --- Nível 2: um subgrupo por bandeira ----------------------------- #
        subgrupos_do_grupo: list[dict] = []
        for sub_categoria in sub_categorias:
            da_bandeira = do_grupo[do_grupo["sub_categoria"] == sub_categoria]
            subgrupo = FeatureGroupSubGroup(
                grupo_pai,
                name=(
                    f'<span class="camada-sub">{html.escape(sub_categoria)}</span>'
                    f'<span class="camada-contagem"> ({len(da_bandeira)})</span>'
                ),
                control=True,
                show=True,
            )
            subgrupo.add_to(mapa)

            for _, ponto in da_bandeira.iterrows():
                folium.CircleMarker(
                    location=(ponto["latitude"], ponto["longitude"]),
                    radius=RAIO_MARCADOR,
                    color="#ffffff",
                    weight=1,
                    fill=True,
                    fill_color=cor,
                    fill_opacity=0.9,
                    popup=folium.Popup(_popup_ponto(ponto), max_width=300),
                    tooltip=(
                        f"{html.escape(str(ponto['nome_instalacao']))} "
                        f"({html.escape(str(sub_categoria))})"
                    ),
                ).add_to(subgrupo)

            subgrupos_do_grupo.append(
                {
                    "rotulo": sub_categoria,
                    "camada": subgrupo,
                    "coluna": f"total_{agregacao._sufixo_coluna(sub_categoria)}",
                    "pontos": len(da_bandeira),
                }
            )

        estrutura.append(
            {
                "categoria": categoria,
                "rotulo": rotulo_grupo,
                "camada": grupo_pai,
                "pontos": len(do_grupo),
                "subs": subgrupos_do_grupo,
            }
        )
        _LOGGER.info(
            "Grupo %r: %d pontos em %d subgrupos.",
            rotulo_grupo,
            len(do_grupo),
            len(sub_categorias),
        )

    return estrutura


# --------------------------------------------------------------------------- #
# 6. Mapa base e controle de camadas
# --------------------------------------------------------------------------- #


def criar_mapa_base() -> folium.Map:
    """Cria o mapa Folium centrado no Sul, no zoom inicial da configuração.

    Returns:
        O `folium.Map`, já com o CSS do painel e da legenda no ``<head>``.
    """
    mapa = folium.Map(
        location=config.CENTRO_MAPA,
        zoom_start=config.ZOOM_INICIAL,
        tiles=config.TILES_PADRAO,
        control_scale=True,
    )
    mapa.get_root().header.add_child(Element(_CSS_PAINEL))
    return mapa


#: Controlador do painel: cascata dos toggles e coroplético reativo.
#:
#: `__CONFIG__` é trocado por um JSON com os nomes das variáveis JavaScript que
#: o folium gera para cada camada, as colunas de cada bandeira e as paletas.
#: A substituição é por `str.replace`, e não `format`/f-string, porque o corpo
#: é JavaScript e está cheio de chaves.
_JS_CONTROLADOR = """
(function () {
    "use strict";
    var cfg = __CONFIG__;

    /* Os três objetos são referenciados pelo IDENTIFICADOR que o folium gera,
       e não por `window[nome]`. Motivo: o folium declara o LayerControl com
       `let`, e `let` no topo de um script não cria propriedade em `window` —
       a busca devolvia `undefined` e a cascata silenciosamente não se ligava a
       nada. Como este bloco é emitido no mesmo <script>, o identificador está
       em escopo, valendo tanto para os `var` das camadas quanto para o `let`
       do painel. */
    var mapa = __MAPA__;
    var geo = __GEOJSON__;
    var controle = __CONTROLE__;
    if (!mapa || !geo || !controle) {
        console.error("controlador: mapa, camada de municípios ou painel não encontrados");
        return;
    }

    /* --- Estado da seleção, espelhando os dois níveis do painel --------- */
    var meta = new Map();
    var grupoAtivo = {};
    var subAtivo = {};
    cfg.grupos.forEach(function (g) {
        var camadaGrupo = window[g.camada];
        if (camadaGrupo) {
            meta.set(camadaGrupo, {tipo: "grupo", id: g.id});
            grupoAtivo[g.id] = mapa.hasLayer(camadaGrupo);
        }
        g.subs.forEach(function (s) {
            var camadaSub = window[s.camada];
            if (camadaSub) {
                meta.set(camadaSub, {tipo: "sub", id: s.rotulo});
                subAtivo[s.rotulo] = mapa.hasLayer(camadaSub);
            }
        });
    });

    /* Subgrupo de grupo desmarcado NÃO conta: o pai manda, igual aos pontos. */
    function selecao() {
        var sel = [];
        cfg.grupos.forEach(function (g) {
            if (!grupoAtivo[g.id]) { return; }
            g.subs.forEach(function (s) {
                if (subAtivo[s.rotulo]) { sel.push(s); }
            });
        });
        return sel;
    }

    var atual = {sel: [], cortes: [], cores: [], max: 0};

    function totalDe(props) {
        var t = 0;
        for (var i = 0; i < atual.sel.length; i++) {
            t += (props[atual.sel[i].coluna] || 0);
        }
        return t;
    }

    /* Limites inferiores das classes dos valores POSITIVOS. O zero fica de
       fora: tem cor própria e não é o piso da escala. */
    function calcularCortes(valores) {
        var positivos = valores.filter(function (v) { return v > 0; })
                               .sort(function (a, b) { return a - b; });
        if (!positivos.length) { return []; }

        var distintos = [];
        for (var i = 0; i < positivos.length; i++) {
            if (distintos[distintos.length - 1] !== positivos[i]) {
                distintos.push(positivos[i]);
            }
        }
        var n = cfg.maxClasses - 1;
        /* Poucos valores distintos (Sulcredi vai só até 3): uma classe por
           valor, em vez de faixas que ficariam vazias. */
        if (distintos.length <= n) { return distintos; }

        var cortes = [];
        for (var k = 0; k < n; k++) {
            var v = positivos[Math.floor(k * positivos.length / n)];
            if (!cortes.length || v > cortes[cortes.length - 1]) { cortes.push(v); }
        }

        /* Quantis colapsam em distribuição muito assimétrica: filtrando por
           Caixa, mais de 80% dos municípios atendidos têm exatamente 1 ponto,
           então TODOS os cortes caem em 1, sobra uma classe só e o mapa fica
           chapado — escondendo que a capital tem 65. Quando isso acontece,
           completa-se com uma progressão geométrica até o máximo, que é a
           escala adequada para contagem de cauda longa. */
        var max = positivos[positivos.length - 1];
        var ultimo = cortes[cortes.length - 1];
        if (cortes.length < n && max > ultimo) {
            var faltam = n - cortes.length;
            /* O expoente é g/(faltam+1), e não g/faltam, para que nenhum corte
               caia EM cima do máximo: um corte igual ao máximo cria uma classe
               final com um município só — o próprio recordista — e desperdiça
               a cor mais escura num caso isolado em vez de na cauda toda. */
            for (var g = 1; g <= faltam; g++) {
                var razao = Math.pow(max / ultimo, g / (faltam + 1));
                var corte = Math.round(ultimo * razao);
                if (corte > cortes[cortes.length - 1] && corte < max) {
                    cortes.push(corte);
                }
            }
        }
        return cortes;
    }

    function amostrar(rampa, n) {
        if (n <= 1) { return [rampa[rampa.length - 1]]; }
        var out = [];
        for (var i = 0; i < n; i++) {
            out.push(rampa[Math.round(i * (rampa.length - 1) / (n - 1))]);
        }
        return out;
    }

    function corDe(total) {
        if (!(total > 0)) { return cfg.corZero; }
        var i = 0;
        while (i + 1 < atual.cortes.length && total >= atual.cortes[i + 1]) { i++; }
        return atual.cores[i] || cfg.corZero;
    }

    function estilo(feature) {
        return {
            fillColor: corDe(feature.__total || 0),
            color: "#8c98a4",
            weight: 0.4,
            fillOpacity: 0.78
        };
    }

    function rotuloSelecao() {
        if (!atual.sel.length) { return "nenhuma bandeira"; }
        if (atual.sel.length === 1) { return atual.sel[0].rotulo; }
        if (atual.sel.length === cfg.totalBandeiras) { return "todas as bandeiras"; }
        return atual.sel.length + " bandeiras";
    }

    function desenharLegenda(valores) {
        var el = document.getElementById("legenda-coropletico");
        if (!el) { return; }

        if (!atual.sel.length) {
            el.innerHTML = "<h4>Nenhuma bandeira marcada</h4>" +
                '<p class="legenda-sub">Marque uma camada no painel à direita ' +
                "para colorir o mapa.</p>";
            return;
        }

        var soma = 0, nZero = 0;
        for (var i = 0; i < valores.length; i++) {
            soma += valores[i];
            if (valores[i] === 0) { nZero++; }
        }

        var linhas = '<tr><td><span class="amostra" style="background:' +
            cfg.corZero + '"></span></td><td>0</td>' +
            '<td class="n-municipios">' + nZero + " mun.</td></tr>";

        for (var c = 0; c < atual.cortes.length; c++) {
            var lo = atual.cortes[c];
            var ultimo = (c + 1 === atual.cortes.length);
            var hi = ultimo ? null : atual.cortes[c + 1] - 1;
            var rotulo;
            if (ultimo) {
                rotulo = (lo >= atual.max) ? String(lo) : (lo + " ou mais");
            } else {
                rotulo = (hi > lo) ? (lo + " a " + hi) : String(lo);
            }
            var n = 0;
            for (var j = 0; j < valores.length; j++) {
                if (valores[j] >= lo && (ultimo || valores[j] <= hi)) { n++; }
            }
            linhas += '<tr><td><span class="amostra" style="background:' +
                atual.cores[c] + '"></span></td><td>' + rotulo + "</td>" +
                '<td class="n-municipios">' + n + " mun.</td></tr>";
        }

        el.innerHTML = "<h4>" + rotuloSelecao() + "</h4>" +
            '<p class="legenda-sub">pontos de atendimento por município' +
            " &middot; " + soma.toLocaleString("pt-BR") + " no total</p>" +
            "<table>" + linhas + "</table>";
    }

    function recalcular() {
        atual.sel = selecao();

        var valores = [];
        atual.max = 0;
        geo.eachLayer(function (camada) {
            var t = totalDe(camada.feature.properties);
            camada.feature.__total = t;
            if (t > atual.max) { atual.max = t; }
            valores.push(t);
        });

        atual.cortes = calcularCortes(valores);
        var rampa = (atual.sel.length === 1 && cfg.rampas[atual.sel[0].rotulo])
            ? cfg.rampas[atual.sel[0].rotulo]
            : cfg.rampaPadrao;
        atual.cores = amostrar(rampa, atual.cortes.length);

        /* Trocar `options.style` também, e não só repintar: o handler de
           mouseout chama resetStyle, que relê options.style. Sem isto, tirar o
           mouse de um município o devolveria à cor da seleção anterior. */
        geo.options.style = estilo;
        geo.setStyle(estilo);

        desenharLegenda(valores);
    }

    /* --- Popup e tooltip ganham o total da seleção atual ---------------- */
    function cabecalho(camada) {
        var t = totalDe(camada.feature.properties);
        return '<div class="selecao-atual"><b>' +
            t.toLocaleString("pt-BR") + "</b> ponto" + (t === 1 ? "" : "s") +
            " &middot; " + rotuloSelecao() + "</div>";
    }

    function envolver(balao) {
        if (!balao) { return; }
        var original = balao.getContent();
        if (typeof original !== "function") { return; }
        balao.setContent(function (camada) {
            var caixa = L.DomUtil.create("div");
            caixa.innerHTML = cabecalho(camada);
            caixa.appendChild(original(camada));
            return caixa;
        });
    }
    envolver(geo.getPopup());
    envolver(geo.getTooltip());

    /* Um clique numa categoria dispara um evento por bandeira (são até 9).
       Sem coalescer, o coroplético seria reclassificado e repintado 9 vezes
       para produzir o mesmo resultado final. */
    var pendente = null;
    function agendarRecalculo() {
        if (pendente) { return; }
        pendente = setTimeout(function () { pendente = null; recalcular(); }, 0);
    }

    mapa.on("overlayadd overlayremove", function (e) {
        var m = meta.get(e.layer);
        if (!m) { return; }
        var ativo = (e.type === "overlayadd");
        if (m.tipo === "grupo") { grupoAtivo[m.id] = ativo; } else { subAtivo[m.id] = ativo; }
        agendarRecalculo();
    });

    /* --------------------------------------------------------------------
       Cascata: marcar/desmarcar a categoria arrasta as bandeiras dela
       -------------------------------------------------------------------- */

    /* O Leaflet guarda um <input> por camada em `_layerControlInputs`, cada um
       carimbado com o id da camada correspondente. É por aí que se chega da
       camada até a caixa de seleção dela no painel. */
    function inputDe(camada) {
        var inputs = (controle && controle._layerControlInputs) || [];
        var id = L.Util.stamp(camada);
        for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].layerId === id) { return inputs[i]; }
        }
        return null;
    }

    var caixas = [];
    cfg.grupos.forEach(function (g) {
        var caixaGrupo = inputDe(window[g.camada]);
        if (!caixaGrupo) { return; }
        var caixasFilhas = [];
        g.subs.forEach(function (s) {
            var c = inputDe(window[s.camada]);
            if (c) { caixasFilhas.push(c); }
        });
        caixas.push({grupo: caixaGrupo, filhas: caixasFilhas});
    });

    /* Caixa da categoria em estado "traço" quando ela está ligada mas nem
       todas as bandeiras dela estão. Sem isso a caixa marcada afirmaria algo
       falso: que o grupo inteiro está no mapa. */
    function atualizarParciais() {
        caixas.forEach(function (c) {
            var ligadas = 0;
            for (var i = 0; i < c.filhas.length; i++) {
                if (c.filhas[i].checked) { ligadas++; }
            }
            c.grupo.indeterminate = c.grupo.checked && ligadas < c.filhas.length;
        });
    }

    caixas.forEach(function (c) {
        /* Estes ouvintes rodam DEPOIS do handler do próprio Leaflet, que já
           tratou o clique na categoria. Marcar as filhas aqui e reprocessar
           com `_onInputClick` sincroniza tudo numa passada só — e os eventos
           overlayadd/overlayremove que ela dispara alimentam o coroplético. */
        c.grupo.addEventListener("click", function () {
            var ligar = c.grupo.checked;
            c.filhas.forEach(function (filha) { filha.checked = ligar; });
            if (controle && controle._onInputClick) { controle._onInputClick(); }
            atualizarParciais();
        });
        /* Sentido inverso: a categoria acompanha as bandeiras. Marcar uma
           bandeira com a categoria desligada não mostrava nada — o pai
           sobrepõe o filho, então o clique parecia não fazer efeito. Aqui a
           categoria passa a valer "alguma bandeira minha está marcada".

           `checked` é atribuído em vez de clicado DE PROPÓSITO: atribuir não
           dispara evento de clique, então o ouvinte de cascata acima não roda.
           Um `.click()` aqui ligaria todas as bandeiras irmãs — o usuário
           marcou uma, e voltaria com nove. */
        c.filhas.forEach(function (filha) {
            filha.addEventListener("click", function () {
                var alguma = false;
                for (var i = 0; i < c.filhas.length; i++) {
                    if (c.filhas[i].checked) { alguma = true; break; }
                }
                if (c.grupo.checked !== alguma) {
                    c.grupo.checked = alguma;
                    if (controle && controle._onInputClick) { controle._onInputClick(); }
                }
                atualizarParciais();
            });
        });
    });

    atualizarParciais();
    recalcular();
})();
"""


class _ControladorReativo(MacroElement):
    """Envelope que emite `_JS_CONTROLADOR` no lugar certo do HTML.

    Existe por uma questão de ORDEM. O controlador referencia as variáveis
    JavaScript que o folium cria para o mapa e para cada camada
    (``map_ab12...``, ``feature_group_sub_group_cd34...``), e portanto tem de
    aparecer depois delas no arquivo. Adicionar o script direto em
    ``get_root().script`` não serve: os filhos diretos daquela seção são
    escritos ANTES de todos os blocos que o folium gera durante a renderização,
    e o controlador acabava no topo, referenciando variáveis ainda não
    declaradas — falhando com "mapa ou camada não encontrados".

    Como `MacroElement` filho do mapa, o bloco entra na ordem de inserção,
    junto com as camadas. Adicionado por último, sai por último.
    """

    _template = Template(
        "{% macro script(this, kwargs) %}{{ this.js | safe }}{% endmacro %}"
    )

    def __init__(self, js: str):
        super().__init__()
        self._name = "ControladorReativo"
        self.js = js


def adicionar_controle_reativo(
    mapa: folium.Map,
    coropletico: folium.GeoJson,
    estrutura: list[dict],
    controle: folium.LayerControl,
) -> None:
    """Injeta o controlador do painel: cascata dos toggles e coroplético reativo.

    Ver "Coroplético reativo" no cabeçalho do módulo para o porquê de a cor ser
    decidida no cliente e não em Python, e `_ControladorReativo` para o porquê
    de o script precisar ser o último elemento adicionado ao mapa.

    Args:
        mapa: mapa com todas as camadas já adicionadas.
        coropletico: camada devolvida por `adicionar_coropletico`.
        estrutura: saída de `adicionar_camadas_de_pontos`.
        controle: `LayerControl` já adicionado — o controlador precisa dele
            para achar a caixa de seleção de cada camada e fazer a cascata.
    """
    grupos = [
        {
            "id": grupo["rotulo"],
            "camada": grupo["camada"].get_name(),
            "subs": [
                {
                    "rotulo": sub["rotulo"],
                    "camada": sub["camada"].get_name(),
                    "coluna": sub["coluna"],
                }
                for sub in grupo["subs"]
            ],
        }
        for grupo in estrutura
    ]

    configuracao = {
        "grupos": grupos,
        "maxClasses": MAX_CLASSES,
        "corZero": COR_ZERO,
        "rampaPadrao": PALETA_COROPLETICO,
        "rampas": {
            sub["rotulo"]: _rampa_de_cor(CORES_BANDEIRA[sub["rotulo"]])
            for grupo in estrutura
            for sub in grupo["subs"]
            if sub["rotulo"] in CORES_BANDEIRA
        },
        "totalBandeiras": sum(len(grupo["subs"]) for grupo in estrutura),
    }

    script = (
        _JS_CONTROLADOR.replace("__CONFIG__", json.dumps(configuracao, ensure_ascii=False))
        .replace("__MAPA__", mapa.get_name())
        .replace("__GEOJSON__", coropletico.get_name())
        .replace("__CONTROLE__", controle.get_name())
    )
    mapa.add_child(_ControladorReativo(script))


def adicionar_controle_de_camadas(mapa: folium.Map) -> folium.LayerControl:
    """Adiciona o `LayerControl` aberto, com a hierarquia indentada.

    Tem de ser a ÚLTIMA coisa adicionada ao mapa: o `LayerControl` varre os
    filhos já presentes para montar a lista, e camada adicionada depois dele não
    aparece no painel.

    Args:
        mapa: mapa com todas as camadas já adicionadas.

    Returns:
        O controle adicionado.
    """
    # `collapsed=False` deixa o painel aberto: com 16 camadas em dois níveis, a
    # hierarquia é a própria legenda das camadas e não deveria depender de o
    # leitor descobrir que precisa passar o mouse sobre um ícone.
    controle = folium.LayerControl(collapsed=False, position="topright")
    controle.add_to(mapa)
    return controle


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #


def gera_mapa(
    caminho_agregado: Path = config.ARQUIVO_AGREGADO_MUNICIPIO,
    caminho_pontos: Path = config.ARQUIVO_IF_SUL_CATEGORIZADO,
    destino: Path = config.ARQUIVO_MAPA,
) -> Path:
    """Gera o mapa interativo completo e grava o HTML.

    Etapas, na ordem:

    1. lê o agregado por município (com geometria) e o dataset de pontos;
    2. monta o mapa base centrado no Sul, no zoom de `config.ZOOM_INICIAL`;
    3. adiciona o coroplético por `total_cooperativas`, com popup e tooltip por
       município (nome, população — ou "dado indisponível" —, total de bancos,
       total de pontos de cooperativas e o detalhamento por `sub_categoria`);
    4. adiciona a legenda discreta do coroplético;
    5. posiciona cada ponto de atendimento no polígono do seu município e monta
       as camadas em dois níveis (grupo pai por `categoria_if`, subgrupo por
       `sub_categoria`);
    6. adiciona o `LayerControl` aberto e grava o HTML.

    Args:
        caminho_agregado: GeoParquet de `src.agregacao`.
        caminho_pontos: Parquet categorizado de `src.etl_bacen`.
        destino: caminho do HTML de saída; o diretório é criado se faltar.

    Returns:
        O caminho do HTML gravado.

    Raises:
        FileNotFoundError: se algum dos dois Parquet de entrada não existir.
    """
    agregado = carregar_agregado(caminho_agregado)
    pontos = agregacao.carregar_pontos(caminho_pontos)

    mapa = criar_mapa_base()

    com_textos = preparar_textos_municipio(agregado)
    coropletico = adicionar_coropletico(mapa, com_textos)
    adicionar_legenda(mapa)

    localizados = localizar_pontos(pontos, agregado)
    estrutura = adicionar_camadas_de_pontos(mapa, localizados)

    # Depois de TODAS as camadas — ver `adicionar_controle_de_camadas`.
    controle = adicionar_controle_de_camadas(mapa)
    # E o controlador por último de todos: ele referencia as variáveis das
    # camadas e do próprio painel, que precisam já estar declaradas no script.
    adicionar_controle_reativo(mapa, coropletico, estrutura, controle)

    destino.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(str(destino))

    imprimir_resumo(agregado, localizados, estrutura, destino)
    return destino


def imprimir_resumo(
    agregado: gpd.GeoDataFrame,
    localizados: pd.DataFrame,
    estrutura: list[dict],
    destino: Path,
) -> None:
    """Imprime o que foi renderizado, para conferência manual.

    Args:
        agregado: saída de `carregar_agregado`.
        localizados: saída de `localizar_pontos`.
        estrutura: saída de `adicionar_camadas_de_pontos`.
        destino: caminho do HTML gravado.
    """
    print("=" * 78)
    print("MAPA — output/mapa_if_sul.html")
    print("=" * 78)
    print(f"Centro {config.CENTRO_MAPA}, zoom {config.ZOOM_INICIAL}, "
          f"base {config.TILES_PADRAO!r}\n")

    valores = agregado[COLUNA_COROPLETICO]
    print(
        f"-- coroplético (reativo): base {COLUNA_COROPLETICO} em "
        f"{len(agregado)} municípios --"
    )
    print(
        f"   {int(valores.sum())} pontos, máximo de {int(valores.max())} num "
        f"município, {int((valores == 0).sum())} municípios em zero"
    )
    print(
        "   as classes e a legenda são recalculadas no navegador a cada "
        "mudança de seleção"
    )
    sem_populacao = int(agregado["populacao"].isna().sum())
    print(f"   população indisponível em {sem_populacao} município(s)\n")

    print(f"-- camadas de ponto: {len(localizados)} marcadores --")
    for grupo in estrutura:
        print(f"   [1] {grupo['rotulo']} ({grupo['pontos']})")
        for sub in grupo["subs"]:
            cor = CORES_BANDEIRA.get(sub["rotulo"], "—")
            print(
                f"        [2] {sub['rotulo']:<20} ({sub['pontos']:>4})  "
                f"cor de marca {cor}"
            )
    print()

    tamanho_mb = destino.stat().st_size / 1024 / 1024
    print(f"Gravado em: {destino}  ({tamanho_mb:.1f} MB)")


def main() -> None:
    """Ponto de entrada para ``python -m src.mapa``."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s %(name)s: %(message)s"
    )
    gera_mapa()


if __name__ == "__main__":
    main()
