"""Testes de `src.embutir` — o que torna o HTML independente de CDN.

Por que este arquivo existe: as bibliotecas embutidas só fazem falta quando a
rede BLOQUEIA a CDN ou não há rede nenhuma. Nos dois casos o mapa continua
abrindo normalmente na máquina de quem o gerou, que tem tudo em cache e
internet — então uma regressão aqui é invisível no uso do dia a dia e só
aparece na hora em que alguém precisa do arquivo justamente onde ele foi feito
para funcionar. Nenhum outro teste cobre isso.

Nada aqui vai à rede: `baixar_recurso` é substituído por um dublê, e o HTML de
entrada é montado no próprio teste.
"""

import re

import pytest

from src import config, embutir

#: CR que NÃO é seguido de LF — o terminador solitário que o modo texto do
#: Python converteria em CRLF. Ver `test_embutir_nao_traduz_quebra_de_linha`.
_CR_SOZINHO = re.compile(rb"\r(?!\n)")

# --------------------------------------------------------------------------- #
# Nome do arquivo em cache
# --------------------------------------------------------------------------- #


def test_nome_em_cache_preserva_a_versao():
    """A versão faz parte do nome — trocar de versão não reusa o arquivo velho.

    É o que impede o cache de servir `leaflet@1.9.3` quando o folium passar a
    pedir outra versão: os dois nomes são diferentes, então o novo é baixado.
    """
    antigo = embutir._nome_em_cache(
        "https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"
    )
    novo = embutir._nome_em_cache(
        "https://cdn.jsdelivr.net/npm/leaflet@2.0.0/dist/leaflet.js"
    )
    assert antigo != novo
    assert "1.9.3" in antigo


def test_nome_em_cache_nao_escapa_do_diretorio():
    """O nome derivado da URL não pode sair de `data/raw/libs/`.

    O `..` sobrevive à normalização (`a/b/../c.js` vira `a_b_.._c.js`) e isso
    está certo: sem separador de caminho ele é um nome de arquivo comum, não
    travessia. O que a asserção cobra é a consequência — que o destino continue
    sendo filho direto do diretório de cache.
    """
    nome = embutir._nome_em_cache("https://cdn.exemplo/a/b/../c.js")
    assert "/" not in nome
    assert "\\" not in nome

    destino = (config.DIR_LIBS / nome).resolve()
    assert destino.parent == config.DIR_LIBS.resolve()


# --------------------------------------------------------------------------- #
# url() relativo dentro do CSS
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("css", "esperado"),
    [
        # O caso real do leaflet.css.
        (
            "url(images/layers.png)",
            "url(https://cdn.exemplo/dist/images/layers.png)",
        ),
        # O caso real do FontAwesome: sobe um nível.
        (
            "url(../webfonts/fa-solid-900.woff2)",
            "url(https://cdn.exemplo/webfonts/fa-solid-900.woff2)",
        ),
        # Com aspas, que também ocorre na prática.
        (
            'url("images/marker.png")',
            'url("https://cdn.exemplo/dist/images/marker.png")',
        ),
    ],
)
def test_url_relativa_vira_absoluta(css, esperado):
    """Embutida no HTML, uma URL relativa apontaria para o lado do MAPA.

    É o ponto mais delicado do módulo: sem a reescrita, `images/layers.png`
    passaria a ser procurado ao lado de `output/mapa_if_sul.html`, onde não
    existe.
    """
    assert embutir.absolutizar_urls_css(css, "https://cdn.exemplo/dist/x.css") == esperado


@pytest.mark.parametrize(
    "css",
    [
        # Já absoluta: mexer só a quebraria.
        "url(https://outra.cdn/f.woff2)",
        "url(//protocolo-relativo.cdn/f.woff2)",
        # Fonte embutida: não é caminho de arquivo.
        "url(data:font/woff2;base64,AAAA)",
        # Diretiva do IE antigo, presente no leaflet.css.
        "url(#default#VML)",
    ],
)
def test_url_que_nao_deve_ser_tocada(css):
    """Só o caminho relativo é reescrito; o resto passa intacto."""
    assert embutir.absolutizar_urls_css(css, "https://cdn.exemplo/dist/x.css") == css


# --------------------------------------------------------------------------- #
# Substituição no HTML
# --------------------------------------------------------------------------- #

_HTML = """<!DOCTYPE html>
<html>
<head>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg/>">
<script src="https://cdn.exemplo/lib.js"></script>
<link rel="stylesheet" href="https://cdn.exemplo/dist/lib.css"/>
</head>
<body><script>var tiles = "https://{s}.basemaps.cartocdn.com/x.png";</script></body>
</html>"""


@pytest.fixture
def html(tmp_path):
    caminho = tmp_path / "mapa.html"
    caminho.write_bytes(_HTML.encode("utf-8"))
    return caminho


@pytest.fixture
def sem_rede(monkeypatch):
    """Substitui o download por conteúdo fixo — nenhum teste vai à rede."""
    conteudo = {
        "https://cdn.exemplo/lib.js": "var x = 1;",
        "https://cdn.exemplo/dist/lib.css": ".a{background:url(images/f.png)}",
    }
    monkeypatch.setattr(
        embutir, "baixar_recurso", lambda url, usar_cache=True: conteudo[url]
    )


def test_embutir_troca_as_tags_pelo_conteudo(html, sem_rede):
    """Depois de embutir, nada de `<script src>` nem `<link rel=stylesheet>`."""
    resumo = embutir.embutir_no_html(html)
    assert resumo == {"scripts": 1, "estilos": 1, "bytes": resumo["bytes"]}

    texto = html.read_text(encoding="utf-8")
    assert "var x = 1;" in texto
    assert embutir.restantes_externos(html) == []
    # E o `url()` da folha foi resolvido contra a CDN de origem, não contra o mapa.
    assert "url(https://cdn.exemplo/dist/images/f.png)" in texto


def test_embutir_preserva_o_favicon_e_o_basemap(html, sem_rede):
    """O favicon é `<link rel=icon>` e os ladrilhos vivem dentro do JS.

    Nenhum dos dois pode ser tocado: o favicon já é um data URI, e o endereço
    dos ladrilhos é um template do Leaflet (`{s}`, `{z}`) que precisa continuar
    apontando para a CARTO — é ele que traz o fundo de ruas quando há rede.
    """
    embutir.embutir_no_html(html)
    texto = html.read_text(encoding="utf-8")
    assert 'rel="icon"' in texto
    assert "data:image/svg+xml" in texto
    assert "{s}.basemaps.cartocdn.com" in texto


def test_embutir_nao_traduz_quebra_de_linha(tmp_path, monkeypatch):
    """CR solitário sobrevive ao par leitura-gravação.

    O JS minificado das bibliotecas traz centenas de CR sozinhos. Com o modo
    texto padrão do Python eles viram CRLF, e o mapa — que é um artefato
    versionado — aparece INTEIRO como modificado no git a cada geração, o que
    guarda uma cópia de 18 MB onde caberia um delta de bytes.
    """
    caminho = tmp_path / "mapa.html"
    original = b'<html>\r<script src="https://cdn.exemplo/lib.js"></script>\r\n\n</html>'
    caminho.write_bytes(original)
    monkeypatch.setattr(embutir, "baixar_recurso", lambda url, usar_cache=True: "a\rb")

    embutir.embutir_no_html(caminho)

    depois = caminho.read_bytes()
    assert depois.count(b"\r\n") == original.count(b"\r\n")
    assert len(_CR_SOZINHO.findall(depois)) == 2, "o CR solitário virou CRLF"


# --------------------------------------------------------------------------- #
# Idioma
# --------------------------------------------------------------------------- #


def test_declarar_idioma_acrescenta_lang(html):
    """O folium escreve `<html>` sem idioma; a página é toda em português."""
    assert embutir.declarar_idioma(html) is True
    assert '<html lang="pt-BR">' in html.read_text(encoding="utf-8")


def test_declarar_idioma_e_idempotente(html):
    """Rodar duas vezes não produz `<html lang lang>`."""
    embutir.declarar_idioma(html)
    assert embutir.declarar_idioma(html) is False
    assert html.read_text(encoding="utf-8").count("lang=") == 1
