#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PDF Downloader and Text Extractor for Systematic Review Session
Description: Downloads PDFs for papers marked as 'Incluído' in the session JSON,
             using robust domain-specific resolvers (UNESP, UDESC, USP, UFRJ, Maxwell, SciELO),
             extracts their text content, and updates the JSON file.
"""

import os
import json
import re
import urllib.parse
import urllib3
import requests
import pypdf

# Disable SSL verification warnings for university repositories with misconfigured SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Centralized path resolution
try:
    from config_app.utils.path_resolver import resolve_path
except ImportError:
    import sys as _sys
    from pathlib import Path as _Path
    _BASE = _Path(__file__).resolve().parent
    if str(_BASE) not in _sys.path:
        _sys.path.insert(0, str(_BASE))
    def resolve_path(p):
        _p = _Path(p)
        return _p if _p.is_absolute() else _BASE / _p

# Configurations — resolved relative to project root
JSON_PATH = str(resolve_path(os.path.join("Revisão teste", "triagem2_sessao.json")))
OUTPUT_PDF_DIR = str(resolve_path(os.path.join("Revisão teste", "pdfs")))

# Request Headers to mimic a browser and avoid basic anti-bot blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
}

def clean_filename(title):
    """Generates a safe filename from the paper title."""
    clean = "".join(c for c in title[:45] if c.isalnum() or c in (' ', '_', '-')).strip()
    clean = clean.replace(' ', '_')
    return clean

def extract_text_from_pdf(pdf_path):
    """Extracts text page by page from a local PDF file."""
    if not os.path.exists(pdf_path):
        return ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        pages_text = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text()
            if txt:
                pages_text.append(f"--- PÁGINA {i+1} ---\n{txt}\n")
        return "\n".join(pages_text)
    except Exception as e:
        print(f"  [Erro] Falha ao extrair texto do PDF {os.path.basename(pdf_path)}: {e}")
        return ""

def get_dspace7_pdf_url(base_api_url, handle):
    """Generic resolver for DSpace 7 REST API."""
    search_url = f"{base_api_url}/api/discover/search/objects?query=handle:{handle}"
    try:
        r = requests.get(search_url, headers=HEADERS, timeout=15, verify=False)
        if r.status_code != 200:
            return None
        data = r.json()
        search_result = data.get('_embedded', {}).get('searchResult', {})
        objects = search_result.get('_embedded', {}).get('objects', [])
        if not objects:
            return None
        
        indexable_object = objects[0].get('_embedded', {}).get('indexableObject', {})
        bundles_url = indexable_object.get('_links', {}).get('bundles', {}).get('href')
        if not bundles_url:
            return None
            
        br = requests.get(bundles_url, headers=HEADERS, timeout=15, verify=False)
        if br.status_code != 200:
            return None
            
        bundles = br.json().get('_embedded', {}).get('bundles', [])
        for b in bundles:
            if b.get('name') == 'ORIGINAL':
                bs_url = b.get('_links', {}).get('bitstreams', {}).get('href')
                if not bs_url:
                    continue
                bs_r = requests.get(bs_url, headers=HEADERS, timeout=15, verify=False)
                if bs_r.status_code != 200:
                    continue
                bs_list = bs_r.json().get('_embedded', {}).get('bitstreams', [])
                for bs in bs_list:
                    content_url = bs.get('_links', {}).get('content', {}).get('href')
                    if content_url:
                        return content_url
    except Exception as e:
        print(f"    [DSpace7 API Error] {e}")
    return None

def resolve_usp_pdf_url(url):
    """USP specific resolver using pt-br.html page crawl."""
    if not url.endswith("pt-br.html"):
        if url.endswith("/"):
            url = url + "pt-br.html"
        else:
            url = url + "/pt-br.html"
            
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        if r.status_code == 200:
            links = re.findall(r'href=["\']([^"\']+)["\']', r.text, re.IGNORECASE)
            pdf_links = [l for l in links if 'pdf' in l.lower()]
            if pdf_links:
                return urllib.parse.urljoin(url, pdf_links[0])
    except Exception as e:
        print(f"    [USP Resolver Error] {e}")
    return None

def resolve_ufrj_pdf_url(url):
    """UFRJ Pantheon specific resolver using HTTPS crawl."""
    url = url.replace("http://", "https://")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        if r.status_code == 200:
            links = re.findall(r'href=["\']([^"\']+)["\']', r.text, re.IGNORECASE)
            pdf_links = [l for l in links if 'pdf' in l.lower() or 'bitstream' in l.lower()]
            if pdf_links:
                return urllib.parse.urljoin(r.url, pdf_links[0])
    except Exception as e:
        print(f"    [UFRJ Resolver Error] {e}")
    return None

def resolve_maxwell_pdf_url(url):
    """Maxwell case-sensitive direct PDF downloader."""
    seq_match = re.search(r'nrSeq=([0-9]+)', url)
    if seq_match:
        nrseq = seq_match.group(1)
        return f"https://www.maxwell.vrac.puc-rio.br/{nrseq}/{nrseq}.PDF"
    return None

def resolve_pdf_url(url):
    """Converts standard database landing pages to direct PDF download links if possible."""
    if not url:
        return ""
        
    url_lower = url.lower()
    
    # 1. If already a PDF
    if url_lower.endswith(".pdf") or ".pdf?" in url_lower:
        return url
        
    # 2. Extract DSpace Handle if present
    handle_match = re.search(r'(?:handle|handle\.net)/([^/]+)/([^/\?]+)', url)
    handle = f"{handle_match.group(1)}/{handle_match.group(2)}" if handle_match else None
    
    # 3. Apply Domain Specific Resolvers
    if "scielo" in url_lower and "script=sci_arttext" in url_lower:
        # SciELO landing pages: convert script=sci_arttext to script=sci_pdf
        return url.replace("script=sci_arttext", "script=sci_pdf")
        
    elif "unesp.br" in url_lower or (handle and handle.startswith("11449/")):
        # UNESP (DSpace 7)
        if handle:
            print("    [Info] Resolvendo via API DSpace 7 da UNESP...")
            res = get_dspace7_pdf_url("https://repositorio.unesp.br/server", handle)
            if res: return res
            
    elif "udesc.br" in url_lower:
        # UDESC (DSpace 7)
        if handle:
            print("    [Info] Resolvendo via API DSpace 7 da UDESC...")
            res = get_dspace7_pdf_url("https://repositorio-api.udesc.br/server", handle)
            if res: return res
            
    elif "teses.usp.br" in url_lower:
        # USP
        print("    [Info] Resolvendo via crawler estático da USP...")
        res = resolve_usp_pdf_url(url)
        if res: return res
        
    elif "pantheon.ufrj.br" in url_lower or (handle and handle.startswith("11422/")):
        # UFRJ
        print("    [Info] Resolvendo via crawler HTTPS da UFRJ...")
        res = resolve_ufrj_pdf_url(url)
        if res: return res
        
    elif "maxwell.vrac.puc-rio.br" in url_lower:
        # Maxwell PUC-Rio
        print("    [Info] Resolvendo via URL direta da Maxwell...")
        res = resolve_maxwell_pdf_url(url)
        if res: return res
        
    # Fallback to original URL
    return url

def download_and_process():
    print("=" * 60)
    print("      DOWNLOADER E EXTRACTOR DE PDFS DA TRIAGEM 2 (OTIMIZADO)")
    print("=" * 60)
    
    if not os.path.exists(JSON_PATH):
        print(f"[ERRO] Arquivo de sessão não encontrado em: {JSON_PATH}")
        return
        
    os.makedirs(OUTPUT_PDF_DIR, exist_ok=True)
    
    # Load session JSON
    print(f"Carregando sessão de {JSON_PATH}...")
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            session = json.load(f)
    except Exception as e:
        print(f"[ERRO] Falha ao ler arquivo JSON: {e}")
        return
        
    trabalhos = session.get('trabalhos', [])
    # Filter papers where Decisao == 'Incluído'
    included = [t for t in trabalhos if t.get('Decisao') == 'Incluído']
    total_included = len(included)
    
    print(f"Total de trabalhos na sessão: {len(trabalhos)}")
    print(f"Trabalhos marcados como 'Incluído': {total_included}")
    print("-" * 60)
    
    if total_included == 0:
        print("Nenhum trabalho marcado como 'Incluído' para processar.")
        return
        
    downloaded_count = 0
    failed_count = 0
    already_done = 0
    completed_count = 0
    
    # Pre-filter already downloaded papers to avoid thread submission overhead
    to_download = []
    for paper in included:
        title = paper.get('Título', 'Sem título')
        paper_id = paper.get('id', '?')
        
        if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
            paper['Extracao'] = {}
        ext = paper['Extracao']
        
        pdf_status = ext.get('status_pdf', 'Pendente')
        pdf_path = ext.get('caminho_pdf', '')
        
        if pdf_status == 'Baixado' and pdf_path and os.path.exists(pdf_path):
            already_done += 1
            if not ext.get('texto_extraido'):
                ext['texto_extraido'] = extract_text_from_pdf(pdf_path)
        else:
            to_download.append(paper)

    total_to_download = len(to_download)
    print(f" - Já baixados/mantidos anteriormente: {already_done}")
    print(f" - Pendentes para download: {total_to_download}")
    print("-" * 60)
    
    if total_to_download > 0:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        counter_lock = threading.Lock()
        
        def download_task(paper, idx):
            nonlocal downloaded_count, failed_count, completed_count
            title = paper.get('Título', 'Sem título')
            paper_id = paper.get('id', '?')
            url = paper.get('Link para Download', '')
            ext = paper['Extracao']
            
            print(f"[{idx}/{total_to_download}] Iniciando ID {paper_id}: {title[:50]}...")
            
            if not url:
                print(f"  -> ID {paper_id}: [AVISO] Sem link para download.")
                ext['status_pdf'] = 'Pendente'
                with counter_lock:
                    failed_count += 1
                    completed_count += 1
                return False
                
            resolved_url = resolve_pdf_url(url)
            safe_title = clean_filename(title)
            filename = f"ID_{paper_id}_{safe_title}.pdf"
            dest_path = os.path.join(OUTPUT_PDF_DIR, filename).replace("\\", "/")
            
            try:
                ext['status_pdf'] = 'Baixando...'
                response = requests.get(resolved_url, headers=HEADERS, timeout=30, verify=False, allow_redirects=True)
                
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '').lower()
                    is_pdf = 'application/pdf' in content_type or response.content.startswith(b'%PDF')
                    
                    if not is_pdf:
                        print(f"  -> ID {paper_id}: [FALHA] Resposta não era um PDF (Content-Type: {content_type}).")
                        ext['status_pdf'] = 'Erro'
                        ext['erro_detalhe'] = f"Retornou HTML/Tipo inválido em vez de PDF (Content-Type: {content_type})"
                        with counter_lock:
                            failed_count += 1
                    else:
                        with open(dest_path, 'wb') as pdf_file:
                            pdf_file.write(response.content)
                            
                        print(f"  -> ID {paper_id}: [OK] PDF salvo.")
                        ext['status_pdf'] = 'Baixado'
                        ext['caminho_pdf'] = dest_path
                        if 'erro_detalhe' in ext:
                            del ext['erro_detalhe']
                        
                        # Extract text content
                        extracted_text = extract_text_from_pdf(dest_path)
                        ext['texto_extraido'] = extracted_text
                        
                        with counter_lock:
                            downloaded_count += 1
                else:
                    print(f"  -> ID {paper_id}: [FALHA] Resposta HTTP: Código {response.status_code}")
                    ext['status_pdf'] = 'Erro'
                    ext['erro_detalhe'] = f"Falha no download (Código HTTP: {response.status_code})"
                    with counter_lock:
                        failed_count += 1
            except requests.exceptions.Timeout:
                print(f"  -> ID {paper_id}: [FALHA] Timeout.")
                ext['status_pdf'] = 'Erro'
                ext['erro_detalhe'] = "Conexão expirou (Timeout)"
                with counter_lock:
                    failed_count += 1
            except Exception as e:
                print(f"  -> ID {paper_id}: [FALHA] Erro: {e}")
                ext['status_pdf'] = 'Erro'
                ext['erro_detalhe'] = str(e)
                with counter_lock:
                    failed_count += 1
            
            with counter_lock:
                completed_count += 1
                print(f"  -> Progresso: {completed_count}/{total_to_download} concluídos.")
                
            return True

        # Run downloads concurrently with 8 workers
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(download_task, paper, idx) for idx, paper in enumerate(to_download, 1)]
            for future in as_completed(futures):
                pass
            
    print("-" * 60)
    print("Salvando atualizações no arquivo JSON de sessão...")
    try:
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=4)
        print("Sessão salva com sucesso!")
    except Exception as e:
        print(f"[ERRO] Falha ao salvar arquivo JSON: {e}")
        return
        
    print("=" * 60)
    print("                      RELATÓRIO FINAL")
    print("=" * 60)
    print(f" - Já baixados/mantidos: {already_done}")
    print(f" - Novos downloads realizados: {downloaded_count}")
    print(f" - Downloads com falha (status 'Erro'): {failed_count}")
    print("=" * 60)

if __name__ == "__main__":
    download_and_process()
