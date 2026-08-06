#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pipeline de Coleta e Raspagem de Metadados do SciELO (Scientific Electronic Library Online)
Autor: Eduardo Matheus Figueira
Descrição: Pipeline automatizado que consulta o portal de busca do SciELO (search.scielo.org),
             realiza raspagem (scraping) de metadados de artigos utilizando requests.Session com retries (Keep-Alive),
             persiste os dados limpos no banco SQLite (com transações otimizadas e UPSERT) e exporta os resultados.
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
from bs4 import BeautifulSoup, Tag  # Biblioteca BeautifulSoup para parsing e extração de elementos HTML
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
SCIELO_SEARCH_URL: str = "https://search.scielo.org/"  # URL base de pesquisa do portal SciELO
PAGE_SIZE: int = 15  # Quantidade de registros por página retornados padrão pela busca do SciELO

# Expressões regulares pré-compiladas no nível do módulo para alto desempenho
RE_YEAR_ID: re.Pattern = re.compile(r"S\d{4}-\d{3,4}(\d{4})")  # Extração de ano a partir do ID do artigo SciELO
RE_YEAR_TEXT: re.Pattern = re.compile(r"((?:19|20)\d{2})")  # Identificação de ano de publicação no texto fonte
RE_TOTAL_HITS: re.Pattern = re.compile(r"de\s+(\d[\d.]*)\s")  # Extração do número total de resultados da busca
RE_DOI: re.Pattern = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)  # Identificação de DOI padrão

# Cabeçalhos HTTP padrão simulando um navegador moderno
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://search.scielo.org/",
}


# ──────────────────────────────────────────────────────────────────────────────
# GERENCIAMENTO DE ARQUIVOS DE CONFIGURAÇÃO (JSON)
# ──────────────────────────────────────────────────────────────────────────────
def create_json_config_template(file_path: str) -> None:
    """
    Cria um arquivo de modelo de configuração no formato JSON para o SciELO Harvester.
    """
    logger.info(f"Creating a new JSON configuration template: {file_path}")  # Registra no log
    template: Dict[str, Any] = {
        "db_path": "scielo_metadata.db",
        "export_path": "scielo_resultados.xlsx",
        "limit": None,
        "delay": 3.0,
        "search_field": "",
        "keywords": [
            "planejamento urbano",
            "causalidade",
        ],
    }
    with open(file_path, "w", encoding="utf-8") as f:  # Abre o arquivo em modo de escrita
        json.dump(template, f, ensure_ascii=False, indent=4)  # Escreve o JSON formatado
    logger.info(f"Successfully generated JSON config template at {file_path}")  # Confirma no log


def read_json_config_file(file_path: str) -> Dict[str, Any]:
    """
    Lê as configurações de busca e palavras-chave do arquivo JSON utilizando validação Pydantic com fallback.
    """
    logger.info(f"Reading configuration from JSON: {file_path}")  # Registra no log
    try:
        from config_app.core.config_schemas import ScieloConfig, load_and_validate_config  # Importa validador
        validated = load_and_validate_config(file_path, ScieloConfig)  # Executa a validação
        data: Dict[str, Any] = validated.model_dump()  # Converte para dicionário
    except (ImportError, ModuleNotFoundError):  # Tratamento específico se a biblioteca não estiver disponível
        logger.warning("Schemas Pydantic não encontrados. Usando fallback de leitura bruta de JSON.")
        with open(file_path, "r", encoding="utf-8") as f:  # Abre o arquivo JSON
            data = json.load(f)  # Carrega o dicionário bruto

    # Constrói o dicionário estronzado de configuração
    config: Dict[str, Any] = {
        "db_path": data.get("db_path", "scielo_metadata.db"),  # Caminho do banco SQLite
        "export_path": data.get("export_path", "scielo_resultados.xlsx"),  # Caminho do arquivo exportado
        "limit": data.get("limit"),  # Limite máximo de registros por palavra-chave
        "delay": float(data.get("delay", 3.0)),  # Atraso entre requisições
        "search_field": data.get("search_field", ""),  # Campo específico de busca Solr/SciELO
        "keywords": data.get("keywords", []),  # Lista de termos de busca
    }
    return config  # Retorna o dicionário de configurações completo


# ──────────────────────────────────────────────────────────────────────────────
# GERENCIADOR DE BANCO DE DADOS (SQLITE)
# ──────────────────────────────────────────────────────────────────────────────
class DatabaseManager:
    """
    Gerencia conexões com o banco de dados SQLite, criação da tabela de esquema,
    inserções em lote com suporte a UPSERT e modo WAL ativado.
    """

    SCHEMA: str = """
    CREATE TABLE IF NOT EXISTS article_metadata (
        id TEXT PRIMARY KEY,
        title TEXT,
        authors TEXT,
        year TEXT,
        type_of_research TEXT DEFAULT 'Artigo',
        journal TEXT,
        abstract TEXT,
        doi TEXT,
        article_url TEXT,
        keyword_query TEXT,
        harvested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    def __init__(self, db_path: str) -> None:
        self.db_path: str = db_path  # Salva o caminho do arquivo de banco de dados SQLite
        self.conn: Optional[sqlite3.Connection] = None  # Inicializa o atributo de conexão como None
        self.init_db()  # Executa a inicialização do banco e tabelas

    def init_db(self) -> None:
        """Inicializa o esquema do banco de dados e ativa o modo WAL se suportado."""
        open_db_path: str = self.db_path  # Obtém o caminho do banco de dados
        # Trata limitação de tamanho de caminho no Windows (Long Path Support)
        if sys.platform.startswith('win') and len(os.path.abspath(open_db_path)) >= 240 and not os.path.abspath(open_db_path).startswith('\\\\?\\'):
            open_db_path = '\\\\?\\' + os.path.abspath(open_db_path)
            
        self.conn = sqlite3.connect(open_db_path)  # Abre a conexão com o arquivo do banco SQLite
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")  # Ativa o modo de gravação WAL para concorrência de leitura/escrita
        except sqlite3.OperationalError as e:  # Se não conseguir ativar o WAL
            logger.warning(f"Could not enable WAL mode ({e}), falling back to default journal mode.")
            
        self.conn.executescript(self.SCHEMA)  # Executa o script de criação da tabela se não existir
        self.conn.commit()  # Confirma a alteração no banco
        logger.info(f"Database initialized successfully at: {self.db_path}")  # Loga o sucesso

    def insert_batch(self, records_list: List[Dict[str, Any]]) -> int:
        """
        Insere ou atualiza (UPSERT) uma lista de registros de artigos no banco de dados SQLite.
        Utiliza transação única (executemany) para alto desempenho, atualizando dados existentes se necessário.
        """
        if not records_list or not self.conn:  # Se a lista estiver vazia ou sem conexão ativa
            return 0  # Retorna 0 inserções
            
        # Cláusula UPSERT nativa do SQLite para atualização se já existir a chave primária id
        query: str = """
            INSERT INTO article_metadata 
            (id, title, authors, year, type_of_research, journal, abstract, doi, article_url, keyword_query)
            VALUES (:id, :title, :authors, :year, :type_of_research, :journal, :abstract, :doi, :article_url, :keyword_query)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                year = excluded.year,
                type_of_research = excluded.type_of_research,
                journal = excluded.journal,
                abstract = CASE WHEN excluded.abstract != '' THEN excluded.abstract ELSE article_metadata.abstract END,
                doi = CASE WHEN excluded.doi != '' THEN excluded.doi ELSE article_metadata.doi END,
                article_url = excluded.article_url,
                keyword_query = excluded.keyword_query;
        """
        try:
            cursor = self.conn.cursor()  # Obtém o cursor
            cursor.executemany(query, records_list)  # Executa o lote na transação
            self.conn.commit()  # Um único commit para todo o lote
            return cursor.rowcount  # Retorna o número de linhas afetadas
        except sqlite3.Error as e:  # Em caso de erro na inserção do lote
            logger.error(f"Error inserting batch into SQLite database: {e}")  # Loga o erro
            if self.conn:
                self.conn.rollback()  # Desfaz a transação
            return 0

    def close(self) -> None:
        """Encerra com segurança a conexão ativa com o banco de dados SQLite."""
        if self.conn:  # Se houver conexão ativa
            self.conn.close()  # Fecha o banco de dados
            self.conn = None  # Limpa o atributo
            logger.info("Database connection closed.")  # Registra encerramento no log


# ──────────────────────────────────────────────────────────────────────────────
# EXTRATOR E ANALISADOR DE HTML (PARSER DE ELEMENTOS)
# ──────────────────────────────────────────────────────────────────────────────
def parse_item(item_tag: Tag) -> Dict[str, Any]:
    """
    Extrai e higieniza os metadados de uma única tag HTML <div class='item'> do resultado de busca do SciELO.
    """
    record: Dict[str, Any] = {}  # Dicionário do registro extraído

    # 1. Extrai o ID único do trabalho no SciELO
    record["id"] = item_tag.get("id", "")

    # 2. Extrai e limpa o Título do artigo
    title_tag = item_tag.find(class_="title")  # Encontra o elemento com a classe title
    record["title"] = title_tag.text.strip() if title_tag else ""  # Limpa o texto
    if record["title"].startswith("[SciELO Preprints] - "):  # Remove prefixo de Preprint se houver
        record["title"] = record["title"].replace("[SciELO Preprints] - ", "")

    # 3. Extrai a URL direta para o artigo
    if title_tag:
        parent_a = title_tag.parent  # Localiza o elemento pai <a>
        if parent_a and parent_a.name == "a":  # Se for uma tag de link
            record["article_url"] = parent_a.get("href", "")  # Extrai a URL
        else:
            record["article_url"] = ""
    else:
        record["article_url"] = ""

    # 4. Extrai e junta os nomes dos Autores
    authors_div = item_tag.find(class_="authors")  # Encontra a div de autores
    if authors_div:
        author_links = authors_div.find_all("a")  # Localiza todas as tags de link de autor
        record["authors"] = "; ".join(a.text.strip() for a in author_links if a.text.strip())  # Junta por "; "
    else:
        record["authors"] = ""

    # 5. Extrai o Periódico / Revista (Journal)
    source_div = item_tag.find(class_="source")  # Localiza a div da fonte
    if source_div:
        source_link = source_div.find("a")  # Localiza o link da revista
        record["journal"] = source_link.text.strip() if source_link else ""  # Extrai o nome limpo
    else:
        record["journal"] = ""

    # 6. Extrai o Ano de publicação (Estratégia 1: via ID; Estratégia 2: via texto da fonte)
    year: str = ""
    m = RE_YEAR_ID.search(record["id"])  # Procura o padrão de ano no ID SciELO
    if m:
        year = m.group(1)  # Obtém o grupo correspondente ao ano
    if not year and source_div:  # Se não achou no ID, busca no texto do periódico
        for s in source_div.stripped_strings:
            m2 = RE_YEAR_TEXT.search(s)  # Procura ano de 4 dígitos no texto
            if m2:
                year = m2.group(1)  # Atribui o ano encontrado
                break
    record["year"] = year

    # 7. Identifica o Tipo de Pesquisa (Preprint vs Artigo)
    record["type_of_research"] = "Preprint" if "preprint" in record["id"].lower() else "Artigo"

    # 8. Extrai o Resumo (dando preferência para o resumo em português)
    abstract_divs = item_tag.find_all(class_="abstract")  # Encontra todas as divs de resumo
    abstract: str = ""
    for ab in abstract_divs:  # Itera sobre os resumos
        text = ab.text.strip()  # Pega o texto limpo
        if text.lower().startswith("resumo"):  # Se for o resumo em português
            abstract = text.replace("Resumo", "", 1).strip()  # Remove a palavra 'Resumo' inicial
            break
    if not abstract and abstract_divs:  # Fallback: pega o primeiro resumo disponível
        abstract = abstract_divs[0].text.strip()
    record["abstract"] = abstract

    # 9. Extrai o identificador DOI utilizando a regex pré-compilada RE_DOI
    doi_span = item_tag.find(class_="DOIResults")  # Localiza o elemento com o DOI
    doi_text: str = doi_span.text.strip() if doi_span else ""  # Pega o texto
    doi_match = RE_DOI.search(doi_text)  # Aplica a busca regex por DOI
    record["doi"] = doi_match.group(1) if doi_match else doi_text  # Guarda o DOI tratado

    return record  # Retorna o dicionário com os metadados do artigo


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE DE COLETA SCIELO
# ──────────────────────────────────────────────────────────────────────────────
class SciELOHarvesterPipeline:
    """
    Pipeline principal que executa a paginação de buscas no portal SciELO,
    realiza o parsing de registros, aplica retries automatizados e persiste no banco SQLite.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        keywords: List[str],
        limit_per_keyword: Optional[int] = None,
        delay: float = 3.0,
        search_field: str = "",
    ) -> None:
        self.db: DatabaseManager = db_manager  # Gerenciador do banco de dados
        self.keywords: List[str] = keywords  # Lista de palavras-chave a pesquisar
        self.limit: Optional[int] = limit_per_keyword  # Limite de registros por termo
        self.delay: float = delay  # Tempo de espera entre chamadas de página
        self.search_field: str = search_field  # Campo de busca específico

        # Inicializa a sessão HTTP do requests com estratégia de Retry automatizada para resiliência
        self.session: requests.Session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        
        retry_strategy = Retry(  # Estratégia de re-tentativa para oscilações de rede
            total=5,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)  # Instancia o adaptador HTTP
        self.session.mount("http://", adapter)  # Monta o adaptador para HTTP
        self.session.mount("https://", adapter)  # Monta o adaptador para HTTPS

        self.total_processed: int = 0  # Contador de registros processados
        self.total_inserted: int = 0  # Contador de registros salvos

    def _warm_session(self) -> None:
        """Acessa a página principal do SciELO para inicializar os cookies de sessão HTTP."""
        try:
            self.session.get(SCIELO_SEARCH_URL, timeout=15)  # Faz uma requisição inicial simples
            time.sleep(1)  # Aguarda 1 segundo
        except Exception as e:
            logger.warning(f"Could not warm session: {e}")  # Alerta caso falhe a aquisição de cookies

    def _fetch_page(self, keyword: str, offset: int) -> Optional[BeautifulSoup]:
        """Realiza a busca HTTP de uma única página de resultados do SciELO."""
        params: Dict[str, str] = {  # Monta os parâmetros da consulta Solr/SciELO
            "q": keyword,
            "lang": "pt",
            "count": str(PAGE_SIZE),
            "from": str(offset),
            "output": "site",
        }
        if self.search_field:  # Se houver campo específico configurado
            params["where"] = self.search_field

        try:
            res = self.session.get(SCIELO_SEARCH_URL, params=params, timeout=20)  # Executa a requisição GET
            if res.status_code == 200:  # Se a resposta for bem-sucedida
                return BeautifulSoup(res.text, "html.parser")  # Retorna o analisador BeautifulSoup
            logger.error(f"HTTP {res.status_code} for keyword '{keyword}' after retries.")
            return None
        except requests.RequestException as e:  # Em caso de erro na requisição de rede
            logger.error(f"Request failed for '{keyword}' after retries: {e}")
            return None

    def _extract_total(self, soup: BeautifulSoup) -> int:
        """Extrai o número total de resultados correspondentes da página de busca."""
        try:
            total_hits_tag = soup.find(id="TotalHits")  # Tenta encontrar a tag pelo id TotalHits
            if total_hits_tag:
                return int(total_hits_tag.text.strip().replace(".", ""))  # Retorna o inteiro sem pontos
        except Exception as e:
            logger.warning(f"Failed to parse TotalHits tag: {e}")

        page_text: str = soup.get_text()  # Obtém todo o texto da página
        m = RE_TOTAL_HITS.search(page_text)  # Aplica a busca regex por 'de X resultados'
        if m:
            return int(m.group(1).replace(".", ""))  # Converte o número capturado para inteiro
        return 0

    def _process_keyword(self, keyword: str) -> None:
        """Executa a coleta paginada completa para uma única palavra-chave."""
        logger.info(f"Processing keyword: '{keyword}'")  # Registra o termo atual
        offset: int = 1  # Offset inicial da busca
        saved_for_keyword: int = 0  # Salvos do termo
        processed_for_keyword: int = 0  # Processados do termo
        total_results: Optional[int] = None  # Total geral de resultados na busca

        while True:  # Loop de páginas
            page_num: int = (offset - 1) // PAGE_SIZE + 1  # Calcula o número da página atual
            logger.info(f"Querying SciELO for '{keyword}' - Page {page_num}...")

            soup = self._fetch_page(keyword, offset)  # Busca o HTML da página
            if soup is None:  # Se falhou a requisição da página
                logger.warning("Failed to fetch page. Stopping this keyword.")
                break  # Encerra a palavra-chave atual

            items = soup.find_all(class_="item")  # Localiza todas as divs com os artigos da página
            if not items:  # Se não houver itens
                logger.info("No more items found. Finished this keyword.")
                break  # Encerra o loop da palavra-chave

            if total_results is None:  # Na primeira página, extrai o total geral
                total_results = self._extract_total(soup)
                if total_results:
                    logger.info(f"Total matching results on SciELO: {total_results}")

            batch_buffer: List[Dict[str, Any]] = []  # Buffer em memória para gravação em lote
            
            for item in items:  # Itera sobre os artigos da página
                record: Dict[str, Any] = parse_item(item)  # Executa o parsing dos metadados
                record["keyword_query"] = keyword  # Guarda o termo de busca utilizado
                processed_for_keyword += 1
                self.total_processed += 1

                if not record["title"]:  # Se não tiver título válido
                    continue  # Pula o item

                batch_buffer.append(record)  # Adiciona ao lote em memória
                
                # Verifica se atingiu o limite configurado
                if self.limit and (saved_for_keyword + len(batch_buffer)) >= self.limit:
                    break

            if batch_buffer:  # Se houver registros no buffer
                inserted_count: int = self.db.insert_batch(batch_buffer)  # Salva o lote em uma única escrita
                saved_for_keyword += inserted_count  # Incrementa salvos do termo
                self.total_inserted += inserted_count  # Incrementa salvos globais
                logger.info(f" -> [BATCH SAVED] Saved/Updated batch of {len(batch_buffer)} records.")

            if self.limit and saved_for_keyword >= self.limit:  # Se atingiu o limite por termo
                logger.info(f"Limit of {self.limit} records reached for keyword '{keyword}'.")
                break  # Abandona o loop

            if total_results and offset + PAGE_SIZE > total_results:  # Se esgotou os resultados do SciELO
                break
            if len(items) < PAGE_SIZE:  # Se a página veio incompleta (última página)
                break

            offset += PAGE_SIZE  # Avança o offset para a próxima página
            time.sleep(self.delay)  # Pausa educada entre páginas

        logger.info(
            f"Finished '{keyword}': processed {processed_for_keyword} "
            f"records, saved {saved_for_keyword} relevant records."
        )

    def run(self) -> None:
        """Executa o pipeline completo de coleta para todas as palavras-chave."""
        logger.info(f"Starting SciELO metadata harvest for keywords: {self.keywords}")
        start: float = time.time()  # Registra o tempo de início
        self._warm_session()  # Inicializa a sessão HTTP

        for keyword in self.keywords:  # Percorre cada palavra-chave
            self._process_keyword(keyword)  # Processa as páginas da palavra-chave
            time.sleep(self.delay)  # Pausa entre palavras-chave

        elapsed: float = time.time() - start  # Calcula a duração total
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")
        logger.info(f"Total processed: {self.total_processed} | Total saved to DB: {self.total_inserted}")


# ──────────────────────────────────────────────────────────────────────────────
# FUNÇÕES DE EXPORTAÇÃO (EXCEL / CSV / JSON)
# ──────────────────────────────────────────────────────────────────────────────
def export_to_format(db_path: str, export_path: str, chunksize: int = 50000) -> bool:
    """
    Exporta a tabela article_metadata do SQLite para Excel, CSV ou JSON.
    Mantém o nome das colunas compatível com o BDTD Harvester para integração do projeto.
    """
    logger.info(f"Exporting database records to: {export_path}")
    try:
        conn: sqlite3.Connection = sqlite3.connect(db_path)  # Conecta ao banco SQLite
        
        # Consulta SQL com apelidos de colunas alinhados ao padrão da BDTD
        query: str = """
            SELECT
                authors   AS "Autores",
                title     AS "Título",
                year      AS "Ano",
                type_of_research AS "Tipo de Pesquisa",
                'N/A (artigo)' AS "Nome do Orientador",
                journal   AS "Universidade / Editora / Revista",
                abstract  AS "Resumo",
                article_url AS "Link para Download"
            FROM article_metadata
            ORDER BY harvested_at DESC
        """
        
        ext: str = os.path.splitext(export_path)[1].lower()  # Pega a extensão do arquivo
        
        # Gravação em blocos para CSV para economia de memória RAM
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
            
        df: pd.DataFrame = pd.read_sql_query(query, conn)  # Carrega os dados para Excel/JSON
        conn.close()
        
        if df.empty:  # Se a tabela estiver vazia
            logger.warning("No records found in the database to export.")
            return False
            
        if ext in ['.xlsx', '.xls']:  # Salva em Excel
            df.to_excel(export_path, index=False)
        elif ext == '.json':  # Salva em JSON
            df.to_json(export_path, orient='records', force_ascii=False, indent=4)
        else:  # Fallback CSV
            logger.warning(f"Unrecognized export format: {ext}. Defaulting to CSV.")
            df.to_csv(export_path, index=False, encoding='utf-8')
            
        logger.info(f"Successfully exported {len(df)} records.")  # Confirma exportação
        return True
    except Exception as e:
        logger.error(f"Failed to export database: {e}")  # Loga falha
        return False


# ──────────────────────────────────────────────────────────────────────────────
# PONTO DE ENTRADA PROGRAMÁTICO (API PYTHON)
# ──────────────────────────────────────────────────────────────────────────────
def run_harvest(
    keywords: List[str],
    db_path: str = "scielo_metadata.db",
    export_path: str = "scielo_resultados.xlsx",
    limit: Optional[int] = None,
    delay: float = 3.0,
    search_field: str = "",
) -> bool:
    """
    Ponto de entrada programático de alto nível para executar o pipeline SciELO Harvester.
    """
    log_dir: str = os.path.dirname(export_path) if os.path.dirname(export_path) else "."
    log_file_path: str = os.path.join(log_dir, "log_scielo.txt")
    setup_logging(log_file_path)  # Configura os handlers de log sem duplicação

    db_manager: Optional[DatabaseManager] = None
    try:
        db_manager = DatabaseManager(db_path)  # Inicializa o gerenciador SQLite
        pipeline: SciELOHarvesterPipeline = SciELOHarvesterPipeline(  # Instancia o pipeline SciELO
            db_manager=db_manager,
            keywords=keywords,
            limit_per_keyword=limit,
            delay=delay,
            search_field=search_field,
        )
        pipeline.run()  # Executa a coleta
        db_manager.close()  # Garante encerramento da conexão
        db_manager = None
        export_to_format(db_path, export_path)  # Exporta os resultados
        return True  # Retorna True em caso de sucesso
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return False
    finally:
        if db_manager:  # Garante fechamento do banco no bloco finally
            db_manager.close()


# ──────────────────────────────────────────────────────────────────────────────
# INTERFACE DE LINHA DE COMANDO (CLI) E EXECUÇÃO PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    """Função principal para parsing de argumentos via linha de comando (CLI)."""
    parser = argparse.ArgumentParser(
        description="Automated Python pipeline to extract SciELO article metadata.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Definição dos argumentos aceitos pela CLI
    parser.add_argument("--db-path", type=str, default="scielo_metadata.db", help="Destination SQLite database.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum records per keyword.")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between page requests (seconds).")
    parser.add_argument("--keywords", type=str, nargs="+", default=["planejamento urbano"], help="Search keywords.")
    parser.add_argument("--export", type=str, default="scielo_resultados.xlsx", help="Output file path.")
    parser.add_argument("--config", type=str, default=None, help="Path to JSON config file.")
    parser.add_argument("--search-field", type=str, default="", help="SciELO search field filter.")

    args = parser.parse_args()  # Lê os argumentos passados
    setup_logging()  # Configura logging no terminal

    config_file: Optional[str] = args.config  # Caminho do arquivo de configuração
    use_config: bool = False

    if config_file and os.path.exists(config_file):  # Se o arquivo foi especificado e existe
        use_config = True
    elif not config_file and os.path.exists("scielo_config.json"):  # Se existir o scielo_config.json padrão
        config_file = "scielo_config.json"
        use_config = True

    db_path: str = args.db_path
    export_path: str = args.export
    limit: Optional[int] = args.limit
    delay: float = args.delay
    keywords: List[str] = args.keywords
    search_field: str = args.search_field

    if use_config and config_file:  # Carrega as opções do arquivo JSON se disponível
        try:
            config = read_json_config_file(config_file)
            db_path = config["db_path"]
            export_path = config["export_path"]
            limit = config["limit"]
            delay = config["delay"]
            keywords = config["keywords"]
            search_field = config.get("search_field", "")
            logger.info(f"Loaded config from {config_file}")
        except Exception as e:
            logger.error(f"Failed to read config: {e}. Falling back to CLI args.")

    else:
        if not config_file and not os.path.exists("scielo_config.json"):
            try:
                create_json_config_template("scielo_config.json")  # Gera o modelo JSON padrão se não existir
            except Exception as e:
                logger.warning(f"Could not create config template: {e}")

    if not keywords:  # Se nenhuma palavra-chave for fornecida
        logger.error("No keywords specified.")
        return

    try:
        # Executa o pipeline de coleta
        success: bool = run_harvest(
            keywords=keywords,
            db_path=db_path,
            export_path=export_path,
            limit=limit,
            delay=delay,
            search_field=search_field,
        )
        if success:
            logger.info("Pipeline executed successfully.")
        else:
            logger.error("Pipeline finished with errors.")
    except KeyboardInterrupt:  # Tratamento de interrupção pelo usuário (Ctrl+C)
        logger.warning("\nPipeline interrupted by user.")
    except Exception as e:  # Captura falha crítica não tratada
        logger.critical(f"Pipeline crashed: {e}", exc_info=True)


# Ponto de entrada do script quando executado diretamente
if __name__ == "__main__":
    main()  # Executa a função principal main