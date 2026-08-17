"""Constantes de configuração do projeto mapa-if-sul.

Centraliza caminhos de diretórios e as regras de recorte do dataset
(estados-alvo, instituições-alvo e segmento de cooperativas).
"""

from pathlib import Path

# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #

# BASE_DIR aponta para a raiz do projeto (pasta "mapa-if-sul"), pois este
# arquivo vive em mapa-if-sul/src/config.py.
BASE_DIR = Path(__file__).resolve().parent.parent

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"

# Sistema de referência geográfico padrão (lat/lon em graus decimais).
CRS_GEOGRAFICO = "EPSG:4326"

# --------------------------------------------------------------------------- #
# Arquivos brutos do BACEN (posição: 30.6.2026)
# --------------------------------------------------------------------------- #

ARQUIVO_AGENCIAS = RAW_DIR / "202606AGENCIAS.xlsx"
ARQUIVO_POSTOS = RAW_DIR / "202606POSTOS.xlsx"

# Nas duas planilhas as linhas 1-9 (1-based) são cabeçalho institucional do
# BACEN; o cabeçalho real das colunas está na linha 10, ou seja, índice 9
# zero-based — que é exatamente o valor esperado por `pandas.read_excel(header=)`.
LINHA_CABECALHO_BACEN = 9

# Destino do dataset categorizado.
ARQUIVO_IF_SUL_CATEGORIZADO = PROCESSED_DIR / "if_sul_categorizado.parquet"

# --------------------------------------------------------------------------- #
# Recorte territorial
# --------------------------------------------------------------------------- #

#: Siglas das UFs da Região Sul mantidas no dataset.
SIGLAS_SUL = ["RS", "SC", "PR"]

#: Código IBGE de cada UF do Sul. São os dois primeiros dígitos do código de
#: município (ex.: 4314902 = Porto Alegre, UF 43 = RS), o que permite derivar a
#: UF de qualquer feição da malha sem consultar a API de Localidades.
CODIGO_UF_SUL = {"PR": 41, "SC": 42, "RS": 43}

#: Quantidade oficial de municípios por UF (divisão territorial vigente).
#: Usado apenas como conferência do que a API de Malhas devolve — se o total
#: divergir, a malha baixada está incompleta e o mapa sairia com buracos.
MUNICIPIOS_POR_UF_SUL = {"PR": 399, "SC": 295, "RS": 497}

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
# Malha territorial e agregação por município
# --------------------------------------------------------------------------- #

ARQUIVO_MALHA_SUL = RAW_DIR / "malha_municipios_sul.geojson"
ARQUIVO_AGREGADO_MUNICIPIO = PROCESSED_DIR / "agregado_municipio.parquet"

# --------------------------------------------------------------------------- #
# Mapa
# --------------------------------------------------------------------------- #

#: Centro inicial do mapa, como (latitude, longitude).
#:
#: É o centro da *bounding box* da malha dos 1.191 municípios do Sul, medida em
#: EPSG:4326 sobre `ARQUIVO_AGREGADO_MUNICIPIO`: lon -57,65..-48,02 e
#: lat -33,75..-22,52. Não é o centroide populacional nem geográfico da região —
#: é o ponto que deixa o retângulo do recorte visualmente centralizado, que é o
#: que importa no enquadramento inicial.
CENTRO_MAPA = (-28.13, -52.84)

#: Zoom inicial do Leaflet/folium.
#:
#: A região ocupa ~9,6° de longitude por ~11,2° de latitude. Em Web Mercator na
#: latitude de -28° a distorção estica a altura em ~1/cos(28°) ≈ 1,13, então o
#: recorte equivale a ~12,7° verticais — o lado que limita o enquadramento.
#: No zoom 6 (5,625° por bloco de 256 px) isso dá ~580 px de altura, que cabe em
#: uma janela de navegador típica; no zoom 7 passaria de 1.150 px e o mapa
#: abriria com RS e PR cortados. Daí 6, e não 7.
ZOOM_INICIAL = 6

#: Camada base padrão.
#:
#: Positron é um basemap claro e de baixo contraste, escolhido porque o mapa
#: principal é coroplético: com o OpenStreetMap padrão, o colorido das ruas e do
#: uso do solo compete com a escala de cores dos municípios. Aceita qualquer
#: alias reconhecido pelo folium (ex.: "OpenStreetMap", "CartoDB dark_matter").
TILES_PADRAO = "CartoDB positron"

#: Destino do mapa interativo gerado por `src.mapa`.
ARQUIVO_MAPA = OUTPUT_DIR / "mapa_if_sul.html"

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
#: DECISÃO (safra 202606): "ITAÚ UNIBANCO HOLDING S.A." fica DE FORA. Ela tem
#: 2 pontos próprios no Sul (2 postos de atendimento, nenhuma agência), mas não
#: é rede de varejo; a entidade operacional é "ITAÚ UNIBANCO S.A.", com 495
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
