#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pipeline de Coleta e Extração de Metadados do PubMed (MEDLINE)
Autor: Eduardo Matheus Figueira
Descrição: Pipeline automatizado que consulta a API NCBI E-utilities (esearch & efetch XML),
             realiza parsing de metadados de artigos científicos, persiste os dados limpos
             no banco SQLite (com transações otimizadas e UPSERT) e exporta os resultados
             em formato compatível com os harvesters BDTD, SciELO e OpenAlex.
"""

import os  # Módulo para interação com o sistema operacional (manipulação de caminhos e arquivos)
import sys  # Módulo para parâmetros e funções específicas do sistema (acesso a stdout, argumentos)
import time  # Módulo para controle de tempo, pausas (sleep) e medição de duração de execução
import sqlite3  # Biblioteca nativa para gerenciamento do banco de dados relacional SQLite
import logging  # Módulo para geração e emissão de mensagens de log no console/arquivo
import argparse  # Módulo para criação de interfaces de linha de comando (argumentos via terminal)
import json  # Módulo nativo para manipulação e estruturação de dados em formato JSON
import re  # Módulo para manipulação e busca de padrões com Expressões Regulares (Regex)
import xml.etree.ElementTree as ET  # Biblioteca nativa para parsing de documentos XML
import pandas as pd  # Biblioteca Pandas para estruturação de dados em DataFrames e exportação
import requests  # Biblioteca HTTP requests com suporte a requisições persistentes (Session Keep-Alive)
from requests.adapters import HTTPAdapter  # Adaptador do requests para controle avançado de conexões HTTP
from urllib3.util.retry import Retry  # Estratégia de tentativas e suporte a resiliência na camada de rede
from typing import List, Dict, Optional, Any  # Importação de anotações de tipo para Type Hints

# Objeto de log do módulo
logger: logging.Logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DE LOGGING CENTRALIZADO
# ──────────────────────────────────────────────────────────────────────────────
def setup_logging(log_file_path: Optional[str] = None) -> None:
    """
    Configura o sistema de log centralizado evitando duplicação de handlers se o script for chamado/importado múltiplas vezes.
    """
    root_logger = logging.getLogger()  # Pega o registrador raiz (root logger)
    root_logger.setLevel(logging.INFO)  # Define o nível mínimo de log para INFO
    
    # Limpa handlers pré-existentes para evitar mensagens duplicadas no console/arquivo
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')  # Formato: Data/Hora - Nível - Mensagem
    
    # Handler de saída no console (sys.stdout)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    
    # Handler para arquivo de log (se fornecido um caminho válido)
    if log_file_path:
        try:
            log_dir = os.path.dirname(log_file_path) if os.path.dirname(log_file_path) else "."
            os.makedirs(log_dir, exist_ok=True)
            open_path = log_file_path
            if sys.platform.startswith('win') and len(os.path.abspath(open_path)) >= 250 and not os.path.abspath(open_path).startswith('\\\\?\\'):
                open_path = '\\\\?\\' + os.path.abspath(open_path)
            file_handler = logging.FileHandler(open_path, mode='w', encoding='utf-8')
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            logger.info(f"Log de execução sendo gravado em: {log_file_path}")
        except Exception as e:
            logger.warning(f"Não foi possível iniciar o arquivo de log para gravação: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES E EXPRESSÕES REGULARES PRÉ-COMPILADAS (OTIMIZAÇÃO DE PERFORMANCE DE CPU)
# ──────────────────────────────────────────────────────────────────────────────
ESEARCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"  # URL da API esearch do NCBI
EFETCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"  # URL da API efetch do NCBI
BATCH_SIZE: int = 100  # Tamanho do lote de PMIDs por requisição efetch

# Expressão regular pré-compilada para extrair ano de 4 dígitos do texto
RE_YEAR_EXTRACT: re.Pattern = re.compile(r"\b(19|20)\d{2}\b")

# Mapeamento de tipos de publicação do PubMed para descritores em português
PUBLICATION_TYPE_MAPPING: Dict[str, str] = {
    "journal article": "Artigo",
    "review": "Revisão",
    "clinical trial": "Ensaio Clínico",
    "meta-analysis": "Meta-Análise",
    "systematic review": "Revisão Sistemática",
    "book": "Livro",
    "chapter": "Capítulo de Livro",
    "editorial": "Editorial",
    "letter": "Carta",
    "case reports": "Relato de Caso",
    "preprint": "Preprint"
}


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES AUXILIARES DE PARSING E HIGIENIZAÇÃO
# ──────────────────────────────────────────────────────────────────────────────
def translate_publication_type(pub_types: List[str]) -> str:
    """
    Traduz tipos de publicação do PubMed para descritores em português.
    Verifica cada tipo em ordem de especificidade e retorna o primeiro match encontrado.
    """
    if not pub_types:  # Se a lista de tipos de publicação estiver vazia
        return "Artigo"  # Retorna o tipo padrão
        
    # Verifica cada tipo retornado pelo PubMed em ordem de aparecimento
    for pt in pub_types:
        pt_lower: str = pt.lower()  # Converte para minúsculas
        if pt_lower in PUBLICATION_TYPE_MAPPING:  # Se existir no dicionário de mapeamento
            return PUBLICATION_TYPE_MAPPING[pt_lower]  # Retorna a tradução correspondente
            
    # Fallback padrão caso nenhum tipo específico seja mapeado
    return "Artigo"


# ──────────────────────────────────────────────────────────────────────────────
# GERENCIAMENTO DE ARQUIVOS DE CONFIGURAÇÃO (JSON)
# ──────────────────────────────────────────────────────────────────────────────
def create_json_config_template(file_path: str) -> None:
    """
    Cria um arquivo de modelo de configuração no formato JSON para o PubMed Harvester.
    """
    logger.info(f"Creating a new JSON configuration template: {file_path}")  # Loga criação
    template: Dict[str, Any] = {  # Dicionário de configuração padrão
        "db_path": "pubmed_metadata.db",
        "export_path": "pubmed_resultados.xlsx",
        "limit": None,
        "delay": 0.35,
        "api_key": "",
        "keywords": [
            "\"planejamento urbano\"",
            "causalidade",
            "desenvolvimento regional"
        ]
    }
    with open(file_path, "w", encoding="utf-8") as f:  # Abre o arquivo em modo de escrita UTF-8
        json.dump(template, f, ensure_ascii=False, indent=4)  # Salva o arquivo JSON com recuo formatado
    logger.info(f"Successfully generated JSON config template at {file_path}")  # Confirma no log


def read_json_config_file(file_path: str) -> Dict[str, Any]:
    """
    Lê as configurações de busca do arquivo JSON utilizando validação Pydantic com fallback.
    """
    logger.info(f"Reading configuration from JSON: {file_path}")  # Loga a leitura
    try:
        from config_app.core.config_schemas import PubMedConfig, load_and_validate_config
        validated = load_and_validate_config(file_path, PubMedConfig)  # Executa validação Pydantic
        data: Dict[str, Any] = validated.model_dump()  # Converte o modelo para dicionário Python
    except (ImportError, ModuleNotFoundError):  # Fallback se Pydantic não estiver disponível
        logger.warning("Schemas Pydantic não encontrados. Usando fallback de leitura bruta de JSON.")
        with open(file_path, "r", encoding="utf-8") as f:  # Abre o arquivo JSON
            data = json.load(f)  # Carrega o JSON bruto

    # Constrói o dicionário estronzado de configurações
    config: Dict[str, Any] = {
        "db_path": data.get("db_path", "pubmed_metadata.db"),  # Caminho do banco SQLite
        "export_path": data.get("export_path", "pubmed_resultados.xlsx"),  # Caminho da exportação
        "limit": data.get("limit"),  # Limite de registros por termo
        "delay": float(data.get("delay", 0.35)),  # Atraso entre requisições (padrao 0.35s para NCBI)
        "api_key": data.get("api_key", ""),  # Chave de API opcional NCBI E-utilities
        "keywords": data.get("keywords", [])  # Lista de palavras-chave
    }
    return config  # Retorna as configurações lidas


# ──────────────────────────────────────────────────────────────────────────────
# GERENCIADOR DE BANCO DE DADOS (SQLITE)
# ──────────────────────────────────────────────────────────────────────────────
class DatabaseManager:
    """
    Gerencia conexões com o banco de dados SQLite, criação da tabela de esquema,
    inserções em lote com suporte a UPSERT e modo WAL ativado.
    """

    SCHEMA: str = """
    CREATE TABLE IF NOT EXISTS pubmed_metadata (
        id TEXT PRIMARY KEY,
        title TEXT,
        authors TEXT,
        year TEXT,
        type_of_research TEXT,
        advisor TEXT DEFAULT 'Não Informado',
        journal TEXT,
        abstract TEXT,
        doi TEXT,
        article_url TEXT,
        keyword_query TEXT,
        harvested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    def __init__(self, db_path: str) -> None:
        self.db_path: str = db_path  # Caminho do arquivo do banco de dados SQLite
        self.conn: Optional[sqlite3.Connection] = None  # Ponteiro para a conexão SQLite
        self.init_db()  # Executa a inicialização do banco

    def init_db(self) -> None:
        """Inicializa o esquema do banco de dados e ativa o modo WAL se suportado."""
        db_dir: str = os.path.dirname(self.db_path)  # Obtém o diretório do arquivo do banco
        if db_dir:  # Se houver diretório especificado
            os.makedirs(db_dir, exist_ok=True)  # Cria a pasta caso não exista
            
        open_db_path: str = self.db_path  # Caminho do arquivo
        # Suporte a caminhos longos no Windows (Long Path Support)
        if sys.platform.startswith('win') and len(os.path.abspath(open_db_path)) >= 240 and not os.path.abspath(open_db_path).startswith('\\\\?\\'):
            open_db_path = '\\\\?\\' + os.path.abspath(open_db_path)
            
        self.conn = sqlite3.connect(open_db_path)  # Abre a conexão com o banco SQLite
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")  # Ativa modo WAL para concorrência
        except sqlite3.OperationalError as e:  # Se o WAL falhar
            logger.warning(f"Could not enable WAL mode ({e}), falling back to default journal mode.")
            
        self.conn.executescript(self.SCHEMA)  # Executa o script de criação da tabela pubmed_metadata
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pubmed_year ON pubmed_metadata (year);")  # Cria índice por ano
        self.conn.commit()  # Confirma a criação no banco
        logger.info(f"Database initialized successfully at: {self.db_path}")  # Registra o sucesso no log

    def insert_batch(self, records_list: List[Dict[str, Any]]) -> int:
        """
        Insere ou atualiza (UPSERT) uma lista de registros no banco de dados SQLite.
        Utiliza transação única (executemany) para alto desempenho, atualizando dados existentes se necessário.
        """
        if not records_list or not self.conn:  # Se a lista estiver vazia ou sem conexão ativa
            return 0  # Retorna 0 registros inseridos
            
        # Cláusula SQL UPSERT nativa do SQLite para atualização em caso de conflito de chave primária
        query: str = """
            INSERT INTO pubmed_metadata 
            (id, title, authors, year, type_of_research, advisor, journal, abstract, doi, article_url, keyword_query)
            VALUES (:id, :title, :authors, :year, :type_of_research, :advisor, :journal, :abstract, :doi, :article_url, :keyword_query)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                year = excluded.year,
                type_of_research = excluded.type_of_research,
                advisor = CASE WHEN excluded.advisor != 'Não Informado' THEN excluded.advisor ELSE pubmed_metadata.advisor END,
                journal = excluded.journal,
                abstract = CASE WHEN excluded.abstract != 'Não Informado' THEN excluded.abstract ELSE pubmed_metadata.abstract END,
                doi = CASE WHEN excluded.doi != 'Não Informado' THEN excluded.doi ELSE pubmed_metadata.doi END,
                article_url = excluded.article_url,
                keyword_query = excluded.keyword_query;
        """
        try:
            cursor = self.conn.cursor()  # Obtém o cursor da conexão
            cursor.executemany(query, records_list)  # Grava a lista em lote na transação
            self.conn.commit()  # Efetiva o commit de todas as alterações em disco
            return cursor.rowcount  # Retorna o número de linhas afetadas
        except sqlite3.Error as e:  # Se ocorrer erro durante a execução da instrução SQL
            logger.error(f"Error inserting batch into SQLite database: {e}")  # Loga a falha
            if self.conn:  # Se a conexão for válida
                self.conn.rollback()  # Executa rollback para manter integridade
            return 0

    def record_exists(self, record_id: str) -> bool:
        """
        Verifica se um registro (PMID) já existe no banco de dados SQLite.
        """
        try:
            cursor = self.conn.cursor()  # Obtém o cursor
            cursor.execute("SELECT 1 FROM pubmed_metadata WHERE id = ?", (record_id,))  # Consulta existência
            return cursor.fetchone() is not None  # Retorna True se encontrou linha, False caso contrário
        except sqlite3.Error:  # Em caso de falha de leitura no banco
            return False

    def close(self) -> None:
        """Encerra com segurança a conexão ativa com o banco de dados SQLite."""
        if self.conn:  # Se houver conexão aberta
            self.conn.close()  # Fecha o banco
            self.conn = None  # Reseta o atributo
            logger.info("Database connection closed.")  # Loga o encerramento


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE DE COLETA PUBMED
# ──────────────────────────────────────────────────────────────────────────────
class PubMedHarvesterPipeline:
    """
    Pipeline principal que consulta a API NCBI E-utilities (esearch & efetch),
    realiza parsing de XML, persiste no SQLite e coordena a exportação.
    """

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]) -> None:
        self.db: DatabaseManager = db_manager  # Gerenciador do banco de dados relacional
        self.keywords: List[str] = config.get("keywords", [])  # Lista de palavras-chave a pesquisar
        self.limit: Optional[int] = config.get("limit")  # Limite máximo de salvamentos por palavra-chave
        self.delay: float = float(config.get("delay", 0.35))  # Intervalo de espera entre chamadas de API
        self.api_key: str = config.get("api_key", "").strip()  # Chave opcional da API NCBI E-utilities
        
        # Inicializa a sessão HTTP do requests com suporte a estratégias de Retry automatizadas
        self.session: requests.Session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PubMedHarvester/1.0 (mailto:research@example.com)"
        })
        
        retry_strategy = Retry(  # Configuração do algoritmo de retries de rede
            total=5,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)  # Cria o adaptador HTTP
        self.session.mount("http://", adapter)  # Acopla a HTTP
        self.session.mount("https://", adapter)  # Acopla a HTTPS

        self.total_processed: int = 0  # Total de registros processados na execução
        self.total_inserted: int = 0  # Total de registros inseridos/atualizados no banco

    def _query_esearch(self, keyword: str) -> List[str]:
        """
        Consulta a API esearch do NCBI para recuperar a lista de PMIDs correspondentes ao termo de busca.
        """
        logger.info(f"Querying esearch for keyword: '{keyword}'...")  # Registra a consulta no log
        params: Dict[str, Any] = {  # Parâmetros da consulta esearch do NCBI
            "db": "pubmed",
            "term": keyword,
            "retmode": "json",
            "retmax": 10000  # Limite máximo retornado pelo NCBI em uma única busca
        }
        if self.api_key:  # Se a API Key NCBI estiver configurada
            params["api_key"] = self.api_key  # Adiciona aos parâmetros HTTP

        try:
            response = self.session.get(ESEARCH_URL, params=params, timeout=15)  # Executa o GET HTTP
            if response.status_code == 200:  # Se a resposta for sucesso
                data: Dict[str, Any] = response.json()  # Converte resposta para JSON
                id_list: List[str] = data.get("esearchresult", {}).get("idlist", [])  # Pega a lista de PMIDs
                logger.info(f"Found {len(id_list)} matching PMIDs in PubMed.")  # Loga quantidade de PMIDs
                return id_list  # Retorna a lista de PMIDs encontrados
            else:  # Se retornar erro HTTP
                logger.error(f"esearch returned HTTP {response.status_code}: {response.text}")
        except Exception as e:  # Se ocorrer erro na chamada HTTP
            logger.error(f"Error querying esearch: {e}")
            
        return []  # Retorna lista vazia em caso de falha

    def _fetch_records_batch(self, pmid_list: List[str]) -> str:
        """
        Busca detalhes completos em formato XML para um lote de PMIDs usando a API efetch do NCBI.
        """
        pmid_str: str = ",".join(pmid_list)  # Junta os PMIDs do lote separados por vírgula
        params: Dict[str, Any] = {  # Parâmetros da requisição efetch
            "db": "pubmed",
            "id": pmid_str,
            "retmode": "xml"
        }
        if self.api_key:  # Se houver API Key NCBI
            params["api_key"] = self.api_key  # Anexa aos parâmetros

        try:
            response = self.session.get(EFETCH_URL, params=params, timeout=30)  # Requisita os detalhes XML do lote
            if response.status_code == 200:  # Se sucesso HTTP 200
                return response.text  # Retorna o texto bruto XML do PubMed
            else:  # Se falhar o lote
                logger.error(f"efetch returned HTTP {response.status_code} for batch.")
        except Exception as e:  # Em caso de erro na requisição do lote
            logger.error(f"Error querying efetch for batch: {e}")
            
        return ""  # Retorna string vazia em caso de erro

    def _parse_xml_to_records(self, xml_data: str, keyword: str) -> List[Dict[str, Any]]:
        """
        Realiza parsing da string XML retornada pelo efetch em uma lista de dicionários de registros limpos.
        """
        records: List[Dict[str, Any]] = []  # Lista de registros parseados
        if not xml_data:  # Se o XML recebido estiver vazio
            return records  # Retorna lista vazia

        try:
            root = ET.fromstring(xml_data)  # Parseia o XML bruto com ElementTree
            for article_node in root.findall(".//PubmedArticle"):  # Itera sobre cada nó PubmedArticle do XML
                # 1. Extrai o PMID (Identificador único do artigo no PubMed)
                pmid_el = article_node.find(".//MedlineCitation/PMID")  # Elemento PMID
                pmid: Optional[str] = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None
                if not pmid:  # Se não houver PMID válido
                    continue  # Pula o artigo

                # 2. Extrai o Título completo do artigo
                title_el = article_node.find(".//ArticleTitle")  # Elemento ArticleTitle
                title: str = "".join(title_el.itertext()).strip() if title_el is not None else "Não Informado"  # Extrai todo o texto
                if title.endswith("."):  # Remove ponto final decorativo se houver
                    title = title[:-1]

                # 3. Extrai e formata os Autores
                author_names: List[str] = []  # Lista para os nomes dos autores
                author_list_el = article_node.find(".//AuthorList")  # Elemento AuthorList
                if author_list_el is not None:  # Se houver lista de autores
                    for author in author_list_el.findall("Author"):  # Itera sobre cada autor
                        last = author.find("LastName")  # Sobrenome
                        fore = author.find("ForeName")  # Nome
                        last_name: str = last.text.strip() if last is not None and last.text else ""
                        fore_name: str = fore.text.strip() if fore is not None and fore.text else ""
                        if last_name and fore_name:  # Se tiver sobrenome e nome
                            author_names.append(f"{last_name}, {fore_name}")  # Formata 'Sobrenome, Nome'
                        elif last_name:  # Apenas sobrenome
                            author_names.append(last_name)
                        elif fore_name:  # Apenas nome
                            author_names.append(fore_name)
                authors: str = "; ".join(author_names) if author_names else "Não Informado"  # Concatena autores por "; "

                # 4. Extrai o Ano de publicação (tentando Year ou parsing de MedlineDate com Regex)
                year: str = "Não Informado"  # Valor inicial de fallback
                pub_date_el = article_node.find(".//JournalIssue/PubDate")  # Elemento PubDate da edição
                if pub_date_el is not None:
                    year_el = pub_date_el.find("Year")  # Elemento Year
                    if year_el is not None and year_el.text:  # Se o ano estritamente numérico estiver presente
                        year = year_el.text.strip()  # Pega o ano
                    else:  # Caso o ano esteja dentro de uma MedlineDate genérica (ex: "2023 Spring")
                        medline_date_el = pub_date_el.find("MedlineDate")
                        if medline_date_el is not None and medline_date_el.text:
                            # Tenta extrair ano de 4 dígitos usando regex pré-compilada
                            match = RE_YEAR_EXTRACT.search(medline_date_el.text)
                            if match:  # Se encontrou ano válido
                                year = match.group(0)  # Pega os 4 dígitos do ano

                # 5. Extrai o Nome do Periódico / Revista (Journal Title)
                journal_el = article_node.find(".//Journal/Title")  # Elemento de título da revista
                journal: str = journal_el.text.strip() if journal_el is not None and journal_el.text else "Não Informado"

                # 6. Extrai o Resumo (Abstract) lidando com múltiplos blocos/seções (ex: Objetivos, Métodos, Resultados)
                abstract_parts: List[str] = []  # Lista das seções do resumo
                abstract_el = article_node.find(".//Abstract")  # Elemento Abstract
                if abstract_el is not None:  # Se o artigo contiver resumo
                    for text_el in abstract_el.findall("AbstractText"):  # Itera sobre cada parágrafo/seção
                        label: Optional[str] = text_el.get("Label")  # Rótulo da seção (ex: OBJECTIVE)
                        text_content: str = "".join(text_el.itertext()).strip()  # Conteúdo de texto limpo
                        if text_content:  # Se o conteúdo não for vazio
                            if label:  # Se tiver rótulo de seção
                                abstract_parts.append(f"{label}: {text_content}")  # Inclui 'RÓTULO: Texto'
                            else:  # Se não tiver rótulo
                                abstract_parts.append(text_content)  # Apenas o texto
                abstract: str = " ".join(abstract_parts).strip() if abstract_parts else "Não Informado"  # Junta seções

                # 7. Extrai o Identificador DOI
                doi: str = "Não Informado"  # Valor padrão para DOI
                for article_id in article_node.findall(".//ArticleIdList/ArticleId"):  # Itera sobre lista de IDs do artigo
                    if article_id.get("IdType") == "doi" and article_id.text:  # Se a tag indicar IdType='doi'
                        doi = article_id.text.strip()  # Pega a string do DOI
                        break  # Interrompe a busca

                # 8. Extrai os Tipos de Publicação e traduz para o padrão em português
                pub_types: List[str] = []  # Lista dos tipos de publicação declarados no PubMed
                pub_type_list_el = article_node.find(".//PublicationTypeList")  # Elemento PublicationTypeList
                if pub_type_list_el is not None:  # Se existir a lista de tipos
                    for pt in pub_type_list_el.findall("PublicationType"):  # Itera sobre as tags PublicationType
                        if pt.text:
                            pub_types.append(pt.text.strip())  # Guarda a descrição em inglês
                type_of_research: str = translate_publication_type(pub_types)  # Traduz para o padrão em português

                # 9. Constrói a URL pública de acesso ao artigo no PubMed
                article_url: str = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"  # URL padrão do artigo no PubMed

                # Adiciona o registro formatado e higienizado à lista final do lote
                records.append({
                    "id": pmid,
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "type_of_research": type_of_research,
                    "advisor": "Não Informado",
                    "journal": journal,
                    "abstract": abstract,
                    "doi": doi,
                    "article_url": article_url,
                    "keyword_query": keyword
                })
        except Exception as e:  # Caso ocorra falha durante o parsing do XML
            logger.error(f"Error parsing XML for batch: {e}")

        return records  # Retorna a lista de registros parseados do lote XML

    def _process_keyword(self, keyword: str) -> None:
        """
        Executa o processo completo de coleta e gravação para uma única palavra-chave.
        """
        logger.info(f"Target query: '{keyword}'")  # Loga o termo de pesquisa atual
        pmids: List[str] = self._query_esearch(keyword)  # Consulta os PMIDs no esearch
        if not pmids:  # Se nenhum PMID for retornado para a palavra-chave
            logger.info("No records matched.")  # Loga aviso
            return  # Encerra o termo atual

        # Filtra os PMIDs já coletados e armazenados previamente no banco SQLite local
        new_pmids: List[str] = [pmid for pmid in pmids if not self.db.record_exists(pmid)]
        logger.info(f"Total PMIDs: {len(pmids)} | Uncollected new PMIDs: {len(new_pmids)}")  # Loga balanço de PMIDs

        if not new_pmids:  # Se todos os PMIDs já existirem no banco de dados
            logger.info("All matching records have already been harvested. Skipping query execution.")
            return  # Pula para a próxima palavra-chave

        saved_for_keyword: int = 0  # Contador de salvamentos do termo
        
        # Processa a lista de novos PMIDs em lotes (tamanho definido por BATCH_SIZE = 100)
        for i in range(0, len(new_pmids), BATCH_SIZE):
            batch: List[str] = new_pmids[i : i + BATCH_SIZE]  # Fatia a lista para obter o lote atual
            logger.info(f"Fetching batch {i // BATCH_SIZE + 1} ({len(batch)} items)...")
            
            xml_data: str = self._fetch_records_batch(batch)  # Faz o efetch do lote XML no NCBI
            records: List[Dict[str, Any]] = self._parse_xml_to_records(xml_data, keyword)  # Converte XML para dicionários
            
            # Acumula registros em um buffer temporário em memória para gravação em lote
            batch_buffer: List[Dict[str, Any]] = []
            
            for record in records:  # Itera sobre os registros parseados do lote
                if self.limit and (saved_for_keyword + len(batch_buffer)) >= self.limit:  # Se atingiu limite do termo
                    break  # Abandona o laço interno
                    
                self.total_processed += 1  # Incrementa o total processado
                batch_buffer.append(record)  # Adiciona ao buffer do lote

            # Insere o lote completo de uma só vez no banco de dados SQLite (UPSERT)
            if batch_buffer:
                inserted_count: int = self.db.insert_batch(batch_buffer)  # Grava em transação única
                saved_for_keyword += inserted_count  # Incrementa salvos do termo
                self.total_inserted += inserted_count  # Incrementa salvos globais
                logger.info(f" -> [BATCH SAVED] Saved/Updated batch of {len(batch_buffer)} records.")

            # Respeita o atraso educado entre requisições da API NCBI
            time.sleep(self.delay)

            # Verifica se o limite de salvamento da palavra-chave foi atingido
            if self.limit and saved_for_keyword >= self.limit:
                logger.info(f"Keyword limit of {self.limit} records reached. Stopping.")
                break  # Encerra as buscas para este termo

    def run(self) -> None:
        """
        Executa o pipeline completo de coleta para todas as palavras-chave configuradas.
        """
        logger.info("=== PUBMED SYSTEM DATA HARVESTER STARTED ===")
        start_time: float = time.time()  # Registra o timestamp inicial

        for kw in self.keywords:  # Itera sobre cada palavra-chave da lista
            self._process_keyword(kw)  # Processa a palavra-chave

        elapsed: float = time.time() - start_time  # Calcula a duração total
        logger.info("=== PUBMED SYSTEM DATA HARVESTER PROCESS COMPLETED ===")
        logger.info(f"Total processed: {self.total_processed} | Total saved to DB: {self.total_inserted}")
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES DE EXPORTAÇÃO (EXCEL / CSV / JSON)
# ──────────────────────────────────────────────────────────────────────────────
def export_to_format(db_path: str, export_path: str, chunksize: int = 50000) -> bool:
    """
    Exporta a tabela pubmed_metadata do SQLite para Excel, CSV ou JSON.
    Mantém o nome das colunas compatível com os harvesters BDTD, SciELO e OpenAlex.
    """
    logger.info(f"Exporting database records to: {export_path}")
    try:
        conn: sqlite3.Connection = sqlite3.connect(db_path)  # Abre a conexão com o banco SQLite
        
        # Consulta SQL com apelidos de colunas alinhados ao padrão da família de extratores
        query: str = """
            SELECT
                authors   AS "Autores",
                title     AS "Título",
                year      AS "Ano",
                type_of_research AS "Tipo de Pesquisa",
                advisor   AS "Nome do Orientador",
                journal   AS "Universidade / Editora / Revista",
                abstract  AS "Resumo",
                article_url AS "Link para Download"
            FROM pubmed_metadata
            ORDER BY harvested_at DESC
        """
        
        ext: str = os.path.splitext(export_path)[1].lower()  # Identifica a extensão do arquivo de saída
        
        # Garante que o diretório de destino existe no sistema de arquivos
        export_dir: str = os.path.dirname(export_path)
        if export_dir:
            os.makedirs(export_dir, exist_ok=True)
        
        # Gravação em blocos (chunking) para arquivos CSV para otimização da memória RAM
        if ext == '.csv':
            first_chunk: bool = True
            total_records: int = 0
            for chunk_df in pd.read_sql_query(query, conn, chunksize=chunksize):
                chunk_df.to_csv(export_path, mode='a' if not first_chunk else 'w', index=False, header=first_chunk, encoding='utf-8')
                first_chunk = False
                total_records += len(chunk_df)
            conn.close()
            if total_records == 0:
                logger.warning("No records found in the database to export.")
                return False
            logger.info(f"Successfully exported {total_records} records to CSV.")
            return True
            
        df: pd.DataFrame = pd.read_sql_query(query, conn)  # Carrega os dados em memória para Excel/JSON
        conn.close()
        
        if df.empty:  # Se o resultado da consulta estiver vazio
            logger.warning("No records found in the database to export.")
            return False
            
        if ext in ['.xlsx', '.xls']:  # Se o formato desejado for planilha Excel
            df.to_excel(export_path, index=False)
        elif ext == '.json':  # Se o formato desejado for arquivo JSON
            df.to_json(export_path, orient='records', force_ascii=False, indent=4)
        else:  # Caso seja um formato não reconhecido, gera planilha Excel por padrão
            logger.warning(f"Unrecognized export format: {ext}. Defaulting to Excel (.xlsx).")
            df.to_excel(export_path, index=False)
            
        logger.info(f"Successfully exported {len(df)} records.")  # Confirma no log
        return True  # Retorna True indicando sucesso
    except Exception as e:  # Em caso de falha durante a exportação dos dados
        logger.error(f"Failed to export database: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# PONTO DE ENTRADA PROGRAMÁTICO (API PYTHON)
# ──────────────────────────────────────────────────────────────────────────────
def run_harvest(config: Dict[str, Any]) -> bool:
    """
    Ponto de entrada programático de alto nível para executar o pipeline PubMed Harvester.
    """
    # Configura o manipulador de arquivos de log se fornecido na estrutura de configuração
    if config.get("log_path"):
        log_dir: str = os.path.dirname(config["log_path"])
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        setup_logging(config["log_path"])
    else:
        setup_logging()

    db_manager: Optional[DatabaseManager] = None
    try:
        # Inicializa o gerenciador do banco de dados SQLite
        db_manager = DatabaseManager(config["db_path"])
        
        # Inicializa e executa o pipeline de coleta
        pipeline: PubMedHarvesterPipeline = PubMedHarvesterPipeline(db_manager, config)
        pipeline.run()

        # Executa a exportação dos dados para o arquivo configurado
        export_to_format(config["db_path"], config["export_path"])

        db_manager.close()  # Encerra o banco com segurança
        db_manager = None
        return True  # Retorna True em caso de sucesso
        
    except Exception as e:  # Se ocorrer erro na execução programática
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        return False
    finally:
        if db_manager:  # Garante encerramento do banco de dados SQLite
            db_manager.close()


# ──────────────────────────────────────────────────────────────────────────────
# INTERFACE DE LINHA DE COMANDO (CLI) E EXECUÇÃO PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    """Função principal para parsing de argumentos via linha de comando (CLI)."""
    parser = argparse.ArgumentParser(
        description="Automated Python pipeline to harvest scholarly metadata from PubMed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Define argumentos da interface de linha de comando
    parser.add_argument("--config", type=str, default=None, help="Path to JSON configuration file.")
    parser.add_argument("--keywords", type=str, nargs="+", help="Search keywords or queries (overrides config).")
    parser.add_argument("--db-path", type=str, help="Path to SQLite database file.")
    parser.add_argument("--export", type=str, help="Export target path (Excel, CSV, JSON).")
    parser.add_argument("--limit", type=int, help="Limit of records to harvest per keyword.")
    parser.add_argument("--delay", type=float, help="Delay between requests in seconds.")
    parser.add_argument("--api-key", type=str, help="NCBI E-utilities API Key.")

    args = parser.parse_args()  # Executa a leitura dos parâmetros passados no terminal
    setup_logging()  # Configura logging no terminal

    config_file: Optional[str] = args.config  # Guarda caminho do arquivo JSON se fornecido
    use_config: bool = False

    if not config_file and os.path.exists("pubmed_config.json"):  # Se o pubmed_config.json padrão existir
        config_file = "pubmed_config.json"
        use_config = True
    elif config_file and os.path.exists(config_file):  # Se o arquivo fornecido existir
        use_config = True

    config: Dict[str, Any] = {}

    if use_config and config_file:  # Se for utilizar arquivo de configuração
        try:
            config = read_json_config_file(config_file)  # Lê as opções do JSON
            logger.info(f"Successfully loaded configuration from: {config_file}")
        except Exception as e:  # Se falhar a leitura
            logger.error(f"Failed to read JSON configuration: {e}. Falling back to CLI args.")
            use_config = False

    if not use_config:  # Caso não utilize arquivo de configuração JSON
        if not args.config and not os.path.exists("pubmed_config.json"):  # Se o modelo padrão não existir
            try:
                create_json_config_template("pubmed_config.json")  # Cria o modelo pubmed_config.json
            except Exception as e:
                logger.warning(f"Could not create config template: {e}")

        # Monta o dicionário de configurações com base nos argumentos CLI
        config = {
            "keywords": args.keywords or ["\"planejamento urbano\""],
            "db_path": args.db_path or "pubmed_metadata.db",
            "export_path": args.export or "pubmed_resultados.xlsx",
            "limit": args.limit,
            "delay": args.delay or 0.35,
            "api_key": args.api_key or ""
        }
    else:
        # Sobrescreve configurações do JSON com argumentos da linha de comando se fornecidos explicitamente
        if args.keywords:
            config["keywords"] = args.keywords
        if args.db_path:
            config["db_path"] = args.db_path
        if args.export:
            config["export_path"] = args.export
        if args.limit is not None:
            config["limit"] = args.limit
        if args.delay is not None:
            config["delay"] = args.delay
        if args.api_key:
            config["api_key"] = args.api_key

    if not config.get("keywords"):  # Valida se existem palavras-chave configuradas
        logger.error("No keywords specified. Please define keywords via CLI or config file.")
        return

    try:
        # Executa o pipeline PubMed Harvester
        success: bool = run_harvest(config)
        if success:
            logger.info("Pipeline executed successfully.")
        else:
            logger.error("Pipeline finished with errors.")
    except KeyboardInterrupt:  # Interrupção pelo usuário via Ctrl+C
        logger.warning("\nPipeline execution interrupted by user.")
    except Exception as e:  # Captura falhas críticas não tratadas
        logger.critical(f"Pipeline crashed due to an unhandled exception: {e}", exc_info=True)


# Ponto de entrada do script quando executado diretamente pelo terminal
if __name__ == "__main__":
    main()  # Invoca a função principal main