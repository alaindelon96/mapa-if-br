"""Mapa interativo dos pontos de atendimento financeiro da Região Sul.

Monta, sobre um mapa Folium centrado em RS/SC/PR, duas leituras complementares
do mesmo recorte:

* um **coroplético** por município, colorido pelo total de pontos de
  atendimento (agências + postos), lido de
  ``data/processed/agregado_municipio.parquet``;
* uma **camada de pontos em dois níveis**, lida de
  ``data/processed/pontos_geocodificados.parquet``, com um ponto por
  atendimento, cada um na coordenada que `src.cnefe` resolveu para ele.

O coroplético é **reativo**: ele mostra sempre o total das bandeiras marcadas no
painel de camadas, e se repinta a cada clique. Ver "Coroplético reativo" abaixo.

Saída: ``output/mapa_if_sul.html`` (ver `config.ARQUIVO_MAPA`).

Uso (a partir da raiz do projeto, com o venv ativo)::

    python -m src.mapa

--------------------------------------------------------------------------
Por que as camadas de ponto são hierárquicas (e não uma lista plana)
--------------------------------------------------------------------------

Uma lista plana de 14 camadas obrigaria 14 cliques para esconder "todos os
bancos". A estrutura aqui é de dois níveis, montada com `folium.FeatureGroup`:

* **Nível 1 — grupo pai**: um por `categoria_if` ("Bancos" e "Cooperativas").
  É o toggle principal e não desenha nada por conta própria: quem o marca ou
  desmarca no painel arrasta junto todas as bandeiras da categoria, pela
  cascata em `_JS_CONTROLADOR`.
* **Nível 2 — subgrupo**: um por `sub_categoria` (Sicredi, Sicoob, ... / Banco
  do Brasil, Bradesco, ...), com os marcadores daquela bandeira. Aparece como
  um toggle próprio, indentado sob o pai.

--------------------------------------------------------------------------
Agrupamento: balão de contagem longe, marcador individual perto
--------------------------------------------------------------------------

Os pontos são agrupados por `MarkerCluster`: no zoom de região, um balão com a
contagem no lugar de dezenas de discos sobrepostos; conforme se aproxima, os
balões se partem em balões menores, e a partir de `ZOOM_SEM_CLUSTER` cada ponto
vira um marcador próprio.

O que NÃO existe mais é o *spiderfy* — o leque com uma linha ligando cada ponto
ao centro do balão. Ele era necessário enquanto todos os pontos de um município
ficavam na MESMA coordenada: sem abrir o leque, não havia como clicar em nada.
Agora que `src.cnefe` dá coordenada própria a cada ponto, aproximar o zoom já
separa os marcadores no lugar onde eles realmente estão, que é uma informação
melhor do que a ordem arbitrária das pernas do leque.

Por isso `disableClusteringAtZoom` é obrigatório aqui, e não um refinamento:
com o spiderfy desligado, um balão que sobrevivesse até o zoom máximo seria um
beco sem saída — os pontos dentro dele não teriam como ser abertos. Desligar o
agrupamento a partir de um zoom garante que todo ponto é alcançável.

O mapa é criado com ``prefer_canvas=True``: nos zoons sem agrupamento os 7.600
marcadores são desenhados num único elemento *canvas* em vez de 7.600 nós SVG,
que é o que mantém a navegação fluida.

Os poucos pontos que ainda caem na mesma coordenada exata (dois atendimentos no
mesmo endereço, ou o fallback de município) são abertos num leque determinístico
por `cnefe.desempatar_coincidentes`, com raio sempre menor que a incerteza do
nível de precisão que o ponto declara.

--------------------------------------------------------------------------
Modo de visão: município OU ponto de atendimento
--------------------------------------------------------------------------

O topo do painel traz um seletor com as duas leituras do mesmo recorte
(`MODOS_VISAO`): **nível cidade**, só os polígonos, e **nível pontos de
atendimento**, só os marcadores. O mapa abre em `MODO_INICIAL`.

O que o modo NÃO faz é mexer na seleção de bandeiras. As duas leituras são da
mesma seleção, com efeitos diferentes: no nível cidade as bandeiras marcadas
decidem a COR dos municípios, no nível de pontos decidem QUAIS marcadores
aparecem. Por isso a lista de bandeiras continua ativa nos dois modos, e trocar
de modo preserva o que estava marcado.

A troca é feita escondendo *panes* do Leaflet, e não adicionando e removendo
camadas — a diferença é de correção, não de estilo, e está explicada em
`_JS_CONTROLADOR`: mexer nas camadas por fora do painel faz o `L.Control.Layers`
se reconstruir e recopiar cada caixa de seleção da presença da camada no mapa,
o que desmarcava as 14 bandeiras ao entrar no modo cidade. Para que o
coroplético possa ser escondido sem levar os marcadores junto, ele recebe um
pane próprio — por padrão os dois desenhariam no mesmo ``overlayPane`` e, com
`prefer_canvas`, no mesmo ``<canvas>``.

--------------------------------------------------------------------------
Cor do marcador: a bandeira, e não a categoria
--------------------------------------------------------------------------

Cada ponto é pintado com a cor de marca da sua bandeira (`CORES_BANDEIRA`) —
Sicredi verde, Caixa azul, Bradesco vermelho —, com o contorno derivado da
mesma cor, escurecido.

Isso REVERTE a escolha anterior, em que a cor separava apenas as duas
categorias (bancos x cooperativas) e a bandeira só aparecia no painel e no
popup. A objeção que motivava aquela escolha continua válida e vale registrar:
14 matizes não são 14 cores distinguíveis, várias das marcas se aproximam entre
si (o verde do Sicredi e o verde-limão da Cresol; os três azuis de Unicred,
Uniprime e Credicoamo) e nenhuma paleta de 14 é segura para daltonismo. Quem
precisar comparar DUAS bandeiras específicas não deve tentar fazê-lo a olho
sobre as 14 ligadas — deve desligar as outras no painel, que é a leitura para a
qual a hierarquia de camadas existe.

O que a mudança compra em troca: com todas ligadas, dá para ver onde uma marca
domina e onde ela não chega, o que a codificação por categoria não mostrava de
jeito nenhum. Duas decisões seguram a legibilidade:

* o marcador cresceu para `RAIO_MARCADOR` px — num disco de 5 px o matiz
  praticamente não se lê;
* cada linha do painel ganhou a amostra da sua cor (`.camada-cor`), para que a
  correspondência cor -> bandeira não dependa de memória.

--------------------------------------------------------------------------
Precisão da posição dos marcadores
--------------------------------------------------------------------------

A posição vem de `src.cnefe`, que casa o endereço publicado pelo BACEN — com o
CEP, que a fonte preenche em 100% das linhas — contra o Cadastro Nacional de
Endereços do Censo 2022. Cada ponto carrega o nível que o resolveu, de
`endereço` a `município`, e esse nível vai NO POPUP, junto do endereço.

Mostrar o nível é o que torna aceitável um mapa de precisão mista: parte dos
pontos está no imóvel exato e parte no miolo urbano do município, e o leitor
consegue saber de qual se trata em vez de supor que todos valem o mesmo. Ver o
cabeçalho de `src.cnefe` para a cadeia completa e para as taxas medidas.

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
import re
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
from branca.element import Element, MacroElement
from folium.plugins import FeatureGroupSubGroup, MarkerCluster
from jinja2 import Template

from src import agregacao, cnefe, config
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

#: Cor de RESERVA do marcador, por categoria.
#:
#: O marcador é pintado com a cor de marca da sua bandeira (`CORES_BANDEIRA`);
#: este de-para só entra quando a bandeira não tem cor cadastrada — o que
#: acontece se uma safra futura trouxer uma marca nova, caso em que os pontos
#: dela saem em laranja (cooperativa) ou roxo (banco) em vez de sumirem ou
#: quebrarem a geração.
#:
#: Laranja e roxo foram escolhidos por serem os dois pares mais distinguíveis
#: (Colorbrewer Dark2) que ainda contrastam com o fundo amarelo-verde-azul do
#: coroplético.
COR_GRUPO = {
    CATEGORIA_COOPERATIVA: "#d95f02",
    CATEGORIA_BANCO: "#5e3c99",
}

#: Identificadores dos dois modos de visão.
MODO_CIDADE = "cidade"
MODO_PONTOS = "pontos"

#: Rótulo e explicação de cada modo, na ordem em que aparecem no seletor.
#:
#: A segunda linha existe porque a mesma lista de bandeiras serve aos dois
#: modos com efeitos diferentes — no modo cidade ela decide a COR dos
#: municípios, no modo pontos decide QUAIS marcadores aparecem. Sem a legenda,
#: marcar uma bandeira no modo cidade parece não fazer nada (o efeito está no
#: coroplético, não numa camada que aparece ou some).
MODOS_VISAO = [
    {
        "id": MODO_CIDADE,
        "rotulo": "Nível cidade",
        "dica": "as bandeiras marcadas colorem os municípios",
    },
    {
        "id": MODO_PONTOS,
        "rotulo": "Nível pontos de atendimento",
        "dica": "as bandeiras marcadas mostram seus pontos",
    },
]

#: Modo em que o mapa abre.
#:
#: `MODO_CIDADE`, porque o mapa abre no zoom da região inteira: ali os 7.600
#: pontos estão todos agrupados em balões e o que se lê de fato é a cor dos
#: municípios. O modo de pontos é a leitura de quem já aproximou.
MODO_INICIAL = MODO_CIDADE

#: Raio do marcador em pixels.
#:
#: Sete, e não cinco: com o marcador pintado na cor da marca, o disco deixou de
#: ser só um alvo de clique e passou a CARREGAR informação — e num disco de 5 px
#: não se distingue o verde do Sicredi do verde-limão da Cresol. O tamanho é o
#: que torna a cor legível.
#:
#: Não muito mais que isso, porém: os discos só aparecem todos juntos a partir
#: de `ZOOM_SEM_CLUSTER`, mas ali o centro de uma cidade grande já os põe lado a
#: lado, e um raio maior os fundiria numa mancha.
RAIO_MARCADOR = 7

#: Espessura do contorno do marcador, em pixels.
LARGURA_CONTORNO_MARCADOR = 1.2

#: Quanto o contorno do marcador é escurecido em relação ao preenchimento.
#:
#: O contorno é derivado da própria cor da marca, e não fixo em branco, porque
#: nenhuma cor fixa serve para as 14: sobre o basemap claro, um contorno branco
#: some no amarelo do Banco do Brasil, e um contorno preto engrossa demais as
#: marcas escuras. Escurecer a própria cor dá borda a todas na mesma medida.
ESCURECIMENTO_CONTORNO = 0.45

#: Zoom a partir do qual o agrupamento é desligado e todo ponto vira marcador.
#:
#: Dezessete é onde uma quadra urbana ocupa a tela inteira (~1 m por pixel nesta
#: latitude). Dois pontos separados pelo raio mínimo de desempate — 8 m, o caso
#: de dois atendimentos no mesmo endereço — ficam a ~8 px um do outro aqui, já
#: distinguíveis, e completamente separados nos zooms seguintes.
#:
#: Abaixo disso o agrupamento ainda vale a pena: no zoom de cidade, o centro de
#: Porto Alegre tem dezenas de pontos em poucos quarteirões, e sem balão eles
#: viram uma mancha sólida em que não se lê quantidade nenhuma.
ZOOM_SEM_CLUSTER = 17

#: Opções do `MarkerCluster` de cada grupo pai.
#:
#: `spiderfyOnMaxZoom` DESLIGADO é o pedido central desta configuração: ele é
#: que desenhava as linhas ligando os pontos ao centro do balão. Ver o cabeçalho
#: do módulo para por que ele pôde ser desligado e por que
#: `disableClusteringAtZoom` passa a ser obrigatório junto.
#:
#: `zoomToBoundsOnClick` é o que substitui o leque na hora de abrir um balão:
#: clicar aproxima até o retângulo que contém os pontos dele, e a partir de
#: `ZOOM_SEM_CLUSTER` eles aparecem separados. `showCoverageOnHover` fica
#: desligado porque o polígono de cobertura desenhado no hover se confunde com o
#: contorno dos municípios do coroplético.
OPCOES_CLUSTER = {
    "chunkedLoading": True,
    "spiderfyOnMaxZoom": False,
    "showCoverageOnHover": False,
    "zoomToBoundsOnClick": True,
    "disableClusteringAtZoom": ZOOM_SEM_CLUSTER,
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
/* Seletor de modo de visão, no topo do painel: é a escolha de PRIMEIRO
   nível, então vem antes da lista de bandeiras e separada dela por um fio. */
.modo-visao {
    margin: 0 0 6px;
    padding-bottom: 7px;
    border-bottom: 1px solid #b8c2cc;
}
.modo-visao label {
    display: block;
    margin: 3px 0;
    font-weight: 600;
    cursor: pointer;
}
.modo-visao input {
    margin: 0 5px 0 0;
    vertical-align: -1px;
}
.modo-visao .modo-dica {
    display: block;
    margin-left: 18px;
    color: #6b7785;
    font-weight: 400;
    font-size: 11px;
}
/* Amostra da cor da bandeira, do lado do nome dela no painel. Redonda e do
   tamanho do marcador, para ser lida como "este é o ponto no mapa". */
.camada-cor {
    display: inline-block;
    width: 11px;
    height: 11px;
    margin-right: 5px;
    border: 1px solid;
    border-radius: 50%;
    vertical-align: -1px;
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
/* Procedência da coordenada nos dois níveis precisos: informação de rodapé,
   não advertência — daí o cinza em vez do âmbar de `.aviso-posicao`. */
.procedencia {
    color: #6b7785;
    font-size: 11px;
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
# 4. Pontos já geocodificados
# --------------------------------------------------------------------------- #


def carregar_pontos_geocodificados(
    caminho: Path = config.ARQUIVO_PONTOS_GEOCODIFICADOS,
) -> pd.DataFrame:
    """Lê os pontos de atendimento com coordenada e nível de precisão.

    Este módulo não geocodifica nada: ele consome o que `src.cnefe` resolveu.
    A separação é intencional — a geocodificação depende de ~580 MB de CNEFE em
    cache e leva minutos, enquanto o desenho do mapa é iterado dezenas de vezes
    durante um ajuste de cor ou de popup.

    Args:
        caminho: Parquet produzido por `src.cnefe`.

    Returns:
        DataFrame com uma linha por ponto de atendimento, incluindo
        `latitude`, `longitude` e `precisao`.

    Raises:
        FileNotFoundError: se o arquivo não existir — rode `python -m src.cnefe`.
        KeyError: se faltar alguma coluna exigida pelo mapa.
    """
    if not caminho.exists():
        raise FileNotFoundError(
            f"Pontos geocodificados não encontrados: {caminho}. "
            "Rode `python -m src.cnefe` para gerá-los."
        )

    pontos = pd.read_parquet(caminho)

    exigidas = {
        "latitude",
        "longitude",
        "precisao",
        "categoria_if",
        "sub_categoria",
        "nome_instalacao",
    }
    faltantes = exigidas - set(pontos.columns)
    if faltantes:
        raise KeyError(
            f"Colunas ausentes em {caminho.name}: {sorted(faltantes)!r}. "
            "Regere o arquivo com `python -m src.cnefe`."
        )

    _LOGGER.info("%d pontos geocodificados carregados de %s.", len(pontos), caminho.name)
    return pontos


# --------------------------------------------------------------------------- #
# 5. Camadas de ponto em dois níveis
# --------------------------------------------------------------------------- #


def _texto_endereco(linha: pd.Series) -> str:
    """Monta a linha de endereço do popup, com número e bairro quando houver.

    Args:
        linha: uma linha de `carregar_pontos_geocodificados`.

    Returns:
        O endereço em uma linha, ex.: ``"R.URUGUAI,185 — CENTRO, 90010-901"``.
    """
    endereco = str(linha["endereco"])
    partes = [html.escape(endereco)]

    numero = linha.get("numero")
    # O número só é acrescentado quando NÃO está embutido no endereço: a fonte
    # grava "PCA.TIRADENTES,410" numas linhas e o número em coluna própria em
    # outras, e repeti-lo produziria "PCA.TIRADENTES,410, 410".
    #
    # A conferência é contra o trecho DEPOIS da última vírgula, e não contra o
    # endereço inteiro: um "in" solto acharia o "15" de "RUA 15 DE NOVEMBRO" e
    # engoliria o número 15 do imóvel.
    if not pd.isna(numero) and str(numero).strip():
        embutido = re.search(r",\s*(\d+)", endereco)
        if not (embutido and embutido.group(1) == str(numero).strip()):
            partes.append(f", {html.escape(str(numero))}")

    complemento = []
    bairro = linha.get("bairro")
    if not pd.isna(bairro) and str(bairro).strip():
        complemento.append(html.escape(str(bairro)))
    cep = linha.get("cep")
    if not pd.isna(cep) and str(cep).strip():
        complemento.append(html.escape(str(cep)))
    if complemento:
        partes.append(" — " + ", ".join(complemento))

    return "".join(partes)


def _popup_ponto(linha: pd.Series) -> str:
    """Monta o HTML do popup de um ponto de atendimento.

    O nível de precisão é parte fixa do popup, e não um detalhe de rodapé: os
    pontos deste mapa NÃO têm todos a mesma precisão — a maioria está no imóvel
    ou na rua, uma minoria só no município —, e quem clica precisa saber em qual
    caso está sem ter de conhecer a implementação. Ver `src.cnefe`.

    Args:
        linha: uma linha de `carregar_pontos_geocodificados`.

    Returns:
        O HTML do popup.
    """
    nome = html.escape(str(linha["nome_instalacao"]))
    instituicao = html.escape(str(linha["nome_instituicao"]))
    sub_categoria = html.escape(str(linha["sub_categoria"]))
    tipo = html.escape(str(linha["tipo_instalacao"]))
    municipio = html.escape(str(linha["municipio"]))
    uf = html.escape(str(linha["uf"]))

    precisao = str(linha.get("precisao", cnefe.PRECISAO_MUNICIPIO))
    descricao = cnefe.DESCRICAO_PRECISAO.get(precisao, precisao)
    # Só os dois níveis frouxos ganham destaque de aviso; nos dois precisos a
    # informação é apenas a procedência da coordenada.
    classe = (
        "aviso-posicao"
        if precisao in (cnefe.PRECISAO_LOCALIDADE, cnefe.PRECISAO_MUNICIPIO)
        else "procedencia"
    )

    return (
        '<div class="popup-municipio">'
        f"<h4>{nome}</h4>"
        f"<div><b>{sub_categoria}</b> &middot; {tipo}</div>"
        f'<div style="color:#6b7785">{instituicao}</div>'
        f"<div style='padding-top:5px'>{_texto_endereco(linha)}<br>{municipio}/{uf}</div>"
        f'<div class="{classe}" style="padding-top:6px">'
        f"Posição: {html.escape(descricao)}.</div>"
        "</div>"
    )


def _tooltip_ponto(linha: pd.Series) -> str:
    """Monta o identificador que aparece ao passar o mouse sobre um ponto.

    Curto de propósito: o tooltip segue o cursor e some, então ele responde só
    "o que é este ponto" — bandeira e nome da instalação. O resto está no popup,
    a um clique.

    Args:
        linha: uma linha de `carregar_pontos_geocodificados`.

    Returns:
        O HTML do tooltip.
    """
    return (
        f'<b>{html.escape(str(linha["sub_categoria"]))}</b> &middot; '
        f'{html.escape(str(linha["tipo_instalacao"]))}<br>'
        f'{html.escape(str(linha["nome_instalacao"]))}'
    )


def _escurecer(cor: str, fracao: float = ESCURECIMENTO_CONTORNO) -> str:
    """Devolve a cor misturada com preto, para usar como contorno.

    Args:
        cor: cor de preenchimento em ``"#rrggbb"``.
        fracao: 0 devolve a cor original, 1 devolve preto.

    Returns:
        A cor escurecida em ``"#rrggbb"``.
    """
    r, g, b = _misturar(_hex_para_rgb(cor), (0, 0, 0), fracao)
    return f"#{r:02x}{g:02x}{b:02x}"


def cor_do_marcador(sub_categoria: str, categoria: str) -> str:
    """Cor de preenchimento do marcador de uma bandeira.

    Args:
        sub_categoria: a bandeira, ex.: ``"Sicredi"``.
        categoria: `CATEGORIA_COOPERATIVA` ou `CATEGORIA_BANCO`, usada como
            reserva quando a bandeira não tem cor de marca cadastrada.

    Returns:
        A cor em ``"#rrggbb"``.
    """
    cor = CORES_BANDEIRA.get(sub_categoria)
    if cor is None:
        _LOGGER.warning(
            "Bandeira %r sem cor em CORES_BANDEIRA; usando a cor de reserva de %r.",
            sub_categoria,
            categoria,
        )
        return COR_GRUPO[categoria]
    return cor


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
    sua bandeira, recontando os balões.

    O agrupamento acontecer no PAI, e não em cada subgrupo, é o que faz os
    pontos de Sicredi e Sicoob vizinhos entrarem no MESMO balão de contagem, em
    vez de virarem dois balões sobrepostos no mesmo pixel.

    Args:
        mapa: mapa base.
        localizados: saída de `carregar_pontos_geocodificados`.

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
            cor = cor_do_marcador(sub_categoria, categoria)
            contorno = _escurecer(cor)
            subgrupo = FeatureGroupSubGroup(
                grupo_pai,
                # A amostra de cor é o que torna a pintura por marca legível:
                # 14 cores no mapa sem nenhuma chave seriam adivinhação, e o
                # painel já lista exatamente as 14 bandeiras, uma por linha.
                name=(
                    f'<span class="camada-cor" style="background:{cor};'
                    f'border-color:{contorno}"></span>'
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
                    color=contorno,
                    weight=LARGURA_CONTORNO_MARCADOR,
                    fill=True,
                    fill_color=cor,
                    fill_opacity=0.92,
                    popup=folium.Popup(_popup_ponto(ponto), max_width=300),
                    tooltip=folium.Tooltip(_tooltip_ponto(ponto), sticky=True),
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
    # `prefer_canvas` desenha os 7.600 marcadores num único canvas em vez de um
    # nó SVG por ponto. Sem cluster, todos existem no DOM ao mesmo tempo, e é
    # essa opção que mantém a navegação fluida — ver o cabeçalho do módulo.
    mapa = folium.Map(
        location=config.CENTRO_MAPA,
        zoom_start=config.ZOOM_INICIAL,
        tiles=config.TILES_PADRAO,
        control_scale=True,
        prefer_canvas=True,
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

    /* O coroplético ganha um painel só dele para que o modo de visão possa
       escondê-lo sem esconder os marcadores. Por padrão os dois desenhariam no
       mesmo `overlayPane` — e, com `prefer_canvas`, no mesmo <canvas>, onde não
       há como separar um do outro.

       zIndex 350: acima dos ladrilhos (200) e abaixo dos marcadores (400/600),
       que é a ordem de leitura — o polígono é fundo, o ponto é figura.

       A troca de painel exige retirar e repor a camada, e isso acontece AQUI,
       antes de o controlador guardar qualquer referência às caixas do painel
       de camadas: retirar e repor faz o `L.Control.Layers` se reconstruir, e
       referências guardadas antes disso apontariam para elementos descartados. */
    var PANE_COROPLETICO = "coropletico";
    if (!mapa.getPane(PANE_COROPLETICO)) {
        mapa.createPane(PANE_COROPLETICO).style.zIndex = 350;
    }
    geo.eachLayer(function (camada) { camada.options.pane = PANE_COROPLETICO; });
    if (mapa.hasLayer(geo)) {
        mapa.removeLayer(geo);
        mapa.addLayer(geo);
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

    /* --------------------------------------------------------------------
       Modo de visão: polígonos OU marcadores
       --------------------------------------------------------------------

       O modo controla só a VISIBILIDADE das duas representações. Quem está
       marcado no painel continua valendo para as duas: no modo cidade a
       seleção de bandeiras colore o coroplético, no modo pontos ela decide
       quais marcadores aparecem. Por isso a lista de bandeiras não é
       desabilitada em nenhum dos dois. */
    var modo = cfg.modoInicial;

    /* Trocar de modo NÃO adiciona nem remove camada nenhuma: o que muda é a
       visibilidade dos painéis (*panes*) do Leaflet em que elas desenham.
       Essa distinção não é estilo, é correção.

       Adicionar ou remover camada por fora do painel de camadas faz o
       `L.Control.Layers` se reconstruir inteiro — ele escuta `layeradd` e
       `layerremove` e, quando a mudança não veio de um clique nele mesmo,
       refaz a lista do zero. Refazer a lista descarta os <input> atuais e
       recria cada um com `checked` copiado de `mapa.hasLayer(camada)`. O
       resultado era o modo cidade, que tira todos os marcadores do mapa,
       DESMARCAR as 14 bandeiras do painel e levar junto a cor do coroplético
       — e ainda deixar a cascata presa a caixas que não estavam mais na tela.

       Com painéis, a divisão de responsabilidade fica limpa: a caixa marcada
       diz quais bandeiras estão selecionadas (e o Leaflet cuida disso sozinho,
       como sempre cuidou), e o modo diz qual das duas representações da mesma
       seleção está à vista. */
    function aplicarModo() {
        var mostrarPontos = (modo === cfg.modoPontos);

        /* `visibility:hidden`, e não `display:none`, porque ele some com o
           conteúdo SEM tirar o elemento do fluxo: o <canvas> em que o
           coroplético é desenhado mantém posição e dimensão, e o Leaflet
           continua redesenhando nele durante os zooms feitos no outro modo —
           voltar para o modo cidade mostra o enquadramento atual, nunca uma
           tela em branco esperando o próximo redesenho. (Conferido no
           navegador: com o painel escondido, o canvas do coroplético seguiu
           sendo repintado a cada mudança de enquadramento.)

           E, como elemento invisível não recebe evento de mouse, o mesmo
           ajuste impede que o tooltip de município apareça no modo de
           pontos, onde não há município desenhado para explicar de onde ele
           veio. */
        var esconder = function (painel, oculto) {
            if (painel) { painel.style.visibility = oculto ? "hidden" : ""; }
        };
        esconder(mapa.getPane(PANE_COROPLETICO), mostrarPontos);
        esconder(mapa.getPane("overlayPane"), !mostrarPontos);
        esconder(mapa.getPane("markerPane"), !mostrarPontos);

        var legenda = document.getElementById("legenda-coropletico");
        if (legenda) { legenda.style.display = mostrarPontos ? "none" : ""; }
    }

    function montarSeletorDeModo() {
        var painel = controle.getContainer && controle.getContainer();
        if (!painel) { return; }
        var lista = painel.querySelector(".leaflet-control-layers-list") || painel;

        var caixa = L.DomUtil.create("div", "modo-visao");
        var html = "";
        cfg.modos.forEach(function (m) {
            html += '<label><input type="radio" name="modo-visao" value="' +
                m.id + '"' + (m.id === modo ? " checked" : "") + ">" +
                m.rotulo + '<span class="modo-dica">' + m.dica + "</span></label>";
        });
        caixa.innerHTML = html;
        lista.insertBefore(caixa, lista.firstChild);

        /* Sem isto, clicar no seletor também chega ao mapa embaixo dele — o
           que faz o mapa dar zoom no duplo clique e arrastar no drag. */
        L.DomEvent.disableClickPropagation(caixa);

        var opcoes = caixa.querySelectorAll("input");
        for (var i = 0; i < opcoes.length; i++) {
            opcoes[i].addEventListener("change", function () {
                modo = this.value;
                aplicarModo();
            });
        }
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
    /* Mesma informação de `caixas`, achatada e com o identificador de cada
       camada ao lado do seu <input>. É o que permite ler a seleção direto das
       caixas — ver `lerPainel`. */
    var caixasPorId = [];
    cfg.grupos.forEach(function (g) {
        var caixaGrupo = inputDe(window[g.camada]);
        if (!caixaGrupo) { return; }
        caixasPorId.push({tipo: "grupo", id: g.id, input: caixaGrupo});
        var caixasFilhas = [];
        g.subs.forEach(function (s) {
            var c = inputDe(window[s.camada]);
            if (c) {
                caixasFilhas.push(c);
                caixasPorId.push({tipo: "sub", id: s.rotulo, input: c});
            }
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

    /* --------------------------------------------------------------------
       A seleção é lida das CAIXAS, não da presença das camadas no mapa
       --------------------------------------------------------------------

       O controlador nasceu escutando overlayadd/overlayremove, o que bastava
       enquanto marcar uma caixa sempre implicava adicionar a camada. Com o
       seletor de modo isso deixou de valer: no modo cidade nenhum marcador
       está no mapa, então DESmarcar uma bandeira manda o Leaflet remover uma
       camada que já não estava lá — `removeLayer` não faz nada e, o que
       importa aqui, NÃO dispara `overlayremove`. O coroplético continuava
       pintado com a bandeira que o usuário acabara de desligar.

       Ler as caixas resolve nos dois sentidos e independe do modo: a caixa é
       a intenção do usuário, a camada no mapa é só a consequência dela no
       modo atual. Os eventos continuam escutados para as mudanças que não
       passam por clique. */
    function lerPainel() {
        caixasPorId.forEach(function (c) {
            if (c.tipo === "grupo") { grupoAtivo[c.id] = c.input.checked; }
            else { subAtivo[c.id] = c.input.checked; }
        });
    }

    /* Registrado DEPOIS dos ouvintes de cascata acima, portanto roda depois
       deles: quando este chega, as caixas já estão no estado final. */
    caixasPorId.forEach(function (c) {
        c.input.addEventListener("click", function () {
            lerPainel();
            agendarRecalculo();
        });
    });

    lerPainel();
    atualizarParciais();
    montarSeletorDeModo();
    recalcular();
    aplicarModo();
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
        "modos": [
            {
                "id": modo["id"],
                "rotulo": html.escape(modo["rotulo"]),
                "dica": html.escape(modo["dica"]),
            }
            for modo in MODOS_VISAO
        ],
        "modoInicial": MODO_INICIAL,
        "modoPontos": MODO_PONTOS,
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
    caminho_pontos: Path = config.ARQUIVO_PONTOS_GEOCODIFICADOS,
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
    5. lê os pontos já geocodificados por `src.cnefe` e monta as camadas em
       dois níveis (grupo pai por `categoria_if`, subgrupo por
       `sub_categoria`);
    6. adiciona o `LayerControl` aberto e grava o HTML.

    Args:
        caminho_agregado: GeoParquet de `src.agregacao`.
        caminho_pontos: Parquet geocodificado de `src.cnefe`.
        destino: caminho do HTML de saída; o diretório é criado se faltar.

    Returns:
        O caminho do HTML gravado.

    Raises:
        FileNotFoundError: se algum dos dois Parquet de entrada não existir.
    """
    agregado = carregar_agregado(caminho_agregado)
    localizados = carregar_pontos_geocodificados(caminho_pontos)

    mapa = criar_mapa_base()

    com_textos = preparar_textos_municipio(agregado)
    coropletico = adicionar_coropletico(mapa, com_textos)
    adicionar_legenda(mapa)

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
        localizados: saída de `carregar_pontos_geocodificados`.
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

    print(f"-- posição dos marcadores (ver src/cnefe.py) --")
    contagem = localizados["precisao"].value_counts()
    for nivel in cnefe.ORDEM_PRECISAO:
        quantos = int(contagem.get(nivel, 0))
        if quantos:
            print(f"   {nivel:<12} {quantos:>5}  {quantos/len(localizados):>6.1%}")
    print()

    print(f"-- camadas de ponto: {len(localizados)} marcadores --")
    for grupo in estrutura:
        print(f"   [1] {grupo['rotulo']} ({grupo['pontos']})")
        for sub in grupo["subs"]:
            cor = cor_do_marcador(sub["rotulo"], grupo["categoria"])
            print(
                f"        [2] {sub['rotulo']:<20} ({sub['pontos']:>4})  "
                f"marcador {cor}"
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
