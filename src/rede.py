"""Preparo do TLS antes de qualquer chamada às APIs e ao FTP do IBGE.

Existe por um motivo prático: nas máquinas onde este projeto roda, TODAS as
chamadas ao IBGE falhavam com ``CERTIFICATE_VERIFY_FAILED``. A causa não é o
IBGE — é antivírus ou proxy corporativo inspecionando HTTPS. Essas ferramentas
reemitem os certificados dos sites com uma autoridade raiz própria, que elas
instalam no repositório de certificados do WINDOWS. O `requests` não olha para
esse repositório: ele valida contra o pacote embutido do `certifi`, onde essa
raiz não está, e recusa a conexão.

`usar_certificados_do_sistema` liga o `truststore`, que substitui a validação
do Python pela do sistema operacional. Com isso o mesmo certificado que o
navegador aceita passa a ser aceito aqui, sem ninguém precisar exportar PEM
nem definir ``REQUESTS_CA_BUNDLE`` à mão.

A dependência é OPCIONAL de propósito: em máquina sem inspeção de HTTPS o
`certifi` já resolve, e um ambiente sem o `truststore` instalado continua
funcionando normalmente — a função apenas não faz nada e registra o motivo.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

#: Guarda de idempotência: `truststore.inject_into_ssl` mexe em estado global do
#: módulo `ssl`, e os módulos de rede chamam a função a cada operação.
_PREPARADO = False


def usar_certificados_do_sistema() -> bool:
    """Faz o Python validar TLS pelo repositório de certificados do sistema.

    Idempotente: chamadas seguintes não fazem nada.

    Returns:
        ``True`` se a validação pelo sistema está ativa, ``False`` se o
        `truststore` não está instalado (e a validação segue pelo `certifi`).
    """
    global _PREPARADO
    if _PREPARADO:
        return True

    try:
        import truststore
    except ImportError:
        _LOGGER.debug(
            "truststore não instalado; TLS continua validando pelo certifi. "
            "Se as chamadas ao IBGE falharem com CERTIFICATE_VERIFY_FAILED, "
            "instale-o com `pip install truststore`."
        )
        return False

    truststore.inject_into_ssl()
    _PREPARADO = True
    _LOGGER.debug("TLS validando pelo repositório de certificados do sistema.")
    return True
