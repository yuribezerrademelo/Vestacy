# =============================================================================
# main.py — Orquestrador principal da automação Mtrix/QlikView
# =============================================================================
#
# ESTRUTURA DE PASTAS ESPERADA:
#   Automação/
#   ├── run.py                ← execute este
#   ├── .env                  ← credenciais (não commitar)
#   └── files/
#       ├── main.py           ← este arquivo
#       ├── config.py
#       ├── coordinates.py
#       ├── screen_utils.py
#       ├── download_watcher.py
#       └── templates/
#           ├── botao_export.png
#           └── botao_dupla_seta.png
#
# EXECUÇÃO:
#   cd "C:\Users\yurib\Downloads\Automação"
#   python run.py
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
from .screen_utils import wait_for_screen_stable, safe_click, aguardar_elemento_visivel, verificar_elemento_ja_visivel
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


def _bloco_esta_ativo(coords: tuple, raio: int = 20, timeout: float = 10) -> bool:
    """
    Verifica se o bloco foi realmente selecionado checando se a região
    ao redor do clique ficou mais ESCURA (azul/destacada).

    Quando um bloco é selecionado no QlikView, o fundo muda de cinza
    claro para azul escuro. Medimos o brilho médio da região antes e
    depois — se escureceu significativamente, o bloco foi ativado.
    """
    x, y   = coords
    regiao = (x - raio, y - raio, raio * 2, raio * 2)

    # Captura estado atual (deve estar mais escuro/azul se ativo)
    deadline = time.time() + timeout
    while time.time() < deadline:
        frame = _capturar_tela()
        # Recorta a região do bloco
        rx, ry, rw, rh = regiao
        recorte = frame[ry:ry+rh, rx:rx+rw]
        brilho = float(recorte.mean())
        logger.debug(f"Brilho do bloco em {coords}: {brilho:.1f}")

        # Bloco ativo = região mais escura (azul) — brilho < 130 em escala 0-255
        if brilho < 130:
            logger.info(f"✔ Bloco confirmado como ativo (brilho={brilho:.1f}).")
            return True
        time.sleep(0.3)

    logger.warning(f"⚠ Bloco não confirmado como ativo (brilho médio alto = região clara).")
    return False


def selecionar_bloco(nome_bloco: str):
    global _bloco_atual
    if _bloco_atual == nome_bloco:
        logger.info(f"Bloco '{nome_bloco}' já ativo — sem ação.")
        return

    coords = BLOCOS[nome_bloco]

    for tentativa in range(1, 4):
        logger.info(f"Selecionando bloco '{nome_bloco}' (tentativa {tentativa}/3)...")

        # Pequena pausa antes de clicar para garantir que QlikView está pronto
        pausa(1.0)
        safe_click(*coords)
        pausa(1.5)

        # Verifica se o bloco ficou destacado (azul)
        if _bloco_esta_ativo(coords):
            aguardar_tela_estavel()
            _bloco_atual = nome_bloco
            logger.info(f"✔ Bloco '{nome_bloco}' selecionado e confirmado.")
            return

        logger.warning(f"⚠ Bloco '{nome_bloco}' não ficou ativo — tentando novamente...")
        pausa(2.0)

    raise RuntimeError(
        f"Falha ao selecionar bloco '{nome_bloco}' após 3 tentativas.\n"
        f"Verifique as coordenadas em coordinates.py e recalibre se necessário."
    )


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
    visivel_seta = aguardar_elemento_visivel(
        coords        = Coords.BOTAO_DUPLA_SETA,
        template_path = _template_seta,
        timeout       = 60,
        poll          = 0.5,
        confidence    = 0.75,
        raio          = 60        # busca só em ±60px ao redor da coordenada calibrada
    )
    if not visivel_seta:
        logger.warning("⚠ Dupla seta não confirmada pelo template — tentando clicar mesmo assim.")
    else:
        logger.info(f"✔ Dupla seta confirmada. Clicando em coordenada calibrada {Coords.BOTAO_DUPLA_SETA}.")

    logger.info("Clicando na dupla seta (») — transpondo coluna Ano/Mês...")
    # Clica SEMPRE na coordenada calibrada do coordinates.py
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

        # --- Dois caminhos antes de clicar ---
        #
        # Condição 1: Botão JÁ visível antes do filtro atualizar
        #   → aguarda dados da tabela atualizarem + estabilizarem → clica
        #
        # Condição 2: Botão ainda NÃO visível
        #   → aguarda aparecer (até 60s) → clica quando aparecer
        #
        # Em ambos os casos, clica na coordenada calibrada do coordinates.py.

        ja_visivel = verificar_elemento_ja_visivel(
            coords        = coords_export,
            template_path = _template_export,
            confidence    = 0.75,
            raio          = 60,
            tentativas    = 4,
        )

        if ja_visivel:
            logger.info(
                "Botão export já visível — aguardando dados do filtro atualizarem..."
            )
            pausa(PAUSA_POS_BOOKMARK)   # reutiliza o mesmo tempo configurável do config.py
            aguardar_tela_estavel()
            logger.info("✔ Dados atualizados. Pronto para clicar.")
        else:
            logger.info("Botão export não visível — aguardando aparecer...")
            aguardar_elemento_visivel(
                coords        = coords_export,
                template_path = _template_export,
                timeout       = 60,
                poll          = 0.5,
                confidence    = 0.75,
                raio          = 60,
            )

        with DownloadSession(
            bookmark=bookmark,
            timeout=DOWNLOAD_TIMEOUT,
            inicio_timeout=INICIO_DOWNLOAD_TIMEOUT
        ) as session:

            # Clica SEMPRE na coordenada calibrada do coordinates.py
            safe_click(*coords_export)
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

def _recuperar_navegacao():
    """
    Tenta recuperar o estado do QlikView sem fechar o navegador.
    Navega de volta para Gráficos | Relatórios e reseta o bloco ativo.
    Útil quando o QlikView pula uma etapa por lentidão.
    """
    global _bloco_atual
    logger.warning("♻ Recuperando navegação — voltando para Gráficos | Relatórios...")
    _bloco_atual = None  # força re-seleção do bloco no próximo ciclo
    try:
        safe_click(*Coords.QLIKVIEW_CENTER)
        pausa(1)
        sucesso = clicar_e_validar(Coords.ABA_GRAFICOS_RELATORIOS, "Gráficos | Relatórios (recuperação)")
        if sucesso:
            aguardar_tela_estavel()
            logger.info("✔ Navegação recuperada com sucesso.")
            return True
    except Exception as e:
        logger.error(f"❌ Falha ao recuperar navegação: {e}")
    return False


def executar_downloads():
    logger.info("=== ETAPA 4: Iniciando loop de downloads ===")
    arquivos    = []
    MAX_RECOVERY = 2  # tentativas de recuperação por download

    for i, (bloco, bookmark, clicar_seta) in enumerate(DOWNLOADS, start=1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Download {i}/8 | Bloco: {bloco} | Bookmark: {bookmark}")
        logger.info(f"{'='*60}")

        for recovery in range(MAX_RECOVERY + 1):
            try:
                selecionar_bloco(bloco)
                aplicar_bookmark(bookmark)

                if clicar_seta:
                    clicar_dupla_seta()

                arquivo = exportar_excel(bookmark, bloco)
                arquivos.append(arquivo)
                logger.info(f"✅ Download {i}/8 concluído: {arquivo.name}\n")
                break  # sucesso — vai para próximo download

            except Exception as e:
                screenshot = str(_BASE_DIR / f"erro_{i}_{bookmark.replace(' ', '_')}.png")
                pyautogui.screenshot(screenshot)

                if recovery < MAX_RECOVERY:
                    logger.warning(
                        f"⚠ Falha no download {i}/8 ({bookmark}): {e}\n"
                        f"   Tentando recuperar sem fechar o navegador "
                        f"(tentativa {recovery + 1}/{MAX_RECOVERY})..."
                    )
                    if not _recuperar_navegacao():
                        logger.error("Recuperação falhou — encerrando.")
                        raise
                    pausa(3)
                else:
                    logger.error(f"❌ Download {i}/8 falhou após {MAX_RECOVERY} recuperações: {e}")
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

    # Pasta de download do Windows — garante que o Chrome lançado pelo
    # Playwright salva os arquivos na mesma pasta que monitoramos.
    _download_dir = get_download_dir()
    _download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            slow_mo=200,
            args=[
                "--start-maximized",
                f"--download-default-directory={str(_download_dir)}",
                "--no-first-run",
                "--disable-default-apps",
            ]
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