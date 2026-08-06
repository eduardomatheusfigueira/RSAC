#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pipeline de Coleta e Extração de Metadados do OpenAlex
Autor: Eduardo Matheus Figueira
Descrição: Pipeline automatizado que consulta a API REST do OpenAlex (api.openalex.org),
             reconstrói resumos a partir do formato de índice invertido, persiste os dados
             limpos no banco SQLite (com transações otimizadas e UPSERT) e exporta os resultados
             em formato compatível com os harvesters BDTD e SciELO.
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
from datetime import datetime  # Módulo para manipulação de datas e timestamps
from requests.adapters import HTTPAdapter  # Adaptador do requests para controle avançado de conexões HTTP
from urllib3.util.retry import Retry  # Estratégia de tentativas e suporte a resiliência na camada de rede
from typing import List, Dict, Optional, Set, Tuple, Any, Union  # Importação de anotações de tipo para Type Hints

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
OPENALEX_BASE_URL: str = "https://api.openalex.org/works"  # URL base da API REST do OpenAlex
PAGE_SIZE: int = 50  # Quantidade ótima de registros por página na API do OpenAlex

# Expressão regular pré-compilada para extrair email de User-Agent
RE_EMAIL_FROM_UA: re.Pattern = re.compile(r'(?:contact|mailto)\s*:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES AUXILIARES DE PARSING E HIGIENIZAÇÃO
# ──────────────────────────────────────────────────────────────────────────────
def reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    """
    Reconstrói o texto do resumo (abstract) a partir do formato de índice invertido do OpenAlex.
    O OpenAlex armazena resumos como dicionários onde a chave é a palavra e o valor é uma lista de posições.
    """
    if not inverted_index or not isinstance(inverted_index, dict):  # Se o índice invertido for nulo ou inválido
        return "Não Informado"  # Retorna o valor padrão de fallback
    try:
        word_positions: List[Tuple[int, str]] = []  # Lista para armazenar pares (posição, palavra)
        for word, positions in inverted_index.items():  # Percorre cada palavra e suas posições
            for pos in positions:  # Para cada posição ocupada pela palavra no texto
                word_positions.append((pos, word))  # Adiciona a tupla (posição, palavra) à lista
        # Ordena a lista de palavras estritamente pela sua posição numérica original no texto
        word_positions.sort(key=lambda x: x[0])
        return " ".join([word for pos, word in word_positions])  # Reagrupa as palavras em texto legível
    except Exception:  # Em caso de erro imprevisto durante a reconstituição do resumo
        return "Não Informado"  # Retorna valor padrão seguro


def translate_format(fmt_str: Optional[str]) -> str:
    """
    Traduz a chave de tipo de trabalho do OpenAlex para uma descrição amigável em português.
    """
    if not fmt_str:  # Se a string do tipo for vazia ou nula
        return "Artigo"  # Assume o padrão de Artigo
    fmt: str = fmt_str.lower()  # Converte a string para minúsculas para comparação uniforme
    if fmt in ["article", "journal-article"]:  # Se for artigo de periódico
        return "Artigo"  # Traduz para Artigo
    elif fmt == "book-chapter":  # Se for capítulo de livro
        return "Capítulo de Livro"  # Traduz para Capítulo de Livro
    elif fmt == "book":  # Se for livro completo
        return "Livro"  # Traduz para Livro
    elif fmt in ["dissertation", "thesis"]:  # Se for tese ou dissertação
        return "Tese/Dissertação"  # Traduz para Tese/Dissertação
    elif fmt == "preprint":  # Se for um preprint não revisado por pares
        return "Preprint"  # Traduz para Preprint
    return fmt_str.capitalize()  # Caso seja outro tipo, retorna capitalizado


def extract_authors(work: Dict[str, Any]) -> str:
    """
    Extrai e junta todos os nomes de autores de um trabalho em uma única string separada por ponto e vírgula.
    """
    authorships: List[Dict[str, Any]] = work.get("authorships", [])  # Obtém a lista de autorias do registro
    authorship_list: List[str] = [  # Compreensão de lista para extrair nomes de autores
        a.get("author", {}).get("display_name", "")  # Extrai o nome de exibição do autor
        for a in authorships  # Itera sobre cada autoria
        if a.get("author", {}).get("display_name")  # Filtra apenas se houver nome válido
    ]
    if not authorship_list:  # Se não houver lista de autores
        return "Não Informado"  # Retorna o valor padrão de ausência
    
    cleaned_authors: List[str] = []  # Lista para autores limpos
    for author in authorship_list:  # Percorre cada nome de autor
        author = author.strip()  # Limpa espaços em branco nas pontas
        if author:  # Se não for uma string vazia
            cleaned_authors.append(author)  # Adiciona à lista
            
    return "; ".join(cleaned_authors) if cleaned_authors else "Não Informado"  # Junta por "; "


def extract_source(work: Dict[str, Any]) -> str:
    """
    Extrai o nome da fonte principal (periódico, conferência, editora ou repositório) do trabalho no OpenAlex.
    """
    source_name: str = ""  # Inicializa a variável com string vazia
    primary_loc: Dict[str, Any] = work.get("primary_location") or {}  # Pega o local primário de publicação
    if primary_loc:  # Se houver local primário
        source: Dict[str, Any] = primary_loc.get("source") or {}  # Obtém o dicionário de fonte
        source_name = source.get("display_name", "")  # Pega o nome de exibição da fonte
        
    if not source_name:  # Se não encontrou na localização primária
        for loc in work.get("locations", []):  # Percorre localizações alternativas
            if loc:  # Se o local for válido
                source = loc.get("source") or {}  # Obtém a fonte
                source_name = source.get("display_name", "")  # Tenta pegar o nome
                if source_name:  # Se achou um nome válido
                    break  # Interrompe o laço
                    
    return source_name.strip() if source_name else "Não Informado"  # Retorna o nome limpo ou o valor padrão


def extract_download_url(work: Dict[str, Any]) -> str:
    """
    Extrai a URL de download ou acesso mais relevante para o trabalho acadêmico.
    Prioriza PDFs de acesso aberto, depois URLs de landing page e finalmente a URL do DOI.
    """
    # 1. Tenta obter a URL de PDF do melhor local de acesso aberto (Open Access)
    best_oa: Dict[str, Any] = work.get("best_oa_location") or {}  # Obtém o melhor local OA
    if best_oa.get("pdf_url"):  # Se houver URL direta para o arquivo PDF
        return best_oa.get("pdf_url")  # Retorna a URL do PDF

    # 2. Tenta obter a URL de PDF do local primário de publicação
    prim_loc: Dict[str, Any] = work.get("primary_location") or {}  # Obtém o local primário
    if prim_loc.get("pdf_url"):  # Se houver URL de PDF no local primário
        return prim_loc.get("pdf_url")  # Retorna a URL do PDF

    # 3. Tenta obter a URL da página inicial (landing page) do melhor local OA
    if best_oa.get("landing_page_url"):  # Se houver landing page OA
        return best_oa.get("landing_page_url")  # Retorna a landing page OA

    # 4. Tenta obter a URL da página inicial (landing page) do local primário
    if prim_loc.get("landing_page_url"):  # Se houver landing page no local primário
        return prim_loc.get("landing_page_url")  # Retorna a landing page primária

    # 5. Percorre qualquer outro local disponível em busca de PDF ou landing page
    for loc in work.get("locations", []):  # Itera sobre todas as localizações registradas
        if loc:  # Se a localização for válida
            if loc.get("pdf_url"):  # Se encontrar PDF
                return loc.get("pdf_url")  # Retorna a URL do PDF
            if loc.get("landing_page_url"):  # Se encontrar landing page
                return loc.get("landing_page_url")  # Retorna a landing page

    # 6. Fallback final: Utiliza a URL completa do DOI se disponível
    if work.get("doi"):  # Se houver um DOI registrado
        return work.get("doi")  # Retorna o link do DOI

    return "Não Informado"  # Retorna o valor padrão caso nenhuma URL válida exista


# ──────────────────────────────────────────────────────────────────────────────
# GERENCIAMENTO DE ARQUIVOS DE CONFIGURAÇÃO (JSON)
# ──────────────────────────────────────────────────────────────────────────────
def create_json_config_template(file_path: str) -> None:
    """
    Cria um arquivo de modelo de configuração no formato JSON para o OpenAlex Harvester.
    """
    logger.info(f"Creating a new JSON configuration template: {file_path}")  # Registra criação no log
    template: Dict[str, Any] = {  # Define o dicionário de exemplo de configuração
        "db_path": "openalex_metadata.db",
        "export_path": "openalex_resultados.xlsx",
        "limit": None,
        "delay": 1.0,
        "email": "",
        "api_key": "",
        "filters": {
            "type": "",
            "publication_year": "",
            "language": ""
        },
        "keywords": [
            "\"inferência causal\" OR \"descoberta causal\"",
            "desenvolvimento regional",
            "planejamento urbano"
        ]
    }
    with open(file_path, "w", encoding="utf-8") as f:  # Abre o arquivo em modo de escrita UTF-8
        json.dump(template, f, ensure_ascii=False, indent=4)  # Salva o arquivo JSON com recuo formatado
    logger.info(f"Successfully generated JSON config template at {file_path}")  # Confirma geração no log


def read_json_config_file(file_path: str) -> Dict[str, Any]:
    """
    Lê as configurações de busca do arquivo JSON e detecta automaticamente schemas flat ou nested (notebook).
    """
    logger.info(f"Reading configuration from JSON: {file_path}")  # Registra leitura no log
    with open(file_path, "r", encoding="utf-8") as f:  # Abre o arquivo JSON para leitura
        data: Dict[str, Any] = json.load(f)  # Carrega o dicionário Python

    # 1. Verifica se é formato nested de notebook (Interface_Revisao.ipynb)
    if "search" in data and "api" in data and "paths" in data:  # Se contiver as chaves nested
        search: Dict[str, Any] = data["search"]  # Sub-dicionário de busca
        api: Dict[str, Any] = data["api"]  # Sub-dicionário de API
        paths: Dict[str, Any] = data["paths"]  # Sub-dicionário de caminhos

        # Parse dos filtros de query do notebook
        filters_dict: Dict[str, str] = {}  # Dicionário de filtros extraídos
        nb_filters: Dict[str, Any] = search.get("filters", {})  # Filtros específicos
        start_year: Optional[int] = search.get("start_year")  # Ano inicial
        end_year: Optional[int] = search.get("end_year")  # Ano final

        if start_year and end_year:  # Se ambos os anos foram informados
            filters_dict["publication_year"] = f"{start_year}-{end_year}"  # Formato de intervalo
        elif start_year:  # Apenas ano inicial
            filters_dict["publication_year"] = f">={start_year}"
        elif end_year:  # Apenas ano final
            filters_dict["publication_year"] = f"<={end_year}"

        if nb_filters.get("only_open_access"):  # Filtro de Acesso Aberto
            filters_dict["is_oa"] = "true"

        if nb_filters.get("repository_ids"):  # IDs de Repositórios
            filters_dict["locations.source.id"] = "|".join(nb_filters["repository_ids"])
        if nb_filters.get("publisher_ids"):  # IDs de Editoras
            filters_dict["primary_location.source.publisher_lineage"] = "|".join(nb_filters["publisher_ids"])
        if nb_filters.get("source_types"):  # Tipos de Fontes
            filters_dict["locations.source.type"] = "|".join(nb_filters["source_types"])

        # Resolve caminhos de saída no diretório configurado
        out_dir: str = paths.get("output_dir", "openalex_outputs")  # Diretório de saída
        os.makedirs(out_dir, exist_ok=True)  # Garante criação da pasta

        return {  # Retorna dicionário padronizado em estrutura plana
            "is_nested": True,
            "keywords": [search.get("query", "")],
            "db_path": os.path.join(out_dir, "openalex_metadata.db"),
            "export_path": os.path.join(out_dir, paths.get("excel_name", "OpenAlex_Data_Export.xlsx")),
            "csv_path": os.path.join(out_dir, paths.get("csv_name", "openalex_clean_data.csv")),
            "json_path": os.path.join(out_dir, paths.get("json_name", "openalex_raw_backup.json")),
            "report_path": os.path.join(out_dir, paths.get("report_name", "openalex_summary_report.md")),
            "log_path": os.path.join(out_dir, paths.get("log_name", "openalex_harvester.log")),
            "limit": api.get("limit"),
            "delay": float(api.get("politeness_delay_seconds", 1.0)),
            "user_agent": api.get("user_agent", "OpenAlexHarvester/1.0"),
            "api_key": api.get("api_key", ""),
            "max_retries": api.get("max_retries", 5),
            "backoff_factor": api.get("backoff_factor", 1.5),
            "filters": filters_dict,
            "output_dir": out_dir,
        }
    else:
        # 2. Formato flat padrão com validação Pydantic (se disponível no ambiente)
        try:
            from config_app.core.config_schemas import OpenAlexConfig, load_and_validate_config
            validated = load_and_validate_config(file_path, OpenAlexConfig)  # Valida pelo schema Pydantic
            vdata: Dict[str, Any] = validated.model_dump()  # Dump dos dados validados
        except (ImportError, ModuleNotFoundError):  # Fallback caso Pydantic não esteja instalado
            logger.warning("Schemas Pydantic não encontrados. Usando fallback de leitura bruta de JSON.")
            vdata = data

        filters_dict = vdata.get("filters", {})  # Obtém dicionário de filtros
        return {  # Retorna dicionário plano com fallbacks seguros
            "is_nested": False,
            "keywords": vdata.get("keywords", []),
            "db_path": vdata.get("db_path", "openalex_metadata.db"),
            "export_path": vdata.get("export_path", "openalex_resultados.xlsx"),
            "limit": vdata.get("limit"),
            "delay": float(vdata.get("delay", 1.0)),
            "email": vdata.get("email", ""),
            "api_key": vdata.get("api_key", ""),
            "filters": filters_dict,
            "output_dir": None,
            "csv_path": None,
            "json_path": None,
            "report_path": None,
            "log_path": None,
            "max_retries": 5,
            "backoff_factor": 2.0,
            "user_agent": None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# GERENCIADOR DE BANCO DE DADOS (SQLITE)
# ──────────────────────────────────────────────────────────────────────────────
class DatabaseManager:
    """
    Gerencia conexões com o banco de dados SQLite, criação da tabela de esquema,
    inserções em lote com suporte a UPSERT e modo WAL ativado.
    """

    SCHEMA: str = """
    CREATE TABLE IF NOT EXISTS openalex_metadata (
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
        self.db_path: str = db_path  # Guarda o caminho do banco de dados SQLite
        self.conn: Optional[sqlite3.Connection] = None  # Inicializa conexão como None
        self.init_db()  # Executa o método de inicialização do banco

    def init_db(self) -> None:
        """Inicializa o esquema do banco de dados e ativa o modo WAL se suportado."""
        db_dir: str = os.path.dirname(self.db_path)  # Obtém o diretório do arquivo do banco
        if db_dir:  # Se houver diretório especificado
            os.makedirs(db_dir, exist_ok=True)  # Cria o diretório caso não exista
            
        open_db_path: str = self.db_path  # Caminho do banco para abertura
        # Suporte a caminhos longos no Windows (Long Path Support)
        if sys.platform.startswith('win') and len(os.path.abspath(open_db_path)) >= 240 and not os.path.abspath(open_db_path).startswith('\\\\?\\'):
            open_db_path = '\\\\?\\' + os.path.abspath(open_db_path)
            
        self.conn = sqlite3.connect(open_db_path)  # Abre a conexão com o banco SQLite
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")  # Ativa modo de gravação WAL para concorrência
        except sqlite3.OperationalError as e:  # Se o sistema de arquivos não suportar WAL
            logger.warning(f"Could not enable WAL mode ({e}), falling back to default journal mode.")
            
        self.conn.executescript(self.SCHEMA)  # Cria a tabela de metadados openalex_metadata
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_openalex_year ON openalex_metadata (year);")  # Cria índice temporal
        self.conn.commit()  # Confirma as alterações no arquivo SQLite
        logger.info(f"Database initialized successfully at: {self.db_path}")  # Loga sucesso da inicialização

    def insert_batch(self, records_list: List[Dict[str, Any]]) -> int:
        """
        Insere ou atualiza (UPSERT) uma lista de registros no banco de dados SQLite.
        Utiliza transação única (executemany) para alto desempenho, atualizando dados existentes se necessário.
        """
        if not records_list or not self.conn:  # Se a lista de registros estiver vazia ou sem conexão
            return 0  # Retorna 0 registros processados
            
        # Cláusula SQL UPSERT nativa para inserir ou atualizar registros duplicados pelo ID de chave primária
        query: str = """
            INSERT INTO openalex_metadata 
            (id, title, authors, year, type_of_research, advisor, journal, abstract, doi, article_url, keyword_query)
            VALUES (:id, :title, :authors, :year, :type_of_research, :advisor, :journal, :abstract, :doi, :article_url, :keyword_query)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                year = excluded.year,
                type_of_research = excluded.type_of_research,
                advisor = CASE WHEN excluded.advisor != 'Não Informado' THEN excluded.advisor ELSE openalex_metadata.advisor END,
                journal = excluded.journal,
                abstract = CASE WHEN excluded.abstract != 'Não Informado' THEN excluded.abstract ELSE openalex_metadata.abstract END,
                doi = CASE WHEN excluded.doi != 'Não Informado' THEN excluded.doi ELSE openalex_metadata.doi END,
                article_url = CASE WHEN excluded.article_url != 'Não Informado' THEN excluded.article_url ELSE openalex_metadata.article_url END,
                keyword_query = excluded.keyword_query;
        """
        try:
            cursor = self.conn.cursor()  # Abre um cursor de execução
            cursor.executemany(query, records_list)  # Executa todas as inserções da lista no lote
            self.conn.commit()  # Confirma a transação inteira no disco
            return cursor.rowcount  # Retorna a quantidade de linhas afetadas
        except sqlite3.Error as e:  # Se houver erro de banco durante a gravação
            logger.error(f"Error inserting batch into SQLite database: {e}")  # Registra o erro
            if self.conn:  # Se houver conexão
                self.conn.rollback()  # Desfaz a transação mal-sucedida
            return 0

    def close(self) -> None:
        """Encerra com segurança a conexão ativa com o banco de dados SQLite."""
        if self.conn:  # Se houver uma conexão ativa
            self.conn.close()  # Fecha a conexão
            self.conn = None  # Reseta o ponteiro de conexão
            logger.info("Database connection closed.")  # Registra o encerramento no log


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE DE COLETA OPENALEX
# ──────────────────────────────────────────────────────────────────────────────
class OpenAlexHarvesterPipeline:
    """
    Pipeline principal que consulta a API REST do OpenAlex com paginação por cursor,
    mapeia os resultados para SQLite e coordena a exportação para Excel/CSV/JSON.
    """

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]) -> None:
        self.db: DatabaseManager = db_manager  # Gerenciador do banco de dados relacional
        self.keywords: List[str] = config["keywords"]  # Lista de termos ou expressões booleanas a buscar
        self.limit: Optional[int] = config["limit"]  # Limite máximo de registros a coletar por termo
        self.delay: float = config["delay"]  # Atraso entre requisições para polidez no servidor
        self.api_key: str = config.get("api_key", "")  # Chave de API opcional para aumentar cota
        self.max_retries: int = config.get("max_retries", 5)  # Número máximo de re-tentativas de rede
        self.backoff_factor: float = config.get("backoff_factor", 1.5)  # Fator de backoff exponencial
        self.filters: Dict[str, str] = config.get("filters", {})  # Filtros específicos adicionais da API
        
        # Extrai email de contato do User-Agent se presente
        self.email: str = config.get("email", "")  # Email do usuário
        if not self.email and config.get("user_agent"):  # Se não houver email mas houver User-Agent
            m = RE_EMAIL_FROM_UA.search(config["user_agent"])  # Procura email no User-Agent
            if m:  # Se encontrou um padrão de email
                self.email = m.group(1)  # Guarda o email extraído

        # Configura cabeçalhos HTTP padrão com identificação (Polite Pool)
        self.headers: Dict[str, str] = {}  # Dicionário de headers HTTP
        if self.email:  # Se tiver email de contato
            self.headers["User-Agent"] = f"mailto:{self.email}"  # Identifica a chamada na Polite Pool do OpenAlex
        elif config.get("user_agent"):  # Se tiver User-Agent customizado
            self.headers["User-Agent"] = config["user_agent"]
        else:  # Fallback: Simula um navegador Chrome moderno
            self.headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

        # Inicializa a sessão HTTP persistente com suporte a Retry automatizado
        self.session: requests.Session = requests.Session()
        self.session.headers.update(self.headers)
        
        retry_strategy = Retry(  # Estratégia de tentativas automatizadas para falhas temporárias
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)  # Instancia adaptador HTTP resiliênte
        self.session.mount("http://", adapter)  # Acopla a HTTP
        self.session.mount("https://", adapter)  # Acopla a HTTPS

        self.total_processed: int = 0  # Contador de registros processados
        self.total_inserted: int = 0  # Contador de registros salvos no banco
        self.raw_results_cache: List[Dict[str, Any]] = []  # Cache de resultados brutos para backup JSON

    def _fetch_page(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Busca uma única página da API do OpenAlex com os parâmetros fornecidos.
        A resiliência de rede é totalmente gerenciada pelo HTTPAdapter com Retry.
        """
        req_params: Dict[str, Any] = params.copy()  # Copia os parâmetros da requisição
        if self.api_key:  # Se houver chave de API fornecida
            req_params["api_key"] = self.api_key  # Inclui a chave nos parâmetros
        if self.email:  # Se houver email fornecido
            req_params["mailto"] = self.email  # Inclui mailto nos parâmetros

        try:
            logger.info(f"Request parameters: {req_params}")  # Loga os parâmetros enviados
            response = self.session.get(OPENALEX_BASE_URL, params=req_params, timeout=30)  # Executa o GET HTTP
            
            if response.status_code == 200:  # Se o status for sucesso HTTP 200
                return response.json()  # Retorna a resposta parseada em JSON
            elif response.status_code == 429:  # Se exceder o limite de taxa de requisições
                logger.warning("Rate limit hit (429). Retry strategy will handle backoff.")
            else:  # Outro código de erro HTTP
                logger.error(f"API request failed with HTTP {response.status_code}: {response.text}")
                
        except requests.RequestException as e:  # Se ocorrer erro na camada de transporte de rede
            logger.error(f"Network error after retries: {e}")

        return None  # Retorna None caso a chamada falhe

    def _process_keyword(self, keyword: str) -> None:
        """
        Executa a coleta completa para uma única palavra-chave usando paginação por cursor.
        """
        logger.info(f"Target query: '{keyword}'")  # Loga o termo de busca atual
        
        # Constrói parâmetros de filtro e query específicos do OpenAlex
        filter_parts: List[str] = []  # Partes da clausula filter
        params: Dict[str, Any] = {  # Dicionário de parâmetros HTTP
            "per_page": PAGE_SIZE,  # Registros por página (50)
            "cursor": "*"  # Cursor inicial do OpenAlex
        }
        
        # Inclui a query de busca no título ou resumo
        if keyword:  # Se houver palavra-chave
            if "*" in keyword or "?" in keyword:  # Se contiver curingas de busca
                params["search.exact"] = keyword  # Usa busca exata
            else:  # Busca padrão em título e resumo
                filter_parts.append(f"title_and_abstract.search:{keyword}")
            
        # Adiciona filtros extras configurados (ano, idioma, tipo)
        for key, value in self.filters.items():  # Percorre os filtros configurados
            if value:  # Se o filtro não for vazio
                if key != "publication_year" or "publication_year" not in filter_parts:
                    if key == "language" and "," in value:  # Tratamento para múltiplos idiomas
                        val_cleaned: str = "|".join([v.strip() for v in value.split(",")])  # Separa por '|'
                        filter_parts.append(f"{key}:{val_cleaned}")
                    else:
                        filter_parts.append(f"{key}:{value}")
                
        if filter_parts:  # Se houver partes de filtro montadas
            params["filter"] = ",".join(filter_parts)  # Junta filtros por vírgula
            
        logger.info(f"Query params: {params}")  # Loga os parâmetros finais da query

        saved_for_keyword: int = 0  # Registros salvos para este termo
        processed_for_keyword: int = 0  # Registros processados para este termo
        page_num: int = 1  # Número da página atual
        total_results: Optional[int] = None  # Total de resultados no catálogo OpenAlex

        logger.info("Initiating search queries on OpenAlex API...")

        while True:  # Loop de paginação por cursor
            logger.info(f"Requesting results starting page {page_num}...")
            data: Optional[Dict[str, Any]] = self._fetch_page(params)  # Requisita a página atual
            
            if data is None:  # Se a requisição retornar None (falha)
                logger.error("Failed to fetch page. Stopping this keyword.")
                break  # Encerra o loop do termo

            results: List[Dict[str, Any]] = data.get("results", [])  # Obtém a lista de resultados da página
            if not results:  # Se a página veio vazia
                logger.info("No more results found. Finished this keyword.")
                break  # Encerra o loop da palavra-chave

            if total_results is None:  # Na primeira página, captura o total estimado no catálogo
                total_results = data.get("meta", {}).get("count", 0)
                logger.info(f"Total matching records in OpenAlex catalog: {total_results}")

            logger.info(f"Fetched {len(results)} records from page {page_num}.")
            
            # Cacheia os resultados brutos recebidos da API para backup em JSON
            self.raw_results_cache.extend(results)

            batch_buffer: List[Dict[str, Any]] = []  # Lote temporário em memória para gravação
            
            for work in results:  # Percorre cada trabalho acadêmico retornado
                processed_for_keyword += 1
                self.total_processed += 1

                # Extrai e limpa o ID do trabalho no OpenAlex (remove prefixo URL se houver)
                work_id: str = work.get("id", "").split("/")[-1] if "/" in work.get("id", "") else work.get("id", "")
                if not work_id:  # Se não houver ID válido
                    continue  # Pula o registro

                title: str = work.get("title") or work.get("display_name") or ""  # Obtém o título
                if not title.strip():  # Se o título estiver em branco
                    continue  # Pula o registro

                authors: str = extract_authors(work)  # Extrai a lista de autores concatenada
                year: str = str(work.get("publication_year", ""))  # Extrai o ano de publicação
                type_of_research: str = translate_format(work.get("type", ""))  # Traduz o tipo de trabalho
                journal: str = extract_source(work)  # Extrai a fonte (periódico/editora)
                abstract: str = reconstruct_abstract(work.get("abstract_inverted_index"))  # Reconstrói o resumo
                
                doi_raw: str = work.get("doi") or ""  # Obtém o DOI bruto
                doi: str = doi_raw.replace("https://doi.org/", "") if doi_raw else "Não Informado"  # Trata o DOI
                
                article_url: str = extract_download_url(work)  # Extrai a melhor URL de acesso/download

                # Constrói o dicionário padronizado do registro
                record: Dict[str, Any] = {
                    "id": work_id,
                    "title": title.strip(),
                    "authors": authors,
                    "year": year,
                    "type_of_research": type_of_research,
                    "advisor": "Não Informado",
                    "journal": journal,
                    "abstract": abstract,
                    "doi": doi,
                    "article_url": article_url,
                    "keyword_query": keyword
                }

                batch_buffer.append(record)  # Adiciona o registro ao lote da página
                
                # Verifica se atingiu o limite de salvamento por palavra-chave
                if self.limit and (saved_for_keyword + len(batch_buffer)) >= self.limit:
                    break

            if batch_buffer:  # Se houver registros no lote
                inserted_count: int = self.db.insert_batch(batch_buffer)  # Salva em lote no SQLite
                saved_for_keyword += inserted_count  # Incrementa salvos da palavra-chave
                self.total_inserted += inserted_count  # Incrementa salvos globais
                logger.info(f" -> [BATCH SAVED] Saved/Updated batch of {len(batch_buffer)} records.")

            if self.limit and saved_for_keyword >= self.limit:  # Se o limite foi atingido
                logger.info(f"Limit of {self.limit} records reached for keyword '{keyword}'.")
                break  # Encerra o processamento do termo

            next_cursor: Optional[str] = data.get("meta", {}).get("next_cursor")  # Obtém o próximo cursor
            if not next_cursor or next_cursor == params["cursor"]:  # Se não houver novo cursor ou repetiu
                logger.info("Finished harvesting all matches from OpenAlex.")
                break  # Concluiu todas as páginas disponíveis

            params["cursor"] = next_cursor  # Atualiza o cursor para a próxima página
            page_num += 1  # Incrementa o contador de páginas
            time.sleep(self.delay)  # Pausa educada entre requisições de página

        logger.info(
            f"Finished '{keyword}': processed {processed_for_keyword} "
            f"records, saved {saved_for_keyword} relevant records."
        )

    def run(self) -> None:
        """
        Executa o pipeline completo de coleta para todas as palavras-chave.
        """
        logger.info("=== OPENALEX SYSTEM DATA HARVESTER STARTED ===")
        start: float = time.time()  # Registra horário de início

        for keyword in self.keywords:  # Itera sobre todas as palavras-chave
            self._process_keyword(keyword)  # Processa a palavra-chave atual
            time.sleep(self.delay)  # Pausa educada entre palavras-chave

        elapsed: float = time.time() - start  # Calcula a duração total
        logger.info("=== OPENALEX SYSTEM DATA HARVESTER PROCESS COMPLETED SUCCESSFULLY ===")
        logger.info(f"Total processed: {self.total_processed} | Total saved to DB: {self.total_inserted}")
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES DE EXPORTAÇÃO E RELATÓRIOS
# ──────────────────────────────────────────────────────────────────────────────
def export_to_format(db_path: str, export_path: str, chunksize: int = 50000) -> bool:
    """
    Exporta a tabela openalex_metadata do SQLite para Excel, CSV ou JSON.
    Mantém o nome das colunas compatível com os harvesters BDTD e SciELO.
    """
    logger.info(f"Exporting database records to: {export_path}")
    try:
        conn: sqlite3.Connection = sqlite3.connect(db_path)  # Abre conexão com o banco SQLite
        
        # Consulta SQL com apelidos de coluna compatíveis com a família de harvesters
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
            FROM openalex_metadata
            ORDER BY harvested_at DESC
        """
        
        ext: str = os.path.splitext(export_path)[1].lower()  # Determina a extensão do arquivo de saída
        
        # Garante que o diretório de exportação de destino existe
        export_dir: str = os.path.dirname(export_path)
        if export_dir:
            os.makedirs(export_dir, exist_ok=True)
        
        # Gravação em blocos (chunking) para CSV para otimização do uso da memória RAM
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
            
        df: pd.DataFrame = pd.read_sql_query(query, conn)  # Carrega dados em memória para Excel ou JSON
        conn.close()
        
        if df.empty:  # Se a consulta retornou vazia
            logger.warning("No records found in the database to export.")
            return False
            
        if ext in ['.xlsx', '.xls']:  # Se o destino for planilha Excel
            df.to_excel(export_path, index=False)
        elif ext == '.json':  # Se o destino for arquivo JSON
            df.to_json(export_path, orient='records', force_ascii=False, indent=4)
        else:  # Caso extensão desconhecida, grava em CSV
            logger.warning(f"Unrecognized export format: {ext}. Defaulting to CSV.")
            df.to_csv(export_path, index=False, encoding='utf-8')
            
        logger.info(f"Successfully exported {len(df)} records.")
        return True
    except Exception as e:  # Se falhar o processo de exportação
        logger.error(f"Failed to export database: {e}")
        return False


def generate_markdown_report(db_path: str, report_path: str, query_details: str) -> None:
    """
    Gera um relatório resumo em formato Markdown com estatísticas descritivas da coleta.
    """
    logger.info(f"Generating markdown summary report: {report_path}")
    try:
        conn: sqlite3.Connection = sqlite3.connect(db_path)  # Abre conexão com o banco
        df: pd.DataFrame = pd.read_sql_query("SELECT year, type_of_research, journal FROM openalex_metadata", conn)
        conn.close()

        if df.empty:  # Se o banco estiver vazio
            logger.warning("No data found to generate markdown report.")
            return

        total_records: int = len(df)  # Registros totais
        year_dist: Dict[str, int] = df["year"].value_counts().sort_index().to_dict()  # Distribuição por ano
        type_dist: Dict[str, int] = df["type_of_research"].value_counts().to_dict()  # Distribuição por tipo
        top_venues: Dict[str, int] = df["journal"].value_counts().head(10).to_dict()  # Top 10 periódicos/editoras

        report_dir: str = os.path.dirname(report_path)  # Diretório do relatório
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)  # Cria o diretório se necessário

        # Escreve o relatório em formato Markdown
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# OpenAlex Harvester Summary Report\n\n")
            f.write(f"**Execution Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## Search Configurations\n")
            f.write(f"- **Search Query:** `{query_details}`\n")
            f.write(f"- **Total Records Stored in DB:** {total_records}\n\n")
            
            f.write("## Distribution by Publication Year\n")
            f.write("| Year | Count |\n|---|---|\n")
            for yr, count in year_dist.items():
                f.write(f"| {yr} | {count} |\n")
            f.write("\n")

            f.write("## Distribution by Research Type\n")
            f.write("| Type of Research | Count |\n|---|---|\n")
            for t, count in type_dist.items():
                f.write(f"| {t} | {count} |\n")
            f.write("\n")

            f.write("## Top 10 Journals / Publishers / Repositories\n")
            f.write("| Source Venue | Count |\n|---|---|\n")
            for venue, count in top_venues.items():
                f.write(f"| {venue} | {count} |\n")
            f.write("\n")

        logger.info("Markdown summary report generated successfully.")
    except Exception as e:
        logger.error(f"Failed to generate markdown report: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# PONTO DE ENTRADA PROGRAMÁTICO (API PYTHON)
# ──────────────────────────────────────────────────────────────────────────────
def run_harvest(config: Dict[str, Any]) -> bool:
    """
    Ponto de entrada programático de alto nível para executar o pipeline OpenAlex Harvester.
    """
    # Configura arquivo de log se especificado na configuração
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
        pipeline: OpenAlexHarvesterPipeline = OpenAlexHarvesterPipeline(db_manager, config)
        pipeline.run()

        # Cacheia dados brutos se o backup em JSON estiver ativado
        if config.get("json_path") and pipeline.raw_results_cache:
            json_dir: str = os.path.dirname(config["json_path"])
            if json_dir:
                os.makedirs(json_dir, exist_ok=True)
            logger.info(f"Exporting JSON raw backup: {config['json_path']}")
            with open(config["json_path"], "w", encoding="utf-8") as f:
                json.dump(pipeline.raw_results_cache, f, indent=4, ensure_ascii=False)

        # Exporta arquivo CSV se caminho configurado
        if config.get("csv_path"):
            csv_dir: str = os.path.dirname(config["csv_path"])
            if csv_dir:
                os.makedirs(csv_dir, exist_ok=True)
            logger.info(f"Exporting CSV: {config['csv_path']}")
            conn: sqlite3.Connection = sqlite3.connect(config["db_path"])
            df: pd.DataFrame = pd.read_sql_query("SELECT * FROM openalex_metadata ORDER BY harvested_at DESC", conn)
            conn.close()
            df.to_csv(config["csv_path"], index=False, encoding="utf-8")

        # Exporta a planilha final (Excel/CSV/JSON)
        export_to_format(config["db_path"], config["export_path"])

        # Gera o relatório em Markdown se configurado
        if config.get("report_path"):
            query_str: str = "; ".join(config["keywords"])
            generate_markdown_report(config["db_path"], config["report_path"], query_str)

        db_manager.close()  # Encerra a conexão do banco com segurança
        db_manager = None
        return True  # Retorna sucesso
        
    except Exception as e:  # Em caso de falha crítica na execução do pipeline
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        return False
    finally:
        if db_manager:  # Bloco de garantia para encerramento do banco de dados
            db_manager.close()


# ──────────────────────────────────────────────────────────────────────────────
# INTERFACE DE LINHA DE COMANDO (CLI) E EXECUÇÃO PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    """Função principal para parsing de argumentos via linha de comando (CLI)."""
    parser = argparse.ArgumentParser(
        description="Automated Python pipeline to harvest scholarly metadata from OpenAlex.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Definição dos argumentos aceitos pela CLI
    parser.add_argument("--db-path", type=str, default="openalex_metadata.db", help="Path to SQLite database file.")
    parser.add_argument("--export", type=str, default="openalex_resultados.xlsx", help="Export target path (Excel, CSV, JSON).")
    parser.add_argument("--limit", type=int, default=None, help="Limit of records to harvest per keyword.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds.")
    parser.add_argument("--email", type=str, default="", help="Contact email for OpenAlex Polite Pool.")
    parser.add_argument("--api-key", type=str, default="", help="OpenAlex API Key (optional).")
    parser.add_argument("--keywords", type=str, nargs="+", default=["planejamento urbano"], help="List of keywords/phrases to query.")
    parser.add_argument("--config", type=str, default=None, help="Path to a JSON configuration file.")

    args = parser.parse_args()  # Leitura dos argumentos
    setup_logging()  # Configuração inicial do sistema de logs no console

    config_file: Optional[str] = args.config  # Obtém o caminho do arquivo de configuração
    use_config: bool = False

    if config_file and os.path.exists(config_file):  # Se arquivo customizado existe
        use_config = True
    elif not config_file and os.path.exists("openalex_config.json"):  # Se existe openalex_config.json
        config_file = "openalex_config.json"
        use_config = True
    elif not config_file and os.path.exists("config_openalex.json"):  # Se existe config_openalex.json
        config_file = "config_openalex.json"
        use_config = True

    config: Dict[str, Any] = {}

    if use_config and config_file:  # Tenta carregar o arquivo JSON configurado
        try:
            config = read_json_config_file(config_file)
            logger.info(f"Successfully loaded configuration from: {config_file}")
        except Exception as e:
            logger.error(f"Failed to read JSON configuration: {e}. Falling back to CLI args.")
            use_config = False

    if not use_config:  # Caso não utilize arquivo de configuração
        if not args.config and not os.path.exists("openalex_config.json"):  # Se não existe o modelo padrão
            try:
                create_json_config_template("openalex_config.json")  # Gera o modelo padronizado JSON
            except Exception as e:
                logger.warning(f"Could not create config template: {e}")

        # Monta o dicionário de configurações a partir da CLI
        config = {
            "is_nested": False,
            "keywords": args.keywords,
            "db_path": args.db_path,
            "export_path": args.export,
            "limit": args.limit,
            "delay": args.delay,
            "email": args.email,
            "api_key": args.api_key,
            "filters": {},
            "output_dir": None,
            "csv_path": None,
            "json_path": None,
            "report_path": None,
            "log_path": None,
            "max_retries": 5,
            "backoff_factor": 2.0,
            "user_agent": None,
        }

    if not config.get("keywords") or not config["keywords"][0]:  # Valida presença de palavras-chave
        logger.error("No keywords or queries specified. Pipeline aborting.")
        return

    try:
        # Executa o pipeline de coleta
        success: bool = run_harvest(config)
        if success:
            logger.info("Pipeline executed successfully.")
        else:
            logger.error("Pipeline finished with errors.")
    except KeyboardInterrupt:  # Interrupção manual do usuário via Ctrl+C
        logger.warning("\nPipeline execution interrupted by user.")
    except Exception as e:  # Exceção não tratada na execução da CLI
        logger.critical(f"Pipeline crashed due to an unhandled exception: {e}", exc_info=True)


# Ponto de entrada do script quando executado diretamente
if __name__ == "__main__":
    main()  # Invoca a função principal main