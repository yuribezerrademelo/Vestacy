# =============================================================================
# main.py — Orquestrador principal da automação Mtrix/QlikView
# =============================================================================
#
# ESTRUTURA DE PASTAS:
#   Vestacy/
#   ├── run.py
#   ├── .env
#   └── files/
#       ├── main.py
#       ├── config.py
#       ├── coordinates.py
#       ├── screen_utils.py
#       ├── download_watcher.py
#       └── templates/
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

_FILES_DIR = Path(__file__).parent   # Vestacy/files/
_BASE_DIR  = _FILES_DIR.parent       # Vestacy/

import numpy as np
import cv2
import pyautogui
import pyperclip
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

from .config import (
    USERNAME, PASSWORD, LOGIN_URL, AMBIENTE_NOME,
    DOWNLOADS, WAIT_STABILITY_TIMEOUT, WAIT_STABILITY_INTERVAL,
    WAIT_STABILITY_THRESHOLD, DOWNLOAD_TIMEOUT,
    PAUSA_POS_BOOKMARK, INICIO_DOWNLOAD_TIMEOUT
)
from .screen_utils import (
    wait_for_screen_stable, safe_click,
    verificar_pixel_visivel, aguardar_elemento_por_pixel,
    clicar_bookmark_por_nome
)
from .download_watcher import (
    get_download_dir, snapshot_dir, _is_temp, renomear_arquivo
)
from .coordinates import Coords
from files.tratar_bases_mtrix import main as tratar_bases
from files.powerbi_download import main as baixar_powerbi
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

        logger.warning(f"⚠ '{descricao}' nao reagiu, tentando novamente...")
        pausa(1)

    logger.error(f"❌ '{descricao}' nao respondeu apos {tentativas} tentativas.")
    return False




# ---------------------------------------------------------------------------
# Login via Chrome real
# ---------------------------------------------------------------------------

def _digitar(texto: str):
    pyperclip.copy(texto)
    pyautogui.hotkey("ctrl", "v")


def abrir_chrome_e_login():
    logger.info("=== ETAPA 1: Abrindo Chrome ===")
    subprocess.Popen(
        f'start chrome --start-maximized "{LOGIN_URL}"',
        shell=True
    )
    pausa(4)
    aguardar_tela_estavel()

    logger.info("=== ETAPA 2: Login ===")
    # Credenciais ja salvas no Chrome — apenas clica em Entrar
    safe_click(*Coords.LOGIN_BOTAO_ENTRAR)
    logger.info("Botao Entrar clicado — aguardando selecao de ambiente...")
    aguardar_tela_estavel(timeout=20)
    pausa(4)

    logger.info("=== ETAPA 3: Selecionar ambiente ===")
    safe_click(*Coords.LOGIN_AMBIENTE)
    logger.info(f"Ambiente '{AMBIENTE_NOME}' selecionado.")
    pausa(6)


# ---------------------------------------------------------------------------
# Navegacao no QlikView
# ---------------------------------------------------------------------------

def focar_qlikview_e_navegar():
    logger.info("=== ETAPA 4: Navegando no QlikView ===")
    pausa(2)

    safe_click(*Coords.QLIKVIEW_CENTER)
    aguardar_tela_estavel()

    sucesso = clicar_e_validar(Coords.ABA_GRAFICOS_RELATORIOS, "Graficos | Relatorios")
    if not sucesso:
        raise RuntimeError("Nao foi possivel navegar para Graficos | Relatorios.")
    aguardar_tela_estavel()


# ---------------------------------------------------------------------------
# Selecionar bloco de filtro
# ---------------------------------------------------------------------------

BLOCOS = {
    "PDV":                    Coords.BLOCO_PDV,
    "Tempo":                  Coords.BLOCO_TEMPO,
    "Agente de Distribuição": Coords.BLOCO_AGENTE_DISTRIB,
    "Produto":                Coords.BLOCO_PRODUTO,
}

_bloco_atual = None


def _bloco_esta_ativo(coords: tuple, raio: int = 20, timeout: float = 15) -> bool:
    # Threshold aumentado para 160 pois cada bloco tem tonalidade de azul diferente.
    # PDV ativo ~ 108, outros blocos podem ficar entre 130-155.
    x, y   = coords
    regiao = (x - raio, y - raio, raio * 2, raio * 2)
    deadline = time.time() + timeout

    while time.time() < deadline:
        frame   = _capturar_tela()
        rx, ry, rw, rh = regiao
        recorte = frame[ry:ry+rh, rx:rx+rw]
        brilho  = float(recorte.mean())
        logger.debug(f"Brilho do bloco em {coords}: {brilho:.1f}")

        if brilho < 160:
            logger.info(f"✔ Bloco confirmado como ativo (brilho={brilho:.1f}).")
            return True
        time.sleep(0.3)

    logger.warning(f"⚠ Bloco nao confirmado (brilho manteve-se acima de 160).")
    return False


def selecionar_bloco(nome_bloco: str):
    global _bloco_atual
    if _bloco_atual == nome_bloco:
        logger.info(f"Bloco '{nome_bloco}' ja ativo.")
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

        logger.warning(f"⚠ Bloco '{nome_bloco}' nao ficou ativo — tentando novamente...")
        pausa(2.0)

    raise RuntimeError(f"Falha ao selecionar bloco '{nome_bloco}' apos 3 tentativas.")


# ---------------------------------------------------------------------------
# Aplicar bookmark
# ---------------------------------------------------------------------------

def aplicar_bookmark(nome_bookmark: str):
    logger.info(f"Aplicando bookmark: '{nome_bookmark}'")

    # Abre o dropdown
    sucesso = clicar_e_validar(Coords.DROPDOWN_BOOKMARK, "Dropdown Bookmark")
    if not sucesso:
        raise RuntimeError("Falha ao abrir dropdown de bookmarks.")
    pausa(2.0)   # aguarda lista expandir completamente

    # Estrategia: X fixo + Y via OCR
    # O dropdown sempre abre na mesma coluna horizontal.
    # Fixar X evita que o OCR clique na tabela ao fundo.
    # A regiao cobre APENAS a largura do dropdown (nao a tabela).
    btn_x, btn_y = Coords.DROPDOWN_BOOKMARK
    x_dropdown   = btn_x - 14           # centro horizontal do dropdown (≈ 609)
    regiao_ocr   = (
        x_dropdown - 90,  # ≈ 519 — inicio da regiao
        btn_y + 20,       # ≈ 121 — comeca abaixo do botao
        200,              # largura estreita: so o dropdown
        420,              # altura cobrindo todos os itens
    )

    achou = clicar_bookmark_por_nome(
        nome   = nome_bookmark,
        x_fixo = x_dropdown,
        regiao = regiao_ocr,
        timeout = 8.0,
    )

    if not achou:
        # Fallback: coordenada calibrada
        logger.warning(f"OCR falhou para '{nome_bookmark}' — usando coordenada calibrada.")
        bookmark_coords = Coords.BOOKMARKS.get(nome_bookmark)
        if bookmark_coords is None:
            raise ValueError(f"Bookmark '{nome_bookmark}' nao mapeado.")
        safe_click(*bookmark_coords)

    aguardar_tela_estavel()
    logger.info(f"Aguardando {PAUSA_POS_BOOKMARK}s para dados carregarem...")
    pausa(PAUSA_POS_BOOKMARK)
    aguardar_tela_estavel()
    logger.info(f"✔ Bookmark '{nome_bookmark}' aplicado e tabela pronta.")


# ---------------------------------------------------------------------------
# Dupla seta
# ---------------------------------------------------------------------------

def clicar_dupla_seta():
    logger.info("Aguardando dupla seta (») ficar visivel...")
    visivel = verificar_pixel_visivel(Coords.BOTAO_DUPLA_SETA, raio=15, brightness_max=210, tentativas=4)
    if not visivel:
        aguardar_elemento_por_pixel(Coords.BOTAO_DUPLA_SETA, raio=15, brightness_max=210, timeout=60)

    sucesso = clicar_e_validar(Coords.BOTAO_DUPLA_SETA, "Dupla seta (»)")
    if not sucesso:
        raise RuntimeError("Falha ao clicar na dupla seta (»).")
    aguardar_tela_estavel()
    logger.info("✔ Coluna Ano/Mes transposta.")


# ---------------------------------------------------------------------------
# Export Excel — 3 cenarios tratados explicitamente
# ---------------------------------------------------------------------------
#
# Cenario 1 (normal):
#   Caixa "Exporting..." aparece → processa → fecha → Chrome abre nova aba
#   → download inicia → arquivo aparece em Downloads
#
# Cenario 2 (falha silenciosa):
#   Caixa "Exporting..." aparece → fecha SEM abrir nova aba → sem download
#   → deve clicar no botao de export novamente
#
# Cenario 3 (press here):
#   Caixa mostra "content opened in another window / press here"
#   → clicar no link "press here" → nova aba abre → download inicia
# ---------------------------------------------------------------------------

BOTAO_EXPORT_POR_BLOCO = {
    "PDV":                    lambda: Coords.EXPORT_PDV,
    "Produto":                lambda: Coords.EXPORT_PRODUTO,
    "Tempo":                  lambda: Coords.EXPORT_TEMPO_AGENTE,
    "Agente de Distribuição": lambda: Coords.EXPORT_TEMPO_AGENTE,
}

MAX_TENTATIVAS_EXPORT    = 3

def _verificar_novo_arquivo(before: set, download_dir: Path):
    """
    Verifica se um novo arquivo definitivo apareceu na pasta de downloads.
    Retorna o arquivo ou None.
    Ignora arquivos temporarios (.crdownload, .tmp, etc).
    """
    try:
        todos   = list(download_dir.iterdir()) if download_dir.exists() else []
        tem_tmp = any(_is_temp(f) for f in todos if f.is_file())
        novos   = {f for f in todos if f.is_file() and not _is_temp(f)} - before

        if novos and not tem_tmp:
            return max(novos, key=lambda f: f.stat().st_mtime)
    except Exception:
        pass
    return None


def _aguardar_arquivo_estavel(arquivo: Path, poll: float = 2.0, ciclos: int = 3) -> bool:
    """
    Aguarda o arquivo ter tamanho estavel por 'ciclos' verificacoes consecutivas.
    Retorna True se estavel, False se nao.
    """
    tamanho_ant = -1
    estavel_count = 0
    for _ in range(ciclos + 5):
        time.sleep(poll)
        try:
            tam = arquivo.stat().st_size
            if tam > 0 and tam == tamanho_ant:
                estavel_count += 1
                if estavel_count >= ciclos:
                    return True
            else:
                estavel_count = 0
            tamanho_ant = tam
        except Exception:
            return False
    return False


# Segundos aguardando arquivo apos dialogo fechar sem download (cenario 2)
ESPERA_APOS_DIALOG_FECHAR = 10


def _monitorar_export(before: set, download_dir: Path) -> Path:
    """
    Monitora o resultado do clique no botao export.

    Cenario 1 (normal):
      Dialogo "Exporting..." processa → Chrome abre nova aba → arquivo aparece.

    Cenario 2 (falha silenciosa):
      Dialogo fecha sem download → retorna None para retentar.
    """
    ref_dialogo      = _capturar_tela()
    dialog_fechou_em = None
    deadline         = time.time() + DOWNLOAD_TIMEOUT

    while time.time() < deadline:
        time.sleep(1)

        # --- 1. Verifica se novo arquivo ja apareceu ---
        arquivo = _verificar_novo_arquivo(before, download_dir)
        if arquivo:
            logger.info(f"Arquivo novo detectado: {arquivo.name}")
            if _aguardar_arquivo_estavel(arquivo):
                logger.info(f"✅ Download completo: {arquivo.name} ({arquivo.stat().st_size:,} bytes)")
                return arquivo
            continue

        # Verifica arquivo temporario (download em progresso)
        try:
            todos   = list(download_dir.iterdir()) if download_dir.exists() else []
            tem_tmp = any(_is_temp(f) for f in todos if f.is_file())
            if tem_tmp:
                logger.info("Download em progresso (arquivo temporario detectado)...")
                continue
        except Exception:
            pass

        # --- 2. Detecta dialogo fechando ---
        if dialog_fechou_em is None:
            atual = _capturar_tela()
            sim   = _similaridade(ref_dialogo, atual)
            if sim < 0.94:
                dialog_fechou_em = time.time()
                logger.info(f"Dialogo fechou (sim={sim:.3f}). "
                            f"Aguardando arquivo por ate {ESPERA_APOS_DIALOG_FECHAR}s...")

        if dialog_fechou_em:
            tempo_desde_fechou = time.time() - dialog_fechou_em

            # Verifica sinal de download
            try:
                todos   = list(download_dir.iterdir()) if download_dir.exists() else []
                tem_tmp = any(_is_temp(f) for f in todos if f.is_file())
                novos   = {f for f in todos if f.is_file() and not _is_temp(f)} - before
                if tem_tmp or novos:
                    continue   # download em andamento, aguarda
            except Exception:
                pass

            if tempo_desde_fechou >= ESPERA_APOS_DIALOG_FECHAR:
                logger.warning(
                    f"Dialogo fechou ha {tempo_desde_fechou:.0f}s sem download "
                    f"→ vai retentar o clique no export."
                )
                return None

    logger.warning("Timeout aguardando download.")
    return None


def exportar_excel(bookmark: str, bloco: str) -> Path:
    """
    Exporta para Excel tratando os 3 cenarios do QlikView.
    So avanca quando o arquivo estiver 100% baixado e renomeado.
    """
    coords_export = BOTAO_EXPORT_POR_BLOCO[bloco]()
    download_dir  = get_download_dir()

    for tentativa in range(1, MAX_TENTATIVAS_EXPORT + 1):
        logger.info(f"Export tentativa {tentativa}/{MAX_TENTATIVAS_EXPORT} | '{bookmark}'")

        # Verifica visibilidade do botao
        ja_visivel = verificar_pixel_visivel(
            coords=coords_export, raio=15, brightness_max=210, tentativas=4
        )
        if ja_visivel:
            logger.info("Botao ja visivel — aguardando dados atualizarem...")
            pausa(PAUSA_POS_BOOKMARK)
            aguardar_tela_estavel()
        else:
            logger.info("Aguardando botao aparecer...")
            aguardar_elemento_por_pixel(
                coords=coords_export, raio=15, brightness_max=210, timeout=60
            )

        # Snapshot antes do clique
        before = snapshot_dir(download_dir)

        # Clica no botao export
        safe_click(*coords_export)
        logger.info(f"Clique no export realizado em {coords_export}.")
        pausa(2)   # aguarda dialogo aparecer

        # Monitora os 3 cenarios
        arquivo = _monitorar_export(before, download_dir)

        if arquivo:
            final = renomear_arquivo(arquivo, bookmark)
            logger.info(f"✅ '{final.name}' baixado e renomeado.")
            return final

        logger.warning(
            f"⚠ Tentativa {tentativa} sem sucesso. "
            f"{'Retentando...' if tentativa < MAX_TENTATIVAS_EXPORT else 'Tentativas esgotadas.'}"
        )
        pausa(3)

    raise RuntimeError(
        f"Download falhou apos {MAX_TENTATIVAS_EXPORT} tentativas para '{bookmark}'."
    )


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def _recuperar_navegacao():
    global _bloco_atual
    logger.warning("Recuperando navegacao...")
    _bloco_atual = None
    try:
        safe_click(*Coords.QLIKVIEW_CENTER)
        pausa(1)
        sucesso = clicar_e_validar(Coords.ABA_GRAFICOS_RELATORIOS, "Graficos | Relatorios (recuperacao)")
        if sucesso:
            aguardar_tela_estavel()
            logger.info("✔ Navegacao recuperada.")
            return True
    except Exception as e:
        logger.error(f"❌ Falha ao recuperar: {e}")
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
                logger.info(f"✅ Download {i}/8 concluido: {arquivo.name}\n")
                pausa(3)   # deixa QlikView estabilizar apos download
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
                    logger.error(f"❌ Download {i}/8 falhou apos {MAX_RECOVERY} recuperacoes: {e}")
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
        logger.info("║   Arquvios baixados com sucesso      ║")
        logger.info("╚══════════════════════════════════════╝")
        logger.info(f"Total: {len(arquivos)} arquivo(s):")
        for f in arquivos:
            logger.info(f"  -> {f.name}")
        tratar_bases()
        baixar_powerbi()
    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()