# Scopus Harvester

Pipeline automatizada em Python para extração de metadados de artigos científicos da base **Scopus** (Elsevier).

A planilha de saída é **100% compatível** com as planilhas geradas pelos harvesters da BDTD, SciELO e OpenAlex, permitindo consolidar os resultados de todas essas bases em uma única planilha final para sua revisão sistemática.

---

## Recursos Principais
- **Tratamento Inteligente de Entitlements (Assinatura)**: Se sua chave API ou IP não permitir acesso total (`view=COMPLETE`), o pipeline migra automaticamente para a busca padrão (`view=STANDARD`) e realiza requisições individuais secundárias via API de *Abstract Retrieval* para preencher os resumos de forma incremental.
- **Evita Redundância**: Salva resultados no banco de dados SQLite (`scopus_metadata.db`) de forma incremental, permitindo retomar de onde parou em caso de queda de conexão ou limite de taxa.
- **Exportação Flexível**: Detecta a extensão do arquivo e exporta para Excel (`.xlsx`), CSV (`.csv`) ou JSON (`.json`).

---

## Instalação

Navegue até a pasta e instale as dependências:

```bash
pip install -r requirements.txt
```

---

## Como Usar

### 1. Via Linha de Comando (CLI)

O script lê por padrão o arquivo de configuração `scopus_config.json` se ele existir no mesmo diretório.

```bash
# Executa usando as configurações do scopus_config.json
python scopus_harvester.py

# Sobrescreve as palavras-chave e define um limite de 10 artigos salvos
python scopus_harvester.py --keywords "(\"causal discovery\" OR \"causal inference\")" --limit 10

# Especifica a chave API diretamente no terminal
python scopus_harvester.py --api-key "SUA_API_KEY_AQUI" --limit 5

# Define um atraso maior entre as requisições (ex: 2.0 segundos)
python scopus_harvester.py --delay 2.0
```

### 2. Via API Python (Uso Programático)

Você pode importar a função `run_harvest` diretamente em seus notebooks ou outros scripts:

```python
from scopus_harvester import run_harvest

config = {
    "db_path": "scopus_metadata.db",
    "export_path": "scopus_resultados.xlsx",
    "limit": 50,
    "delay": 1.5,
    "api_key": "SUA_API_KEY_AQUI",
    "view": "COMPLETE",
    "keywords": [
        "\"causal inference\" AND \"regional development\""
    ]
}

success = run_harvest(config)
if success:
    print("Coleta concluída com sucesso!")
```

---

## Arquivo de Configuração (`scopus_config.json`)

Você pode configurar a coleta ajustando os campos no arquivo `scopus_config.json`:

```json
{
    "db_path": "scopus_metadata.db",
    "export_path": "scopus_resultados.xlsx",
    "limit": null,
    "delay": 1.0,
    "api_key": "33698870c47d2706e3a3fc4c03397832",
    "view": "COMPLETE",
    "keywords": [
        "(\"inferência causal\" OR \"causal inference\") AND (\"descoberta causal\" OR \"causal discovery\")"
    ]
}
```

- `db_path`: Caminho do banco de dados SQLite intermediário.
- `export_path`: Caminho final do arquivo exportado (use `.xlsx` para Excel ou `.csv` para CSV).
- `limit`: Limite de artigos a serem salvos por palavra-chave (use `null` para trazer todos os resultados da busca).
- `delay`: Atraso em segundos entre requisições de página para respeitar os limites de taxa da Elsevier.
- `api_key`: Sua chave API Scopus (Elsevier).
- `view`: Escolha de nível de metadados (`COMPLETE` ou `STANDARD`). Deixe `COMPLETE` por padrão (caso falhe com erro HTTP 403 por falta de assinatura de dados completos, o script migra automaticamente para `STANDARD`).

---

## Colunas da Planilha de Saída

As colunas geradas no Excel/CSV final seguem rigorosamente a estrutura abaixo:

| Coluna | Descrição | Compatível? |
| :--- | :--- | :---: |
| **Autores** | Lista de autores separados por ponto e vírgula (ex: `Smith, John; Doe, Jane`). | ✅ |
| **Título** | Título do artigo científico. | ✅ |
| **Ano** | Ano de publicação (extraído de `prism:coverDate`). | ✅ |
| **Tipo de Pesquisa** | Mapeamento adaptado para o português (ex: `Artigo`, `Revisão`, `Artigo de Conferência`, `Livro`). | ✅ |
| **Nome do Orientador** | Sempre exportado como `"Não Informado"` (coluna mantida para compatibilidade com BDTD). | ✅ |
| **Universidade / Editora / Revista** | Nome do periódico, editora ou conferência de publicação (`prism:publicationName`). | ✅ |
| **Resumo** | Resumo em inglês ou português. | ✅ |
| **Link para Download** | Link direto de acesso ao registro na plataforma do Scopus. | ✅ |

---

## Dica Importante sobre Assinatura Scopus
Para que a API da Scopus libere o resumo (`dc:description`) e a lista completa de autores, certifique-se de que:
1. Você está executando este script conectado à **VPN institucional** de sua universidade ou em computadores da rede acadêmica que assina a Scopus.
2. Caso use em uma conexão residencial sem VPN, a API Scopus pode retornar erro 403 na busca `COMPLETE` ou recusar o abstract. O script fará o fallback automático para coletar o máximo de metadados possíveis na busca `STANDARD`, porém a lista de autores poderá ficar resumida ao primeiro autor e resumos específicos de periódicos fechados podem vir marcados como restritos.
