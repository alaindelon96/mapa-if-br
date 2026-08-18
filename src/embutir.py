"""Embute no HTML as bibliotecas que o folium referencia por CDN.

O folium escreve o mapa com ``<script src>`` e ``<link rel=stylesheet>``
apontando para cinco CDNs — jsdelivr, cdnjs, unpkg, code.jquery.com e
netdna.bootstrapcdn.com. São 14 arquivos, 703 KB (163 KB comprimidos), e sem
eles o Leaflet não existe: a página abre com a moldura montada, o mapa NÃO
renderiza, o painel de bandeiras não é criado e os indicadores ficam nos
travessões de espera. Não é degradação, é tela vazia.

Isso é problema em duas situações reais: rede corporativa que bloqueia CDN
(comum), e o arquivo aberto sem internet — por ``file://``, de pen drive ou
como anexo de e-mail, que é justamente como um HTML autocontido costuma
circular.

Depois de embutir, o mapa passa a funcionar nas duas. O que NÃO vem junto são
os ladrilhos do basemap (CARTO): eles são baixados sob demanda conforme o
enquadramento, são milhares, e não há como empacotá-los. Sem eles o mapa perde
o fundo de ruas e mantém todo o resto — coroplético, divisas, os 7.600
marcadores, popups, filtros, busca e ranking. Com rede, nada muda: os
ladrilhos carregam como sempre.

--------------------------------------------------------------------------
Por que as URLs relativas dentro do CSS viram absolutas
--------------------------------------------------------------------------

Quatro das folhas trazem ``url(...)`` relativo — ``images/layers.png`` no
leaflet.css, as fontes do FontAwesome e dos glyphicons, os PNG do
awesome-markers. Embutida no HTML, uma URL relativa passa a ser resolvida
contra o endereço do MAPA, e não contra o da CDN de onde a folha veio: todas
apontariam para um caminho inexistente ao lado do arquivo.

A saída é reescrevê-las para a URL absoluta da própria CDN. Assim, com rede, o
resultado é idêntico ao de hoje; sem rede, faltam só esses ativos — e nenhum
deles é usado por este mapa, que desenha com `CircleMarker` e traz o próprio
símbolo em SVG inline.

--------------------------------------------------------------------------
Cache
--------------------------------------------------------------------------

Os arquivos são baixados uma vez para ``data/raw/libs/`` e reaproveitados,
como já é feito com a malha e o CNEFE: são versões fixas, presas na URL
(``leaflet@1.9.3``), e não mudam entre execuções.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

from src import config, rede

_LOGGER = logging.getLogger(__name__)

#: Casa ``<script src="https://...">...</script>`` e captura a URL.
_PADRAO_SCRIPT = re.compile(
    r'<script\b[^>]*\bsrc="(https?://[^"]+)"[^>]*>\s*</script>', re.IGNORECASE
)

#: Casa ``<link rel="stylesheet" href="https://...">``.
#:
#: O ``rel="stylesheet"`` é exigido no padrão para que o ``<link rel="icon">``
#: do favicon — que já é um data URI e não sai daqui — fique de fora.
_PADRAO_CSS = re.compile(
    r'<link\b[^>]*\brel="stylesheet"[^>]*\bhref="(https?://[^"]+)"[^>]*/?>',
    re.IGNORECASE,
)

#: ``url(...)`` dentro de uma folha, ignorando os que já são data URI.
_PADRAO_URL_CSS = re.compile(r"""url\(\s*(["']?)(?!data:)([^"')]+)\1\s*\)""")

#: Timeout (segundos) do download de cada recurso. São arquivos de dezenas a
#: centenas de KB em CDN, então o valor é curto de propósito: é melhor falhar
#: rápido e dizer o que houve do que pendurar a geração do mapa.
TIMEOUT = 30


def _nome_em_cache(url: str) -> str:
    """Deriva o nome do arquivo em cache a partir da URL.

    Mantém a URL legível no nome — ``leaflet@1.9.3`` continua visível — para
    que dê para saber o que está em ``data/raw/libs/`` sem abrir os arquivos.
    A versão faz parte do nome, então uma troca de versão do folium baixa os
    arquivos novos em vez de reaproveitar os antigos por engano.

    Args:
        url: endereço do recurso.

    Returns:
        Nome de arquivo seguro em qualquer sistema de arquivos.
    """
    sem_esquema = re.sub(r"^https?://", "", url)
    return re.sub(r"[^A-Za-z0-9._@-]+", "_", sem_esquema)


def baixar_recurso(url: str, usar_cache: bool = True) -> str:
    """Baixa (ou reaproveita do cache) o conteúdo de um recurso da CDN.

    Args:
        url: endereço do ``.js`` ou ``.css``.
        usar_cache: quando ``True``, devolve o arquivo já baixado sem
            reconsultar a CDN. É o padrão: as versões são fixas na URL.

    Returns:
        O conteúdo, como texto.

    Raises:
        requests.HTTPError: se a CDN recusar a requisição.
        requests.RequestException: falha de rede ou de TLS.
    """
    destino = config.DIR_LIBS / _nome_em_cache(url)
    if usar_cache and destino.exists() and destino.stat().st_size > 0:
        _LOGGER.debug("Reaproveitando %s do cache.", destino.name)
        return destino.read_text(encoding="utf-8")

    rede.usar_certificados_do_sistema()
    _LOGGER.info("Baixando %s ...", url)
    resposta = requests.get(url, timeout=TIMEOUT)
    resposta.raise_for_status()
    # As CDNs servem JS/CSS em UTF-8, mas nem sempre declaram o charset, e o
    # `requests` cai para ISO-8859-1 quando ele falta — o que corromperia os
    # acentos de comentários e de conteúdo `content:` no CSS.
    if not resposta.encoding or resposta.encoding.lower() == "iso-8859-1":
        resposta.encoding = "utf-8"
    conteudo = resposta.text

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    return conteudo


def absolutizar_urls_css(css: str, url_origem: str) -> str:
    """Reescreve os ``url(...)`` relativos da folha para URL absoluta.

    Ver o cabeçalho do módulo para o porquê.

    Args:
        css: conteúdo da folha de estilo.
        url_origem: URL de onde ela veio, que é a base da resolução.

    Returns:
        A folha com os caminhos relativos resolvidos.
    """

    def _trocar(casamento: re.Match) -> str:
        aspas, alvo = casamento.group(1), casamento.group(2).strip()
        # Já absoluto (http://, https:// ou //cdn...): nada a fazer.
        if re.match(r"^(https?:)?//", alvo):
            return casamento.group(0)
        # `#default#VML` é diretiva do IE antigo, e `#id` é referência interna
        # ao próprio documento — nenhum dos dois é caminho de arquivo.
        if alvo.startswith("#"):
            return casamento.group(0)
        return f"url({aspas}{urljoin(url_origem, alvo)}{aspas})"

    return _PADRAO_URL_CSS.sub(_trocar, css)


def embutir_no_html(caminho: Path, usar_cache: bool = True) -> dict[str, int]:
    """Substitui no HTML as referências de CDN pelo conteúdo dos arquivos.

    Args:
        caminho: o HTML gravado por `mapa.gera_mapa`.
        usar_cache: reaproveita os arquivos de ``data/raw/libs/``.

    Returns:
        ``{"scripts", "estilos", "bytes"}`` — quantos de cada tipo foram
        embutidos e quantos bytes isso acrescentou ao arquivo.

    Raises:
        requests.RequestException: se algum recurso não puder ser baixado. A
            falha NÃO é engolida de propósito: seguir em frente gravaria um
            mapa que continua dependendo de CDN enquanto o README afirma o
            contrário — exatamente o tipo de divergência silenciosa que este
            projeto barra em toda etapa.
    """
    html = caminho.read_text(encoding="utf-8")
    tamanho_antes = len(html.encode("utf-8"))
    contagem = {"scripts": 0, "estilos": 0}

    def _embutir_script(casamento: re.Match) -> str:
        url = casamento.group(1)
        js = baixar_recurso(url, usar_cache=usar_cache)
        # Um `</script>` dentro de string do próprio JS fecharia a tag aqui e
        # despejaria o resto do arquivo como texto na página.
        js = js.replace("</script", r"<\/script")
        contagem["scripts"] += 1
        return f"<script>/* {url} */\n{js}\n</script>"

    def _embutir_css(casamento: re.Match) -> str:
        url = casamento.group(1)
        css = absolutizar_urls_css(baixar_recurso(url, usar_cache=usar_cache), url)
        css = css.replace("</style", r"<\/style")
        contagem["estilos"] += 1
        return f"<style>/* {url} */\n{css}\n</style>"

    html = _PADRAO_SCRIPT.sub(_embutir_script, html)
    html = _PADRAO_CSS.sub(_embutir_css, html)

    caminho.write_text(html, encoding="utf-8")
    acrescimo = len(html.encode("utf-8")) - tamanho_antes

    _LOGGER.info(
        "Embutidos %d script(s) e %d folha(s) de estilo (+%.0f KB).",
        contagem["scripts"],
        contagem["estilos"],
        acrescimo / 1024,
    )
    return {**contagem, "bytes": acrescimo}


def restantes_externos(caminho: Path) -> list[str]:
    """Lista as bibliotecas externas que o HTML ainda carrega.

    Serve de conferência depois de `embutir_no_html`: nada deve sobrar. O que
    o mapa continua buscando na rede são os ladrilhos do basemap e os ativos
    de CSS reescritos para absoluto — nenhum dos dois casa com estes padrões,
    e nenhum dos dois impede o mapa de funcionar.

    Args:
        caminho: o HTML gravado.

    Returns:
        As URLs de ``<script src>`` e ``<link rel=stylesheet>`` que restaram.
    """
    html = caminho.read_text(encoding="utf-8")
    return _PADRAO_SCRIPT.findall(html) + _PADRAO_CSS.findall(html)
