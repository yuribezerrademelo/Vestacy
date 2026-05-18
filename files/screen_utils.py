# =============================================================================
# screen_utils.py — Utilitários de espera e interação com a tela
# =============================================================================

import time
import logging
from pathlib import Path

import numpy as np
import pyautogui
import cv2

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.3


# ---------------------------------------------------------------------------
# Captura e comparação de tela
# ---------------------------------------------------------------------------

def _capture(region=None) -> np.ndarray:
    """
    Captura screenshot usando mss (preferido) ou pyautogui (fallback).

    mss é mais confiável com janelas GPU-aceleradas como QlikView —
    o pyautogui usa GDI e pode não capturar janelas renderizadas por GPU
    em certos estados (ex: após abrir dropdown, antes de Alt+Tab).
    """
    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            if region:
                x, y, w, h = region
                monitor = {"left": x, "top": y, "width": w, "height": h}
            else:
                monitor = sct.monitors[0]  # tela inteira
            shot = sct.grab(monitor)
            arr  = np.array(shot)
            # mss retorna BGRA — converte para RGB depois para cinza
            arr_rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
            return cv2.cvtColor(arr_rgb, cv2.COLOR_RGB2GRAY)
    except Exception:
        # Fallback para pyautogui se mss não estiver disponível
        shot = pyautogui.screenshot(region=region)
        arr  = np.array(shot)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def _capture_pil(region=None):
    """
    Captura screenshot como imagem PIL — usada no template matching.
    Também usa mss quando disponível.
    """
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            if region:
                x, y, w, h = region
                monitor = {"left": x, "top": y, "width": w, "height": h}
            else:
                monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        return pyautogui.screenshot(region=region)


def _compare(img1: np.ndarray, img2: np.ndarray) -> float:
    result = cv2.matchTemplate(img1, img2, cv2.TM_CCOEFF_NORMED)
    return float(result[0][0])


# ---------------------------------------------------------------------------
# Estabilidade de tela
# ---------------------------------------------------------------------------

def wait_for_screen_stable(
    timeout: float   = 60,
    interval: float  = 0.5,
    threshold: float = 0.995,
    region=None
) -> bool:
    """Aguarda a tela parar de mudar. Retorna True quando estável."""
    logger.info("Aguardando estabilidade da tela...")
    deadline  = time.time() + timeout
    prev_shot = _capture(region)

    while time.time() < deadline:
        time.sleep(interval)
        curr_shot  = _capture(region)
        similarity = _compare(prev_shot, curr_shot)
        logger.debug(f"Similaridade: {similarity:.4f}")

        if similarity >= threshold:
            logger.info(f"Tela estável (similaridade={similarity:.4f})")
            return True

        prev_shot = curr_shot

    logger.warning("Timeout: tela não estabilizou dentro do prazo.")
    return False


# ---------------------------------------------------------------------------
# Aguardar elemento visível na tela
# ---------------------------------------------------------------------------

def aguardar_elemento_visivel(
    coords: tuple,
    template_path: str = None,
    timeout: float     = 60,
    poll: float        = 0.5,
    raio: int          = 30,
    confidence: float  = 0.70,
    estavel_por: float = 1.5,
) -> bool:
    """
    Aguarda um elemento aparecer na tela antes de prosseguir.

    ESTRATÉGIA 1 — Template matching (preferida):
        Procura a imagem do elemento na tela a cada 'poll' segundos.
        Só retorna True quando o ícone for encontrado com confiança >= confidence.
        Requer que o arquivo de template exista no caminho informado.

    ESTRATÉGIA 2 — Detecção por mudança + estabilidade (fallback):
        Monitora a região ao redor de 'coords'.
        Aguarda a região MUDAR do estado inicial (elemento apareceu)
        e depois ESTABILIZAR por 'estavel_por' segundos.
        Evita o falso positivo de região em branco/estável.

    Args:
        coords:        (x, y) centro do elemento.
        template_path: Caminho para PNG de referência (opcional).
        timeout:       Tempo máximo de espera em segundos.
        poll:          Intervalo entre verificações.
        raio:          Raio da região monitorada (px) no fallback.
        confidence:    Confiança mínima para template matching.
        estavel_por:   Segundos de estabilidade exigidos após mudança.

    Returns:
        True se detectado, False se timeout atingido.
    """

    # --- Estratégia 1: template matching ---
    if template_path:
        p = Path(template_path)
        if p.exists():
            logger.info(
                f"Aguardando elemento via template '{p.name}' "
                f"(confiança={confidence}, timeout={timeout}s)..."
            )

            # Pré-carrega o template via PIL para suportar caminhos com
            # caracteres especiais (acentos, ç, etc.) no Windows.
            # OpenCV / pyautogui não suportam caminhos não-ASCII diretamente.
            try:
                from PIL import Image as _PILImage
                template_img = _PILImage.open(str(p))
            except Exception as e:
                logger.warning(f"⚠ Falha ao carregar template '{p.name}': {e} — usando fallback por região.")
                template_img = None

            if template_img is not None:
                # Converte template para numpy grayscale para matching manual via OpenCV
                tmpl_np = cv2.cvtColor(np.array(template_img), cv2.COLOR_RGB2GRAY)
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        # Captura APENAS a região próxima das coordenadas calibradas.
                        # Isso evita falsos positivos em outras partes da tela.
                        bx, by = coords
                        margin = raio * 4  # área de busca = raio * 4 ao redor do ponto
                        region_x = max(0, bx - margin)
                        region_y = max(0, by - margin)
                        region_w = margin * 2
                        region_h = margin * 2
                        tela_np = _capture(region=(region_x, region_y, region_w, region_h))

                        # Template deve ser menor que a região capturada
                        if tmpl_np.shape[0] >= tela_np.shape[0] or tmpl_np.shape[1] >= tela_np.shape[1]:
                            # Região menor que o template — busca na tela inteira como fallback
                            tela_np = _capture()

                        resultado = cv2.matchTemplate(tela_np, tmpl_np, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(resultado)
                        if max_val >= confidence:
                            logger.info(
                                f"✔ Elemento confirmado na região de {coords} "
                                f"(score={max_val:.2f})."
                            )
                            # Retorna True — o clique usa a coordenada calibrada, não a encontrada
                            return True
                        logger.debug(f"Template score={max_val:.3f} < {confidence}")
                    except Exception as e:
                        logger.debug(f"Erro no template matching: {e}")
                    time.sleep(poll)

                logger.warning(
                    f"⚠ Template '{p.name}' não encontrado na tela após {timeout}s. "
                    f"Verifique se o template está correto e se o botão está visível."
                )
                return None

        else:
            # Template informado mas arquivo não existe — avisa e usa fallback
            logger.warning(
                f"⚠ Arquivo de template não encontrado: {template_path}\n"
                f"   Usando detecção por região como fallback.\n"
                f"   Coloque o arquivo PNG em: {template_path}"
            )
            # sem template — cai no fallback por região abaixo

    # --- Estratégia 2: mudança + estabilidade de região ---
    x, y   = coords
    regiao = (x - raio, y - raio, raio * 2, raio * 2)

    logger.info(
        f"Aguardando elemento via região "
        f"(centro={coords}, raio={raio}px, timeout={timeout}s)...\n"
        f"  Fase 1: aguardando a região MUDAR (elemento aparecer)\n"
        f"  Fase 2: aguardando a região ESTABILIZAR (elemento pronto)"
    )

    deadline     = time.time() + timeout
    estado_ini   = _capture(region=regiao)   # estado antes do elemento aparecer
    mudou        = False
    acumulado    = 0.0
    prev         = estado_ini

    while time.time() < deadline:
        time.sleep(poll)
        curr     = _capture(region=regiao)
        sim_ini  = _compare(estado_ini, curr)  # vs estado inicial
        sim_prev = _compare(prev, curr)         # vs frame anterior

        if not mudou:
            # Fase 1: aguarda qualquer mudança em relação ao estado inicial
            if sim_ini < 0.990:
                logger.info("  Fase 1 concluída: região mudou (elemento aparecendo).")
                mudou     = True
                acumulado = 0.0
        else:
            # Fase 2: aguarda estabilidade após mudança
            if sim_prev >= 0.995:
                acumulado += poll
                if acumulado >= estavel_por:
                    logger.info(
                        f"✔ Região estável por {acumulado:.1f}s após mudança "
                        f"— elemento considerado visível."
                    )
                    # Retorna as coordenadas do centro da região monitorada
                    return coords
            else:
                acumulado = 0.0  # ainda mudando, reinicia contagem

        prev = curr

    if not mudou:
        logger.warning(
            f"⚠ Região nunca mudou do estado inicial após {timeout}s.\n"
            f"   O elemento pode não ter aparecido. Verifique as coordenadas."
        )
    else:
        logger.warning(
            f"⚠ Região mudou mas não estabilizou após {timeout}s."
        )
    return False


# Alias para compatibilidade
aguardar_botao_export = aguardar_elemento_visivel


# ---------------------------------------------------------------------------
# Cliques seguros
# ---------------------------------------------------------------------------

def safe_click(x: int, y: int, clicks: int = 1, interval: float = 0.1):
    """Clique em coordenadas absolutas com movimento suave."""
    logger.info(f"Clicando em ({x}, {y})")
    pyautogui.moveTo(x, y, duration=0.3)
    pyautogui.click(clicks=clicks, interval=interval)


def safe_click_image(template_path: str, confidence: float = 0.8, region=None):
    """Localiza imagem na tela e clica nela."""
    try:
        location = pyautogui.locateOnScreen(
            template_path, confidence=confidence, region=region
        )
        if location:
            centro = pyautogui.center(location)
            safe_click(centro.x, centro.y)
            return centro
    except pyautogui.ImageNotFoundException:
        pass
    raise RuntimeError(f"Imagem não encontrada na tela: {template_path}")


# ---------------------------------------------------------------------------
# Drag-and-drop
# ---------------------------------------------------------------------------

def drag_and_drop(
    from_x: int, from_y: int,
    to_x: int,   to_y: int,
    steps: int      = 30,
    duration: float = 1.0
):
    """Drag-and-drop suave entre dois pontos absolutos."""
    logger.info(f"Drag-and-drop: ({from_x},{from_y}) → ({to_x},{to_y})")
    pyautogui.moveTo(from_x, from_y, duration=0.3)
    pyautogui.mouseDown()
    time.sleep(0.2)

    step_x         = (to_x - from_x) / steps
    step_y         = (to_y - from_y) / steps
    sleep_per_step = duration / steps

    for i in range(steps):
        pyautogui.moveTo(
            from_x + int(step_x * (i + 1)),
            from_y + int(step_y * (i + 1)),
            duration=sleep_per_step
        )

    time.sleep(0.2)
    pyautogui.mouseUp()
    logger.info("Drag-and-drop concluído.")