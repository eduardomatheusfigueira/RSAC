#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDTD Metadata Harvester & Scraper Pipeline
Author: Scientific Data Engineer / Python Specialist
Description: Automated data pipeline that queries the BDTD using bdtd-scraper,
             scrapes detailed webpage metadata (like advisors and universities),
             persists the clean data in SQLite, and exports it to Excel.
"""

import os
import sys
import time
import sqlite3
import logging
import argparse
import unicodedata
import urllib.request
import re
import pandas as pd
from bs4 import BeautifulSoup
import bdtd_scraper.api

# Configure logging to display informative and clean logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# BDTD API CONSTRAINT: The BDTD VuFind server uses a Web Application Firewall
# (WAF) that blocks HTTP requests containing 3 or more filter[] query parameters
# with an HTTP 429 (Too Many Requests) response. This is a server-side rule that
# cannot be changed by clients.
#
# To work around this, we enforce a maximum of 2 API-level filters per request.
# Language filters (e.g. ~language:por) are separated and applied locally on
# the returned records as post-processing, keeping the API filter count low.
# ──────────────────────────────────────────────────────────────────────────────
BDTD_MAX_API_FILTERS = 2


def sanitize_bdtd_filters(raw_filters):
    """
    Separates a list of BDTD Solr filter strings into:
      - api_filters:  filters safe to send as filter[] params (max BDTD_MAX_API_FILTERS)
      - allowed_langs: set of language codes to apply locally as post-filtering

    Any non-language filters beyond BDTD_MAX_API_FILTERS are dropped with a warning.

    Returns:
        tuple(list[str], set[str]): (api_filters, allowed_languages)
    """
    api_filters = []
    allowed_languages = set()

    for f in (raw_filters or []):
        # Match both "language:xxx" and "~language:xxx"
        stripped = f.lstrip('~')
        if stripped.startswith('language:'):
            lang_code = stripped.split(':', 1)[1].strip()
            if lang_code:
                allowed_languages.add(lang_code)
        else:
            api_filters.append(f)

    # Enforce the WAF limit
    if len(api_filters) > BDTD_MAX_API_FILTERS:
        dropped = api_filters[BDTD_MAX_API_FILTERS:]
        api_filters = api_filters[:BDTD_MAX_API_FILTERS]
        logger.warning(
            f"BDTD WAF limit: Too many API filters ({len(api_filters) + len(dropped)}). "
            f"Keeping first {BDTD_MAX_API_FILTERS}: {api_filters}. "
            f"Dropped: {dropped}"
        )

    return api_filters, allowed_languages


def clean_creator_name(creator_str):
    """
    Cleans up author/creator names by stripping trailing birth/death years
    (e.g., "Silva, Pedro, 1976-" -> "Silva, Pedro").
    """
    if not creator_str:
        return ""
    parts = re.split(r'[;\n]+', creator_str)
    cleaned_parts = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Clean up trailing birth/death years or trailing hyphens
        part = re.sub(r',\s*\d{4}-\d*$', '', part)
        part = re.sub(r',\s*\d{4}-$', '', part)
        part = re.sub(r'\s*\d{4}-\d*$', '', part)
        part = re.sub(r'\s*\d{4}-$', '', part)
        part = part.strip(',;.- ')
        if part:
            cleaned_parts.append(part)
    return "; ".join(cleaned_parts)


def clean_advisor_name(advisor_str):
    """
    Cleans advisor names by removing Lattes CV links, ORCID URLs,
    institutional departments, and birth/death years.
    """
    if not advisor_str or advisor_str.lower() == "não informado":
        return "Não Informado"
    
    # Split by semicolon or newline
    parts = re.split(r'[;\n]+', advisor_str)
    cleaned_parts = []
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        # 1. Filter out URLs (Lattes, ORCID, etc.)
        if part.startswith('http://') or part.startswith('https://') or 'lattes.cnpq.br' in part or 'orcid.org' in part:
            continue
            
        # 2. Filter out institutional information
        lower_part = part.lower()
        is_institution = any(word in lower_part for word in [
            'universidade', 'faculdade', 'instituto', 'programa de', 'departamento',
            'campus', 'reitor', 'pró-reitoria', 'coordenador', 'membro da banca'
        ])
        if is_institution:
            continue
            
        # 3. Clean up trailing birth/death years (e.g., "Torezzan, Cristiano, 1976-")
        part = re.sub(r',\s*\d{4}-\d*$', '', part)
        part = re.sub(r',\s*\d{4}-$', '', part)
        part = re.sub(r'\s*\d{4}-\d*$', '', part)
        part = re.sub(r'\s*\d{4}-$', '', part)
        
        # Strip trailing hyphens or punctuation
        part = part.strip(',;.- ')
        if part:
            cleaned_parts.append(part)
            
    if not cleaned_parts:
        return "Não Informado"
        
    return "; ".join(cleaned_parts)


def process_record_fields(title, creator, description, advisor, source_institution):
    """
    Cleans up description and advisor fields to prevent misfiled data.
    If the description is actually an advisor name, it clears the description
    and uses the name to populate the advisor field if needed.
    """
    # 1. Clean the advisor name first
    cleaned_advisor = clean_advisor_name(advisor)
    
    # 2. Check if description is actually a misfiled advisor name
    desc_clean = description.strip()
    is_misfiled_advisor = False
    extracted_advisor = None
    
    # Matches "Orientador: Name" or "Orientador(a): Name" or "Orientadores: Name"
    match = re.match(r'^(?:orientador|orientadora|orientadores|orientador\(a\))\s*:\s*(.+)$', desc_clean, re.IGNORECASE)
    if match:
        is_misfiled_advisor = True
        extracted_advisor = match.group(1).strip()
    elif desc_clean.lower().startswith('orientador'):
        # If it's a short text starting with Orientador
        if len(desc_clean) < 150:
            is_misfiled_advisor = True
            extracted_advisor = desc_clean
            
    if is_misfiled_advisor:
        # Clear description
        desc_clean = ""
        # If the advisor was not informed or is a generic fallback, use the extracted advisor name
        if extracted_advisor and (cleaned_advisor == "Não Informado" or len(cleaned_advisor) < len(extracted_advisor)):
            cleaned_advisor = clean_advisor_name(extracted_advisor)
            
    # Normalize empty values
    if not desc_clean:
        desc_clean = "Não Informado"
        
    return desc_clean, cleaned_advisor


def normalize_text(text):
    """
    Normalizes Portuguese characters (removes accents, converts to lowercase)
    for robust keyword matching and comparison.
    """
    if not text:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()


def create_config_template(file_path):
    """
    Creates a pre-formatted Excel configuration file template with openpyxl.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    
    logger.info(f"Creating a new configuration template: {file_path}")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Configuração"
    
    # Enable gridlines
    ws.views.sheetView[0].showGridLines = True
    
    # Styles
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    label_font = Font(name="Calibri", size=11, bold=True)
    regular_font = Font(name="Calibri", size=11)
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    # Section 1 Headers
    ws['A1'] = "Configurações Gerais"
    ws['B1'] = "Valor"
    ws['A1'].fill = header_fill
    ws['A1'].font = header_font
    ws['B1'].fill = header_fill
    ws['B1'].font = header_font
    
    # Parameters
    params = [
        ("Banco de Dados (SQLite)", "bdtd_metadata.db"),
        ("Excel de Saída", "resultados_coleta.xlsx"),
        ("Limite por Termo (Deixe vazio para coletar todos)", ""),
        ("Atraso entre requisições (segundos)", "2.0"),
        ("Tipo de Busca (Campo de Busca: AllFields, Title, Author, Subject, Advisor)", "AllFields"),
        ("Ordenação (year, year asc, relevance, title, author)", "year"),
        ("Filtro: Tipo de Documento (doctoralThesis, masterThesis, article)", ""),
        ("Filtro: Instituição (Sigla, ex: USP, UNICAMP)", ""),
        ("Filtro: Ano de Publicação (ex: 2025 ou [2020 TO 2026])", ""),
        ("Filtro: Idioma (ex: por, eng, spa)", "")
    ]
    
    for i, (param, val) in enumerate(params, start=2):
        ws[f'A{i}'] = param
        ws[f'B{i}'] = val
        ws[f'A{i}'].font = label_font
        ws[f'B{i}'].font = regular_font
        ws[f'A{i}'].border = thin_border
        ws[f'B{i}'].border = thin_border
        
    # Section 2 Headers (Keywords)
    ws['D1'] = "Termos de Busca"
    ws['D1'].fill = header_fill
    ws['D1'].font = header_font
    
    keywords = [
        '("Inferencia causal" OR "descoberta causal")',
        'desenvolvimento regional',
        'planejamento urbano'
    ]
    
    for i, kw in enumerate(keywords, start=2):
        ws[f'D{i}'] = kw
        ws[f'D{i}'].font = regular_font
        ws[f'D{i}'].border = thin_border
        
    # Auto-fit columns
    ws.column_dimensions['A'].width = 55
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 5
    ws.column_dimensions['D'].width = 50
    
    wb.save(file_path)
    logger.info(f"Successfully generated config template at {file_path}")


def read_config_file(file_path):
    """
    Reads search settings and keywords from the Excel configuration file.
    """
    import openpyxl
    logger.info(f"Reading configuration from Excel: {file_path}")
    
    wb = openpyxl.load_workbook(file_path)
    if "Configuração" not in wb.sheetnames:
        raise ValueError(f"Sheet 'Configuração' not found in {file_path}")
        
    ws = wb["Configuração"]
    
    config = {
        'db_path': 'bdtd_metadata.db',
        'export_excel': 'resultados_coleta.xlsx',
        'limit': None,
        'delay': 2.0,
        'search_type': 'AllFields',
        'sort_order': 'year',
        'filters': [],
        'keywords': []
    }
    
    # Read parameters from Column A/B
    for r in range(2, 20):
        param = ws[f'A{r}'].value
        val = ws[f'B{r}'].value
        if not param:
            continue
            
        param_str = str(param).strip().lower()
        if "banco" in param_str:
            if val: config['db_path'] = str(val).strip()
        elif "excel" in param_str:
            if val: config['export_excel'] = str(val).strip()
        elif "limite" in param_str:
            if val is not None and str(val).strip():
                try:
                    config['limit'] = int(val)
                except ValueError:
                    logger.warning(f"Invalid limit value: {val}. Defaulting to no limit.")
        elif "atraso" in param_str:
            if val is not None and str(val).strip():
                try:
                    config['delay'] = float(val)
                except ValueError:
                    logger.warning(f"Invalid delay value: {val}. Defaulting to 2.0s.")
        elif "tipo de busca" in param_str:
            if val: config['search_type'] = str(val).strip()
        elif "ordenação" in param_str or "ordenacao" in param_str:
            if val: config['sort_order'] = str(val).strip()
        elif "filtro: tipo de documento" in param_str:
            if val:
                fmt = str(val).strip()
                config['filters'].append(f"format:{fmt}")
        elif "filtro: instituição" in param_str or "filtro: instituicao" in param_str:
            if val:
                inst = str(val).strip()
                config['filters'].append(f"institution:{inst}")
        elif "filtro: ano de publicação" in param_str or "filtro: ano de publicacao" in param_str:
            if val:
                yr = str(val).strip()
                config['filters'].append(f"publishDate:{yr}")
        elif "filtro: idioma" in param_str:
            if val:
                lang = str(val).strip()
                if ',' in lang:
                    langs = [l.strip() for l in lang.split(',')]
                    for l in langs:
                        config['filters'].append(f"~language:{l}")
                else:
                    config['filters'].append(f"language:{lang}")
                    
    # Read keywords from Column D
    r = 2
    while True:
        val = ws[f'D{r}'].value
        if val is None:
            break
        val_str = str(val).strip()
        if val_str:
            config['keywords'].append(val_str)
        r += 1
        
    return config


def create_json_config_template(file_path):
    """
    Creates a template JSON configuration file.
    """
    import json
    logger.info(f"Creating a new JSON configuration template: {file_path}")
    
    template = {
        "db_path": "bdtd_metadata.db",
        "export_path": "resultados_coleta.xlsx",
        "limit": None,
        "delay": 2.0,
        "search_type": "AllFields",
        "sort_order": "year",
        "filters": {
            "format": "",
            "institution": "",
            "publishDate": "",
            "language": ""
        },
        "keywords": [
            '("Inferencia causal" OR "descoberta causal")',
            "desenvolvimento regional",
            "planejamento urbano"
        ]
    }
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, ensure_ascii=False, indent=4)
    logger.info(f"Successfully generated JSON config template at {file_path}")


def read_json_config_file(file_path):
    """
    Reads search settings and keywords from the JSON configuration file.
    """
    import json
    logger.info(f"Reading configuration from JSON: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    config = {
        'db_path': data.get('db_path', 'bdtd_metadata.db'),
        'export_excel': data.get('export_path', 'resultados_coleta.xlsx'),
        'limit': data.get('limit'),
        'delay': float(data.get('delay', 2.0)),
        'search_type': data.get('search_type', 'AllFields'),
        'sort_order': data.get('sort_order', 'year'),
        'filters': [],
        'scrape_details': data.get('scrape_details', True),
        'keywords': data.get('keywords', [])
    }
    
    # Process filters
    filters_dict = data.get('filters', {})
    if isinstance(filters_dict, dict):
        for key, val in filters_dict.items():
            if val:
                val_str = str(val).strip()
                if key == 'language' and ',' in val_str:
                    langs = [l.strip() for l in val_str.split(',')]
                    for lang in langs:
                        config['filters'].append(f"~language:{lang}")
                else:
                    config['filters'].append(f"{key}:{val_str}")
    elif isinstance(filters_dict, list):
        config['filters'] = filters_dict
            
    return config


def extract_authors(authors_dict):
    """
    Extracts and joins all primary, secondary, and corporate authors into a single string.
    This handles various possible data structures in the authors dictionary.
    """
    if not authors_dict:
        return ""
    
    author_list = []
    
    # 1. Primary Authors
    primary = authors_dict.get('primary', {})
    if isinstance(primary, dict):
        author_list.extend(primary.keys())
    elif isinstance(primary, list):
        author_list.extend(primary)
        
    # 2. Secondary Authors (Co-authors, advisors, etc.)
    secondary = authors_dict.get('secondary', [])
    if isinstance(secondary, dict):
        author_list.extend(secondary.keys())
    elif isinstance(secondary, list):
        for sa in secondary:
            if isinstance(sa, dict):
                author_list.extend(sa.keys())
            else:
                author_list.append(str(sa))
                
    # 3. Corporate Authors
    corporate = authors_dict.get('corporate', [])
    if isinstance(corporate, dict):
        author_list.extend(corporate.keys())
    elif isinstance(corporate, list):
        for ca in corporate:
            if isinstance(ca, dict):
                author_list.extend(ca.keys())
            else:
                author_list.append(str(ca))
                
    return "; ".join([a.strip() for a in author_list if a])


def extract_subjects(subjects_list):
    """
    Extracts subjects from the list of lists returned by the API and joins them by semicolons.
    Example: [['Ciências Humanas - Geografia'], ['Sustentabilidade']] -> "Ciências Humanas - Geografia; Sustentabilidade"
    """
    if not subjects_list:
        return ""
    
    keywords = []
    for sub in subjects_list:
        if isinstance(sub, list) and len(sub) > 0:
            keywords.append(str(sub[0]).strip())
        elif isinstance(sub, str):
            keywords.append(sub.strip())
            
    return "; ".join([k for k in keywords if k])


def extract_url(urls_list):
    """
    Extracts the URL string from the list of URLs returned by the API.
    Can handle dictionaries (e.g. [{'url': '...', 'desc': '...'}]) or raw strings.
    """
    if not urls_list:
        return ""
    first_url = urls_list[0]
    if isinstance(first_url, dict):
        return first_url.get('url', '').strip()
    return str(first_url).strip()


def translate_format(fmt_str):
    """Translates the VuFind format type key to a user-friendly Portuguese descriptor."""
    if not fmt_str:
        return "Tese/Dissertação"
    fmt = fmt_str.lower()
    if 'doctoralthesis' in fmt or 'doctoral thesis' in fmt or 'tese' in fmt:
        return 'Tese'
    elif 'masterthesis' in fmt or 'master thesis' in fmt or 'dissertacao' in fmt or 'dissertação' in fmt:
        return 'Dissertação'
    elif 'article' in fmt or 'artigo' in fmt or 'journal' in fmt:
        return 'Artigo'
    elif 'book' in fmt or 'livro' in fmt:
        return 'Livro'
    elif 'chapter' in fmt or 'capitulo' in fmt:
        return 'Capítulo de Livro'
    return fmt_str.capitalize()


def scrape_record_details(record_id, cookie="OasisbrVerify=verified_human"):
    """
    Scrapes the BDTD public webpage for a single record to fetch fields
    not returned by the REST API, such as the advisor (orientador) and
    detailed university names.
    """
    url = f"https://bdtd.ibict.br/vufind/Record/{record_id}"
    req = urllib.request.Request(url)
    req.add_header('Cookie', cookie)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    
    details = {}
    try:
        res = urllib.request.urlopen(req, timeout=30)
        html = res.read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. Scrape DC meta tags from the head
        for meta in soup.find_all('meta'):
            name = meta.attrs.get('name')
            content = meta.attrs.get('content')
            if name and content:
                details[name] = content
                
        # 2. Scrape metadata tables (including the Metadados tab)
        for row in soup.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            if th and td:
                key = th.text.strip()
                val = td.text.strip()
                # If there are multiple lines (e.g. lists of subjects or publishers), join them
                lines = [l.strip() for l in val.split('\n') if l.strip()]
                if len(lines) > 1:
                    details[key] = "; ".join(lines)
                else:
                    details[key] = lines[0] if lines else ""
    except Exception as e:
        logger.warning(f"Failed to scrape webpage details for record {record_id}: {e}")
        
    return details


def get_source_info(details):
    """
    Extracts the source context (University, Publisher, or Journal)
    based on the document format.
    """
    fmt = details.get('format', '').lower()
    
    # Candidate fields
    institution = details.get('instname_str') or details.get('Instituição de defesa:') or details.get('Instituição:') or details.get('institution')
    publisher = details.get('publisher.none.fl_str_mv') or details.get('dc.publisher.none.fl_str_mv') or details.get('Editora:') or details.get('Editora')
    source = details.get('reponame_str') or details.get('dc.source.none.fl_str_mv') or details.get('Fonte:') or details.get('container_title')
    
    if 'thesis' in fmt or 'tese' in fmt or 'dissertacao' in fmt:
        return institution or source or publisher or "Não Informado"
    elif 'book' in fmt or 'livro' in fmt:
        return publisher or institution or source or "Não Informado"
    elif 'article' in fmt or 'artigo' in fmt or 'journal' in fmt:
        return source or publisher or institution or "Não Informado"
        
    # General fallback
    return institution or publisher or source or "Não Informado"


class DatabaseManager:
    """
    Manages SQLite database connections, schema creation, and record insertions.
    """
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.init_db()

    def init_db(self):
        """Initializes the database schema and sets up tables."""
        try:
            open_db_path = self.db_path
            if sys.platform.startswith('win') and len(os.path.abspath(open_db_path)) >= 240 and not os.path.abspath(open_db_path).startswith('\\\\?\\'):
                open_db_path = '\\\\?\\' + os.path.abspath(open_db_path)
            self.conn = sqlite3.connect(open_db_path)
            cursor = self.conn.cursor()
            
            # Create table with correct SQL typings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS academic_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT UNIQUE,
                    title TEXT,
                    creator TEXT,
                    date TEXT,
                    description TEXT,
                    subject TEXT,
                    type_of_research TEXT,
                    advisor TEXT,
                    source_institution TEXT,
                    download_url TEXT,
                    harvested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Index on record_id for fast duplicate checks, and title/date for search optimizations
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_record_id ON academic_metadata (record_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON academic_metadata (date);")
            
            self.conn.commit()
            logger.info(f"Database initialized successfully at: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize SQLite database: {e}")
            raise

    def insert_record(self, record_dict):
        """
        Inserts a single academic record into the database.
        Uses INSERT OR IGNORE to prevent duplicate entries based on the UNIQUE record_id.
        Returns True if a new record was inserted, False if it was ignored.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO academic_metadata 
                (record_id, title, creator, date, description, subject, type_of_research, advisor, source_institution, download_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_dict.get('record_id'),
                record_dict.get('title'),
                record_dict.get('creator'),
                record_dict.get('date'),
                record_dict.get('description'),
                record_dict.get('subject'),
                record_dict.get('type_of_research'),
                record_dict.get('advisor'),
                record_dict.get('source_institution'),
                record_dict.get('download_url')
            ))
            self.conn.commit()
            
            # If cursor.rowcount > 0, it means a record was inserted
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error inserting record {record_dict.get('record_id')}: {e}")
            return False

    def close(self):
        """Closes the connection to the database."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed.")


class BDTDHarvesterPipeline:
    """
    Core data pipeline that runs searches against the BDTD, parses matching records,
    scrapes advisor/university details, and coordinates SQLite persistence.
    """
    def __init__(self, db_manager, keywords, limit_per_keyword=None, delay=2.0, page_size=100,
                 search_type='AllFields', sort_order='year', filters=None, scrape_details=True):
        self.db = db_manager
        self.keywords = keywords
        self.limit_per_keyword = limit_per_keyword
        self.delay = delay
        self.page_size = page_size
        self.search_type = search_type or 'AllFields'
        self.sort_order = sort_order or 'year'
        self.scrape_details = scrape_details
        
        # Sanitize filters using the central WAF-aware function.
        self.api_filters, self.allowed_languages = sanitize_bdtd_filters(filters)
        
        if self.allowed_languages:
            logger.info(f"Language filter will be applied locally (post-filter): {self.allowed_languages}")
        if self.api_filters:
            logger.info(f"API filters to send ({len(self.api_filters)}/{BDTD_MAX_API_FILTERS} max): {self.api_filters}")
        
        # Fields to request from the VuFind search API
        self.request_fields = [
            'id', 'title', 'authors', 'subjects', 
            'languages', 'formats', 'urls', 'summary', 'publicationDates'
        ]

    def fetch_with_retries(self, keyword, page, max_retries=5, backoff_factor=2):
        """
        Queries bdtd_scraper.api.get_search_results with retry logic for network robustness.
        """
        retries = 0
        current_delay = self.delay
        
        # Clean the keyword to prevent WAF blocks (429 errors) and slow Lucene proximity queries.
        # 1. Stripping quotes prevents WAF false positives and slow Solr proximity searches.
        # 2. Removing accents (diacritics) avoids WAF rules blocking non-ASCII parameters.
        clean_keyword = keyword.replace('"', '').replace("'", "").strip()
        clean_keyword = unicodedata.normalize('NFKD', clean_keyword).encode('ASCII', 'ignore').decode('utf-8')
        if clean_keyword != keyword:
            logger.info(f"Cleaned query keyword: from '{keyword}' to '{clean_keyword}'")
            
        query_params = {
            'lookfor': clean_keyword,
            'page': page,
            'limit': self.page_size,
            'field': self.request_fields,
            'type': self.search_type,
            'sort': self.sort_order
        }
        
        if self.api_filters:
            query_params['filter'] = self.api_filters
            
        while retries < max_retries:
            is_rate_limited = False
            try:
                logger.info(f"Querying BDTD for '{keyword}' - Page {page}...")
                response = bdtd_scraper.api.get_search_results(**query_params)
                
                if response.get('status') == 'OK' or 'records' in response:
                    # Apply local language post-filter if configured
                    if self.allowed_languages and 'records' in response:
                        original_count = len(response['records'])
                        response['records'] = [
                            rec for rec in response['records']
                            if not rec.get('languages') or
                               any(lang in self.allowed_languages for lang in rec.get('languages', []))
                        ]
                        filtered_count = original_count - len(response['records'])
                        if filtered_count > 0:
                            logger.info(f"Local language filter removed {filtered_count} records (kept {len(response['records'])}/{original_count})")
                    return response
                
                logger.warning(f"Unexpected status in API response: {response.get('status')}")
                
            except Exception as e:
                err_msg = str(e)
                logger.warning(f"Error querying API (Attempt {retries + 1}/{max_retries}): {err_msg}")
                if "429" in err_msg:
                    is_rate_limited = True
                
            retries += 1
            if retries < max_retries:
                sleep_time = current_delay * (backoff_factor ** (retries - 1))
                if is_rate_limited:
                    sleep_time = max(15.0, sleep_time)
                    logger.warning(f"Rate limit hit (429). Cool down sleep initiated for {sleep_time:.2f} seconds...")
                else:
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                
        raise ConnectionError(f"Failed to fetch data from BDTD API after {max_retries} attempts.")

    def run(self):
        """Executes the harvesting pipeline for all keywords."""
        total_inserted = 0
        total_processed = 0
        
        # Keep track of unique records processed in this run to avoid logging duplicates
        seen_record_ids = set()

        logger.info(f"Starting metadata harvest for keywords: {self.keywords}")
        start_time = time.time()

        for keyword in self.keywords:
            logger.info(f"Processing keyword: '{keyword}'")
            page = 1
            keyword_inserted = 0
            keyword_processed = 0
            has_more_results = True
            
            while has_more_results:
                try:
                    res = self.fetch_with_retries(keyword, page)
                except Exception as e:
                    logger.error(f"Skipping keyword '{keyword}' due to API connection failure: {e}")
                    break
                
                records = res.get('records', [])
                result_count = res.get('resultCount', 0)
                
                if not records:
                    logger.info(f"No records returned for '{keyword}' on page {page}. Stopping.")
                    break
                
                logger.info(f"Retrieved {len(records)} records (Total matching on BDTD: {result_count})")
                
                for record in records:
                    record_id = record.get('id')
                    if not record_id:
                        continue
                        
                    keyword_processed += 1
                    total_processed += 1
                    
                    # Deduping inside local set to avoid double parsing in this loop
                    if record_id in seen_record_ids:
                        continue
                    seen_record_ids.add(record_id)
                    
                    # Extract fields with safe defaults and robust parser helper functions
                    title = record.get('title', '').strip()
                    creator = extract_authors(record.get('authors'))
                    
                    pub_dates = record.get('publicationDates', [])
                    date = str(pub_dates[0]).strip() if pub_dates else ""
                    
                    summaries = record.get('summary', [])
                    description = " ".join([s.strip() for s in summaries if s]).strip()
                    
                    subject = extract_subjects(record.get('subjects'))
                    
                    # Fetch web page details if enabled
                    if getattr(self, 'scrape_details', True):
                        logger.info(f" -> Scraping page details for record: {record_id}...")
                        details = scrape_record_details(record_id)
                    else:
                        details = {}
                    
                    # Format translation
                    type_of_research = translate_format(
                        details.get('format') or 
                        (record.get('formats', [''])[0] if record.get('formats') else '')
                    )
                    
                    # Advisor extraction logic (handles "Não Informado" replacement with Solr contributor field)
                    advisor = details.get('Orientador(a):')
                    if not advisor or "não informado" in advisor.lower():
                        advisor = details.get('dc.contributor.none.fl_str_mv') or advisor
                    if not advisor:
                        advisor = "Não Informado"
                        
                    # Source institution / publisher / journal name
                    source_institution = get_source_info(details)
                    if source_institution == "Não Informado" and record.get('institutions'):
                        source_institution = record.get('institutions')[0]
                        
                    # Clean creator/authors to remove birth/death years
                    creator = clean_creator_name(creator)
                    
                    # Resolve misfiled description (resumo) containing advisor names & clean advisor name
                    description, advisor = process_record_fields(
                        title=title, creator=creator, description=description, 
                        advisor=advisor, source_institution=source_institution
                    )
                    
                    # Extract download/access URL robustly (SEMPRE COM O LINK!)
                    download_url = extract_url(record.get('urls'))
                    if not download_url and details.get('Link de acesso:'):
                        download_url = details.get('Link de acesso:')
                    if not download_url and details.get('url'):
                        download_url = details.get('url')
                    if not download_url:
                        download_url = f"https://bdtd.ibict.br/vufind/Record/{record_id}"
                    
                    record_dict = {
                        'record_id': record_id,
                        'title': title,
                        'creator': creator,
                        'date': date,
                        'description': description,
                        'subject': subject,
                        'type_of_research': type_of_research,
                        'advisor': advisor,
                        'source_institution': source_institution,
                        'download_url': download_url
                    }
                    
                    inserted = self.db.insert_record(record_dict)
                    if inserted:
                        keyword_inserted += 1
                        total_inserted += 1
                        logger.info(f" -> [SAVED] {record_id} | Orientador: {advisor} | Instituição: {source_institution}")
                        
                        # Check limit inside loop
                        if self.limit_per_keyword and keyword_inserted >= self.limit_per_keyword:
                            break
                    else:
                        logger.debug(f" -> [DUPLICATE] {record_id} already in DB.")
                        
                    # Polite delay between webpage scrapes
                    time.sleep(1.0)
                        
                # Check limits after batch
                if self.limit_per_keyword and keyword_inserted >= self.limit_per_keyword:
                    logger.info(f"Limit of {self.limit_per_keyword} records reached for keyword '{keyword}'.")
                    break
                    
                # Pagination condition
                if page * self.page_size >= result_count or len(records) < self.page_size:
                    has_more_results = False
                    logger.info(f"All BDTD pages exhausted for keyword '{keyword}'.")
                else:
                    page += 1
                    time.sleep(self.delay)
                    
            logger.info(f"Finished '{keyword}': processed {keyword_processed} records, saved {keyword_inserted} relevant records.")

        elapsed = time.time() - start_time
        logger.info(f"Pipeline execution completed in {elapsed:.2f} seconds.")
        logger.info(f"Total processed: {total_processed} | Total saved to DB: {total_inserted}")


def export_to_format(db_path, export_path):
    """
    Exports the academic_metadata table from the SQLite database to Excel, CSV, or JSON
    based on the file extension of the target export path.
    """
    logger.info(f"Exporting database records to: {export_path}")
    try:
        conn = sqlite3.connect(db_path)
        
        # Select and rename columns as requested by the user
        query = """
            SELECT 
                creator AS "Autores",
                title AS "Título",
                date AS "Ano",
                type_of_research AS "Tipo de Pesquisa",
                advisor AS "Nome do Orientador",
                source_institution AS "Universidade / Editora / Revista",
                description AS "Resumo",
                download_url AS "Link para Download"
            FROM academic_metadata
            ORDER BY harvested_at DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            logger.warning("No records found in the database to export.")
            return False
            
        ext = os.path.splitext(export_path)[1].lower()
        if ext in ['.xlsx', '.xls']:
            df.to_excel(export_path, index=False)
        elif ext == '.csv':
            df.to_csv(export_path, index=False, encoding='utf-8')
        elif ext == '.json':
            df.to_json(export_path, orient='records', force_ascii=False, indent=4)
        else:
            logger.warning(f"Unrecognized export format: {ext}. Defaulting to CSV.")
            df.to_csv(export_path, index=False, encoding='utf-8')
            
        logger.info(f"Successfully exported {len(df)} records.")
        return True
    except Exception as e:
        logger.error(f"Failed to export database: {e}")
        return False


def run_harvest(keywords, db_path='bdtd_metadata.db', export_path='bdtd_metadata.xlsx', 
                limit=None, delay=2.0, page_size=100, search_type='AllFields', 
                sort_order='year', filters=None, scrape_details=True):
    """
    High-level entrypoint to execute the BDTD metadata harvesting pipeline programmatically.
    """
    # Attach file handler for logging execution history
    try:
        log_dir = os.path.dirname(export_path) if os.path.dirname(export_path) else "."
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "log_bdtd.txt")
        open_path = log_file_path
        if sys.platform.startswith('win') and len(os.path.abspath(open_path)) >= 250 and not os.path.abspath(open_path).startswith('\\\\?\\'):
            open_path = '\\\\?\\' + os.path.abspath(open_path)
        file_handler = logging.FileHandler(open_path, mode='w', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(file_handler)
        logger.info(f"Log de execução sendo gravado em: {log_file_path}")
    except Exception as e:
        logger.warning(f"Não foi possível iniciar o arquivo de log para gravação: {e}")

    db_manager = None
    try:
        # Initialize Database Manager
        db_manager = DatabaseManager(db_path)
        
        # Setup and run Harvester Pipeline
        pipeline = BDTDHarvesterPipeline(
            db_manager=db_manager,
            keywords=keywords,
            limit_per_keyword=limit,
            delay=delay,
            page_size=page_size,
            search_type=search_type,
            sort_order=sort_order,
            filters=filters,
            scrape_details=scrape_details
        )
        pipeline.run()
        
        # Close database connection to ensure all writes are flushed
        db_manager.close()
        db_manager = None
        
        # Export database data to Excel/CSV/JSON
        export_to_format(db_path, export_path)
        return True
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return False
    finally:
        if db_manager:
            db_manager.close()


def main():
    parser = argparse.ArgumentParser(
        description="Automated Python pipeline to extract BDTD academic metadata and save to SQLite / Excel.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--db-path', 
        type=str, 
        default='bdtd_metadata.db', 
        help="Filename or path of the destination SQLite database."
    )
    parser.add_argument(
        '--limit', 
        type=int, 
        default=None, 
        help="Maximum number of records to retrieve and save PER keyword. If omitted, collects all matching records."
    )
    parser.add_argument(
        '--delay', 
        type=float, 
        default=2.0, 
        help="Polite wait time (in seconds) between requests to avoid overloading the BDTD server."
    )
    parser.add_argument(
        '--page-size', 
        type=int, 
        default=100, 
        help="Number of records to fetch per pagination request (max 100)."
    )
    parser.add_argument(
        '--keywords',
        type=str,
        nargs='+',
        default=[
            "desenvolvimento regional", 
            "políticas públicas", 
            "planejamento urbano"
        ],
        help="List of keywords/phrases to search for."
    )
    parser.add_argument(
        '--export-excel',
        type=str,
        default='bdtd_metadata.xlsx',
        help="Path where the final sheet should be saved (supports .xlsx, .csv, .json)."
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help="Path to a JSON or Excel configuration file. If omitted, checks for bdtd_config.json first, then bdtd_config.xlsx."
    )
    parser.add_argument(
        '--type',
        type=str,
        default='AllFields',
        help="Search field type (AllFields, Title, Author, Subject, Advisor)."
    )
    parser.add_argument(
        '--sort',
        type=str,
        default='year',
        help="Sorting order (year, year asc, relevance, title, author)."
    )
    parser.add_argument(
        '--filter',
        type=str,
        nargs='*',
        default=[],
        help="List of Solr filters (e.g. format:masterThesis institution:USP)."
    )
    parser.add_argument(
        '--fast-mode',
        action='store_true',
        help="Skip individual webpage scraping (scrape_details=False) for maximum speed."
    )
    
    args = parser.parse_args()
    
    config_file = args.config
    use_config = False
    config_type = None
    
    if config_file:
        if os.path.exists(config_file):
            use_config = True
            config_type = 'json' if config_file.lower().endswith('.json') else 'excel'
    else:
        # Check defaults
        if os.path.exists('bdtd_config.json'):
            config_file = 'bdtd_config.json'
            use_config = True
            config_type = 'json'
        elif os.path.exists('bdtd_config.xlsx'):
            config_file = 'bdtd_config.xlsx'
            use_config = True
            config_type = 'excel'
            
    scrape_details = not args.fast_mode
    if use_config:
        try:
            if config_type == 'json':
                config = read_json_config_file(config_file)
            else:
                config = read_config_file(config_file)
                
            db_path = config['db_path']
            export_excel = config['export_excel']
            limit = config['limit']
            delay = config['delay']
            target_keywords = config['keywords']
            search_type = config.get('search_type', 'AllFields')
            sort_order = config.get('sort_order', 'year')
            filters = config.get('filters', [])
            if 'scrape_details' in config and not args.fast_mode:
                scrape_details = config['scrape_details']
            logger.info(f"Loaded config from {config_file}: DB={db_path}, Export={export_excel}, Limit={limit}, Delay={delay}, Type={search_type}, Sort={sort_order}, Filters={filters}, ScrapeDetails={scrape_details}, Keywords={target_keywords}")
        except Exception as e:
            logger.error(f"Failed to read configuration file: {e}. Falling back to CLI arguments.")
            db_path = args.db_path
            export_excel = args.export_excel
            limit = args.limit
            delay = args.delay
            target_keywords = args.keywords
            search_type = args.type
            sort_order = args.sort
            filters = args.filter
    else:
        # Generate default templates if they do not exist
        if not config_file:
            try:
                if not os.path.exists('bdtd_config.json'):
                    create_json_config_template('bdtd_config.json')
                if not os.path.exists('bdtd_config.xlsx'):
                    create_config_template('bdtd_config.xlsx')
            except Exception as e:
                logger.warning(f"Could not create configuration templates: {e}")
                
        db_path = args.db_path
        export_excel = args.export_excel
        limit = args.limit
        delay = args.delay
        target_keywords = args.keywords
        search_type = args.type
        sort_order = args.sort
        filters = args.filter

    if not target_keywords:
        logger.error("No keywords specified. Please define keywords via CLI or config file.")
        return

    try:
        # Execute high-level run_harvest function
        success = run_harvest(
            keywords=target_keywords,
            db_path=db_path,
            export_path=export_excel,
            limit=limit,
            delay=delay,
            page_size=args.page_size,
            search_type=search_type,
            sort_order=sort_order,
            filters=filters,
            scrape_details=scrape_details
        )
        if success:
            logger.info("Pipeline executed successfully.")
        else:
            logger.error("Pipeline finished with errors.")
    except KeyboardInterrupt:
        logger.warning("\nPipeline interrupted by user.")
    except Exception as e:
        logger.critical(f"Pipeline crashed due to an unhandled exception: {e}", exc_info=True)


if __name__ == '__main__':
    main()
