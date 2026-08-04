#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAlex Harvester - Automated Python pipeline to extract OpenAlex article metadata.

Retrieves scholarly work metadata from the OpenAlex API (api.openalex.org),
reconstructs abstracts from inverted index format, saves to SQLite, and
exports to Excel/CSV/JSON in a format compatible with BDTD and SciELO outputs.

Supports both standard flat configuration and nested notebook configuration.
"""

import argparse
import json
import logging
import os
import sys
import re
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
def reconstruct_abstract(inverted_index) -> str:
    """
    Reconstructs plain text abstract from OpenAlex's abstract_inverted_index.
    """
    if not inverted_index or not isinstance(inverted_index, dict):
        return "Não Informado"
    try:
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        # Sort by their positions in the text
        word_positions.sort(key=lambda x: x[0])
        return " ".join([word for pos, word in word_positions])
    except Exception:
        return "Não Informado"


def translate_format(fmt_str) -> str:
    """
    Translates OpenAlex work type key to a user-friendly Portuguese descriptor.
    """
    if not fmt_str:
        return "Artigo"
    fmt = fmt_str.lower()
    if fmt in ["article", "journal-article"]:
        return "Artigo"
    elif fmt == "book-chapter":
        return "Capítulo de Livro"
    elif fmt == "book":
        return "Livro"
    elif fmt in ["dissertation", "thesis"]:
        return "Tese/Dissertação"
    elif fmt == "preprint":
        return "Preprint"
    return fmt_str.capitalize()


def extract_authors(work: dict) -> str:
    """
    Extracts and joins all author names into a single string separated by semicolons.
    """
    authorships = work.get("authorships", [])
    authorship_list = [
        a.get("author", {}).get("display_name", "")
        for a in authorships
        if a.get("author", {}).get("display_name")
    ]
    if not authorship_list:
        return "Não Informado"
    
    cleaned_authors = []
    for author in authorship_list:
        author = author.strip()
        if author:
            cleaned_authors.append(author)
            
    return "; ".join(cleaned_authors) if cleaned_authors else "Não Informado"


def extract_source(work: dict) -> str:
    """
    Extracts the source venue name (Journal, Conference, Publisher, etc.)
    """
    source_name = ""
    primary_loc = work.get("primary_location") or {}
    if primary_loc:
        source = primary_loc.get("source") or {}
        source_name = source.get("display_name", "")
        
    if not source_name:
        for loc in work.get("locations", []):
            if loc:
                source = loc.get("source") or {}
                source_name = source.get("display_name", "")
                if source_name:
                    break
                    
    return source_name.strip() if source_name else "Não Informado"


def extract_download_url(work: dict) -> str:
    """
    Extracts the most relevant open-access download or access URL for a work.
    """
    # 1. Best Open Access location PDF URL
    best_oa = work.get("best_oa_location") or {}
    if best_oa.get("pdf_url"):
        return best_oa.get("pdf_url")

    # 2. Primary location PDF URL
    prim_loc = work.get("primary_location") or {}
    if prim_loc.get("pdf_url"):
        return prim_loc.get("pdf_url")

    # 3. Best Open Access location landing page URL
    if best_oa.get("landing_page_url"):
        return best_oa.get("landing_page_url")

    # 4. Primary location landing page URL
    if prim_loc.get("landing_page_url"):
        return prim_loc.get("landing_page_url")

    # 5. Any location PDF or landing page URL
    for loc in work.get("locations", []):
        if loc:
            if loc.get("pdf_url"):
                return loc.get("pdf_url")
            if loc.get("landing_page_url"):
                return loc.get("landing_page_url")

    # 6. DOI URL
    if work.get("doi"):
        return work.get("doi")

    return "Não Informado"


# ============================================================
# Config Parser
# ============================================================
def read_json_config(file_path: str) -> dict:
    """
    Reads configuration from JSON and automatically handles flat or nested schemas.
    """
    logger.info(f"Reading configuration from JSON: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Check for nested notebook format (Interface_Revisao.ipynb)
    if "search" in data and "api" in data and "paths" in data:
        search = data["search"]
        api = data["api"]
        paths = data["paths"]

        # Parse query filters
        filters_dict = {}
        nb_filters = search.get("filters", {})
        start_year = search.get("start_year")
        end_year = search.get("end_year")

        if start_year and end_year:
            filters_dict["publication_year"] = f"{start_year}-{end_year}"
        elif start_year:
            filters_dict["publication_year"] = f">={start_year}"
        elif end_year:
            filters_dict["publication_year"] = f"<={end_year}"

        if nb_filters.get("only_open_access"):
            filters_dict["is_oa"] = "true"

        if nb_filters.get("repository_ids"):
            filters_dict["locations.source.id"] = "|".join(nb_filters["repository_ids"])
        if nb_filters.get("publisher_ids"):
            filters_dict["primary_location.source.publisher_lineage"] = "|".join(nb_filters["publisher_ids"])
        if nb_filters.get("source_types"):
            filters_dict["locations.source.type"] = "|".join(nb_filters["source_types"])

        # Resolve paths
        out_dir = paths.get("output_dir", "openalex_outputs")
        os.makedirs(out_dir, exist_ok=True)

        return {
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
        # 2. Standard flat format
        try:
            from config_app.core.config_schemas import OpenAlexConfig, load_and_validate_config
            validated = load_and_validate_config(file_path, OpenAlexConfig)
            vdata = validated.model_dump()
        except Exception as e:
            logger.warning(f"Validação de schema via Pydantic falhou ou indisponível ({e}). Usando fallback de leitura bruta.")
            vdata = data

        filters_dict = vdata.get("filters", {})
        return {
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


def create_default_config_template(file_path: str):
    """
    Creates a template JSON configuration file.
    """
    logger.info(f"Creating a new JSON configuration template: {file_path}")
    template = {
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
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=4)
    logger.info(f"Successfully generated JSON config template at {file_path}")


# ============================================================
# Database Manager
# ============================================================
class DatabaseManager:
    """
    Manages SQLite database creation and record insertions.
    """
    SCHEMA = """
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
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_openalex_year ON openalex_metadata (year);")
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
                INSERT OR IGNORE INTO openalex_metadata
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

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed.")


# ============================================================
# OpenAlex Harvester Pipeline
# ============================================================
class OpenAlexHarvesterPipeline:
    """
    Queries OpenAlex REST API with cursor pagination, mapping retrieved results
    to SQLite and exporting to Excel/CSV/JSON formats.
    """
    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, db_manager: DatabaseManager, config: dict):
        self.db = db_manager
        self.keywords = config["keywords"]
        self.limit = config["limit"]
        self.delay = config["delay"]
        self.api_key = config["api_key"]
        
        # Build headers
        self.email = config.get("email", "")
        # Parse email from user-agent if present
        if not self.email and config.get("user_agent"):
            m = re.search(r'(?:contact|mailto)\s*:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', config["user_agent"])
            if m:
                self.email = m.group(1)

        self.headers = {}
        if self.email:
            self.headers["User-Agent"] = f"mailto:{self.email}"
        elif config["user_agent"]:
            self.headers["User-Agent"] = config["user_agent"]
        else:
            self.headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

        self.max_retries = config.get("max_retries", 5)
        self.backoff_factor = config.get("backoff_factor", 1.5)
        self.filters = config.get("filters", {})

        self.total_processed = 0
        self.total_inserted = 0
        self.raw_results_cache = []

    def fetch_page_with_retry(self, params: dict) -> dict | None:
        """
        Fetches page from OpenAlex with retries and exponential backoff.
        """
        retries = 0
        current_delay = self.delay
        
        while retries < self.max_retries:
            try:
                # Append API key and mailto if provided
                req_params = params.copy()
                if self.api_key:
                    req_params["api_key"] = self.api_key
                if self.email:
                    req_params["mailto"] = self.email

                logger.info(f"Request parameters: {req_params}")
                logger.info(f"Request headers: {self.headers}")

                response = requests.get(
                    self.BASE_URL,
                    params=req_params,
                    headers=self.headers,
                    timeout=30
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    logger.warning(
                        "Rate limit hit (429 Too Many Requests). "
                        f"Retrying attempt {retries + 1}/{self.max_retries}..."
                    )
                else:
                    logger.error(
                        f"API request failed with HTTP {response.status_code}: {response.text}"
                    )
                    
            except requests.RequestException as e:
                logger.warning(
                    f"Network error (Attempt {retries + 1}/{self.max_retries}): {e}"
                )

            retries += 1
            if retries < self.max_retries:
                sleep_time = current_delay * (self.backoff_factor ** (retries - 1))
                time.sleep(sleep_time)

        return None

    def process_keyword(self, keyword: str):
        """
        Retrieves all pages for a single keyword query using cursor pagination.
        """
        logger.info(f"Target query: '{keyword}'")
        
        # Build filter parameter and query parameters
        filter_parts = []
        params = {
            "per_page": 50, # Optimal default page size
            "cursor": "*"
        }
        
        # Include search query
        if keyword:
            if "*" in keyword or "?" in keyword:
                params["search.exact"] = keyword
            else:
                filter_parts.append(f"title_and_abstract.search:{keyword}")
            
        # Add extra filters
        for key, value in self.filters.items():
            if value:
                if key != "publication_year" or "publication_year" not in filter_parts:
                    if key == "language" and "," in value:
                        # OpenAlex OR separator is '|'
                        val_cleaned = "|".join([v.strip() for v in value.split(",")])
                        filter_parts.append(f"{key}:{val_cleaned}")
                    else:
                        filter_parts.append(f"{key}:{value}")
                
        if filter_parts:
            params["filter"] = ",".join(filter_parts)
            
        logger.info(f"Query params: {params}")

        saved_for_keyword = 0
        processed_for_keyword = 0
        page_num = 1
        total_results = None

        logger.info("Initiating search queries on OpenAlex API...")

        while True:
            logger.info(f"Requesting results starting page {page_num}...")
            data = self.fetch_page_with_retry(params)
            
            if data is None:
                logger.error("Failed to fetch page. Stopping this keyword.")
                break

            results = data.get("results", [])
            if not results:
                logger.info("No more results found. Finished this keyword.")
                break

            if total_results is None:
                total_results = data.get("meta", {}).get("count", 0)
                logger.info(f"Total matching records in OpenAlex catalog: {total_results}")

            fetched_count = len(results)
            logger.info(f"Fetched {fetched_count} records from page {page_num}.")
            
            # Cache raw results for JSON backup
            self.raw_results_cache.extend(results)

            for work in results:
                processed_for_keyword += 1
                self.total_processed += 1

                # Parse work metadata
                work_id = work.get("id", "").split("/")[-1] if "/" in work.get("id", "") else work.get("id", "")
                if not work_id:
                    continue

                title = work.get("title") or work.get("display_name") or ""
                if not title.strip():
                    continue

                authors = extract_authors(work)
                year = str(work.get("publication_year", ""))
                type_of_research = translate_format(work.get("type", ""))
                journal = extract_source(work)
                abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
                
                doi_raw = work.get("doi") or ""
                doi = doi_raw.replace("https://doi.org/", "") if doi_raw else "Não Informado"
                
                article_url = extract_download_url(work)

                record = {
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

                inserted = self.db.insert_record(record)
                if inserted:
                    saved_for_keyword += 1
                    self.total_inserted += 1
                    logger.info(f" -> [SAVED] {work_id} | Autores: {authors[:40]} | Fonte: {journal[:40]}")

                if self.limit and saved_for_keyword >= self.limit:
                    logger.info(f"Limit of {self.limit} records reached for keyword '{keyword}'.")
                    break

            if self.limit and saved_for_keyword >= self.limit:
                break

            next_cursor = data.get("meta", {}).get("next_cursor")
            if not next_cursor or next_cursor == params["cursor"]:
                logger.info("Finished harvesting all matches from OpenAlex.")
                break

            params["cursor"] = next_cursor
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
        logger.info("=== OPENALEX SYSTEM DATA HARVESTER STARTED ===")
        start = time.time()

        for keyword in self.keywords:
            self.process_keyword(keyword)
            time.sleep(self.delay)

        elapsed = time.time() - start
        logger.info("=== OPENALEX SYSTEM DATA HARVESTER PROCESS COMPLETED SUCCESSFULLY ===")
        logger.info(f"Total processed: {self.total_processed} | Total saved to DB: {self.total_inserted}")
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")


# ============================================================
# Export and Summary Report Functions
# ============================================================
def export_to_format(db_path: str, export_path: str) -> bool:
    """
    Exports openalex_metadata table to Excel, CSV, or JSON.
    Column names match the BDTD harvester output for compatibility.
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
            FROM openalex_metadata
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
            logger.warning(
                f"Unrecognized export format: {ext}. Defaulting to CSV."
            )
            df.to_csv(export_path, index=False, encoding="utf-8")

        logger.info(f"Successfully exported {len(df)} records.")
        return True
    except Exception as e:
        logger.error(f"Failed to export database: {e}")
        return False


def generate_markdown_report(db_path: str, report_path: str, query_details: str):
    """
    Generates a beautiful summary report in markdown.
    """
    logger.info(f"Generating markdown summary report: {report_path}")
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT year, type_of_research, journal FROM openalex_metadata", conn)
        conn.close()

        if df.empty:
            logger.warning("No data found to generate markdown report.")
            return

        total_records = len(df)
        year_dist = df["year"].value_counts().sort_index().to_dict()
        type_dist = df["type_of_research"].value_counts().to_dict()
        top_venues = df["journal"].value_counts().head(10).to_dict()

        report_dir = os.path.dirname(report_path)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)

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


# ============================================================
# High-Level API
# ============================================================
def run_harvest(config: dict) -> bool:
    """
    High-level entrypoint to execute the OpenAlex harvesting pipeline.
    """
    db_manager = None
    try:
        # Set up log file handler if configured
        if config.get("log_path"):
            log_dir = os.path.dirname(config["log_path"])
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            open_path = config["log_path"]
            if sys.platform.startswith('win') and len(os.path.abspath(open_path)) >= 250 and not os.path.abspath(open_path).startswith('\\\\?\\'):
                open_path = '\\\\?\\' + os.path.abspath(open_path)
            fh = logging.FileHandler(open_path, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            logger.addHandler(fh)

        # Initialize SQLite DB
        db_manager = DatabaseManager(config["db_path"])
        
        # Initialize and run pipeline
        pipeline = OpenAlexHarvesterPipeline(db_manager, config)
        pipeline.run()

        # Cache raw data if JSON backup configured
        if config.get("json_path") and pipeline.raw_results_cache:
            json_dir = os.path.dirname(config["json_path"])
            if json_dir:
                os.makedirs(json_dir, exist_ok=True)
            logger.info(f"Exporting JSON raw backup: {config['json_path']}")
            with open(config["json_path"], "w", encoding="utf-8") as f:
                json.dump(pipeline.raw_results_cache, f, indent=4, ensure_ascii=False)

        # Export CSV if configured
        if config.get("csv_path"):
            csv_dir = os.path.dirname(config["csv_path"])
            if csv_dir:
                os.makedirs(csv_dir, exist_ok=True)
            logger.info(f"Exporting CSV: {config['csv_path']}")
            conn = sqlite3.connect(config["db_path"])
            df = pd.read_sql_query("SELECT * FROM openalex_metadata ORDER BY harvested_at DESC", conn)
            conn.close()
            df.to_csv(config["csv_path"], index=False, encoding="utf-8")

        # Export Excel (default/specified path)
        export_to_format(config["db_path"], config["export_path"])

        # Generate summary report if configured
        if config.get("report_path"):
            query_str = "; ".join(config["keywords"])
            generate_markdown_report(config["db_path"], config["report_path"], query_str)

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
        description="Automated Python pipeline to harvest scholarly metadata from OpenAlex.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="openalex_metadata.db",
        help="Path to SQLite database file."
    )
    parser.add_argument(
        "--export",
        type=str,
        default="openalex_resultados.xlsx",
        help="Export target path (Excel, CSV, JSON)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit of records to harvest per keyword."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds."
    )
    parser.add_argument(
        "--email",
        type=str,
        default="",
        help="Contact email for OpenAlex Polite Pool."
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default="",
        help="OpenAlex API Key (optional)."
    )
    parser.add_argument(
        "--keywords",
        type=str,
        nargs="+",
        default=["planejamento urbano"],
        help="List of keywords/phrases to query."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a JSON configuration file."
    )

    args = parser.parse_args()

    # Determine configuration file path
    config_file = args.config
    use_config = False

    if config_file and os.path.exists(config_file):
        use_config = True
    elif not config_file and os.path.exists("openalex_config.json"):
        config_file = "openalex_config.json"
        use_config = True
    elif not config_file and os.path.exists("config_openalex.json"):
        # Detect nested notebook config if present in current directory
        config_file = "config_openalex.json"
        use_config = True

    if use_config:
        try:
            config = read_json_config(config_file)
            logger.info(f"Successfully loaded configuration from: {config_file}")
        except Exception as e:
            logger.error(f"Failed to read JSON configuration: {e}. Falling back to CLI args.")
            use_config = False

    if not use_config:
        # CLI fallback
        # Generate default template if none exists
        if not args.config and not os.path.exists("openalex_config.json"):
            try:
                create_default_config_template("openalex_config.json")
            except Exception as e:
                logger.warning(f"Could not create config template: {e}")

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

    if not config["keywords"] or not config["keywords"][0]:
        logger.error("No keywords or queries specified. Pipeline aborting.")
        return

    try:
        success = run_harvest(config)
        if success:
            logger.info("Pipeline executed successfully.")
        else:
            logger.error("Pipeline finished with errors.")
    except KeyboardInterrupt:
        logger.warning("\nPipeline execution interrupted by user.")
    except Exception as e:
        logger.critical(f"Pipeline crashed due to an unhandled exception: {e}", exc_info=True)


if __name__ == "__main__":
    main()
