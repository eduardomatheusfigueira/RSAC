# 🔬 RSAC - Sistema Automatizado de Revisão Sistemática da Literatura

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![AI Partner](https://img.shields.io/badge/AI%20Partner-Google%20Gemini-orange.svg)](https://deepmind.google/technologies/gemini/)

O **RSAC (Sistema de Revisão Sistemática da Literatura)** é uma plataforma desktop e linha de comando integrada para automação end-to-end de **Revisões Sistemáticas da Literatura (SLR)** e **Mapeamentos Sistemáticos**. 

O sistema guia o pesquisador desde a **definição rigorosa do protocolo metodológico** (com suporte de Inteligência Artificial), passando pela **coleta automatizada em múltiplas bases acadêmicas**, **deduplicação**, **triagem de títulos/resumos**, até a **extração automatizada de dados a partir dos PDFs integrais**.

---

## 📌 Sumário

- [O que é o RSAC](#-o-que-é-o-rsac)
- [Principais Funcionalidades](#-principais-funcionalidades)
- [Arquitetura do Sistema](#-arquitetura-do-sistema)
- [Requisitos do Sistema](#-requisitos-do-sistema)
- [Como Instalar](#-como-instalar)
- [Como Usar (Passo a Passo)](#-como-usar-passo-a-passo)
  - [1. Iniciar a Aplicação](#1-iniciar-a-aplicação)
  - [2. Configurar a Chave da IA (Gemini)](#2-configurar-a-chave-da-ia-gemini)
  - [3. Definir o Protocolo de Pesquisa (com Parceiro IA)](#3-definir-o-protocolo-de-pesquisa-com-parceiro-ia)
  - [4. Coleta Automatizada nas Bases (Harvesters)](#4-coleta-automatizada-nas-bases-harvesters)
  - [5. Triagem de Trabalhos (Fase 1: Título e Resumo)](#5-triagem-de-trabalhos-fase-1-título-e-resumo)
  - [6. Triagem 2 - Extração de Dados dos PDFs (Fase 2)](#6-triagem-2---extração-de-dados-dos-pdfs-fase-2)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Contribuição](#-contribuição)
- [Licença](#-licença)

---

## 💡 O que é o RSAC?

A realização de uma revisão sistemática tradicional exige centenas de horas de trabalho manual na formulação de buscas, download de artigos, triagem de títulos/resumos e preenchimento de planilhas de extração.

O **RSAC** resolve esse desafio combinando:
1. **Modelos Metodológicos Consagrados**: Suporte nativo a normas internacionais como PRISMA-P, Campbell, CEE/ROSES, EBSE/Kitchenham, Methodi Ordinatio e Umbrella Reviews.
2. **Parceiro de Pesquisa IA (Google Gemini)**: Assistente metodológico que sugere estratégias de busca booleanas puras, critérios de elegibilidade PICO/PCC/SPICE e questões de extração de dados.
3. **Coletores Multi-Base (Harvesters)**: Módulos automatizados para consulta simultânea e estruturada nas principais bases científicas nacionais e internacionais.
4. **Pipeline Automatizado de PDFs**: Download automatizado de textos integrais e leitura/extração inteligente de dados suportada por visão computacional e LLMs.

---

## ✨ Principais Funcionalidades

- 🤖 **Parceiro de Pesquisa IA**: Escreva a ideia e os objetivos da sua pesquisa e a IA preenche todo o protocolo metodológico selecionado.
- 📋 **7 Metodologias Internacionais**:
  - **PRISMA-P** (Área da Saúde / PICO)
  - **Campbell Collaboration** (Ciências Sociais / SPICE / SPIDER)
  - **CEE / ROSES** (Ecologia e Meio Ambiente / PECO)
  - **EBSE** (Engenharia de Software / Kitchenham & Wohlin)
  - **Umbrella Review** (Overviews de Revisões / AMSTAR-2 & ROBIS)
  - **Scoping Review** (PRISMA-ScR / Framework PCC)
  - **Methodi Ordinatio** (Cálculo do Fator Inordinatio, Ki e JCR)
- 🔍 **Coleta Automatizada Multi-Base**:
  - **BDTD** (Biblioteca Digital Brasileira de Teses e Dissertações)
  - **SciELO** (Scientific Electronic Library Online)
  - **OpenAlex** (Base Científica Global)
  - **PubMed** (Literatura Médica e Biológica via Entrez API)
  - **Scopus** (Elsevier API)
- 🧹 **Deduplicação Inteligente**: Algoritmo de identificação de duplicatas por título normalizado, DOI e similaridade textual.
- 🎯 **Triagem Fase 1 (Título & Resumo)**: Triagem manual interativa ou em lote por IA com justificativas científicas para inclusão/exclusão.
- 📄 **Triagem Fase 2 & Extração de PDFs**: Leitura automatizada de PDFs, sincronização de campos de extração definidos no protocolo e preenchimento assistido por IA.
- 💾 **Esquema JSON Unificado**: Salve e retome todo o estado da sua revisão em um único arquivo JSON padronizado.

---

## 🛠️ Requisitos do Sistema

- **Sistema Operacional**: Windows 10/11, Linux ou macOS.
- **Python**: Versão **3.8 ou superior** (Recomendado Python 3.10+).
- **Chave de API do Google Gemini** (Gratuita): Obtenha no [Google AI Studio](https://aistudio.google.com/).

---

## 📦 Como Instalar

### 1. Clonar o Repositório

```bash
git clone https://github.com/eduardomatheusfigueira/RSAC.git
cd RSAC
```

### 2. Criar e Ativar um Ambiente Virtual (Recomendado)

- **No Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\activate
  ```

- **No Linux / macOS:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 3. Instalar as Dependências

```bash
pip install -r config_app/requirements.txt
```
*(Caso queira rodar harvesters específicos individualmente, instale os `requirements.txt` das respectivas pastas).*

---

## 🚀 Como Usar (Passo a Passo)

### 1. Iniciar a Aplicação

No Windows, você pode simplesmente dar um duplo clique no arquivo `Iniciar_Configurador.bat` ou rodar via terminal:

```bash
python config_app/main.py
```

---

### 2. Configurar a Chave da IA (Gemini)

1. Acesse a aba **Configuração Geral**.
2. No painel **Configuração do Gemini AI**, insira sua **Chave de API (API Key)**.
3. Escolha o modelo desejado (ex: `gemini-2.5-flash` ou `gemini-3.6-flash`).
4. Clique em **Salvar Configuração** e depois em **Testar Conexão API** para confirmar.

---

### 3. Definir o Protocolo de Pesquisa (com Parceiro IA)

1. Acesse a aba **Protocolo de Pesquisa**.
2. Escolha o protocolo metodológico desejado no dropdown (ex: `PRISMA-P (Saúde)`).
3. No painel lateral **🤖 Parceiro de Pesquisa (I.A.)**:
   - Escreva o tema da sua pesquisa e o que quer descobrir (ex: *"Quero investigar o impacto do uso de inteligência artificial no diagnóstico precoce de diabetes tipo 2"*).
   - Clique em **✨ Sugerir Protocolo com I.A.**.
4. A IA preencherá automaticamente o formulário do protocolo com:
   - Título e escopo do projeto
   - Detalhamento PICO / PCC / SPICE
   - Estratégia de busca em strings booleanas puras (ex: `("artificial intelligence" OR "ai") AND ("diabetes")`)
   - Critérios de Inclusão e Exclusão
   - **Questões / Campos de Extração de Dados**
5. Ajuste os campos manualmente se necessário e clique em **Gerar Configuração de Busca e Avançar**.

---

### 4. Coleta Automatizada nas Bases (Harvesters)

1. Na aba **Configuração Geral**, selecione as bases que deseja consultar (SciELO, BDTD, OpenAlex, PubMed, Scopus).
2. Configure os filtros temporais (ex: 2018 a 2026) e de idioma.
3. Clique em **Iniciar Harvester / Busca Automatizada** na aba da base desejada.
4. Ao final da busca, utilize o script de consolidação para agrupar e deduplicar os resultados em um único arquivo de sessão.

---

### 5. Triagem de Trabalhos (Fase 1: Título e Resumo)

1. Acesse a aba **Triagem de Trabalhos**.
2. Carregue o arquivo de sessão consolidado (`.json` ou `.csv`).
3. Navegue pelos artigos na lista:
   - Leia o título e resumo.
   - Marque como **Incluído** ou **Excluído** (indicando o motivo da exclusão).
4. **Triagem Assistida por IA**:
   - Clique em **🤖 Analisar com Parceiro I.A.** para obter uma sugestão automática de triagem baseada nos seus critérios de inclusão/exclusão.
   - Use o modo **⚡ Executar Triagem em Lote com IA** para processar centenas de trabalhos automaticamente.

---

### 6. Triagem 2 - Extração de Dados dos PDFs (Fase 2)

1. Acesse a aba **Triagem 2 - Extração**.
2. As **Questões de Extração de Dados** definidas no seu protocolo aparecerão automaticamente na lista de campos.
3. Clique em **Baixar todos os PDFs** ou coloque os arquivos `.pdf` na pasta indicada.
4. Clique em **Escanear Pasta de PDFs**.
5. Ao selecionar cada trabalho incluído:
   - O texto do PDF será lido automaticamente.
   - Preencha as respostas para cada campo de extração manualmente ou clique em **🤖 Preencher Campos com IA (Gemini)** para que a IA extraia as respostas diretamente do texto do artigo.
6. Exporte os dados consolidados em planilha Excel (`.xlsx`) para análise final ou meta-análise.

---

## 📁 Estrutura do Projeto

```text
RSAC/
├── config_app/                  # Interface Gráfica Principal (Tkinter)
│   ├── main.py                  # Aplicação principal (GUI, IA Partner & Triagem)
│   └── config_gemini.json       # Configuração local da API Key (ignorado pelo Git)
├── bdtd_harvester/              # Coletor BDTD (Teses e Dissertações)
├── scielo_harvester/            # Coletor SciELO (Artigos Científicos)
├── openalex_harvester/          # Coletor OpenAlex (Base Global)
├── pubmed_harvester/            # Coletor PubMed (Medicina / Biologia)
├── scopus_harvester/            # Coletor Scopus (Elsevier API)
├── consolidar_e_deduplicar.py   # Script de consolidação e deduplicação de buscas
├── baixar_pdfs.py               # Downloader automatizado de PDFs integrais
├── Iniciar_Configurador.bat     # Atalho de inicialização no Windows
├── Procedimento_Uso_Sistema_Revisao.md # Manual detalhado de procedimentos metodológicos
└── README.md                    # Documentação do projeto
```

---

## 🛡️ Segurança e Privacidade

- **Chave da API Gemini**: Sua chave da API é armazenada **exclusivamente de forma local** no seu computador (`config_gemini.json`) e **nunca é enviada** a repositórios remotos.
- **Privacidade dos Dados**: Suas consultas de pesquisa e arquivos de dados permanecem na sua máquina.

---

## 🤝 Contribuição

Contribuições são muito bem-vindas! Sinta-se à vontade para abrir uma *Issue* ou enviar um *Pull Request*:

1. Faça um Fork do projeto
2. Crie uma branch para sua funcionalidade (`git checkout -b feature/minha-funcionalidade`)
3. Faça o commit das suas alterações (`git commit -m 'Adiciona minha funcionalidade'`)
4. Envie a branch (`git push origin feature/minha-funcionalidade`)
5. Abra um Pull Request

---

## 📄 Licença

Este projeto está licenciado sob a licença **MIT** - veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

<p align="center">
  Desenvolvido com 💙 para potencializar a pesquisa científica rigorosa e transparente.
</p>
