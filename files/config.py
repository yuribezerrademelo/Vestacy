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
PAUSA_POS_BOOKMARK = 8

# --- Sequência de downloads ---
# Formato: (bloco_filtro, nome_bookmark, clicar_dupla_seta)
# Sequencia de downloads.
# ST - Grit usa fluxo especial via "Relatorios Personalizados" (ver main.py).
# Os demais seguem o fluxo padrao de bloco → bookmark → export.
DOWNLOADS = [
    ("Relatorios Personalizados", "ST - Grit",                  False),
    ("Tempo",                     "CATEGORIA AR",                False),
    ("Agente de Distribuição",    "ST - DBs",                    False),
    ("Agente de Distribuição",    "Sell Out - DB's - Com CPF",  False),
    ("Produto",                   "Produto",                     True),
]
# =============================================================================
# DROPDOWN DE BOOKMARKS — configuração para clique calculado
# =============================================================================
# Manter BOOKMARK_ORDER atualizado quando adicionar ou remover bookmarks.
# A ordem deve ser EXATAMENTE a mesma exibida no dropdown (alfabética).
# Para atualizar: basta inserir/remover o nome na posição correta.
#
# Parâmetros de posição (BOOKMARK_Y_FIRST e BOOKMARK_ITEM_HEIGHT) só precisam
# ser recalibrados se o QlikView mudar de layout ou resolução de tela.
# =============================================================================

# BOOKMARK_ORDER — lista EXATA do dropdown, na ordem em que aparece (sem "Select Bookmark").
# Navegacao End+Up calcula a posicao de cada item automaticamente.
# Atualizar quando adicionar/remover bookmarks no QlikView.
BOOKMARK_ORDER = [
    "CATEGORIA AR",               # 0
    "OnePage - Aba PDV",          # 1
    "OnePage - Aba PDV - Mateus", # 2
    "Produto",                    # 3
    "Sell Out - DB's - Com CPF",  # 4
    "ST - DBs",                   # 5
    "ST - Grit",                  # 6
]

# Y da primeira linha de itens do dropdown (pixels da tela)
# Calibrado com CATEGORIA AR selecionado visualmente
BOOKMARK_Y_FIRST = 143

# Altura de cada item em pixels (espaçamento entre linhas)
BOOKMARK_ITEM_HEIGHT = 24.5

# X fixo do centro da coluna de itens do dropdown
BOOKMARK_X = 609