# =============================================================================
# config.py — Configurações centrais da automação
# =============================================================================
# ⚠️  Credenciais ficam no arquivo .env na pasta Automação/
#     MTRIX_USER=seu_usuario
#     MTRIX_PASS=sua_senha
# =============================================================================

import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env da pasta Automação/ (pai de files/)
_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# --- Credenciais ---
USERNAME = os.getenv("MTRIX_USER")
PASSWORD = os.getenv("MTRIX_PASS")

if not USERNAME or not PASSWORD:
    raise EnvironmentError(
        f"Credenciais não encontradas.\n"
        f"Arquivo .env procurado em: {_ENV_PATH}\n"
        f"Verifique se o arquivo existe e contém:\n"
        f"  MTRIX_USER=seu_usuario\n"
        f"  MTRIX_PASS=sua_senha"
    )

# --- URLs ---
LOGIN_URL = "https://login.mtrix.com.br"

# --- Ambiente a selecionar após login ---
AMBIENTE_NOME = "VESTACY EH - CENSOR"

# --- Pasta de downloads ---
# None = detecta automaticamente (ver lógica abaixo)
# Para forçar uma pasta específica, defina o caminho completo:
# DOWNLOAD_DIR = r"C:\Users\yurib\Downloads"
DOWNLOAD_DIR = None

# --- Resolução do monitor ---
SCREEN_WIDTH  = 2560
SCREEN_HEIGHT = 1440

# --- Estabilidade de tela ---
WAIT_STABILITY_TIMEOUT   = 60
WAIT_STABILITY_INTERVAL  = 0.5
WAIT_STABILITY_THRESHOLD = 0.990

# --- Timeout total do download (segundos) ---
DOWNLOAD_TIMEOUT = 1800  # 30 minutos

# --- Timeout para DETECTAR O INÍCIO do download (segundos) ---
# O QlikView pode ficar minutos com o diálogo aberto antes do arquivo aparecer.
INICIO_DOWNLOAD_TIMEOUT = 45   # 45s — se o dialogo fechou sem download, retenta rapido

# --- Pausa após aplicar bookmark (segundos) ---
# Garante que os dados da tabela carregaram antes de tentar o export.
PAUSA_POS_BOOKMARK = 5

# --- Sequência de downloads ---
# Formato: (bloco_filtro, nome_bookmark, clicar_dupla_seta)
DOWNLOADS = [
    ("PDV",                    "ST - Grit",             False),
    ("PDV",                    "ST - Grit - Mateus",    False),
    ("Tempo",                  "CATEGORIA AR",           False),
    ("Tempo",                  "CATEGORIA AR - MATEUS",  False),
    ("Agente de Distribuição", "ST - DBs",              False),
    ("Agente de Distribuição", "ST - DBs - Mateus",     False),
    ("Produto",                "Produto",               True),
    ("Produto",                "Produto - Mateus",      False),
]