#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Resolves and downloads failed repository PDFs for Included papers in the systematic review session.
Uses landing page HTML parsing and handles SSL verification issues.
"""

import os
import json
import re
import urllib.parse
import urllib3
import requests
import pypdf

# Disable SSL verification warnings for Brazilian university repositories with misconfigured SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

JSON_PATH = os.path.join("Revisão teste", "triagem2_sessao.json")
OUTPUT_PDF_DIR = os.path.join("Revisão teste", "pdfs")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
}

def clean_filename(title):
    clean = "".join(c for c in title[:45] if c.isalnum() or c in (' ', '_', '-')).strip()
    clean = clean.replace(' ', '_')
    return clean

def extract_pdf_candidate_urls(html, base_url):
    candidates = []
    
    # 1. Search for href links in HTML
    for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        link = match.group(1).replace('&amp;', '&')
        
        # We look for typical PDF/DSpace download patterns:
        # - Contains '/bitstream/' (DSpace)
        # - Ends with '.pdf' (possibly with query parameters)
        # - Contains '/download'
        # - Contains '/viewer' or '/reader' (some custom repository viewers)
        link_lower = link.lower()
        if '/bitstream/' in link_lower or '.pdf' in link_lower or '/download' in link_lower or 'sequence=' in link_lower:
            candidates.append(link)
            
    # 2. Resolve relative URLs to absolute URLs
    resolved = []
    for c in candidates:
        absolute = urllib.parse.urljoin(base_url, c)
        resolved.append(absolute)
        
    # Return unique resolved links (maintaining order)
    return list(dict.fromkeys(resolved))

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

def main():
    print("=" * 70)
    print("   CRAWLER AGÊNTICO DE PDFS DE REPOSITÓRIOS UNIVERSITÁRIOS")
    print("=" * 70)
    
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
    # Get all included works that don't have a downloaded PDF
    failed_papers = []
    for t in trabalhos:
        if t.get('Decisao') == 'Incluído':
            ext = t.get('Extracao', {})
            if ext.get('status_pdf') != 'Baixado':
                failed_papers.append(t)
                
    total_failed = len(failed_papers)
    print(f"Total de trabalhos marcados como 'Incluído': {len([t for t in trabalhos if t.get('Decisao')=='Incluído'])}")
    print(f"Trabalhos pendentes de PDF para processar: {total_failed}")
    print("-" * 70)
    
    if total_failed == 0:
        print("Nenhum PDF pendente para baixar. Todos estão com status 'Baixado'!")
        return
        
    downloaded_count = 0
    errors_count = 0
    completed_count = 0
    
    if total_failed > 0:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        counter_lock = threading.Lock()
        
        def download_failed_task(paper, idx):
            nonlocal downloaded_count, errors_count, completed_count
            paper_id = paper['id']
            title = paper.get('Título', 'Sem título')
            url = paper.get('Link para Download', '')
            ext = paper['Extracao']
            
            print(f"[{idx}/{total_failed}] Iniciando ID {paper_id}: {title[:55]}...")
            
            if not url:
                print(f"  -> ID {paper_id}: [Pendente] Sem link cadastrado.")
                ext['status_pdf'] = 'Pendente'
                with counter_lock:
                    completed_count += 1
                return False
                
            print(f"  -> ID {paper_id}: Acessando página: {url}")
            try:
                response = requests.get(url, headers=HEADERS, timeout=20, verify=False, allow_redirects=True)
                
                if response.status_code != 200:
                    print(f"  -> ID {paper_id}: [Falha] Erro HTTP ao carregar página: {response.status_code}")
                    ext['status_pdf'] = 'Erro'
                    with counter_lock:
                        errors_count += 1
                        completed_count += 1
                    return False
                    
                content_type = response.headers.get('Content-Type', '').lower()
                is_pdf = 'application/pdf' in content_type or response.content.startswith(b'%PDF')
                
                dest_filename = f"ID_{paper_id}_{clean_filename(title)}.pdf"
                dest_path = os.path.join(OUTPUT_PDF_DIR, dest_filename).replace("\\", "/")
                
                if is_pdf:
                    print(f"  -> ID {paper_id}: [OK] Página redirecionou diretamente para o arquivo PDF!")
                    with open(dest_path, 'wb') as pdf_file:
                        pdf_file.write(response.content)
                    ext['status_pdf'] = 'Baixado'
                    ext['caminho_pdf'] = dest_path
                    ext['texto_extraido'] = extract_text_from_pdf(dest_path)
                    with counter_lock:
                        downloaded_count += 1
                        completed_count += 1
                    return True
                    
                candidates = extract_pdf_candidate_urls(response.text, response.url)
                print(f"  -> ID {paper_id}: Links candidatos extraídos: {len(candidates)}")
                
                download_success = False
                for c_url in candidates:
                    if c_url.strip('/') == url.strip('/'):
                        continue
                    print(f"    -> ID {paper_id}: Tentando baixar candidato: {c_url}")
                    try:
                        r_pdf = requests.get(c_url, headers=HEADERS, timeout=20, verify=False, allow_redirects=True)
                        if r_pdf.status_code == 200:
                            c_type = r_pdf.headers.get('Content-Type', '').lower()
                            if 'application/pdf' in c_type or r_pdf.content.startswith(b'%PDF'):
                                with open(dest_path, 'wb') as pdf_file:
                                    pdf_file.write(r_pdf.content)
                                print(f"    -> ID {paper_id}: [SUCESSO] PDF baixado.")
                                ext['status_pdf'] = 'Baixado'
                                ext['caminho_pdf'] = dest_path
                                ext['texto_extraido'] = extract_text_from_pdf(dest_path)
                                download_success = True
                                with counter_lock:
                                    downloaded_count += 1
                                break
                            else:
                                print(f"    -> ID {paper_id}: Ignorado. Tipo de conteúdo: {c_type}")
                        else:
                            print(f"    -> ID {paper_id}: Ignorado. Código HTTP: {r_pdf.status_code}")
                    except Exception as ex:
                        print(f"    -> ID {paper_id}: Erro ao acessar link: {ex}")
                        
                if download_success:
                    pass
                else:
                    print(f"  -> ID {paper_id}: [Falha] Nenhum PDF válido pôde ser extraído da página.")
                    ext['status_pdf'] = 'Erro'
                    with counter_lock:
                        errors_count += 1
            except Exception as e:
                print(f"  -> ID {paper_id}: [Falha] Erro ao processar página: {e}")
                ext['status_pdf'] = 'Erro'
                with counter_lock:
                    errors_count += 1
            
            with counter_lock:
                completed_count += 1
                print(f"  -> Progresso failed: {completed_count}/{total_failed} concluídos.")
                
            return True

        # Run concurrently with 8 threads
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(download_failed_task, paper, idx) for idx, paper in enumerate(failed_papers, 1)]
            for future in as_completed(futures):
                pass
                
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
    print("                      RELATÓRIO CRAWLER")
    print("=" * 70)
    print(f" - PDFs baixados e associados nesta rodada: {downloaded_count}")
    print(f" - Trabalhos que continuam com falha: {errors_count}")
    print("=" * 70)

if __name__ == "__main__":
    main()
