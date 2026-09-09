"""Testes da separação entre bandeira de filtro e marca exibida.

`sub_categoria` e `marca_exibicao` respondem a perguntas diferentes e os testes
aqui existem para que elas não voltem a se confundir:

* `sub_categoria` é a chave do FILTRO, da legenda e da cor. Ela tem poucos
  valores estáveis e agrupa os sistemas pequenos em ``"Outra Cooperativa"``;
* `marca_exibicao` é o nome mostrado ao leitor no tooltip e nos popups. Ela
  nomeia os sistemas que o filtro agrupa, e é igual a `sub_categoria` em todo
  o resto do dataset.

Os testes de regra (classe `TestRegrasDeClassificacao`) rodam sobre DataFrames
montados na hora e não dependem de nenhum artefato. Os de invariante leem
``if_sul_categorizado.parquet`` e ``agregado_municipio.parquet`` já gravados —
rode `python -m src.etl_bacen` e `python -m src.agregacao` antes.
"""

import pandas as pd
import pytest

from src import agregacao, config
from src.etl_bacen import (
    CATEGORIA_BANCO,
    CATEGORIA_COOPERATIVA,
    MARCAS_OUTRAS_COOPERATIVAS,
    SUB_CATEGORIA_COOP_INDEFINIDA,
    classificar_sub_categoria,
)


def _linha(
    nome_instituicao: str,
    nome_instalacao: str,
    cnpj: str = "99.999.999",
    categoria: str = CATEGORIA_COOPERATIVA,
) -> dict:
    """Monta uma linha mínima com o que `classificar_sub_categoria` lê."""
    return {
        "cnpj": cnpj,
        "nome_instituicao": nome_instituicao,
        "nome_instalacao": nome_instalacao,
        "categoria_if": categoria,
    }


def _classificar(*linhas: dict) -> pd.DataFrame:
    return classificar_sub_categoria(pd.DataFrame(list(linhas)))


@pytest.fixture(scope="module")
def pontos() -> pd.DataFrame:
    if not config.arquivo_if_categorizado().exists():
        pytest.fail(
            f"{config.arquivo_if_categorizado()} não existe. "
            "Rode `python -m src.etl_bacen` antes."
        )
    return pd.read_parquet(config.arquivo_if_categorizado())


@pytest.fixture(scope="module")
def agregado() -> pd.DataFrame:
    if not config.arquivo_agregado_municipio().exists():
        pytest.fail(
            f"{config.arquivo_agregado_municipio()} não existe. "
            "Rode `python -m src.agregacao` antes."
        )
    return pd.read_parquet(config.arquivo_agregado_municipio())


# --------------------------------------------------------------------------- #
# 1. As regras de classificação
# --------------------------------------------------------------------------- #


class TestRegrasDeClassificacao:
    """Etapas 2 e 3 da bandeira, e o de-para de `marca_exibicao`."""

    def test_marca_na_razao_social_define_a_bandeira(self):
        """O caso comum: a marca está escrita no nome da instituição."""
        r = _classificar(
            _linha("COOPERATIVA DE CRÉDITO ... - SICOOB CREDISC", "PA CENTRO")
        )
        assert r.loc[0, "sub_categoria"] == "Sicoob"
        assert r.loc[0, "marca_exibicao"] == "Sicoob"

    def test_marca_so_no_nome_da_instalacao_define_a_bandeira(self):
        """O furo que motivou a etapa 3, no caso real da CREDPOM.

        A razão social não traz "SICOOB" em lugar nenhum; o nome do posto traz.
        Antes da etapa 3 esta linha virava "Outra Cooperativa", e o mapa exibia
        essa legenda logo acima de um nome que dizia "SICOOB".
        """
        r = _classificar(
            _linha(
                "COOPERATIVA DE ECONOMIA E CRÉDITO MÚTUO DOS MILITARES "
                "ESTADUAIS DE SANTA CATARINA - CREDPOM",
                "SICOOB PA - JOINVILLE",
                cnpj="04.572.960",
            )
        )
        assert r.loc[0, "sub_categoria"] == "Sicoob"
        assert r.loc[0, "marca_exibicao"] == "Sicoob"

    def test_razao_social_tem_precedencia_sobre_nome_da_instalacao(self):
        """A etapa 3 só alcança quem a etapa 2 não classificou."""
        r = _classificar(
            _linha("COOPERATIVA ... - SICREDI SERRANA", "SICOOB PA - QUALQUER")
        )
        assert r.loc[0, "sub_categoria"] == "Sicredi"

    def test_cnpj_ailos_tem_precedencia_sobre_o_texto(self):
        """Filiação declarada vence marca escrita, como antes da mudança."""
        r = _classificar(
            _linha("COOPERATIVA ... - VIACREDI", "PA CENTRO", cnpj="82.639.451")
        )
        assert r.loc[0, "sub_categoria"] == "Ailos"

    @pytest.mark.parametrize(
        ("razao_social", "esperada"),
        [
            ("SISPRIME DO BRASIL - COOPERATIVA DE CRÉDITO", "Sisprime"),
            ("LAR COOPERATIVA DE CRÉDITO - LAR CREDI", "Lar Credi"),
            ("CREDI&GENTE - COOPERATIVA DE CRÉDITO E INVESTIMENTOS", "Credi&Gente"),
            ("CREDISIS CREDIPLAN - COOPERATIVA DE CRÉDITO ...", "Credisis"),
            ("COOPERATIVA DE CREDITO RURAL SEARA - CREDISEARA", "Crediseara"),
        ],
    )
    def test_marca_exibicao_nomeia_quem_fica_no_balde(self, razao_social, esperada):
        """O sistema é nomeado sem deixar de filtrar como "Outra Cooperativa"."""
        r = _classificar(_linha(razao_social, "PA CENTRO"))
        assert r.loc[0, "sub_categoria"] == SUB_CATEGORIA_COOP_INDEFINIDA
        assert r.loc[0, "marca_exibicao"] == esperada

    def test_cooperativa_sem_marca_alguma_fica_sem_nome(self):
        """Sem marca escrita, `marca_exibicao` repete o rótulo do balde.

        É o único caso em que "Outra Cooperativa" é afirmação verdadeira sobre
        o dado, e não um nome que se perdeu.
        """
        r = _classificar(
            _linha("COOPERATIVA DE CRÉDITO DOS FUNCIONÁRIOS DE ALGO LTDA", "PAC 1")
        )
        assert r.loc[0, "sub_categoria"] == SUB_CATEGORIA_COOP_INDEFINIDA
        assert r.loc[0, "marca_exibicao"] == SUB_CATEGORIA_COOP_INDEFINIDA

    def test_marca_exibicao_de_banco_repete_a_sub_categoria(self):
        """A coluna vale para o dataset inteiro, não só para cooperativas."""
        r = _classificar(
            _linha("BANCO DO BRASIL S.A.", "AG CENTRO", categoria=CATEGORIA_BANCO)
        )
        assert r.loc[0, "sub_categoria"] == "Banco do Brasil"
        assert r.loc[0, "marca_exibicao"] == "Banco do Brasil"

    def test_marcas_do_balde_nao_reclassificam_bandeira_reconhecida(self):
        """`MARCAS_OUTRAS_COOPERATIVAS` não toca em quem já tem bandeira.

        "COOPAVEL" aparece na razão social de uma cooperativa Sicredi
        hipotética: a marca do balde não pode roubar a bandeira dela.
        """
        r = _classificar(
            _linha("COOPERATIVA ... SICREDI ... COOPAVEL REGIÃO", "PA CENTRO")
        )
        assert r.loc[0, "sub_categoria"] == "Sicredi"
        assert r.loc[0, "marca_exibicao"] == "Sicredi"


# --------------------------------------------------------------------------- #
# 2. Invariantes do dataset gravado
# --------------------------------------------------------------------------- #


def test_dataset_tem_a_coluna_marca_exibicao(pontos):
    assert "marca_exibicao" in pontos.columns, (
        "`marca_exibicao` ausente em if_sul_categorizado.parquet. O Parquet é "
        "de uma safra anterior à coluna — rode `python -m src.etl_bacen`."
    )
    assert int(pontos["marca_exibicao"].isna().sum()) == 0, (
        "Toda linha tem de ter `marca_exibicao`; quando não há marca própria "
        "ela repete `sub_categoria`."
    )


def test_marca_exibicao_so_difere_dentro_do_balde(pontos):
    """Fora de "Outra Cooperativa", as duas colunas são a mesma coisa.

    É o que permite qualquer superfície ler `marca_exibicao` sem precisar saber
    se aquele ponto é um caso especial.
    """
    fora = pontos[pontos["sub_categoria"] != SUB_CATEGORIA_COOP_INDEFINIDA]
    divergentes = fora[fora["marca_exibicao"] != fora["sub_categoria"]]
    assert divergentes.empty, (
        f"{len(divergentes)} linha(s) com `marca_exibicao` != `sub_categoria` "
        f"fora do balde. Exemplos: "
        f"{divergentes[['sub_categoria', 'marca_exibicao']].head().to_dict('records')!r}"
    )


def test_marcas_do_balde_saem_do_de_para_declarado(pontos):
    """Nenhum nome inventado: só o que está em `MARCAS_OUTRAS_COOPERATIVAS`."""
    previstas = {marca for marca, _ in MARCAS_OUTRAS_COOPERATIVAS}
    previstas.add(SUB_CATEGORIA_COOP_INDEFINIDA)

    no_balde = pontos[pontos["sub_categoria"] == SUB_CATEGORIA_COOP_INDEFINIDA]
    encontradas = set(no_balde["marca_exibicao"].dropna().unique())
    assert encontradas <= previstas, (
        f"marca_exibicao fora do de-para: {sorted(encontradas - previstas)!r}."
    )


def test_nenhuma_cooperativa_exibe_sicoob_sem_ser_sicoob(pontos):
    """A contradição original não pode voltar.

    Um ponto cujo nome de instalação diz "SICOOB" e cuja legenda diz "Outra
    Cooperativa" é exatamente o defeito que a etapa 3 corrigiu.
    """
    coop = pontos[pontos["categoria_if"] == CATEGORIA_COOPERATIVA]
    diz_sicoob = coop["nome_instalacao"].astype("string").str.upper().str.contains(
        r"\bSICOOB\b", regex=True, na=False
    )
    contraditorios = coop[diz_sicoob & (coop["sub_categoria"] != "Sicoob")]
    assert contraditorios.empty, (
        f"{len(contraditorios)} ponto(s) com 'SICOOB' no nome da instalação mas "
        f"bandeira {sorted(set(contraditorios['sub_categoria']))!r}."
    )


# --------------------------------------------------------------------------- #
# 3. O detalhe que chega ao popup do município
# --------------------------------------------------------------------------- #


def test_agregado_tem_a_coluna_de_detalhe(agregado):
    assert agregacao.COLUNA_DETALHE_OUTRAS in agregado.columns, (
        f"`{agregacao.COLUNA_DETALHE_OUTRAS}` ausente no agregado — rode "
        "`python -m src.agregacao`."
    )
    assert int(agregado[agregacao.COLUNA_DETALHE_OUTRAS].isna().sum()) == 0, (
        "Município sem detalhe recebe string vazia, nunca nulo: o popup não "
        "testa NaN."
    )


def test_detalhe_existe_exatamente_onde_ha_outra_cooperativa(agregado):
    """O detalhe está preenchido se e somente se a contagem do balde é > 0."""
    # `.astype(bool)` nos dois lados de propósito: o detalhe é `string` do
    # pandas e produz uma máscara `boolean` (nullable), que nunca é `.equals()`
    # de uma máscara `bool` mesmo com valores idênticos. A comparação que
    # interessa aqui é de VALOR.
    tem_detalhe = (agregado[agregacao.COLUNA_DETALHE_OUTRAS].str.len() > 0).astype(bool)
    tem_ponto = (agregado["total_outra_coop"] > 0).astype(bool)

    divergentes = agregado[tem_detalhe != tem_ponto]
    assert divergentes.empty, (
        f"{len(divergentes)} município(s) em que a presença do detalhe não bate "
        f"com `total_outra_coop`. Exemplos: "
        f"{divergentes[['municipio_nome', 'total_outra_coop', agregacao.COLUNA_DETALHE_OUTRAS]].head().to_dict('records')!r}"
    )


def test_soma_do_detalhe_bate_com_a_contagem_do_municipio(agregado):
    """"Sisprime 3 · Credisis 1" tem de somar exatamente `total_outra_coop`."""
    com_detalhe = agregado[agregado[agregacao.COLUNA_DETALHE_OUTRAS].str.len() > 0]

    def _somar(texto: str) -> int:
        return sum(
            int(parte.rsplit(" ", 1)[1])
            for parte in texto.split(agregacao.SEPARADOR_DETALHE)
        )

    somas = com_detalhe[agregacao.COLUNA_DETALHE_OUTRAS].map(_somar)
    divergentes = com_detalhe[somas != com_detalhe["total_outra_coop"]]
    assert divergentes.empty, (
        f"{len(divergentes)} município(s) em que o detalhe não soma "
        f"`total_outra_coop`. Exemplos: "
        f"{divergentes[['municipio_nome', 'total_outra_coop', agregacao.COLUNA_DETALHE_OUTRAS]].head().to_dict('records')!r}"
    )
