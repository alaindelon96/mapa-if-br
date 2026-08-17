"""Mapa interativo dos pontos de atendimento financeiro da Região Sul.

Monta, sobre um mapa Folium centrado em RS/SC/PR, duas leituras complementares
do mesmo recorte:

* um **coroplético** por município, colorido por `total_cooperativas`, lido de
  ``data/processed/agregado_municipio.parquet``;
* uma **camada de pontos em dois níveis**, lida de
  ``data/processed/if_sul_categorizado.parquet``, com um ponto por atendimento.

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
"""

from __future__ import annotations

import html
import logging
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
from branca.colormap import StepColormap
from branca.element import Element
from folium.plugins import FeatureGroupSubGroup, MarkerCluster

from src import agregacao, config
from src.etl_bacen import CATEGORIA_BANCO, CATEGORIA_COOPERATIVA

_LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Coroplético
# --------------------------------------------------------------------------- #

#: Coluna do agregado que dá a cor de cada município.
COLUNA_COROPLETICO = "total_cooperativas"

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

#: Limite INFERIOR de cada classe (fechado à esquerda, aberto à direita).
#:
#: Classes fixas, e não quantis calculados a cada execução: com quantis, a mesma
#: cor significaria coisas diferentes entre duas safras e a comparação visual
#: entre elas seria falsa. Os cortes vêm da distribuição observada na safra
#: 202606 (mediana 2, máximo 71, cauda muito longa à direita) e distribuem os
#: 1.191 municípios em classes de tamanho comparável: 33 / 306 / 315 / 349 /
#: 132 / 56. Uma escala linear de 0 a 71 jogaria ~97% dos municípios nas duas
#: cores mais claras e o mapa não mostraria nada.
LIMITES_CLASSES = [0, 1, 2, 3, 5, 10]

#: Rótulo de cada classe na legenda, na mesma ordem de `LIMITES_CLASSES`.
ROTULOS_CLASSES = ["0", "1", "2", "3 a 4", "5 a 9", "10 ou mais"]

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


def criar_escala_cores() -> StepColormap:
    """Monta a escala de cores discreta do coroplético.

    Returns:
        `StepColormap` de 6 classes sobre `PALETA_COROPLETICO`, com os cortes de
        `LIMITES_CLASSES`. O limite superior é aberto: qualquer valor acima do
        último corte recebe a cor mais escura.
    """
    # O `index` do StepColormap tem n+1 posições: os n limites inferiores mais o
    # teto da última classe. Um teto alto e fixo mantém a escala idêntica entre
    # safras, mesmo que apareça um município com mais pontos que o atual máximo.
    teto = 10_000
    return StepColormap(
        colors=PALETA_COROPLETICO,
        index=[*LIMITES_CLASSES, teto],
        vmin=LIMITES_CLASSES[0],
        vmax=teto,
    )


def _cor_do_municipio(valor, escala: StepColormap) -> str:
    """Devolve a cor de preenchimento de um município.

    Args:
        valor: contagem em `COLUNA_COROPLETICO`.
        escala: saída de `criar_escala_cores`.

    Returns:
        Cor em notação CSS; cinza claro quando o valor é nulo, para que
        "sem dado" nunca se confunda com a cor da classe 0.
    """
    if valor is None or pd.isna(valor):
        return "#e6e6e6"
    return escala(float(valor))


def adicionar_coropletico(
    mapa: folium.Map,
    agregado: gpd.GeoDataFrame,
) -> folium.GeoJson:
    """Adiciona a camada coroplética dos municípios, com popup e tooltip.

    Usa `folium.GeoJson` com `style_function` em vez de `folium.Choropleth`:
    o `Choropleth` monta a cor a partir de um join interno e não expõe as
    propriedades da feição, o que obrigaria a sobrepor uma segunda camada
    invisível só para carregar o popup — duas cópias da mesma geometria no HTML.

    Args:
        mapa: mapa base.
        agregado: saída de `preparar_textos_municipio`.

    Returns:
        A camada adicionada.
    """
    escala = criar_escala_cores()

    # Só as colunas usadas pelo mapa entram no GeoJSON embutido no HTML: as 20
    # colunas de contagem já estão resumidas no `popup_html` e repeti-las em
    # 1.191 feições engordaria o arquivo à toa.
    colunas = [
        "municipio_ibge",
        "municipio_nome",
        "uf",
        COLUNA_COROPLETICO,
        "popup_html",
        "tooltip_html",
        "geometry",
    ]

    camada = folium.GeoJson(
        agregado[colunas],
        name=(
            '<span class="camada-grupo">Municípios — cooperativas</span>'
            '<span class="camada-contagem"> (coroplético)</span>'
        ),
        style_function=lambda feicao: {
            "fillColor": _cor_do_municipio(
                feicao["properties"][COLUNA_COROPLETICO], escala
            ),
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


def adicionar_legenda(mapa: folium.Map, agregado: gpd.GeoDataFrame) -> None:
    """Adiciona a legenda do coroplético, com a contagem de municípios por classe.

    Legenda montada à mão em vez da barra automática do `branca`: a escala é
    discreta e de classes desiguais (0, 1, 2, 3-4, 5-9, 10+), e a barra contínua
    do branca posicionaria os rótulos proporcionalmente ao valor, sugerindo que
    a classe "10 ou mais" ocupa quase toda a escala. A contagem ao lado de cada
    faixa mostra quantos municípios caem nela, que é o que responde "essa cor
    escura é rara ou comum?".

    Args:
        mapa: mapa base.
        agregado: saída de `carregar_agregado`.
    """
    valores = agregado[COLUNA_COROPLETICO]
    limites_com_teto = [*LIMITES_CLASSES, float("inf")]

    linhas = []
    for indice, (cor, rotulo) in enumerate(zip(PALETA_COROPLETICO, ROTULOS_CLASSES)):
        na_classe = int(
            (
                (valores >= limites_com_teto[indice])
                & (valores < limites_com_teto[indice + 1])
            ).sum()
        )
        linhas.append(
            f'<tr><td><span class="amostra" style="background:{cor}"></span></td>'
            f"<td>{rotulo}</td>"
            f'<td class="n-municipios">{na_classe} mun.</td></tr>'
        )

    legenda = (
        '<div class="legenda-mapa">'
        "<h4>Pontos de cooperativas</h4>"
        '<p class="legenda-sub">por município &middot; '
        f"{len(agregado)} municípios do Sul</p>"
        "<table>" + "".join(linhas) + "</table>"
        "</div>"
    )
    mapa.get_root().html.add_child(Element(legenda))


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
        Dicionário ``{rótulo do grupo: [sub_categorias, ...]}``, para o resumo.
    """
    estrutura: dict[str, list[str]] = {}

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

        estrutura[rotulo_grupo] = sub_categorias
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
    adicionar_coropletico(mapa, com_textos)
    adicionar_legenda(mapa, agregado)

    localizados = localizar_pontos(pontos, agregado)
    estrutura = adicionar_camadas_de_pontos(mapa, localizados)

    # Depois de TODAS as camadas — ver `adicionar_controle_de_camadas`.
    adicionar_controle_de_camadas(mapa)

    destino.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(str(destino))

    imprimir_resumo(agregado, localizados, estrutura, destino)
    return destino


def imprimir_resumo(
    agregado: gpd.GeoDataFrame,
    localizados: pd.DataFrame,
    estrutura: dict[str, list[str]],
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
    print(f"-- coroplético: {COLUNA_COROPLETICO} em {len(agregado)} municípios --")
    limites = [*LIMITES_CLASSES, float("inf")]
    for indice, rotulo in enumerate(ROTULOS_CLASSES):
        na_classe = int(
            ((valores >= limites[indice]) & (valores < limites[indice + 1])).sum()
        )
        print(f"   {PALETA_COROPLETICO[indice]}  {rotulo:>10}  {na_classe:>5} mun.")
    sem_populacao = int(agregado["populacao"].isna().sum())
    print(f"   população indisponível em {sem_populacao} município(s)\n")

    print(f"-- camadas de ponto: {len(localizados)} marcadores --")
    for rotulo_grupo, sub_categorias in estrutura.items():
        do_grupo = localizados[
            localizados["sub_categoria"].isin(sub_categorias)
        ]
        print(f"   [1] {rotulo_grupo} ({len(do_grupo)})")
        for sub_categoria in sub_categorias:
            n = int((localizados["sub_categoria"] == sub_categoria).sum())
            print(f"        [2] {sub_categoria:<20} ({n})")
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
