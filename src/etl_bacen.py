"""ETL dos cadastros de atendimento do BACEN para a Região Sul.

Lê as duas planilhas publicadas pelo Banco Central (posição 30.6.2026) —
agências e postos de atendimento —, padroniza as duas em um esquema comum,
recorta para RS/SC/PR, mantém apenas cooperativas de crédito e os cinco
bancos-alvo, e classifica cada ponto em `categoria_if` / `sub_categoria`.

Uso (a partir da raiz do projeto, com o venv ativo)::

    python -m src.etl_bacen

Saída: ``data/processed/if_sul_categorizado.parquet``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from src import config

# --------------------------------------------------------------------------- #
# Esquema comum de saída
# --------------------------------------------------------------------------- #

#: Colunas do esquema padronizado, na ordem em que aparecem no dataset final.
COLUNAS_ESQUEMA_COMUM = [
    "cnpj",
    "nome_instituicao",
    "segmento",
    "nome_instalacao",
    "endereco",
    "numero",
    "bairro",
    "cep",
    "municipio",
    "uf",
    "municipio_ibge",
    "tipo_instalacao",
    "fonte_arquivo",
]

#: Colunas cujo conteúdo é texto e passa por `strip()` + colapso de espaços.
#: O BACEN publica os campos com padding de espaços à direita (ex.:
#: "BANCO DO BRASIL S.A.                    "), tanto nos nomes das colunas
#: quanto nos valores.
COLUNAS_TEXTO = [
    "cnpj",
    "nome_instituicao",
    "segmento",
    "nome_instalacao",
    "endereco",
    "numero",
    "bairro",
    "cep",
    "municipio",
    "uf",
]

#: Colunas do endereço que existem nas duas planilhas e são carregadas para o
#: dataset final com um único propósito: alimentar a geocodificação de
#: `src.cnefe`.
#:
#: `endereco` sozinho não basta para localizar o ponto. A fonte publica o
#: logradouro abreviado e sem separador ("PCA.TIRADENTES,410"), e o que salva o
#: casamento com o CNEFE do IBGE são os três campos ao lado:
#:
#: * `cep` — preenchido em 100% das linhas da safra 202606, e a chave mais
#:   confiável que existe aqui porque não depende de casar texto. Atenção: em
#:   ~58% das linhas é o CEP geral do município (terminado em ``-000``), que
#:   não identifica logradouro — `src.cnefe` trata os dois casos em níveis de
#:   precisão diferentes;
#: * `numero` — o número do imóvel; vem em coluna própria em 89% dos postos,
#:   mas em só 34% das agências, onde costuma estar embutido no `endereco`
#:   depois da vírgula. A extração de um a partir do outro é feita na
#:   geocodificação, não aqui, para que este módulo continue publicando o que a
#:   fonte publica;
#: * `bairro` — 98% preenchido; não entra no casamento hoje, e é carregado por
#:   ser o desempate óbvio caso uma safra futura precise dele.
COLUNAS_ENDERECO_BACEN = ["endereco", "numero", "bairro", "cep"]

# Rótulos de `tipo_instalacao`, definidos pela planilha de origem.
TIPO_AGENCIA = "Agência"
TIPO_POSTO = "Posto de Atendimento"

# Rótulos de `categoria_if` — o dataset final admite apenas estes dois valores.
CATEGORIA_COOPERATIVA = "Cooperativa de Crédito"
CATEGORIA_BANCO = "Banco"

# --------------------------------------------------------------------------- #
# Mapeamento das colunas de origem -> esquema comum
# --------------------------------------------------------------------------- #
#
# Cada entrada lista os nomes aceitos na planilha de origem, em ordem de
# preferência. A busca é feita de forma tolerante a acentos, caixa e espaços
# (ver `_resolver_coluna`), o que é necessário porque as duas planilhas NÃO
# usam a mesma grafia:
#   - AGENCIAS traz "MUNICíPIO" (com "í" minúsculo, grafia da própria fonte);
#   - POSTOS  traz "MUNICIPIO" (sem acento).
# O nome da instalação também muda: "NOME AGÊNCIA" vs. "NOME INSTALAÇÃO".

MAPA_COLUNAS_AGENCIAS = {
    "cnpj": ["CNPJ"],
    "nome_instituicao": ["NOME INSTITUIÇÃO"],
    "segmento": ["SEGMENTO"],
    "nome_instalacao": ["NOME AGÊNCIA"],
    "endereco": ["ENDEREÇO"],
    "numero": ["NÚMERO", "NUMERO"],
    "bairro": ["BAIRRO"],
    "cep": ["CEP"],
    "municipio": ["MUNICÍPIO", "MUNICIPIO"],
    "uf": ["UF"],
    "municipio_ibge": ["MUNICIPIO IBGE", "MUNICÍPIO IBGE"],
}

MAPA_COLUNAS_POSTOS = {
    "cnpj": ["CNPJ"],
    "nome_instituicao": ["NOME INSTITUIÇÃO"],
    "segmento": ["SEGMENTO"],
    "nome_instalacao": ["NOME INSTALAÇÃO"],
    "endereco": ["ENDEREÇO"],
    "numero": ["NÚMERO", "NUMERO"],
    "bairro": ["BAIRRO"],
    "cep": ["CEP"],
    "municipio": ["MUNICIPIO", "MUNICÍPIO"],
    "uf": ["UF"],
    "municipio_ibge": ["MUNICIPIO IBGE", "MUNICÍPIO IBGE"],
}

# --------------------------------------------------------------------------- #
# Regras de sub_categoria
# --------------------------------------------------------------------------- #

#: Bancos-alvo -> nome comercial usado em `sub_categoria`.
#: As chaves são os nomes EXATOS da fonte (mesmos de `config.BANCOS_ALVO`);
#: não há inferência textual aqui, é um de-para fechado.
NOME_COMERCIAL_BANCO = {
    "BANCO DO BRASIL S.A.": "Banco do Brasil",
    "BANCO BRADESCO S.A.": "Bradesco",
    "ITAÚ UNIBANCO S.A.": "Itaú",
    "CAIXA ECONOMICA FEDERAL": "Caixa",
    "BANCO SANTANDER (BRASIL) S.A.": "Santander",
}

#: Rótulo das cooperativas cuja bandeira não é reconhecida por nenhuma regra.
SUB_CATEGORIA_COOP_INDEFINIDA = "Outra Cooperativa"

#: ETAPA 1 das regras de bandeira: filiação por RAIZ DE CNPJ.
#:
#: Avaliada ANTES das regras textuais, porque CNPJ é critério declarado e
#: não depende de a marca estar escrita na razão social. Hoje só o Ailos usa
#: esse mecanismo (ver `config.CNPJS_AILOS` para o porquê); a estrutura é uma
#: lista para permitir acrescentar outros sistemas com o mesmo tratamento.
REGRAS_BANDEIRA_POR_CNPJ = [
    ("Ailos", config.CNPJS_AILOS),
]

#: ETAPA 2 das regras de bandeira: marca escrita no nome, avaliadas NA ORDEM
#: e com "primeira que casar vence".
#:
#: Como funciona: o padrão é aplicado sobre `nome_instituicao` depois de
#: maiúsculas + remoção de acentos (ver `_dobrar_acentos`), de modo que
#: "CRÉDITO"/"CREDITO" e "AÇU"/"ACU" não interferem. `\b` garante que o token
#: da marca apareça como palavra inteira: "UNICRED" casa em
#: "COOPERATIVA DE CRÉDITO UNICRED UNIÃO LTDA", mas não casaria dentro de uma
#: palavra maior. `\b` também resolve as grafias com barra, como
#: "SULCREDI/CREDILUZ" e "SULCREDI/IBIAM", já que "/" não é caractere de palavra.
#:
#: O critério aqui é PURAMENTE textual: a marca precisa estar escrita na razão
#: social/nome de fantasia publicado pelo BACEN. Não há inferência a partir de
#: conhecimento externo — quando o nome não traz a marca e o CNPJ não está em
#: nenhuma lista de filiação, a linha cai em `SUB_CATEGORIA_COOP_INDEFINIDA` em
#: vez de ser adivinhada.
#:
#: Verificado na safra 202606 (RS/SC/PR): estes sete padrões não se sobrepõem —
#: nenhuma razão social casa dois deles ao mesmo tempo —, portanto a ordem
#: abaixo não altera o resultado. Ela é mantida explícita para que a
#: precedência siga determinística caso surjam nomes ambíguos em safras futuras.
REGRAS_BANDEIRA_COOPERATIVA = [
    ("Sicredi", r"\bSICREDI\b"),
    ("Sicoob", r"\bSICOOB\b"),
    ("Cresol", r"\bCRESOL\b"),
    ("Unicred", r"\bUNICRED\b"),
    ("Uniprime", r"\bUNIPRIME\b"),
    ("Sulcredi", r"\bSULCREDI\b"),
    ("Credicoamo", r"\bCREDICOAMO\b"),
    # Fallback do Ailos: nenhuma linha da safra 202606 traz "AILOS" escrito,
    # mas a regra fica aqui para capturar a Central caso ela venha a operar
    # pontos próprios sem constar em CNPJS_AILOS.
    ("Ailos", r"\bAILOS\b"),
]


# --------------------------------------------------------------------------- #
# Helpers de normalização de texto
# --------------------------------------------------------------------------- #


def _normalizar_espacos(valor: str) -> str:
    """Remove espaços das bordas e colapsa espaços internos repetidos.

    Args:
        valor: texto cru vindo da planilha.

    Returns:
        Texto com `strip()` aplicado e sequências de espaços em branco
        reduzidas a um único espaço. Ex.: ``"NOME INSTITUIÇÃO   "`` ->
        ``"NOME INSTITUIÇÃO"``; ``"COOPERATIVA   DE   CRÉDITO"`` ->
        ``"COOPERATIVA DE CRÉDITO"``.
    """
    return re.sub(r"\s+", " ", str(valor)).strip()


def _normalizar_serie_texto(serie: pd.Series) -> pd.Series:
    """Aplica `_normalizar_espacos` a uma Series, preservando valores nulos.

    Args:
        serie: coluna de texto do DataFrame.

    Returns:
        Series de dtype ``string`` com espaços normalizados; posições nulas
        continuam nulas (não se tornam string vazia).
    """
    return (
        serie.astype("string")
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def _dobrar_acentos(serie: pd.Series) -> pd.Series:
    """Devolve a Series em maiúsculas e sem acentos, para casamento de padrões.

    Usa decomposição Unicode NFKD e descarta as marcas combinantes, de forma
    que "CRÉDITO" e "CREDITO" (ambas grafias ocorrem na base do BACEN) fiquem
    idênticas.

    Args:
        serie: coluna de texto.

    Returns:
        Series de dtype ``string``, em caixa alta e sem diacríticos.
    """

    def _dobrar(valor: object) -> object:
        if pd.isna(valor):
            return valor
        decomposto = unicodedata.normalize("NFKD", str(valor))
        return "".join(c for c in decomposto if not unicodedata.combining(c)).upper()

    return serie.map(_dobrar).astype("string")


def _raiz_cnpj(serie: pd.Series) -> pd.Series:
    """Extrai a raiz do CNPJ (os 8 primeiros dígitos) de uma Series.

    Descarta qualquer formatação (pontos, barra, hífen) e ignora filial e
    dígito verificador. É o denominador comum entre a coluna CNPJ das planilhas
    do BACEN, que publica só a raiz (``"82.639.451"``), e as listas de filiação
    informadas com o CNPJ completo (``"82.639.451/0001-38"``).

    Args:
        serie: coluna com CNPJ em qualquer formatação.

    Returns:
        Series de dtype ``string`` com 8 dígitos; nulo onde a origem é nula ou
        não tem dígitos suficientes.
    """
    digitos = serie.astype("string").str.replace(r"\D", "", regex=True)
    raiz = digitos.str.slice(0, 8)
    return raiz.where(raiz.str.len() == 8, pd.NA)


def _resolver_coluna(colunas: list[str], candidatos: list[str]) -> str:
    """Localiza, entre as colunas do DataFrame, a primeira que casa um candidato.

    O casamento ignora caixa, acentos e espaços extras, porque as planilhas do
    BACEN variam a grafia dos rótulos entre si (ex.: "MUNICíPIO" vs.
    "MUNICIPIO").

    Args:
        colunas: nomes de coluna já presentes no DataFrame.
        candidatos: nomes aceitos, em ordem de preferência.

    Returns:
        O nome real da coluna encontrada no DataFrame.

    Raises:
        KeyError: se nenhum candidato existir no DataFrame.
    """

    def _chave(texto: str) -> str:
        decomposto = unicodedata.normalize("NFKD", _normalizar_espacos(texto))
        return "".join(c for c in decomposto if not unicodedata.combining(c)).upper()

    indice = {_chave(coluna): coluna for coluna in colunas}
    for candidato in candidatos:
        encontrada = indice.get(_chave(candidato))
        if encontrada is not None:
            return encontrada
    raise KeyError(
        f"Nenhuma das colunas {candidatos!r} foi encontrada. "
        f"Colunas disponíveis: {sorted(colunas)!r}"
    )


# --------------------------------------------------------------------------- #
# 1. Leitura
# --------------------------------------------------------------------------- #


def ler_planilha_bacen(
    caminho: Path, linha_cabecalho: int = config.LINHA_CABECALHO_BACEN
) -> pd.DataFrame:
    """Lê uma planilha do BACEN pulando o cabeçalho institucional.

    As duas planilhas trazem, nas primeiras linhas, o cabeçalho institucional
    (BACEN / DESIG / DIACO, título do relatório e a data de posição). O
    cabeçalho real das colunas está na linha 10 (índice 9, zero-based) e os
    dados começam na linha 11.

    Todos os campos são lidos como texto (``dtype=str``) para não perder zeros
    à esquerda de CNPJ, CEP e do código IBGE do município. Os nomes das colunas
    chegam com padding de espaços e são normalizados aqui.

    Args:
        caminho: caminho do arquivo ``.xlsx``.
        linha_cabecalho: índice zero-based da linha de cabeçalho das colunas.

    Returns:
        DataFrame cru, com os nomes de coluna já sem padding.

    Raises:
        FileNotFoundError: se o arquivo não existir em ``data/raw/``.
    """
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}. "
            "Baixe as planilhas do BACEN para data/raw/."
        )

    df = pd.read_excel(caminho, header=linha_cabecalho, dtype=str)
    # "NOME INSTITUIÇÃO                    " -> "NOME INSTITUIÇÃO"
    df.columns = [_normalizar_espacos(coluna) for coluna in df.columns]
    return df


# --------------------------------------------------------------------------- #
# 2. Padronização no esquema comum
# --------------------------------------------------------------------------- #


def padronizar_esquema(
    df: pd.DataFrame,
    mapa_colunas: dict[str, list[str]],
    tipo_instalacao: str,
    fonte_arquivo: str,
) -> pd.DataFrame:
    """Reduz uma planilha do BACEN ao esquema comum do projeto.

    Seleciona e renomeia as colunas de interesse, normaliza os espaços dos
    campos de texto e acrescenta as duas colunas de procedência
    (`tipo_instalacao` e `fonte_arquivo`). Linhas sem UF são descartadas —
    são as linhas de rodapé/notas que o BACEN deixa ao final da planilha.

    Args:
        df: DataFrame cru devolvido por `ler_planilha_bacen`.
        mapa_colunas: de-para ``coluna_destino -> [nomes aceitos na origem]``.
        tipo_instalacao: ``"Agência"`` ou ``"Posto de Atendimento"``.
        fonte_arquivo: nome do arquivo de origem, para rastreabilidade.

    Returns:
        DataFrame com exatamente as colunas de `COLUNAS_ESQUEMA_COMUM`.
    """
    colunas_origem = list(df.columns)
    renomeio = {
        _resolver_coluna(colunas_origem, candidatos): destino
        for destino, candidatos in mapa_colunas.items()
    }

    padronizado = df[list(renomeio)].rename(columns=renomeio).copy()

    for coluna in COLUNAS_TEXTO:
        padronizado[coluna] = _normalizar_serie_texto(padronizado[coluna])

    padronizado["municipio_ibge"] = _normalizar_serie_texto(
        padronizado["municipio_ibge"]
    )
    # Cast explícito para manter todas as colunas do esquema com dtype "string"
    # (uma atribuição escalar produziria dtype "str" e deixaria o Parquet
    # com tipos mistos entre colunas de texto).
    padronizado["tipo_instalacao"] = pd.Series(
        tipo_instalacao, index=padronizado.index, dtype="string"
    )
    padronizado["fonte_arquivo"] = pd.Series(
        fonte_arquivo, index=padronizado.index, dtype="string"
    )

    # Rodapé da planilha: linhas sem UF não são pontos de atendimento.
    padronizado = padronizado[padronizado["uf"].notna()]

    return padronizado[COLUNAS_ESQUEMA_COMUM].reset_index(drop=True)


def carregar_agencias() -> pd.DataFrame:
    """Carrega a planilha de agências já no esquema comum.

    Returns:
        DataFrame de agências com `tipo_instalacao == "Agência"`.
    """
    df = ler_planilha_bacen(config.ARQUIVO_AGENCIAS)
    return padronizar_esquema(
        df,
        MAPA_COLUNAS_AGENCIAS,
        tipo_instalacao=TIPO_AGENCIA,
        fonte_arquivo=config.ARQUIVO_AGENCIAS.name,
    )


def carregar_postos() -> pd.DataFrame:
    """Carrega a planilha de postos de atendimento já no esquema comum.

    Returns:
        DataFrame de postos com `tipo_instalacao == "Posto de Atendimento"`.
    """
    df = ler_planilha_bacen(config.ARQUIVO_POSTOS)
    return padronizar_esquema(
        df,
        MAPA_COLUNAS_POSTOS,
        tipo_instalacao=TIPO_POSTO,
        fonte_arquivo=config.ARQUIVO_POSTOS.name,
    )


# --------------------------------------------------------------------------- #
# 3. Concatenação
# --------------------------------------------------------------------------- #


def combinar_bases(agencias: pd.DataFrame, postos: pd.DataFrame) -> pd.DataFrame:
    """Empilha agências e postos em um único DataFrame.

    Args:
        agencias: saída de `carregar_agencias`.
        postos: saída de `carregar_postos`.

    Returns:
        DataFrame único; a origem de cada linha permanece identificável por
        `tipo_instalacao` e `fonte_arquivo`.
    """
    return pd.concat([agencias, postos], ignore_index=True)


# --------------------------------------------------------------------------- #
# 4. Recorte territorial
# --------------------------------------------------------------------------- #


def filtrar_sul(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém apenas as linhas cuja UF está em `config.SIGLAS_SUL`.

    Args:
        df: base combinada nacional.

    Returns:
        DataFrame restrito a RS, SC e PR.
    """
    return df[df["uf"].isin(config.SIGLAS_SUL)].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 6. Diagnóstico Itaú Unibanco vs. Itaú Unibanco Holding
# --------------------------------------------------------------------------- #


def diagnosticar_itau(df: pd.DataFrame) -> pd.DataFrame:
    """Imprime a contagem de linhas de "ITAÚ UNIBANCO S.A." vs. a Holding.

    Roda ANTES do filtro de instituições, sobre a base combinada RS/SC/PR, para
    permitir decidir se "ITAÚ UNIBANCO HOLDING S.A." tem pontos de atendimento
    próprios e deveria entrar em `config.BANCOS_ALVO`.

    Args:
        df: base combinada já restrita a RS/SC/PR.

    Returns:
        DataFrame com a contagem por nome de instituição e `tipo_instalacao`,
        para inspeção programática além do print.
    """
    nomes = ["ITAÚ UNIBANCO S.A.", "ITAÚ UNIBANCO HOLDING S.A."]
    recorte = df[df["nome_instituicao"].isin(nomes)]

    contagem = (
        recorte.groupby(["nome_instituicao", "tipo_instalacao"], dropna=False)
        .size()
        .rename("linhas")
        .reset_index()
    )

    print("=" * 78)
    print("DIAGNÓSTICO — Itaú: entidade operacional vs. holding (base RS/SC/PR)")
    print("=" * 78)
    for nome in nomes:
        total = int((recorte["nome_instituicao"] == nome).sum())
        print(f"  {nome:<32} {total:>6} linha(s)")
        detalhe = contagem[contagem["nome_instituicao"] == nome]
        for _, linha in detalhe.iterrows():
            print(f"      - {linha['tipo_instalacao']:<24} {int(linha['linhas']):>6}")
    print(
        "\n  DECISÃO (safra 202606): a HOLDING fica FORA do dataset — apenas\n"
        "  'ITAÚ UNIBANCO S.A.' está em BANCOS_ALVO. O diagnóstico segue rodando\n"
        "  a cada execução: se a contagem da HOLDING crescer de forma relevante\n"
        "  em safras futuras, reavaliar a decisão."
    )
    print()

    return contagem


# --------------------------------------------------------------------------- #
# 5. Recorte de instituições
# --------------------------------------------------------------------------- #


def filtrar_instituicoes_alvo(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém somente cooperativas de crédito e os cinco bancos-alvo.

    Uma linha é mantida se:

    * `segmento == config.SEGMENTO_COOPERATIVA` (qualquer bandeira), OU
    * `nome_instituicao` é exatamente igual a um item de `config.BANCOS_ALVO`.

    O match dos bancos é por igualdade exata sobre o nome já normalizado
    (strip + colapso de espaços), nunca por `contains` — assim subsidiárias
    como "BANCO BRADESCO FINANCIAMENTOS S.A." ou "ITAÚ UNIBANCO HOLDING S.A."
    não entram. Todo o resto (bancos estrangeiros, financeiras, sociedades de
    crédito, corretoras, BNDES etc.) é descartado.

    Args:
        df: base combinada já restrita a RS/SC/PR.

    Returns:
        DataFrame filtrado.
    """
    bancos_alvo = [_normalizar_espacos(nome) for nome in config.BANCOS_ALVO]

    eh_cooperativa = df["segmento"] == config.SEGMENTO_COOPERATIVA
    eh_banco_alvo = df["nome_instituicao"].isin(bancos_alvo)

    return df[eh_cooperativa | eh_banco_alvo].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 7. categoria_if
# --------------------------------------------------------------------------- #


def classificar_categoria_if(df: pd.DataFrame) -> pd.DataFrame:
    """Cria `categoria_if` com apenas dois valores possíveis.

    Valores: ``"Cooperativa de Crédito"`` (segmento cooperativo) e ``"Banco"``
    (os cinco bancos-alvo). Como a função roda depois de
    `filtrar_instituicoes_alvo`, toda linha cai em um dos dois grupos.

    Args:
        df: DataFrame já filtrado para cooperativas + bancos-alvo.

    Returns:
        Cópia do DataFrame com a coluna `categoria_if`.

    Raises:
        ValueError: se sobrar alguma linha não classificada, o que indicaria
            que o filtro de instituições foi alterado ou não foi aplicado.
    """
    bancos_alvo = [_normalizar_espacos(nome) for nome in config.BANCOS_ALVO]
    resultado = df.copy()

    resultado["categoria_if"] = pd.NA
    eh_cooperativa = resultado["segmento"] == config.SEGMENTO_COOPERATIVA
    resultado.loc[eh_cooperativa, "categoria_if"] = CATEGORIA_COOPERATIVA
    # `~eh_cooperativa` evita reclassificar caso um mesmo nome apareça nos dois
    # conjuntos; na prática os grupos são disjuntos nesta base.
    eh_banco = ~eh_cooperativa & resultado["nome_instituicao"].isin(bancos_alvo)
    resultado.loc[eh_banco, "categoria_if"] = CATEGORIA_BANCO

    nao_classificadas = int(resultado["categoria_if"].isna().sum())
    if nao_classificadas:
        exemplos = (
            resultado.loc[resultado["categoria_if"].isna(), "nome_instituicao"]
            .unique()[:5]
            .tolist()
        )
        raise ValueError(
            f"{nao_classificadas} linha(s) sem categoria_if. Exemplos: {exemplos!r}"
        )

    resultado["categoria_if"] = resultado["categoria_if"].astype("string")
    return resultado


# --------------------------------------------------------------------------- #
# 8. sub_categoria
# --------------------------------------------------------------------------- #


def classificar_sub_categoria(df: pd.DataFrame) -> pd.DataFrame:
    """Cria `sub_categoria` com o nome comercial da instituição.

    Bancos: de-para fechado `NOME_COMERCIAL_BANCO` (Banco do Brasil, Bradesco,
    Itaú, Caixa, Santander).

    Cooperativas: duas etapas, "primeira regra que casar vence".

    1. `REGRAS_BANDEIRA_POR_CNPJ` — filiação declarada, casada pela raiz do
       CNPJ. Roda primeiro por ser critério objetivo, independente de a marca
       estar escrita no nome.
    2. `REGRAS_BANDEIRA_COOPERATIVA` — marca escrita no `nome_instituicao`,
       comparada em caixa alta e sem acentos.

    Quando nenhuma das duas etapas casa, a linha recebe
    ``"Outra Cooperativa"`` — não há tentativa de adivinhar a filiação por
    outros meios.

    Args:
        df: DataFrame com `categoria_if` já preenchida.

    Returns:
        Cópia do DataFrame com a coluna `sub_categoria`.

    Raises:
        ValueError: se algum banco-alvo ficar sem nome comercial, o que
            indicaria divergência entre `config.BANCOS_ALVO` e
            `NOME_COMERCIAL_BANCO`.
    """
    resultado = df.copy()
    resultado["sub_categoria"] = pd.NA

    # --- Bancos: de-para exato, sem inferência textual ---------------------- #
    eh_banco = resultado["categoria_if"] == CATEGORIA_BANCO
    resultado.loc[eh_banco, "sub_categoria"] = resultado.loc[
        eh_banco, "nome_instituicao"
    ].map(NOME_COMERCIAL_BANCO)

    bancos_sem_de_para = int(eh_banco.sum()) - int(
        resultado.loc[eh_banco, "sub_categoria"].notna().sum()
    )
    if bancos_sem_de_para:
        faltantes = (
            resultado.loc[eh_banco & resultado["sub_categoria"].isna(), "nome_instituicao"]
            .unique()
            .tolist()
        )
        raise ValueError(
            "Banco-alvo sem nome comercial em NOME_COMERCIAL_BANCO: "
            f"{faltantes!r}"
        )

    # --- Cooperativas: regras explícitas, na ordem ------------------------- #
    eh_cooperativa = resultado["categoria_if"] == CATEGORIA_COOPERATIVA
    nome_para_match = _dobrar_acentos(resultado["nome_instituicao"])

    # `pendente` garante o comportamento "primeira regra que casar vence":
    # uma linha já rotulada não é reavaliada pelas regras seguintes.
    pendente = eh_cooperativa.copy()

    # Etapa 1 — filiação por raiz de CNPJ (critério declarado, tem precedência).
    raiz = _raiz_cnpj(resultado["cnpj"])
    for bandeira, cnpjs_filiadas in REGRAS_BANDEIRA_POR_CNPJ:
        raizes_filiadas = set(
            _raiz_cnpj(pd.Series(list(cnpjs_filiadas), dtype="string")).dropna()
        )
        casa = pendente & raiz.isin(raizes_filiadas).fillna(False)
        resultado.loc[casa, "sub_categoria"] = bandeira
        pendente = pendente & ~casa

    # Etapa 2 — marca escrita na razão social.
    for bandeira, padrao in REGRAS_BANDEIRA_COOPERATIVA:
        casa = pendente & nome_para_match.str.contains(
            padrao, regex=True, na=False
        )
        resultado.loc[casa, "sub_categoria"] = bandeira
        pendente = pendente & ~casa

    # Cooperativas sem nenhuma marca reconhecida no nome.
    resultado.loc[pendente, "sub_categoria"] = SUB_CATEGORIA_COOP_INDEFINIDA

    resultado["sub_categoria"] = resultado["sub_categoria"].astype("string")
    return resultado


# --------------------------------------------------------------------------- #
# 9. Código IBGE
# --------------------------------------------------------------------------- #


def padronizar_municipio_ibge(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza `municipio_ibge` como string de 7 dígitos.

    Remove um eventual sufixo ``.0`` (caso a coluna já tenha passado por
    conversão numérica em algum ponto), mantém apenas dígitos e completa com
    zeros à esquerda até 7 caracteres — o código IBGE de município tem 7
    dígitos (UF + município + dígito verificador).

    Args:
        df: DataFrame com a coluna `municipio_ibge`.

    Returns:
        Cópia do DataFrame com `municipio_ibge` como ``string`` de 7 dígitos.

    Raises:
        ValueError: se algum código não resultar em exatamente 7 dígitos.
    """
    resultado = df.copy()

    codigo = (
        resultado["municipio_ibge"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\D", "", regex=True)
    )
    # Strings vazias (célula em branco na origem) viram nulo em vez de "0000000".
    codigo = codigo.replace("", pd.NA)
    codigo = codigo.str.zfill(7)

    invalidos = codigo.notna() & ~codigo.str.fullmatch(r"\d{7}").fillna(False)
    if invalidos.any():
        exemplos = codigo[invalidos].unique()[:5].tolist()
        raise ValueError(
            f"{int(invalidos.sum())} código(s) IBGE fora do padrão de 7 dígitos: "
            f"{exemplos!r}"
        )

    resultado["municipio_ibge"] = codigo
    return resultado


# --------------------------------------------------------------------------- #
# 10. Persistência
# --------------------------------------------------------------------------- #


def salvar_parquet(
    df: pd.DataFrame, caminho: Path = config.ARQUIVO_IF_SUL_CATEGORIZADO
) -> Path:
    """Grava o dataset final em Parquet, criando o diretório se necessário.

    Args:
        df: dataset categorizado.
        caminho: destino do arquivo ``.parquet``.

    Returns:
        O caminho gravado.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(caminho, index=False)
    return caminho


# --------------------------------------------------------------------------- #
# Resumo
# --------------------------------------------------------------------------- #


def imprimir_resumo(df: pd.DataFrame, top_indefinidas: int = 15) -> None:
    """Imprime o resumo do dataset final para conferência manual.

    Mostra o total de linhas por UF, por `categoria_if` e por `sub_categoria`,
    e destaca quantas cooperativas ficaram sem bandeira identificada — com uma
    amostra dos nomes, para revisão das regras de extração.

    Args:
        df: dataset final, já categorizado.
        top_indefinidas: quantos nomes de "Outra Cooperativa" listar.
    """
    print("=" * 78)
    print("RESUMO — data/processed/if_sul_categorizado.parquet")
    print("=" * 78)
    print(f"Total de linhas: {len(df)}\n")

    print("-- linhas por UF --")
    print(df["uf"].value_counts().to_string(), "\n")

    print("-- linhas por tipo_instalacao --")
    print(df["tipo_instalacao"].value_counts().to_string(), "\n")

    print("-- linhas por categoria_if --")
    print(df["categoria_if"].value_counts().to_string(), "\n")

    print("-- linhas por sub_categoria --")
    print(df["sub_categoria"].value_counts().to_string(), "\n")

    print("-- sub_categoria x UF --")
    print(
        pd.crosstab(df["sub_categoria"], df["uf"]).to_string(),
        "\n",
    )

    indefinidas = df[
        (df["categoria_if"] == CATEGORIA_COOPERATIVA)
        & (df["sub_categoria"] == SUB_CATEGORIA_COOP_INDEFINIDA)
    ]
    total_coop = int((df["categoria_if"] == CATEGORIA_COOPERATIVA).sum())
    pct = (len(indefinidas) / total_coop * 100) if total_coop else 0.0

    print("=" * 78)
    print(
        f'REVISAR — cooperativas sem bandeira ("{SUB_CATEGORIA_COOP_INDEFINIDA}"): '
        f"{len(indefinidas)} de {total_coop} linhas de cooperativa ({pct:.1f}%), "
        f"{indefinidas['nome_instituicao'].nunique()} instituições distintas"
    )
    print("=" * 78)
    if len(indefinidas):
        print(f"Top {top_indefinidas} nomes sem bandeira reconhecida:")
        print(
            indefinidas["nome_instituicao"]
            .value_counts()
            .head(top_indefinidas)
            .to_string()
        )
    print()


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #


def executar() -> pd.DataFrame:
    """Roda o ETL completo, grava o Parquet e imprime os diagnósticos.

    Etapas: leitura das duas planilhas -> padronização no esquema comum ->
    concatenação -> recorte RS/SC/PR -> diagnóstico Itaú -> recorte de
    instituições -> `categoria_if` -> `sub_categoria` -> código IBGE ->
    gravação em Parquet -> resumo.

    Returns:
        O dataset final categorizado.
    """
    agencias = carregar_agencias()
    postos = carregar_postos()
    print(
        f"Lidas {len(agencias)} agências e {len(postos)} postos "
        f"(Brasil, antes de qualquer filtro).\n"
    )

    combinada = combinar_bases(agencias, postos)
    sul = filtrar_sul(combinada)
    print(f"Base RS/SC/PR antes do filtro de instituições: {len(sul)} linhas.\n")

    # Etapa 6: diagnóstico exigido antes do recorte de instituições.
    diagnosticar_itau(sul)

    alvo = filtrar_instituicoes_alvo(sul)
    print(
        f"Após o filtro de instituições (cooperativas + {len(config.BANCOS_ALVO)} "
        f"bancos-alvo): {len(alvo)} linhas "
        f"({len(sul) - len(alvo)} descartadas).\n"
    )

    categorizado = classificar_categoria_if(alvo)
    categorizado = classificar_sub_categoria(categorizado)
    categorizado = padronizar_municipio_ibge(categorizado)

    destino = salvar_parquet(categorizado)
    imprimir_resumo(categorizado)
    print(f"Dataset gravado em: {destino}")

    return categorizado


def main() -> None:
    """Ponto de entrada para ``python -m src.etl_bacen``."""
    executar()


if __name__ == "__main__":
    main()
