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
    PAUSA_POS_BOOKMARK, INICIO_DOWNLOAD_TIMEOUT,
    BOOKMARK_ORDER, BOOKMARK_Y_FIRST, BOOKMARK_ITEM_HEIGHT, BOOKMARK_X
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
    logger.info("Botao Entrar clicado — aguardando pagina de selecao de ambiente...")

    # Aguarda a pagina de selecao de ambiente carregar completamente
    pausa(3)
    aguardar_tela_estavel(timeout=30)
    pausa(3)   # margem extra para elementos da pagina renderizarem

    logger.info("=== ETAPA 3: Selecionar ambiente ===")
    safe_click(*Coords.LOGIN_AMBIENTE)
    logger.info(f"Ambiente '{AMBIENTE_NOME}' selecionado. Aguardando QlikView inicializar...")

    # O QlikView pode levar de 20 a 60 segundos para inicializar completamente.
    # Aguarda estabilidade multiplas vezes para garantir que o carregamento terminou.
    pausa(8)
    aguardar_tela_estavel(timeout=90)
    pausa(5)
    aguardar_tela_estavel(timeout=30)
    pausa(3)
    logger.info("QlikView inicializado.")


# ---------------------------------------------------------------------------
# Navegacao no QlikView
# ---------------------------------------------------------------------------

def focar_qlikview_e_navegar():
    logger.info("=== ETAPA 4: Navegando no QlikView ===")

    # Clica no centro para garantir foco na janela do QlikView
    pausa(3)
    safe_click(*Coords.QLIKVIEW_CENTER)
    pausa(2)
    aguardar_tela_estavel()

    sucesso = clicar_e_validar(Coords.ABA_GRAFICOS_RELATORIOS, "Graficos | Relatorios")
    if not sucesso:
        raise RuntimeError("Nao foi possivel navegar para Graficos | Relatorios.")
    pausa(2)
    aguardar_tela_estavel()


# ---------------------------------------------------------------------------
# Selecionar bloco de filtro
# ---------------------------------------------------------------------------

BLOCOS = {
    "PDV":                      Coords.BLOCO_PDV,
    "Tempo":                    Coords.BLOCO_TEMPO,
    "Agente de Distribuição":   Coords.BLOCO_AGENTE_DISTRIB,
    "Produto":                  Coords.BLOCO_PRODUTO,
    # Relatórios Personalizados é tratado separadamente em _navegar_relat_pdv()
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

def _calcular_y_bookmark(nome: str):
    """
    Calcula a coordenada Y de um bookmark usando H=24.5px por item.
    Y = BOOKMARK_Y_FIRST + round(indice * BOOKMARK_ITEM_HEIGHT)
    Retorna None se o nome nao estiver em BOOKMARK_ORDER.
    """
    try:
        idx = BOOKMARK_ORDER.index(nome)
        return round(BOOKMARK_Y_FIRST + idx * BOOKMARK_ITEM_HEIGHT)
    except ValueError:
        return None


def _selecionar_bookmark_teclado(nome: str) -> bool:
    """
    Seleciona um bookmark navegando com teclado: End + N x Up + Enter.

    POR QUE End E NAO Home:
      "Select Bookmark" aparece como item navegavel APENAS quando nenhum
      filtro esta ativo (primeiro download). Apos qualquer selecao, ele
      desaparece e Home vai direto para CATEGORIA AR.

      Isso causava inconsistencia: com "Select Bookmark" visivelm Home ia
      para posicao 0 ("Select Bookmark") e o indice ficava correto.
      Sem ele, Home ia para posicao 0 (CATEGORIA AR) e o indice ficava
      1 abaixo do esperado.

      End SEMPRE vai para o ultimo item (ST-Grit-Mateus, posicao fixa)
      independente do estado. A partir dai, subimos com Up ate o alvo.
      O resultado e identico com ou sem "Select Bookmark" visivelm:

        Com "Select Bookmark": End=visual 16, Up 15 -> visual 1 = CATEGORIA AR
        Sem "Select Bookmark": End=visual 15, Up 15 -> visual 0 = CATEGORIA AR
        Mesmo alvo, mesma quantidade de teclas. ✓

    Returns True se executou, False se nome nao esta em BOOKMARK_ORDER.
    """
    if nome not in BOOKMARK_ORDER:
        logger.warning(f"'{nome}' nao esta em BOOKMARK_ORDER — teclado indisponivel.")
        return False

    n   = len(BOOKMARK_ORDER)         # 16 itens (sem "Select Bookmark")
    idx = BOOKMARK_ORDER.index(nome)
    ups = (n - 1) - idx               # quantas vezes pressionar Up apos End

    # Garante que o foco esta NA LISTA do dropdown, nao no botao.
    # Sem este Down inicial o End/Enter podem agir no botao e nao na lista,
    # causando o dropdown ficar aberto sem selecionar nada.
    pyautogui.press("down")
    pausa(0.25)

    # End -> ultimo item (ST-Grit), sempre consistente.
    # Enviado 2x como seguranca extra.
    pyautogui.press("end")
    pausa(0.15)
    pyautogui.press("end")
    pausa(0.3)

    # Up × ups -> chega ao item desejado
    if ups > 0:
        pyautogui.press("up", presses=ups, interval=0.03)
    pausa(0.25)

    # Enter -> confirma
    pyautogui.press("enter")
    logger.info(
        f"Bookmark '{nome}' selecionado via teclado "
        f"(End + {ups}x Up, indice {idx}/{n-1})."
    )
    return True


def aplicar_bookmark(nome_bookmark: str):
    """
    Seleciona um bookmark no dropdown do QlikView.

    Estrategia em 3 niveis:

    1. Clique calculado: Y = BOOKMARK_Y_FIRST + idx * BOOKMARK_ITEM_HEIGHT.
       Robusto, sem dependencia de foco de teclado ou estado do dropdown.

    2. Teclado End+Up: fallback se bookmark nao estiver em BOOKMARK_ORDER.

    3. Coordenada calibrada: ultimo recurso (coordinates.py).
    """
    logger.info(f"Aplicando bookmark: '{nome_bookmark}'")

    # Garante foco no QlikView antes de qualquer interacao com o dropdown
    safe_click(*Coords.QLIKVIEW_CENTER)
    pausa(0.8)

    # Abre o dropdown com safe_click (nao usa clicar_e_validar porque
    # a verificacao de brilho do botao falha ao abrir lista — o botao
    # nao muda de cor quando a lista expande, causando RuntimeError
    # desnecessario e ativando a recuperacao completa da navegacao).
    logger.info("Abrindo dropdown de bookmarks...")
    safe_click(*Coords.DROPDOWN_BOOKMARK)
    pausa(2.0)   # aguarda a lista expandir completamente   # aguarda lista expandir e foco do teclado estabilizar

    # Teclado End+Up para todos os itens.
    # End vai sempre ao ultimo item da lista (ST-Grit-Mateus),
    # independente do scroll ou do item selecionado anteriormente.
    # Subindo N vezes chega ao item correto sem depender de Y ou posicao visual.
    if nome_bookmark in BOOKMARK_ORDER:
        _selecionar_bookmark_teclado(nome_bookmark)
    else:
        logger.warning(f"'{nome_bookmark}' nao em BOOKMARK_ORDER — coordenada calibrada.")
        bm = Coords.BOOKMARKS.get(nome_bookmark)
        if bm is None:
            raise ValueError(f"'{nome_bookmark}' nao encontrado.")
        safe_click(*bm)

    # Espera dupla: aguarda a tabela recarregar completamente após o bookmark.
    # aguardar_tela_estavel pode retornar rápido se a página ficar estável
    # momentaneamente no meio do carregamento — a pausa extra cobre isso.
    logger.info(f"Aguardando tabela recarregar apos bookmark...")
    pausa(PAUSA_POS_BOOKMARK)
    aguardar_tela_estavel()
    pausa(4.0)            # segunda espera: garante que os dados terminaram de carregar
    aguardar_tela_estavel()
    logger.info(f"✔ Bookmark '{nome_bookmark}' aplicado e tabela pronta.")


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
# ---------------------------------------------------------------------------
# Relatórios Personalizados — fluxo especial ST - Grit
# ---------------------------------------------------------------------------

def _navegar_relat_pdv():
    """
    Navega para Relatórios Personalizados -> PDV.

    Usa safe_click (sem verificacao de brilho) porque o bloco
    Relatorios Personalizados tem visual diferente dos demais.
    Pausa generosa entre os dois cliques: a view precisa carregar
    completamente antes de clicar em PDV, caso contrário o clique
    cai num bloco diferente da tela principal (ex: Forca de Vendas do AD).
    """
    global _bloco_atual

    # Passo 1: clica no bloco e aguarda a transicao completa da view.
    # Tenta até 3 vezes caso o clique não registre.
    logger.info("Clicando em Relatorios Personalizados...")
    for tentativa_bloco in range(1, 4):
        safe_click(*Coords.BLOCO_RELATORIOS_PERSONALIZADOS)
        pausa(6.0)           # espera generosa para a view carregar
        aguardar_tela_estavel()
        pausa(2.0)

        # Verifica se a view de Relatorios Personalizados ficou ativa
        # (brilho abaixo de 160 = bloco ativado / destacado)
        frame   = _capturar_tela()
        bx, by  = Coords.BLOCO_RELATORIOS_PERSONALIZADOS
        recorte = frame[by-20:by+20, bx-20:bx+20]
        brilho  = float(recorte.mean())
        logger.info(f"Brilho Relatorios Personalizados (tentativa {tentativa_bloco}): {brilho:.1f}")
        if brilho < 180:   # threshold mais alto — visual diferente dos outros blocos
            logger.info("Relatorios Personalizados confirmado como ativo.")
            break
        logger.warning(f"Bloco pode nao ter ativado (brilho={brilho:.1f}). Retentando...")
    else:
        logger.warning("Nao foi possivel confirmar Relatorios Personalizados — prosseguindo mesmo assim.")

    # Aguarda o conteúdo da view carregar completamente antes de clicar em PDV.
    # O QlikView pode ter pausas no meio do carregamento que enganam o
    # aguardar_tela_estavel() — por isso usamos duas verificações consecutivas
    # com pausa generosa entre elas.
    logger.info("Aguardando view de Relatorios Personalizados carregar completamente...")
    pausa(5.0)
    aguardar_tela_estavel(timeout=60)
    pausa(4.0)                          # segunda espera: garante que o carregamento terminou
    aguardar_tela_estavel(timeout=30)
    pausa(2.0)

    # Passo 2: clica em PDV dentro da view ja carregada.
    logger.info("Clicando em PDV dentro de Relatorios Personalizados...")
    safe_click(*Coords.RELAT_PERSONALIZADOS_PDV)

    pausa(6.0)
    aguardar_tela_estavel(timeout=60)
    pausa(3.0)
    aguardar_tela_estavel(timeout=30)
    pausa(2.0)

    logger.info("Navegado para Relatorios Personalizados — PDV.")
    _bloco_atual = "Relatorios Personalizados"


def _preparar_tabela_relat_pdv():
    """
    Prepara a tabela do Relatório PDV para exportação.
    1. Aguarda tabela carregar completamente.
    2. Arrasta 'Cód. Cliente' -> aguarda tabela recarregar.
    3. Arrasta 'Ano/Mês (Num)' -> aguarda tabela recarregar.
    4. Right-click em 'Ano/Mês (Num)' -> Collapse All.
    """
    # Aguarda a tabela carregar os dados ANTES de qualquer drag.
    # Após aplicar o bookmark, o Relatórios Personalizados PDV pode levar
    # mais tempo que as views normais. Duas verificações consecutivas
    # garantem que não é uma pausa falsa no meio do carregamento.
    logger.info("Aguardando tabela PDV carregar dados antes de reposicionar colunas...")
    pausa(4.0)
    aguardar_tela_estavel(timeout=120)
    pausa(4.0)
    aguardar_tela_estavel(timeout=60)
    pausa(2.0)
    logger.info("Tabela estavel. Iniciando reposicionamento de colunas...")
    pyautogui.moveTo(*Coords.HEADER_COD_CLIENTE, duration=0.6)
    pausa(0.5)
    pyautogui.dragTo(*Coords.HEADER_COD_CLIENTE_DESTINO, duration=1.0, button="left")
    pausa(1.0)

    # Aguarda tabela recarregar completamente após o drag
    aguardar_tela_estavel()
    pausa(2.0)   # margem extra para o QlikView processar a mudança de layout
    aguardar_tela_estavel()
    logger.info("'Cod. Cliente' reposicionado.")

    # ── Drag 2: Ano/Mês (Num) ────────────────────────────────────────────────
    logger.info("Arrastando 'Ano/Mes (Num)'...")
    pyautogui.moveTo(*Coords.HEADER_ANO_MES, duration=0.6)
    pausa(0.5)
    pyautogui.dragTo(*Coords.HEADER_ANO_MES_DESTINO, duration=1.0, button="left")
    pausa(1.0)

    # Aguarda tabela recarregar completamente após o drag
    aguardar_tela_estavel()
    pausa(2.0)   # margem extra
    aguardar_tela_estavel()
    logger.info("'Ano/Mes (Num)' reposicionado.")

    # ── Collapse All ─────────────────────────────────────────────────────────
    logger.info("Executando Collapse All em 'Ano/Mes (Num)'...")
    pyautogui.rightClick(*Coords.HEADER_ANO_MES_FINAL)
    pausa(0.8)   # aguarda o menu de contexto abrir completamente
    safe_click(*Coords.MENU_COLLAPSE_ALL)

    aguardar_tela_estavel()
    pausa(1.5)
    aguardar_tela_estavel()
    logger.info("Tabela preparada — colunas desnecessarias ocultadas.")


# Export Excel — 3 cenarios tratados explicitamente
# ---------------------------------------------------------------------------
#
# Cenario 1 (normal):
#   Caixa "Exporting..." aparece -> processa -> fecha -> Chrome abre nova aba
#   -> download inicia -> arquivo aparece em Downloads
#
# Cenario 2 (falha silenciosa):
#   Caixa "Exporting..." aparece -> fecha SEM abrir nova aba -> sem download
#   -> deve clicar no botao de export novamente
#
# Cenario 3 (press here):
#   Caixa mostra "content opened in another window / press here"
#   -> clicar no link "press here" -> nova aba abre -> download inicia
# ---------------------------------------------------------------------------

BOTAO_EXPORT_POR_BLOCO = {
    "PDV":                       lambda: Coords.EXPORT_PDV,
    "Produto":                   lambda: Coords.EXPORT_PRODUTO,
    "Tempo":                     lambda: Coords.EXPORT_TEMPO_AGENTE,
    "Agente de Distribuição":    lambda: Coords.EXPORT_TEMPO_AGENTE,
    "Relatorios Personalizados": lambda: Coords.EXPORT_RELAT_PDV,
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
      Dialogo "Exporting..." processa -> Chrome abre nova aba -> arquivo aparece.

    Cenario 2 (falha silenciosa):
      Dialogo fecha sem download -> retorna None para retentar.
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
                    f"-> vai retentar o clique no export."
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
        logger.info(f"Download {i}/{len(DOWNLOADS)} | Bloco: {bloco} | Bookmark: {bookmark}")
        logger.info(f"{'='*60}")

        for recovery in range(MAX_RECOVERY + 1):
            try:
                if bloco == "Relatorios Personalizados":
                    # Fluxo especial: ST - Grit via Relatorios Personalizados.
                    # Ordem obrigatoria: navegar -> aguardar -> bookmark -> preparar.
                    _navegar_relat_pdv()
                    aplicar_bookmark(bookmark)
                    _preparar_tabela_relat_pdv()
                else:
                    # Fluxo padrao
                    selecionar_bloco(bloco)
                    aplicar_bookmark(bookmark)
                    if clicar_seta:
                        clicar_dupla_seta()

                arquivo = exportar_excel(bookmark, bloco)
                arquivos.append(arquivo)
                logger.info(f"✅ Download {i}/{len(DOWNLOADS)} concluido: {arquivo.name}\n")
                pausa(3)   # deixa QlikView estabilizar apos download
                break

            except Exception as e:
                screenshot = str(_BASE_DIR / f"erro_{i}_{bookmark.replace(' ', '_')}.png")
                pyautogui.screenshot(screenshot)

                if recovery < MAX_RECOVERY:
                    logger.warning(
                        f"⚠ Falha no download {i}/{len(DOWNLOADS)} ({bookmark}): {e}\n"
                        f"   Recuperando (tentativa {recovery + 1}/{MAX_RECOVERY})..."
                    )
                    if not _recuperar_navegacao():
                        logger.error("Recuperacao falhou — encerrando.")
                        raise
                    pausa(3)
                else:
                    logger.error(f"❌ Download {i}/{len(DOWNLOADS)} falhou apos {MAX_RECOVERY} recuperacoes: {e}")
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