"""Testes de integridade dos artefatos do pipeline.

Diferente de `test_estrutura.py`, que é fumaça sobre o código, aqui os testes
leem os dois Parquet já gravados em ``data/processed/`` e verificam invariantes
do RESULTADO:

* `if_<recorte>_categorizado.parquet` — o recorte não deixou vazar nada que não
  fosse cooperativa de crédito ou um dos cinco bancos-alvo, e todo código IBGE
  está no padrão de 7 dígitos;
* `agregado_municipio_<recorte>.parquet` — foi gravado depois do dataset que o
  originou, a agregação não perdeu nenhum ponto no join com a malha, e não há
  município repetido;
* `pontos_geocodificados_<recorte>.parquet` — todo ponto tem coordenada, ela
  cai dentro do retângulo do recorte, e o nível de precisão declarado é um dos
  previstos.

QUAL recorte é lido: o ATIVO (`config.SIGLAS_UF`), que sem nada é a Região Sul.
Para conferir os artefatos de outro recorte, rode
``MAPA_IF_UFS=BR pytest`` — ver `config.VARIAVEL_RECORTE`. Os testes nunca
misturam recortes: os caminhos e os valores esperados saem todos do mesmo.

Os arquivos são pré-requisito: rode ``python -m src.etl_bacen``,
``python -m src.agregacao`` e ``python -m src.cnefe`` antes. Sem eles os testes
falham com a instrução, em vez de passarem silenciosamente sobre um dataset
inexistente.
"""

import re
from datetime import UTC, datetime

import geopandas as gpd
import pandas as pd
import pytest

from src import cnefe, config
from src.etl_bacen import (
    CATEGORIA_BANCO,
    CATEGORIA_COOPERATIVA,
    NOME_COMERCIAL_BANCO,
    _normalizar_espacos,
)

#: Padrão do código IBGE de município: exatamente 7 dígitos (UF + município +
#: dígito verificador). Sem `-`, sem `.0`, sem zero à esquerda faltando.
PADRAO_CODIGO_IBGE = re.compile(r"^\d{7}$")

#: Folga, em segundos, dos dois testes que comparam data de gravação.
#:
#: O git NÃO preserva mtime: no `clone` e no `checkout` todo arquivo recebe a
#: hora em que foi escrito no disco, na ordem do índice — que é alfabética.
#: "agregado_municipio_sul.parquet" vem antes de "if_sul_categorizado.parquet",
#: então num clone o agregado é sempre gravado PRIMEIRO e fica alguns
#: milissegundos mais velho que o dataset que o originou.
#:
#: Sem folga, isso reprovava um clone recém-feito com a mensagem de artefato
#: desatualizado — medido em dois clones do repositório: 5,8 ms e 7,5 ms de
#: diferença. Um artefato REALMENTE esquecido está minutos, horas ou dias
#: atrás, nunca milissegundos, então a folga separa os dois casos sem afrouxar
#: o que o teste existe para pegar.
TOLERANCIA_CHECKOUT_S = 60.0


def _exigir_arquivo(caminho, comando):
    if not caminho.exists():
        pytest.fail(
            f"{caminho} não existe. Rode `{comando}` a partir da raiz do projeto "
            "antes de executar os testes."
        )


@pytest.fixture(scope="module")
def pontos() -> pd.DataFrame:
    """Dataset categorizado do BACEN: uma linha por ponto de atendimento."""
    _exigir_arquivo(config.arquivo_if_categorizado(), "python -m src.etl_bacen")
    return pd.read_parquet(config.arquivo_if_categorizado())


@pytest.fixture(scope="module")
def agregado() -> pd.DataFrame:
    """Agregado por município.

    Lido com `pandas` (e não `geopandas`) de propósito: os testes olham só as
    colunas de contagem, e a geometria não precisa ser desserializada.
    """
    _exigir_arquivo(config.arquivo_agregado_municipio(), "python -m src.agregacao")
    return pd.read_parquet(config.arquivo_agregado_municipio())


# --------------------------------------------------------------------------- #
# 1. categoria_if só admite os dois rótulos previstos
# --------------------------------------------------------------------------- #


def test_categoria_if_so_tem_cooperativa_e_banco(pontos):
    """Nenhuma outra categoria vazou pelo filtro de instituições."""
    esperadas = {CATEGORIA_COOPERATIVA, CATEGORIA_BANCO}

    sem_categoria = int(pontos["categoria_if"].isna().sum())
    assert sem_categoria == 0, (
        f"{sem_categoria} linha(s) sem `categoria_if` — toda linha do dataset "
        "final tem de estar classificada."
    )

    encontradas = set(pontos["categoria_if"].dropna().unique())
    assert encontradas <= esperadas, (
        f"categoria_if fora do previsto: {sorted(encontradas - esperadas)!r}. "
        f"Esperado apenas {sorted(esperadas)!r}."
    )

    # O recorte territorial é parte do mesmo filtro: se caiu UF de fora, o
    # dataset não é o recorte que o nome do arquivo diz.
    ufs = set(pontos["uf"].dropna().unique())
    do_recorte = set(config.SIGLAS_UF)
    assert ufs <= do_recorte, (
        f"UF fora do recorte {config.nome_do_recorte()} no dataset: "
        f"{sorted(ufs - do_recorte)!r}."
    )


# --------------------------------------------------------------------------- #
# 2. Os bancos são exatamente os cinco alvos
# --------------------------------------------------------------------------- #


def test_sub_categoria_banco_so_tem_os_cinco_alvos(pontos):
    """Nenhum banco fora de `config.BANCOS_ALVO` passou pelo filtro."""
    bancos = pontos[pontos["categoria_if"] == CATEGORIA_BANCO]
    assert len(bancos) > 0, "Nenhuma linha de categoria_if == 'Banco' no dataset."

    esperadas = set(NOME_COMERCIAL_BANCO.values())

    encontradas = set(bancos["sub_categoria"].dropna().unique())
    assert encontradas <= esperadas, (
        f"sub_categoria de banco fora do de-para: {sorted(encontradas - esperadas)!r}. "
        f"Esperado apenas {sorted(esperadas)!r}."
    )
    assert encontradas == esperadas, (
        "Banco-alvo sem nenhum ponto no dataset: "
        f"{sorted(esperadas - encontradas)!r}. Os cinco deveriam ter rede no Sul — "
        "a ausência indica filtro ou de-para alterado."
    )

    # Checagem pela origem, não só pelo rótulo: o nome bruto da instituição tem
    # de ser um dos cinco nomes exatos de BANCOS_ALVO. Pega o caso em que uma
    # subsidiária ("BANCO BRADESCO FINANCIAMENTOS S.A.") entrasse no recorte e
    # recebesse por engano um nome comercial válido.
    permitidos = {_normalizar_espacos(nome) for nome in config.BANCOS_ALVO}
    instituicoes = set(bancos["nome_instituicao"].dropna().unique())
    assert instituicoes <= permitidos, (
        f"Instituição fora de BANCOS_ALVO classificada como Banco: "
        f"{sorted(instituicoes - permitidos)!r}."
    )


#: Fração máxima do dataset que pode ficar de fora do agregado sem que isso
#: seja tratado como defeito.
#:
#: Um ponto entra no agregado pelo `municipio_ibge`, e fica de fora em dois
#: casos — os dois REAIS, os dois reportados no log da agregação, e nenhum dos
#: dois presente no recorte do Sul:
#:
#: * o código não foi resolvido a partir do nome publicado pelo BACEN. Na safra
#:   202608 é 1 ponto, um Itaú cujo município vem escrito "GOIANA/GO" — Goiana
#:   é em Pernambuco;
#: * o código existe e a malha do IBGE não o tem. São 2 pontos em Boa Esperança
#:   do Norte/MT, município que o cadastro do BACEN já traz e a divisão
#:   territorial da API de Malhas ainda não.
#:
#: O teto é 0,1% e não zero porque zero reprovaria o país inteiro por causa de
#: uma grafia errada na fonte e de um município novo. E não é "qualquer
#: número": passar de 0,1% deixa de ser anomalia de cadastro e vira defeito do
#: de-para nome->código, que é o que estes testes existem para pegar.
FRACAO_MAXIMA_SEM_MUNICIPIO = 0.001


@pytest.fixture(scope="module")
def sem_municipio_na_malha(pontos, agregado) -> pd.DataFrame:
    """Os pontos que o join com a malha não alcança, com a causa de cada um."""
    codigos = set(agregado["municipio_ibge"])
    return pontos[~pontos["municipio_ibge"].isin(codigos)]


def _exigir_perda_aceitavel(perdidos, total, contexto):
    """Reprova se a perda passar de `FRACAO_MAXIMA_SEM_MUNICIPIO`."""
    limite = max(int(total * FRACAO_MAXIMA_SEM_MUNICIPIO), 1)
    if len(perdidos) <= limite:
        return
    sem_codigo = int(perdidos["municipio_ibge"].isna().sum())
    pytest.fail(
        f"{contexto}: {len(perdidos)} de {total} pontos ({len(perdidos)/total:.2%}) "
        f"não entram no agregado, acima do teto de {limite}. "
        f"{sem_codigo} sem `municipio_ibge` e "
        f"{len(perdidos) - sem_codigo} com código fora da malha "
        f"({sorted(perdidos['municipio_ibge'].dropna().unique())[:10]!r}). "
        "Uma perda desse tamanho não é anomalia de cadastro: confira o de-para "
        "nome->código em `etl_bacen.padronizar_municipio_ibge` e se a malha "
        "está na mesma divisão territorial do BACEN."
    )


# --------------------------------------------------------------------------- #
# 3. Código IBGE no padrão de 7 dígitos
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fonte", ["pontos", "agregado"])
def test_codigo_municipio_tem_7_digitos(fonte, request):
    """Nos dois artefatos, `municipio_ibge` é sempre string de 7 dígitos.

    O join da agregação é feito por igualdade de string entre os dois lados —
    um código com formatação diferente (``4314902.0``, ``431490``) não casaria
    e o ponto sumiria da contagem sem erro.
    """
    df = request.getfixturevalue(fonte)
    codigo = df["municipio_ibge"]

    nulos = int(codigo.isna().sum())
    if fonte == "agregado":
        # A malha é a fonte do código; ali um nulo é defeito, sem atenuante.
        assert nulos == 0, (
            f"{nulos} linha(s) do agregado sem `municipio_ibge` — a malha do "
            "IBGE é quem fornece o código, então nulo aqui é malha quebrada."
        )
    else:
        # No dataset do BACEN o nulo é o município que o de-para não resolveu.
        # Ver `FRACAO_MAXIMA_SEM_MUNICIPIO` para por que o limite não é zero.
        limite = max(int(len(df) * FRACAO_MAXIMA_SEM_MUNICIPIO), 1)
        assert nulos <= limite, (
            f"{nulos} de {len(df)} linhas sem `municipio_ibge`, acima do teto "
            f"de {limite}. Municípios afetados: "
            f"{sorted(df.loc[codigo.isna(), 'municipio'].unique())[:10]!r}."
        )

    # O nulo já foi julgado acima, com o critério de cada artefato; aqui a
    # pergunta é outra — o que EXISTE está no formato certo? Deixar o nulo
    # nesta peneira faria os dois testes reprovarem pela mesma linha, com a
    # mensagem errada ("fora do padrão de 7 dígitos: [<NA>]").
    presentes = codigo.dropna()
    invalidos = presentes[
        ~presentes.astype("string").str.fullmatch(r"\d{7}").fillna(False)
    ]
    assert len(invalidos) == 0, (
        f"{len(invalidos)} código(s) fora do padrão de 7 dígitos em `{fonte}`. "
        f"Exemplos: {invalidos.unique()[:5].tolist()!r}"
    )

    # Redundante com o fullmatch acima, mas explicita a intenção do padrão.
    assert all(PADRAO_CODIGO_IBGE.match(str(c)) for c in presentes.unique())


def test_codigos_do_agregado_pertencem_as_ufs_do_recorte(agregado):
    """Os dois primeiros dígitos do código só podem ser os das UFs do recorte."""
    prefixos = set(agregado["municipio_ibge"].astype("string").str.slice(0, 2))
    esperados = {str(config.CODIGO_UF[uf]) for uf in config.SIGLAS_UF}
    assert prefixos <= esperados, (
        f"Município fora do recorte {config.nome_do_recorte()} na malha: "
        f"prefixos {sorted(prefixos - esperados)!r}."
    )


def test_geometria_do_agregado_e_sempre_poligonal():
    """Todo município é `Polygon` ou `MultiPolygon` — nunca uma coleção.

    Não é preciosismo de tipo. O Leaflet monta uma `GeometryCollection` como um
    GRUPO de camadas aninhado, e um grupo não responde a `getElement`, que é o
    que o `bindTooltip` da camada de municípios chama ao varrer as feições. O
    sintoma é o mapa inteiro em branco com os indicadores em "—", e o defeito
    não aparece em teste nenhum que olhe só os números.

    Foi assim que o reparo de geometria inválida de `ibge_malha` quebrou o mapa
    nacional: `make_valid` desfez a auto-interseção de Nhamundá/AM e devolveu o
    polígono junto com um fiapo de linha.
    """
    _exigir_arquivo(config.arquivo_agregado_municipio(), "python -m src.agregacao")
    malha = gpd.read_parquet(config.arquivo_agregado_municipio())

    tipos = malha.geometry.geom_type.value_counts().to_dict()
    fora = {t: n for t, n in tipos.items() if t not in ("Polygon", "MultiPolygon")}
    assert not fora, (
        f"Município(s) com geometria não poligonal: {fora}. "
        f"Exemplos: "
        f"{malha.loc[~malha.geometry.geom_type.isin(['Polygon', 'MultiPolygon']), 'municipio_nome'].head().tolist()!r}."
    )


def test_coluna_regiao_bate_com_a_uf(agregado):
    """Todo município traz a região da sua UF, sem nulo e sem discordância.

    A coluna existe para o filtro hierárquico do mapa (região -> estado). Uma
    linha com `regiao` nula sumiria do mapa ao escolher qualquer região; uma
    com a região errada apareceria na região errada — os dois em silêncio, já
    que nada mais no pipeline lê essa coluna.
    """
    sem_regiao = int(agregado["regiao"].isna().sum())
    assert sem_regiao == 0, f"{sem_regiao} município(s) sem `regiao`."

    esperada = agregado["uf"].map(config.REGIAO_POR_UF)
    divergentes = agregado[agregado["regiao"] != esperada]
    assert len(divergentes) == 0, (
        f"{len(divergentes)} município(s) com `regiao` divergente da UF. "
        f"Exemplos: {divergentes[['municipio_nome', 'uf', 'regiao']].head().to_dict('records')!r}"
    )


# --------------------------------------------------------------------------- #
# 4. Nenhum ponto perdido no join com a malha
# --------------------------------------------------------------------------- #


def test_agregado_nao_e_mais_antigo_que_o_dataset():
    """O agregado tem de ter sido gravado DEPOIS do dataset que o originou.

    É pré-condição de todas as comparações entre os dois arquivos daqui em
    diante: se o ETL foi rodado de novo sem reagregar, os dois Parquet são de
    safras diferentes e qualquer igualdade entre eles é coincidência — ou,
    pior, a divergência aponta para um bug que não existe.

    A comparação é por `mtime` do arquivo, não por conteúdo: é o único carimbo
    de tempo disponível: nenhum dos dois Parquet grava metadado de geração.
    Consequência prática: reescrever o agregado sem regerá-lo (um `touch`, uma
    cópia, um checkout) engana este teste. Ele pega o descuido comum — rodar
    `src.etl_bacen` e esquecer `src.agregacao` —, não adulteração deliberada.

    A comparação leva a folga de `TOLERANCIA_CHECKOUT_S` porque o git não
    preserva mtime e escreve os arquivos em ordem alfabética: num clone o
    agregado nasce alguns milissegundos mais velho que o dataset, e sem a folga
    um repositório recém-clonado reprovava aqui. Ver a constante.
    """
    _exigir_arquivo(config.arquivo_if_categorizado(), "python -m src.etl_bacen")
    _exigir_arquivo(config.arquivo_agregado_municipio(), "python -m src.agregacao")

    mtime_pontos = config.arquivo_if_categorizado().stat().st_mtime
    mtime_agregado = config.arquivo_agregado_municipio().stat().st_mtime

    def _quando(timestamp: float) -> str:
        # `astimezone()` sem argumento adota o fuso local, que é o que se quer
        # aqui: a mensagem é lida por quem está na máquina que gerou o arquivo.
        return (
            datetime.fromtimestamp(timestamp, tz=UTC)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S")
        )

    atraso = mtime_pontos - mtime_agregado
    assert mtime_agregado >= mtime_pontos - TOLERANCIA_CHECKOUT_S, (
        f"{config.arquivo_agregado_municipio().name} está DESATUALIZADO: gravado em "
        f"{_quando(mtime_agregado)}, {atraso:.0f}s ANTES de "
        f"{config.arquivo_if_categorizado().name} ({_quando(mtime_pontos)}). "
        "Rode `python -m src.agregacao` para reagregar sobre o dataset atual."
    )


def test_soma_das_contagens_bate_com_o_total_de_pontos(
    pontos, agregado, sem_municipio_na_malha
):
    """`total_cooperativas + total_bancos` somados = linhas do dataset filtrado.

    A diferença admitida é EXATAMENTE a dos pontos sem município na malha, e
    nada além dela: se a soma for menor do que isso, um ponto sumiu no join por
    outro motivo; se for MAIOR que o total, houve duplicação de linha no merge.
    Ver `FRACAO_MAXIMA_SEM_MUNICIPIO` para as duas causas admitidas.
    """
    total_pontos = len(pontos)
    soma_agregado = int(
        agregado["total_cooperativas"].sum() + agregado["total_bancos"].sum()
    )
    perdidos = len(sem_municipio_na_malha)

    _exigir_perda_aceitavel(sem_municipio_na_malha, total_pontos, "soma do agregado")
    assert soma_agregado == total_pontos - perdidos, (
        f"Soma das contagens do agregado ({soma_agregado}) != linhas do dataset "
        f"({total_pontos}) menos os {perdidos} ponto(s) sem município na malha. "
        f"Diferença não explicada: "
        f"{total_pontos - perdidos - soma_agregado}."
    )


def test_total_por_categoria_bate_com_o_dataset(
    pontos, agregado, sem_municipio_na_malha
):
    """A quebra por categoria também tem de fechar, não só o total.

    Como no total, o desconto é o dos pontos sem município na malha — mas
    descontado POR CATEGORIA: um ponto perdido é de cooperativa ou de banco, e
    somar o desconto no lugar errado esconderia justamente o desequilíbrio que
    este teste procura.
    """
    fora = sem_municipio_na_malha
    _exigir_perda_aceitavel(fora, len(pontos), "contagem por categoria")

    esperado = {
        "total_cooperativas": int(
            (pontos["categoria_if"] == CATEGORIA_COOPERATIVA).sum()
            - (fora["categoria_if"] == CATEGORIA_COOPERATIVA).sum()
        ),
        "total_bancos": int(
            (pontos["categoria_if"] == CATEGORIA_BANCO).sum()
            - (fora["categoria_if"] == CATEGORIA_BANCO).sum()
        ),
    }
    obtido = {coluna: int(agregado[coluna].sum()) for coluna in esperado}
    assert obtido == esperado, (
        f"Contagem por categoria divergente entre os dois artefatos: "
        f"agregado={obtido}, dataset menos os {len(fora)} sem município="
        f"{esperado}."
    )


def test_total_geral_e_a_soma_das_duas_categorias(agregado):
    """`total_geral` é derivado; nenhum município pode divergir da soma."""
    soma = agregado["total_cooperativas"] + agregado["total_bancos"]
    divergentes = agregado.loc[soma != agregado["total_geral"], "municipio_ibge"]
    assert len(divergentes) == 0, (
        f"{len(divergentes)} município(s) com total_geral != cooperativas + bancos. "
        f"Exemplos: {divergentes.head().tolist()!r}"
    )


# --------------------------------------------------------------------------- #
# 5. Um município, uma linha
# --------------------------------------------------------------------------- #


def test_nao_ha_municipio_duplicado_no_agregado(agregado):
    """Chave duplicada aqui significaria contagem inflada no mapa."""
    duplicados = agregado.loc[
        agregado["municipio_ibge"].duplicated(keep=False), "municipio_ibge"
    ]
    assert len(duplicados) == 0, (
        f"{duplicados.nunique()} código(s) de município repetido(s) no agregado. "
        f"Exemplos: {sorted(duplicados.unique())[:5]!r}"
    )


# --------------------------------------------------------------------------- #
# 6. Geocodificação dos pontos (src.cnefe)
# --------------------------------------------------------------------------- #

#: Folga, em graus, do retângulo que contém o recorte.
#:
#: Meio grau é ~55 km — bem mais que qualquer deslocamento em leque, e bem
#: menos que a distância até a UF vizinha mais próxima que interessaria pegar.
FOLGA_CAIXA_GRAUS = 0.5


@pytest.fixture(scope="module")
def caixa_do_recorte(agregado) -> dict[str, float]:
    """Retângulo que contém o recorte ativo, com folga de `FOLGA_CAIXA_GRAUS`.

    Sai da geometria da malha, e não de números transcritos: a versão anterior
    era a caixa do Sul escrita à mão, que reprovaria qualquer outro recorte.

    Serve para pegar a classe de erro que passaria despercebida: coordenada
    trocada de sinal, latitude e longitude invertidas, ou casamento com um
    endereço de outra região do país. O teste é grosseiro de propósito — a
    conferência fina, contra o polígono do município de cada ponto, é feita na
    própria geocodificação por `cnefe.conferir_dentro_do_municipio`.
    """
    malha = gpd.read_parquet(config.arquivo_agregado_municipio())
    oeste, sul, leste, norte = malha.total_bounds
    return {
        "lon_min": float(oeste) - FOLGA_CAIXA_GRAUS,
        "lon_max": float(leste) + FOLGA_CAIXA_GRAUS,
        "lat_min": float(sul) - FOLGA_CAIXA_GRAUS,
        "lat_max": float(norte) + FOLGA_CAIXA_GRAUS,
    }


@pytest.fixture(scope="module")
def geocodificados() -> pd.DataFrame:
    """Pontos de atendimento com coordenada e nível de precisão."""
    _exigir_arquivo(config.arquivo_pontos_geocodificados(), "python -m src.cnefe")
    return pd.read_parquet(config.arquivo_pontos_geocodificados())


def test_todo_ponto_geocodificado_tem_coordenada(geocodificados, pontos):
    """Nenhum ponto fica sem posição, e nenhum ponto se perde no caminho.

    O fallback de município garante coordenada para 100% das linhas; a única
    perda admitida é a de código IBGE inexistente na malha, que o próprio
    `src.cnefe` registra no log.
    """
    nulos = int(geocodificados[["latitude", "longitude"]].isna().any(axis=1).sum())
    assert nulos == 0, f"{nulos} ponto(s) sem coordenada no arquivo geocodificado."

    assert len(geocodificados) <= len(pontos), (
        f"A geocodificação devolveu {len(geocodificados)} linhas para "
        f"{len(pontos)} pontos do dataset — ela não deveria criar linhas."
    )


def test_coordenadas_caem_dentro_do_recorte(geocodificados, caixa_do_recorte):
    """Toda coordenada está no retângulo que contém as UFs do recorte."""
    fora = geocodificados[
        (geocodificados["longitude"] < caixa_do_recorte["lon_min"])
        | (geocodificados["longitude"] > caixa_do_recorte["lon_max"])
        | (geocodificados["latitude"] < caixa_do_recorte["lat_min"])
        | (geocodificados["latitude"] > caixa_do_recorte["lat_max"])
    ]
    assert len(fora) == 0, (
        f"{len(fora)} ponto(s) fora do retângulo de {config.nome_do_recorte()}. "
        f"Exemplos: "
        f"{fora[['municipio', 'uf', 'latitude', 'longitude']].head().to_dict('records')!r}"
    )


def test_todo_ponto_cai_dentro_do_proprio_municipio(geocodificados):
    """A invariante forte da geocodificação: ponto no polígono do seu município.

    `caixa_do_recorte` é grosseira de propósito e só pega coordenada trocada de sinal
    ou de outra região do país. A conferência que importa é esta: um CEP
    digitado errado na fonte casa com um endereço REAL e plausível em outra
    cidade, e nada no texto denuncia — só o polígono. `src.cnefe` rebaixa esses
    pontos na geração; o teste existe para que uma regressão nessa conferência,
    ou uma mudança de ordem que a torne obsoleta (o deslocamento em leque é
    aplicado depois dela), não passe despercebida.
    """
    _exigir_arquivo(config.arquivo_agregado_municipio(), "python -m src.agregacao")
    malha = gpd.read_parquet(config.arquivo_agregado_municipio())

    dentro = cnefe.conferir_dentro_do_municipio(geocodificados, malha)
    fora = geocodificados[~dentro]
    assert len(fora) == 0, (
        f"{len(fora)} ponto(s) fora do polígono do próprio município. "
        f"Exemplos: "
        f"{fora[['municipio', 'uf', 'precisao', 'latitude', 'longitude']].head().to_dict('records')!r}"
    )


def test_precisao_declarada_e_um_dos_niveis_previstos(geocodificados):
    """`precisao` só admite os quatro níveis de `cnefe.ORDEM_PRECISAO`.

    O popup do mapa lê essa coluna para descrever ao leitor o que a posição do
    marcador significa; um valor fora da tabela viraria texto solto na tela.
    """
    encontrados = set(geocodificados["precisao"].dropna().unique())
    previstos = set(cnefe.ORDEM_PRECISAO)
    assert encontrados <= previstos, (
        f"Nível de precisão desconhecido: {sorted(encontrados - previstos)!r}. "
        f"Previstos: {sorted(previstos)!r}."
    )


def test_geocodificado_nao_e_mais_antigo_que_o_dataset():
    """O arquivo geocodificado tem de ser posterior ao dataset que o originou.

    Mesma razão de `test_agregado_nao_e_mais_antigo_que_o_dataset`: rodar o ETL
    e esquecer `src.cnefe` deixaria o mapa desenhando os pontos da safra
    anterior.
    """
    _exigir_arquivo(config.arquivo_if_categorizado(), "python -m src.etl_bacen")
    _exigir_arquivo(config.arquivo_pontos_geocodificados(), "python -m src.cnefe")

    mtime_pontos = config.arquivo_if_categorizado().stat().st_mtime
    mtime_geo = config.arquivo_pontos_geocodificados().stat().st_mtime
    assert mtime_geo >= mtime_pontos - TOLERANCIA_CHECKOUT_S, (
        f"{config.arquivo_pontos_geocodificados().name} está DESATUALIZADO em "
        f"{mtime_pontos - mtime_geo:.0f}s em relação a "
        f"{config.arquivo_if_categorizado().name}. "
        "Rode `python -m src.cnefe` para regerá-lo."
    )


def test_agregado_tem_todos_os_municipios_do_recorte(agregado):
    """A malha completa do recorte, não só os municípios que têm atendimento.

    Um município a menos aqui é um buraco no coroplético, não um zero. Com o
    recorte padrão são os 1.191 do Sul; com ``--ufs BR``, os 5.570 do país.
    """
    esperado_por_uf = config.municipios_esperados()
    esperado = sum(esperado_por_uf.values())
    assert len(agregado) == esperado, (
        f"Agregado tem {len(agregado)} municípios; a divisão territorial "
        f"vigente tem {esperado} em {config.nome_do_recorte()}."
    )

    por_uf = agregado["uf"].value_counts().to_dict()
    assert por_uf == esperado_por_uf, (
        f"Contagem de municípios por UF divergente: {por_uf} != "
        f"{esperado_por_uf}."
    )


def test_tabela_de_municipios_soma_o_brasil():
    """As 27 entradas de `config.MUNICIPIOS_POR_UF` somam 5.570.

    Esta tabela é a barreira contra malha incompleta — é contra ela que
    `pipeline._obter_malha` recusa uma malha com buraco. Um número errado aqui
    não faria nada falhar: faria a barreira aprovar a malha errada, ou reprovar
    a certa. Daí conferir a tabela contra o total oficial do país, que é o
    único número redondo e verificável do conjunto.
    """
    assert set(config.MUNICIPIOS_POR_UF) == set(config.CODIGO_UF), (
        "MUNICIPIOS_POR_UF e CODIGO_UF têm de cobrir as MESMAS 27 UFs; "
        f"diferença: {set(config.MUNICIPIOS_POR_UF) ^ set(config.CODIGO_UF)!r}."
    )
    total = sum(config.MUNICIPIOS_POR_UF.values())
    assert total == config.TOTAL_MUNICIPIOS_BR, (
        f"A tabela soma {total} municípios; o Brasil tem "
        f"{config.TOTAL_MUNICIPIOS_BR}."
    )

    por_regiao = {
        regiao: sum(config.MUNICIPIOS_POR_UF[uf] for uf in ufs)
        for regiao, ufs in config.REGIOES.items()
    }
    assert por_regiao["Sul"] == 1191, (
        f"A Região Sul tem 1.191 municípios; a tabela diz {por_regiao['Sul']}."
    )
