"""Constantes de configuração do projeto mapa-if-br.

Centraliza caminhos de diretórios e as regras de recorte do dataset
(estados-alvo, instituições-alvo e segmento de cooperativas).
"""

import math
import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #

# BASE_DIR aponta para a raiz do projeto, pois este arquivo vive em
# <raiz>/src/config.py. O nome da pasta não importa: quem clonar para um
# diretório com outro nome continua funcionando.
BASE_DIR = Path(__file__).resolve().parent.parent

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"

# Sistema de referência geográfico padrão (lat/lon em graus decimais).
CRS_GEOGRAFICO = "EPSG:4326"

# --------------------------------------------------------------------------- #
# Arquivos brutos do BACEN (posição: 31.8.2026)
# --------------------------------------------------------------------------- #

ARQUIVO_AGENCIAS = RAW_DIR / "202608AGENCIAS.xlsx"
ARQUIVO_POSTOS = RAW_DIR / "202608POSTOS.xlsx"

#: Safra dos dados do BACEN, no formato em que ela é EXIBIDA (mês/ano).
#:
#: Vive aqui, ao lado dos arquivos de onde ela sai, para que o cabeçalho do
#: mapa e o crédito de fontes não precisem repetir a data por conta própria:
#: trocar de safra é trocar os dois arquivos acima e esta linha, e a página
#: inteira acompanha. Ver `src.mapa.adicionar_moldura`.
DATA_DADOS = "08/2026"

# Nas duas planilhas as linhas 1-9 (1-based) são cabeçalho institucional do
# BACEN; o cabeçalho real das colunas está na linha 10, ou seja, índice 9
# zero-based — que é exatamente o valor esperado por `pandas.read_excel(header=)`.
LINHA_CABECALHO_BACEN = 9

# O destino do dataset categorizado é derivado do recorte — ver
# `arquivo_if_categorizado`, na seção "Artefatos derivados do recorte".

# --------------------------------------------------------------------------- #
# Recorte territorial
# --------------------------------------------------------------------------- #

#
# As tabelas abaixo descrevem o PAÍS INTEIRO e são fixas; o que varia de uma
# execução para outra é `SIGLAS_UF`, o recorte ATIVO, que diz quais dessas UFs
# entram no dataset, na malha, no CNEFE e no mapa. O padrão é o BRASIL inteiro;
# `definir_recorte` o troca a partir da linha de comando (``--ufs``).

#: Código IBGE de cada UF. São os dois primeiros dígitos do código de município
#: (ex.: 4314902 = Porto Alegre, UF 43 = RS), o que permite derivar a UF de
#: qualquer feição da malha sem consultar a API de Localidades.
CODIGO_UF = {
    # Norte
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17,
    # Nordeste
    "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25,
    "PE": 26, "AL": 27, "SE": 28, "BA": 29,
    # Sudeste
    "MG": 31, "ES": 32, "RJ": 33, "SP": 35,
    # Sul
    "PR": 41, "SC": 42, "RS": 43,
    # Centro-Oeste
    "MS": 50, "MT": 51, "GO": 52, "DF": 53,
}

#: Quantidade oficial de municípios por UF (divisão territorial vigente).
#:
#: Usado como conferência do que a API de Malhas devolve — se o total divergir,
#: a malha baixada está incompleta e o mapa sairia com buracos onde deveria
#: mostrar zero. A SOMA das 27 entradas tem de dar exatamente `TOTAL_MUNICIPIOS_BR`,
#: e é isso que `test_tabela_de_municipios_soma_o_brasil` cobra: uma tabela com
#: um número errado transformaria a barreira contra malha incompleta na própria
#: fonte do erro.
MUNICIPIOS_POR_UF = {
    "RO": 52, "AC": 22, "AM": 62, "RR": 15, "PA": 144, "AP": 16, "TO": 139,
    "MA": 217, "PI": 224, "CE": 184, "RN": 167, "PB": 223,
    "PE": 185, "AL": 102, "SE": 75, "BA": 417,
    "MG": 853, "ES": 78, "RJ": 92, "SP": 645,
    "PR": 399, "SC": 295, "RS": 497,
    "MS": 79, "MT": 141, "GO": 246, "DF": 1,
}

#: Total de municípios do Brasil na divisão territorial vigente.
TOTAL_MUNICIPIOS_BR = 5570

#: As cinco grandes regiões do IBGE -> as UFs de cada uma.
#:
#: A ordem das chaves é a do IBGE (Norte -> Centro-Oeste) e é a ordem em que os
#: botões de região aparecem na barra de controles do mapa. Dentro de cada
#: região as UFs vão na ordem de código, que é como o IBGE as publica.
REGIOES = {
    "Norte": ["RO", "AC", "AM", "RR", "PA", "AP", "TO"],
    "Nordeste": ["MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"],
    "Sudeste": ["MG", "ES", "RJ", "SP"],
    "Sul": ["PR", "SC", "RS"],
    "Centro-Oeste": ["MS", "MT", "GO", "DF"],
}

#: UF -> nome da região dela. Derivado de `REGIOES` para que exista uma fonte
#: só: acrescentar uma UF lá já a coloca aqui.
REGIAO_POR_UF = {uf: regiao for regiao, ufs in REGIOES.items() for uf in ufs}

#: Nome oficial de cada UF, para os rótulos da lista de estados do mapa.
#:
#: A busca da barra de controles casa contra ESTE texto, e não contra a sigla:
#: digitar "Rio" precisa achar Rio de Janeiro, Rio Grande do Norte e Rio Grande
#: do Sul, o que a sigla sozinha não permite.
NOME_UF = {
    "RO": "Rondônia", "AC": "Acre", "AM": "Amazonas", "RR": "Roraima",
    "PA": "Pará", "AP": "Amapá", "TO": "Tocantins",
    "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará",
    "RN": "Rio Grande do Norte", "PB": "Paraíba", "PE": "Pernambuco",
    "AL": "Alagoas", "SE": "Sergipe", "BA": "Bahia",
    "MG": "Minas Gerais", "ES": "Espírito Santo", "RJ": "Rio de Janeiro",
    "SP": "São Paulo",
    "PR": "Paraná", "SC": "Santa Catarina", "RS": "Rio Grande do Sul",
    "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "GO": "Goiás",
    "DF": "Distrito Federal",
}

#: Todas as 27 UFs, na ordem de código — o recorte nacional.
SIGLAS_BR = sorted(CODIGO_UF, key=lambda uf: CODIGO_UF[uf])

#: Recorte territorial PADRÃO: o Brasil inteiro.
#:
#: É o que `python main.py` sem argumentos produz, e é DE PROPÓSITO o mesmo
#: recorte do mapa publicado: quem clona o repositório e roda o comando óbvio
#: reproduz o que está no ar. Um padrão que gerasse outra coisa faria a
#: primeira execução de todo mundo contradizer o site.
#:
#: O preço é que essa primeira execução é cara — ~3,9 GB de CNEFE e dezenas de
#: minutos —, e quem quiser o caminho barato pede o recorte menor:
#: ``--ufs Sul`` leva ~580 MB e ~1,5 min. O `main` avisa, antes de começar,
#: quantas UFs faltam baixar (ver `main._anunciar_inicio`).
#:
#: O projeto nasceu com a Região Sul como padrão, e o nome do repositório é
#: dessa época.
RECORTE_PADRAO = list(SIGLAS_BR)

#: Recorte ATIVO desta execução — a lista de UFs que o pipeline inteiro enxerga.
#:
#: É a única constante deste bloco que muda em tempo de execução, e por isso
#: todo mundo a lê como ``config.SIGLAS_UF`` na hora de usar, nunca a captura
#: num valor default de parâmetro: um default é avaliado na importação do
#: módulo, ou seja, ANTES de `definir_recorte` rodar, e congelaria o Sul.
SIGLAS_UF = list(RECORTE_PADRAO)


def definir_recorte(ufs: list[str]) -> list[str]:
    """Fixa o recorte territorial desta execução.

    Chamado uma vez, por `main`, logo depois de processar a linha de comando e
    antes de qualquer etapa do pipeline.

    A ORDEM RECEBIDA É PRESERVADA (só a caixa é normalizada e a repetição
    removida), porque ela é visível: é nela que as UFs aparecem no filtro de
    estado da barra do mapa. Ordenar por código aqui trocaria os três botões do
    recorte padrão de lugar sem nenhum dado ter mudado. Onde a ordem NÃO pode
    depender de digitação — o slug do arquivo — quem ordena é `slug_recorte`.

    Args:
        ufs: siglas do recorte, ex.: ``["SC", "RS", "PR"]``.

    Returns:
        A lista já normalizada, a mesma que ficou em `SIGLAS_UF`.

    Raises:
        ValueError: se a lista vier vazia ou trouxer uma sigla inexistente.
    """
    global SIGLAS_UF

    normalizadas: list[str] = []
    for uf in ufs:
        sigla = str(uf).strip().upper()
        if sigla and sigla not in normalizadas:
            normalizadas.append(sigla)

    if not normalizadas:
        raise ValueError("O recorte territorial não pode ser vazio.")

    desconhecidas = sorted(set(normalizadas) - set(CODIGO_UF))
    if desconhecidas:
        raise ValueError(
            f"UF inexistente no recorte: {desconhecidas!r}. "
            f"As siglas válidas são {sorted(CODIGO_UF)!r}."
        )

    SIGLAS_UF = normalizadas
    return SIGLAS_UF


def interpretar_recorte(texto: str) -> list[str]:
    """Converte a forma escrita de um recorte na lista de siglas.

    Aceita três formas, nesta ordem: ``BR`` (as 27 UFs), o nome de uma região
    (``Sul``, ``Centro-Oeste``, sem depender de acento, hífen ou caixa) e uma
    lista de siglas separadas por vírgula.

    Mora aqui, e não no `main`, porque tem DOIS chamadores: a opção ``--ufs``
    da linha de comando e a variável de ambiente `VARIAVEL_RECORTE`, que é como
    o `pytest` — que não tem argumentos próprios — aponta para outro recorte.

    Args:
        texto: a forma escrita, ex.: ``"BR"``, ``"Sul"``, ``"RS,SC,PR"``.

    Returns:
        A lista de siglas, ainda não validada (quem valida é `definir_recorte`).

    Raises:
        ValueError: se o texto não render nenhuma sigla.
    """
    limpo = texto.strip()
    if limpo.upper() == "BR":
        return list(SIGLAS_BR)

    sem_pontuacao = limpo.replace("-", " ").replace("_", " ").casefold()
    for regiao, ufs in REGIOES.items():
        if regiao.replace("-", " ").casefold() == sem_pontuacao:
            return list(ufs)

    siglas = [parte.strip().upper() for parte in limpo.split(",") if parte.strip()]
    if not siglas:
        raise ValueError(
            f"Recorte não reconhecido: {texto!r}. Use BR, o nome de uma região "
            f"({', '.join(REGIOES)}) ou siglas separadas por vírgula "
            "(ex.: RS,SC,PR)."
        )
    return siglas


#: Variável de ambiente que fixa o recorte fora da linha de comando.
#:
#: Existe para o `pytest`, que roda sem argumentos próprios e leria sempre os
#: artefatos do recorte padrão: ``MAPA_IF_UFS=BR pytest`` faz os testes
#: conferirem os artefatos nacionais. Fora dos testes, prefira ``--ufs``.
VARIAVEL_RECORTE = "MAPA_IF_UFS"

_recorte_do_ambiente = os.environ.get(VARIAVEL_RECORTE, "").strip()
if _recorte_do_ambiente:
    definir_recorte(interpretar_recorte(_recorte_do_ambiente))


def recorte(ufs: list[str] | None = None) -> list[str]:
    """Resolve o recorte a usar: o informado, ou o ativo.

    O atalho que evita repetir ``ufs if ufs is not None else config.SIGLAS_UF``
    em cada função do pipeline que aceita um recorte explícito.

    Args:
        ufs: recorte explícito; ``None`` usa `SIGLAS_UF`.

    Returns:
        Uma cópia da lista de siglas.
    """
    return list(SIGLAS_UF if ufs is None else ufs)


def municipios_esperados(ufs: list[str] | None = None) -> dict[str, int]:
    """Quantos municípios a malha do recorte tem de trazer, por UF.

    É o recorte de `MUNICIPIOS_POR_UF`, e é contra ELE que `src.pipeline`
    compara a malha baixada — comparar contra a tabela inteira reprovaria
    qualquer recorte menor que o Brasil.

    Args:
        ufs: recorte explícito; ``None`` usa o ativo.

    Returns:
        ``{sigla: quantidade}``, só com as UFs do recorte.
    """
    return {uf: MUNICIPIOS_POR_UF[uf] for uf in recorte(ufs)}


def regioes_do_recorte(ufs: list[str] | None = None) -> dict[str, list[str]]:
    """As regiões que o recorte alcança, cada uma só com as UFs presentes.

    É o que alimenta os botões de região da barra de controles: com o recorte
    do Sul a barra mostra uma região só, com as três UFs dela, sem precisar de
    dado nacional nenhum.

    Args:
        ufs: recorte explícito; ``None`` usa o ativo.

    Returns:
        ``{região: [siglas]}``, na ordem de `REGIOES`, sem as regiões vazias.
    """
    presentes = set(recorte(ufs))
    return {
        regiao: [uf for uf in ufs_da_regiao if uf in presentes]
        for regiao, ufs_da_regiao in REGIOES.items()
        if presentes & set(ufs_da_regiao)
    }


def nome_do_recorte(ufs: list[str] | None = None) -> str:
    """Nome legível do recorte, para cabeçalho de log e resumo de execução.

    Args:
        ufs: recorte explícito; ``None`` usa o ativo.

    Returns:
        ``"Brasil (27 UFs)"``, ``"Região Sul (PR, SC, RS)"`` ou a lista de
        siglas, conforme o recorte case ou não com o país ou com uma região.
    """
    atual = recorte(ufs)
    if set(atual) == set(SIGLAS_BR):
        return f"Brasil ({len(atual)} UFs)"
    for regiao, ufs_da_regiao in REGIOES.items():
        if set(atual) == set(ufs_da_regiao):
            return f"Região {regiao} ({', '.join(atual)})"
    return ", ".join(atual)


#: Como um nome de região vira pedaço de nome de arquivo.
#:
#: São cinco, e escrever a tabela à mão evita arrastar o `unidecode` para
#: dentro do `config`, que hoje não importa nada do projeto.
_SLUG_REGIAO = {
    "Norte": "norte",
    "Nordeste": "nordeste",
    "Sudeste": "sudeste",
    "Sul": "sul",
    "Centro-Oeste": "centro-oeste",
}


def slug_recorte(ufs: list[str] | None = None) -> str:
    """Identificador curto do recorte, usado no nome de cada artefato.

    Existe para que dois recortes NÃO sobrescrevam o cache um do outro: sem
    ele, um ``--ufs BR`` gravaria a malha nacional por cima de
    ``malha_municipios_sul.geojson`` e a execução seguinte do recorte padrão
    leria 5.570 municípios acreditando ler 1.191 — sem nada falhar.

    O recorte padrão continua produzindo ``"sul"``, ou seja, exatamente os
    nomes de arquivo que o projeto já usava.

    Args:
        ufs: recorte explícito; ``None`` usa o ativo.

    Returns:
        ``"br"`` para o país inteiro, o nome da região quando o recorte é
        exatamente uma delas, e as siglas unidas por ``-`` no resto dos casos.
    """
    atual = recorte(ufs)
    if set(atual) == set(SIGLAS_BR):
        return "br"
    for regiao, ufs_da_regiao in REGIOES.items():
        if set(atual) == set(ufs_da_regiao):
            return _SLUG_REGIAO[regiao]
    return "-".join(sorted(atual)).lower()


# --------------------------------------------------------------------------- #
# Artefatos derivados do recorte
# --------------------------------------------------------------------------- #
#
# Os cinco caminhos abaixo são FUNÇÕES, e não constantes, porque o nome de cada
# um carrega o slug do recorte (ver `slug_recorte`). Como constante, o valor
# seria fixado na importação do módulo — antes de `definir_recorte` rodar — e
# uma execução nacional gravaria tudo com nome de Sul.
#
# Ninguém os usa como valor default de parâmetro pelo mesmo motivo: os módulos
# declaram ``caminho: Path | None = None`` e resolvem na primeira linha.


def arquivo_if_categorizado(ufs: list[str] | None = None) -> Path:
    """Dataset do BACEN recortado e classificado (saída de `src.etl_bacen`)."""
    return PROCESSED_DIR / f"if_{slug_recorte(ufs)}_categorizado.parquet"


def arquivo_malha(ufs: list[str] | None = None) -> Path:
    """Malha municipal crua do IBGE, em cache (`ibge_malha.baixar_malha`)."""
    return RAW_DIR / f"malha_municipios_{slug_recorte(ufs)}.geojson"


def arquivo_agregado_municipio(ufs: list[str] | None = None) -> Path:
    """Uma linha por município, com geometria (saída de `src.agregacao`)."""
    return PROCESSED_DIR / f"agregado_municipio_{slug_recorte(ufs)}.parquet"


def arquivo_pontos_geocodificados(ufs: list[str] | None = None) -> Path:
    """Pontos com coordenada e nível de precisão (saída de `src.cnefe`)."""
    return PROCESSED_DIR / f"pontos_geocodificados_{slug_recorte(ufs)}.parquet"


def arquivo_mapa(ufs: list[str] | None = None) -> Path:
    """HTML interativo autocontido (saída de `src.mapa`)."""
    return OUTPUT_DIR / f"mapa_if_{slug_recorte(ufs)}.html"

# --------------------------------------------------------------------------- #
# APIs do IBGE (https://servicodados.ibge.gov.br/api/docs)
# --------------------------------------------------------------------------- #

URL_IBGE_MALHAS = "https://servicodados.ibge.gov.br/api/v3/malhas"
URL_IBGE_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades"
URL_IBGE_AGREGADOS = "https://servicodados.ibge.gov.br/api/v3/agregados"

#: Nível de generalização das geometrias: "minima", "intermediaria" ou "maxima".
#: "intermediaria" entrega os 1.191 municípios do Sul em ~2 MB — detalhe
#: suficiente para um mapa web, sem o peso dos ~10 MB da qualidade máxima.
QUALIDADE_MALHA = "intermediaria"

#: Agregado SIDRA 6579 = "População residente estimada"; variável 9324 = a
#: própria estimativa, em pessoas. O período é sempre pedido como ``-1``
#: (última posição disponível), nunca fixado em um ano no código.
AGREGADO_IBGE_POPULACAO = "6579"
VARIAVEL_IBGE_POPULACAO = "9324"

#: Timeout (segundos) das chamadas às APIs do IBGE. A malha de um estado em
#: qualidade intermediária chega a ~1 MB e o servidor do IBGE é lento em
#: horário comercial, daí o valor folgado.
TIMEOUT_IBGE = 180

# --------------------------------------------------------------------------- #
# CNEFE — Cadastro Nacional de Endereços para Fins Estatísticos (Censo 2022)
# --------------------------------------------------------------------------- #

#: Diretório dos arquivos por UF do CNEFE em CSV, no FTP do IBGE.
#:
#: O CNEFE é a fonte de coordenadas dos pontos de atendimento (ver `src.cnefe`).
#: Cada endereço do país aparece nele com CEP, logradouro, número e LAT/LON
#: medidos no Censo 2022 — é o que permite geocodificar o endereço publicado
#: pelo BACEN sem depender de serviço externo com limite de requisições.
URL_IBGE_CNEFE = (
    "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_"
    "Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF"
)

#: Onde os ZIP do CNEFE ficam em cache. São ~580 MB para os três estados do
#: Sul, baixados uma única vez; `data/raw/` inteiro está no .gitignore.
DIR_CNEFE = RAW_DIR / "cnefe"

#: Timeout (segundos) do download de um ZIP do CNEFE. Os arquivos vão de 7 MB
#: (AC) a 1,08 GB (SP), e a ~2,4 MB/s medidos o maior leva ~7,5 min — o valor
#: abaixo cobre uma conexão bem mais lenta antes de desistir.
TIMEOUT_CNEFE = 1800

#: Quantas vezes um download do CNEFE é tentado antes de a etapa desistir.
#:
#: O FTP do IBGE derruba a conexão no meio de um arquivo com alguma frequência
#: (``IncompleteRead``), e num recorte nacional são 27 downloads seguidos: sem
#: retentativa, uma queda em qualquer um deles derruba um pipeline de dezenas
#: de minutos, e a execução seguinte refaz a varredura inteira do que já estava
#: em cache. Quatro tentativas cobrem a instabilidade passageira sem insistir
#: contra um servidor que está de fato fora.
TENTATIVAS_CNEFE = 4

#: Segundos de espera antes da 2ª tentativa; dobra a cada uma seguinte.
ESPERA_CNEFE = 5.0

# O destino dos pontos geocodificados é derivado do recorte — ver
# `arquivo_pontos_geocodificados`.

# --------------------------------------------------------------------------- #
# Malha territorial e agregação por município
# --------------------------------------------------------------------------- #
#
# Os dois caminhos desta etapa também são derivados do recorte: ver
# `arquivo_malha` e `arquivo_agregado_municipio`.

# --------------------------------------------------------------------------- #
# Mapa
# --------------------------------------------------------------------------- #

#: Espaço, em pixels, que o cartão do mapa ocupa numa janela típica.
#:
#: É o orçamento contra o qual `zoom_da_caixa` decide o zoom de abertura. Não
#: precisa ser exato: ele só separa um zoom do seguinte, e cada passo de zoom
#: DOBRA o tamanho aparente, então qualquer valor entre ~580 e ~1.150 px de
#: altura escolhe o mesmo zoom 6 para a Região Sul.
LARGURA_UTIL_MAPA_PX = 1100
ALTURA_UTIL_MAPA_PX = 700

#: Lado do bloco de ladrilhos do Leaflet, em pixels. No zoom `z` o mundo inteiro
#: (360° de longitude) cabe em ``2**z`` blocos desses.
LADO_LADRILHO_PX = 256

#: Retângulo envolvente do Brasil, no formato ``[[sul, oeste], [norte, leste]]``.
#:
#: Enquadramento de partida de quem precisa de um mapa ANTES de haver malha
#: carregada — hoje só o andaime `src.mapping`. O pipeline não o usa: lá o
#: enquadramento sai da geometria de fato do recorte (`mapa.enquadramento_inicial`).
CAIXA_BRASIL = [[-33.75, -73.99], [5.27, -28.85]]


#: Piso e teto do zoom de abertura.
#:
#: O piso é o mundo inteiro; o teto existe para que um recorte de um município
#: só não abra colado no telhado das casas. Nenhum dos dois é alcançado pelos
#: recortes reais do projeto (a UF menor, o DF, dá zoom 9).
ZOOM_MINIMO_ENQUADRAMENTO = 2
ZOOM_MAXIMO_ENQUADRAMENTO = 12

#: Piso de amplitude, em graus, para não dividir por zero num recorte de um
#: ponto só (um único município degenerado, ou uma malha vazia).
_GRAUS_MINIMOS = 0.05


def centro_da_caixa(caixa: list[list[float]]) -> tuple[float, float]:
    """Centro de um retângulo envolvente, como ``(latitude, longitude)``.

    Não é o centroide populacional nem o geográfico do recorte — é o ponto que
    deixa o retângulo visualmente centralizado, que é o que importa no
    enquadramento de abertura. Os dois decimais são a precisão em que 1° vale
    ~1 km: mais casas não mudam nada na tela e só sujam o resumo da execução.

    Args:
        caixa: ``[[sul, oeste], [norte, leste]]``, em graus decimais.

    Returns:
        ``(lat, lon)`` do centro, arredondado a duas casas.
    """
    (sul, oeste), (norte, leste) = caixa
    return (round((sul + norte) / 2, 2), round((oeste + leste) / 2, 2))


def zoom_da_caixa(
    caixa: list[list[float]],
    largura_px: int = LARGURA_UTIL_MAPA_PX,
    altura_px: int = ALTURA_UTIL_MAPA_PX,
) -> int:
    """Maior zoom do Leaflet em que o retângulo inteiro ainda cabe na tela.

    O cálculo é o que os comentários do projeto sempre descreveram à mão, agora
    aplicado ao recorte carregado em vez de a uma constante:

    1. no zoom ``z``, um bloco de `LADO_LADRILHO_PX` cobre ``360 / 2**z`` graus;
    2. em Web Mercator a altura é esticada por ``1 / cos(latitude)``, então o
       recorte "pesa" mais em graus verticais do que os que ele mede — a
       correção é feita na latitude do centro, onde a distorção é a média;
    3. o zoom escolhido é o maior em que largura E altura cabem no orçamento.

    Conferência da Região Sul, o recorte padrão: 9,6° de longitude por 11,2° de
    latitude, esticados a ~12,7° verticais na latitude de -28°. No zoom 6
    (5,625° por bloco) isso dá ~580 px de altura, que cabe; no zoom 7 passaria
    de 1.150 px e o mapa abriria com RS e PR cortados. Daí 6, e não 7 — o mesmo
    valor que a constante `ZOOM_INICIAL` trazia fixo.

    Args:
        caixa: ``[[sul, oeste], [norte, leste]]``, em graus decimais.
        largura_px: espaço horizontal disponível.
        altura_px: espaço vertical disponível.

    Returns:
        Um zoom entre `ZOOM_MINIMO_ENQUADRAMENTO` e `ZOOM_MAXIMO_ENQUADRAMENTO`.
    """
    (sul, oeste), (norte, leste) = caixa

    graus_horizontais = max(abs(leste - oeste), _GRAUS_MINIMOS)
    # A latitude do centro, e não a do extremo: usar o extremo superestimaria a
    # distorção do recorte inteiro pelo pedaço mais distorcido dele.
    lat_central = math.radians(max(min((sul + norte) / 2, 85.0), -85.0))
    graus_verticais = max(abs(norte - sul) / math.cos(lat_central), _GRAUS_MINIMOS)

    melhor = ZOOM_MINIMO_ENQUADRAMENTO
    for zoom in range(ZOOM_MINIMO_ENQUADRAMENTO, ZOOM_MAXIMO_ENQUADRAMENTO + 1):
        graus_por_bloco = 360.0 / (2**zoom)
        cabe = (
            graus_horizontais / graus_por_bloco * LADO_LADRILHO_PX <= largura_px
            and graus_verticais / graus_por_bloco * LADO_LADRILHO_PX <= altura_px
        )
        if not cabe:
            break
        melhor = zoom
    return melhor


#: Nome da camada base, para log e para o rótulo interno da camada.
#:
#: Positron é um basemap claro e de baixo contraste, escolhido porque o mapa
#: principal é coroplético: com o OpenStreetMap padrão, o colorido das ruas e do
#: uso do solo compete com a escala de cores dos municípios.
TILES_PADRAO = "CartoDB positron"

#: Chave de API dos basemaps da CARTO.
#:
#: A CARTO passou a exigir chave nos ladrilhos raster: sem ela o servidor
#: devolve a tile com a marca d'água "API KEY REQUIRED" carimbada por cima
#: (não é erro HTTP — a tile vem 200, só que suja). A chave é gratuita, pedida
#: em https://carto.com/basemaps/apikey, e cobre 5 milhões de tiles por mês.
#:
#: Ela vive no código porque é uma chave de *cliente*: o mapa é um HTML
#: estático servido no GitHub Pages, e a URL do ladrilho — chave inclusa — é
#: necessariamente visível para quem abrir a página. Não há como escondê-la
#: sem um proxy próprio. Ainda assim o valor pode ser trocado pela variável de
#: ambiente CARTO_API_KEY, para gerar uma versão do mapa com outra chave sem
#: editar o arquivo. Definir a variável como vazia derruba o parâmetro e o
#: mapa volta a sair com marca d'água.
CARTO_API_KEY = os.environ.get(
    "CARTO_API_KEY", "cb1_3455_1_404241543fec4488f0ff11c8"
)

#: Template da URL dos ladrilhos, no formato que o Leaflet interpola.
#:
#: `{s}` é o subdomínio (ver SUBDOMINIOS_TILES), `{z}/{x}/{y}` o endereço do
#: ladrilho e `{r}` o sufixo de tela retina ("@2x" ou vazio) — todos resolvidos
#: pelo Leaflet no navegador, e por isso escritos literalmente, sem f-string.
#: O parâmetro é `key=`, NÃO `api_key=`: o CDN ignora nomes desconhecidos em
#: silêncio, devolvendo a tile carimbada com HTTP 200, então errar o nome do
#: parâmetro não dá erro nenhum — só não tira a marca d'água.
URL_TILES_PADRAO = (
    "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
    + (f"?key={CARTO_API_KEY}" if CARTO_API_KEY else "")
)

#: Subdomínios do CDN da CARTO. São quatro (a-d), e não os três do padrão do
#: folium, o que dá ao navegador mais conexões paralelas para os ladrilhos.
SUBDOMINIOS_TILES = "abcd"

#: Zoom máximo servido pelo basemap raster da CARTO.
ZOOM_MAXIMO_TILES = 20

#: Crédito exibido no canto do mapa.
#:
#: Manter OpenStreetMap e CARTO visíveis é condição do uso gratuito dos
#: basemaps — é o que a CARTO pede em troca da chave. Não remover.
ATRIBUICAO_TILES = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap'
    '</a> contributors &copy; <a href="https://carto.com/attributions">CARTO'
    "</a>"
)

#: Destino do mapa interativo gerado por `src.mapa`.
ARQUIVO_MAPA = OUTPUT_DIR / "mapa_if_sul.html"

#: Cache das bibliotecas JS/CSS que o folium referencia por CDN.
#:
#: Elas são embutidas no HTML por `src.embutir` para que o mapa funcione em
#: rede que bloqueie CDN e também sem internet nenhuma. São ~700 KB em 14
#: arquivos de versão fixa (a versão está na própria URL), baixados uma vez.
DIR_LIBS = RAW_DIR / "libs"

# --------------------------------------------------------------------------- #
# Recorte de instituições
# --------------------------------------------------------------------------- #

#: Nomes EXATOS da coluna "NOME INSTITUIÇÃO" dos cinco bancos-alvo.
#:
#: O match é feito por igualdade exata (após `strip()` e colapso de espaços
#: internos), NUNCA por `contains`. Isso é deliberado: um `contains("BRADESCO")`
#: capturaria "BANCO BRADESCO BBI S.A." e "BANCO BRADESCO FINANCIAMENTOS S.A.",
#: e um `contains("ITAÚ")` capturaria "ITAÚ UNIBANCO HOLDING S.A.", que não são
#: rede de atendimento bancário de varejo.
#:
#: Atenção à grafia da fonte: "ITAÚ UNIBANCO S.A." leva acento, mas
#: "CAIXA ECONOMICA FEDERAL" NÃO leva acento em "ECONOMICA" — os valores abaixo
#: reproduzem literalmente o que está na planilha do BACEN.
#:
#: DECISÃO (safra 202608): "ITAÚ UNIBANCO HOLDING S.A." fica DE FORA. Ela tem
#: 2 pontos próprios no Sul (2 postos de atendimento, nenhuma agência), mas não
#: é rede de varejo; a entidade operacional é "ITAÚ UNIBANCO S.A.", com 493
#: pontos. O diagnóstico que embasou a decisão continua rodando a cada execução
#: do ETL (ver `etl_bacen.diagnosticar_itau`), para reavaliação em safras futuras.
BANCOS_ALVO = [
    "BANCO DO BRASIL S.A.",
    "BANCO BRADESCO S.A.",
    "ITAÚ UNIBANCO S.A.",
    "CAIXA ECONOMICA FEDERAL",
    "BANCO SANTANDER (BRASIL) S.A.",
]

#: Valor exato da coluna "SEGMENTO" que identifica cooperativas de crédito.
#: Todas as linhas com este segmento são mantidas, independentemente da
#: bandeira/sistema (Sicredi, Sicoob, Cresol, Unicred, Ailos, independentes...).
SEGMENTO_COOPERATIVA = "Cooperativa de Crédito"

# --------------------------------------------------------------------------- #
# Sistema Ailos — filiação por CNPJ
# --------------------------------------------------------------------------- #

#: CNPJ da matriz de cada cooperativa filiada ao Sistema Ailos -> nome comercial.
#:
#: Por que uma lista de CNPJ e não uma regra textual: o Ailos NÃO assina o
#: próprio nome nas razões sociais publicadas pelo BACEN — cada filiada aparece
#: com marca própria ("... - VIACREDI", "... - TRANSPOCRED", "... - ÚNILOS").
#: Nenhuma linha da base contém a string "AILOS", então só é possível
#: identificar o sistema por filiação declarada, nunca inferindo do nome.
#:
#: O casamento é feito pela RAIZ do CNPJ (os 8 primeiros dígitos), porque as
#: planilhas do BACEN publicam apenas a raiz na coluna CNPJ (ex.: "82.639.451").
#: Assim a filial informada abaixo para a Viacredi Alto Vale (/0002-33) casa
#: normalmente com as linhas dela na base.
#:
#: Fonte: relação de filiadas fornecida pelo Ailos (Cooperativa Central Ailos).
#: Duas entradas não produzem linhas no recorte RS/SC/PR e isso é esperado:
#: a Cooperativa Central Ailos (05.463.212) não opera rede de atendimento
#: própria, e a Credisan (62.109.566) é sediada em São João da Boa Vista/SP.
CNPJS_AILOS = {
    "05.463.212/0001-29": "Cooperativa Central Ailos",
    "03.427.097/0001-01": "Acentra",
    "03.461.243/0001-15": "Acredicoop",
    "10.218.474/0001-68": "Civia",
    "05.979.692/0001-85": "Credcrea",
    "08.850.613/0001-20": "Credelesc",
    "09.590.601/0001-76": "Credicomin",
    "09.512.539/0001-02": "Credifoz",
    "62.109.566/0001-03": "Credisan",
    "10.143.743/0001-74": "Crevisc",
    "10.311.218/0001-10": "Evolua",
    "08.075.352/0001-18": "Transpocred",
    "02.405.189/0001-28": "Únilos",
    "82.639.451/0001-38": "Viacredi",
    "16.779.741/0002-33": "Viacredi Alto Vale",
}
