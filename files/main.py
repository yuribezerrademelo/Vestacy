# =============================================================================
# main.py — Orquestrador principal da automação Mtrix/QlikView
# =============================================================================
#
# ESTRUTURA DE PASTAS ESPERADA:
#   Automação/
#   ├── main.py               ← este arquivo
#   └── files/
#       ├── config.py
#       ├── coordinates.py
#       ├── screen_utils.py
#       └── download_watcher.py
#
# EXECUÇÃO:
#   cd "C:\Users\yurib\Downloads\Automação"
#   python main.py
#
# DEPENDÊNCIAS:
#   pip install playwright pyautogui opencv-python pillow python-dotenv pytesseract
#   playwright install chromium
# =============================================================================

import time
import logging
import sys
import ctypes
import ctypes.wintypes
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos base do projeto
# ---------------------------------------------------------------------------
_FILES_DIR = Path(__file__).parent          # Automação/files/
_BASE_DIR  = _FILES_DIR.parent              # Automação/
# (sys.path não é necessário com importações relativas)

import numpy as np
import cv2
import pyautogui
from playwright.sync_api import sync_playwright

from .config import (
    USERNAME, PASSWORD, LOGIN_URL, AMBIENTE_NOME,
    DOWNLOADS, WAIT_STABILITY_TIMEOUT, WAIT_STABILITY_INTERVAL,
    WAIT_STABILITY_THRESHOLD, DOWNLOAD_TIMEOUT, SCREEN_WIDTH, SCREEN_HEIGHT,
    PAUSA_POS_BOOKMARK, INICIO_DOWNLOAD_TIMEOUT
)
from .screen_utils import wait_for_screen_stable, safe_click, aguardar_elemento_visivel
from .download_watcher import DownloadSession, get_download_dir
from .coordinates import Coords

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_BASE_DIR / "automacao.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utilitários de imagem
# ---------------------------------------------------------------------------

def _capturar_tela() -> np.ndarray:
    shot = pyautogui.screenshot()
    arr  = np.array(shot)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def _similaridade(a: np.ndarray, b: np.ndarray) -> float:
    resultado = cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)
    return float(resultado[0][0])


# ---------------------------------------------------------------------------
# Helpers gerais
# ---------------------------------------------------------------------------

def pausa(s: float = 1.0):
    time.sleep(s)


def aguardar_tela_estavel(timeout: float = None):
    wait_for_screen_stable(
        timeout   = timeout or WAIT_STABILITY_TIMEOUT,
        interval  = WAIT_STABILITY_INTERVAL,
        threshold = WAIT_STABILITY_THRESHOLD
    )


def clicar_e_validar(coordenada: tuple, descricao: str, tentativas: int = 3) -> bool:
    """
    Clica em uma coordenada e valida que a tela MUDOU após o clique.
    Repete até 'tentativas' vezes se a tela não reagir.

    NÃO usar para o botão de export — o diálogo flutuante do QlikView
    não altera o fundo, o que faria a validação falhar incorretamente.
    """
    for tentativa in range(1, tentativas + 1):
        logger.info(f"Clicando em '{descricao}' (tentativa {tentativa}/{tentativas})")
        antes = _capturar_tela()
        safe_click(*coordenada)

        deadline = time.time() + 15
        reagiu   = False
        while time.time() < deadline:
            time.sleep(0.4)
            depois = _capturar_tela()
            if _similaridade(antes, depois) < 0.990:
                reagiu = True
                break

        if reagiu:
            logger.info(f"✔ '{descricao}' respondeu.")
            return True

        logger.warning(f"⚠ '{descricao}' não reagiu, tentando novamente...")
        pausa(1)

    logger.error(f"❌ '{descricao}' não respondeu após {tentativas} tentativas.")
    return False


# ---------------------------------------------------------------------------
# Detecção do diálogo "press here"
# ---------------------------------------------------------------------------

def _dialogo_press_here_visivel() -> bool:
    """
    Detecta o diálogo 'opened in another window / press here'.
    Tenta OCR primeiro, depois template matching como fallback.
    """
    try:
        import pytesseract
        shot  = pyautogui.screenshot()
        texto = pytesseract.image_to_string(shot).lower()
        if "press here" in texto or "another window" in texto:
            logger.info("Diálogo 'press here' detectado via OCR.")
            return True
    except Exception:
        pass

    template_path = _FILES_DIR / "templates" / "press_here.png"
    if template_path.exists():
        try:
            template  = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
            tela      = _capturar_tela()
            resultado = cv2.matchTemplate(tela, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(resultado)
            if max_val >= 0.85:
                logger.info(f"Diálogo 'press here' detectado via template (score={max_val:.2f}).")
                return True
        except Exception as e:
            logger.debug(f"Template matching falhou: {e}")

    return False


# ---------------------------------------------------------------------------
# Etapas 1 & 2: Login via Playwright
# ---------------------------------------------------------------------------

def fazer_login(page):
    logger.info("=== ETAPA 1: Login ===")
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")

    inputs = page.locator("input")
    inputs.nth(0).fill(USERNAME)
    inputs.nth(1).fill(PASSWORD)
    page.locator("button, input[type='submit']").filter(has_text="Entrar").click()
    page.wait_for_load_state("networkidle")
    logger.info("Login realizado.")

    logger.info("=== ETAPA 2: Selecionar ambiente ===")
    page.wait_for_selector(f"text={AMBIENTE_NOME}", timeout=15000)
    page.click(f"text={AMBIENTE_NOME}")
    logger.info(f"Ambiente '{AMBIENTE_NOME}' selecionado.")
    pausa(6)


# ---------------------------------------------------------------------------
# Etapa 3: QlikView — validar janela e navegar
# ---------------------------------------------------------------------------

def _garantir_janela_maximizada():
    TOLERANCIA = 50
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        largura = rect.right  - rect.left
        altura  = rect.bottom - rect.top
        logger.info(f"Janela ativa: {largura}x{altura} | Esperado: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")

        if largura >= SCREEN_WIDTH - TOLERANCIA and altura >= SCREEN_HEIGHT - TOLERANCIA:
            logger.info("Janela já maximizada.")
        else:
            logger.info("Janela não maximizada — aplicando Win+Up...")
            pyautogui.hotkey("win", "up")
            pausa(1)
    except Exception as e:
        logger.warning(f"Não foi possível verificar janela ({e}) — maximizando por precaução.")
        pyautogui.hotkey("win", "up")
        pausa(1)


def focar_qlikview_e_navegar():
    logger.info("=== ETAPA 3: Navegando no QlikView ===")
    pausa(2)
    _garantir_janela_maximizada()

    safe_click(*Coords.QLIKVIEW_CENTER)
    aguardar_tela_estavel()

    sucesso = clicar_e_validar(Coords.ABA_GRAFICOS_RELATORIOS, "Gráficos | Relatórios")
    if not sucesso:
        raise RuntimeError("Não foi possível navegar para Gráficos | Relatórios.")
    aguardar_tela_estavel()


# ---------------------------------------------------------------------------
# Etapa 4: Selecionar bloco de filtro
# ---------------------------------------------------------------------------

BLOCOS = {
    "PDV":                    Coords.BLOCO_PDV,
    "Tempo":                  Coords.BLOCO_TEMPO,
    "Agente de Distribuição": Coords.BLOCO_AGENTE_DISTRIB,
    "Produto":                Coords.BLOCO_PRODUTO,
}

_bloco_atual = None


def selecionar_bloco(nome_bloco: str):
    global _bloco_atual
    if _bloco_atual == nome_bloco:
        logger.info(f"Bloco '{nome_bloco}' já ativo — sem ação.")
        return

    sucesso = clicar_e_validar(BLOCOS[nome_bloco], f"Bloco '{nome_bloco}'")
    if not sucesso:
        raise RuntimeError(f"Falha ao selecionar bloco '{nome_bloco}'.")

    aguardar_tela_estavel()
    _bloco_atual = nome_bloco
    logger.info(f"✔ Bloco '{nome_bloco}' selecionado.")


# ---------------------------------------------------------------------------
# Etapa 5: Aplicar bookmark
# ---------------------------------------------------------------------------

def aplicar_bookmark(nome_bookmark: str):
    logger.info(f"Aplicando bookmark: '{nome_bookmark}'")

    sucesso = clicar_e_validar(Coords.DROPDOWN_BOOKMARK, "Dropdown Bookmark")
    if not sucesso:
        raise RuntimeError("Falha ao abrir dropdown de bookmarks.")
    pausa(1.5)

    bookmark_coords = Coords.BOOKMARKS.get(nome_bookmark)
    if bookmark_coords is None:
        raise ValueError(f"Bookmark '{nome_bookmark}' não mapeado em coordinates.py.")

    sucesso = clicar_e_validar(bookmark_coords, f"Bookmark '{nome_bookmark}'")
    if not sucesso:
        raise RuntimeError(f"Falha ao selecionar bookmark '{nome_bookmark}'.")

    # Primeira espera: layout termina de renderizar
    aguardar_tela_estavel()

    # Segunda espera: dados da tabela terminam de carregar
    # O QlikView finaliza o layout antes dos dados — essa pausa garante
    # que o botão de export está ativo quando o script for clicar.
    logger.info(f"Aguardando {PAUSA_POS_BOOKMARK}s para dados da tabela carregarem...")
    pausa(PAUSA_POS_BOOKMARK)
    aguardar_tela_estavel()

    logger.info(f"✔ Bookmark '{nome_bookmark}' aplicado e tabela pronta.")


# ---------------------------------------------------------------------------
# Dupla seta (»)
# ---------------------------------------------------------------------------

def clicar_dupla_seta():
    logger.info("Aguardando dupla seta (») ficar visível...")
    _template_seta = str(_FILES_DIR / "templates" / "botao_dupla_seta.png")
    visivel = aguardar_elemento_visivel(
        coords        = Coords.BOTAO_DUPLA_SETA,
        template_path = _template_seta,
        timeout       = 60,
        poll          = 0.5,
        confidence    = 0.70,
    )
    if not visivel:
        logger.warning("⚠ Dupla seta não detectada via template — tentando clicar mesmo assim.")

    logger.info("Clicando na dupla seta (») — transpondo coluna Ano/Mês...")
    sucesso = clicar_e_validar(Coords.BOTAO_DUPLA_SETA, "Dupla seta (»)")
    if not sucesso:
        raise RuntimeError("Falha ao clicar na dupla seta (»).")
    aguardar_tela_estavel()
    logger.info("✔ Coluna Ano/Mês transposta para vertical.")


# ---------------------------------------------------------------------------
# Export Excel com retry automático
# ---------------------------------------------------------------------------

BOTAO_EXPORT_POR_BLOCO = {
    "PDV":                    lambda: Coords.EXPORT_PDV,
    "Produto":                lambda: Coords.EXPORT_PRODUTO,
    "Tempo":                  lambda: Coords.EXPORT_TEMPO_AGENTE,
    "Agente de Distribuição": lambda: Coords.EXPORT_TEMPO_AGENTE,
}

MAX_TENTATIVAS_EXPORT = 3


def exportar_excel(bookmark: str, bloco: str) -> Path:
    """
    Exporta para Excel com retry automático.

    O QlikView pode demorar bastante para iniciar o download após o clique —
    o diálogo de loading fica aberto por minutos antes do arquivo aparecer.
    INICIO_DOWNLOAD_TIMEOUT (config.py) controla esse prazo de espera.

    Cenários tratados:
      1. Normal: clica → loading → arquivo aparece na pasta.
      2. Loading fecha sem baixar: detectado pelo timeout → retry.
      3. Diálogo "press here": detectado por OCR → clica no link.
    """
    coords_export = BOTAO_EXPORT_POR_BLOCO[bloco]()

    # Caminho do template do botão (opcional — ver screen_utils.aguardar_botao_export)
    _template_export = str(_FILES_DIR / "templates" / "botao_export.png")

    for tentativa in range(1, MAX_TENTATIVAS_EXPORT + 1):
        logger.info(f"Export tentativa {tentativa}/{MAX_TENTATIVAS_EXPORT} | '{bookmark}'")

        # Aguarda o botão de export aparecer ANTES de clicar
        visivel = aguardar_elemento_visivel(
            coords        = coords_export,
            template_path = _template_export,
            timeout       = 60,
            poll          = 0.5,
            confidence    = 0.70,
            raio          = 25
        )
        if not visivel:
            logger.warning("⚠ Botão de export não detectado — tentando clicar mesmo assim.")

        with DownloadSession(
            bookmark=bookmark,
            timeout=DOWNLOAD_TIMEOUT,
            inicio_timeout=INICIO_DOWNLOAD_TIMEOUT
        ) as session:

            safe_click(*coords_export)
            logger.info(f"Clicando em {coords_export}")
            pausa(2)

            if _dialogo_press_here_visivel():
                logger.warning("Diálogo 'press here' → clicando no link...")
                safe_click(*Coords.LINK_PRESS_HERE)
                pausa(3)

        if session.iniciou and session.arquivo_final:
            logger.info(f"✅ '{session.arquivo_final.name}' baixado e renomeado.")
            return session.arquivo_final

        logger.warning(
            f"⚠ Download não iniciou na tentativa {tentativa}. "
            f"{'Tentando novamente...' if tentativa < MAX_TENTATIVAS_EXPORT else 'Tentativas esgotadas.'}"
        )
        pausa(3)

    raise RuntimeError(
        f"Download falhou após {MAX_TENTATIVAS_EXPORT} tentativas para '{bookmark}'."
    )


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def executar_downloads():
    logger.info("=== ETAPA 4: Iniciando loop de downloads ===")
    arquivos = []

    for i, (bloco, bookmark, clicar_seta) in enumerate(DOWNLOADS, start=1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Download {i}/8 | Bloco: {bloco} | Bookmark: {bookmark}")
        logger.info(f"{'='*60}")

        try:
            selecionar_bloco(bloco)
            aplicar_bookmark(bookmark)

            if clicar_seta:
                clicar_dupla_seta()

            arquivo = exportar_excel(bookmark, bloco)
            arquivos.append(arquivo)
            logger.info(f"✅ Download {i}/8 concluído: {arquivo.name}\n")

        except Exception as e:
            logger.error(f"❌ Erro no download {i}/8 ({bookmark}): {e}")
            screenshot = str(_BASE_DIR / f"erro_{i}_{bookmark.replace(' ', '_')}.png")
            pyautogui.screenshot(screenshot)
            logger.error(f"Screenshot salvo: {screenshot}")
            raise

    return arquivos


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    logger.info("╔══════════════════════════════════════╗")
    logger.info("║   Automação Mtrix — Iniciando        ║")
    logger.info("╚══════════════════════════════════════╝")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            slow_mo=200,
            args=["--start-maximized"]
        )
        context = browser.new_context(no_viewport=True)
        page    = context.new_page()

        try:
            fazer_login(page)
            focar_qlikview_e_navegar()
            arquivos = executar_downloads()

            logger.info("\n╔══════════════════════════════════════╗")
            logger.info("║   Automação concluída com sucesso!   ║")
            logger.info("╚══════════════════════════════════════╝")
            logger.info(f"Total: {len(arquivos)} arquivo(s):")
            for f in arquivos:
                logger.info(f"  → {f.name}")

        except Exception as e:
            logger.critical(f"Erro fatal: {e}", exc_info=True)
            sys.exit(1)

        finally:
            pausa(2)
            browser.close()


if __name__ == "__main__":
    main()