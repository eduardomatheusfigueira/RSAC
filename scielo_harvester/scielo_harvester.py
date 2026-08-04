#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SciELO Harvester - Automated Python pipeline to extract SciELO article metadata.

Scrapes the SciELO search interface (search.scielo.org) and saves structured
metadata to SQLite and exports to Excel/CSV/JSON with columns compatible
with the BDTD Harvester output.

Usage:
    CLI:  python scielo_harvester.py --keywords "planejamento urbano" --limit 50
    API:  from scielo_harvester import run_harvest
          run_harvest(keywords=["planejamento urbano"], limit=50)
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
from bs4 import BeautifulSoup

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================
SCIELO_SEARCH_URL = "https://search.scielo.org/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://search.scielo.org/",
}
PAGE_SIZE = 15  # SciELO always returns 15 items per page


# ============================================================
# JSON Configuration
# ============================================================
def create_json_config_template(file_path):
    """Creates a template JSON configuration file for the SciELO harvester."""
    logger.info(f"Creating a new JSON configuration template: {file_path}")
    template = {
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
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=4)
    logger.info(f"Successfully generated JSON config template at {file_path}")


def read_json_config_file(file_path):
    """Reads search settings and keywords from a JSON configuration file using Pydantic schema validation."""
    logger.info(f"Reading configuration from JSON: {file_path}")
    try:
        from config_app.core.config_schemas import ScieloConfig, load_and_validate_config
        validated = load_and_validate_config(file_path, ScieloConfig)
        data = validated.model_dump()
    except Exception as e:
        logger.warning(f"Validação de schema via Pydantic falhou ou indisponível ({e}). Usando fallback de leitura bruta.")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    config = {
        "db_path": data.get("db_path", "scielo_metadata.db"),
        "export_path": data.get("export_path", "scielo_resultados.xlsx"),
        "limit": data.get("limit"),
        "delay": float(data.get("delay", 3.0)),
        "search_field": data.get("search_field", ""),
        "keywords": data.get("keywords", []),
    }
    return config


# ============================================================
# Database Manager
# ============================================================
class DatabaseManager:
    """Manages all SQLite database operations."""

    SCHEMA = """
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

    def __init__(self, db_path):
        self.db_path = db_path
        open_db_path = db_path
        if sys.platform.startswith('win') and len(os.path.abspath(open_db_path)) >= 240 and not os.path.abspath(open_db_path).startswith('\\\\?\\'):
            open_db_path = '\\\\?\\' + os.path.abspath(open_db_path)
        self.conn = sqlite3.connect(open_db_path)
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as e:
            logger.warning(f"Could not enable WAL mode ({e}), falling back to default journal mode.")
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()
        logger.info(f"Database initialized successfully at: {db_path}")

    def insert_record(self, record: dict) -> bool:
        """Inserts a single record. Returns True if inserted, False if duplicate."""
        try:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO article_metadata
                    (id, title, authors, year, type_of_research,
                     journal, abstract, doi, article_url, keyword_query)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["title"],
                    record["authors"],
                    record["year"],
                    record.get("type_of_research", "Artigo"),
                    record["journal"],
                    record["abstract"],
                    record["doi"],
                    record["article_url"],
                    record["keyword_query"],
                ),
            )
            self.conn.commit()
            return self.conn.total_changes > 0
        except sqlite3.IntegrityError:
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed.")


# ============================================================
# HTML Parser — extracts metadata from a single SciELO item
# ============================================================
def parse_item(item_tag):
    """Parses a single <div class='item'> from SciELO search results."""
    record = {}

    # --- ID ---
    record["id"] = item_tag.get("id", "")

    # --- Title ---
    title_tag = item_tag.find(class_="title")
    record["title"] = title_tag.text.strip() if title_tag else ""
    # Remove SciELO Preprints prefix
    if record["title"].startswith("[SciELO Preprints] - "):
        record["title"] = record["title"].replace("[SciELO Preprints] - ", "")

    # --- Article URL ---
    if title_tag:
        parent_a = title_tag.parent
        if parent_a and parent_a.name == "a":
            record["article_url"] = parent_a.get("href", "")
        else:
            record["article_url"] = ""
    else:
        record["article_url"] = ""

    # --- Authors ---
    authors_div = item_tag.find(class_="authors")
    if authors_div:
        author_links = authors_div.find_all("a")
        record["authors"] = "; ".join(
            a.text.strip() for a in author_links if a.text.strip()
        )
    else:
        record["authors"] = ""

    # --- Journal (source) ---
    source_div = item_tag.find(class_="source")
    if source_div:
        source_link = source_div.find("a")
        record["journal"] = source_link.text.strip() if source_link else ""
    else:
        record["journal"] = ""

    # --- Year ---
    # Strategy 1: Extract from item ID (e.g. S2215-25632026000100163-cri → 2026)
    year = ""
    m = re.search(r"S\d{4}-\d{3,4}(\d{4})", record["id"])
    if m:
        year = m.group(1)
    # Strategy 2: Look for year pattern in source div strings
    if not year and source_div:
        for s in source_div.stripped_strings:
            m2 = re.search(r"((?:19|20)\d{2})", s)
            if m2:
                year = m2.group(1)
                break
    record["year"] = year

    # --- Type ---
    if "preprint" in record["id"].lower():
        record["type_of_research"] = "Preprint"
    else:
        record["type_of_research"] = "Artigo"

    # --- Abstract (prefer Portuguese) ---
    abstract_divs = item_tag.find_all(class_="abstract")
    abstract = ""
    for ab in abstract_divs:
        text = ab.text.strip()
        if text.lower().startswith("resumo"):
            abstract = text
            break
    # Fallback: use first abstract in any language
    if not abstract and abstract_divs:
        abstract = abstract_divs[0].text.strip()
    record["abstract"] = abstract

    # --- DOI ---
    doi_span = item_tag.find(class_="DOIResults")
    record["doi"] = doi_span.text.strip() if doi_span else ""

    return record


# ============================================================
# SciELO Search Scraper Pipeline
# ============================================================
class SciELOHarvesterPipeline:
    """Paginates through SciELO search results and stores metadata."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        keywords: list,
        limit_per_keyword: int = None,
        delay: float = 3.0,
        search_field: str = "",
    ):
        self.db = db_manager
        self.keywords = keywords
        self.limit = limit_per_keyword
        self.delay = delay
        self.search_field = search_field

        # Persistent session for cookies
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        self.total_processed = 0
        self.total_inserted = 0

    def _warm_session(self):
        """Visit the SciELO home page to acquire cookies before querying."""
        try:
            self.session.get(SCIELO_SEARCH_URL, timeout=15)
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Could not warm session: {e}")

    def _fetch_page(self, keyword: str, offset: int) -> BeautifulSoup | None:
        """Fetches a single search results page."""
        params = {
            "q": keyword,
            "lang": "pt",
            "count": str(PAGE_SIZE),
            "from": str(offset),
            "output": "site",
        }
        if self.search_field:
            params["where"] = self.search_field

        try:
            res = self.session.get(
                SCIELO_SEARCH_URL, params=params, timeout=20
            )
            if res.status_code == 200:
                return BeautifulSoup(res.text, "html.parser")
            elif res.status_code == 403:
                logger.warning(
                    "Received 403 Forbidden. Waiting 10 seconds before retry..."
                )
                time.sleep(10)
                res = self.session.get(
                    SCIELO_SEARCH_URL, params=params, timeout=20
                )
                if res.status_code == 200:
                    return BeautifulSoup(res.text, "html.parser")
            logger.error(f"HTTP {res.status_code} for keyword '{keyword}'")
            return None
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None

    def _extract_total(self, soup: BeautifulSoup) -> int:
        """Tries to extract the total number of matching results from the page."""
        try:
            total_hits_tag = soup.find(id="TotalHits")
            if total_hits_tag:
                return int(total_hits_tag.text.strip().replace(".", ""))
        except Exception as e:
            logger.warning(f"Failed to parse TotalHits tag: {e}")

        page_text = soup.get_text()
        # Pattern: "X - Y de Z resultados" or "X to Y of Z"
        m = re.search(r"de\s+(\d[\d.]*)\s", page_text)
        if m:
            return int(m.group(1).replace(".", ""))
        return 0

    def _process_keyword(self, keyword: str):
        """Harvests all pages for a single keyword."""
        logger.info(f"Processing keyword: '{keyword}'")
        offset = 1
        saved_for_keyword = 0
        processed_for_keyword = 0
        total_results = None

        while True:
            page_num = (offset - 1) // PAGE_SIZE + 1
            logger.info(f"Querying SciELO for '{keyword}' - Page {page_num}...")

            soup = self._fetch_page(keyword, offset)
            if soup is None:
                logger.warning("Failed to fetch page. Stopping this keyword.")
                break

            items = soup.find_all(class_="item")
            if not items:
                logger.info("No more items found. Finished this keyword.")
                break

            if total_results is None:
                total_results = self._extract_total(soup)
                if total_results:
                    logger.info(
                        f"Total matching results on SciELO: {total_results}"
                    )

            for item in items:
                record = parse_item(item)
                record["keyword_query"] = keyword
                processed_for_keyword += 1
                self.total_processed += 1

                if not record["title"]:
                    continue

                inserted = self.db.insert_record(record)
                if inserted:
                    saved_for_keyword += 1
                    self.total_inserted += 1
                    logger.info(
                        f" -> [SAVED] {record['id'][:50]} | "
                        f"{record['authors'][:40]} | "
                        f"{record['journal'][:40]}"
                    )

                if self.limit and saved_for_keyword >= self.limit:
                    logger.info(
                        f"Limit of {self.limit} records reached for "
                        f"keyword '{keyword}'."
                    )
                    break

            if self.limit and saved_for_keyword >= self.limit:
                break

            # Check if there are more pages
            if total_results and offset + PAGE_SIZE > total_results:
                break
            if len(items) < PAGE_SIZE:
                break

            offset += PAGE_SIZE
            time.sleep(self.delay)

        logger.info(
            f"Finished '{keyword}': processed {processed_for_keyword} "
            f"records, saved {saved_for_keyword} relevant records."
        )

    def run(self):
        """Executes the full harvesting pipeline for all keywords."""
        logger.info(
            f"Starting SciELO metadata harvest for keywords: {self.keywords}"
        )
        start = time.time()
        self._warm_session()

        for keyword in self.keywords:
            self._process_keyword(keyword)
            time.sleep(self.delay)

        elapsed = time.time() - start
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")
        logger.info(
            f"Total processed: {self.total_processed} | "
            f"Total saved to DB: {self.total_inserted}"
        )


# ============================================================
# Export — compatible with BDTD harvester output columns
# ============================================================
def export_to_format(db_path: str, export_path: str) -> bool:
    """
    Exports article_metadata table to Excel, CSV, or JSON.
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
                'N/A (artigo)' AS "Nome do Orientador",
                journal   AS "Universidade / Editora / Revista",
                abstract  AS "Resumo",
                article_url AS "Link para Download"
            FROM article_metadata
            ORDER BY harvested_at DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            logger.warning("No records found in the database to export.")
            return False

        ext = os.path.splitext(export_path)[1].lower()
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


# ============================================================
# High-Level Python API
# ============================================================
def run_harvest(
    keywords: list,
    db_path: str = "scielo_metadata.db",
    export_path: str = "scielo_resultados.xlsx",
    limit: int = None,
    delay: float = 3.0,
    search_field: str = "",
) -> bool:
    """
    High-level entrypoint to execute the SciELO harvesting pipeline
    programmatically.

    Args:
        keywords: List of search terms.
        db_path: Path to the SQLite database file.
        export_path: Path to the output file (.xlsx, .csv, or .json).
        limit: Maximum number of records per keyword (None = all).
        delay: Polite delay in seconds between requests.
        search_field: SciELO search field filter (empty = all fields).

    Returns:
        True if successful, False otherwise.
    """
    db_manager = None
    try:
        log_dir = os.path.dirname(export_path) if os.path.dirname(export_path) else "."
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "log_scielo.txt")
        open_path = log_file_path
        if sys.platform.startswith('win') and len(os.path.abspath(open_path)) >= 250 and not os.path.abspath(open_path).startswith('\\\\?\\'):
            open_path = '\\\\?\\' + os.path.abspath(open_path)
        file_handler = logging.FileHandler(open_path, mode='w', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(file_handler)
        logger.info(f"Log de execução sendo gravado em: {log_file_path}")
    except Exception as e:
        logger.warning(f"Não foi possível iniciar o arquivo de log para gravação: {e}")

    try:
        db_manager = DatabaseManager(db_path)
        pipeline = SciELOHarvesterPipeline(
            db_manager=db_manager,
            keywords=keywords,
            limit_per_keyword=limit,
            delay=delay,
            search_field=search_field,
        )
        pipeline.run()
        db_manager.close()
        db_manager = None
        export_to_format(db_path, export_path)
        return True
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return False
    finally:
        if db_manager:
            db_manager.close()


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description=(
            "Automated Python pipeline to extract SciELO article metadata "
            "and save to SQLite / Excel / CSV / JSON."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="scielo_metadata.db",
        help="Filename or path of the destination SQLite database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum records to retrieve PER keyword. "
            "If omitted, collects all matching records."
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Polite wait time (seconds) between page requests.",
    )
    parser.add_argument(
        "--keywords",
        type=str,
        nargs="+",
        default=["planejamento urbano"],
        help="List of keywords/phrases to search for.",
    )
    parser.add_argument(
        "--export",
        type=str,
        default="scielo_resultados.xlsx",
        help=(
            "Output file path (supports .xlsx, .csv, .json). "
            "Columns are compatible with BDTD harvester output."
        ),
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help=(
            "Path to a JSON configuration file. "
            "If omitted, checks for scielo_config.json."
        ),
    )
    parser.add_argument(
        "--search-field",
        type=str,
        default="",
        help="SciELO search field (empty = all fields).",
    )

    args = parser.parse_args()

    # --- Config file resolution ---
    config_file = args.config
    use_config = False

    if config_file and os.path.exists(config_file):
        use_config = True
    elif not config_file and os.path.exists("scielo_config.json"):
        config_file = "scielo_config.json"
        use_config = True

    if use_config:
        try:
            config = read_json_config_file(config_file)
            db_path = config["db_path"]
            export_path = config["export_path"]
            limit = config["limit"]
            delay = config["delay"]
            keywords = config["keywords"]
            search_field = config.get("search_field", "")
            logger.info(
                f"Loaded config from {config_file}: "
                f"DB={db_path}, Export={export_path}, "
                f"Limit={limit}, Delay={delay}, Keywords={keywords}"
            )
        except Exception as e:
            logger.error(
                f"Failed to read config: {e}. Falling back to CLI args."
            )
            db_path = args.db_path
            export_path = args.export
            limit = args.limit
            delay = args.delay
            keywords = args.keywords
            search_field = args.search_field
    else:
        # Generate default template if none exists
        if not config_file and not os.path.exists("scielo_config.json"):
            try:
                create_json_config_template("scielo_config.json")
            except Exception as e:
                logger.warning(f"Could not create config template: {e}")

        db_path = args.db_path
        export_path = args.export
        limit = args.limit
        delay = args.delay
        keywords = args.keywords
        search_field = args.search_field

    if not keywords:
        logger.error(
            "No keywords specified. "
            "Please define keywords via CLI or config file."
        )
        return

    try:
        success = run_harvest(
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
    except KeyboardInterrupt:
        logger.warning("\nPipeline interrupted by user.")
    except Exception as e:
        logger.critical(
            f"Pipeline crashed due to an unhandled exception: {e}",
            exc_info=True,
        )


if __name__ == "__main__":
    main()
