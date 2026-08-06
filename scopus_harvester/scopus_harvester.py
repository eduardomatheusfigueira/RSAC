#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pipeline de Coleta e Extração de Metadados do Scopus
Autor: Eduardo Matheus Figueira
Descrição: Pipeline automatizado que consulta a API Scopus Search (api.elsevier.com),
             suporta a visualização COMPLETE (lista completa de autores e resumo) com fallback
             automático para STANDARD e a API de Abstract Retrieval em caso de erros 403.
             Persiste os dados no SQLite (com transações em lote e UPSERT) e exporta os resultados
             em formato compatível com os harvesters BDTD, SciELO, OpenAlex e PubMed.
"""

import os  # Módulo para interação com o sistema operacional (manipulação de caminhos e arquivos)
import sys  # Módulo para parâmetros e funções específicas do sistema (acesso a stdout, argumentos)
import time  # Módulo para controle de tempo, pausas (sleep) e medição de duração de execução
import sqlite3  # Biblioteca nativa para gerenciamento do banco de dados relacional SQLite
import logging  # Módulo para geração e emissão de mensagens de log no console/arquivo
import argparse  # Módulo para criação de interfaces de linha de comando (argumentos via terminal)
import json  # Módulo nativo para manipulação e estruturação de dados em formato JSON
import re  # Módulo para manipulação e busca de padrões com Expressões Regulares (Regex)
import pandas as pd  # Biblioteca Pandas para estruturação de dados em DataFrames e exportação
import requests  # Biblioteca HTTP requests com suporte a requisições persistentes (Session Keep-Alive)
from requests.adapters import HTTPAdapter  # Adaptador do requests para controle avançado de conexões HTTP
from urllib3.util.retry import Retry  # Estratégia de tentativas e suporte a resiliência na camada de rede
from typing import List, Dict, Optional, Any, Union  # Importação de anotações de tipo para Type Hints

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
# CONSTANTES E LIMITES DA API (OTIMIZAÇÃO E REGRAS DE NEGÓCIO)
# ──────────────────────────────────────────────────────────────────────────────
SCOPUS_SEARCH_URL: str = "https://api.elsevier.com/content/search/scopus"  # URL da API de busca do Scopus
ABSTRACT_RETRIEVAL_URL: str = "https://api.elsevier.com/content/abstract/eid/"  # URL da API de recuperação de resumos
SCOPUS_MAX_OFFSET: int = 5000  # Limite máximo de offset permitido pela API padrão do Scopus


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES AUXILIARES DE PARSING E HIGIENIZAÇÃO
# ──────────────────────────────────────────────────────────────────────────────
def translate_format(subtype_desc: Optional[str], agg_type: Optional[str]) -> str:
    """
    Traduz subtypeDescription ou prism:aggregationType do Scopus para descritores em português.
    """
    val: str = (subtype_desc or agg_type or "").lower().strip()  # Converte valor para minúsculas
    if not val:  # Se não houver valor informado
        return "Artigo"  # Retorna o padrão
    if "article" in val:  # Se contiver 'article'
        return "Artigo"  # Traduz para Artigo
    elif "review" in val:  # Se contiver 'review'
        return "Revisão"  # Traduz para Revisão
    elif "conference" in val or "proceeding" in val:  # Se for de conferência
        return "Artigo de Conferência"  # Traduz para Artigo de Conferência
    elif "chapter" in val:  # Se for capítulo de livro
        return "Capítulo de Livro"  # Traduz para Capítulo de Livro
    elif "book" in val:  # Se for livro
        return "Livro"  # Traduz para Livro
    elif "thesis" in val or "dissertation" in val:  # Se for tese/dissertação
        return "Tese/Dissertação"  # Traduz para Tese/Dissertação
    return val.capitalize()  # Caso contrário, retorna o termo capitalizado


def extract_authors(entry: Dict[str, Any]) -> str:
    """
    Extrai e junta os nomes dos autores em uma única string separada por ponto e vírgula.
    Lida com a estrutura de dicionário ou lista retornada pela API do Scopus.
    """
    authors_data: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = entry.get("author")  # Obtém o nó de autores
    if authors_data:  # Se houver dados de autores
        # Verifica se é um único autor (dict) ou lista de autores
        if isinstance(authors_data, dict):
            authors_data = [authors_data]
        
        author_list: List[str] = []  # Lista para armazenar nomes de autores
        for auth in authors_data:  # Itera sobre os autores
            name: Optional[str] = auth.get("authname")  # Tenta pegar o nome formatado authname
            if not name:  # Se não houver authname
                surname: str = auth.get("surname", "")  # Pega o sobrenome
                given: str = auth.get("given-name", "")  # Pega o primeiro nome
                if surname or given:  # Se algum existir
                    name = f"{surname}, {given}".strip(", ")  # Formata 'Sobrenome, Nome'
            if name:  # Se o nome formatado for válido
                author_list.append(name.strip())  # Adiciona à lista
        
        if author_list:  # Se a lista contiver autores
            return "; ".join(author_list)  # Junta os nomes por "; "

    # Fallback para dc:creator (frequentemente o nome do primeiro autor como string na visualização STANDARD)
    creator: Optional[str] = entry.get("dc:creator")
    if creator:  # Se dc:creator existir
        return creator.strip()  # Retorna o nome do criador limpo

    return "Não Informado"  # Retorna o valor de fallback


def extract_url(entry: Dict[str, Any]) -> str:
    """
    Extrai a URL web mais relevante para o documento no Scopus.
    Prioriza links com referência 'scopus', depois 'self', e finalmente DOI ou EID.
    """
    links: Union[List[Dict[str, str]], Dict[str, str]] = entry.get("link", [])  # Obtém os links do registro
    if isinstance(links, dict):  # Se for um único dicionário de link
        links = [links]

    # 1. Procura por um link com atributo @ref ou @rel igual a 'scopus'
    for link in links:
        ref: Optional[str] = link.get("@ref") or link.get("@rel")
        if ref == "scopus":
            href: Optional[str] = link.get("@href")
            if href:
                return href

    # 2. Tenta URL com relação 'self' (geralmente a URL da própria API ou recurso)
    for link in links:
        ref = link.get("@ref") or link.get("@rel")
        if ref == "self":
            href = link.get("@href")
            if href:
                return href

    # 3. Fallback usando DOI para montar URL direta do resolvedor
    doi: Optional[str] = entry.get("prism:doi")
    if doi:
        return f"https://doi.org/{doi}"

    # 4. Fallback usando EID para montar a URL da página do Scopus
    eid: Optional[str] = entry.get("eid")
    if eid:
        return f"https://www.scopus.com/record/display.uri?eid={eid}&origin=resultslist"

    return "Não Informado"  # Retorna valor padrão se nenhuma URL for encontrada


def fetch_abstract_retrieval(session: requests.Session, eid: str, headers: Dict[str, str]) -> str:
    """
    Consulta a API de Abstract Retrieval como fallback quando a visualização STANDARD está ativa.
    """
    url: str = f"{ABSTRACT_RETRIEVAL_URL}{eid}"  # Monta a URL de recuperação pelo EID
    params: Dict[str, str] = {"view": "META_ABS"}  # Define a visualização META_ABS
    
    # Copia headers para evitar mutar o dicionário original
    req_headers: Dict[str, str] = headers.copy()
    req_headers["Accept"] = "application/json"
    
    try:
        logger.info(f"Querying Abstract Retrieval API for EID: {eid}...")  # Loga a chamada secundária
        response = session.get(url, headers=req_headers, params=params, timeout=15)  # Requisita a API
        if response.status_code == 200:  # Se sucesso HTTP 200
            data: Dict[str, Any] = response.json()  # Converte em JSON
            ret_response: Dict[str, Any] = data.get("abstracts-retrieval-response", {})
            coredata: Dict[str, Any] = ret_response.get("coredata", {})
            desc: Any = coredata.get("dc:description")  # Extrai a descrição do resumo
            if desc:  # Se houver descrição
                if isinstance(desc, dict):  # Trata variação em que dc:description vem como dict contendo a chave '$'
                    desc = desc.get("$", "")
                return str(desc).strip()  # Retorna o resumo limpo
        elif response.status_code == 403:  # Se acesso for negado pela assinatura
            logger.warning(f"Abstract retrieval for EID {eid} returned 403 Forbidden (restricted subscription).")
    except Exception as e:  # Caso ocorra falha na requisição secundária
        logger.error(f"Failed to fetch abstract for EID {eid} via Abstract Retrieval: {e}")

    return "Não disponível na busca padrão (requer view=COMPLETE)"  # Retorna mensagem explicativa em falha


# ──────────────────────────────────────────────────────────────────────────────
# GERENCIAMENTO DE ARQUIVOS DE CONFIGURAÇÃO (JSON)
# ──────────────────────────────────────────────────────────────────────────────
def create_json_config_template(file_path: str) -> None:
    """
    Cria um arquivo de modelo de configuração no formato JSON para o Scopus Harvester.
    """
    logger.info(f"Creating a new JSON configuration template: {file_path}")  # Loga a criação
    template: Dict[str, Any] = {  # Define a estrutura de exemplo do arquivo de configuração
        "db_path": "scopus_metadata.db",
        "export_path": "scopus_resultados.xlsx",
        "limit": None,
        "delay": 1.0,
        "api_key": "",
        "insttoken": "",
        "view": "COMPLETE",
        "keywords": [
            "\"planejamento urbano\"",
            "causalidade",
            "desenvolvimento regional"
        ]
    }
    with open(file_path, "w", encoding="utf-8") as f:  # Abre o arquivo para escrita UTF-8
        json.dump(template, f, ensure_ascii=False, indent=4)  # Escreve o JSON formatado
    logger.info(f"Successfully generated JSON config template at {file_path}")  # Confirma geração


def read_json_config_file(file_path: str) -> Dict[str, Any]:
    """
    Lê as configurações de busca do arquivo JSON utilizando validação Pydantic com fallback.
    """
    logger.info(f"Reading configuration from JSON: {file_path}")  # Loga a leitura
    try:
        from config_app.core.config_schemas import ScopusConfig, load_and_validate_config
        validated = load_and_validate_config(file_path, ScopusConfig)  # Valida pelo schema Pydantic
        data: Dict[str, Any] = validated.model_dump()  # Extrai dicionário dos dados validados
    except (ImportError, ModuleNotFoundError):  # Fallback caso Pydantic não esteja disponível
        logger.warning("Schemas Pydantic não encontrados. Usando fallback de leitura bruta de JSON.")
        with open(file_path, "r", encoding="utf-8") as f:  # Abre o arquivo JSON
            data = json.load(f)  # Carrega o JSON bruto

    # Constrói o dicionário estronzado de configurações
    config: Dict[str, Any] = {
        "keywords": data.get("keywords", []),  # Lista de palavras-chave
        "db_path": data.get("db_path", "scopus_metadata.db"),  # Caminho do banco SQLite
        "export_path": data.get("export_path", "scopus_resultados.xlsx"),  # Caminho da exportação
        "limit": data.get("limit"),  # Limite máximo de registros por palavra-chave
        "delay": float(data.get("delay", 1.0)),  # Atraso em segundos entre requisições
        "api_key": data.get("api_key", ""),  # Chave de API do Scopus
        "insttoken": data.get("insttoken", ""),  # Token de instituição opcional
        "view": data.get("view", "COMPLETE")  # Modo de visualização (COMPLETE ou STANDARD)
    }
    return config  # Retorna o dicionário de configurações


# ──────────────────────────────────────────────────────────────────────────────
# GERENCIADOR DE BANCO DE DADOS (SQLITE)
# ──────────────────────────────────────────────────────────────────────────────
class DatabaseManager:
    """
    Gerencia conexões com o banco de dados SQLite, criação da tabela de esquema,
    inserções em lote com suporte a UPSERT e modo WAL ativado.
    """

    SCHEMA: str = """
    CREATE TABLE IF NOT EXISTS scopus_metadata (
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
        self.db_path: str = db_path  # Caminho do arquivo de banco de dados SQLite
        self.conn: Optional[sqlite3.Connection] = None  # Ponteiro de conexão SQLite
        self.init_db()  # Executa o método de inicialização

    def init_db(self) -> None:
        """Inicializa o esquema do banco de dados e ativa o modo WAL se suportado."""
        db_dir: str = os.path.dirname(self.db_path)  # Obtém o diretório do arquivo do banco
        if db_dir:  # Se houver diretório especificado
            os.makedirs(db_dir, exist_ok=True)  # Cria a pasta caso não exista
            
        open_db_path: str = self.db_path  # Caminho para abertura
        # Suporte a caminhos longos no Windows (Long Path Support)
        if sys.platform.startswith('win') and len(os.path.abspath(open_db_path)) >= 240 and not os.path.abspath(open_db_path).startswith('\\\\?\\'):
            open_db_path = '\\\\?\\' + os.path.abspath(open_db_path)
            
        self.conn = sqlite3.connect(open_db_path)  # Conecta ao arquivo do banco SQLite
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")  # Ativa o modo de gravação WAL para concorrência
        except sqlite3.OperationalError as e:  # Se o sistema de arquivos não suportar WAL
            logger.warning(f"Could not enable WAL mode ({e}), falling back to default journal mode.")
            
        self.conn.executescript(self.SCHEMA)  # Cria a tabela scopus_metadata
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_scopus_year ON scopus_metadata (year);")  # Cria índice temporal
        self.conn.commit()  # Efetiva as alterações no banco de dados
        logger.info(f"Database initialized successfully at: {self.db_path}")  # Loga sucesso da inicialização

    def insert_batch(self, records_list: List[Dict[str, Any]]) -> int:
        """
        Insere ou atualiza (UPSERT) uma lista de registros no banco de dados SQLite.
        Utiliza transação única (executemany) para alto desempenho, atualizando dados existentes se necessário.
        """
        if not records_list or not self.conn:  # Se a lista de registros estiver vazia ou sem conexão ativa
            return 0  # Retorna 0 registros inseridos
            
        # Cláusula SQL UPSERT nativa para inserir ou atualizar em caso de chave primária duplicada
        query: str = """
            INSERT INTO scopus_metadata 
            (id, title, authors, year, type_of_research, advisor, journal, abstract, doi, article_url, keyword_query)
            VALUES (:id, :title, :authors, :year, :type_of_research, :advisor, :journal, :abstract, :doi, :article_url, :keyword_query)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                year = excluded.year,
                type_of_research = excluded.type_of_research,
                advisor = CASE WHEN excluded.advisor != 'Não Informado' THEN excluded.advisor ELSE scopus_metadata.advisor END,
                journal = excluded.journal,
                abstract = CASE WHEN excluded.abstract != 'Não Informado' THEN excluded.abstract ELSE scopus_metadata.abstract END,
                doi = CASE WHEN excluded.doi != 'Não Informado' THEN excluded.doi ELSE scopus_metadata.doi END,
                article_url = excluded.article_url,
                keyword_query = excluded.keyword_query;
        """
        try:
            cursor = self.conn.cursor()  # Obtém o cursor da conexão
            cursor.executemany(query, records_list)  # Grava o lote inteiro em uma transação única
            self.conn.commit()  # Confirma a transação em disco
            return cursor.rowcount  # Retorna o número de linhas afetadas
        except sqlite3.Error as e:  # Se ocorrer erro durante a instrução SQL
            logger.error(f"Error inserting batch into SQLite database: {e}")  # Loga o erro
            if self.conn:  # Se a conexão for válida
                self.conn.rollback()  # Desfaz a transação para evitar inconsistências
            return 0

    def record_exists(self, record_id: str) -> bool:
        """
        Verifica se um registro já existe no banco de dados.
        Utilizado para evitar chamadas desnecessárias à API secundária de Abstract Retrieval.
        """
        try:
            cursor = self.conn.cursor()  # Obtém o cursor
            cursor.execute("SELECT 1 FROM scopus_metadata WHERE id = ?", (record_id,))  # Consulta se o ID existe
            return cursor.fetchone() is not None  # Retorna True se o ID já existia
        except sqlite3.Error:  # Em caso de falha de consulta no banco
            return False

    def close(self) -> None:
        """Encerra com segurança a conexão ativa com o banco de dados SQLite."""
        if self.conn:  # Se houver conexão aberta
            self.conn.close()  # Fecha a conexão
            self.conn = None  # Reseta o ponteiro
            logger.info("Database connection closed.")  # Registra encerramento no log


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE DE COLETA SCOPUS
# ──────────────────────────────────────────────────────────────────────────────
class ScopusHarvesterPipeline:
    """
    Pipeline principal que consulta a API Scopus Search com paginação por cursor (ou offset como fallback),
    lida com as restrições de visualização COMPLETE vs STANDARD, persiste no SQLite e coordena a exportação.
    """

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]) -> None:
        self.db: DatabaseManager = db_manager  # Gerenciador do banco relacional
        self.keywords: List[str] = config["keywords"]  # Lista de termos de busca
        self.limit: Optional[int] = config.get("limit")  # Limite de salvamento por palavra-chave
        self.delay: float = float(config.get("delay", 1.0))  # Atraso entre requisições de página
        self.api_key: str = config.get("api_key", "")  # Chave de API do Scopus
        self.view: str = config.get("view", "COMPLETE")  # Modo de visualização desejado (COMPLETE ou STANDARD)
        self.insttoken: str = config.get("insttoken", "")  # Token de instituição opcional

        # Configuração inicial de cabeçalhos HTTP com autenticação
        self.headers: Dict[str, str] = {
            "Accept": "application/json",
            "X-ELS-APIKey": self.api_key
        }
        if self.insttoken:  # Se houver Insttoken
            self.headers["X-ELS-Insttoken"] = self.insttoken  # Adiciona ao cabeçalho

        # Inicializa a sessão HTTP persistente com suporte a estratégia de Retry automatizado
        self.session: requests.Session = requests.Session()
        self.session.headers.update(self.headers)
        
        retry_strategy = Retry(  # Estratégia de re-tentativa para falhas temporárias de rede
            total=5,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)  # Instancia adaptador resiliênte
        self.session.mount("http://", adapter)  # Acopla a HTTP
        self.session.mount("https://", adapter)  # Acopla a HTTPS

        self.total_processed: int = 0  # Total de registros processados
        self.total_inserted: int = 0  # Total de registros inseridos no banco
        self.raw_results_cache: List[Dict[str, Any]] = []  # Cache de resultados brutos
        
        # Controle de paginação (pode migrar automaticamente de 'cursor' para 'offset')
        self.pagination_mode: str = "cursor"
        self.start_offset: int = 0

    def _fetch_page(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Busca uma página de resultados da API do Scopus com tratamento de fallback automático para view e paginação.
        """
        try:
            logger.info(f"Request parameters: {params}")  # Loga os parâmetros da chamada
            response = self.session.get(SCOPUS_SEARCH_URL, params=params, timeout=30)  # Requisita a API do Scopus

            if response.status_code == 200:  # Se a chamada foi bem-sucedida (HTTP 200)
                return response.json()  # Retorna o dicionário JSON retornado
            
            elif response.status_code in [400, 401, 403]:  # Se houver erro de permissão ou parâmetro
                # Verifica se é erro de falta de autorização de view ou restrição de uso de cursor
                is_view_auth_error: bool = False
                is_cursor_restricted: bool = False
                try:
                    err_json: Dict[str, Any] = response.json()  # Parseia a mensagem de erro do Scopus
                    status_text: str = err_json.get("service-error", {}).get("status", {}).get("statusText", "")
                    if "not authorized to access the requested view" in status_text.lower():
                        is_view_auth_error = True
                    if "use of the cursor parameter is restricted" in status_text.lower():
                        is_cursor_restricted = True
                except Exception:
                    pass

                # Se o cursor for restrito pela chave/IP, faz o fallback imediato para paginação baseada em offset (start/count)
                if is_cursor_restricted:
                    logger.warning(
                        "Cursor parameter is restricted for this API key/IP. "
                        "Falling back to offset-based pagination (start/count)."
                    )
                    self.pagination_mode = "offset"
                    if "cursor" in params:
                        del params["cursor"]
                    params["start"] = 0
                    self.start_offset = 0
                    return self._fetch_page(params)  # Retry recursivo com novo modo de paginação

                # Se a view requisitada era COMPLETE e houve erro de autorização, migra automaticamente para STANDARD
                if params.get("view") == "COMPLETE" and (response.status_code in [401, 403] or is_view_auth_error):
                    logger.warning(
                        f"HTTP {response.status_code} View Authorization issue encountered with view=COMPLETE. "
                        "Your API key or IP address does not have entitlement to retrieve complete records. "
                        "Migrating to view=STANDARD for this run."
                    )
                    self.view = "STANDARD"  # Altera a view padrão da instância
                    params["view"] = "STANDARD"  # Atualiza os parâmetros
                    return self._fetch_page(params)  # Retry recursivo com a view STANDARD
                else:  # Caso o erro de permissão persista mesmo com a view STANDARD
                    logger.error(
                        f"Scopus API Access Error ({response.status_code}). Please verify your API Key "
                        f"and network connection (VPN/Institutional IP). Response: {response.text}"
                    )
            elif response.status_code == 429:  # Se exceder o limite de requisições da API
                logger.warning("Scopus API rate limit exceeded (429). Sleeping for 5 seconds...")
                time.sleep(5.0)  # Aguarda 5 segundos
                return self._fetch_page(params)  # Retry recursivo
            else:  # Outro erro HTTP inesperado
                logger.error(f"Scopus API returned HTTP {response.status_code}: {response.text}")
                
        except requests.RequestException as e:  # Se ocorrer erro na camada de transporte de rede
            logger.error(f"Network error querying Scopus API: {e}")
            
        return None  # Retorna None caso a chamada falhe definitivamente

    def _process_keyword(self, keyword: str) -> None:
        """
        Executa a paginação por cursor (ou offset) para uma única palavra-chave.
        """
        logger.info(f"Target query: '{keyword}'")  # Registra a palavra-chave atual no log
        
        # Monta os parâmetros iniciais da busca no Scopus
        params: Dict[str, Any] = {
            "query": keyword,
            "count": 25,  # Tamanho padrão ótimo por página no Scopus (25)
            "view": self.view  # Modo de visualização (COMPLETE ou STANDARD)
        }
        
        if self.pagination_mode == "cursor":  # Se estiver usando paginação por cursor
            params["cursor"] = "*"  # Cursor inicial
        else:  # Se estiver usando paginação por offset
            params["start"] = 0  # Offset inicial

        saved_for_keyword: int = 0  # Salvos da palavra-chave
        processed_for_keyword: int = 0  # Processados da palavra-chave
        page_num: int = 1  # Número da página atual
        total_results: Optional[str] = None  # Total de resultados no catálogo

        logger.info("Initiating search queries on Scopus API...")

        while True:  # Loop de páginas
            logger.info(f"Requesting page {page_num}...")
            data: Optional[Dict[str, Any]] = self._fetch_page(params)  # Busca os dados da página
            
            if data is None:  # Se a requisição retornar None (falha)
                logger.error("Failed to retrieve data page. Stopping current keyword.")
                break  # Abandona a palavra-chave

            results_payload: Dict[str, Any] = data.get("search-results", {})  # Obtém a raiz search-results
            
            # Extrai o número total de registros no catálogo Scopus se ainda não definido
            if total_results is None:
                total_results = results_payload.get("opensearch:totalResults", "0")
                logger.info(f"Total matching records in Scopus catalog: {total_results}")

            entries: Union[List[Dict[str, Any]], Dict[str, Any]] = results_payload.get("entry", [])  # Lista de registros
            if not entries:  # Se não houver registros retornados
                logger.info("No more results returned. Finished this keyword.")
                break  # Concluiu a palavra-chave

            # Trata o caso em que a API retorna um único dicionário em vez de uma lista
            if isinstance(entries, dict):
                entries = [entries]

            fetched_count: int = len(entries)  # Quantidade de itens na página
            logger.info(f"Fetched {fetched_count} records from page {page_num}.")
            
            # Cacheia os registros brutos recebidos da API para backup
            self.raw_results_cache.extend(entries)

            batch_buffer: List[Dict[str, Any]] = []  # Buffer em memória para gravação em lote

            for entry in entries:  # Percorre cada registro da página
                processed_for_keyword += 1
                self.total_processed += 1

                # Extrai o ID único do registro (prioriza EID ou dc:identifier)
                eid: Optional[str] = entry.get("eid")
                dc_id: Optional[str] = entry.get("dc:identifier")
                record_id: Optional[str] = eid or (dc_id.replace("SCOPUS_ID:", "") if dc_id else None)
                
                if not record_id:  # Se não houver ID válido
                    continue  # Pula o item

                # Verifica se o registro já existe no banco SQLite para evitar chamadas caras à API secundária
                if self.db.record_exists(record_id):
                    continue  # Pula se já estiver no banco de dados

                title: str = entry.get("dc:title") or ""  # Obtém o título do trabalho
                if not title.strip():  # Se o título for vazio
                    continue  # Pula o item

                authors: str = extract_authors(entry)  # Extrai e junta os nomes dos autores
                
                cover_date: str = entry.get("prism:coverDate") or ""  # Data de capa da publicação
                year: str = cover_date[:4] if len(cover_date) >= 4 else "Não Informado"  # Extrai o ano de 4 dígitos
                
                type_of_research: str = translate_format(  # Traduz o tipo de trabalho
                    entry.get("subtypeDescription"),
                    entry.get("prism:aggregationType")
                )
                
                journal: str = entry.get("prism:publicationName") or "Não Informado"  # Nome da revista/conferência
                
                # Extrai ou resolve o resumo (abstract)
                abstract: str = "Não Informado"  # Valor padrão
                if self.view == "COMPLETE":  # Se estiver usando a visão COMPLETE
                    abstract_raw = entry.get("dc:description")  # Tenta pegar dc:description
                    if isinstance(abstract_raw, dict):  # Trata variação em formato dicionário com chave '$'
                        abstract = abstract_raw.get("$", "")
                    elif abstract_raw:
                        abstract = str(abstract_raw)
                
                # Se o resumo não veio disponível na busca, tenta buscá-lo via API de Abstract Retrieval
                if not abstract or str(abstract).strip().lower() in ["none", "não informado", ""]:
                    abstract = fetch_abstract_retrieval(self.session, record_id, self.headers)  # Busca via API secundária
                    # Pausa educada entre chamadas da API secundária
                    time.sleep(0.2)

                doi: str = entry.get("prism:doi") or "Não Informado"  # Extrai o DOI
                article_url: str = extract_url(entry)  # Extrai a URL de acesso ao documento

                # Constrói o dicionário padronizado do registro
                record: Dict[str, Any] = {
                    "id": record_id,
                    "title": title.strip(),
                    "authors": authors,
                    "year": str(year),
                    "type_of_research": type_of_research,
                    "advisor": "Não Informado",
                    "journal": journal.strip(),
                    "abstract": str(abstract).strip() if abstract else "Não Informado",
                    "doi": doi.strip(),
                    "article_url": article_url.strip(),
                    "keyword_query": keyword
                }

                batch_buffer.append(record)  # Adiciona ao lote da página
                
                # Verifica se atingiu o limite de registros configurado para o termo
                if self.limit and (saved_for_keyword + len(batch_buffer)) >= self.limit:
                    break

            # Descarrega o lote completo da página no banco SQLite em uma transação única (UPSERT)
            if batch_buffer:
                inserted_count: int = self.db.insert_batch(batch_buffer)  # Grava o lote no banco
                saved_for_keyword += inserted_count  # Incrementa salvos do termo
                self.total_inserted += inserted_count  # Incrementa salvos globais
                logger.info(f" -> [BATCH SAVED] Saved/Updated batch of {len(batch_buffer)} records.")

            if self.limit and saved_for_keyword >= self.limit:  # Se o limite foi atingido
                logger.info(f"Limit of {self.limit} records reached for keyword '{keyword}'.")
                break  # Encerra a busca para a palavra-chave

            # Lógica de avançar a paginação
            if self.pagination_mode == "cursor":  # Se estiver paginando por cursor
                cursor_obj: Dict[str, str] = results_payload.get("cursor", {})  # Nó cursor
                current_cursor: Optional[str] = cursor_obj.get("@current")  # Cursor atual
                next_cursor: Optional[str] = cursor_obj.get("@next")  # Próximo cursor
                
                # Se o próximo cursor for vazio, idêntico ou ausente, encerra a paginação do termo
                if not next_cursor or next_cursor == current_cursor:
                    logger.info("Finished harvesting all matches from Scopus for this query.")
                    break
                
                params["cursor"] = next_cursor  # Atualiza o cursor para a próxima requisição
            else:  # Se estiver paginando por offset
                if fetched_count < params["count"]:  # Se retornou menos itens que o tamanho da página
                    logger.info("Fetched less than page count. Finished harvesting all matches from Scopus.")
                    break  # Concluiu a busca
                
                self.start_offset += fetched_count  # Avança o offset
                params["start"] = self.start_offset  # Atualiza o parâmetro start

                # Aplica o limite de segurança de offset (5000) para chaves de API Scopus padrão
                if self.start_offset >= SCOPUS_MAX_OFFSET:
                    logger.warning(f"Reached Scopus {SCOPUS_MAX_OFFSET} record offset limit for standard API keys.")
                    break  # Interrompe o laço para evitar erro HTTP 400 da API Scopus

            page_num += 1  # Incrementa o número da página
            time.sleep(self.delay)  # Pausa educada entre requisições de página

        logger.info(
            f"Finished '{keyword}': processed {processed_for_keyword} "
            f"records, saved {saved_for_keyword} relevant records."
        )

    def run(self) -> None:
        """
        Executa o pipeline completo de coleta para todas as palavras-chave configuradas.
        """
        logger.info("=== SCOPUS SYSTEM DATA HARVESTER STARTED ===")
        start: float = time.time()  # Registra o timestamp inicial

        for keyword in self.keywords:  # Itera sobre todas as palavras-chave da lista
            self._process_keyword(keyword)  # Processa a palavra-chave atual
            time.sleep(self.delay)  # Pausa educada entre termos

        elapsed: float = time.time() - start  # Calcula a duração total
        logger.info("=== SCOPUS SYSTEM DATA HARVESTER PROCESS COMPLETED ===")
        logger.info(f"Total processed: {self.total_processed} | Total saved to DB: {self.total_inserted}")
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES DE EXPORTAÇÃO (EXCEL / CSV / JSON)
# ──────────────────────────────────────────────────────────────────────────────
def export_to_format(db_path: str, export_path: str, chunksize: int = 50000) -> bool:
    """
    Exporta a tabela scopus_metadata do SQLite para Excel, CSV ou JSON.
    Mantém o nome das colunas compatível com os harvesters BDTD, SciELO, OpenAlex e PubMed.
    """
    logger.info(f"Exporting database records to: {export_path}")
    try:
        conn: sqlite3.Connection = sqlite3.connect(db_path)  # Conecta ao arquivo do banco SQLite
        
        # Consulta SQL com apelidos de colunas no padrão unificado do projeto
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
            FROM scopus_metadata
            ORDER BY harvested_at DESC
        """
        
        ext: str = os.path.splitext(export_path)[1].lower()  # Pega a extensão do arquivo
        
        # Garante que o diretório de exportação existe no sistema de arquivos
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
        
        if df.empty:  # Se não houver dados no banco
            logger.warning("No records found in the database to export.")
            return False
            
        if ext in ['.xlsx', '.xls']:  # Se for planilha Excel
            df.to_excel(export_path, index=False)
        elif ext == '.json':  # Se for arquivo JSON
            df.to_json(export_path, orient='records', force_ascii=False, indent=4)
        else:  # Caso formato não reconhecido, exporta como Excel (.xlsx) por padrão
            logger.warning(f"Unrecognized export format: {ext}. Defaulting to Excel (.xlsx).")
            df.to_excel(export_path, index=False)
            
        logger.info(f"Successfully exported {len(df)} records.")  # Confirma exportação no log
        return True  # Retorna True em caso de sucesso
    except Exception as e:  # Caso falhe o processo de exportação
        logger.error(f"Failed to export database: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# PONTO DE ENTRADA PROGRAMÁTICO (API PYTHON)
# ──────────────────────────────────────────────────────────────────────────────
def run_harvest(config: Dict[str, Any]) -> bool:
    """
    Ponto de entrada programático de alto nível para executar o pipeline Scopus Harvester.
    """
    # Configura arquivo de log se especificado na estrutura de configuração
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
        
        # Inicializa e executa o pipeline Scopus Harvester
        pipeline: ScopusHarvesterPipeline = ScopusHarvesterPipeline(db_manager, config)
        pipeline.run()

        # Executa a exportação dos dados coletados
        export_to_format(config["db_path"], config["export_path"])

        db_manager.close()  # Fecha a conexão do banco com segurança
        db_manager = None
        return True  # Retorna sucesso
        
    except Exception as e:  # Se ocorrer erro durante a execução
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        return False
    finally:
        if db_manager:  # Garante fechamento do banco de dados
            db_manager.close()


# ──────────────────────────────────────────────────────────────────────────────
# INTERFACE DE LINHA DE COMANDO (CLI) E EXECUÇÃO PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    """Função principal para parsing de argumentos via linha de comando (CLI)."""
    parser = argparse.ArgumentParser(
        description="Automated Python pipeline to harvest scholarly metadata from Scopus.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Definição dos argumentos da CLI
    parser.add_argument("--config", type=str, default=None, help="Path to JSON configuration file.")
    parser.add_argument("--keywords", type=str, nargs="+", help="Search keywords or queries (overrides config).")
    parser.add_argument("--db-path", type=str, help="Path to SQLite database file.")
    parser.add_argument("--export", type=str, help="Export target path (Excel, CSV, JSON).")
    parser.add_argument("--limit", type=int, help="Limit of records to harvest per keyword.")
    parser.add_argument("--delay", type=float, help="Delay between requests in seconds.")
    parser.add_argument("--api-key", type=str, help="Scopus API Key.")
    parser.add_argument("--view", type=str, choices=["STANDARD", "COMPLETE"], help="Scopus view mode.")

    args = parser.parse_args()  # Efetua a leitura dos argumentos da linha de comando
    setup_logging()  # Configura logging no terminal

    config_file: Optional[str] = args.config  # Caminho do arquivo de configuração fornecido
    use_config: bool = False

    if not config_file and os.path.exists("scopus_config.json"):  # Se scopus_config.json existir no diretório atual
        config_file = "scopus_config.json"
        use_config = True
    elif config_file and os.path.exists(config_file):  # Se o arquivo especificado existir
        use_config = True

    config: Dict[str, Any] = {}

    if use_config and config_file:  # Se for utilizar arquivo de configuração JSON
        try:
            config = read_json_config_file(config_file)  # Lê o arquivo JSON
            logger.info(f"Successfully loaded configuration from: {config_file}")
        except Exception as e:  # Se falhar a leitura do JSON
            logger.error(f"Failed to read JSON configuration: {e}. Falling back to CLI args.")
            use_config = False

    if not use_config:  # Caso não utilize arquivo de configuração JSON
        if not args.config and not os.path.exists("scopus_config.json"):  # Se o modelo padrão não existir
            try:
                create_json_config_template("scopus_config.json")  # Cria o modelo scopus_config.json
            except Exception as e:
                logger.warning(f"Could not create config template: {e}")

        # Monta a estrutura de configuração baseada nos parâmetros recebidos da CLI
        config = {
            "keywords": args.keywords or ["\"planejamento urbano\""],
            "db_path": args.db_path or "scopus_metadata.db",
            "export_path": args.export or "scopus_resultados.xlsx",
            "limit": args.limit,
            "delay": args.delay or 1.0,
            "api_key": args.api_key or "",
            "insttoken": "",
            "view": args.view or "COMPLETE"
        }
    else:
        # Sobrescreve configurações lidas do JSON caso argumentos CLI tenham sido passados
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
        if args.view:
            config["view"] = args.view

    if not config.get("api_key"):  # Valida se a chave de API do Scopus foi fornecida
        logger.error(
            "Scopus API Key is missing. Please provide it via config file "
            "or command line --api-key parameter."
        )
        return
        
    if not config.get("keywords"):  # Valida presença de palavras-chave
        logger.error("No keywords specified. Please define keywords via CLI or config file.")
        return

    try:
        # Executa o pipeline Scopus Harvester
        success: bool = run_harvest(config)
        if success:
            logger.info("Pipeline executed successfully.")
        else:
            logger.error("Pipeline finished with errors.")
    except KeyboardInterrupt:  # Tratamento de interrupção manual via Ctrl+C
        logger.warning("\nPipeline execution interrupted by user.")
    except Exception as e:  # Captura falha não tratada
        logger.critical(f"Pipeline crashed due to an unhandled exception: {e}", exc_info=True)


# Ponto de entrada do script quando executado diretamente pelo terminal
if __name__ == "__main__":
    main()  # Invoca a função principal main