# RSAC - Revisão Sistemática Assistida por Computador

O **RSAC (Revisão Sistemática Assistida por Computador)** é uma plataforma desktop e de linha de comando integrada para automação end-to-end de Revisões Sistemáticas da Literatura (SLR - *Systematic Literature Review*) e Mapeamentos Sistemáticos da Literatura.

O sistema orienta o pesquisador desde a definição rigorosa do protocolo metodológico (com suporte de Inteligência Artificial), passando pela coleta automatizada em múltiplas bases acadêmicas, deduplicação, triagem de títulos e resumos, até a leitura e extração automatizada de dados a partir dos PDFs integrais dos estudos elegíveis.

---

## Sumário

- [Visão Geral](#visão-geral)
- [Principais Funcionalidades](#principais-funcionalidades)
- [Arquitetura e Metodologias Suportadas](#arquitetura-e-metodologias-suportadas)
- [Requisitos do Sistema](#requisitos-do-sistema)
- [Instalação](#instalação)
- [Guia de Uso](#guia-de-uso)
  - [1. Inicialização do Sistema](#1-inicialização-do-sistema)
  - [2. Configuração da API do Gemini AI](#2-configuração-da-api-do-gemini-ai)
  - [3. Definição do Protocolo Metodológico](#3-definição-do-protocolo-metodológico)
  - [4. Coleta Automatizada nas Bases (Harvesters)](#4-coleta-automatizada-nas-bases-harvesters)
  - [5. Triagem de Trabalhos (Fase 1: Título e Resumo)](#5-triagem-de-trabalhos-fase-1-título-e-resumo)
  - [6. Extração de Dados dos PDFs (Fase 2)](#6-extração-de-dados-dos-pdfs-fase-2)
- [Estrutura de Diretórios](#estrutura-de-diretórios)
- [Segurança e Privacidade](#segurança-e-privacidade)
- [Licença](#licença)

---

## Visão Geral

A condução de revisões sistemáticas exige rigor metodológico, reprodutibilidade e transparência. O processo tradicional, no entanto, é suscetível a viés operacional e consome recursos significativos na formulação de strings de busca, consolidação de registros, download de artigos e preenchimento manual de matrizes de extração.

O RSAC integra em uma única solução:
1. **Modelos Metodológicos Padronizados**: Implementação direta das diretrizes PRISMA-P, Campbell, CEE/ROSES, EBSE/Kitchenham, Methodi Ordinatio e Umbrella Reviews.
2. **Assistente de Pesquisa Metodológico**: Integração com LLMs (Google Gemini) atuando com perfil de pesquisador sênior para geração automatizada de estratégias de busca booleanas puras, critérios de inclusão/exclusão e questões de extração de dados.
3. **Coletores Multibase (Harvesters)**: Módulos de extração automática para BDTD, SciELO, OpenAlex, PubMed e Scopus.
4. **Pipeline Integrado de Processamento de PDFs**: Download de artigos e extração automatizada de dados diretamente dos arquivos de texto integral.

---

## Principais Funcionalidades

- **Parceiro de Pesquisa IA**: Preenchimento automatizado de protocolos de pesquisa a partir da descrição textual do tema e objetivos do estudo.
- **Formulação de Buscas Booleanas Puras**: Geração e sanitização automática de expressões de busca sem contaminação de rótulos ou nomes de bases.
- **Suporte a 7 Metodologias Internacionais**:
  - PRISMA-P (Saúde / Estrutura PICO)
  - Campbell Collaboration (Ciências Sociais / Estrutura SPICE e SPIDER)
  - CEE / ROSES (Ecologia e Meio Ambiente / Estrutura PECO)
  - EBSE (Engenharia de Software / Métodos de Kitchenham e Wohlin)
  - Umbrella Review (Overview de Revisões / Avaliação AMSTAR-2 e ROBIS)
  - Scoping Review (PRISMA-ScR / Framework PCC)
  - Methodi Ordinatio (Cálculo do Fator Inordinatio, Ki e Fator de Impacto JCR/SJR)
- **Coleta de Literatura Automatizada**: Integração com APIs e protocolos OAI-PMH/REST para BDTD, SciELO, OpenAlex, PubMed e Scopus.
- **Algoritmo de Deduplicação**: Identificação e remoção de duplicatas por normalização de títulos, chave DOI e similaridade textual.
- **Triagem em Duas Fases**:
  - Fase 1: Análise de título e resumo (manual ou assistida em lote por IA).
  - Fase 2: Leitura de PDFs integrais e preenchimento de questões de extração.
- **Persistência Unificada em JSON**: Exportação e importação completa do estado da revisão em formato JSON padronizado.

---

## Requisitos do Sistema

- **Python**: Versão 3.8 ou superior (Recomendado Python 3.10+).
- **Sistema Operacional**: Windows 10/11, Linux ou macOS.
- **Credencial de API**: Chave de API do Google Gemini (configurada localmente).

---

## Instalação

### 1. Clonar o Repositório

```bash
git clone https://github.com/eduardomatheusfigueira/RSAC.git
cd RSAC
```

### 2. Configurar o Ambiente Virtual

No Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\activate
```

No Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar Dependências

```bash
pip install -r config_app/requirements.txt
```

---

## Guia de Uso

### 1. Inicialização do Sistema

No Windows, execute o arquivo executável de inicialização ou execute o script via terminal:

```bash
python config_app/main.py
```

### 2. Configuração da API do Gemini AI

1. Acesse a aba **Configuração Geral**.
2. No painel **Configuração do Gemini AI**, informe a Chave de API.
3. Selecione o modelo (ex: `gemini-2.5-flash` ou `gemini-3.6-flash`).
4. Clique em **Salvar Configuração** e execute o teste de conexão.

### 3. Definição do Protocolo Metodológico

1. Acesse a aba **Protocolo de Pesquisa**.
2. Selecione a metodologia desejada no menu dropdown (ex: `PRISMA-P (Saúde)`).
3. No painel **Parceiro de Pesquisa (I.A.)**, descreva o objetivo e contexto da pesquisa.
4. Clique em **Sugerir Protocolo com I.A.**.
5. O sistema preencherá automaticamente os campos PICO/PCC, critérios de elegibilidade, estratégias de busca e questões de extração de dados.
6. Clique em **Gerar Configuração de Busca e Avançar** para propagar as configurações para o fluxo de trabalho.

### 4. Coleta Automatizada nas Bases (Harvesters)

1. Na aba **Configuração Geral**, ative as bases de interesse (SciELO, BDTD, OpenAlex, PubMed, Scopus).
2. Ajuste os limites temporais e filtros de idioma.
3. Execute o módulo de coleta desejado na respectiva aba.
4. Execute o utilitário de consolidação para agrupar e deduplicar os registros recuperados.

### 5. Triagem de Trabalhos (Fase 1: Título e Resumo)

1. Acesse a aba **Triagem de Trabalhos** e carregue a sessão consolidada.
2. Analise os estudos e atribua as decisões de **Incluído** ou **Excluído** (com respectiva justificativa).
3. Utilize a função **Executar Triagem em Lote com IA** para classificação automatizada baseada nos critérios definidos.

### 6. Extração de Dados dos PDFs (Fase 2)

1. Acesse a aba **Triagem 2 - Extração**.
2. Verifique os campos de extração definidos na etapa de protocolo.
3. Coloque os arquivos `.pdf` na pasta configurada ou utilize a função de download automatizado.
4. Execute o escaneamento dos PDFs e utilize o assistente de IA para preenchimento dos campos de extração de dados.
5. Exporte os dados extraídos em formato Excel (`.xlsx`) para análise qualitativa ou quantitativa.

---

## Estrutura de Diretórios

```text
RSAC/
├── config_app/                  # Interface Gráfica e Núcleo do Sistema (Tkinter)
│   ├── main.py                  # Código-fonte principal da aplicação
│   ├── core/                    # Eschemas de validação de configuração
│   └── utils/                   # Resolução de caminhos e compatibilidade DPI
├── src/                         # Camadas de arquitetura (Clean Architecture)
│   ├── core/                    # Entidades de domínio, serviços e comandos
│   ├── infrastructure/          # Parsers Gemini, cache LRU, sanitização de texto
│   └── presentation/            # Sistema de temas, tipografia e componentes visuais
├── assets/                      # Recursos de estilo e fontes embarcadas (TTF)
├── bdtd_harvester/              # Coletor BDTD (Teses e Dissertações)
├── scielo_harvester/            # Coletor SciELO (Artigos Científicos)
├── openalex_harvester/          # Coletor OpenAlex (Base Acadêmica Global)
├── pubmed_harvester/            # Coletor PubMed (Literatura Biomédica)
├── scopus_harvester/            # Coletor Scopus (Elsevier API)
├── tests/                       # Suíte completa de testes automatizados (pytest)
├── ConfiguradorRevisao.spec     # Especificação PyInstaller para build em .exe único
├── build.bat                    # Script de compilação automatizada do executável
├── Iniciar_Configurador.bat     # Atalho de execução via Python
└── README.md                    # Documentação técnica do sistema
```

---

## Segurança e Privacidade

- **Armazenamento Local de Credenciais**: A chave de API do Gemini é armazenada exclusivamente em arquivo local (`config_gemini.json`), o qual é ignorado por padrão no controle de versão.
- **Integridade dos Dados**: O processamento de dados e os arquivos da pesquisa são mantidos no ambiente local do usuário.

---

## Licença

Este projeto está sob a licença MIT. Para mais detalhes, consulte o arquivo LICENSE.
