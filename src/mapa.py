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

As duas leituras não são entregues soltas numa tela cheia de mapa: elas vão
dentro de uma **moldura de página** — marca, título, quatro indicadores, barra
de controles, cartão do mapa e coluna de bandeiras e de ranking. Ver "Moldura
da página" abaixo e `adicionar_moldura`.

Saída: ``output/mapa_if_sul.html`` (ver `config.ARQUIVO_MAPA`).

Uso (a partir da raiz do projeto, com o venv ativo)::

    python -m src.mapa

--------------------------------------------------------------------------
Moldura da página
--------------------------------------------------------------------------

O arquivo gerado é lido por quem decide onde abrir, fechar ou reforçar ponto de
atendimento — não por quem sabe operar um mapa. A moldura existe para responder,
sem clique nenhum, as três perguntas que essa leitura faz antes de qualquer
outra: de quando é o dado, quanto existe e onde falta.

* a **faixa de marca** traz o símbolo do cooperativismo e o selo da safra
  (`config.DATA_DADOS`), porque a data do dado é a primeira coisa perguntada
  sobre um mapa recebido pronto;
* os **quatro indicadores** respondem à mesma seleção que colore o mapa, e são
  reescritos a cada clique: pontos de atendimento, municípios atendidos,
  municípios SEM atendimento e a população que mora neles. Os dois últimos são
  o motivo de a faixa existir — o coroplético mostra onde a rede está, e os
  indicadores dizem o tamanho do que ela deixa de fora;
* a **barra de controles** reúne as duas escolhas de escopo (o modo de visão e
  o estado) e a busca de município, tudo numa linha só, acima do mapa;
* a **coluna lateral** tem as bandeiras (o painel de camadas do Leaflet,
  encaixado ali) e o ranking dos municípios de maior presença, que responde
  "onde a rede se concentra" — pergunta que um coroplético não responde, porque
  as manchas escuras caem nas capitais, que o leitor já conhece.

O mapa e o painel de camadas nascem soltos e são MOVIDOS para dentro dos
cartões pelo controlador, na carga da página; `adicionar_moldura` explica por
que o HTML não pode já nascer montado.

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
Modo de visão: município, ponto de atendimento, ou os dois
--------------------------------------------------------------------------

A barra de controles abre com um seletor das três leituras do mesmo recorte
(`MODOS_VISAO`): **municípios**, com os polígonos pintados; **pontos**, com os
marcadores; e **ambos**, com as duas sobrepostas. O mapa abre em
`MODO_INICIAL`. Ao lado dos botões fica a explicação do modo escolhido, trocada
junto com ele.

O que o modo NÃO faz é mexer na seleção de bandeiras. As leituras são da mesma
seleção, com efeitos diferentes: no nível cidade as bandeiras marcadas decidem
a COR dos municípios, no nível de pontos decidem QUAIS marcadores aparecem. Por
isso a lista de bandeiras continua ativa nos três modos, e trocar de modo
preserva o que estava marcado.

A DIVISA de município é desenhada em todos os modos: no nível de pontos o
polígono perde o preenchimento e sobra o fio. Sem ele, um marcador no interior
não diz a que cidade pertence — e é essa a pergunta que o mapa responde. O que
o modo liga e desliga é o preenchimento (com ele, a legenda e o clique no
polígono), nunca a camada.

Os marcadores são escondidos por *pane* do Leaflet, e não adicionando e
removendo camadas — a diferença é de correção, não de estilo, e está explicada
em `_JS_CONTROLADOR`: mexer nas camadas por fora do painel faz o
`L.Control.Layers` se reconstruir e recopiar cada caixa de seleção da presença
da camada no mapa, o que desmarcava as 14 bandeiras ao entrar no modo cidade.
Para que o coroplético seja controlado sem levar os marcadores junto, ele
desenha num pane próprio (`PANE_COROPLETICO`) — por padrão os dois estariam no
mesmo ``overlayPane`` e, com `prefer_canvas`, no mesmo ``<canvas>``.

--------------------------------------------------------------------------
Recorte por estado
--------------------------------------------------------------------------

Ao lado do modo de visão, a barra traz o filtro de UF: com um estado marcado, o
mapa se enquadra nele (`fitBounds` nos limites daquela UF) e os outros dois
SOMEM inteiros — polígono, divisa estadual e marcadores. Não é só um zoom.

Sumir é mais forte do que esmaecer, e é o ponto: a escala de cores, a legenda,
os quatro indicadores, o ranking, as contagens do painel e a busca passam a
falar só do estado escolhido. Um estado vizinho deixado à mostra continuaria
disputando a leitura das classes, que são recalculadas sobre o recorte
visível.

Nos marcadores o recorte é feito trocando o conteúdo de cada subgrupo em lote
(`addLayers`/`removeLayers` do MarkerCluster), e não escondendo ponto a ponto:
balão de contagem que sobrevivesse com os pontos escondidos mostraria um número
que não corresponde a nada na tela.

--------------------------------------------------------------------------
Divisa estadual
--------------------------------------------------------------------------

As três UFs entram como uma camada própria (`adicionar_divisas_uf`), dissolvida
a partir da mesma malha municipal — não há segundo download nem risco de as
duas fronteiras discordarem. O traço é bem mais grosso que o do município
(`LARGURA_DIVISA_UF` contra `LARGURA_CONTORNO_MUNICIPIO`), porque a hierarquia
território -> município tem de se ler de relance, e vai num pane acima do
coroplético e abaixo dos pontos, sem receber eventos de mouse.

--------------------------------------------------------------------------
Busca de município
--------------------------------------------------------------------------

A ponta direita da barra de controles traz um campo de busca com sugestões. O
casamento é por texto normalizado (sem acento e sem caixa), então "sao lourenco"
acha "São Lourenço do Sul"; prefixo vem antes de trecho no meio do nome.
Escolher um resultado enquadra o município e, nos modos em que o polígono está
pintado, abre o popup dele — o mesmo caminho que uma linha do ranking usa.

A lista sai da própria camada de municípios já carregada no navegador — nenhum
índice extra é embarcado no HTML — e respeita o filtro de UF: com um estado
marcado, só os municípios dele são sugeridos.

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
(ver `CORES_BANDEIRA`); com duas ou mais, volta para a rampa da identidade,
porque não existe "cor da marca" de um conjunto.

--------------------------------------------------------------------------
Identidade visual
--------------------------------------------------------------------------

A página inteira é Helvetica, em turquesa e azul-petróleo (ver "Identidade
visual" nas constantes). As duas cores têm papéis fixos: o petróleo é o texto
de peso e as superfícies escuras, a turquesa é o destaque e o que está ligado.

O que NÃO segue a identidade são as cores de marca dos marcadores
(`CORES_BANDEIRA`) e a rampa de bandeira única: ali a cor é dado, não
decoração — repintar o marcador da Caixa de turquesa desfaria justamente a
leitura que a cor por bandeira existe para permitir.
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
from folium.map import CustomPane
from folium.plugins import FeatureGroupSubGroup, MarkerCluster
from jinja2 import Template

from src import agregacao, cnefe, config, embutir
from src.etl_bacen import CATEGORIA_BANCO, CATEGORIA_COOPERATIVA

_LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Identidade visual
# --------------------------------------------------------------------------- #

#: Pilha de fontes de TODA a página — moldura, painel, popup e legenda.
#:
#: Helvetica é a fonte pedida; as duas seguintes são o que a substitui onde ela
#: não está instalada — "Helvetica Neue" no macOS e Arial no Windows. As três
#: têm a mesma métrica, então nenhuma medida do layout muda conforme a máquina
#: que abre o arquivo, que é o requisito de um HTML distribuído por e-mail.
FONTE_PADRAO = 'Helvetica, "Helvetica Neue", Arial, sans-serif'

#: Turquesa e azul-petróleo, as duas cores da identidade.
#:
#: A dupla é usada em papéis fixos, e não alternada por gosto: o PETRÓLEO é a
#: cor do texto de peso e das superfícies escuras (cabeçalho, títulos, divisa
#: estadual), a TURQUESA é a cor de ação e de destaque (opção marcada, valor de
#: indicador, foco do teclado). Manter os dois papéis separados é o que faz o
#: leitor aprender, em dois segundos, que turquesa = "está ligado".
COR_TURQUESA = "#14b8a6"
COR_TURQUESA_ESCURO = "#0f766e"
COR_TURQUESA_CLARO = "#e3f5f2"
COR_PETROLEO = "#0b4a5a"
COR_PETROLEO_ESCURO = "#06303b"
COR_PETROLEO_CLARO = "#1c6b7d"

#: Neutros da moldura: fundo da página, superfície dos cartões, texto e fios.
#:
#: O fundo NÃO é branco puro: os cartões são brancos e precisam se destacar
#: contra alguma coisa. O cinza-esverdeado abaixo é o branco da página puxado
#: na direção do petróleo, o que mantém a página numa temperatura só.
COR_PAPEL = "#f1f6f6"
COR_CARTAO = "#ffffff"
COR_TINTA = "#0e2a33"
COR_TINTA_SUAVE = "#5d757e"
COR_LINHA = "#dbe6e8"

#: Título, linha de apoio e data da safra, exibidos no alto da página.
#:
#: A data vem de `config.DATA_DADOS` — é a mesma safra dos arquivos do BACEN
#: lidos pelo ETL, e não uma string de apresentação escrita à parte, para que
#: trocar de safra não deixe o cabeçalho mentindo.
TITULO_MAPA = "Mapa da Presença Física das Cooperativas e Bancos"
OLHO_MAPA = "Cobertura &middot; Mapa interativo"
SUBTITULO_MAPA = (
    "Agências e postos de atendimento no Rio Grande do Sul, Santa Catarina "
    "e Paraná."
)
CREDITO_FONTES = (
    "Fontes: BACEN — agências e postos de atendimento (posição {data}); "
    "IBGE — malha municipal, população estimada e CNEFE/Censo 2022."
)

#: Símbolo do cooperativismo — o pinheiro dentro do círculo.
#:
#: Vai como SVG inline, e não como imagem: o arquivo é distribuído solto (por
#: e-mail, por pen drive) e um ``<img src="...">`` apontando para fora quebraria
#: exatamente aí. Inline, o símbolo viaja dentro do próprio HTML.
#:
#: A geometria é a do símbolo: um anel, três pinheiros e a base deles, com os
#: dois vãos verticais atravessando a figura de cima a baixo. O recorte
#: (`clipPath`) no miolo do anel é o que corta os pinheiros das pontas contra a
#: curva do círculo, como no original. `currentColor` deixa a cor ser decidida
#: pelo CSS de quem o usa, em vez de ficar presa aqui.
SVG_ICONE_COOPERATIVISMO = """
<svg class="icone-coop" viewBox="0 0 250 250" role="img"
     aria-label="Símbolo do cooperativismo">
  <defs>
    <clipPath id="coop-miolo"><circle cx="125" cy="125" r="95"/></clipPath>
  </defs>
  <circle cx="125" cy="125" r="104" fill="none" stroke="currentColor"
          stroke-width="18"/>
  <g clip-path="url(#coop-miolo)" fill="currentColor">
    <polygon points="24,62 -14,178 62,178"/>
    <polygon points="125,32 86,178 164,178"/>
    <polygon points="226,62 188,178 264,178"/>
    <rect x="-24" y="178" width="86" height="32"/>
    <rect x="86" y="178" width="78" height="32"/>
    <rect x="188" y="178" width="86" height="32"/>
  </g>
</svg>
"""

#: O mesmo símbolo, reduzido ao essencial, como ícone da aba do navegador.
#:
#: Em 16 px os três pinheiros viram uma mancha; esta versão tem um só, com o
#: traço do anel mais grosso, que é o que ainda se lê nesse tamanho. Vai como
#: data URI no ``<link rel="icon">`` pelo mesmo motivo do símbolo grande: nada
#: neste HTML pode depender de um arquivo ao lado.
#:
#: Os atributos usam aspas SIMPLES porque o SVG inteiro vira o valor de um
#: atributo HTML, que é delimitado por aspas duplas. Com aspas duplas aqui, o
#: primeiro `xmlns=` fecharia o `href=` do <link> e o resto do símbolo vazaria
#: para fora da tag — os elementos órfãos acabariam no corpo do documento,
#: empurrando a página inteira para baixo. O `#` da cor vai como `%23` pelo
#: mesmo motivo: num data URI ele iniciaria o fragmento.
_SVG_FAVICON = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 250 250'>"
    "<circle cx='125' cy='125' r='102' fill='none' stroke='%23{cor}' "
    "stroke-width='26'/>"
    "<polygon points='125,40 68,182 182,182' fill='%23{cor}'/>"
    "<rect x='104' y='170' width='42' height='46' fill='%23{cor}'/>"
    "</svg>"
)

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

#: Paleta sequencial de 6 classes, da turquesa clara ao azul-petróleo.
#:
#: É a rampa da identidade (`COR_TURQUESA` -> `COR_PETROLEO`), e não uma paleta
#: pronta do ColorBrewer, mas foi construída sob as mesmas duas exigências que
#: tornavam a YlGnBu anterior aceitável:
#:
#: * sequencial, porque a variável é uma contagem que só cresce;
#: * monotônica em LUMINOSIDADE, do claro ao escuro. É o que a mantém legível
#:   em escala de cinza e para deuteranopia/protanopia — a leitura passa a
#:   depender de claro-escuro, não de matiz, e turquesa e petróleo são vizinhos
#:   demais para serem separados por matiz de qualquer jeito.
PALETA_COROPLETICO = [
    "#c9ece5",
    "#9addd2",
    "#63c4be",
    "#31a1a4",
    "#1a7583",
    "#0a4655",
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
COR_ZERO = "#e9edee"

#: Cor de município sem dado (valor nulo). Distinta de `COR_ZERO`.
COR_SEM_DADO = "#d6dbdd"

#: Cor e espessura do contorno de município.
#:
#: Duas espessuras porque o fio faz dois papéis. Com o preenchimento à vista
#: (modo cidade), ele apenas separa duas manchas de cor e pode ser fino a ponto
#: de sumir. No modo de pontos não há mancha nenhuma: o fio é a ÚNICA divisa
#: desenhada sobre o basemap, e em 0,4 px ele praticamente não se lê no
#: Positron. Daí engrossar quando o preenchimento sai.
COR_CONTORNO_MUNICIPIO = "#a3b7bb"
LARGURA_CONTORNO_MUNICIPIO = 0.4
LARGURA_CONTORNO_MUNICIPIO_SEM_FUNDO = 0.8

#: Opacidade do preenchimento do coroplético.
OPACIDADE_COROPLETICO = 0.78

#: Traço da divisa entre estados.
#:
#: Grosso e escuro contra o fio claro e fino do município: a diferença entre os
#: dois é o que faz a hierarquia UF -> município ser lida sem legenda. É o
#: petróleo escuro da identidade, e não preto: tem contraste de sobra sobre o
#: Positron sem o peso do preto, que brigaria com os marcadores.
COR_DIVISA_UF = COR_PETROLEO_ESCURO
LARGURA_DIVISA_UF = 2.4

#: Painéis (*panes*) do Leaflet criados para este mapa, e o z-index de cada um.
#:
#: Os padrões do Leaflet que importam aqui: ladrilhos em 200, ``overlayPane``
#: (onde caem os marcadores de ponto) em 400 e ``markerPane`` (os balões de
#: contagem) em 600. Os dois panes abaixo se encaixam nessa ordem — coroplético
#: como fundo, divisa estadual por cima dele, ambos abaixo dos pontos, que é a
#: ordem de leitura: polígono é fundo, ponto é figura.
#:
#: Os panes são criados em Python (`criar_mapa_base`) e não no controlador em
#: JavaScript: o pane precisa existir ANTES de a camada ser adicionada, porque é
#: no `onAdd` que o Leaflet escolhe o renderizador dela. Criado depois, o
#: controlador teria de retirar e repor a camada — e retirar/repor camada por
#: fora do painel faz o `L.Control.Layers` se reconstruir (ver `_JS_CONTROLADOR`).
PANE_COROPLETICO = "coropletico"
Z_INDEX_COROPLETICO = 350
PANE_DIVISAS_UF = "divisas-uf"
Z_INDEX_DIVISAS_UF = 360

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

#: Identificadores dos modos de visão.
MODO_CIDADE = "cidade"
MODO_PONTOS = "pontos"
MODO_AMBOS = "ambos"

#: Rótulo e explicação de cada modo, na ordem em que aparecem no seletor.
#:
#: O rótulo é curto porque vira um botão-segmento na barra de controles, onde
#: três nomes longos não caberiam lado a lado. A `dica` é que carrega a
#: explicação, exibida ao lado dos botões e trocada junto com a escolha.
#:
#: Ela existe porque a mesma lista de bandeiras serve aos dois modos com
#: efeitos diferentes — no modo de municípios ela decide a COR dos polígonos,
#: no de pontos decide QUAIS marcadores aparecem. Sem a dica, marcar uma
#: bandeira no modo de municípios parece não fazer nada (o efeito está no
#: coroplético, não numa camada que aparece ou some).
MODOS_VISAO = [
    {
        "id": MODO_CIDADE,
        "rotulo": "Municípios",
        "dica": "a cor de cada município é o total das bandeiras marcadas",
    },
    {
        "id": MODO_PONTOS,
        "rotulo": "Pontos",
        "dica": "um disco por ponto de atendimento das bandeiras marcadas",
    },
    {
        "id": MODO_AMBOS,
        "rotulo": "Ambos",
        "dica": "as duas leituras sobrepostas",
    },
]

#: Modo em que o mapa abre.
#:
#: `MODO_CIDADE`, porque o mapa abre no zoom da região inteira: ali os 7.600
#: pontos estão todos agrupados em balões e o que se lê de fato é a cor dos
#: municípios. O modo de pontos é a leitura de quem já aproximou.
MODO_INICIAL = MODO_CIDADE

#: Texto de apoio do campo de busca de município.
TEXTO_BUSCA = "Buscar município\u2026"

#: Mínimo de caracteres digitados antes de a busca sugerir alguma coisa.
#:
#: Com uma letra só a lista viria cheia e sem serventia — são 1.191 municípios,
#: e "a" casa com quase todos. Duas já separam o suficiente para valer a pena.
MIN_CARACTERES_BUSCA = 2

#: Quantas sugestões a busca mostra por vez.
#:
#: Oito cabem sem rolagem sob o campo e sem cobrir o mapa. Quem não achou o
#: município nas oito primeiras digita mais uma letra, que é mais rápido do que
#: percorrer uma lista longa.
MAX_SUGESTOES_BUSCA = 8

#: Zoom máximo ao enquadrar o município escolhido na busca.
#:
#: `fitBounds` sozinho aproximaria um município pequeno até o nível de rua, onde
#: não se vê mais nem a divisa dele nem os vizinhos. Doze mostra o município
#: inteiro com o entorno, que é o enquadramento de quem acabou de procurá-lo.
ZOOM_BUSCA = 12

#: Quantos municípios a lista de maior presença mostra.
#:
#: Doze, e não vinte e cinco: a lista responde "onde a rede se concentra", e
#: essa resposta está nas primeiras posições — o resto é cauda, que o mapa
#: mostra melhor do que uma lista. Doze também é o que cabe no cartão sem
#: rolagem na maioria das telas.
MAX_RANKING = 12

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

#: Opacidade do preenchimento do disco.
#:
#: Um pouco abaixo de 1 para que dois marcadores sobrepostos ainda se
#: denunciem, sem que a cor de marca perca saturação.
OPACIDADE_MARCADOR = 0.92

#: Largura máxima do popup de um ponto, em pixels.
#:
#: 312 = os 300 de largura útil + os 12 do recuo da barra de rolagem que
#: `.popup-municipio` reserva, pela mesma razão do popup do município.
MAX_LARGURA_POPUP_PONTO = 312

#: Largura máxima do popup de um município, em pixels.
#:
#: 352 = os 340 de largura útil + os 12 da barra de rolagem. Sem a
#: compensação, o recuo comeria largura do conteúdo e a linha da população
#: passaria a quebrar em duas.
MAX_LARGURA_POPUP_MUNICIPIO = 352

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
# Aparência da página
# --------------------------------------------------------------------------- #

#: As cores e a fonte da identidade, publicadas como variáveis CSS.
#:
#: Existe para que as constantes Python acima sejam a ÚNICA definição de cada
#: cor. O resto da folha usa `var(--turquesa)` e nunca o valor cru, então
#: mudar a identidade é editar as constantes — não caçar hexadecimais soltos
#: em ~600 linhas de CSS.
_VARIAVEIS_CSS = f"""
:root {{
    --fonte: {FONTE_PADRAO};
    --turquesa: {COR_TURQUESA};
    --turquesa-escuro: {COR_TURQUESA_ESCURO};
    --turquesa-claro: {COR_TURQUESA_CLARO};
    --petroleo: {COR_PETROLEO};
    --petroleo-escuro: {COR_PETROLEO_ESCURO};
    --petroleo-claro: {COR_PETROLEO_CLARO};
    --papel: {COR_PAPEL};
    --cartao: {COR_CARTAO};
    --tinta: {COR_TINTA};
    --tinta-suave: {COR_TINTA_SUAVE};
    --linha: {COR_LINHA};
    --raio: 14px;
    --raio-menor: 9px;
    --sombra: 0 1px 2px rgba(11, 74, 90, 0.05),
              0 6px 18px -10px rgba(11, 74, 90, 0.28);
}}
"""

#: Folha de estilo da página: moldura, barra de controles, cartões e balões.
#:
#: A moldura é um APLICATIVO DE ALTURA FIXA, não um documento que rola: `.app`
#: ocupa 100vh e o par mapa+coluna recebe a sobra (`flex: 1; min-height: 0`).
#: É o que garante que os três blocos de decisão — indicadores, controles e
#: mapa — estejam na tela ao mesmo tempo, sem rolagem. Quem rola é o conteúdo
#: de cada cartão, dentro dele. Abaixo de 1000 px de largura a regra se
#: inverte (ver a media query no fim): a coluna vai para baixo do mapa e a
#: página passa a rolar, porque em tela estreita lado a lado não cabe.
_CSS_CORPO = """
html, body {
    height: 100%;
    margin: 0;
    padding: 0;
    background: var(--papel);
    color: var(--tinta);
    font-family: var(--fonte);
    -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }

.app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
}

/* --- Faixa de marca ---------------------------------------------------- *
   Fundo petróleo em vez de branco: é a única superfície escura da página e
   serve de âncora — abaixo dela tudo é claro, e o olho encontra o topo sem
   procurar. */
.app-topo {
    flex: none;
    background: var(--petroleo);
    color: #fff;
}
.app-topo-interno {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    max-width: 1680px;
    margin: 0 auto;
    padding: 9px 20px;
}
.marca {
    display: flex;
    align-items: center;
    gap: 11px;
    min-width: 0;
}
.icone-coop {
    display: block;
    width: 34px;
    height: 34px;
    color: var(--turquesa);
}
.marca-texto { line-height: 1.25; min-width: 0; }
.marca-texto b {
    display: block;
    font-size: 14px;
    font-weight: bold;
    letter-spacing: 0.2px;
}
.marca-texto small {
    display: block;
    font-size: 11px;
    color: #9fc4cd;
}
/* Selo da safra: a data do dado é a primeira pergunta de quem recebe um mapa
   pronto, então ela fica no topo, e não num rodapé de fonte. */
.selo-safra {
    flex: none;
    padding: 5px 12px;
    border: 1px solid rgba(94, 234, 212, 0.4);
    border-radius: 999px;
    background: rgba(20, 184, 166, 0.14);
    color: #9beadd;
    font-size: 11px;
    letter-spacing: 0.3px;
    white-space: nowrap;
}
.selo-safra b { color: #fff; font-weight: bold; }

.app-corpo {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
    width: 100%;
    max-width: 1680px;
    margin: 0 auto;
    padding: 12px 20px 11px;
}

/* --- Título e indicadores, lado a lado --------------------------------- *
   Dividem uma linha só porque a soma dos dois empilhados custaria ~180 px da
   altura do mapa. Em tela estreita a linha quebra e os indicadores descem. */
.app-abertura {
    flex: none;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 20px;
    flex-wrap: wrap;
}
/* `flex: 0 1 auto` no título e `flex: 1 1 0` nos indicadores: a linha tem
   largura de sobra para os dois, mas a faixa de indicadores mede pelo texto
   mais largo de cada cartão e pedia ~830 px, o que estourava a linha e a fazia
   quebrar. Com base zero eles passam a dividir o que sobra do título, e cada
   nota que não couber é cortada com reticências em vez de virar duas linhas. */
.app-cabecalho {
    flex: 0 1 auto;
    min-width: 280px;
}
.olho {
    margin: 0 0 5px;
    color: var(--turquesa-escuro);
    font-size: 10.5px;
    font-weight: bold;
    letter-spacing: 1.3px;
    text-transform: uppercase;
}
.app-cabecalho h1 {
    margin: 0;
    color: var(--petroleo);
    font-size: 22px;
    font-weight: bold;
    letter-spacing: -0.4px;
    line-height: 1.15;
}
.app-linha-fina {
    margin: 5px 0 0;
    color: var(--tinta-suave);
    font-size: 12.5px;
}

/* --- Indicadores -------------------------------------------------------- *
   Quatro números que respondem à seleção atual, na ordem em que a pergunta
   costuma ser feita: quanto existe, onde existe, onde NÃO existe e quanta
   gente mora no que não existe. O quarto é o que transforma o mapa em pauta
   de decisão — sem ele, "347 municípios sem atendimento" não tem tamanho. */
.indicadores {
    flex: 1 1 0;
    min-width: 0;
    display: grid;
    grid-template-columns: repeat(4, minmax(112px, 1fr));
    gap: 9px;
}
.indicador-rotulo,
.indicador-nota {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.indicador {
    padding: 7px 11px;
    background: var(--cartao);
    border: 1px solid var(--linha);
    border-radius: var(--raio-menor);
    box-shadow: var(--sombra);
}
.indicador-rotulo {
    margin: 0;
    color: var(--tinta-suave);
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 0.55px;
    text-transform: uppercase;
}
.indicador-valor {
    margin: 2px 0 0;
    color: var(--petroleo);
    font-size: 20px;
    font-weight: bold;
    letter-spacing: -0.5px;
    line-height: 1.1;
}
.indicador-nota {
    margin: 1px 0 0;
    color: var(--tinta-suave);
    font-size: 11px;
    min-height: 15px;
}
/* O indicador de lacuna é o único com cor própria: ele não descreve o que a
   rede cobre, e sim o que ela deixa de fora. */
.indicador.lacuna .indicador-valor { color: var(--turquesa-escuro); }

/* --- Barra de controles ------------------------------------------------- */
.barra {
    flex: none;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 6px 8px;
    background: var(--cartao);
    border: 1px solid var(--linha);
    border-radius: var(--raio);
    box-shadow: var(--sombra);
}
.barra-grupo {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
}
.barra-rotulo {
    color: var(--tinta-suave);
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 0.55px;
    text-transform: uppercase;
    white-space: nowrap;
}
.barra-divisor {
    width: 1px;
    align-self: stretch;
    margin: 0 2px;
    background: var(--linha);
}
/* Segmentos: o rádio some e quem pinta é o <label>, via `:has(:checked)`.
   O <input> continua no DOM — não é decoração, é o que dá navegação por
   teclado e leitura por leitor de tela de graça. */
.segmentos {
    display: flex;
    gap: 3px;
    padding: 3px;
    background: var(--papel);
    border-radius: var(--raio-menor);
}
.segmento {
    position: relative;
    padding: 5px 10px;
    border-radius: 7px;
    color: var(--tinta-suave);
    font-size: 12px;
    font-weight: bold;
    white-space: nowrap;
    cursor: pointer;
    transition: background 0.12s, color 0.12s;
}
.segmento input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
}
.segmento:hover { color: var(--petroleo); }
.segmento:has(input:checked) {
    background: var(--turquesa-escuro);
    color: #fff;
}
.segmento:has(input:focus-visible) {
    outline: 2px solid var(--turquesa);
    outline-offset: 1px;
}
/* A explicação do modo fica FORA do botão: dentro, ela dobraria a altura da
   barra só para repetir o que o rótulo já diz na maior parte do tempo. */
.barra-dica {
    flex: 1 1 60px;
    min-width: 0;
    color: var(--tinta-suave);
    font-size: 11.5px;
    font-style: italic;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* --- Busca de município ------------------------------------------------- */
.busca-municipio {
    position: relative;
    width: 232px;
    flex: none;
}
.busca-municipio input {
    width: 100%;
    padding: 7px 10px;
    border: 1px solid var(--linha);
    border-radius: var(--raio-menor);
    background: var(--papel);
    color: var(--tinta);
    font: 12px/1.4 var(--fonte);
}
.busca-municipio input::placeholder { color: var(--tinta-suave); }
.busca-municipio input:focus {
    outline: none;
    border-color: var(--turquesa);
    box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.18);
}
/* A lista flutua sobre o mapa (`position: absolute` + z-index acima dos
   controles do Leaflet, que vão até 1000): dentro do fluxo ela empurraria a
   barra e o mapa para baixo a cada tecla digitada. */
.busca-sugestoes {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    z-index: 1200;
    margin: 0;
    padding: 4px;
    max-height: 244px;
    overflow-y: auto;
    list-style: none;
    background: var(--cartao);
    border: 1px solid var(--linha);
    border-radius: var(--raio-menor);
    box-shadow: 0 10px 26px -8px rgba(11, 74, 90, 0.35);
    font-size: 12px;
}
.busca-sugestoes[hidden] { display: none; }
.busca-sugestoes li {
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;
}
.busca-sugestoes li.ativa {
    background: var(--turquesa-claro);
    color: var(--petroleo);
}
.busca-sugestoes .busca-uf {
    color: var(--tinta-suave);
    font-size: 11px;
}
.busca-sugestoes .busca-vazio {
    color: var(--tinta-suave);
    cursor: default;
}

/* --- Mapa e coluna lateral ---------------------------------------------- */
.area {
    flex: 1;
    display: flex;
    gap: 12px;
    min-height: 0;
}
.cartao {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--cartao);
    border: 1px solid var(--linha);
    border-radius: var(--raio);
    box-shadow: var(--sombra);
    overflow: hidden;
}
.cartao-mapa { flex: 1; min-width: 0; }
/* O mapa do folium é movido para cá pelo controlador (ver `_JS_CONTROLADOR`);
   ele chega com `width/height: 100%`, então o encaixe só precisa ter altura
   própria — que vem do `flex: 1` sobre um pai de altura definida. */
.mapa-slot {
    position: relative;
    flex: 1;
    min-height: 0;
}
.coluna-lateral {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 320px;
    flex: none;
    min-height: 0;
}
/* A lista de bandeiras pede a altura do proprio conteudo (`flex-basis: auto`,
   sem crescer) e o ranking fica com o que sobrar. E o que evita a lista
   principal de controle rolar em tela grande, onde as 16 linhas cabem
   inteiras, sem deixar o ranking sumir em tela pequena — os dois `min-height`
   seguram o piso quando a coluna aperta. */
.cartao-bandeiras {
    flex: 0 1 auto;
    min-height: 170px;
}
.cartao-ranking {
    flex: 1 1 180px;
    min-height: 150px;
}
.cartao-topo {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--linha);
}
.cartao-topo h2 {
    margin: 0;
    color: var(--petroleo);
    font-size: 12.5px;
    font-weight: bold;
    letter-spacing: 0.1px;
}
.cartao-nota {
    color: var(--tinta-suave);
    font-size: 11px;
    white-space: nowrap;
}
.cartao-conteudo {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 8px 12px 12px;
}
.acoes { display: flex; gap: 5px; flex: none; }
.acoes button {
    padding: 4px 9px;
    border: 1px solid var(--linha);
    border-radius: 999px;
    background: var(--papel);
    color: var(--tinta-suave);
    font: bold 11px var(--fonte);
    cursor: pointer;
}
.acoes button:hover {
    border-color: var(--turquesa);
    background: var(--turquesa-claro);
    color: var(--turquesa-escuro);
}

/* --- Lista de bandeiras (o LayerControl do Leaflet, remontado aqui) ------ *
   O painel é movido para dentro do cartão pelo controlador, então tudo que o
   Leaflet lhe dá de aparência de controle flutuante — fundo, borda, sombra,
   `float`, largura mínima — é desfeito abaixo. O que fica é a lista. */
#painel-bandeiras .leaflet-control-layers {
    width: 100%;
    margin: 0;
    border: none;
    border-radius: 0;
    box-shadow: none;
    background: transparent;
    float: none;
}
/* O Leaflet grava uma altura em pixels neste elemento ao abrir o painel,
   calculada sobre o tamanho do MAPA. Dentro do cartão essa conta não vale — a
   rolagem passa a ser do cartão. */
#painel-bandeiras .leaflet-control-layers-list {
    height: auto !important;
    margin: 0;
}
#painel-bandeiras .leaflet-control-layers-toggle { display: none; }
#painel-bandeiras .leaflet-control-layers-separator { display: none; }
/* O Leaflet monta cada linha como ``label > span > (input, span)``: o <span>
   externo embrulha caixa e rótulo, o interno recebe o HTML do nome — que aqui
   traz a amostra de cor, o texto e a contagem. Os dois viram caixas flex, e é
   isso que alinha os três pedaços numa linha e empurra a contagem para a
   direita. */
#painel-bandeiras .leaflet-control-layers-overlays label {
    display: block;
    margin: 0;
    padding: 5px 7px;
    border-radius: 7px;
    font-size: 12px;
    cursor: pointer;
}
#painel-bandeiras .leaflet-control-layers-overlays label:hover {
    background: var(--turquesa-claro);
}
#painel-bandeiras .leaflet-control-layers-overlays label > span {
    display: flex;
    align-items: center;
    gap: 7px;
}
#painel-bandeiras .leaflet-control-layers-overlays label > span > span {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
}
#painel-bandeiras input[type="checkbox"] {
    flex: none;
    width: 14px;
    height: 14px;
    margin: 0;
    accent-color: var(--turquesa-escuro);
    cursor: pointer;
}
/* Nível 1 — a categoria: caixa-alta pequena e fio acima, para abrir bloco. */
.leaflet-control-layers-overlays label:has(.camada-grupo) {
    margin-top: 10px !important;
    border-top: 1px solid var(--linha);
    border-radius: 0;
    padding-top: 10px !important;
}
.leaflet-control-layers-overlays label:first-child:has(.camada-grupo) {
    margin-top: 0 !important;
    border-top: none;
    padding-top: 5px !important;
}
.camada-grupo {
    flex: 1;
    color: var(--petroleo);
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 0.7px;
    text-transform: uppercase;
}
/* Nível 2 — a bandeira: linha inteira indentada, com fio-guia à esquerda. */
.leaflet-control-layers-overlays label:has(.camada-sub) {
    margin-left: 9px !important;
    border-left: 2px solid var(--linha);
    border-radius: 0 7px 7px 0;
}
.camada-sub {
    flex: 1;
    color: var(--tinta);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.camada-contagem {
    flex: none;
    margin-left: auto;
    color: var(--tinta-suave);
    font-weight: normal;
    font-variant-numeric: tabular-nums;
}
/* Amostra da cor da bandeira. Redonda e do tamanho do marcador, para ser lida
   como "este é o ponto no mapa". */
.camada-cor {
    flex: none;
    display: inline-block;
    width: 11px;
    height: 11px;
    border: 1px solid;
    border-radius: 50%;
}

/* --- Ranking de municípios ---------------------------------------------- *
   A pergunta "onde estão os maiores" não se responde olhando um coroplético:
   as manchas escuras ficam nas capitais, que o leitor já conhece. A lista
   ordenada responde direto, e cada linha enquadra o município no mapa. */
.ranking {
    margin: 0;
    padding: 6px 8px 12px;
    list-style: none;
    counter-reset: posicao;
}
.ranking li {
    display: grid;
    grid-template-columns: 20px 1fr auto;
    align-items: center;
    gap: 8px;
    padding: 5px 6px;
    border-radius: 7px;
    cursor: pointer;
}
.ranking li:hover { background: var(--turquesa-claro); }
.ranking .posicao {
    color: var(--tinta-suave);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    text-align: right;
}
.ranking .nome {
    min-width: 0;
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.ranking .nome em {
    color: var(--tinta-suave);
    font-size: 10.5px;
    font-style: normal;
}
.ranking .valor {
    color: var(--petroleo);
    font-size: 12px;
    font-weight: bold;
    font-variant-numeric: tabular-nums;
}
/* A barra ocupa a linha inteira, atrás do nome, para que a comparação entre
   posições seja visual e não exija ler os números um a um. */
.ranking .trilho {
    grid-column: 2 / 4;
    height: 3px;
    margin-top: -2px;
    border-radius: 2px;
    background: var(--papel);
    overflow: hidden;
}
.ranking .trilho i {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--turquesa);
}
.ranking .vazio {
    display: block;
    padding: 8px 6px;
    color: var(--tinta-suave);
    font-size: 12px;
    cursor: default;
}

/* --- Legenda, no rodapé do cartão do mapa ------------------------------- *
   Faixa horizontal, e não caixa flutuante sobre o mapa: flutuando ela tapa
   município, e num mapa cujas classes mudam a cada clique a legenda é parte
   da leitura — não pode estar por cima do que descreve. */
.mapa-rodape {
    flex: none;
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    padding: 6px 12px;
    border-top: 1px solid var(--linha);
    background: var(--cartao);
    font-size: 11.5px;
}
.legenda-titulo {
    color: var(--petroleo);
    font-weight: bold;
    white-space: nowrap;
}
.legenda-titulo span {
    color: var(--tinta-suave);
    font-weight: normal;
}
.legenda-escala { display: flex; align-items: flex-end; gap: 2px; }
.legenda-classe { text-align: center; min-width: 44px; }
.legenda-classe i {
    display: block;
    height: 10px;
    border: 1px solid rgba(11, 74, 90, 0.18);
    border-radius: 2px;
}
.legenda-classe b {
    display: block;
    margin-top: 3px;
    font-size: 10.5px;
    font-weight: normal;
    font-variant-numeric: tabular-nums;
}
.legenda-classe small {
    display: block;
    color: var(--tinta-suave);
    font-size: 9.5px;
}
.legenda-classe.zero { margin-right: 8px; }
.legenda-recado { color: var(--tinta-suave); }
.legenda-fonte {
    margin-left: auto;
    color: var(--tinta-suave);
    font-size: 10.5px;
    text-align: right;
}

/* --- Rodapé de fontes --------------------------------------------------- */
.app-rodape {
    flex: none;
    color: var(--tinta-suave);
    font-size: 10px;
    line-height: 1.4;
}

/* --- Ajustes no Leaflet ------------------------------------------------- */
.leaflet-container { font-family: var(--fonte) !important; }
.leaflet-bar a,
.leaflet-control-zoom a {
    color: var(--petroleo);
    border-bottom-color: var(--linha);
    font-family: var(--fonte);
    font-size: 19px;
}
.leaflet-bar a:hover { background: var(--turquesa-claro); }
.leaflet-bar {
    border: 1px solid var(--linha);
    box-shadow: var(--sombra);
}
.leaflet-control-attribution {
    background: rgba(255, 255, 255, 0.86) !important;
    color: var(--tinta-suave);
    font-size: 10px;
}
.leaflet-control-attribution a { color: var(--turquesa-escuro); }
.leaflet-control-scale-line {
    border-color: var(--tinta-suave);
    color: var(--tinta);
    background: rgba(255, 255, 255, 0.8);
}
/* Balão de contagem do MarkerCluster nas duas cores da identidade — o padrão
   do plugin é verde-amarelo-laranja, que brigava com a rampa do coroplético
   e sugeria uma escala de cor que não existe ali. */
.marker-cluster div {
    background: var(--turquesa-escuro);
    color: #fff;
    font: bold 11px var(--fonte);
}
.marker-cluster { background: rgba(20, 184, 166, 0.32); }
.marker-cluster-large div { background: var(--petroleo); }
.marker-cluster-large { background: rgba(11, 74, 90, 0.3); }

/* --- Balões de município e de ponto ------------------------------------- */
.leaflet-popup-content-wrapper {
    border-radius: var(--raio-menor);
    box-shadow: 0 12px 30px -10px rgba(11, 74, 90, 0.45);
}
.leaflet-popup-content { margin: 12px 14px; }
.leaflet-tooltip {
    border: 1px solid var(--linha);
    border-radius: 7px;
    box-shadow: var(--sombra);
    font-family: var(--fonte);
}
.popup-municipio {
    font: 12px/1.45 var(--fonte);
    max-height: 320px;
    overflow-y: auto;
    /* Faixa livre à direita para a barra de rolagem. Sem ela, a barra cobre os
       números — que são alinhados à direita e encostavam na borda do container.
       O recuo resolve os dois tipos de barra: a clássica ocupa layout e fica
       depois do padding; a de sobreposição é DESENHADA sobre esta faixa, e é
       por isso que `scrollbar-gutter: stable` não serviria aqui (por
       especificação ele não reserva nada quando a barra é de sobreposição). */
    padding-right: 12px;
}
.popup-municipio h4 {
    margin: 0 0 7px;
    color: var(--petroleo);
    font-size: 13.5px;
    font-weight: bold;
}
.popup-municipio table {
    border-collapse: collapse;
    width: 100%;
}
.popup-municipio th {
    text-align: left;
    font-weight: bold;
    padding: 1px 8px 1px 0;
}
.popup-municipio td {
    text-align: right;
    padding: 1px 0;
    font-variant-numeric: tabular-nums;
}
.popup-municipio .secao {
    padding-top: 5px;
    border-top: 1px solid var(--linha);
}
.popup-municipio .secao th { color: var(--petroleo); }
.popup-municipio .bandeira th {
    font-weight: normal;
    padding-left: 10px;
    color: var(--tinta-suave);
}
/* As marcas que compõem "Outra Cooperativa". Ocupa a linha inteira porque é
   uma enumeração, não um par rótulo/valor: alinhada à direita como as demais
   células de número, uma lista de três marcas ficaria ilegível. */
.popup-municipio .detalhe-outras td {
    text-align: left;
    padding: 0 0 2px 20px;
    color: var(--tinta-suave);
    font-size: 11px;
    line-height: 1.4;
}
.popup-municipio .indisponivel,
.aviso-posicao {
    color: #8a6d1f;
    font-style: italic;
}
/* Procedência da coordenada nos dois níveis precisos: informação de rodapé,
   não advertência — daí o cinza em vez do âmbar de `.aviso-posicao`. */
.procedencia {
    color: var(--tinta-suave);
    font-size: 11px;
}
.popup-secundario { color: var(--tinta-suave); }
/* Cabeçalho que o controlador insere no balão do município, com o total da
   seleção atual. */
.selecao-atual {
    margin-bottom: 6px;
    padding: 5px 8px;
    border-radius: 6px;
    background: var(--turquesa-claro);
    color: var(--petroleo);
    font: 12px/1.4 var(--fonte);
}
.selecao-atual b { font-size: 13px; }
/* O folium embrulha o conteúdo do GeoJsonPopup/Tooltip numa <table>; sem isto
   a tabela interna do balão herda a borda e o padding dessa casca. */
.leaflet-popup-content table td,
.leaflet-tooltip table td {
    border: none;
    padding: 0;
}

/* --- Telas estreitas ---------------------------------------------------- *
   Abaixo de 1000 px o lado a lado não cabe: a coluna desce para baixo do
   mapa, os dois ganham altura fixa e a página volta a rolar. */
@media (max-width: 1000px) {
    .app { height: auto; overflow: visible; }
    .app-corpo { padding: 14px 14px 18px; }
    .indicadores { grid-template-columns: repeat(2, minmax(122px, 1fr)); }
    .area { flex-direction: column; }
    .cartao-mapa { height: 62vh; min-height: 380px; flex: none; }
    .coluna-lateral { width: 100%; }
    .cartao-bandeiras, .cartao-ranking { height: 340px; flex: none; }
    .barra-busca { flex: 1 1 100%; }
    .busca-municipio { width: 100%; }
    .barra-dica { display: none; }
}
"""

#: CSS completo da página, pronto para entrar no ``<head>``.
_CSS_PAGINA = "<style>" + _VARIAVEIS_CSS + _CSS_CORPO + "</style>"


# --------------------------------------------------------------------------- #
# 1. Carregamento
# --------------------------------------------------------------------------- #


def carregar_agregado(caminho: Path | None = None) -> gpd.GeoDataFrame:
    """Lê o agregado por município, com a geometria.

    Args:
        caminho: GeoParquet produzido por `src.agregacao`; ``None`` deriva do
            recorte ativo.

    Returns:
        GeoDataFrame com uma linha por município do recorte, em
        `config.CRS_GEOGRAFICO`.

    Raises:
        FileNotFoundError: se o arquivo não existir — rode `python -m src.agregacao`.
        KeyError: se faltar alguma coluna exigida pelo mapa.
    """
    caminho = caminho or config.arquivo_agregado_municipio()
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


#: As três funções de formatação que a página inteira usa, traduzidas do
#: Python que as escrevia na geração.
#:
#: Vivem num bloco só, e não copiadas dentro de cada script que precisa delas,
#: pelo mesmo motivo que fez a lógica de popup sair do Python: duas
#: implementações da mesma regra divergem com o tempo. `esc` e `escRe` são o
#: `html.escape` e o `re.escape` da biblioteca padrão do Python — as duas com o
#: conjunto de caracteres e a ordem de substituição exatos —, e `inteiroBR` é o
#: antigo `_formatar_inteiro`.
#:
#: São emitidas antes de qualquer camada, como filho do mapa, para estarem
#: declaradas quando os demais blocos rodarem.
_JS_FORMATO = r"""
window.mapaFormato = (function () {
    "use strict";

    /* Mesmo conjunto e MESMA ORDEM do `html.escape` do Python (que escapa
       aspas por padrão): inverter a ordem faria o `&` de `&amp;` ser
       reescapado. */
    function esc(t) {
        return String(t)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#x27;");
    }

    /* Equivalente do `re.escape`: o Python 3.7+ escapa exatamente este
       conjunto de caracteres, e nenhum outro. */
    function escRe(t) {
        return String(t).replace(/[()[\]{}?*+\-|^$\\.&~# \t\n\r\v\f]/g, "\\$&");
    }

    /* Equivalente de `f"{int(v):,}".replace(",", ".")`: separador de milhar
       brasileiro. Escrito à mão, e não com `toLocaleString`, porque o
       resultado do `toLocaleString` depende do locale instalado no navegador
       de quem abre o arquivo — e este arquivo circula por e-mail. */
    function inteiroBR(valor) {
        var n = Math.trunc(Number(valor));
        var digitos = Math.abs(n).toString();
        return (n < 0 ? "-" : "") +
            digitos.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    }

    return {esc: esc, escRe: escRe, inteiroBR: inteiroBR};
})();
"""


#: O popup e o tooltip do município, montados no navegador a partir das
#: contagens que a feição já carregava.
#:
#: Ver `preparar_propriedades_municipio` para o que saiu do arquivo. A ligação
#: é feita na CAMADA, e não feição a feição: o `bindPopup` de um `L.GeoJSON`
#: aceita uma função e a chama com a feição clicada, que é como o próprio
#: `folium.GeoJsonPopup` funciona por dentro. Os dois envelopes
#: (``<table><tr><td>``) e as duas classes (``foliumpopup``, ``foliumtooltip``)
#: são os que o folium escrevia, reproduzidos porque o CSS da página mira
#: exatamente essa estrutura.
_JS_MUNICIPIO = r"""
(function () {
    "use strict";
    var cfg = __CONFIG__;
    var geo = __GEOJSON__;
    var f = window.mapaFormato;
    if (!geo || !f) {
        console.error("municípios: camada ou formatador não encontrados");
        return;
    }

    /* Tradução de `_texto_populacao`. Município que a API de agregados do IBGE
       não devolveu NÃO pode virar 0 no popup: zero habitante é uma afirmação
       sobre o município, "indisponível" é uma afirmação sobre o dado. */
    function textoPopulacao(props) {
        if (props.populacao_valor == null) {
            return '<span class="indisponivel">dado indisponível</span>';
        }
        var texto = f.inteiroBR(props.populacao_valor) + " hab.";
        var ano = props.populacao_ano;
        if (ano != null && String(ano).trim()) {
            texto += " (" + f.esc(String(ano)) + ")";
        }
        return texto;
    }

    /* Tradução de `_linhas_por_bandeira`. Só entram as bandeiras com ao menos
       1 ponto no município: listar as 14 com zero em quase todas transformaria
       o popup numa tabela de zeros, em que a informação — quais bandeiras
       existem ali — fica escondida. */
    function linhasPorBandeira(props, secao) {
        var linhas = [];
        secao.bandeiras.forEach(function (bandeira) {
            var rotulo = bandeira[0];
            var total = props[bandeira[1]];
            if (total == null || !Math.trunc(total)) { return; }
            linhas.push('<tr class="bandeira"><th>' + f.esc(rotulo) +
                "</th><td>" + f.inteiroBR(total) + "</td></tr>");
            /* "Outra Cooperativa" é a única bandeira que agrupa marcas
               distintas. Sem esta linha o popup afirmaria que há N pontos de
               algo sem nome, quando a fonte publica o nome de todos eles. */
            if (rotulo === cfg.subIndefinida) {
                var detalhe = String(props[cfg.colunaDetalhe] || "").trim();
                if (detalhe) {
                    linhas.push('<tr class="detalhe-outras"><td colspan="2">' +
                        f.esc(detalhe) + "</td></tr>");
                }
            }
        });
        if (!linhas.length) {
            return '<tr class="bandeira"><th>—</th><td>nenhum ponto</td></tr>';
        }
        return linhas.join("");
    }

    function popupMunicipio(camada) {
        var props = camada.feature.properties;
        var corpo = '<div class="popup-municipio">' +
            "<h4>" + f.esc(props.municipio_nome) + "/" + f.esc(props.uf) + "</h4>" +
            "<table>" +
            "<tr><th>População</th><td>" + textoPopulacao(props) + "</td></tr>";
        cfg.secoes.forEach(function (secao) {
            corpo += '<tr class="secao"><th>' + f.esc(secao.rotulo) + "</th>" +
                "<td>" + f.inteiroBR(props[secao.coluna]) + "</td></tr>" +
                linhasPorBandeira(props, secao);
        });
        return envelope(corpo + "</table></div>");
    }

    function tooltipMunicipio(camada) {
        var props = camada.feature.properties;
        return envelope(
            "<b>" + f.esc(props.municipio_nome) + "/" + f.esc(props.uf) + "</b><br>" +
            "Cooperativas: " + f.inteiroBR(props.total_cooperativas) +
            " &nbsp;|&nbsp; Bancos: " + f.inteiroBR(props.total_bancos) +
            '<br><span class="popup-secundario">clique para o detalhamento' +
            "</span>"
        );
    }

    /* O envelope que o `GeoJsonPopup`/`GeoJsonTooltip` do folium montava: um
       `<div>` criado por script, com o conteúdo dentro de uma tabela de uma
       célula. A tabela não é decorativa — `.leaflet-popup-content table td` e
       `.leaflet-tooltip table td` são regras da folha de estilo da página. */
    function envelope(html) {
        var div = L.DomUtil.create("div");
        div.innerHTML = "<table><tr>\n            <td>" + html +
            "</td>\n        </tr></table>";
        return div;
    }

    geo.bindTooltip(tooltipMunicipio, {sticky: true, className: "foliumtooltip"});
    geo.bindPopup(popupMunicipio, {
        maxWidth: cfg.maxLarguraPopup,
        className: "foliumpopup"
    });
})();
"""


def preparar_propriedades_municipio(agregado: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Acrescenta ao agregado os campos crus que o popup do município consome.

    Esta função JÁ MONTOU o HTML do popup e do tooltip, em Python, e não monta
    mais: as contagens por bandeira sempre viajaram nas propriedades da feição
    — é delas que o coroplético reativo soma a seleção do painel —, então o
    HTML pré-renderizado era uma segunda cópia dos mesmos números, em prosa.
    Custava 1,19 MB de ``popup_html`` e 0,25 MB de ``tooltip_html`` para 1.191
    municípios, dos quais o leitor abre alguns. Quem monta o texto agora é
    `_JS_MUNICIPIO`, no clique e no hover.

    O que sobra aqui são os três campos que as contagens não continham:

    * `populacao_valor` — a população como NÚMERO, porque o indicador de lacuna
      a soma. A conversão para `int`/`None` na mão, em vez de deixar o `Int64`
      seguir para o GeoJSON, é o que garante ``null`` no arquivo: o valor
      ausente do pandas serializa como `NaN`, que não é JSON válido e faria
      `JSON.parse` falhar em qualquer ferramenta que não seja o navegador;
    * `populacao_ano` — o ano da estimativa, que aparece entre parênteses;
    * `outras_coops_detalhe` — a composição de "Outra Cooperativa", que não é
      derivável das contagens: ela nomeia marcas que o filtro agrupa.

    Args:
        agregado: saída de `carregar_agregado`.

    Returns:
        Uma CÓPIA do agregado com as três colunas acima normalizadas.
    """
    com_campos = agregado.copy()

    com_campos["populacao_valor"] = [
        None if pd.isna(valor) else int(valor)
        for valor in com_campos["populacao"]
    ]
    com_campos["populacao_ano"] = [
        None if pd.isna(valor) or not str(valor).strip() else str(valor)
        for valor in com_campos["populacao_ano"]
    ]

    detalhe = com_campos.get(agregacao.COLUNA_DETALHE_OUTRAS)
    com_campos[agregacao.COLUNA_DETALHE_OUTRAS] = (
        [""] * len(com_campos)
        if detalhe is None
        else ["" if pd.isna(v) else str(v) for v in detalhe]
    )

    return com_campos


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
        for canal, destino in zip(rgb, alvo, strict=True)
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
        agregado: saída de `preparar_propriedades_municipio`.

    Returns:
        A camada adicionada.
    """
    # As 14 colunas por bandeira vão para as propriedades da feição porque é o
    # cliente que soma a seleção atual — sem elas, filtrar por bandeira no
    # navegador seria impossível. É o que permite o coroplético reativo.
    #
    # `populacao_valor` entra pelo mesmo motivo, um nível acima: é dela que sai
    # o indicador de população em municípios SEM nenhum ponto da seleção, que
    # também muda a cada clique.
    colunas = [
        "municipio_ibge",
        "municipio_nome",
        "uf",
        # `regiao` viaja junto de `uf` porque o recorte no navegador passa por
        # ela: com 27 UFs o filtro é hierárquico (região -> estado), e o
        # controlador precisa saber a que região cada município pertence sem
        # carregar uma segunda tabela UF -> região no HTML.
        "regiao",
        "populacao_valor",
        # O ano da estimativa e a composição de "Outra Cooperativa" são os dois
        # campos do popup que as contagens não carregam. Somados, custam ~30 KB
        # nas 1.191 feições — contra os 1,44 MB do popup e do tooltip que este
        # mesmo arquivo trazia prontos até a etapa anterior.
        "populacao_ano",
        agregacao.COLUNA_DETALHE_OUTRAS,
        "total_geral",
        "total_bancos",
        "total_cooperativas",
        *_colunas_por_bandeira(),
        "geometry",
    ]

    camada = folium.GeoJson(
        agregado[colunas],
        name="Municípios",
        control=False,
        # `pane` chega às feições porque o folium repassa os kwargs às opções
        # do `L.geoJson`, e o Leaflet usa esse mesmo objeto de opções ao
        # construir cada polígono. Ver `PANE_COROPLETICO` para o porquê.
        pane=PANE_COROPLETICO,
        style_function=lambda _feicao: {
            "fillColor": COR_ZERO,
            "color": COR_CONTORNO_MUNICIPIO,
            "weight": LARGURA_CONTORNO_MUNICIPIO,
            "fillOpacity": OPACIDADE_COROPLETICO,
        },
        highlight_function=lambda _feicao: {
            "weight": 2.4,
            "color": COR_PETROLEO_ESCURO,
        },
        # Sem `popup=` nem `tooltip=`: os dois são ligados pelo controlador,
        # com uma FUNÇÃO no lugar do campo pré-renderizado — ver `_JS_MUNICIPIO`.
        # O `GeoJsonPopup` do folium só sabe despejar o valor bruto de um campo
        # numa célula de tabela, e o que se quer aqui é montar o texto na hora,
        # a partir das contagens que a feição já carrega.
        smooth_factor=0.5,
    )
    camada.add_to(mapa)

    # O texto do popup e do tooltip é montado no navegador, a partir destas
    # mesmas propriedades. O script vai como filho do mapa logo depois da
    # camada, porque referencia a variável que o folium acabou de declarar
    # para ela.
    configuracao = {
        "secoes": [
            {
                "rotulo": "Bancos (5 grandes)",
                "coluna": "total_bancos",
                "bandeiras": _bandeiras_da_categoria(CATEGORIA_BANCO),
            },
            {
                "rotulo": "Pontos de cooperativas",
                "coluna": "total_cooperativas",
                "bandeiras": _bandeiras_da_categoria(CATEGORIA_COOPERATIVA),
            },
        ],
        "subIndefinida": agregacao.SUB_CATEGORIA_COOP_INDEFINIDA,
        "colunaDetalhe": agregacao.COLUNA_DETALHE_OUTRAS,
        "maxLarguraPopup": MAX_LARGURA_POPUP_MUNICIPIO,
    }
    mapa.add_child(
        _ScriptDoMapa(
            _JS_MUNICIPIO.replace(
                "__CONFIG__", json.dumps(configuracao, ensure_ascii=False)
            ).replace("__GEOJSON__", camada.get_name()),
            nome="TextosDoMunicipio",
        )
    )
    return camada


def _bandeiras_da_categoria(categoria: str) -> list[list[str]]:
    """Pares ``[bandeira, coluna do agregado]`` de uma categoria, na ordem do painel.

    Args:
        categoria: `CATEGORIA_COOPERATIVA` ou `CATEGORIA_BANCO`.

    Returns:
        Ex.: ``[["Sicredi", "total_sicredi"], ...]``.
    """
    return [
        [sub, f"total_{agregacao._sufixo_coluna(sub)}"]
        for sub in ORDEM_SUB_CATEGORIAS[categoria]
    ]


def dissolver_divisas_uf(agregado: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Une os municípios de cada UF num polígono só, para desenhar a divisa.

    A fronteira estadual é derivada da MESMA malha municipal que o coroplético
    usa, e não baixada à parte: assim as duas não têm como discordar — a divisa
    do RS é, por construção, o contorno externo dos 497 municípios desenhados.

    Args:
        agregado: saída de `carregar_agregado`.

    Returns:
        GeoDataFrame com uma linha por UF, colunas ``uf`` e ``geometry``.
    """
    divisas = agregado[["uf", "geometry"]].dissolve(by="uf", as_index=False)
    _LOGGER.info(
        "Divisas estaduais dissolvidas: %s.", ", ".join(sorted(divisas["uf"]))
    )
    return divisas


def adicionar_divisas_uf(
    mapa: folium.Map,
    agregado: gpd.GeoDataFrame,
) -> folium.GeoJson:
    """Adiciona a camada da divisa entre estados, por cima do coroplético.

    Entra com ``control=False`` (é fundo, não opção) e ``interactive=False``:
    a divisa não tem popup nem tooltip, e um polígono do tamanho de um estado
    capturando o mouse roubaria o clique de todo município e de todo marcador
    embaixo dela. O pane próprio, sem eventos de ponteiro, é a segunda trava do
    mesmo problema.

    Args:
        mapa: mapa base, já com os panes de `criar_mapa_base`.
        agregado: saída de `carregar_agregado`.

    Returns:
        A camada adicionada — o controlador reativo a usa para apagar a divisa
        dos estados que o filtro de UF deixa de fora.
    """
    camada = folium.GeoJson(
        dissolver_divisas_uf(agregado),
        name="Divisas estaduais",
        control=False,
        pane=PANE_DIVISAS_UF,
        interactive=False,
        style_function=lambda _feicao: {
            "color": COR_DIVISA_UF,
            "weight": LARGURA_DIVISA_UF,
            "fill": False,
        },
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


def limites_por_uf(agregado: gpd.GeoDataFrame) -> dict[str, list[list[float]]]:
    """Retângulo envolvente de cada UF e do recorte inteiro, no formato do Leaflet.

    É o que o filtro de estado usa para enquadrar o mapa (`fitBounds`), e a
    chave ``"todos"`` é para onde ele volta ao desmarcar o filtro.

    A caixa sai da geometria de fato, e não de uma constante: `CENTRO_MAPA` e
    `ZOOM_INICIAL` descrevem o enquadramento de abertura, que é escolha de
    apresentação; aqui o que se quer é o retângulo real de cada estado.

    Args:
        agregado: saída de `carregar_agregado`.

    Returns:
        Ex.: ``{"todos": [[-33.75, -57.65], [-22.52, -48.02]], "RS": [...]}``,
        cada valor no par ``[[sul, oeste], [norte, leste]]`` que o Leaflet pede.
    """

    def caixa(recorte: gpd.GeoDataFrame) -> list[list[float]]:
        oeste, sul, leste, norte = recorte.total_bounds
        return [[float(sul), float(oeste)], [float(norte), float(leste)]]

    limites = {"todos": caixa(agregado)}
    for uf, do_estado in agregado.groupby("uf"):
        limites[str(uf)] = caixa(do_estado)
    return limites


def enquadramento_inicial(
    agregado: gpd.GeoDataFrame,
) -> tuple[tuple[float, float], int]:
    """Centro e zoom de abertura, medidos no recorte que foi carregado.

    Substitui as constantes `CENTRO_MAPA` e `ZOOM_INICIAL` que o projeto
    carregava calculadas à mão para a *bounding box* do Sul. A conta é a mesma
    que os comentários daquelas constantes descreviam — está em
    `config.centro_da_caixa` e `config.zoom_da_caixa` —, só que aplicada à
    geometria de fato, e não a números transcritos: com o recorte do Sul ela
    devolve ``(-28.13, -52.84)`` e zoom 6, exatamente os valores antigos.

    Args:
        agregado: saída de `carregar_agregado`.

    Returns:
        ``((lat, lon), zoom)``.
    """
    caixa = limites_por_uf(agregado)["todos"]
    return config.centro_da_caixa(caixa), config.zoom_da_caixa(caixa)


def ufs_do_recorte(agregado: gpd.GeoDataFrame) -> list[str]:
    """UFs presentes no agregado, na ordem em que o filtro de estado as mostra.

    Quem manda sobre QUAIS UFs entram é o dado: o mapa é gerado a partir do
    agregado já gravado, que pode ter sido produzido por um recorte diferente
    do ativo — abrir ``python -m src.mapa`` sobre o agregado nacional é
    exatamente esse caso.

    Quem manda sobre a ORDEM é o recorte ativo (`config.SIGLAS_UF`), porque
    ela é escolha de apresentação e está declarada lá. O que sobrar entra
    depois, em ordem de código do IBGE, e uma UF fora até da tabela entra por
    último, em ordem alfabética — nada é descartado, para que o filtro continue
    cobrindo todo o agregado mesmo com a configuração para trás.

    Args:
        agregado: saída de `carregar_agregado`.

    Returns:
        Ex.: ``["RS", "SC", "PR"]``.
    """
    presentes = {str(uf) for uf in agregado["uf"].dropna().unique()}

    do_recorte = [uf for uf in config.SIGLAS_UF if uf in presentes]
    restantes = presentes - set(do_recorte)
    conhecidas = [uf for uf in config.SIGLAS_BR if uf in restantes]
    novas = sorted(restantes - set(config.SIGLAS_BR))
    if novas:
        _LOGGER.warning(
            "UF(s) fora de config.CODIGO_UF no agregado: %r. "
            "Entraram ao fim do filtro de estado; atualize a tabela.",
            novas,
        )
    return do_recorte + conhecidas + novas


# --------------------------------------------------------------------------- #
# 4. Moldura da página
# --------------------------------------------------------------------------- #


def _segmentos(nome: str, opcoes: list[tuple[str, str]], marcado: str) -> str:
    """Monta um grupo de botões-segmento (rádios estilizados) da barra.

    Os rádios são gerados aqui, em Python, e não pelo controlador em
    JavaScript: os modos e as UFs são conhecidos na geração, e HTML que já
    nasce no arquivo aparece na primeira pintura — o que o JavaScript montasse
    piscaria depois. O controlador só liga os ouvintes.

    Args:
        nome: valor de ``name`` compartilhado pelos rádios do grupo.
        opcoes: pares ``(valor, rótulo)`` na ordem de exibição.
        marcado: o valor que abre marcado.

    Returns:
        O HTML do grupo.
    """
    botoes = "".join(
        f'<label class="segmento"><input type="radio" name="{nome}" '
        f'value="{html.escape(valor)}"'
        f'{" checked" if valor == marcado else ""}>{rotulo}</label>'
        for valor, rotulo in opcoes
    )
    return f'<div class="segmentos">{botoes}</div>'


def _html_indicadores() -> str:
    """Monta os quatro cartões de indicador, ainda sem número.

    Os valores são escritos pelo controlador a cada mudança de seleção — ver
    `_JS_CONTROLADOR`. O que sai daqui é só a moldura, com um traço no lugar do
    número: gerar o valor da seleção inicial em Python o deixaria desatualizado
    já no primeiro clique.

    Returns:
        O HTML da faixa de indicadores.
    """
    cartoes = [
        ("kpi-pontos", "Pontos de atendimento", ""),
        ("kpi-municipios", "Municípios atendidos", ""),
        ("kpi-vazios", "Municípios sem atendimento", " lacuna"),
        ("kpi-populacao", "População sem atendimento", " lacuna"),
    ]
    return (
        '<section class="indicadores" aria-live="polite">'
        + "".join(
            f'<article class="indicador{extra}">'
            f'<p class="indicador-rotulo">{rotulo}</p>'
            f'<p class="indicador-valor" id="{ident}">&mdash;</p>'
            f'<p class="indicador-nota" id="{ident}-nota"></p>'
            "</article>"
            for ident, rotulo, extra in cartoes
        )
        + "</section>"
    )


def adicionar_moldura(mapa: folium.Map, agregado: gpd.GeoDataFrame) -> None:
    """Injeta a moldura da página: marca, título, indicadores, barra e cartões.

    O que entra aqui é a página INTEIRA em volta do mapa — cabeçalho de marca,
    título, os quatro indicadores, a barra de leitura/estado/busca, o cartão do
    mapa (vazio), a coluna de bandeiras e de ranking, e o rodapé de fontes. O
    mapa e o painel de camadas são MOVIDOS para dentro dela pelo controlador,
    assim que a página carrega (ver `_JS_CONTROLADOR`).

    Mover em vez de gerar no lugar certo é imposição do folium: os elementos
    adicionados a ``get_root().html`` são escritos ANTES da ``<div>`` do mapa,
    que só é anexada ao documento durante a renderização. Não há como abrir a
    moldura antes e fechá-la depois sem partir o HTML em dois pedaços
    desbalanceados, um de cada lado do mapa. Com a moldura inteira de um lado e
    uma linha de JavaScript encaixando o mapa nela, o HTML fica bem formado e o
    encaixe acontece antes da primeira pintura — os scripts do folium são
    síncronos, então nada pisca.

    Args:
        mapa: mapa base.
        agregado: saída de `carregar_agregado`, de onde sai a lista de UFs do
            filtro de estado.
    """
    modos = [(modo["id"], html.escape(modo["rotulo"])) for modo in MODOS_VISAO]
    ufs = [("", "Todos")] + [(uf, uf) for uf in ufs_do_recorte(agregado)]

    moldura = f"""
<div class="app">
  <header class="app-topo">
    <div class="app-topo-interno">
      <span class="marca">
        {SVG_ICONE_COOPERATIVISMO}
        <span class="marca-texto">
          <b>Presença Física</b>
          <small>Cooperativas de crédito e bancos &middot; Região Sul</small>
        </span>
      </span>
      <span class="selo-safra">Dados de <b>{config.DATA_DADOS}</b></span>
    </div>
  </header>

  <div class="app-corpo">
    <div class="app-abertura">
      <div class="app-cabecalho">
        <p class="olho">{OLHO_MAPA}</p>
        <h1>{TITULO_MAPA}</h1>
        <p class="app-linha-fina">{SUBTITULO_MAPA}</p>
      </div>
      {_html_indicadores()}
    </div>

    <div class="barra">
      <div class="barra-grupo">
        <span class="barra-rotulo">Leitura</span>
        {_segmentos("modo-visao", modos, MODO_INICIAL)}
      </div>
      <div class="barra-divisor"></div>
      <div class="barra-grupo">
        <span class="barra-rotulo">Estado</span>
        {_segmentos("filtro-uf", ufs, "")}
      </div>
      <div class="barra-dica" id="dica-modo"></div>
      <div class="barra-grupo barra-busca">
        <div class="busca-municipio">
          <input id="busca-campo" type="text" autocomplete="off"
                 placeholder="{html.escape(TEXTO_BUSCA)}"
                 aria-label="{html.escape(TEXTO_BUSCA)}">
          <ul class="busca-sugestoes" id="busca-lista" hidden></ul>
        </div>
      </div>
    </div>

    <div class="area">
      <section class="cartao cartao-mapa">
        <div class="mapa-slot" id="slot-mapa"></div>
        <div class="mapa-rodape" id="legenda-coropletico"></div>
      </section>

      <aside class="coluna-lateral">
        <section class="cartao cartao-bandeiras">
          <header class="cartao-topo">
            <h2>Bandeiras</h2>
            <div class="acoes">
              <button type="button" id="acao-todas">Todas</button>
              <button type="button" id="acao-nenhuma">Nenhuma</button>
            </div>
          </header>
          <div class="cartao-conteudo" id="painel-bandeiras"></div>
        </section>

        <section class="cartao cartao-ranking">
          <header class="cartao-topo">
            <h2>Maior presença</h2>
            <span class="cartao-nota" id="ranking-nota"></span>
          </header>
          <ol class="cartao-conteudo ranking" id="ranking-lista"></ol>
        </section>
      </aside>
    </div>

    <p class="app-rodape">{CREDITO_FONTES.format(data=config.DATA_DADOS)}</p>
  </div>
</div>
"""
    mapa.get_root().html.add_child(Element(moldura))


# --------------------------------------------------------------------------- #
# 5. Pontos já geocodificados
# --------------------------------------------------------------------------- #


def carregar_pontos_geocodificados(caminho: Path | None = None) -> pd.DataFrame:
    """Lê os pontos de atendimento com coordenada e nível de precisão.

    Este módulo não geocodifica nada: ele consome o que `src.cnefe` resolveu.
    A separação é intencional — a geocodificação depende de ~580 MB de CNEFE em
    cache e leva minutos, enquanto o desenho do mapa é iterado dezenas de vezes
    durante um ajuste de cor ou de popup.

    Args:
        caminho: Parquet produzido por `src.cnefe`; ``None`` deriva do recorte
            ativo.

    Returns:
        DataFrame com uma linha por ponto de atendimento, incluindo
        `latitude`, `longitude` e `precisao`.

    Raises:
        FileNotFoundError: se o arquivo não existir — rode `python -m src.cnefe`.
        KeyError: se faltar alguma coluna exigida pelo mapa.
    """
    caminho = caminho or config.arquivo_pontos_geocodificados()
    if not caminho.exists():
        raise FileNotFoundError(
            f"Pontos geocodificados não encontrados: {caminho}. "
            "Rode `python -m src.cnefe` para gerá-los."
        )

    pontos = pd.read_parquet(caminho)

    # A lista cobre TUDO que o desenho lê: as três colunas da geocodificação,
    # as duas que montam as camadas e as sete que popup e tooltip renderizam.
    # Uma lista mais curta deixaria um Parquet de safra antiga passar na
    # validação e quebrar com KeyError lá adiante, dentro do laço dos 7.600
    # marcadores — sem a mensagem que diz como consertar.
    exigidas = {
        "latitude",
        "longitude",
        "precisao",
        "categoria_if",
        "sub_categoria",
        "marca_exibicao",
        "nome_instalacao",
        "nome_instituicao",
        "tipo_instalacao",
        "endereco",
        "numero",
        "bairro",
        "cep",
        "municipio",
        "uf",
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
# 6. Camadas de ponto em dois níveis
# --------------------------------------------------------------------------- #


#: Casas decimais com que a coordenada de cada ponto viaja no HTML.
#:
#: Sete casas são ~1,1 cm de latitude. É bem mais fino do que o mapa consegue
#: mostrar (no zoom 20, o máximo que o basemap serve, um pixel vale ~13 cm) e
#: bem mais grosso do que o leque que separa pontos coincidentes, que trabalha
#: em metros (`cnefe.RAIO_DESEMPATE_M`). O que ele economiza é real: a
#: coordenada vem de um float32 do CNEFE alargado para float64, e o `repr` do
#: float64 escreve 18 dígitos — ``-25.42959976196289`` —, dos quais os últimos
#: dez são artefato da conversão, não medida do Censo.
CASAS_COORDENADA = 7

#: Colunas do ponto que viajam como TABELA de valores distintos + um índice por
#: ponto, em vez do valor repetido linha a linha.
#:
#: São as de baixa cardinalidade: os 7.603 pontos do Sul têm 2 tipos de
#: instalação, 4 níveis de precisão, 14 bandeiras, 228 instituições e 1.157
#: municípios. Escrever "COOPERATIVA DE CRÉDITO, POUPANÇA E INVESTIMENTO DO
#: NORTE E NORDESTE DE SANTA CATARINA - SICREDI NORTE SC" 200 vezes é o tipo de
#: repetição que o gzip disfarça no arquivo baixado e o `JSON.parse` do
#: navegador não.
COLUNAS_TABELADAS = (
    "nome_instituicao",
    "marca_exibicao",
    "tipo_instalacao",
    "municipio",
    "uf",
    "precisao",
    "bairro",
    "cep",
    "numero",
)

#: Colunas que viajam como texto solto, uma string por ponto.
#:
#: São as duas de cardinalidade quase máxima — 7.226 nomes de instalação e
#: 5.686 endereços em 7.603 pontos. Tabelar não economizaria nada: a tabela
#: teria quase o tamanho da coluna, mais o vetor de índices por cima.
COLUNAS_LIVRES = ("nome_instalacao", "endereco")

#: Nome curto de cada coluna dentro do payload. Ele aparece uma vez só no
#: arquivo, mas mantém o JSON legível para quem for depurá-lo no navegador.
_APELIDO_COLUNA = {
    "nome_instituicao": "inst",
    "marca_exibicao": "marca",
    "tipo_instalacao": "tipo",
    "municipio": "mun",
    "uf": "uf",
    "precisao": "prec",
    "bairro": "bairro",
    "cep": "cep",
    "numero": "num",
    "nome_instalacao": "nome",
    "endereco": "end",
}


def _texto_da_celula(valor) -> str:
    """Normaliza uma célula do Parquet no texto que o navegador vai receber.

    Nulo do pandas vira string vazia, e não ``"nan"`` ou ``"<NA>"``: é a string
    vazia que as funções JavaScript testam para decidir se o campo existe, do
    mesmo modo que as versões em Python testavam com `pd.isna`.

    Args:
        valor: a célula, de qualquer dtype.

    Returns:
        O texto.
    """
    return "" if pd.isna(valor) else str(valor)


def _tabelar(valores: list[str]) -> tuple[list[str], list[int]]:
    """Troca uma coluna de textos por (tabela de distintos, índices).

    A tabela sai na ordem de PRIMEIRA APARIÇÃO, e não ordenada: assim os
    valores mais frequentes tendem a receber os índices menores, que são os
    mais curtos de escrever, e a saída continua determinística — que é o que
    permite comparar dois HTML gerados do mesmo dado.

    Args:
        valores: a coluna, já normalizada por `_texto_da_celula`.

    Returns:
        ``(tabela, indices)``, com ``tabela[indices[i]] == valores[i]``.
    """
    tabela: list[str] = []
    posicao: dict[str, int] = {}
    indices: list[int] = []
    for valor in valores:
        indice = posicao.get(valor)
        if indice is None:
            indice = len(tabela)
            posicao[valor] = indice
            tabela.append(valor)
        indices.append(indice)
    return tabela, indices


def _dados_dos_pontos(ordenados: pd.DataFrame) -> dict:
    """Monta o payload compacto dos pontos, no formato que o JavaScript lê.

    O formato é de ARRAYS PARALELOS, um por campo, e não uma lista de objetos:
    um objeto por ponto repetiria os nomes das chaves 30 mil vezes, que é
    exatamente o custo que esta etapa existe para eliminar. Cada campo aparece
    de uma das três formas:

    * `lat` / `lon` — números, arredondados a `CASAS_COORDENADA`;
    * as colunas de `COLUNAS_TABELADAS` — uma tabela de valores distintos em
      ``tab`` e um vetor de índices em ``col``;
    * as colunas de `COLUNAS_LIVRES` — o texto solto, em ``livre``.

    A ORDEM das linhas é a ordem de criação dos marcadores no navegador, e é a
    mesma em que `adicionar_camadas_de_pontos` percorre grupos e bandeiras: é
    isso que permite a cada subgrupo receber uma FAIXA ``[ini, fim)`` do vetor,
    em vez de uma coluna dizendo, ponto a ponto, a que bandeira ele pertence.

    Args:
        ordenados: os pontos já concatenados na ordem de emissão.

    Returns:
        O dicionário que vira JSON no HTML.
    """
    dados: dict = {
        "n": len(ordenados),
        "lat": [round(float(v), CASAS_COORDENADA) for v in ordenados["latitude"]],
        "lon": [round(float(v), CASAS_COORDENADA) for v in ordenados["longitude"]],
        "tab": {},
        "col": {},
        "livre": {},
        # O disco e o contorno são os mesmos de sempre, mas agora quem os
        # aplica é o laço JavaScript, então eles precisam atravessar.
        "raio": RAIO_MARCADOR,
        "larguraContorno": LARGURA_CONTORNO_MARCADOR,
        "opacidadePreenchimento": OPACIDADE_MARCADOR,
        "maxLarguraPopup": MAX_LARGURA_POPUP_PONTO,
        # A tabela de precisão é de `src.cnefe` e atravessa em vez de ser
        # reescrita aqui: duas cópias da mesma tabela divergem com o tempo.
        "precisao": {
            "descricao": dict(cnefe.DESCRICAO_PRECISAO),
            "aviso": [cnefe.PRECISAO_LOCALIDADE, cnefe.PRECISAO_MUNICIPIO],
        },
    }

    for coluna in COLUNAS_TABELADAS:
        tabela, indices = _tabelar(
            [_texto_da_celula(v) for v in ordenados[coluna]]
        )
        dados["tab"][_APELIDO_COLUNA[coluna]] = tabela
        dados["col"][_APELIDO_COLUNA[coluna]] = indices

    for coluna in COLUNAS_LIVRES:
        dados["livre"][_APELIDO_COLUNA[coluna]] = [
            _texto_da_celula(v) for v in ordenados[coluna]
        ]

    return dados


#: O laço que constrói os marcadores no navegador, e as funções de popup e de
#: tooltip que antes eram Python.
#:
#: As quatro funções de texto — `enderecoDoPonto`, `marcaDoPonto`,
#: `popupDoPonto` e `tooltipDoPonto` — são a tradução literal das que viviam
#: neste módulo (`_texto_endereco`, `_marca_do_ponto`, `_popup_ponto`,
#: `_tooltip_ponto`), APAGADAS na mesma mudança. Duas implementações da mesma
#: regra divergem com o tempo, e a regra aqui não é cosmética: ela decide
#: quando o número do imóvel já está visível no texto do logradouro, qual nome
#: comercial aparece no lugar de "Outra Cooperativa" e qual dos dois
#: tratamentos o nível de precisão recebe.
#:
#: Elas rodam no CLIQUE e no HOVER, e não na geração: o `bindPopup` do Leaflet
#: aceita uma FUNÇÃO no lugar do conteúdo e só a chama quando o balão abre
#: (`DivOverlay._updateContent`). Era isso que custava ~4 MB no arquivo do Sul —
#: HTML de popup e de tooltip pré-renderizado para 7.603 pontos, dos quais o
#: leitor abre alguns.
_JS_PONTOS = r"""
var mapaPontos = __DADOS__;

(function () {
    "use strict";
    var d = mapaPontos;
    /* `esc` e `escRe` são o `html.escape` e o `re.escape` do Python, definidos
       uma vez só em `_JS_FORMATO` — ver o comentário lá sobre por que não são
       copiados aqui. */
    var esc = window.mapaFormato.esc;
    var escRe = window.mapaFormato.escRe;

    /* Valor tabelado (`d.tab`) e texto solto (`d.livre`) — ver
       `_dados_dos_pontos`. */
    function v(coluna, i) { return d.tab[coluna][d.col[coluna][i]]; }
    function livre(coluna, i) { return d.livre[coluna][i]; }

    /* Tradução de `_marca_do_ponto`. Prefere a `marca_exibicao`, que nomeia as
       cooperativas agrupadas sob "Outra Cooperativa", e cai na bandeira quando
       o campo vem vazio. */
    function marcaDoPonto(i, sub) {
        var marca = v("marca", i);
        return (marca && marca.trim()) ? marca : sub;
    }

    /* Tradução de `_texto_endereco`.

       O número só é acrescentado quando NÃO está embutido no endereço: a fonte
       grava "PCA.TIRADENTES,410" numas linhas e o número em coluna própria em
       outras, e repeti-lo produziria "PCA.TIRADENTES,410, 410".

       O número já está à vista quando aparece DEPOIS DE UMA VÍRGULA
       ("PCA.TIRADENTES,410", "AVENIDA DA VINDIMA, NUM 303") ou NO FIM do
       endereço ("AV BENTO GONCALVES 1157") — as duas formas que a fonte usa
       para embutir o número no texto do logradouro.

       As duas posições são exigidas por motivos opostos. Só a vírgula deixava
       passar "AV BENTO GONCALVES 1157" e rendia "1157, 1157" no popup. Já
       procurar o número em QUALQUER posição erra para o outro lado: o "15" de
       "RUA 15 DE NOVEMBRO" esconderia o número 15 de um imóvel dessa mesma rua.

       O bairro e o CEP entram SEM `trim`, como no original: o `trim` decide se
       o campo existe, não o que é exibido. */
    function enderecoDoPonto(i) {
        var endereco = livre("end", i);
        var partes = [esc(endereco)];

        var numero = v("num", i);
        if (numero && numero.trim()) {
            var procurado = escRe(numero.trim());
            var padrao = new RegExp(
                ",[^,]*\\b" + procurado + "\\b|\\b" + procurado + "\\b\\s*$"
            );
            if (!padrao.test(endereco)) {
                partes.push(", " + esc(numero.trim()));
            }
        }

        var complemento = [];
        var bairro = v("bairro", i);
        if (bairro && bairro.trim()) { complemento.push(esc(bairro)); }
        var cep = v("cep", i);
        if (cep && cep.trim()) { complemento.push(esc(cep)); }
        if (complemento.length) {
            partes.push(" — " + complemento.join(", "));
        }

        return partes.join("");
    }

    /* Tradução de `_popup_ponto`.

       O nível de precisão é parte fixa do popup, e não um detalhe de rodapé:
       os pontos deste mapa NÃO têm todos a mesma precisão — a maioria está no
       imóvel ou na rua, uma minoria só no município —, e quem clica precisa
       saber em qual caso está sem ter de conhecer a implementação. */
    function popupDoPonto(i, sub) {
        var nome = esc(livre("nome", i));
        var instituicao = esc(v("inst", i));
        var marca = esc(marcaDoPonto(i, sub));
        var subCategoria = esc(sub);
        var tipo = esc(v("tipo", i));
        var municipio = esc(v("mun", i));
        var uf = esc(v("uf", i));

        /* Quando a marca exibida não é a bandeira, o ponto está pintado com a
           cor de "Outra Cooperativa" e é por esse nome que ele aparece no
           filtro. Dizer isso evita a contradição de um marcador rotulado
           "Sisprime" que some ao desmarcar uma camada chamada outra coisa. */
        var filtro = (marca === subCategoria) ? "" :
            '<div class="popup-secundario">no filtro: ' + subCategoria + "</div>";

        var precisao = v("prec", i);
        var descricao = d.precisao.descricao[precisao];
        if (descricao === undefined) { descricao = precisao; }
        /* Só os dois níveis frouxos ganham destaque de aviso; nos dois
           precisos a informação é apenas a procedência da coordenada. */
        var classe = d.precisao.aviso.indexOf(precisao) >= 0
            ? "aviso-posicao" : "procedencia";

        return '<div class="popup-municipio">' +
            "<h4>" + nome + "</h4>" +
            "<div><b>" + marca + "</b> &middot; " + tipo + "</div>" +
            filtro +
            '<div class="popup-secundario">' + instituicao + "</div>" +
            "<div style='padding-top:5px'>" + enderecoDoPonto(i) +
            "<br>" + municipio + "/" + uf + "</div>" +
            '<div class="' + classe + '" style="padding-top:6px">' +
            "Posição: " + esc(descricao) + ".</div>" +
            "</div>";
    }

    /* Tradução de `_tooltip_ponto`. Curto de propósito: o tooltip segue o
       cursor e some, então responde só "o que é este ponto" — marca e nome da
       instalação. O resto está no popup, a um clique.

       A comparação marca/bandeira é feita aqui nos textos CRUS e no popup nos
       já escapados. As duas versões em Python faziam exatamente assim, e o
       resultado só poderia divergir para um nome de bandeira que contivesse
       `&`, `<`, `>` ou aspas. */
    function tooltipDoPonto(i, sub) {
        var marca = marcaDoPonto(i, sub);
        var sufixo = (marca === sub) ? "" :
            ' <span class="popup-secundario">(' + esc(sub) + ")</span>";
        return "<b>" + esc(marca) + "</b>" + sufixo + " &middot; " +
            esc(v("tipo", i)) + "<br>" + esc(livre("nome", i));
    }

    /* Os dois envelopes que o folium punha em volta do conteúdo. Reproduzidos
       porque o CSS da página mira o que está dentro deles: o `<div>` do
       tooltip e o `<div>` de dimensão cheia do popup. O `id` que o folium
       sorteava para o div do popup não é reproduzido — nada, nem CSS nem
       JavaScript, olhava para ele. */
    function envelopePopup(html) {
        return '<div style="width: 100.0%; height: 100.0%;">' + html + "</div>";
    }
    function envelopeTooltip(html) {
        return "<div>" + html + "</div>";
    }

    /* Constrói os marcadores de UMA bandeira e os entrega ao subgrupo dela.

       Chamada uma vez por subgrupo, com a faixa `[ini, fim)` daquela bandeira
       no vetor de pontos. É deliberado que ela rode ANTES de
       `subgrupo.addTo(mapa)`: com o subgrupo ainda fora do mapa, `addLayer` só
       guarda o marcador em `_layers`, e o cluster recebe os milhares de uma
       vez, no lote que o `Leaflet.FeatureGroup.SubGroup` dispara ao ser
       adicionado. Era esse o caminho que o HTML gerado pelo folium seguia;
       chamá-la depois faria o agrupamento se reorganizar uma vez por ponto.

       As opções do disco são compartilhadas por UF dentro da bandeira — o
       único campo que varia entre marcadores é `tags`. Compartilhar é seguro
       porque o `L.Util.setOptions` do Leaflet COPIA o objeto recebido para um
       novo, em vez de guardá-lo. */
    window.mapaPontosCriar = function (subgrupo, ini, fim, sub, cor, contorno) {
        var opcoesPorUf = {};

        function conteudoPopup(camada) {
            return envelopePopup(popupDoPonto(camada.__ponto, sub));
        }
        function conteudoTooltip(camada) {
            return envelopeTooltip(tooltipDoPonto(camada.__ponto, sub));
        }

        for (var i = ini; i < fim; i++) {
            var uf = v("uf", i);
            var opcoes = opcoesPorUf[uf];
            if (!opcoes) {
                opcoes = opcoesPorUf[uf] = {
                    bubblingMouseEvents: true,
                    color: contorno,
                    dashArray: null,
                    dashOffset: null,
                    fill: true,
                    fillColor: cor,
                    fillOpacity: d.opacidadePreenchimento,
                    fillRule: "evenodd",
                    lineCap: "round",
                    lineJoin: "round",
                    opacity: 1.0,
                    radius: d.raio,
                    stroke: true,
                    /* A UF viaja com o marcador porque é por ela que o filtro
                       de estado escolhe quem fica no mapa. Continua em `tags`,
                       o mesmo campo de antes, que é onde o controlador a
                       procura (`m.options.tags`). */
                    tags: [uf],
                    weight: d.larguraContorno
                };
            }
            var marcador = L.circleMarker([d.lat[i], d.lon[i]], opcoes);
            /* O índice do ponto, e não os textos dele: é com o índice que as
               funções de popup e de tooltip acham a linha na hora da
               interação. */
            marcador.__ponto = i;
            subgrupo.addLayer(marcador);
            marcador.bindPopup(conteudoPopup, {maxWidth: d.maxLarguraPopup});
            marcador.bindTooltip(conteudoTooltip, {sticky: true});
        }
    };
})();
"""


class _ScriptDoMapa(MacroElement):
    """Envelope que emite um bloco de JavaScript cru na ordem de inserção.

    Existe por uma questão de ORDEM. Os scripts deste módulo referenciam as
    variáveis JavaScript que o folium cria para o mapa e para cada camada
    (``map_ab12...``, ``feature_group_sub_group_cd34...``), e portanto têm de
    aparecer depois delas no arquivo. Adicionar o script direto em
    ``get_root().script`` não serve: os filhos diretos daquela seção são
    escritos ANTES de todos os blocos que o folium gera durante a renderização,
    e o script acabava no topo, referenciando variáveis ainda não declaradas —
    falhando com "mapa ou camada não encontrados".

    Como `MacroElement` filho de outro elemento, o bloco entra na ordem de
    inserção daquele elemento. São dois usos, e a diferença entre eles importa:

    * filho do MAPA, adicionado por último — sai por último, depois de todas as
      camadas. É o caso do controlador reativo;
    * filho de um SUBGRUPO — sai dentro da janela em que aquele subgrupo já
      existe e ainda não foi adicionado ao mapa, que é de onde o laço de
      construção dos marcadores depende para entregar os pontos ao cluster em
      lote (ver `_JS_PONTOS`).

    Attributes:
        js: o JavaScript a emitir, já com os nomes das variáveis substituídos.
    """

    _template = Template(
        "{% macro script(this, kwargs) %}{{ this.js | safe }}{% endmacro %}"
    )

    def __init__(self, js: str, nome: str = "ScriptDoMapa"):
        super().__init__()
        self._name = nome
        self.js = js


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
) -> list[dict]:
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

    Os MARCADORES, porém, não são emitidos aqui um a um. O que vai para o HTML
    é o vetor compacto de `_dados_dos_pontos` mais uma chamada por bandeira ao
    laço de `_JS_PONTOS`, que constrói os discos no navegador. A troca é de
    representação, não de comportamento: o marcador que o laço monta tem as
    mesmas opções, entra no mesmo subgrupo, na mesma ordem, e responde ao
    clique e ao hover com o mesmo texto — que agora é montado na hora, em vez
    de vir pronto no arquivo.

    Args:
        mapa: mapa base.
        localizados: saída de `carregar_pontos_geocodificados`.

    Returns:
        Um dicionário por grupo, com o rótulo, o objeto da camada-pai e a lista
        de subgrupos (rótulo, objeto da camada, coluna do agregado e contagem).
        O controlador reativo precisa dos OBJETOS, não só dos nomes: é por eles
        que o JavaScript identifica qual camada o usuário marcou.
    """
    # As faixas são montadas ANTES de qualquer camada existir, porque o vetor
    # de pontos precisa ir para o HTML na mesma ordem em que os marcadores
    # serão criados — é o que permite a cada bandeira receber um `[ini, fim)`
    # em vez de uma coluna de bandeira por ponto. Ver `_dados_dos_pontos`.
    faixas: list[dict] = []
    partes: list[pd.DataFrame] = []
    inicio = 0
    for categoria, rotulo_grupo in ROTULO_GRUPO.items():
        do_grupo = localizados[localizados["categoria_if"] == categoria]
        if do_grupo.empty:
            _LOGGER.warning("Nenhum ponto na categoria %r; grupo omitido.", categoria)
            continue

        subs: list[dict] = []
        for sub_categoria in _ordenar_sub_categorias(
            set(do_grupo["sub_categoria"].dropna().unique()), categoria
        ):
            da_bandeira = do_grupo[do_grupo["sub_categoria"] == sub_categoria]
            partes.append(da_bandeira)
            subs.append(
                {
                    "rotulo": sub_categoria,
                    "cor": cor_do_marcador(sub_categoria, categoria),
                    "ini": inicio,
                    "fim": inicio + len(da_bandeira),
                    "pontos": len(da_bandeira),
                }
            )
            inicio += len(da_bandeira)

        faixas.append(
            {
                "categoria": categoria,
                "rotulo": rotulo_grupo,
                "pontos": len(do_grupo),
                "subs": subs,
            }
        )

    ordenados = (
        pd.concat(partes, ignore_index=True)
        if partes
        else localizados.iloc[0:0]
    )

    # O payload e as funções de texto vão como filhos do MAPA, e antes dos
    # clusters, porque o laço de cada bandeira os chama: filhos do mapa saem na
    # ordem de inserção, então este bloco precede todos os subgrupos.
    mapa.add_child(
        _ScriptDoMapa(
            _JS_PONTOS.replace(
                "__DADOS__",
                json.dumps(
                    _dados_dos_pontos(ordenados),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
            nome="DadosDosPontos",
        )
    )

    estrutura: list[dict] = []
    for faixa in faixas:
        # --- Nível 1: o grupo pai ------------------------------------------ #
        grupo_pai = MarkerCluster(
            name=(
                f'<span class="camada-grupo">{html.escape(faixa["rotulo"])}</span>'
                f'<span class="camada-contagem"> ({faixa["pontos"]})</span>'
            ),
            options=OPCOES_CLUSTER,
            control=True,
            show=True,
        )
        grupo_pai.add_to(mapa)

        # --- Nível 2: um subgrupo por bandeira ----------------------------- #
        subgrupos_do_grupo: list[dict] = []
        for sub in faixa["subs"]:
            cor = sub["cor"]
            contorno = _escurecer(cor)
            subgrupo = FeatureGroupSubGroup(
                grupo_pai,
                # A amostra de cor é o que torna a pintura por marca legível:
                # 14 cores no mapa sem nenhuma chave seriam adivinhação, e o
                # painel já lista exatamente as 14 bandeiras, uma por linha.
                name=(
                    f'<span class="camada-cor" style="background:{cor};'
                    f'border-color:{contorno}"></span>'
                    f'<span class="camada-sub">{html.escape(sub["rotulo"])}</span>'
                    f'<span class="camada-contagem"> ({sub["pontos"]})</span>'
                ),
                control=True,
                show=True,
            )
            subgrupo.add_to(mapa)

            # Filho do SUBGRUPO, e não do mapa: é o que coloca a chamada na
            # janela entre a criação do subgrupo e o `addTo(mapa)` dele, que é
            # onde os marcadores têm de entrar para chegarem ao cluster em um
            # lote só. Ver `_ScriptDoMapa` e `_JS_PONTOS`.
            subgrupo.add_child(
                _ScriptDoMapa(
                    "mapaPontosCriar({camada},{ini},{fim},{sub},{cor},{contorno});".format(
                        camada=subgrupo.get_name(),
                        ini=sub["ini"],
                        fim=sub["fim"],
                        sub=json.dumps(sub["rotulo"], ensure_ascii=False),
                        cor=json.dumps(cor),
                        contorno=json.dumps(contorno),
                    ),
                    nome=f'MarcadoresDe{sub["ini"]}',
                )
            )

            subgrupos_do_grupo.append(
                {
                    "rotulo": sub["rotulo"],
                    "camada": subgrupo,
                    "coluna": f'total_{agregacao._sufixo_coluna(sub["rotulo"])}',
                    "pontos": sub["pontos"],
                }
            )

        estrutura.append(
            {
                "categoria": faixa["categoria"],
                "rotulo": faixa["rotulo"],
                "camada": grupo_pai,
                "pontos": faixa["pontos"],
                "subs": subgrupos_do_grupo,
            }
        )
        _LOGGER.info(
            "Grupo %r: %d pontos em %d subgrupos.",
            faixa["rotulo"],
            faixa["pontos"],
            len(subgrupos_do_grupo),
        )

    return estrutura


# --------------------------------------------------------------------------- #
# 7. Mapa base e controle de camadas
# --------------------------------------------------------------------------- #


def criar_mapa_base(
    centro: tuple[float, float], zoom: int
) -> folium.Map:
    """Cria o mapa Folium no enquadramento medido para o recorte.

    A folha de estilo NÃO entra aqui — ver `aplicar_folha_de_estilo`.

    Args:
        centro: ``(latitude, longitude)`` de abertura, de `enquadramento_inicial`.
        zoom: zoom de abertura, de `enquadramento_inicial`.

    Returns:
        O `folium.Map`, já com a camada base, os dois panes próprios e, no
        ``<head>``, o título da aba e o ícone.
    """
    # `prefer_canvas` desenha os 7.600 marcadores num único canvas em vez de um
    # nó SVG por ponto. Sem cluster, todos existem no DOM ao mesmo tempo, e é
    # essa opção que mantém a navegação fluida — ver o cabeçalho do módulo.
    mapa = folium.Map(
        location=list(centro),
        zoom_start=zoom,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    # A camada base é adicionada aqui, e não pelo `tiles=` do construtor, só
    # para poder entrar com `control=False`: o `LayerControl` desenha uma
    # seção de camadas-base mesmo quando existe UMA, e o resultado é um botão
    # de rádio permanentemente marcado, com o alias interno do folium por
    # rótulo ("cartodbpositron"), que não oferece escolha nenhuma. Sem camada
    # base no painel, o Leaflet omite a seção e o separador dela.
    #
    # A URL é montada em `config` em vez de vir do alias "CartoDB positron" do
    # folium porque o alias não tem onde encaixar a chave de API que a CARTO
    # passou a exigir — ver `config.CARTO_API_KEY`. Passando a URL crua, o
    # folium também deixa de fornecer a atribuição embutida no alias, então ela
    # vem explícita em `attr=`, e mantê-la no mapa é condição do uso gratuito.
    folium.TileLayer(
        tiles=config.URL_TILES_PADRAO,
        attr=config.ATRIBUICAO_TILES,
        name=config.TILES_PADRAO,
        subdomains=config.SUBDOMINIOS_TILES,
        max_zoom=config.ZOOM_MAXIMO_TILES,
        max_native_zoom=config.ZOOM_MAXIMO_TILES,
        control=False,
    ).add_to(mapa)

    # As funções de formatação vêm antes de qualquer camada: os scripts das
    # camadas as chamam, e filhos do mapa saem na ordem de inserção.
    mapa.add_child(_ScriptDoMapa(_JS_FORMATO, nome="Formatadores"))

    # Os panes vêm antes de qualquer camada — ver `PANE_COROPLETICO`.
    CustomPane(
        PANE_COROPLETICO, z_index=Z_INDEX_COROPLETICO, pointer_events=True
    ).add_to(mapa)
    CustomPane(
        PANE_DIVISAS_UF, z_index=Z_INDEX_DIVISAS_UF, pointer_events=False
    ).add_to(mapa)

    raiz = mapa.get_root()
    # O título da aba e o ícone: sem eles o navegador rotula o arquivo pelo
    # caminho ("mapa_if_sul.html") e desenha a folha em branco padrão, o que
    # entrega mal um material que circula com várias abas abertas.
    raiz.title = TITULO_MAPA
    raiz.header.add_child(
        Element(
            '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,'
            + _SVG_FAVICON.format(cor=COR_TURQUESA.lstrip("#"))
            + '">'
        )
    )
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
    var divisas = __DIVISAS__;
    var controle = __CONTROLE__;
    if (!mapa || !geo || !controle) {
        console.error("controlador: mapa, camada de municípios ou painel não encontrados");
        return;
    }

    /* --------------------------------------------------------------------
       Encaixe na moldura da página
       --------------------------------------------------------------------

       O mapa e o painel de camadas nascem soltos — o mapa como <div> no corpo
       do documento, o painel como controle flutuante no canto do mapa — e são
       movidos daqui para dentro dos cartões que `adicionar_moldura` desenhou.
       Ver o docstring daquela função para por que o HTML não pode já nascer
       assim. Este bloco roda durante a análise do documento, antes da primeira
       pintura, então não há salto na tela.

       Aqui só se MOVE. A remedição do tamanho fica para o fim do arquivo, em
       `remedirEEnquadrar`, por um motivo medido: chamada aqui, ela lia
       `clientWidth` zero e o mapa abria em zoom 20 sobre um ponto. */
    var slotMapa = document.getElementById("slot-mapa");
    if (slotMapa) {
        slotMapa.appendChild(mapa.getContainer());
    }
    var caixaBandeiras = document.getElementById("painel-bandeiras");
    var painelCamadas = controle.getContainer && controle.getContainer();
    if (caixaBandeiras && painelCamadas) {
        caixaBandeiras.appendChild(painelCamadas);
    }

    /* --- Estado da seleção, espelhando os dois níveis do painel --------- */
    var meta = new Map();
    var grupoAtivo = {};
    var subAtivo = {};
    cfg.grupos.forEach(function (g) {
        g.obj = window[g.camada];
        if (g.obj) {
            meta.set(g.obj, {tipo: "grupo", id: g.id});
            grupoAtivo[g.id] = mapa.hasLayer(g.obj);
        }
        g.subs.forEach(function (s) {
            s.obj = window[s.camada];
            if (!s.obj) { return; }
            meta.set(s.obj, {tipo: "sub", id: s.rotulo});
            subAtivo[s.rotulo] = mapa.hasLayer(s.obj);

            /* Índice dos marcadores da bandeira por UF, montado uma vez na
               carga: é ele que deixa o filtro de estado trocar o conteúdo do
               subgrupo por um lote pronto, em vez de varrer os 7.600 pontos a
               cada clique. A UF de cada marcador chega em `options.tags` — ver
               `adicionar_camadas_de_pontos`. */
            s.todos = s.obj.getLayers();
            s.porUf = {};
            s.todos.forEach(function (m) {
                var uf = (m.options.tags || [])[0] || "";
                (s.porUf[uf] = s.porUf[uf] || []).push(m);
            });
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
       desabilitada em nenhum dos três. */
    var modo = cfg.modoInicial;

    /* UF em foco no filtro de estado; `null` significa as três. */
    var ufSelecionada = null;

    function mostraCidade() { return modo !== cfg.modoPontos; }
    function mostraPontos() { return modo !== cfg.modoCidade; }

    /* Serve tanto às propriedades de um município quanto a um item do índice
       da busca: os dois carregam a sigla em `uf`. */
    function dentroDoRecorte(comUf) {
        return !ufSelecionada || comUf.uf === ufSelecionada;
    }

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
        var cidade = mostraCidade();
        var pontos = mostraPontos();

        /* `visibility:hidden`, e não `display:none`, porque ele some com o
           conteúdo SEM tirar o elemento do fluxo: o <canvas> em que os
           marcadores são desenhados mantém posição e dimensão, e o Leaflet
           continua redesenhando nele durante os zooms feitos no outro modo —
           voltar ao modo de pontos mostra o enquadramento atual, nunca uma
           tela em branco esperando o próximo redesenho. (Conferido no
           navegador: com o painel escondido, o canvas seguiu sendo repintado a
           cada mudança de enquadramento.) */
        var esconder = function (painel, oculto) {
            if (painel) { painel.style.visibility = oculto ? "hidden" : ""; }
        };
        esconder(mapa.getPane("overlayPane"), !pontos);
        esconder(mapa.getPane("markerPane"), !pontos);

        /* O pane do coroplético NUNCA é escondido: no modo de pontos ele para
           de pintar o preenchimento, mas continua desenhando a divisa de
           município (ver `estilo`) — sem ela, um marcador no interior não diz
           a que cidade pertence. O que sai junto com o preenchimento é a
           interação: sem mancha de cor não há o que o clique explique, e um
           polígono do tamanho de um município roubaria o clique dos marcadores
           em cima dele. Duas travas para o mesmo — o pane deixa de receber
           eventos de ponteiro, e cada feição fica não-interativa (`repintar`),
           que é o que vale no renderizador de canvas. */
        var painelCoro = mapa.getPane(cfg.paneCoropletico);
        if (painelCoro) { painelCoro.style.pointerEvents = cidade ? "" : "none"; }
        if (!cidade && geo.getPopup()) { mapa.closePopup(geo.getPopup()); }

        /* A legenda NÃO some no modo de pontos: ela troca de assunto. A faixa
           é o rodapé fixo do cartão do mapa, e escondê-la abriria um vão branco
           embaixo dele; além disso continua havendo o que explicar naquele modo
           — que ali cada disco é um ponto e a cor dele é a bandeira. */
        desenharLegenda();
        escreverDica();

        repintar();
    }

    /* Os dois seletores de escopo — o modo e o estado — já vêm no HTML,
       montados por `_segmentos` na geração. O controlador não desenha mais
       nenhum dos dois: ele só liga os ouvintes.

       A troca não é de estilo. Enquanto as caixas eram INSERIDAS na lista do
       `L.Control.Layers`, elas viviam dentro de um elemento que o Leaflet
       reconstrói inteiro sempre que uma camada entra ou sai do mapa por fora
       do painel — qualquer reconstrução dessas as apagaria, junto com os
       ouvintes. Fora do painel, o problema deixa de existir. */
    function escreverDica() {
        var caixa = document.getElementById("dica-modo");
        if (!caixa) { return; }
        var escolhido = null;
        cfg.modos.forEach(function (m) { if (m.id === modo) { escolhido = m; } });
        caixa.textContent = escolhido ? escolhido.dica : "";
    }

    function ligarSeletorDeModo() {
        var opcoes = document.querySelectorAll('input[name="modo-visao"]');
        for (var i = 0; i < opcoes.length; i++) {
            opcoes[i].addEventListener("change", function () {
                modo = this.value;
                aplicarModo();
            });
        }
    }

    /* --------------------------------------------------------------------
       Filtro por estado
       --------------------------------------------------------------------

       Marcar uma UF enquadra o mapa nela e APAGA as outras duas: polígono,
       divisa e marcadores. Ver "Recorte por estado" no cabeçalho do módulo
       para por que apagar, e não esmaecer. */

    /* Troca o conteúdo de um subgrupo de bandeira EM LOTE.

       O caminho natural — `subgrupo.removeLayer(m)` ponto a ponto — repassa
       cada marcador ao MarkerCluster individualmente, e são até 5 mil por
       troca: o agrupamento se reorganiza a cada um deles. Os métodos de lote
       do cluster (`addLayers`/`removeLayers`) fazem a mesma coisa numa
       passada, e é justamente o que o próprio Leaflet.FeatureGroup.SubGroup
       usa quando o pai os oferece.

       O preço é escrever direto em `_layers`, que é interno ao subgrupo. É
       deliberado e necessário: o subgrupo precisa continuar sabendo quais
       marcadores são dele para reinjetá-los no cluster quando a bandeira for
       remarcada no painel. Escrever só no cluster deixaria os dois em
       desacordo no primeiro clique seguinte.

       A camada do subgrupo NÃO é adicionada nem removida do mapa aqui: fosse
       assim, o `L.Control.Layers` se reconstruiria e as caixas de seleção do
       painel voltariam ao estado que o mapa tem, desmarcando bandeiras. */
    function definirConteudo(sub, marcadores) {
        var pai = sub.getParentGroup && sub.getParentGroup();
        var emLote = pai && pai.addLayers && pai.removeLayers;
        var noMapa = !!sub._map;

        if (noMapa && emLote) { pai.removeLayers(sub.getLayers()); }
        var novos = {};
        marcadores.forEach(function (m) { novos[sub.getLayerId(m)] = m; });
        sub._layers = novos;
        if (noMapa && emLote) { pai.addLayers(marcadores); }
    }

    function marcadoresDe(s) {
        return ufSelecionada ? (s.porUf[ufSelecionada] || []) : s.todos;
    }

    function aplicarRecorteNosPontos() {
        cfg.grupos.forEach(function (g) {
            g.subs.forEach(function (s) {
                if (s.obj) { definirConteudo(s.obj, marcadoresDe(s)); }
            });
        });
    }

    /* A contagem ao lado de cada bandeira passa a ser a do recorte: deixá-la
       no total dos três estados faria o painel contradizer o mapa. */
    function escreverContagem(camada, quantos) {
        var input = inputDe(camada);
        var rotulo = input && input.closest("label");
        var alvo = rotulo && rotulo.querySelector(".camada-contagem");
        if (alvo) { alvo.textContent = " (" + quantos.toLocaleString("pt-BR") + ")"; }
    }

    function atualizarContagens() {
        cfg.grupos.forEach(function (g) {
            var total = 0;
            g.subs.forEach(function (s) {
                var quantos = marcadoresDe(s).length;
                total += quantos;
                if (s.obj) { escreverContagem(s.obj, quantos); }
            });
            if (g.obj) { escreverContagem(g.obj, total); }
        });
    }

    /* --------------------------------------------------------------------
       Todo enquadramento deste mapa é SEM ANIMAÇÃO
       --------------------------------------------------------------------

       Não é preferência de estilo: com o contêiner do mapa movido para dentro
       do cartão (ver "Encaixe na moldura da página"), o voo animado do Leaflet
       não CHEGA ao destino. A animação de zoom depende de um `transitionend`
       no elemento-proxy que o Leaflet cria na inicialização, e reparentar o
       contêiner deixa esse evento de chegar: o `fitBounds` animado sai do
       lugar mas para no meio, num zoom que não é nem o de origem nem o de
       destino.

       Medido neste arquivo: abrindo, o mapa parava em zoom 6 sobre o centro do
       construtor, com o RS e o PR cortados; clicando "SC", o enquadramento não
       saía do lugar. Com `animate: false` os dois acertam o destino.

       O salto seco também não é perda: as duas chamadas que enquadram trocam o
       CONTEÚDO junto com o recorte — o filtro de estado apaga dois estados
       inteiros, e a busca abre o balão do município. Voar sobre um mapa cujo
       conteúdo mudou no primeiro quadro não informa nada. */
    var ANIMAR_ENQUADRAMENTO = false;

    function enquadrar() {
        var limites = ufSelecionada
            ? cfg.limites[ufSelecionada]
            : cfg.limites.todos;
        if (limites) {
            mapa.fitBounds(limites, {
                padding: [14, 14],
                animate: ANIMAR_ENQUADRAMENTO
            });
        }
    }

    function selecionarUf(uf) {
        ufSelecionada = uf || null;
        aplicarRecorteNosPontos();
        atualizarContagens();
        recalcular();
        atualizarBusca();
        enquadrar();
    }

    function ligarFiltroDeUf() {
        var opcoes = document.querySelectorAll('input[name="filtro-uf"]');
        for (var i = 0; i < opcoes.length; i++) {
            opcoes[i].addEventListener("change", function () {
                selecionarUf(this.value);
            });
        }
    }

    /* --------------------------------------------------------------------
       Busca de município
       --------------------------------------------------------------------

       O índice sai da própria camada de municípios já carregada: nome, UF e a
       referência à feição, que é quem sabe os próprios limites. Nada de novo
       é embarcado no HTML por causa da busca. */
    var indice = [];
    var sugestoes = [];
    var campoBusca = null;
    var listaBusca = null;
    var destacada = -1;

    /* Os municípios atualmente listados no ranking, na ordem em que aparecem:
       é por esta lista que o clique numa linha chega à camada do município. */
    var ranking = [];

    /* Sem acento e sem caixa dos dois lados: é o que faz "sao lourenco" achar
       "São Lourenço do Sul" — ninguém digita o acento numa caixa de busca. */
    function normalizar(valor) {
        return String(valor)
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim();
    }

    function montarIndice() {
        geo.eachLayer(function (camada) {
            var props = camada.feature.properties;
            indice.push({
                nome: String(props.municipio_nome),
                uf: props.uf,
                chave: normalizar(props.municipio_nome),
                camada: camada
            });
        });
        indice.sort(function (a, b) {
            return a.chave < b.chave ? -1 : (a.chave > b.chave ? 1 : 0);
        });
    }

    /* Prefixo antes de trecho no meio: quem digita "santa" quer "Santa Rosa"
       na frente de "Bom Jesus de Santa..." . */
    function candidatos(termo) {
        var alvo = normalizar(termo);
        if (alvo.length < cfg.minBusca) { return []; }

        var comeca = [];
        var contem = [];
        for (var i = 0; i < indice.length; i++) {
            var item = indice[i];
            if (!dentroDoRecorte(item)) { continue; }
            var posicao = item.chave.indexOf(alvo);
            if (posicao === 0) { comeca.push(item); }
            else if (posicao > 0) { contem.push(item); }
            if (comeca.length >= cfg.maxSugestoes) { break; }
        }
        return comeca.concat(contem).slice(0, cfg.maxSugestoes);
    }

    function desenharSugestoes() {
        if (!listaBusca) { return; }
        destacada = -1;
        listaBusca.innerHTML = "";

        if (!sugestoes.length) {
            /* Campo curto demais não é "não achei", é "ainda não procurei". */
            if (normalizar(campoBusca.value).length >= cfg.minBusca) {
                var vazio = L.DomUtil.create("li", "busca-vazio", listaBusca);
                vazio.textContent = "nenhum município";
                listaBusca.hidden = false;
            } else {
                listaBusca.hidden = true;
            }
            return;
        }

        sugestoes.forEach(function (item, i) {
            var linha = L.DomUtil.create("li", "", listaBusca);
            linha.setAttribute("data-i", String(i));
            /* `textContent`, e não `innerHTML`: o nome vem do dado. */
            linha.textContent = item.nome + " ";
            var uf = L.DomUtil.create("span", "busca-uf", linha);
            uf.textContent = item.uf;
        });
        listaBusca.hidden = false;
    }

    function atualizarBusca() {
        if (!campoBusca) { return; }
        sugestoes = candidatos(campoBusca.value);
        desenharSugestoes();
    }

    function destacar(indiceAlvo) {
        var linhas = listaBusca.querySelectorAll("li[data-i]");
        if (!linhas.length) { return; }
        destacada = (indiceAlvo + linhas.length) % linhas.length;
        for (var i = 0; i < linhas.length; i++) {
            linhas[i].classList.toggle("ativa", i === destacada);
        }
        linhas[destacada].scrollIntoView({block: "nearest"});
    }

    function fecharSugestoes() {
        if (listaBusca) { listaBusca.hidden = true; }
        destacada = -1;
    }

    /* O popup do município é do GRUPO — o folium o vincula ao GeoJson inteiro
       e monta o conteúdo a partir de `_source`, a feição que o abriu, que
       normalmente é definida pelo clique. Aqui não houve clique, então a
       origem é dita à mão antes de abrir. */
    function abrirPopupMunicipio(camada, centro) {
        var popup = geo.getPopup();
        if (!popup) { return; }
        popup._source = camada;
        geo.openPopup(centro);
    }

    /* Serve à busca e ao ranking, que pedem a mesma coisa: enquadrar um
       município e explicá-lo. O que muda é `vindoDaBusca` — escrever o nome no
       campo confirma o que o usuário acabou de escolher ali, mas depois de um
       clique no ranking a mesma escrita pareceria uma busca que ele não fez. */
    function irPara(item, vindoDaBusca) {
        if (!item) { return; }
        var limites = item.camada.getBounds();
        mapa.fitBounds(limites, {
            maxZoom: cfg.zoomBusca,
            padding: [24, 24],
            animate: ANIMAR_ENQUADRAMENTO
        });
        /* O popup só faz sentido onde o polígono está pintado; no nível de
           pontos ele abriria sobre um mapa sem coroplético nenhum. */
        if (mostraCidade()) { abrirPopupMunicipio(item.camada, limites.getCenter()); }
        if (vindoDaBusca && campoBusca) { campoBusca.value = item.nome; }
        fecharSugestoes();
    }

    /* O campo vive na barra de controles, fora do mapa — e não mais como
       `L.Control` flutuante sobre ele. Além de tirar do mapa uma caixa que
       tapava municípios, isso dispensa os três `L.DomEvent` que existiam só
       para impedir que o clique, a rolagem e cada tecla digitada chegassem ao
       Leaflet embaixo: fora do contêiner do mapa, não há o que interceptar. */
    function ligarBusca() {
        campoBusca = document.getElementById("busca-campo");
        listaBusca = document.getElementById("busca-lista");
        if (!campoBusca || !listaBusca) { return; }

        campoBusca.addEventListener("input", atualizarBusca);
        campoBusca.addEventListener("focus", atualizarBusca);
        campoBusca.addEventListener("keydown", function (e) {
            if (e.key === "ArrowDown") {
                destacar(destacada + 1);
                e.preventDefault();
            } else if (e.key === "ArrowUp") {
                destacar(destacada - 1);
                e.preventDefault();
            } else if (e.key === "Enter") {
                /* Sem nenhuma destacada, Enter leva à primeira: é o resultado
                   que o usuário está olhando. */
                irPara(sugestoes[destacada < 0 ? 0 : destacada], true);
                e.preventDefault();
            } else if (e.key === "Escape") {
                fecharSugestoes();
            }
        });

        listaBusca.addEventListener("click", function (e) {
            var linha = e.target.closest("li[data-i]");
            if (linha) {
                irPara(sugestoes[Number(linha.getAttribute("data-i"))], true);
            }
        });
        listaBusca.addEventListener("mousemove", function (e) {
            var linha = e.target.closest("li[data-i]");
            if (linha) { destacar(Number(linha.getAttribute("data-i"))); }
        });

        /* Clique fora fecha a lista. O teste é pela caixa que embrulha campo e
           sugestões, e não pelo campo: clicar numa sugestão é clicar fora do
           <input>, e fechar a lista ali cancelaria a própria escolha. */
        document.addEventListener("click", function (e) {
            if (campoBusca && !campoBusca.parentNode.contains(e.target)) {
                fecharSugestoes();
            }
        });
    }

    /* Uma linha do ranking leva ao mesmo lugar que uma sugestão da busca. */
    function ligarRanking() {
        var el = document.getElementById("ranking-lista");
        if (!el) { return; }
        el.addEventListener("click", function (e) {
            var linha = e.target.closest("li[data-i]");
            if (linha) {
                irPara(ranking[Number(linha.getAttribute("data-i"))], false);
            }
        });
    }

    var atual = {sel: [], cortes: [], cores: [], max: 0, valores: []};

    function formatarNumero(n) {
        return Number(n).toLocaleString("pt-BR");
    }

    /* Números grandes abreviados nos indicadores: "1,4 mi" cabe no cartão e é
       lido de relance; "1.412.883" ocupa a largura toda e não é lido — ninguém
       decide nada com o dígito da unidade de uma população. A contagem exata
       continua disponível no balão de cada município. */
    function formatarCompacto(n) {
        if (n >= 1000000) {
            return (n / 1000000).toFixed(1).replace(".", ",") + " mi";
        }
        if (n >= 10000) { return formatarNumero(Math.round(n / 1000)) + " mil"; }
        return formatarNumero(n);
    }

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

    /* Município fora do recorte não é pintado de cinza: não é desenhado. Ver
       "Recorte por estado" no cabeçalho do módulo. */
    var ESTILO_OCULTO = {stroke: false, fill: false};

    function estilo(feature) {
        if (!dentroDoRecorte(feature.properties)) { return ESTILO_OCULTO; }
        var cidade = mostraCidade();
        /* Todas as chaves em TODOS os caminhos: `setStyle` funde o objeto nas
           opções da feição, então chave omitida aqui preserva o valor do
           estilo anterior — sem o `stroke: true`, o município que voltasse ao
           recorte continuaria com o traço desligado. */
        return {
            stroke: true,
            color: cfg.contorno.cor,
            weight: cidade ? cfg.contorno.peso : cfg.contorno.pesoSemFundo,
            fill: cidade,
            fillColor: corDe(feature.__total || 0),
            fillOpacity: cfg.contorno.opacidadeFundo
        };
    }

    /* Repinta os polígonos e acerta quem responde ao mouse. */
    function repintar() {
        var cidade = mostraCidade();

        /* Trocar `options.style` também, e não só repintar: o handler de
           mouseout chama resetStyle, que relê options.style. Sem isto, tirar o
           mouse de um município o devolveria à cor da seleção anterior. */
        geo.options.style = estilo;
        geo.setStyle(estilo);
        geo.eachLayer(function (camada) {
            camada.options.interactive =
                cidade && dentroDoRecorte(camada.feature.properties);
        });

        if (divisas) {
            divisas.setStyle(function (feature) {
                return dentroDoRecorte(feature.properties)
                    ? cfg.estiloDivisaUf
                    : ESTILO_OCULTO;
            });
        }
    }

    function rotuloSelecao() {
        if (!atual.sel.length) { return "nenhuma bandeira"; }
        if (atual.sel.length === 1) { return atual.sel[0].rotulo; }
        if (atual.sel.length === cfg.totalBandeiras) { return "todas as bandeiras"; }
        return atual.sel.length + " bandeiras";
    }

    /* A legenda é uma FAIXA HORIZONTAL no rodapé do cartão do mapa, e não uma
       caixa flutuante sobre ele. Flutuando, ela tapava município — e num mapa
       cujas classes são recalculadas a cada clique a legenda faz parte da
       leitura, não pode estar por cima do que descreve.

       Ela também não fica vazia em nenhum estado: sem bandeira marcada diz o
       que fazer, e no modo de pontos explica a codificação dos discos, que é o
       que está na tela ali. */
    function desenharLegenda() {
        var el = document.getElementById("legenda-coropletico");
        if (!el) { return; }

        var fonte = '<span class="legenda-fonte">' + cfg.creditoLegenda + "</span>";
        var escopo = ufSelecionada ? (" &middot; " + ufSelecionada) : "";

        if (!mostraCidade()) {
            el.innerHTML = '<span class="legenda-titulo">Pontos de atendimento' +
                "<span>" + escopo + "</span></span>" +
                '<span class="legenda-recado">Um disco por ponto; a cor é a ' +
                "bandeira, na mesma amostra da lista ao lado. Aproxime o zoom " +
                "para abrir os balões de contagem.</span>" + fonte;
            return;
        }

        if (!atual.sel.length) {
            el.innerHTML = '<span class="legenda-titulo">Nenhuma bandeira ' +
                "marcada</span>" +
                '<span class="legenda-recado">Marque uma bandeira na lista ao ' +
                "lado para colorir o mapa.</span>" + fonte;
            return;
        }

        var valores = atual.valores;
        var nZero = 0;
        for (var i = 0; i < valores.length; i++) {
            if (valores[i] === 0) { nZero++; }
        }

        var classes = '<span class="legenda-classe zero"><i style="background:' +
            cfg.corZero + '"></i><b>0</b><small>' + formatarNumero(nZero) +
            " mun.</small></span>";

        for (var c = 0; c < atual.cortes.length; c++) {
            var lo = atual.cortes[c];
            var ultimo = (c + 1 === atual.cortes.length);
            var hi = ultimo ? null : atual.cortes[c + 1] - 1;
            var rotulo;
            if (ultimo) {
                rotulo = (lo >= atual.max) ? String(lo) : (lo + "+");
            } else {
                rotulo = (hi > lo) ? (lo + "\u2013" + hi) : String(lo);
            }
            var n = 0;
            for (var j = 0; j < valores.length; j++) {
                if (valores[j] >= lo && (ultimo || valores[j] <= hi)) { n++; }
            }
            classes += '<span class="legenda-classe"><i style="background:' +
                atual.cores[c] + '"></i><b>' + rotulo + "</b><small>" +
                formatarNumero(n) + " mun.</small></span>";
        }

        el.innerHTML = '<span class="legenda-titulo">Pontos por município' +
            "<span> &middot; " + rotuloSelecao() + escopo + "</span></span>" +
            '<span class="legenda-escala">' + classes + "</span>" + fonte;
    }

    /* --------------------------------------------------------------------
       Indicadores e ranking
       --------------------------------------------------------------------

       Os dois respondem à MESMA seleção que colore o mapa, e é isso que os
       torna úteis a quem decide: o coroplético mostra o desenho da rede, os
       quatro números dizem o tamanho dela, e a lista diz onde ela se
       concentra. Nenhum dos três é lido sozinho.

       Os dois indicadores de lacuna — municípios sem nenhum ponto da seleção e
       a população que mora neles — são o motivo de a faixa existir. "347
       municípios descobertos" só vira pauta quando vem acompanhado de quanta
       gente isso é. */
    function atualizarIndicadores(resumo) {
        var escrever = function (id, valor, nota) {
            var alvo = document.getElementById(id);
            if (alvo) { alvo.textContent = valor; }
            var rodape = document.getElementById(id + "-nota");
            if (rodape) {
                rodape.textContent = nota;
                /* A nota é cortada com reticências quando o cartão aperta; o
                   `title` é o que a devolve inteira ao passar o mouse. */
                rodape.title = nota;
            }
        };
        var escopo = ufSelecionada ? (" \u00b7 " + ufSelecionada) : "";
        var total = resumo.municipios || 1;
        var pctAtendidos = Math.round(resumo.atendidos * 100 / total);
        var pctVazios = Math.round(resumo.semPonto * 100 / total);

        escrever("kpi-pontos", formatarNumero(resumo.pontos),
                 rotuloSelecao() + escopo);
        escrever("kpi-municipios", formatarNumero(resumo.atendidos),
                 pctAtendidos + "% de " + formatarNumero(resumo.municipios));
        escrever("kpi-vazios", formatarNumero(resumo.semPonto),
                 pctVazios + "% de " + formatarNumero(resumo.municipios));
        /* A população sem dado é declarada, e não somada como zero: o IBGE não
           devolve estimativa para alguns municípios, e engolir isso faria o
           indicador subestimar a lacuna sem avisar. */
        escrever("kpi-populacao", formatarCompacto(resumo.popSemPonto),
                 resumo.popSemDado
                     ? "sem estimativa em " + resumo.popSemDado
                     : "nesses " + formatarNumero(resumo.semPonto) +
                       " municípios");
    }

    function desenharRanking(lista) {
        var el = document.getElementById("ranking-lista");
        var nota = document.getElementById("ranking-nota");
        if (!el) { return; }

        ranking = lista.sort(function (a, b) { return b.total - a.total; })
                       .slice(0, cfg.maxRanking);
        el.innerHTML = "";
        if (nota) {
            nota.textContent = ranking.length
                ? ("top " + ranking.length + (ufSelecionada ? " \u00b7 " + ufSelecionada : ""))
                : "";
        }
        if (!ranking.length) {
            var vazio = L.DomUtil.create("li", "vazio", el);
            vazio.textContent = "Nenhum município com ponto nesta seleção.";
            return;
        }

        var teto = ranking[0].total;
        ranking.forEach(function (item, i) {
            var linha = L.DomUtil.create("li", "", el);
            linha.setAttribute("data-i", String(i));
            linha.title = "Enquadrar " + item.nome + " no mapa";

            var posicao = L.DomUtil.create("span", "posicao", linha);
            posicao.textContent = String(i + 1);

            /* `textContent`, e não `innerHTML`: o nome vem do dado. */
            var nome = L.DomUtil.create("span", "nome", linha);
            nome.textContent = item.nome + " ";
            var uf = L.DomUtil.create("em", "", nome);
            uf.textContent = item.uf;

            var valor = L.DomUtil.create("span", "valor", linha);
            valor.textContent = formatarNumero(item.total);

            /* A barra é proporcional ao PRIMEIRO colocado, não ao total: o que
               a lista responde é "quão longe do maior", e nenhuma capital passa
               de uns poucos por cento do total do recorte — barras medidas
               contra ele seriam todas invisíveis. */
            var trilho = L.DomUtil.create("span", "trilho", linha);
            var barra = L.DomUtil.create("i", "", trilho);
            barra.style.width =
                Math.max(2, Math.round(item.total * 100 / teto)) + "%";
        });
    }

    /* Uma única varredura dos 1.191 municípios alimenta as quatro leituras —
       a escala de cores, a legenda, os indicadores e o ranking. Elas descrevem
       exatamente o mesmo recorte, então varrer quatro vezes só abriria espaço
       para as quatro discordarem entre si. */
    function recalcular() {
        atual.sel = selecao();

        var valores = [];
        var comPontos = [];
        var resumo = {
            municipios: 0,
            pontos: 0,
            atendidos: 0,
            semPonto: 0,
            popSemPonto: 0,
            popSemDado: 0
        };
        atual.max = 0;
        geo.eachLayer(function (camada) {
            var props = camada.feature.properties;
            var t = totalDe(props);
            camada.feature.__total = t;
            /* As classes, a legenda e os indicadores descrevem o que está NA
               TELA: município fora do recorte não entra em nenhum dos três. */
            if (!dentroDoRecorte(props)) { return; }
            if (t > atual.max) { atual.max = t; }
            valores.push(t);

            resumo.municipios++;
            resumo.pontos += t;
            if (t > 0) {
                resumo.atendidos++;
                comPontos.push({
                    nome: String(props.municipio_nome),
                    uf: props.uf,
                    total: t,
                    camada: camada
                });
            } else {
                resumo.semPonto++;
                if (props.populacao_valor == null) {
                    resumo.popSemDado++;
                } else {
                    resumo.popSemPonto += props.populacao_valor;
                }
            }
        });

        atual.valores = valores;
        atual.cortes = calcularCortes(valores);
        var rampa = (atual.sel.length === 1 && cfg.rampas[atual.sel[0].rotulo])
            ? cfg.rampas[atual.sel[0].rotulo]
            : cfg.rampaPadrao;
        atual.cores = amostrar(rampa, atual.cortes.length);

        repintar();
        desenharLegenda();
        atualizarIndicadores(resumo);
        desenharRanking(comPontos);
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

    /* Com 14 bandeiras, isolar uma custava 13 cliques para desmarcar as
       outras, e voltar ao total custava os mesmos 13 de volta. Os dois botões
       fazem as duas coisas numa passada.

       Eles escrevem nas caixas e chamam `_onInputClick` — o mesmo caminho de um
       clique de verdade no painel —, e não `addLayer`/`removeLayer`: mexer nas
       camadas por fora faria o `L.Control.Layers` se reconstruir. */
    function ligarAcoesDeSelecao() {
        var aplicar = function (ligar) {
            caixas.forEach(function (c) {
                c.grupo.checked = ligar;
                c.filhas.forEach(function (filha) { filha.checked = ligar; });
            });
            if (controle && controle._onInputClick) { controle._onInputClick(); }
            atualizarParciais();
        };
        var todas = document.getElementById("acao-todas");
        var nenhuma = document.getElementById("acao-nenhuma");
        if (todas) {
            todas.addEventListener("click", function () { aplicar(true); });
        }
        if (nenhuma) {
            nenhuma.addEventListener("click", function () { aplicar(false); });
        }
    }

    atualizarParciais();
    atualizarContagens();

    ligarSeletorDeModo();
    ligarFiltroDeUf();
    ligarAcoesDeSelecao();

    montarIndice();
    ligarBusca();
    ligarRanking();
    recalcular();
    aplicarModo();

    /* --------------------------------------------------------------------
       Remedir e enquadrar, depois de a moldura estar pronta
       --------------------------------------------------------------------

       O `invalidateSize` é obrigatório porque o Leaflet mede o contêiner uma
       única vez, no `L.map(...)`, e ali ele ainda ocupava a janela inteira —
       sem remedir, o mapa seguiria calculando ladrilhos, enquadramento e
       cliques para um retângulo do tamanho da tela dentro de um cartão bem
       menor.

       Ele vem AQUI, e não junto do encaixe lá em cima, porque a essa altura o
       cartão já tem a altura definitiva: a legenda do rodapé, que divide o
       cartão com o mapa, acabou de ser escrita. Medido antes, o Leaflet lia
       largura zero e o mapa abria em zoom 20 sobre um ponto.

       E o enquadramento de abertura é CALCULADO, não o par centro/zoom do
       construtor: aquele foi medido com o mapa ocupando a janela inteira, e
       dentro do cartão o mesmo zoom cortaria o RS e o PR. `fitBounds` sobre o
       recorte inteiro acerta em qualquer proporção de tela — que é o que um
       arquivo aberto ora no notebook, ora no projetor, precisa.

       A repetição no `load` é a garantia de que a medida final vale: este
       bloco roda com o documento ainda em análise, e qualquer coisa que mude a
       caixa depois (a barra de rolagem aparecendo, uma fonte trocando de
       métrica) deixaria o mapa desalinhado até o primeiro zoom. */
    function remedirEEnquadrar() {
        mapa.invalidateSize();
        enquadrar();
    }

    remedirEEnquadrar();
    window.addEventListener("load", remedirEEnquadrar);
})();
"""


class _FolhaDeEstilo(MacroElement):
    """Envelope que emite a folha de estilo no FIM do ``<head>``.

    Existe pelo mesmo motivo que `_ScriptDoMapa`, um andar acima: por
    causa da ORDEM. O folium carrega, sem ser perguntado, o Bootstrap, o
    FontAwesome, o leaflet.css e o MarkerCluster.Default.css — e várias regras
    deles colidem com as daqui: o Bootstrap redefine a fonte do ``<body>``, o
    MarkerCluster pinta o balão de contagem de verde-amarelo-laranja. Em
    empate de especificidade, quem vem depois vence.

    Adicionada a ``get_root().header`` na construção, a folha sairia ANTES de
    todas essas — os elementos criados durante a renderização são anexados ao
    cabeçalho depois dos que já estavam lá — e perderia todos os empates. Como
    `MacroElement` filho do mapa, adicionado por último, ela sai por último e
    ganha todos.
    """

    _template = Template(
        "{% macro header(this, kwargs) %}{{ this.css | safe }}{% endmacro %}"
    )

    def __init__(self, css: str):
        super().__init__()
        self._name = "FolhaDeEstilo"
        self.css = css


def aplicar_folha_de_estilo(mapa: folium.Map) -> None:
    """Acrescenta a folha de estilo da página, para sair por último no ``<head>``.

    Tem de ser a ÚLTIMA coisa adicionada ao mapa — ver `_FolhaDeEstilo` para o
    porquê.

    Args:
        mapa: mapa com todas as camadas, o painel e o controlador já
            adicionados.
    """
    mapa.add_child(_FolhaDeEstilo(_CSS_PAGINA))


def adicionar_controle_reativo(
    mapa: folium.Map,
    coropletico: folium.GeoJson,
    divisas: folium.GeoJson,
    estrutura: list[dict],
    controle: folium.LayerControl,
    agregado: gpd.GeoDataFrame,
) -> None:
    """Injeta o controlador do painel: cascata dos toggles e coroplético reativo.

    Ver "Coroplético reativo" no cabeçalho do módulo para o porquê de a cor ser
    decidida no cliente e não em Python, e `_ScriptDoMapa` para o porquê
    de o script precisar ser o último elemento adicionado ao mapa.

    Args:
        mapa: mapa com todas as camadas já adicionadas.
        coropletico: camada devolvida por `adicionar_coropletico`.
        divisas: camada devolvida por `adicionar_divisas_uf`, que o filtro de
            estado apaga fora do recorte.
        estrutura: saída de `adicionar_camadas_de_pontos`.
        controle: `LayerControl` já adicionado — o controlador precisa dele
            para achar a caixa de seleção de cada camada e fazer a cascata.
        agregado: saída de `carregar_agregado`, de onde saem as UFs do filtro e
            os limites de enquadramento de cada uma.
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
        "modoCidade": MODO_CIDADE,
        "modoPontos": MODO_PONTOS,
        "paneCoropletico": PANE_COROPLETICO,
        # O estilo do município é decidido no cliente (ele muda com o modo e
        # com o recorte), então as medidas vão junto em vez de ficarem
        # duplicadas em JavaScript.
        "contorno": {
            "cor": COR_CONTORNO_MUNICIPIO,
            "peso": LARGURA_CONTORNO_MUNICIPIO,
            "pesoSemFundo": LARGURA_CONTORNO_MUNICIPIO_SEM_FUNDO,
            "opacidadeFundo": OPACIDADE_COROPLETICO,
        },
        "estiloDivisaUf": {
            "stroke": True,
            "color": COR_DIVISA_UF,
            "weight": LARGURA_DIVISA_UF,
            "fill": False,
        },
        "ufs": ufs_do_recorte(agregado),
        "limites": limites_por_uf(agregado),
        "textoBusca": TEXTO_BUSCA,
        "minBusca": MIN_CARACTERES_BUSCA,
        "maxSugestoes": MAX_SUGESTOES_BUSCA,
        "zoomBusca": ZOOM_BUSCA,
        "maxRanking": MAX_RANKING,
        # O crédito repetido na faixa da legenda: quem recorta a imagem do mapa
        # para um slide leva a fonte e a safra junto, sem precisar do rodapé da
        # página.
        "creditoLegenda": f"BACEN &middot; {config.DATA_DADOS}",
    }

    script = (
        _JS_CONTROLADOR.replace("__CONFIG__", json.dumps(configuracao, ensure_ascii=False))
        .replace("__MAPA__", mapa.get_name())
        .replace("__GEOJSON__", coropletico.get_name())
        .replace("__DIVISAS__", divisas.get_name())
        .replace("__CONTROLE__", controle.get_name())
    )
    mapa.add_child(_ScriptDoMapa(script, nome="ControladorReativo"))


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
    caminho_agregado: Path | None = None,
    caminho_pontos: Path | None = None,
    destino: Path | None = None,
) -> Path:
    """Gera o mapa interativo completo e grava o HTML.

    Etapas, na ordem:

    1. lê o agregado por município (com geometria) e o dataset de pontos;
    2. mede o enquadramento de abertura na geometria do recorte carregado
       (`enquadramento_inicial`) e monta o mapa base nele;
    3. adiciona o coroplético por `total_cooperativas`, com popup e tooltip por
       município (nome, população — ou "dado indisponível" —, total de bancos,
       total de pontos de cooperativas e o detalhamento por `sub_categoria`),
       e por cima dele a divisa entre estados, dissolvida da mesma malha;
    4. adiciona a moldura da página — marca, título, indicadores, barra de
       controles, cartões e rodapé de fontes;
    5. lê os pontos já geocodificados por `src.cnefe` e monta as camadas em
       dois níveis (grupo pai por `categoria_if`, subgrupo por
       `sub_categoria`);
    6. adiciona o `LayerControl` aberto, o controlador reativo e a folha de
       estilo (nesta ordem, que é obrigatória), e grava o HTML.

    Args:
        caminho_agregado: GeoParquet de `src.agregacao`; ``None`` deriva do
            recorte ativo.
        caminho_pontos: Parquet geocodificado de `src.cnefe`; ``None`` deriva
            do recorte ativo.
        destino: caminho do HTML de saída; ``None`` deriva do recorte ativo. O
            diretório é criado se faltar.

    Returns:
        O caminho do HTML gravado.

    Raises:
        FileNotFoundError: se algum dos dois Parquet de entrada não existir.
    """
    caminho_agregado = caminho_agregado or config.arquivo_agregado_municipio()
    caminho_pontos = caminho_pontos or config.arquivo_pontos_geocodificados()
    destino = destino or config.arquivo_mapa()

    agregado = carregar_agregado(caminho_agregado)
    localizados = carregar_pontos_geocodificados(caminho_pontos)

    centro, zoom = enquadramento_inicial(agregado)
    mapa = criar_mapa_base(centro, zoom)

    com_textos = preparar_propriedades_municipio(agregado)
    coropletico = adicionar_coropletico(mapa, com_textos)
    divisas = adicionar_divisas_uf(mapa, agregado)
    adicionar_moldura(mapa, agregado)

    estrutura = adicionar_camadas_de_pontos(mapa, localizados)

    # Depois de TODAS as camadas — ver `adicionar_controle_de_camadas`.
    controle = adicionar_controle_de_camadas(mapa)
    # E o controlador por último de todos: ele referencia as variáveis das
    # camadas e do próprio painel, que precisam já estar declaradas no script.
    adicionar_controle_reativo(
        mapa, coropletico, divisas, estrutura, controle, agregado
    )
    # E a folha de estilo depois de tudo, para vencer o Bootstrap e o
    # MarkerCluster que o folium carrega sozinho — ver `_FolhaDeEstilo`.
    aplicar_folha_de_estilo(mapa)

    destino.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(str(destino))

    # Depois de gravar, e não antes: o folium só escreve as tags de CDN na
    # renderização final, então não há o que substituir enquanto o mapa é um
    # objeto em memória. Ver `src.embutir` para o porquê de o HTML precisar
    # carregar as bibliotecas dentro de si.
    embutido = embutir.embutir_no_html(destino)
    embutir.declarar_idioma(destino)

    imprimir_resumo(
        agregado, localizados, estrutura, destino, embutido, (centro, zoom)
    )
    return destino


def imprimir_resumo(
    agregado: gpd.GeoDataFrame,
    localizados: pd.DataFrame,
    estrutura: list[dict],
    destino: Path,
    embutido: dict[str, int] | None = None,
    enquadramento: tuple[tuple[float, float], int] | None = None,
) -> None:
    """Imprime o que foi renderizado, para conferência manual.

    Args:
        agregado: saída de `carregar_agregado`.
        localizados: saída de `carregar_pontos_geocodificados`.
        estrutura: saída de `adicionar_camadas_de_pontos`.
        destino: caminho do HTML gravado.
        embutido: contagem devolvida por `embutir.embutir_no_html`.
        enquadramento: ``((lat, lon), zoom)`` de `enquadramento_inicial`;
            ``None`` remede sobre o agregado.
    """
    centro, zoom = enquadramento or enquadramento_inicial(agregado)

    print("=" * 78)
    print(f"MAPA — {destino.relative_to(config.BASE_DIR)}")
    print("=" * 78)
    print(f"UFs no agregado: {', '.join(ufs_do_recorte(agregado))}")
    print(f"Centro {centro}, zoom {zoom}, base {config.TILES_PADRAO!r}")
    # Sem chave a CARTO não devolve erro: devolve o ladrilho com a marca
    # d'água "API KEY REQUIRED" impressa por cima. Como o mapa sai "pronto" de
    # qualquer jeito, o aviso precisa estar aqui, ou a ausência da chave só
    # aparece depois de publicado.
    if config.CARTO_API_KEY:
        print(f"Chave CARTO: ...{config.CARTO_API_KEY[-6:]} (sem marca d'água)\n")
    else:
        print("ATENÇÃO: sem chave da CARTO — o basemap sairá com marca "
              "d'água. Ver config.CARTO_API_KEY.\n")

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

    print("-- posição dos marcadores (ver src/cnefe.py) --")
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

    if embutido is not None:
        restantes = embutir.restantes_externos(destino)
        print("-- autonomia do arquivo --")
        print(
            f"   {embutido['scripts']} script(s) e {embutido['estilos']} folha(s) "
            f"de estilo embutidos (+{embutido['bytes'] / 1024:.0f} KB)"
        )
        if restantes:
            print(f"   ATENÇÃO: {len(restantes)} biblioteca(s) ainda vêm de CDN:")
            for url in restantes:
                print(f"      - {url}")
        else:
            print("   nenhuma biblioteca externa restante — o mapa abre sem rede")
        print(
            "   (o basemap continua vindo da CARTO: sem rede, some o "
            "fundo de ruas)\n"
        )

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
