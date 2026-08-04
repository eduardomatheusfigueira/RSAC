#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PubMed Harvester - Automated Python pipeline to extract PubMed (MEDLINE) article metadata.
Retrieves metadata from NCBI E-utilities (esearch & efetch XML), saves to SQLite,
and exports to Excel/CSV/JSON in a format compatible with BDTD, SciELO, and OpenAlex.
"""

import argparse
import json
import logging
import os
import sys
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
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
def translate_publication_type(pub_types: list) -> str:
    """
    Translates publication types from PubMed to Portuguese descriptors.
    """
    if not pub_types:
        return "Artigo"
        
    # Standard mapping
    mapping = {
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
    
    # Check each type in order of specificity
    for pt in pub_types:
        pt_lower = pt.lower()
        if pt_lower in mapping:
            return mapping[pt_lower]
            
    # Default fallback
    return "Artigo"

# ============================================================
# Database Manager
# ============================================================
class DatabaseManager:
    """
    Manages SQLite database creation and record insertions.
    Schema matches BDTD, SciELO, OpenAlex, and Scopus.
    """
    SCHEMA = """
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
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pubmed_year ON pubmed_metadata (year);")
        self.conn.commit()
        logger.info(f"Database initialized successfully at: {db_path}")

    def insert_record(self, record: dict) -> bool:
        """
        Inserts a single academic record. Returns True if inserted, False if duplicate/error.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO pubmed_metadata
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
            cursor.execute("SELECT 1 FROM pubmed_metadata WHERE id = ?", (record_id,))
            return cursor.fetchone() is not None
        except sqlite3.Error:
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed.")

# ============================================================
# PubMed Harvester Pipeline
# ============================================================
class PubMedHarvesterPipeline:
    """
    Queries NCBI E-utilities API to harvest literature,
    saves results to SQLite database, and handles pagination.
    """
    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def __init__(self, db_manager: DatabaseManager, config: dict):
        self.db = db_manager
        self.keywords = config.get("keywords", [])
        self.limit = config.get("limit")
        self.delay = float(config.get("delay", 0.35))
        self.api_key = config.get("api_key", "").strip()
        
        self.total_processed = 0
        self.total_inserted = 0

    def query_esearch(self, keyword: str) -> list:
        """
        Queries NCBI esearch to retrieve list of PMIDs matching the search term.
        """
        logger.info(f"Querying esearch for keyword: '{keyword}'...")
        params = {
            "db": "pubmed",
            "term": keyword,
            "retmode": "json",
            "retmax": 10000  # Max limit for a single search
        }
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            response = requests.get(self.ESEARCH_URL, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                id_list = data.get("esearchresult", {}).get("idlist", [])
                logger.info(f"Found {len(id_list)} matching PMIDs in PubMed.")
                return id_list
            else:
                logger.error(f"esearch returned HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Error querying esearch: {e}")
            
        return []

    def fetch_records_batch(self, pmid_list: list) -> str:
        """
        Fetches full XML details for a batch of PMIDs using efetch.
        """
        pmid_str = ",".join(pmid_list)
        params = {
            "db": "pubmed",
            "id": pmid_str,
            "retmode": "xml"
        }
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            response = requests.get(self.EFETCH_URL, params=params, timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                logger.error(f"efetch returned HTTP {response.status_code} for batch.")
        except Exception as e:
            logger.error(f"Error querying efetch for batch: {e}")
            
        return ""

    def parse_xml_to_records(self, xml_data: str, keyword: str) -> list:
        """
        Parses XML string returned by efetch into list of dictionaries.
        """
        records = []
        if not xml_data:
            return records

        try:
            root = ET.fromstring(xml_data)
            for article_node in root.findall(".//PubmedArticle"):
                # 1. PMID
                pmid_el = article_node.find(".//MedlineCitation/PMID")
                pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None
                if not pmid:
                    continue

                # 2. Title
                title_el = article_node.find(".//ArticleTitle")
                title = "".join(title_el.itertext()).strip() if title_el is not None else "Não Informado"
                if title.endswith("."):
                    title = title[:-1]

                # 3. Authors
                author_names = []
                author_list_el = article_node.find(".//AuthorList")
                if author_list_el is not None:
                    for author in author_list_el.findall("Author"):
                        last = author.find("LastName")
                        fore = author.find("ForeName")
                        last_name = last.text.strip() if last is not None and last.text else ""
                        fore_name = fore.text.strip() if fore is not None and fore.text else ""
                        if last_name and fore_name:
                            author_names.append(f"{last_name}, {fore_name}")
                        elif last_name:
                            author_names.append(last_name)
                        elif fore_name:
                            author_names.append(fore_name)
                authors = "; ".join(author_names) if author_names else "Não Informado"

                # 4. Publication Year
                year = "Não Informado"
                pub_date_el = article_node.find(".//JournalIssue/PubDate")
                if pub_date_el is not None:
                    year_el = pub_date_el.find("Year")
                    if year_el is not None and year_el.text:
                        year = year_el.text.strip()
                    else:
                        medline_date_el = pub_date_el.find("MedlineDate")
                        if medline_date_el is not None and medline_date_el.text:
                            # Try to extract 4 digit year
                            match = re.search(r"\b(19|20)\d{2}\b", medline_date_el.text)
                            if match:
                                year = match.group(0)

                # 5. Journal
                journal_el = article_node.find(".//Journal/Title")
                journal = journal_el.text.strip() if journal_el is not None and journal_el.text else "Não Informado"

                # 6. Abstract
                abstract_parts = []
                abstract_el = article_node.find(".//Abstract")
                if abstract_el is not None:
                    for text_el in abstract_el.findall("AbstractText"):
                        label = text_el.get("Label")
                        text_content = "".join(text_el.itertext()).strip()
                        if text_content:
                            if label:
                                abstract_parts.append(f"{label}: {text_content}")
                            else:
                                abstract_parts.append(text_content)
                abstract = " ".join(abstract_parts).strip() if abstract_parts else "Não Informado"

                # 7. DOI
                doi = "Não Informado"
                for article_id in article_node.findall(".//ArticleIdList/ArticleId"):
                    if article_id.get("IdType") == "doi" and article_id.text:
                        doi = article_id.text.strip()
                        break

                # 8. Publication Types
                pub_types = []
                pub_type_list_el = article_node.find(".//PublicationTypeList")
                if pub_type_list_el is not None:
                    for pt in pub_type_list_el.findall("PublicationType"):
                        if pt.text:
                            pub_types.append(pt.text.strip())
                type_of_research = translate_publication_type(pub_types)

                # 9. URL
                article_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

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
        except Exception as e:
            logger.error(f"Error parsing XML for batch: {e}")

        return records

    def process_keyword(self, keyword: str):
        """
        Runs the full harvesting process for a single keyword.
        """
        logger.info(f"Target query: '{keyword}'")
        pmids = self.query_esearch(keyword)
        if not pmids:
            logger.info("No records matched.")
            return

        # Skip PMIDs that already exist in the database
        new_pmids = [pmid for pmid in pmids if not self.db.record_exists(pmid)]
        logger.info(f"Total PMIDs: {len(pmids)} | Uncollected new PMIDs: {len(new_pmids)}")

        if not new_pmids:
            logger.info("All matching records have already been harvested. Skipping query execution.")
            return

        # Fetch in batches of 100
        batch_size = 100
        saved_for_keyword = 0
        
        for i in range(0, len(new_pmids), batch_size):
            batch = new_pmids[i : i + batch_size]
            logger.info(f"Fetching batch {i // batch_size + 1} ({len(batch)} items)...")
            
            xml_data = self.fetch_records_batch(batch)
            records = self.parse_xml_to_records(xml_data, keyword)
            
            for record in records:
                if self.limit and saved_for_keyword >= self.limit:
                    break
                self.total_processed += 1
                inserted = self.db.insert_record(record)
                if inserted:
                    saved_for_keyword += 1
                    self.total_inserted += 1
                    logger.info(f" -> [SAVED] PMID: {record['id']} | Title: {record['title'][:40]}... | Journal: {record['journal'][:30]}")

            # Honor delay between API queries
            time.sleep(self.delay)

            # Check if keyword limit reached
            if self.limit and saved_for_keyword >= self.limit:
                logger.info(f"Keyword limit of {self.limit} records reached. Stopping.")
                break

    def run(self):
        """
        Starts the pipeline over all keywords in config.
        """
        logger.info("=== PUBMED SYSTEM DATA HARVESTER STARTED ===")
        start_time = time.time()

        for kw in self.keywords:
            self.process_keyword(kw)

        elapsed = time.time() - start_time
        logger.info("=== PUBMED SYSTEM DATA HARVESTER PROCESS COMPLETED ===")
        logger.info(f"Total processed: {self.total_processed} | Total saved to DB: {self.total_inserted}")
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")

# ============================================================
# Export Functions
# ============================================================
def export_to_format(db_path: str, export_path: str) -> bool:
    """
    Exports pubmed_metadata table to Excel, CSV, or JSON.
    Column names match BDTD, SciELO, OpenAlex, and Scopus for seamless consolidation.
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
            FROM pubmed_metadata
            ORDER BY harvested_at DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            logger.warning("No records found in the database to export.")
            return False

        ext = os.path.splitext(export_path)[1].lower()
        export_dir = os.path.dirname(export_path)
        if export_dir:
            os.makedirs(export_dir, exist_ok=True)
            
        if ext in [".xlsx", ".xls"]:
            df.to_excel(export_path, index=False)
        elif ext == ".csv":
            df.to_csv(export_path, index=False, encoding="utf-8")
        elif ext == ".json":
            df.to_json(export_path, orient="records", force_ascii=False, indent=4)
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
    High-level entrypoint to execute the PubMed harvesting pipeline.
    """
    db_manager = None
    try:
        db_manager = DatabaseManager(config["db_path"])
        pipeline = PubMedHarvesterPipeline(db_manager, config)
        pipeline.run()

        # Export (default to specified path)
        export_to_format(config["db_path"], config["export_path"])

        db_manager.close()
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
        description="Automated Python pipeline to harvest scholarly metadata from PubMed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON configuration file (e.g. pubmed_config.json)."
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
        help="NCBI E-utilities API Key."
    )

    args = parser.parse_args()

    # Load configuration
    config = {}
    config_file = args.config

    if not config_file and os.path.exists("pubmed_config.json"):
        config_file = "pubmed_config.json"

    if config_file and os.path.exists(config_file):
        try:
            from config_app.core.config_schemas import PubMedConfig, load_and_validate_config
            validated = load_and_validate_config(config_file, PubMedConfig)
            config = validated.model_dump()
        except Exception as e:
            logger.warning(f"Validação de schema via Pydantic falhou ou indisponível ({e}). Usando fallback de leitura bruta.")
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
    else:
        # Defaults
        config = {
            "keywords": ["\"planejamento urbano\""],
            "db_path": "pubmed_metadata.db",
            "export_path": "pubmed_resultados.xlsx",
            "limit": None,
            "delay": 0.35,
            "api_key": ""
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

    run_harvest(config)

if __name__ == "__main__":
    main()
