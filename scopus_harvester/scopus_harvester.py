#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scopus Harvester - Automated Python pipeline to extract Scopus article metadata.

Retrieves scholarly work metadata from the Scopus Search API (api.elsevier.com),
supports view=COMPLETE (full author list and abstract) with automatic fallback
to view=STANDARD and the Abstract Retrieval API in case of 403 Forbidden errors.
Saves data to SQLite to enable incremental runs, and exports to Excel/CSV/JSON.
"""

import argparse
import json
import logging
import os
import sys
import sqlite3
import time
from datetime import datetime

import pandas as pd
import requests

# ============================================================
# Logging Config
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
# Helper Functions
# ============================================================
def translate_format(subtype_desc: str, agg_type: str) -> str:
    """
    Translates Scopus subtypeDescription or prism:aggregationType to Portuguese.
    """
    val = (subtype_desc or agg_type or "").lower().strip()
    if not val:
        return "Artigo"
    if "article" in val:
        return "Artigo"
    elif "review" in val:
        return "Revisão"
    elif "conference" in val or "proceeding" in val:
        return "Artigo de Conferência"
    elif "chapter" in val:
        return "Capítulo de Livro"
    elif "book" in val:
        return "Livro"
    elif "thesis" in val or "dissertation" in val:
        return "Tese/Dissertação"
    return val.capitalize()


def extract_authors(entry: dict) -> str:
    """
    Extracts and joins author names into a single string separated by semicolons.
    """
    authors_data = entry.get("author")
    if authors_data:
        # Check if single author (dict) or list of authors
        if isinstance(authors_data, dict):
            authors_data = [authors_data]
        
        author_list = []
        for auth in authors_data:
            name = auth.get("authname")
            if not name:
                surname = auth.get("surname", "")
                given = auth.get("given-name", "")
                if surname or given:
                    name = f"{surname}, {given}".strip(", ")
            if name:
                author_list.append(name.strip())
        
        if author_list:
            return "; ".join(author_list)

    # Fallback to dc:creator (often first author name as string in STANDARD view)
    creator = entry.get("dc:creator")
    if creator:
        return creator.strip()

    return "Não Informado"


def extract_url(entry: dict) -> str:
    """
    Extracts the most relevant web URL to the document in Scopus.
    """
    links = entry.get("link", [])
    if isinstance(links, dict):
        links = [links]

    # Look for link with @ref or @rel equal to 'scopus'
    for link in links:
        ref = link.get("@ref") or link.get("@rel")
        if ref == "scopus":
            href = link.get("@href")
            if href:
                return href

    # Try 'self' URL (usually API URL)
    for link in links:
        ref = link.get("@ref") or link.get("@rel")
        if ref == "self":
            href = link.get("@href")
            if href:
                return href

    # Fallback using DOI
    doi = entry.get("prism:doi")
    if doi:
        return f"https://doi.org/{doi}"

    # Fallback using EID
    eid = entry.get("eid")
    if eid:
        return f"https://www.scopus.com/record/display.uri?eid={eid}&origin=resultslist"

    return "Não Informado"


def fetch_abstract_retrieval(eid: str, api_key: str, headers: dict) -> str:
    """
    Queries the Abstract Retrieval API as a fallback when view=STANDARD is active.
    """
    url = f"https://api.elsevier.com/content/abstract/eid/{eid}"
    params = {
        "view": "META_ABS"
    }
    
    # Copy headers to avoid mutating parent
    req_headers = headers.copy()
    req_headers["Accept"] = "application/json"
    
    try:
        logger.info(f"Querying Abstract Retrieval API for EID: {eid}...")
        response = requests.get(url, headers=req_headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            ret_response = data.get("abstracts-retrieval-response", {})
            coredata = ret_response.get("coredata", {})
            desc = coredata.get("dc:description")
            if desc:
                # Handle possible JSON structure variations
                if isinstance(desc, dict):
                    # sometimes desc can contain key '$'
                    desc = desc.get("$", "")
                return str(desc).strip()
        elif response.status_code == 403:
            logger.warning(f"Abstract retrieval for EID {eid} returned 403 Forbidden (restricted subscription).")
    except Exception as e:
        logger.error(f"Failed to fetch abstract for EID {eid} via Abstract Retrieval: {e}")

    return "Não disponível na busca padrão (requer view=COMPLETE)"


# ============================================================
# Config Parser
# ============================================================
def read_json_config(file_path: str) -> dict:
    """
    Reads configuration from JSON using Pydantic schema validation.
    """
    logger.info(f"Reading configuration from JSON: {file_path}")
    try:
        from config_app.core.config_schemas import ScopusConfig, load_and_validate_config
        validated = load_and_validate_config(file_path, ScopusConfig)
        data = validated.model_dump()
    except Exception as e:
        logger.warning(f"Validação de schema via Pydantic falhou ou indisponível ({e}). Usando fallback de leitura bruta.")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    return {
        "keywords": data.get("keywords", []),
        "db_path": data.get("db_path", "scopus_metadata.db"),
        "export_path": data.get("export_path", "scopus_resultados.xlsx"),
        "limit": data.get("limit"),
        "delay": float(data.get("delay", 1.0)),
        "api_key": data.get("api_key", ""),
        "view": data.get("view", "COMPLETE"),
        "insttoken": data.get("insttoken", "")
    }


# ============================================================
# Database Manager
# ============================================================
class DatabaseManager:
    """
    Manages SQLite database creation and record insertions.
    Schema matches BDTD, SciELO, and OpenAlex.
    """
    SCHEMA = """
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

    def __init__(self, db_path):
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        open_db_path = db_path
        if sys.platform.startswith('win') and len(os.path.abspath(open_db_path)) >= 240 and not os.path.abspath(open_db_path).startswith('\\\\?\\'):
            open_db_path = '\\\\?\\' + os.path.abspath(open_db_path)
        self.conn = sqlite3.connect(open_db_path)
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as e:
            logger.warning(f"Could not enable WAL mode ({e}), falling back to default journal mode.")
        self.conn.executescript(self.SCHEMA)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_scopus_year ON scopus_metadata (year);")
        self.conn.commit()
        logger.info(f"Database initialized successfully at: {db_path}")

    def insert_record(self, record: dict) -> bool:
        """
        Inserts a single academic record. Returns True if inserted, False if duplicate.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO scopus_metadata
                (id, title, authors, year, type_of_research, advisor, journal, abstract, doi, article_url, keyword_query)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["title"],
                    record["authors"],
                    record["year"],
                    record["type_of_research"],
                    record.get("advisor", "Não Informado"),
                    record["journal"],
                    record["abstract"],
                    record["doi"],
                    record["article_url"],
                    record["keyword_query"]
                )
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error inserting record {record.get('id')}: {e}")
            return False

    def record_exists(self, record_id: str) -> bool:
        """
        Checks if a record already exists in the database.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1 FROM scopus_metadata WHERE id = ?", (record_id,))
            return cursor.fetchone() is not None
        except sqlite3.Error:
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed.")


# ============================================================
# Scopus Harvester Pipeline
# ============================================================
class ScopusHarvesterPipeline:
    """
    Queries Scopus REST Search API with cursor pagination, handles COMPLETE vs STANDARD fallback,
    saves retrieved results to SQLite database, and prepares raw data cache.
    """
    SEARCH_URL = "https://api.elsevier.com/content/search/scopus"

    def __init__(self, db_manager: DatabaseManager, config: dict):
        self.db = db_manager
        self.keywords = config["keywords"]
        self.limit = config["limit"]
        self.delay = config["delay"]
        self.api_key = config["api_key"]
        self.view = config["view"] # COMPLETE or STANDARD
        self.insttoken = config.get("insttoken", "")

        # Headers setup
        self.headers = {
            "Accept": "application/json",
            "X-ELS-APIKey": self.api_key
        }
        if self.insttoken:
            self.headers["X-ELS-Insttoken"] = self.insttoken

        self.total_processed = 0
        self.total_inserted = 0
        self.raw_results_cache = []
        self.pagination_mode = "cursor"
        self.start_offset = 0

    def fetch_page(self, params: dict) -> dict | None:
        """
        Fetches search page from Scopus API with error handling.
        """
        try:
            logger.info(f"Request parameters: {params}")
            response = requests.get(
                self.SEARCH_URL,
                headers=self.headers,
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            
            elif response.status_code in [400, 401, 403]:
                # Check if it is a view entitlement error or cursor restriction error
                is_view_auth_error = False
                is_cursor_restricted = False
                try:
                    err_json = response.json()
                    status_text = err_json.get("service-error", {}).get("status", {}).get("statusText", "")
                    if "not authorized to access the requested view" in status_text.lower():
                        is_view_auth_error = True
                    if "use of the cursor parameter is restricted" in status_text.lower():
                        is_cursor_restricted = True
                except Exception:
                    pass

                # If cursor is restricted, fallback to offset pagination immediately
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
                    return self.fetch_page(params)

                # If view was COMPLETE, we fallback to STANDARD
                if params.get("view") == "COMPLETE" and (response.status_code in [401, 403] or is_view_auth_error):
                    logger.warning(
                        f"HTTP {response.status_code} View Authorization issue encountered with view=COMPLETE. "
                        "Your API key or IP address does not have entitlement to retrieve complete records. "
                        "Migrating to view=STANDARD for this run."
                    )
                    # Trigger fallback in-place
                    self.view = "STANDARD"
                    params["view"] = "STANDARD"
                    # Retry immediately with STANDARD view
                    return self.fetch_page(params)
                else:
                    logger.error(
                        f"Scopus API Access Error ({response.status_code}). Please verify your API Key "
                        f"and network connection (VPN/Institutional IP). Response: {response.text}"
                    )
            elif response.status_code == 429:
                logger.warning("Scopus API rate limit exceeded (429). Sleeping for 5 seconds...")
                time.sleep(5.0)
                return self.fetch_page(params)
            else:
                logger.error(
                    f"Scopus API returned HTTP {response.status_code}: {response.text}"
                )
        except requests.RequestException as e:
            logger.error(f"Network error querying Scopus API: {e}")
            
        return None

    def process_keyword(self, keyword: str):
        """
        Runs cursor pagination for a single keyword.
        """
        logger.info(f"Target query: '{keyword}'")
        
        # Scopus search params
        params = {
            "query": keyword,
            "count": 25,  # 25 is optimal and standard for COMPLETE views
            "cursor": "*",
            "view": self.view
        }

        saved_for_keyword = 0
        processed_for_keyword = 0
        page_num = 1
        total_results = None

        logger.info("Initiating search queries on Scopus API...")

        while True:
            logger.info(f"Requesting page {page_num}...")
            data = self.fetch_page(params)
            
            if data is None:
                logger.error("Failed to retrieve data page. Stopping current keyword.")
                break

            results_payload = data.get("search-results", {})
            
            # Fetch total matches if not yet set
            if total_results is None:
                total_results = results_payload.get("opensearch:totalResults", "0")
                logger.info(f"Total matching records in Scopus catalog: {total_results}")

            entries = results_payload.get("entry", [])
            if not entries:
                logger.info("No more results returned. Finished this keyword.")
                break

            # Handle case where single entry is dict instead of list
            if isinstance(entries, dict):
                entries = [entries]

            fetched_count = len(entries)
            logger.info(f"Fetched {fetched_count} records from page {page_num}.")
            
            # Cache raw results
            self.raw_results_cache.extend(entries)

            for entry in entries:
                processed_for_keyword += 1
                self.total_processed += 1

                # Parse unique ID: we parse it from 'dc:identifier' or 'eid'
                eid = entry.get("eid")
                dc_id = entry.get("dc:identifier")
                record_id = eid or (dc_id.replace("SCOPUS_ID:", "") if dc_id else None)
                
                if not record_id:
                    continue

                if self.db.record_exists(record_id):
                    # Record already harvested, skip to avoid duplicate processing and API calls
                    continue

                title = entry.get("dc:title") or ""
                if not title.strip():
                    continue

                authors = extract_authors(entry)
                
                cover_date = entry.get("prism:coverDate") or ""
                year = cover_date[:4] if len(cover_date) >= 4 else "Não Informado"
                
                type_of_research = translate_format(
                    entry.get("subtypeDescription"),
                    entry.get("prism:aggregationType")
                )
                
                journal = entry.get("prism:publicationName") or "Não Informado"
                
                # Fetch or resolve abstract
                abstract = "Não Informado"
                if self.view == "COMPLETE":
                    abstract = entry.get("dc:description")
                    if isinstance(abstract, dict):
                        abstract = abstract.get("$", "")
                
                # If abstract is not available, try to fetch it via retrieval API
                if not abstract or str(abstract).strip().lower() in ["none", "não informado", ""]:
                    # Call retrieval API
                    abstract = fetch_abstract_retrieval(record_id, self.api_key, self.headers)
                    # Be polite, wait a fraction of a second to prevent aggressive polling
                    time.sleep(0.2)

                doi = entry.get("prism:doi") or "Não Informado"
                article_url = extract_url(entry)

                record = {
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

                inserted = self.db.insert_record(record)
                if inserted:
                    saved_for_keyword += 1
                    self.total_inserted += 1
                    logger.info(f" -> [SAVED] {record_id} | Autores: {authors[:40]} | Fonte: {journal[:40]}")

                if self.limit and saved_for_keyword >= self.limit:
                    logger.info(f"Limit of {self.limit} records reached for keyword '{keyword}'.")
                    break

            if self.limit and saved_for_keyword >= self.limit:
                break

            # Handle pagination
            if self.pagination_mode == "cursor":
                cursor_obj = results_payload.get("cursor", {})
                current_cursor = cursor_obj.get("@current")
                next_cursor = cursor_obj.get("@next")
                
                # If next cursor is empty, identical, or not present, we terminate
                if not next_cursor or next_cursor == current_cursor:
                    logger.info("Finished harvesting all matches from Scopus for this query.")
                    break

                params["cursor"] = next_cursor
            else:
                # Offset mode pagination
                if fetched_count < params["count"]:
                    logger.info("Fetched less than page count. Finished harvesting all matches from Scopus.")
                    break
                
                self.start_offset += fetched_count
                params["start"] = self.start_offset

                # Enforce safety offset limit (5000) for standard API keys
                if self.start_offset >= 5000:
                    logger.warning("Reached Scopus 5,000 record offset limit for standard API keys.")
                    break

            page_num += 1
            time.sleep(self.delay)

        logger.info(
            f"Finished '{keyword}': processed {processed_for_keyword} "
            f"records, saved {saved_for_keyword} relevant records."
        )

    def run(self):
        """
        Runs the harvesting pipeline for all keywords.
        """
        logger.info("=== SCOPUS SYSTEM DATA HARVESTER STARTED ===")
        start = time.time()

        for keyword in self.keywords:
            self.process_keyword(keyword)
            time.sleep(self.delay)

        elapsed = time.time() - start
        logger.info("=== SCOPUS SYSTEM DATA HARVESTER PROCESS COMPLETED ===")
        logger.info(f"Total processed: {self.total_processed} | Total saved to DB: {self.total_inserted}")
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")


# ============================================================
# Export Functions
# ============================================================
def export_to_format(db_path: str, export_path: str) -> bool:
    """
    Exports scopus_metadata table to Excel, CSV, or JSON.
    Column names match BDTD, SciELO, and OpenAlex for seamless consolidation.
    """
    logger.info(f"Exporting database records to: {export_path}")
    try:
        conn = sqlite3.connect(db_path)
        query = """
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
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            logger.warning("No records found in the database to export.")
            return False

        ext = os.path.splitext(export_path)[1].lower()
        
        # Ensure export directory exists
        export_dir = os.path.dirname(export_path)
        if export_dir:
            os.makedirs(export_dir, exist_ok=True)
            
        if ext in [".xlsx", ".xls"]:
            df.to_excel(export_path, index=False)
        elif ext == ".csv":
            df.to_csv(export_path, index=False, encoding="utf-8")
        elif ext == ".json":
            df.to_json(
                export_path, orient="records", force_ascii=False, indent=4
            )
        else:
            logger.warning(f"Unrecognized export format: {ext}. Defaulting to Excel (.xlsx).")
            df.to_excel(export_path, index=False)

        logger.info(f"Successfully exported {len(df)} records.")
        return True
    except Exception as e:
        logger.error(f"Failed to export database: {e}")
        return False


# ============================================================
# High-Level API
# ============================================================
def run_harvest(config: dict) -> bool:
    """
    High-level entrypoint to execute the Scopus harvesting pipeline.
    """
    db_manager = None
    try:
        # Initialize SQLite DB
        db_manager = DatabaseManager(config["db_path"])
        
        # Initialize and run pipeline
        pipeline = ScopusHarvesterPipeline(db_manager, config)
        pipeline.run()

        # Export Excel (default/specified path)
        export_to_format(config["db_path"], config["export_path"])

        db_manager.close()
        db_manager = None
        return True
        
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        return False
    finally:
        if db_manager:
            db_manager.close()


# ============================================================
# CLI Command Line Interface
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Automated Python pipeline to harvest scholarly metadata from Scopus.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON configuration file (e.g. scopus_config.json)."
    )
    parser.add_argument(
        "--keywords",
        type=str,
        nargs="+",
        help="Search keywords or queries (overrides config if provided)."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to SQLite database file."
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export target path (Excel, CSV, JSON)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit of records to harvest per keyword."
    )
    parser.add_argument(
        "--delay",
        type=float,
        help="Delay between requests in seconds."
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Scopus API Key."
    )
    parser.add_argument(
        "--view",
        type=str,
        choices=["STANDARD", "COMPLETE"],
        help="Scopus view mode."
    )

    args = parser.parse_args()

    # Load configuration
    config = {}
    config_file = args.config

    # If no config specified but scopus_config.json exists, load it by default
    if not config_file and os.path.exists("scopus_config.json"):
        config_file = "scopus_config.json"

    if config_file and os.path.exists(config_file):
        config = read_json_config(config_file)
    else:
        # Defaults
        config = {
            "keywords": ["\"planejamento urbano\""],
            "db_path": "scopus_metadata.db",
            "export_path": "scopus_resultados.xlsx",
            "limit": None,
            "delay": 1.0,
            "api_key": "",
            "view": "COMPLETE"
        }

    # Override config with command line arguments if provided
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

    if not config.get("api_key"):
        logger.error(
            "Scopus API Key is missing. Please provide it via config file "
            "or command line --api-key parameter."
        )
        return

    # Execute
    run_harvest(config)


if __name__ == "__main__":
    main()
