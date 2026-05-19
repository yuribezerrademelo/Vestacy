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
#   cd "C:\Users\yurib\Downloads\Automação\Vestacy"
#   python run.py
#
# DEPENDÊNCIAS:
#   pip install pyautogui opencv-python pillow python-dotenv pytesseract pyperclip mss
# =============================================================================

import time
import logging
import sys
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos base do projeto
# ---------------------------------------------------------------------------
_FILES_DIR = Path(__file__).parent   # Vestacy/files/
_BASE_DIR  = _FILES_DIR.parent       # Vestacy/

import numpy as np
import cv2
import pyautogui
import pyperclip

from .config import (
    USERNAME, PASSWORD, LOGIN_URL, AMBIENTE_NOME,
    DOWNLOADS, WAIT_STABILITY_TIMEOUT, WAIT_STABILITY_INTERVAL,
    WAIT_STABILITY_THRESHOLD, DOWNLOAD_TIMEOUT,
    PAUSA_POS_BOOKMARK, INICIO_DOWNLOAD_TIMEOUT
)
from .screen_utils import (
    wait_for_screen_stable, safe_click,
    verificar_pixel_visivel, aguardar_elemento_por_pixel
)
from .download_watcher import DownloadSession, get_download_dir, _is_temp, snapshot_dir
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
# Etapas 1, 2 e 3: Abrir Chrome real e fazer login via PyAutoGUI
# ---------------------------------------------------------------------------

def _digitar(texto: str):
    """Digita texto via clipboard — funciona com qualquer layout de teclado."""
    pyperclip.copy(texto)
    pyautogui.hotkey("ctrl", "v")


def abrir_chrome_e_login():
    """
    Abre o Chrome instalado no PC (perfil real do usuário) e faz login.
    O Chrome real usa a pasta Downloads configurada pelo usuário.
    """
    logger.info("=== ETAPA 1: Abrindo Chrome ===")
    subprocess.Popen(
        f'start chrome --start-maximized "{LOGIN_URL}"',
        shell=True
    )
    pausa(4)
    aguardar_tela_estavel()

    logger.info("=== ETAPA 2: Login ===")
    # Credenciais já salvas no Chrome — apenas clica em Entrar
    safe_click(*Coords.LOGIN_BOTAO_ENTRAR)
    logger.info("Botão Entrar clicado — aguardando seleção de ambiente...")
    aguardar_tela_estavel(timeout=20)
    pausa(2)

    logger.info("=== ETAPA 3: Selecionar ambiente ===")
    safe_click(*Coords.LOGIN_AMBIENTE)
    logger.info(f"Ambiente '{AMBIENTE_NOME}' selecionado.")
    pausa(6)


# ---------------------------------------------------------------------------
# Etapa 4: QlikView — focar janela e navegar
# ---------------------------------------------------------------------------

def focar_qlikview_e_navegar():
    logger.info("=== ETAPA 4: Navegando no QlikView ===")
    pausa(2)

    safe_click(*Coords.QLIKVIEW_CENTER)
    aguardar_tela_estavel()

    sucesso = clicar_e_validar(Coords.ABA_GRAFICOS_RELATORIOS, "Gráficos | Relatórios")
    if not sucesso:
        raise RuntimeError("Não foi possível navegar para Gráficos | Relatórios.")
    aguardar_tela_estavel()


# ---------------------------------------------------------------------------
# Etapa 5: Selecionar bloco de filtro
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
    Verifica se o bloco foi selecionado checando se a região ficou mais
    escura (azul). Bloco ativo = brilho < 130.
    """
    x, y   = coords
    regiao = (x - raio, y - raio, raio * 2, raio * 2)
    deadline = time.time() + timeout

    while time.time() < deadline:
        frame   = _capturar_tela()
        rx, ry, rw, rh = regiao
        recorte = frame[ry:ry+rh, rx:rx+rw]
        brilho  = float(recorte.mean())
        logger.debug(f"Brilho do bloco em {coords}: {brilho:.1f}")

        if brilho < 130:
            logger.info(f"✔ Bloco confirmado como ativo (brilho={brilho:.1f}).")
            return True
        time.sleep(0.3)

    logger.warning("⚠ Bloco não confirmado como ativo (brilho alto = região clara).")
    return False


def selecionar_bloco(nome_bloco: str):
    global _bloco_atual
    if _bloco_atual == nome_bloco:
        logger.info(f"Bloco '{nome_bloco}' já ativo — sem ação.")
        return

    coords = BLOCOS[nome_bloco]

    for tentativa in range(1, 4):
        logger.info(f"Selecionando bloco '{nome_bloco}' (tentativa {tentativa}/3)...")
        pausa(1.0)
        safe_click(*coords)
        pausa(1.5)

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
# Etapa 6: Aplicar bookmark
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

    aguardar_tela_estavel()
    logger.info(f"Aguardando {PAUSA_POS_BOOKMARK}s para dados da tabela carregarem...")
    pausa(PAUSA_POS_BOOKMARK)
    aguardar_tela_estavel()
    logger.info(f"✔ Bookmark '{nome_bookmark}' aplicado e tabela pronta.")


# ---------------------------------------------------------------------------
# Dupla seta (»)
# ---------------------------------------------------------------------------

def clicar_dupla_seta():
    """
    Aguarda a dupla seta (») ficar visível por verificação de pixel
    e clica na coordenada calibrada.
    """
    logger.info("Aguardando dupla seta (») ficar visível...")

    visivel = verificar_pixel_visivel(
        coords         = Coords.BOTAO_DUPLA_SETA,
        raio           = 15,
        brightness_max = 210,
        tentativas     = 4,
    )
    if not visivel:
        logger.info("Dupla seta não visível — aguardando aparecer...")
        aguardar_elemento_por_pixel(
            coords         = Coords.BOTAO_DUPLA_SETA,
            raio           = 15,
            brightness_max = 210,
            timeout        = 60,
        )

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
    Exporta para Excel com retry automático e verificação de pixel.

    Condição 1: Botão JÁ visível → aguarda dados atualizarem → clica
    Condição 2: Botão NÃO visível → aguarda aparecer → clica
    """
    coords_export = BOTAO_EXPORT_POR_BLOCO[bloco]()

    for tentativa in range(1, MAX_TENTATIVAS_EXPORT + 1):
        logger.info(f"Export tentativa {tentativa}/{MAX_TENTATIVAS_EXPORT} | '{bookmark}'")

        ja_visivel = verificar_pixel_visivel(
            coords         = coords_export,
            raio           = 15,
            brightness_max = 210,
            tentativas     = 4,
        )

        if ja_visivel:
            logger.info("Botão export já visível — aguardando dados do filtro atualizarem...")
            pausa(PAUSA_POS_BOOKMARK)
            aguardar_tela_estavel()
            logger.info("✔ Dados atualizados. Pronto para clicar.")
        else:
            logger.info("Botão export ainda não visível — aguardando aparecer...")
            aguardar_elemento_por_pixel(
                coords         = coords_export,
                raio           = 15,
                brightness_max = 210,
                timeout        = 60,
                poll           = 0.5,
            )

        with DownloadSession(
            bookmark=bookmark,
            timeout=DOWNLOAD_TIMEOUT,
            inicio_timeout=INICIO_DOWNLOAD_TIMEOUT
        ) as session:

            safe_click(*coords_export)
            pausa(2)

            if _dialogo_press_here_visivel():
                logger.warning("Diálogo 'press here' → clicando no link...")
                safe_click(*Coords.LINK_PRESS_HERE)
                pausa(3)
            else:
                # Monitora por até 20s se o diálogo fechar sem iniciar download.
                # Quando o diálogo fecha, a tela muda significativamente.
                # Se isso acontecer sem arquivo novo → retenta o clique.
                ref_dialogo = _capturar_tela()
                for _ in range(20):
                    time.sleep(1)
                    try:
                        atuais  = set(session.download_dir.iterdir())
                        tem_tmp = any(_is_temp(f) for f in atuais if f.is_file())
                        novos   = {f for f in atuais if f.is_file() and not _is_temp(f)} - session._snapshot
                        if tem_tmp or novos:
                            logger.info("Download iniciado durante monitoramento do diálogo.")
                            break
                    except Exception:
                        pass

                    atual = _capturar_tela()
                    if _similaridade(ref_dialogo, atual) < 0.96:
                        logger.warning(
                            "Diálogo fechou sem download detectado — "
                            "retentando o clique no export..."
                        )
                        break

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
# Loop principal de downloads
# ---------------------------------------------------------------------------

def _recuperar_navegacao():
    """Volta para Gráficos | Relatórios sem fechar o navegador."""
    global _bloco_atual
    logger.warning("Recuperando navegacao — voltando para Graficos | Relatorios...")
    _bloco_atual = None
    try:
        safe_click(*Coords.QLIKVIEW_CENTER)
        pausa(1)
        sucesso = clicar_e_validar(
            Coords.ABA_GRAFICOS_RELATORIOS, "Graficos | Relatorios (recuperacao)"
        )
        if sucesso:
            aguardar_tela_estavel()
            logger.info("✔ Navegacao recuperada com sucesso.")
            return True
    except Exception as e:
        logger.error(f"❌ Falha ao recuperar navegacao: {e}")
    return False


def executar_downloads():
    logger.info("=== ETAPA 5: Iniciando loop de downloads ===")
    arquivos    = []
    MAX_RECOVERY = 2

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
                break

            except Exception as e:
                screenshot = str(_BASE_DIR / f"erro_{i}_{bookmark.replace(' ', '_')}.png")
                pyautogui.screenshot(screenshot)

                if recovery < MAX_RECOVERY:
                    logger.warning(
                        f"⚠ Falha no download {i}/8 ({bookmark}): {e}\n"
                        f"   Recuperando (tentativa {recovery + 1}/{MAX_RECOVERY})..."
                    )
                    if not _recuperar_navegacao():
                        logger.error("Recuperacao falhou — encerrando.")
                        raise
                    pausa(3)
                else:
                    logger.error(f"❌ Download {i}/8 falhou após {MAX_RECOVERY} recuperações: {e}")
                    logger.error(f"Screenshot: {screenshot}")
                    raise

    return arquivos


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    logger.info("╔══════════════════════════════════════╗")
    logger.info("║   Automacao Mtrix - Iniciando        ║")
    logger.info("╚══════════════════════════════════════╝")

    try:
        abrir_chrome_e_login()
        focar_qlikview_e_navegar()
        arquivos = executar_downloads()

        logger.info("\n╔══════════════════════════════════════╗")
        logger.info("║   Automacao concluida com sucesso!   ║")
        logger.info("╚══════════════════════════════════════╝")
        logger.info(f"Total: {len(arquivos)} arquivo(s):")
        for f in arquivos:
            logger.info(f"  -> {f.name}")

    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()