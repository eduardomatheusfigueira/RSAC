#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deduplication and Consolidation Script
Reads collected records from all 5 databases (OpenAlex, SciELO, BDTD, Scopus, PubMed),
deduplicates by DOI and normalized title, and exports the unified list for screening.
"""

import os
import re
import sqlite3
import unicodedata
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Centralized path resolution
try:
    from config_app.utils.path_resolver import resolve_path, BASE_DIR
except ImportError:
    # Fallback: if running standalone without config_app in path
    import sys
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    if _script_dir not in sys.path:
        sys.path.insert(0, _script_dir)
    from pathlib import Path as _Path
    BASE_DIR = _Path(_script_dir)
    def resolve_path(p):
        _p = _Path(p)
        return _p if _p.is_absolute() else BASE_DIR / _p

def normalize_title(title: str) -> str:
    """
    Normalizes titles by converting to lowercase, removing punctuation,
    accents, and whitespace for robust comparison.
    """
    if not title or pd.isna(title):
        return ""
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", str(title))
    text = "".join([c for c in text if not unicodedata.combining(c)])
    # Convert to lowercase and strip special characters
    text = text.lower()
    text = re.sub(r"[^a-z0-9]", "", text)
    return text.strip()

def clean_doi(doi: str) -> str:
    """
    Cleans and normalizes DOI strings.
    """
    if not doi or pd.isna(doi):
        return ""
    doi_str = str(doi).strip().lower()
    if doi_str in ["não informado", "nao informado", "n/a", "none", "nan", ""]:
        return ""
    # Extract DOI from URL if present
    match = re.search(r"doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", doi_str, re.IGNORECASE)
    if match:
        return match.group(1)
    return doi_str

def load_from_sqlite(db_path: str, table_name: str, col_mapping: dict = None) -> pd.DataFrame:
    """
    Attempts to read data from SQLite database.
    """
    if not os.path.exists(db_path):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        conn.close()
        if col_mapping:
            df = df.rename(columns=col_mapping)
        logger.info(f"Loaded {len(df)} records from SQLite database: {db_path}")
        return df
    except Exception as e:
        logger.warning(f"Could not read SQLite table {table_name} from {db_path}: {e}")
        return pd.DataFrame()

def load_from_csv(csv_path: str, col_mapping: dict = None) -> pd.DataFrame:
    """
    Attempts to read data from a CSV file.
    """
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(csv_path)
        if col_mapping:
            df = df.rename(columns=col_mapping)
        logger.info(f"Loaded {len(df)} records from CSV: {csv_path}")
        return df
    except Exception as e:
        logger.warning(f"Could not read CSV {csv_path}: {e}")
        return pd.DataFrame()

def load_from_excel(xlsx_path: str, col_mapping: dict = None) -> pd.DataFrame:
    """
    Attempts to read data from an Excel file.
    """
    if not os.path.exists(xlsx_path):
        return pd.DataFrame()
    try:
        df = pd.read_excel(xlsx_path)
        if col_mapping:
            df = df.rename(columns=col_mapping)
        logger.info(f"Loaded {len(df)} records from Excel: {xlsx_path}")
        return df
    except Exception as e:
        logger.warning(f"Could not read Excel {xlsx_path}: {e}")
        return pd.DataFrame()

def main():
    logger.info("Starting consolidation and deduplication process...")
    
    # 1. Define paths and database schemas
    # For SQLite databases, look both in root and in subfolders
    sources_to_load = {
        "OpenAlex": {
            "db": [str(resolve_path("openalex_metadata.db")), str(resolve_path("openalex_harvester/openalex_metadata.db"))],
            "table": "openalex_metadata",
            "csv": [str(resolve_path("openalex_outputs/openalex_clean_data.csv"))],
            "xlsx": [str(resolve_path("openalex_outputs/OpenAlex_Data_Export.xlsx"))],
            "mapping": {"id": "id"}
        },
        "SciELO": {
            "db": [str(resolve_path("scielo_metadata.db")), str(resolve_path("scielo_harvester/scielo_metadata.db"))],
            "table": "scielo_metadata",
            "csv": [str(resolve_path("scielo_outputs/scielo_clean_data.csv"))],
            "xlsx": [str(resolve_path("scielo_outputs/SciELO_Data_Export.xlsx"))],
            "mapping": {"id": "id"}
        },
        "Scopus": {
            "db": [str(resolve_path("scopus_metadata.db")), str(resolve_path("scopus_harvester/scopus_metadata.db"))],
            "table": "scopus_metadata",
            "csv": [str(resolve_path("scopus_outputs/scopus_clean_data.csv"))],
            "xlsx": [str(resolve_path("scopus_resultados.xlsx")), str(resolve_path("scopus_outputs/Scopus_Data_Export.xlsx"))],
            "mapping": {"id": "id"}
        },
        "BDTD": {
            "db": [str(resolve_path("bdtd_metadata.db")), str(resolve_path("bdtd_harvester/bdtd_metadata.db"))],
            "table": "bdtd_metadata",
            "csv": [str(resolve_path("bdtd_outputs/bdtd_clean_data.csv"))],
            "xlsx": [str(resolve_path("bdtd_outputs/BDTD_Data_Export.xlsx"))],
            "mapping": {
                "record_id": "id",
                "creator": "authors",
                "date": "year",
                "description": "abstract",
                "source_institution": "journal",
                "download_url": "article_url"
            }
        },
        "PubMed": {
            "db": [str(resolve_path("pubmed_metadata.db")), str(resolve_path("pubmed_harvester/pubmed_metadata.db"))],
            "table": "pubmed_metadata",
            "csv": [str(resolve_path("pubmed_outputs/pubmed_clean_data.csv"))],
            "xlsx": [str(resolve_path("pubmed_resultados.xlsx")), str(resolve_path("pubmed_outputs/PubMed_Data_Export.xlsx"))],
            "mapping": {"id": "id"}
        }
    }
    
    # Target columns in Portuguese (as expected by Planilha Triagem)
    target_columns = [
        "authors", "title", "year", "type_of_research", 
        "advisor", "journal", "abstract", "doi", "article_url"
    ]
    
    portuguese_mapping = {
        "Autores": "authors",
        "Título": "title",
        "Ano": "year",
        "Tipo de Pesquisa": "type_of_research",
        "Nome do Orientador": "advisor",
        "Universidade / Editora / Revista": "journal",
        "Resumo": "abstract",
        "Link para Download": "article_url",
        "DOI": "doi"
    }

    all_records = []
    
    # Load from each source
    for source_name, config in sources_to_load.items():
        df_source = pd.DataFrame()
        
        # Strategy A: SQLite
        for db_file in config["db"]:
            if os.path.exists(db_file):
                df_source = load_from_sqlite(db_file, config["table"], config["mapping"])
                if not df_source.empty:
                    break
                    
        # Strategy B: CSV
        if df_source.empty:
            for csv_file in config["csv"]:
                if os.path.exists(csv_file):
                    df_source = load_from_csv(csv_file)
                    if not df_source.empty:
                        # Translate from Portuguese headers if needed
                        df_source = df_source.rename(columns=portuguese_mapping)
                        df_source = df_source.rename(columns=config["mapping"])
                        break
                        
        # Strategy C: Excel
        if df_source.empty:
            for xlsx_file in config["xlsx"]:
                if os.path.exists(xlsx_file):
                    df_source = load_from_excel(xlsx_file)
                    if not df_source.empty:
                        # Translate from Portuguese headers
                        df_source = df_source.rename(columns=portuguese_mapping)
                        df_source = df_source.rename(columns=config["mapping"])
                        break
                        
        if df_source.empty:
            logger.info(f"Source {source_name}: No data files found. Skipping.")
            continue
            
        # Ensure all target columns exist
        for col in target_columns:
            if col not in df_source.columns:
                df_source[col] = "Não Informado"
                
        # Clean fields
        df_source["source"] = source_name
        df_source = df_source[target_columns + ["source"]].copy()
        
        all_records.append(df_source)

    if not all_records:
        logger.error("No harvested data found to consolidate!")
        return

    # Unify all dataframes
    df_all = pd.concat(all_records, ignore_index=True)
    logger.info(f"Loaded a total of {len(df_all)} raw records from active sources.")
    
    # Fill NA values
    df_all = df_all.fillna("Não Informado")
    for col in df_all.columns:
        df_all[col] = df_all[col].astype(str).replace({"nan": "Não Informado", "None": "Não Informado", "": "Não Informado"})

    # Prepare fields for deduplication
    df_all["clean_doi"] = df_all["doi"].apply(clean_doi)
    df_all["clean_title"] = df_all["title"].apply(normalize_title)
    
    # Sort so that records with complete details (e.g. non-empty abstract) come first
    def get_quality_score(row):
        score = 0
        if row["abstract"] and row["abstract"].lower() not in ["não informado", "nao informado", "", "não disponível na busca padrão (requer view=complete)"]:
            score += 10
        if row["doi"] and row["doi"].lower() not in ["não informado", "nao informado", ""]:
            score += 5
        if row["authors"] and row["authors"].lower() not in ["não informado", "nao informado", ""]:
            score += 2
        return score

    df_all["quality_score"] = df_all.apply(get_quality_score, axis=1)
    df_all = df_all.sort_values(by="quality_score", ascending=False)

    # 2. Deduplication process
    unique_records = []
    removed_records = []
    
    seen_dois = set()
    seen_titles = set()
    
    for idx, row in df_all.iterrows():
        doi = row["clean_doi"]
        title = row["clean_title"]
        
        is_dup = False
        dup_reason = ""
        dup_match = None
        
        # Check by DOI
        if doi:
            for r in unique_records:
                if r["clean_doi"] == doi:
                    is_dup = True
                    dup_reason = f"Duplicate DOI: {doi}"
                    dup_match = r
                    break
                    
        # Check by Title
        if not is_dup and title:
            for r in unique_records:
                if r["clean_title"] == title:
                    is_dup = True
                    dup_reason = f"Duplicate Title"
                    dup_match = r
                    break
                    
        if is_dup:
            # Add current source to the existing record's sources
            if row["source"] not in dup_match["sources"].split("; "):
                dup_match["sources"] = f"{dup_match['sources']}; {row['source']}"
            
            row_dict = row.to_dict()
            row_dict["dup_reason"] = dup_reason
            removed_records.append(row_dict)
        else:
            row_dict = row.to_dict()
            row_dict["sources"] = row["source"]
            unique_records.append(row_dict)

    df_unique = pd.DataFrame(unique_records)
    df_removed = pd.DataFrame(removed_records)

    # Format outputs
    output_dir = str(resolve_path("consolidado"))
    os.makedirs(output_dir, exist_ok=True)
    
    if not df_unique.empty:
        # Re-sort by title or year for presentation
        df_unique = df_unique.sort_values(by=["year", "title"], ascending=[False, True])
        # Select target columns for Excel compatibility
        # Rename columns back to Portuguese for template compatibility
        df_export = df_unique.rename(columns={
            "authors": "authors",
            "title": "title",
            "year": "year",
            "type_of_research": "type_of_research",
            "advisor": "advisor",
            "journal": "periodico",
            "abstract": "abstract",
            "doi": "doi",
            "article_url": "url",
            "sources": "sources"
        })
        
        # Export to CSV
        df_export = df_export[["sources", "doi", "title", "authors", "year", "periodico", "abstract", "url"]]
        output_csv = os.path.join(output_dir, "registros_unificados.csv")
        df_export.to_csv(output_csv, index=False, encoding="utf-8")
        logger.info(f"Saved {len(df_export)} unique consolidated records to '{output_csv}'.")
    else:
        logger.warning("No unique records found after consolidation.")

    if not df_removed.empty:
        dup_csv = os.path.join(output_dir, "duplicatas_removidas.csv")
        df_removed.to_csv(dup_csv, index=False, encoding="utf-8")
        logger.info(f"Saved {len(df_removed)} removed duplicate records to '{dup_csv}'.")
    else:
        # Create empty file
        dup_csv = os.path.join(output_dir, "duplicatas_removidas.csv")
        pd.DataFrame(columns=["title", "doi", "source", "dup_reason"]).to_csv(dup_csv, index=False)

    logger.info("Consolidation and deduplication complete.")

if __name__ == "__main__":
    main()
