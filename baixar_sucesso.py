#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
baixar_sucesso.py: Downloads the 14 non-bot-walled PDFs for Included papers in the systematic review session.
Handles UNESP, UDESC, USP, UFRJ, and Maxwell.
"""

import os
import json
import re
import urllib.parse
import urllib3
import requests
import pypdf

# Disable SSL verification warnings for university repositories
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Centralized path resolution
try:
    from config_app.utils.path_resolver import resolve_path
except ImportError:
    from pathlib import Path as _Path
    _BASE = _Path(__file__).resolve().parent
    def resolve_path(p):
        _p = _Path(p)
        return _p if _p.is_absolute() else _BASE / _p

JSON_PATH = str(resolve_path(os.path.join("Revisão teste", "triagem2_sessao.json")))
OUTPUT_PDF_DIR = str(resolve_path(os.path.join("Revisão teste", "pdfs")))

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
}

def clean_filename(title):
    clean = "".join(c for c in title[:45] if c.isalnum() or c in (' ', '_', '-')).strip()
    clean = clean.replace(' ', '_')
    return clean

def extract_text_from_pdf(pdf_path):
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
                    # Return the first bitstream content link (usually the PDF)
                    content_url = bs.get('_links', {}).get('content', {}).get('href')
                    if content_url:
                        return content_url
    except Exception as e:
        print(f"    [DSpace7 API Error] {e}")
    return None

def resolve_usp_pdf_url(url):
    """USP specific resolver using pt-br.html page crawl."""
    # Ensure URL points to the static page
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
                # Resolve relative URL to absolute
                return urllib.parse.urljoin(url, pdf_links[0])
    except Exception as e:
        print(f"    [USP Resolver Error] {e}")
    return None

def resolve_ufrj_pdf_url(url):
    """UFRJ Pantheon specific resolver using HTTPS crawl."""
    # Force HTTPS to prevent connection refusals
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

def process_paper(paper):
    title = paper.get('Título', 'Sem título')
    paper_id = paper['id']
    url = paper.get('Link para Download', '')
    
    if not url:
        return False, "Sem link cadastrado."
        
    resolved_pdf_url = None
    
    # 1. Detect Domain and Resolve
    url_lower = url.lower()
    
    # Extract handle if present
    handle_match = re.search(r'(?:handle|handle\.net)/([^/]+)/([^/\?]+)', url)
    handle = f"{handle_match.group(1)}/{handle_match.group(2)}" if handle_match else None
    
    if "unesp.br" in url_lower or (handle and handle.startswith("11449/")):
        # UNESP (DSpace 7)
        if handle:
            print("  Detectado: UNESP (DSpace 7)")
            resolved_pdf_url = get_dspace7_pdf_url("https://repositorio.unesp.br/server", handle)
    elif "udesc.br" in url_lower:
        # UDESC (DSpace 7)
        if handle:
            print("  Detectado: UDESC (DSpace 7)")
            resolved_pdf_url = get_dspace7_pdf_url("https://repositorio-api.udesc.br/server", handle)
    elif "teses.usp.br" in url_lower:
        # USP
        print("  Detectado: USP (Teses)")
        resolved_pdf_url = resolve_usp_pdf_url(url)
    elif "pantheon.ufrj.br" in url_lower or (handle and handle.startswith("11422/")):
        # UFRJ
        print("  Detectado: UFRJ (Pantheon)")
        resolved_pdf_url = resolve_ufrj_pdf_url(url)
    elif "maxwell.vrac.puc-rio.br" in url_lower:
        # Maxwell PUC-Rio
        print("  Detectado: Maxwell PUC-Rio")
        resolved_pdf_url = resolve_maxwell_pdf_url(url)
        
    if not resolved_pdf_url:
        # Check if URL itself is direct PDF link
        if url_lower.endswith(".pdf") or ".pdf?" in url_lower:
            resolved_pdf_url = url
            
    if not resolved_pdf_url:
        return False, "Não foi possível resolver o link direto do PDF para este repositório."
        
    print(f"  Link direto resolvido: {resolved_pdf_url}")
    
    # 2. Download and Verify
    dest_filename = f"ID_{paper_id}_{clean_filename(title)}.pdf"
    dest_path = os.path.join(OUTPUT_PDF_DIR, dest_filename).replace("\\", "/")
    
    try:
        r = requests.get(resolved_pdf_url, headers=HEADERS, timeout=30, verify=False)
        if r.status_code == 200:
            content_type = r.headers.get('Content-Type', '').lower()
            is_pdf = 'application/pdf' in content_type or r.content.startswith(b'%PDF')
            
            if not is_pdf:
                return False, f"O link retornado não era um PDF válido (Content-Type: {content_type})"
                
            with open(dest_path, 'wb') as f:
                f.write(r.content)
                
            # 3. Extract text
            print("  Extraindo texto...")
            text = extract_text_from_pdf(dest_path)
            
            # Update paper metadata
            if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
                paper['Extracao'] = {}
            ext = paper['Extracao']
            ext['status_pdf'] = 'Baixado'
            ext['caminho_pdf'] = dest_path
            ext['texto_extraido'] = text
            if 'erro_detalhe' in ext:
                del ext['erro_detalhe']
                
            return True, f"Sucesso! PDF salvo em: {dest_path}"
        else:
            return False, f"Falha no download (Código HTTP: {r.status_code})"
    except Exception as e:
        return False, f"Erro durante download/processamento: {e}"

def main():
    print("=" * 70)
    print("        DOWNLOADER DE PDFS PARA REPOSITÓRIOS COMPATÍVEIS")
    print("=" * 70)
    
    if not os.path.exists(JSON_PATH):
        print(f"[ERRO] Arquivo de sessão não encontrado em: {JSON_PATH}")
        return
        
    os.makedirs(OUTPUT_PDF_DIR, exist_ok=True)
    
    print(f"Carregando sessão de {JSON_PATH}...")
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            session = json.load(f)
    except Exception as e:
        print(f"[ERRO] Falha ao ler arquivo JSON: {e}")
        return
        
    trabalhos = session.get('trabalhos', [])
    
    # Select included papers that do not have a downloaded PDF and belong to the domains we can handle programmatically
    target_domains = ["unesp.br", "udesc.br", "usp.br", "ufrj.br", "maxwell.vrac.puc-rio.br", "11449/", "11422/"]
    
    to_process = []
    for t in trabalhos:
        if t.get('Decisao') == 'Incluído':
            ext = t.get('Extracao', {})
            if ext.get('status_pdf') != 'Baixado':
                url = t.get('Link para Download', '')
                if any(dom in url.lower() for dom in target_domains):
                    to_process.append(t)
                    
    total_to_process = len(to_process)
    print(f"Trabalhos compatíveis pendentes para processar: {total_to_process}")
    print("-" * 70)
    
    if total_to_process == 0:
        print("Nenhum PDF compatível pendente nesta rodada.")
        return
        
    downloaded_count = 0
    failed_count = 0
    
    for idx, paper in enumerate(to_process, 1):
        paper_id = paper['id']
        title = paper.get('Título', 'Sem título')
        print(f"[{idx}/{total_to_process}] ID {paper_id}: {title[:60]}...")
        
        success, message = process_paper(paper)
        if success:
            print(f"  -> {message}")
            downloaded_count += 1
        else:
            print(f"  -> [FALHA] {message}")
            if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
                paper['Extracao'] = {}
            paper['Extracao']['status_pdf'] = 'Erro'
            paper['Extracao']['erro_detalhe'] = message
            failed_count += 1
        print()
            
    print("-" * 70)
    print("Gravando atualizações no arquivo JSON de sessão...")
    try:
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=4)
        print("Sessão salva com sucesso!")
    except Exception as e:
        print(f"[ERRO] Falha ao salvar arquivo JSON: {e}")
        return
        
    print("=" * 70)
    print("                      RELATÓRIO DE PROCESSAMENTO")
    print("=" * 70)
    print(f" - PDFs baixados com sucesso: {downloaded_count}")
    print(f" - Falhas ocorridas: {failed_count}")
    print("=" * 70)

if __name__ == "__main__":
    main()
