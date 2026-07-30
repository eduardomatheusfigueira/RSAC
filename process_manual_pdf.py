#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
process_manual_pdf.py: Identifies the latest PDF downloaded in the Downloads folder,
moves it to the systematic review folder under the correct ID and clean title,
extracts its text, and updates the JSON file.
"""

import os
import json
import re
import glob
import shutil
import pypdf
import sys

JSON_PATH = os.path.join("Revisão teste", "triagem2_sessao.json")
OUTPUT_PDF_DIR = os.path.join("Revisão teste", "pdfs")
DOWNLOADS_DIR = os.path.expanduser("~/Downloads")

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

def get_latest_downloaded_pdf():
    pdf_pattern = os.path.join(DOWNLOADS_DIR, "*.pdf")
    files = glob.glob(pdf_pattern)
    if not files:
        return None
    # Sort by modification time, newest first
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def associate_pdf_to_paper(paper_id):
    print(f"Buscando último PDF baixado em: {DOWNLOADS_DIR}")
    latest_pdf = get_latest_downloaded_pdf()
    if not latest_pdf:
        print("[ERRO] Nenhum PDF encontrado na pasta Downloads.")
        return False
        
    print(f"Último PDF encontrado: {latest_pdf}")
    print(f"Confirmar associação com o ID {paper_id}...")
    
    if not os.path.exists(JSON_PATH):
        print(f"[ERRO] Arquivo de sessão não encontrado em: {JSON_PATH}")
        return False
        
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            session = json.load(f)
    except Exception as e:
        print(f"[ERRO] Falha ao ler arquivo JSON: {e}")
        return False
        
    trabalhos = session.get('trabalhos', [])
    paper = None
    for t in trabalhos:
        if str(t.get('id')) == str(paper_id):
            paper = t
            break
            
    if not paper:
        print(f"[ERRO] Trabalho com ID {paper_id} não encontrado no JSON.")
        return False
        
    title = paper.get('Título', 'Sem título')
    print(f"Trabalho encontrado: {title}")
    
    # Destination path
    safe_title = clean_filename(title)
    dest_filename = f"ID_{paper_id}_{safe_title}.pdf"
    dest_path = os.path.join(OUTPUT_PDF_DIR, dest_filename).replace("\\", "/")
    
    os.makedirs(OUTPUT_PDF_DIR, exist_ok=True)
    
    try:
        shutil.move(latest_pdf, dest_path)
        print(f"[OK] Arquivo movido com sucesso para: {dest_path}")
        
        # Extract text
        print("Extraindo texto do PDF...")
        text = extract_text_from_pdf(dest_path)
        
        # Update metadata
        if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
            paper['Extracao'] = {}
        ext = paper['Extracao']
        ext['status_pdf'] = 'Baixado'
        ext['caminho_pdf'] = dest_path
        ext['texto_extraido'] = text
        if 'erro_detalhe' in ext:
            del ext['erro_detalhe']
            
        # Save JSON
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=4)
        print("[SUCESSO] JSON de sessão atualizado!")
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao processar arquivo: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python process_manual_pdf.py <ID_DO_TRABALHO>")
        sys.exit(1)
    target_id = sys.argv[1]
    associate_pdf_to_paper(target_id)
