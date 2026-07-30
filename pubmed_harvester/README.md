# PubMed Harvester

Pipeline automatizada em Python para extração de metadados de artigos científicos da base de dados **PubMed (MEDLINE)** da NCBI via API E-utilities.

A planilha de saída é **100% compatível** com as planilhas geradas pelos harvesters da BDTD, SciELO, OpenAlex e Scopus, permitindo consolidar os resultados de todas essas bases em uma única planilha final para sua revisão sistemática.

---

## Como Usar

### 1. Via Linha de Comando (CLI)

O script lê por padrão o arquivo de configuração `pubmed_config.json` se ele existir no mesmo diretório.

```bash
# Executa usando as configurações do pubmed_config.json
python pubmed_harvester.py

# Sobrescreve as palavras-chave e define um limite de 10 artigos salvos
python pubmed_harvester.py --keywords "(\"causal discovery\" OR \"causal inference\")" --limit 10

# Especifica a chave API NCBI diretamente no terminal (para aumentar a taxa de limites)
python pubmed_harvester.py --api-key "SUA_NCBI_API_KEY_AQUI" --limit 5
```

### 2. Configurações (`pubmed_config.json`)

* `db_path`: Caminho do banco de dados SQLite intermediário.
* `export_path`: Planilha final de saída (Excel `.xlsx` ou CSV `.csv`).
* `limit`: Limite de artigos por palavra-chave (use `null` para recuperar todos).
* `delay`: Tempo em segundos entre as requisições (padrão `0.35` segundos).
* `api_key`: Sua chave de API do NCBI (opcional).
* `keywords`: Termos de busca.
