# mapa-if-sul

Mapa interativo da **cobertura de cooperativas de crédito e dos cinco maiores
bancos no Brasil** — as 27 unidades da federação, numa única página.

> O nome do repositório é de quando o recorte era a Região Sul. O projeto nasceu
> ali e cresceu para o país; o recorte hoje é um parâmetro (`--ufs`), e a Região
> Sul continua sendo o padrão de quem roda sem argumentos.

## 1. O que é e para que serve

O projeto responde a uma pergunta de geografia econômica: **onde o cooperativismo
de crédito atende, e onde os grandes bancos atendem, nos 5.570 municípios do
Brasil?**

A resposta curta, na safra 202608: **1.096 municípios — quase um em cada cinco —
não têm nenhuma agência nem posto de atendimento** de cooperativa de crédito ou
dos cinco maiores bancos. Moram neles 7,7 milhões de pessoas. E a distribuição
desse vazio é o achado: ele vai de **1,7% dos municípios no Sul a 40% no
Nordeste**.

| Região | Pontos | Municípios atendidos | Sem nenhum ponto |
|---|---:|---:|---:|
| Norte | 1.645 | 314 | 136 (30%) |
| Nordeste | 4.329 | 1.085 | **709 (40%)** |
| Centro-Oeste | 2.768 | 405 | 62 (13%) |
| Sudeste | 14.233 | 1.499 | 169 (10%) |
| Sul | 7.603 | 1.171 | 20 (1,7%) |
| **Brasil** | **30.578** | **4.474** | **1.096 (19,7%)** |

Foi para tornar esse contraste visível que o recorte deixou de ser regional: no
Sul, onde o projeto nasceu, o vazio assistencial quase não aparece.

A partir dos cadastros de agências e postos de atendimento publicados pelo Banco
Central e das bases territoriais do IBGE, o pipeline produz uma página HTML
autocontida com duas leituras sobrepostas:

- **coroplético por município** — a intensidade de cobertura de cada município,
  reativa ao recorte escolhido (cooperativas, bancos ou o total), com população
  e contagem por bandeira no popup;
- **camadas de pontos em dois níveis** — cada agência e cada posto no endereço
  em que de fato está, colorido pela cor de marca da instituição, com o nível de
  precisão da coordenada declarado ponto a ponto.

O caso de uso que motiva o recorte é a **identificação de vazios assistenciais**:
municípios onde só a cooperativa está presente, onde só o banco está, ou onde não
há nenhum dos dois. Por isso a malha usada é a completa — os municípios sem
nenhum ponto de atendimento aparecem no mapa como zero, e não como buraco.

O resultado é `output/mapa_if_br.html`, que abre direto no navegador, sem
servidor e **sem internet**: folha de estilo, símbolo, ícone e as bibliotecas
JavaScript (Leaflet, MarkerCluster e o resto do que o folium carregaria por
CDN) vão todos embutidos no arquivo — ver `src/embutir.py`. Ele circula por
e-mail ou pen drive e funciona em rede corporativa que bloqueie CDN.

São **20,6 MB em disco e 5,1 MB no que o navegador baixa** (o servidor comprime
com gzip). O arquivo abre em ~2,5 s e o modo de pontos leva mais alguns segundos
para o agrupamento espalhar os 30 mil marcadores pelo país.

A única coisa que continua vindo da rede é o **basemap** — os ladrilhos de
ruas da CARTO, baixados sob demanda conforme o enquadramento, que por serem
milhares não têm como ser empacotados. Sem eles o mapa perde o fundo de ruas
e mantém todo o resto: coroplético, divisas, os 30.578 marcadores, popups,
filtros, busca e ranking.

Esses ladrilhos exigem uma **chave de API da CARTO** — gratuita, pedida em
<https://carto.com/basemaps/apikey>, com franquia de 5 milhões de ladrilhos por
mês. Ela fica em `config.CARTO_API_KEY` e entra na URL como `?key=`. Sem chave
o servidor não devolve erro: devolve o ladrilho com a marca d'água
"API KEY REQUIRED" carimbada por cima, e o mapa sai publicado assim. Para gerar
com outra chave, sem editar o arquivo, basta exportar `CARTO_API_KEY` antes de
rodar. A atribuição do OpenStreetMap e da CARTO no canto do mapa é condição do
uso gratuito e não deve ser removida.

## 2. Escopo

O recorte é **deliberadamente fechado** e não é uma amostra do sistema
financeiro: é o universo de duas populações escolhidas.

### Está dentro

| | Critério | Como é aplicado |
|---|---|---|
| **Cooperativas de crédito** | **todos** os sistemas, sem exceção | toda linha cujo campo `SEGMENTO` do BACEN seja exatamente `Cooperativa de Crédito` |
| **Bancos** | **somente cinco** | igualdade exata do campo `NOME INSTITUIÇÃO` com a lista abaixo |

Os cinco bancos, com a grafia **literal** da fonte (`config.BANCOS_ALVO`):

```
BANCO DO BRASIL S.A.
BANCO BRADESCO S.A.
ITAÚ UNIBANCO S.A.
CAIXA ECONOMICA FEDERAL          <- sem acento em "ECONOMICA", como na fonte
BANCO SANTANDER (BRASIL) S.A.
```

Do lado cooperativo entram **todos os sistemas**, filiados ou independentes.
Os identificados por bandeira própria hoje são **Sicredi, Sicoob, Cresol,
Unicred e Ailos**; qualquer cooperativa que não case com nenhum deles permanece
no dataset sob o rótulo `Outra Cooperativa` — ela **não é descartada**, apenas
não tem bandeira própria no filtro.

#### Quem merece bandeira própria: o corte de 100 pontos

Ter linha, cor e filtro próprios exige **mais de 100 pontos no país**. A régua é
da safra 202608 e substituiu uma lista que fora calibrada na paisagem do Sul,
onde três sistemas regionais pareciam grandes e nacionalmente não são:

| Sistema | Pontos no país | UFs | |
|---|---:|---:|---|
| Sicoob | 4.447 | 27 | bandeira |
| Sicredi | 3.258 | 27 | bandeira |
| Cresol | 1.139 | 20 | bandeira |
| Ailos | 383 | 8 | bandeira |
| Unicred | 371 | 24 | bandeira |
| Credicoamo | 53 | 3 | → `Outra Cooperativa` |
| Uniprime | 46 | 6 | → `Outra Cooperativa` |
| Sulcredi | 27 | 1 | → `Outra Cooperativa` |

O corte é sobre **pontos**, e não sobre número de UFs, porque é a quantidade de
pontos que decide se uma linha do painel mostra alguma coisa no mapa: uma
bandeira de 27 pontos, marcada sozinha, pinta 27 municípios de 5.570 e deixa o
resto em cinza.

Os três rebaixados **continuam nomeados** no tooltip e no popup, via
`marca_exibicao` (ver abaixo). Eles perdem o filtro, não o nome.

Uma consequência que vale registrar: com o rebaixamento, `Outra Cooperativa`
(384 pontos) ficou **maior que Ailos (383) e Unicred (371)**. O balde não é mais
o resto pequeno — é a nona maior linha do painel.

O **Sistema Ailos** é identificado por **CNPJ**, e não pelo nome: nenhuma
razão social publicada pelo BACEN contém a string "AILOS" — cada filiada assina
com marca própria (Viacredi, Transpocred, Únilos...). A relação de filiadas está
em `config.CNPJS_AILOS`. No recorte nacional ela alcança **383 pontos em 8 UFs**
— o sistema tem mais território do que o recorte original mostrava.

#### Como a bandeira é decidida

São três etapas, "primeira que casar vence", em `etl_bacen.classificar_sub_categoria`:

| # | Critério | Onde está a regra |
|---|---|---|
| 1 | **filiação por raiz de CNPJ** — critério declarado, tem precedência | `REGRAS_BANDEIRA_POR_CNPJ` |
| 2 | **marca escrita na razão social** (`NOME INSTITUIÇÃO`) | `REGRAS_BANDEIRA_COOPERATIVA` |
| 3 | **marca escrita no nome da instalação** (`NOME INSTALAÇÃO`) | `REGRAS_BANDEIRA_POR_INSTALACAO` |

A etapa 3 existe porque há cooperativas filiadas a um sistema que **não escrevem
a marca na razão social**, mas batizam cada posto com ela. No país da safra
202608 são **42 instituições, somando 749 pontos** — Sicoob e Unicred — entre
elas a `COOPERATIVA DE ECONOMIA E CRÉDITO MÚTUO DOS MILITARES ESTADUAIS DE SANTA
CATARINA - CREDPOM`, cujos postos se chamam `SICOOB PA - JOINVILLE`,
`SICOOB PA - LAGES` e assim por diante. Lendo só a razão social, o mapa exibia
"Outra Cooperativa" na legenda logo acima de um nome que dizia "SICOOB".

No recorte do Sul essa regra salvava 58 pontos e parecia um remendo para quatro
cooperativas catarinenses. No país ela sustenta **7,5% de todo o cooperativismo
do mapa**.

O critério continua sendo o mesmo — a marca precisa estar **escrita num campo
publicado pelo BACEN**, sem inferência externa. O que mudou foi o número de
campos lidos: dois em vez de um.

#### `marca_exibicao`: o nome por trás de "Outra Cooperativa"

Depois das três etapas, e do rebaixamento dos três sistemas acima, sobram na
safra 202608 **384 pontos** em `Outra Cooperativa`, de 64 instituições. Desses,
**338 têm marca escrita** e aparecem por ela: Credisis 71, Credicoamo 53,
Sisprime 50, Uniprime 46, Lar Credi 35, Sulcredi 27, Credi&Gente 17, Cogem 8, e
mais nove com 1 a 5 pontos cada.

Os outros **46 pontos, em 28 instituições, não têm marca nenhuma escrita** — e
o padrão diz mais que a lista: quase todas são cooperativas de **vínculo
fechado**, de empregados de uma empresa (Vale, Nestlé, BASF, Eaton, CBMM,
Vallourec, Correios, PUC-Rio) ou de uma categoria (bancários, magistrados,
policiais federais, servidores municipais). Elas não têm marca comercial porque
não vendem para fora: a razão social *é* a identidade. Continuam no mapa, sob o
rótulo agregado.

O projeto trata isso separando dois papéis que estavam na mesma coluna:

- **`sub_categoria`** continua sendo a chave do **filtro, da legenda e da cor**.
  `Outra Cooperativa` segue existindo ali, agrupando os sistemas pequenos —
  promover cada um a bandeira própria encheria o painel de linhas de 1 ponto;
- **`marca_exibicao`** é o nome **exibido ao leitor**. Vale o nome comercial
  (`Sisprime`, `Credisis`...) para as linhas do balde, e é igual a
  `sub_categoria` para todo o resto.

Onde `marca_exibicao` aparece:

| Superfície | O que mostra |
|---|---|
| tooltip do ponto | `**Sisprime** (Outra Cooperativa) · Posto de Atendimento` |
| popup do ponto | a marca no título, e `no filtro: Outra Cooperativa` abaixo |
| popup do município | sob a linha `Outra Cooperativa`, a composição: `Sisprime 3 · Credisis 1` |

A lista está em `etl_bacen.MARCAS_OUTRAS_COOPERATIVAS` e é avaliada **somente
sobre as linhas que sobraram** como `Outra Cooperativa`, o que torna impossível
ela mexer em qualquer bandeira reconhecida.

> Estes rótulos dizem **qual marca a linha exibe**, não a que central ela
> pertence. Credisis e Sisprime são centrais, e alguma dessas cooperativas pode
> ser filiada a um sistema já reconhecido sem escrever a marca em campo nenhum —
> como acontecia com o Ailos, resolvido só por lista de CNPJ declarada pela
> própria central.

### Está fora

- **Todas as demais instituições financeiras** — bancos fora dos cinco, bancos
  digitais, financeiras, corretoras, instituições de pagamento;
- **subsidiárias dos cinco bancos que não são rede de varejo.** O casamento é por
  igualdade exata, nunca por `contains`, justamente para não capturar
  "BANCO BRADESCO BBI S.A.", "BANCO BRADESCO FINANCIAMENTOS S.A." ou
  "ITAÚ UNIBANCO HOLDING S.A.";
- **correspondentes bancários, caixas eletrônicos e canais digitais.** As duas
  planilhas do BACEN cobrem agências e postos de atendimento; nenhum outro canal
  de atendimento entra na contagem.

> **Decisão registrada (safra 202608):** `ITAÚ UNIBANCO HOLDING S.A.` ficou de
> fora. Ela tem 8 pontos próprios no país — 1 agência e 7 postos — contra 3.419
> da entidade operacional `ITAÚ UNIBANCO S.A.`. O diagnóstico que embasou a
> decisão roda a cada execução do ETL (`etl_bacen.diagnosticar_itau`), para
> reavaliação em safras futuras.

## 3. Fontes de dados

Todas públicas e oficiais. As duas planilhas do BACEN são baixadas **à mão**; o
resto o pipeline busca sozinho.

### BACEN — cadastro de atendimento (entrada manual)

Página de origem:

```
https://www.bcb.gov.br/estabilidadefinanceira/agenciasconsorcio
```

Dela saem os dois arquivos que devem ser salvos em `data/raw/`, posição
**31.8.2026**:

| Arquivo | Conteúdo |
|---|---|
| `202608AGENCIAS.xlsx` | agências em funcionamento |
| `202608POSTOS.xlsx` | postos de atendimento (PA, PAE) |

O BACEN publica cada um como `.zip` contendo o `.xlsx` de mesmo nome; é o
`.xlsx` que vai para `data/raw/`. A publicação é mensal, no quinto dia útil
do mês seguinte à data-base.

Nas duas planilhas as linhas 1–9 são cabeçalho institucional; o cabeçalho real
das colunas está na linha 10 (`config.LINHA_CABECALHO_BACEN`).

### IBGE — APIs de serviços de dados (busca automática)

Documentação geral: `https://servicodados.ibge.gov.br/api/docs`

| Uso | URL base |
|---|---|
| **Malhas** — polígono de cada município do recorte | `https://servicodados.ibge.gov.br/api/v3/malhas` |
| **Localidades** — nome oficial do município | `https://servicodados.ibge.gov.br/api/v1/localidades` |
| **Agregados / SIDRA** — população residente estimada | `https://servicodados.ibge.gov.br/api/v3/agregados` |

A malha é pedida por UF em `/malhas/estados/{UF}` com `intrarregiao=municipio` e
qualidade `intermediaria` — uma chamada por UF do recorte, 27 no país. A
generalização dessa qualidade ocasionalmente cruza o contorno consigo mesmo: na
safra 202608 são três municípios (Nhamundá/AM, Barbalha/CE e Juína/MT), que
`ibge_malha.reparar_geometrias` conserta na leitura. Sem o reparo, a dissolução
das divisas estaduais falha com `TopologyException`. A população vem do **agregado SIDRA 6579**
("População residente estimada"), variável **9324**, sempre no período `-1`
(última posição disponível) — o ano nunca é fixado no código.

### IBGE — CNEFE, Censo 2022 (busca automática)

Cadastro Nacional de Endereços para Fins Estatísticos, a fonte das coordenadas
de cada ponto de atendimento:

```
https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF
```

É **um arquivo por UF** — `11_RO.zip` a `53_DF.zip` —, baixados na primeira
execução para `data/raw/cnefe/` e reaproveitados em todas as seguintes, inclusive
entre recortes diferentes: o CNEFE é produto do Censo 2022 e não muda.

| Recorte | Arquivos | Tamanho |
|---|---:|---:|
| Região Sul (padrão) | 3 | ~580 MB |
| Brasil | 27 | **~3,9 GB** |

São ~90 milhões de endereços no país. O download é a parte frágil: o FTP do IBGE
derruba a conexão no meio de um arquivo com alguma frequência, e por isso
`cnefe.baixar_uf` tenta até `config.TENTATIVAS_CNEFE` vezes, com espera que
dobra, e só aceita no cache um ZIP que passe por `zipfile.is_zipfile`. Um
download interrompido nunca vira cache corrompido: a gravação é em arquivo
temporário, renomeado só no fim.

## 4. Instalação e execução

### Requisitos

- Python 3.12 ou superior
- espaço em disco para o CNEFE: **~1 GB** para a Região Sul, **~5 GB** para o país
- Conexão com a internet na primeira execução

### Instalação

Criar o ambiente virtual, a partir da raiz do projeto:

```bash
python -m venv venv
```

Ativar no Windows (PowerShell):

```bash
.\venv\Scripts\Activate.ps1
```

Ativar no Linux/macOS:

```bash
source venv/bin/activate
```

Instalar as dependências:

```bash
pip install -r requirements.txt
```

Por fim, baixar as duas planilhas do BACEN (seção 3) e salvá-las em `data/raw/`.

### Execução

```bash
python main.py
```

A primeira execução baixa o CNEFE e leva bem mais tempo que as seguintes, que
reaproveitam tudo que já está em `data/raw/`. Ao final, o caminho do mapa é
impresso na tela:

```
Abra o mapa no navegador: ...\output\mapa_if_sul.html
```

Para o país inteiro:

```bash
python main.py --ufs BR
```

Ordens de grandeza medidas nesta máquina, com tudo em cache: a Região Sul leva
~1,5 min de ponta a ponta; o Brasil, ~40 min, quase todos na varredura dos 27
arquivos do CNEFE. **A varredura não é retomável** — uma falha na etapa 4 custa
a etapa 4 inteira na próxima tentativa.

Opções:

| Argumento | Efeito |
|---|---|
| `--ufs RECORTE` | recorte territorial: `BR` para as 27 UFs, o nome de uma região (`Norte`, `Nordeste`, `Centro-Oeste`, `Sudeste`, `Sul`) ou siglas separadas por vírgula (`--ufs RS,SC,PR`). Padrão: a Região Sul. |
| `--sem-cache-malha` | rebaixa a malha municipal da API do IBGE. Necessário só quando a divisão territorial muda. |
| `--sem-cache-cnefe` | rebaixa os ZIP do CNEFE (um por UF do recorte). Necessário só para se recuperar de um cache corrompido. |
| `-v`, `--verbose` | log de nível DEBUG e traceback completo em caso de falha. |

Códigos de saída: `0` sucesso, `1` falha de execução, `2` erro de uso, `130`
interrompido com Ctrl+C.

Quando algo falha, o `main.py` identifica a etapa e imprime o que fazer em vez
de um traceback — falha de rede no IBGE, certificado recusado por antivírus,
planilha ausente, ZIP corrompido e malha incompleta têm cada um sua instrução.

### Etapas do pipeline

`python main.py` roda as cinco em sequência; cada uma também roda sozinha
durante o desenvolvimento.

| # | Módulo | O que faz | Artefato |
|---|---|---|---|
| 1 | `src.etl_bacen` | recorta o território e as instituições-alvo, classifica bandeira | `data/processed/if_sul_categorizado.parquet` |
| 2 | `src.ibge_malha` | malha municipal do recorte + nome oficial e população | `data/raw/malha_municipios_sul.geojson` |
| 3 | `src.agregacao` | junta os dois pelo código IBGE, uma linha por município | `data/processed/agregado_municipio_sul.parquet` |
| 4 | `src.cnefe` | resolve a coordenada de cada ponto contra o CNEFE do Censo 2022 | `data/processed/pontos_geocodificados_sul.parquet` |
| 5 | `src.mapa` | coroplético reativo, camadas de ponto e a moldura de página | `output/mapa_if_sul.html` |

O HTML carrega os pontos como **dados**, e não como marcadores prontos: um vetor
compacto de arrays paralelos, com tabela de valores repetidos, e um laço
JavaScript que monta os discos. Popup e tooltip — do ponto e do município — são
montados no clique e no hover, e não pré-renderizados. Sem isso o arquivo
nacional passaria de 60 MB.

| | Em disco | Baixado (gzip) | Por ponto |
|---|---:|---:|---:|
| Região Sul (7.603 pontos) | 4,3 MB | 1,1 MB | 590 B |
| Brasil (30.578 pontos) | 20,6 MB | 5,1 MB | 673 B |

O `sul` nos nomes é o **slug do recorte**, e não parte fixa do nome: cada
recorte grava com o seu (`if_br_categorizado.parquet`,
`malha_municipios_sudeste.geojson`), de modo que trocar de recorte não
sobrescreve o cache do anterior. Ver `config.slug_recorte`.

A etapa 5 termina chamando `src.embutir`, que troca as tags de CDN escritas
pelo folium pelo conteúdo dos arquivos. São ~700 KB em 14 bibliotecas,
baixadas uma vez para `data/raw/libs/` e reaproveitadas — o mesmo esquema de
cache da malha e do CNEFE. No arquivo comprimido que o navegador baixa isso
custa ~50 KB, uma vez só — as bibliotecas não crescem com o recorte.

### Testes

```bash
pytest
```

Os testes leem os Parquet já gravados em `data/processed/` e verificam
invariantes do resultado — nenhuma instituição fora do escopo vazou, nenhum ponto
se perdeu no join com a malha, toda coordenada cai dentro do polígono do próprio
município, toda geometria é poligonal. Rode o pipeline antes; sem os artefatos
eles falham com a instrução.

Eles conferem o **recorte ativo**, que sem nada é a Região Sul. Para conferir os
artefatos de outro recorte:

```bash
MAPA_IF_UFS=BR pytest
```

## 5. Limitações conhecidas

### Precisão das coordenadas

Não é uniforme, e o mapa **declara o nível ponto a ponto** no popup em vez de
fingir exatidão. Os quatro níveis, do melhor para o pior:

| Nível | O que significa | Brasil | Região Sul |
|---|---|---:|---:|
| `endereco` | endereço do imóvel localizado no CNEFE — a posição é a medida no Censo 2022 | 16.231 (53,1%) | 4.469 (58,8%) |
| `logradouro` | o logradouro foi localizado, o número não; posição aproximada dentro da rua | 10.511 (34,4%) | 2.271 (29,9%) |
| `localidade` | logradouro não localizado; posição na área urbana do município | 2.579 (8,4%) | 681 (9,0%) |
| `municipio` | endereço não localizado no CNEFE; **o ponto é o do município, não o do estabelecimento** | 1.257 (4,1%) | 182 (2,4%) |

**A precisão degrada fora do Sul, e o mapa não esconde isso.** Os pontos que só
se sabe estarem no município **dobram** de 2,4% para 4,1%, e o nível mais
preciso cai quase 6 pontos percentuais. A causa é a mesma listada abaixo — a
qualidade do endereço publicado pelo BACEN —, distribuída de forma desigual pelo
país. Como o nível é declarado ponto a ponto no popup, um mapa de precisão mista
continua legível: o leitor sabe de qual caso se trata.

Os pontos em nível `municipio` **não devem ser lidos como endereço**. A contagem
por município continua correta em todos os níveis — o que varia é onde o
marcador cai dentro dele.

Três causas concentram o rebaixamento, todas na qualidade do endereço publicado
pelo BACEN: o logradouro vem abreviado e sem separador (`PCA.TIRADENTES,410`);
em **59%** das linhas o CEP é o CEP geral do município (terminado em `-000`), que
não identifica logradouro; e o número do imóvel só vem em coluna própria em
**17%** das agências (contra 89% dos postos) — nas demais ele está embutido no
texto do endereço, de onde precisa ser extraído.

Pontos que cairiam exatamente sobre a mesma coordenada são deslocados em leque
para continuarem clicáveis — nesses casos a posição exibida é, por construção,
deslocada alguns metros da real.

### Defasagem entre as fontes

As três fontes têm datas diferentes, e o mapa as sobrepõe assim mesmo:

- **BACEN — 08/2026:** é um retrato estático. Agência aberta ou fechada depois
  dessa posição não aparece. Atualizar é trocar os dois `.xlsx`, o
  `config.DATA_DADOS` e rodar de novo. O cadastro do BACEN e a divisão
  territorial do IBGE também não andam juntos: Boa Esperança do Norte/MT já
  existe num e ainda não no outro;
- **CNEFE — Censo 2022:** endereço criado depois do Censo não existe no cadastro
  e cai para um nível de precisão inferior;
- **População — estimativa do SIDRA**, não contagem censitária.

### Recorte e classificação

- **A ausência de um ponto no mapa não significa ausência de atendimento.**
  Correspondentes bancários, caixas eletrônicos fora de posto e canais digitais
  estão fora do escopo, e é justamente por eles que boa parte dos municípios sem
  agência é atendida. O mapa mede **presença física de agência e posto**, não
  acesso a serviço financeiro;
- a comparação entre as duas categorias é **assimétrica por construção**: todo o
  cooperativismo contra cinco bancos. Ela não é "cooperativas × bancos", e sim
  "cooperativas × os cinco maiores";
- a filiação ao **Ailos** depende da lista de CNPJ em `config.CNPJS_AILOS`,
  fornecida pela Central. Uma filiação nova não aparece até a lista ser
  atualizada à mão;
- a lista de bandeiras próprias é decidida pelo **corte de 100 pontos no país**
  (seção 2), que é uma régua da safra 202608 e não uma lei da natureza: um
  sistema que cresça passa a merecer bandeira, e a lista precisa ser revista a
  cada safra. Ela é escrita à mão em `etl_bacen.REGRAS_BANDEIRA_COOPERATIVA`
  justamente para que a mudança seja uma decisão revisável, e não um efeito
  colateral do dado novo;
- as bandeiras são reconhecidas pela **marca escrita na razão social ou
  no nome da instalação**. Cooperativa que não escreva a marca em nenhum dos
  dois cai em `Outra Cooperativa`. O critério é textual: uma filiação real que
  não apareça escrita em campo nenhum continua invisível para a regra, e só uma
  lista de CNPJ declarada pela central resolve — foi o caso do Ailos;
- `MARCAS_OUTRAS_COOPERATIVAS` **nomeia**, mas não reclassifica: ela alimenta
  `marca_exibicao` para o tooltip e o popup, e não muda filtro, cor nem
  contagem. Um sistema novo que apareça em safra futura fica sem nome no popup
  até ser acrescentado à lista — o resumo de `python -m src.etl_bacen` imprime
  quantas linhas ficaram nessa situação;
- a lista dos cinco bancos usa **igualdade exata**. Se o BACEN mudar a grafia de
  uma razão social, aquele banco desaparece do recorte — o teste
  `test_sub_categoria_banco_so_tem_os_cinco_alvos` existe para pegar isso.

### Geometria e ambiente

- a malha é baixada em qualidade `intermediaria` (~9 MB para os 5.570
  municípios): o contorno é generalizado, adequado para leitura em tela e não
  para medição de área ou análise de fronteira. Três municípios vêm com
  auto-interseção e são reparados na leitura (ver seção 3);
- **três pontos do país não entram no mapa**, e o log da agregação os nomeia:
  um cujo `municipio_ibge` o de-para não resolveu — um Itaú cujo município o
  BACEN publica como `GOIANA/GO`, e Goiana é em Pernambuco — e dois em Boa
  Esperança do Norte/MT, município que o cadastro do BACEN já traz e a divisão
  territorial da API de Malhas ainda não. São 3 em 30.581; o teto tolerado pelos
  testes é 0,1% do dataset, acima do qual a divergência deixa de ser anomalia de
  cadastro e passa a indicar defeito do de-para;
- **falha de TLS ao chamar o IBGE.** Em máquina com antivírus ou proxy que
  inspeciona HTTPS, todas as chamadas falham com `CERTIFICATE_VERIFY_FAILED`:
  essas ferramentas reemitem os certificados com uma autoridade raiz própria,
  instalada no repositório do Windows, onde o `certifi` não olha. O `truststore`
  resolve fazendo o Python validar pelo repositório do sistema (ver
  `src/rede.py`). É dependência **opcional** — sem ela o projeto roda
  normalmente onde não há inspeção de HTTPS.

## Publicação

O mapa é publicado no GitHub Pages, em
<https://alaindelon96.github.io/mapa-if-sul/>.

Os artefatos gerados vivem numa branch **órfã `gh-pages`**, e não na `main`. A
`main` guarda só o código; o `.gitignore` a impede de aceitar HTML gerado de
volta.

A separação tem uma razão medida. O folium sorteia os identificadores dos
elementos a cada execução, então duas gerações do MESMO dado diferem em ~106 mil
trechos e o git não consegue guardar só o delta: **cada versão commitada somava
o arquivo inteiro ao histórico, para sempre**. Com o mapa do Sul eram ~1,1 MB por
safra; com o nacional seriam ~5 MB. Numa branch órfã o custo continua existindo,
mas fica isolado do histórico do código — clonar o repositório para trabalhar
nele não arrasta mais nenhum mapa.

O que a `main` guarda da publicação é a **fonte**: `index.html` (a página de
entrada, escrita à mão, que redireciona para o mapa) e `.nojekyll` (que impede o
GitHub de processar o site com Jekyll). O que ela não guarda é o HTML gerado.

### Como publicar uma safra

```bash
git worktree add ../mapa-gh-pages gh-pages
```

```bash
cp index.html .nojekyll ../mapa-gh-pages/ && cp output/mapa_if_br.html ../mapa-gh-pages/output/
```

```bash
cd ../mapa-gh-pages && git add -A && git commit -m "safra 202608" && git push
```

O `git worktree` evita trocar de branch no diretório de trabalho — a `gh-pages`
não tem código nenhum, e um `checkout` esvaziaria a pasta do projeto por alguns
segundos.

### Limites que valem conhecer

| Limite | Valor | Onde estamos |
|---|---|---|
| GitHub: aviso por arquivo | 50 MiB | 19,6 MiB |
| GitHub: bloqueio por arquivo | 100 MiB | folgado |
| GitHub Pages: tamanho do site | 1 GB | folgado |
| GitHub Pages: banda | 100 GB/mês (soft) | depende do tráfego |
| **Cloudflare Pages: por asset** | **25 MiB (rígido)** | **19,6 MiB — 78% do teto** |

O único apertado é o da Cloudflare, caso o site migre para lá: uma safra que
cresça ~27% estoura. Se isso virar problema, o caminho já está preparado — o
mapa é gerado por recorte (`--ufs`), então dá para publicar um arquivo por
região em vez de um do país inteiro.

## Estrutura

```
mapa-if-sul/
├── data/
│   ├── raw/          # dados de entrada originais (não versionados)
│   └── processed/    # dados tratados, prontos para uso
├── src/              # código-fonte do projeto
├── output/           # artefatos gerados (mapas .html, imagens)
├── tests/            # testes automatizados (pytest)
├── requirements.txt
├── README.md
├── index.html        # página de entrada do Pages (fonte; publicada na gh-pages)
├── .nojekyll         # idem — desliga o Jekyll no GitHub Pages
└── main.py           # ponto de entrada
```

O `output/` fica vazio num clone: o HTML gerado não é versionado na `main` (ver
**Publicação**). Rode o pipeline para produzi-lo.

## Identidade visual

A página é toda em Helvetica, nas duas cores da identidade — turquesa
(`#14b8a6`) e azul-petróleo (`#0b4a5a`). Elas têm papéis fixos: o petróleo é o
texto de peso e as superfícies escuras, a turquesa é o destaque e o que está
ligado. As constantes ficam no bloco "Identidade visual" de `src/mapa.py` e são
publicadas como variáveis CSS, então mudar a identidade é editar aquelas linhas.

Fogem dela, de propósito, as cores de marca dos marcadores (`CORES_BANDEIRA`):
ali a cor é dado, e não decoração.

A safra exibida no cabeçalho e no crédito de fontes vem de `config.DATA_DADOS`.

## Dependências principais

| Biblioteca | Versão | Uso |
|---|---|---|
| pandas | 3.0.5 | manipulação de dados tabulares |
| openpyxl | 3.1.5 | leitura/escrita de arquivos `.xlsx` |
| pyarrow | 22.0.0 | engine de leitura/escrita `.parquet` |
| geopandas | 1.1.4 | dados geoespaciais em DataFrames |
| shapely | 2.1.2 | geometrias e operações espaciais |
| pyproj | 3.7.2 | projeções e transformação de coordenadas |
| folium | 0.20.0 | mapas interativos em HTML |
| requests | 2.34.2 | requisições HTTP |
| Unidecode | 1.4.0 | normalização de texto acentuado |
| truststore | 0.10.4 | valida TLS pelos certificados do sistema (ver limitações) |
| pytest | 9.1.1 | testes automatizados |
