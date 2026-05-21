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
        import mss # type: ignore
        import mss.tools # type: ignore
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
        import mss # type: ignore
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


def verificar_elemento_ja_visivel(
    coords: tuple,
    template_path: str = None,
    confidence: float  = 0.75,
    raio: int          = 60,
    tentativas: int    = 3,
    poll: float        = 0.5,
) -> bool:
    """
    Verificação RÁPIDA: o elemento já está visível agora?

    Faz até 'tentativas' capturas com 'poll' segundos entre elas.
    Retorna True imediatamente se encontrar, False se não encontrar.
    Não espera — apenas verifica o estado atual da tela.
    """
    if template_path:
        p = Path(template_path)
        if p.exists():
            try:
                from PIL import Image as _PILImage
                template_img = _PILImage.open(str(p))
                tmpl_np = cv2.cvtColor(np.array(template_img), cv2.COLOR_RGB2GRAY)
            except Exception:
                return False

            for _ in range(tentativas):
                try:
                    bx, by = coords
                    margin = raio * 4
                    region_x = max(0, bx - margin)
                    region_y = max(0, by - margin)
                    tela_np = _capture(region=(region_x, region_y, margin * 2, margin * 2))

                    if tmpl_np.shape[0] >= tela_np.shape[0] or tmpl_np.shape[1] >= tela_np.shape[1]:
                        tela_np = _capture()

                    resultado = cv2.matchTemplate(tela_np, tmpl_np, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(resultado)
                    if max_val >= confidence:
                        logger.info(f"✔ Elemento já visível (score={max_val:.2f}).")
                        return True
                except Exception as e:
                    logger.debug(f"Verificação rápida erro: {e}")
                time.sleep(poll)

    return False


def verificar_pixel_visivel(
    coords: tuple,
    raio: int          = 15,
    brightness_max: int = 210,
    tentativas: int    = 3,
    poll: float        = 0.3,
) -> bool:
    """
    Verificação por pixel: existe algo visível (não-fundo) nas coordenadas?

    Captura uma pequena área ao redor de 'coords' e calcula o brilho médio.
    - Brilho baixo (< brightness_max): pixel escuro = ícone/botão presente ✅
    - Brilho alto (>= brightness_max): pixel claro = fundo vazio ❌

    Muito mais confiável que template matching para detectar ícones escuros
    sobre fundo claro (como os botões do QlikView).

    Args:
        coords:         (x, y) centro da área a verificar.
        raio:           Raio da área capturada em pixels.
        brightness_max: Limiar de brilho — abaixo = elemento visível.
        tentativas:     Número de capturas para confirmar.
        poll:           Intervalo entre tentativas em segundos.
    """
    x, y = coords
    regiao = (x - raio, y - raio, raio * 2, raio * 2)

    for t in range(tentativas):
        try:
            frame  = _capture(region=regiao)
            brilho = float(frame.mean())
            logger.debug(f"Brilho em {coords}: {brilho:.1f} (max={brightness_max})")
            if brilho < brightness_max:
                logger.info(f"✔ Elemento detectado em {coords} (brilho={brilho:.1f}).")
                return True
        except Exception as e:
            logger.debug(f"Erro na verificação por pixel: {e}")
        if t < tentativas - 1:
            time.sleep(poll)

    return False


def aguardar_elemento_por_pixel(
    coords: tuple,
    raio: int           = 15,
    brightness_max: int = 210,
    timeout: float      = 60,
    poll: float         = 0.5,
) -> bool:
    """
    Aguarda até que um elemento apareça nas coordenadas (verificação por pixel).

    Fica em loop verificando o brilho da região até encontrar pixels escuros
    (indicando que o ícone/botão apareceu) ou até o timeout ser atingido.

    Returns:
        True se o elemento apareceu, False se timeout atingido.
    """
    logger.info(
        f"Aguardando elemento aparecer em {coords} "
        f"(brilho < {brightness_max}, timeout={timeout}s)..."
    )
    deadline = time.time() + timeout

    while time.time() < deadline:
        if verificar_pixel_visivel(coords, raio=raio,
                                   brightness_max=brightness_max, tentativas=1):
            return True
        time.sleep(poll)

    logger.warning(f"⚠ Elemento não detectado em {coords} após {timeout}s.")
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


# ---------------------------------------------------------------------------
# Localização e clique por texto via OCR
# ---------------------------------------------------------------------------

def localizar_texto_e_clicar(
    texto: str,
    regiao: tuple   = None,
    timeout: float  = 5.0,
    poll: float     = 0.5,
    escala: int     = 2,
    confianca: int  = 40,
) -> bool:
    """
    Localiza um texto na tela via OCR (pytesseract) e clica nele.

    Mais robusto que coordenadas fixas para listas de texto como dropdowns
    do QlikView — funciona independente de scroll ou posição da janela.

    Args:
        texto:      Texto a localizar (busca por substring, case-insensitive).
        regiao:     (x, y, w, h) área de busca. None = tela inteira.
        timeout:    Tempo máximo de tentativas em segundos.
        poll:       Intervalo entre tentativas.
        escala:     Fator de ampliação da imagem para melhorar OCR (2 = 2x).
        confianca:  Confiança mínima do OCR (0-100). Valores baixos são
                    mais permissivos com fontes difíceis.

    Returns:
        True se encontrou e clicou, False caso contrário.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("pytesseract não disponível — usando coordenada fixa como fallback.")
        return False

    offset_x = regiao[0] if regiao else 0
    offset_y = regiao[1] if regiao else 0

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            # Captura a região desejada
            if regiao:
                shot = pyautogui.screenshot(region=regiao)
            else:
                shot = pyautogui.screenshot()

            # Amplia a imagem para melhorar a precisão do OCR
            shot_grande = shot.resize(
                (shot.width * escala, shot.height * escala),
                Image.LANCZOS
            )

            # Extrai dados de texto com posições
            data = pytesseract.image_to_data(
                shot_grande,
                output_type=pytesseract.Output.DICT,
                config="--psm 6"   # bloco uniforme de texto
            )

            # Reconstrói linhas agrupando palavras por (bloco, parágrafo, linha)
            linhas: dict = {}
            for i in range(len(data["text"])):
                conf = int(data["conf"][i])
                word = data["text"][i].strip()
                if conf < confianca or not word:
                    continue

                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                if key not in linhas:
                    linhas[key] = {
                        "palavras": [],
                        "left": [],
                        "top":  [],
                        "right":[],
                        "bot":  [],
                    }
                linhas[key]["palavras"].append(word)
                linhas[key]["left"].append(data["left"][i])
                linhas[key]["top"].append(data["top"][i])
                linhas[key]["right"].append(data["left"][i] + data["width"][i])
                linhas[key]["bot"].append(data["top"][i] + data["height"][i])

            # Procura o texto alvo entre as linhas reconstruídas
            texto_lower = texto.lower()
            for key, ld in linhas.items():
                linha_str = " ".join(ld["palavras"])
                if texto_lower in linha_str.lower():
                    # Centro da linha (corrige escala e soma offset da região)
                    cx = (min(ld["left"]) + max(ld["right"])) // 2 // escala + offset_x
                    cy = (min(ld["top"])  + max(ld["bot"]))  // 2 // escala + offset_y
                    logger.info(f"✔ Texto '{texto}' encontrado em ({cx}, {cy}) via OCR.")
                    safe_click(cx, cy)
                    return True

        except Exception as e:
            logger.debug(f"OCR erro: {e}")

        time.sleep(poll)

    logger.warning(f"⚠ Texto '{texto}' não encontrado na tela após {timeout}s.")
    return False

# ---------------------------------------------------------------------------
# Clique em bookmark por nome via OCR + X fixo
# ---------------------------------------------------------------------------

def clicar_bookmark_por_nome(
    nome: str,
    x_fixo: int,
    regiao: tuple,
    timeout: float = 8.0,
    poll: float    = 0.5,
    escala: int    = 2,
    confianca: int = 25,
) -> bool:
    """
    Localiza um item de dropdown pelo nome via OCR e clica usando X fixo.

    Por que X fixo?
    O QlikView renderiza a tabela de dados atras do dropdown. Se usarmos
    as coordenadas X do OCR, ele pode encontrar texto na tabela e clicar la.
    Ao fixar X no centro do dropdown e usar OCR so para encontrar Y,
    garantimos que o clique cai sempre dentro do dropdown.

    Usa mss para capturar a tela (mais confiavel com janelas GPU como QlikView).

    Args:
        nome:      Nome exato do bookmark (ex: "ST - Grit - Mateus").
        x_fixo:    Coordenada X do centro do dropdown.
        regiao:    (x, y, w, h) regiao de busca — deve cobrir so o dropdown.
        timeout:   Tempo maximo de tentativas em segundos.
        poll:      Intervalo entre tentativas.
        escala:    Fator de ampliacao para melhorar OCR (2 = 2x).
        confianca: Confianca minima do OCR (0-100). Valor baixo = mais permissivo.

    Returns:
        True se encontrou e clicou, False caso contrario.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("pytesseract nao disponivel para busca de bookmark.")
        return False

    offset_y   = regiao[1]
    nome_lower = nome.lower().strip()
    deadline   = time.time() + timeout

    # Normaliza o nome para comparacao tolerante (OCR as vezes omite espacos em tracos)
    def normalizar(s: str) -> str:
        return s.lower().strip().replace(" - ", "-").replace("- ", "-").replace(" -", "-")

    nome_norm = normalizar(nome)

    while time.time() < deadline:
        try:
            # Captura via mss (mais confiavel com QlikView GPU)
            try:
                import mss # type: ignore
                rx, ry, rw, rh = regiao
                with mss.mss() as sct:
                    monitor = {"left": rx, "top": ry, "width": rw, "height": rh}
                    raw = sct.grab(monitor)
                    shot = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            except Exception:
                shot = pyautogui.screenshot(region=regiao)

            # Amplia para melhorar precisao do OCR
            shot_grande = shot.resize(
                (shot.width * escala, shot.height * escala),
                Image.LANCZOS
            )

            # Extrai texto com posicoes
            data = pytesseract.image_to_data(
                shot_grande,
                output_type=pytesseract.Output.DICT,
                config="--psm 6"
            )

            # Reconstroi linhas agrupando palavras por (bloco, paragrafo, linha)
            linhas: dict = {}
            for i in range(len(data["text"])):
                conf = int(data["conf"][i])
                word = data["text"][i].strip()
                if conf < confianca or not word:
                    continue
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                if key not in linhas:
                    linhas[key] = {"palavras": [], "tops": [], "bots": []}
                linhas[key]["palavras"].append(word)
                linhas[key]["tops"].append(data["top"][i])
                linhas[key]["bots"].append(data["top"][i] + data["height"][i])

            # Procura match: exato primeiro, depois normalizado
            for modo in ["exato", "normalizado"]:
                for key, ld in linhas.items():
                    linha = " ".join(ld["palavras"]).strip()

                    if modo == "exato":
                        match = linha.lower() == nome_lower
                    else:
                        match = normalizar(linha) == nome_norm

                    if match:
                        # Y calculado pelo OCR + offset da regiao
                        cy = (min(ld["tops"]) + max(ld["bots"])) // 2 // escala + offset_y
                        logger.info(
                            f"Bookmark '{nome}' encontrado via OCR "
                            f"(modo={modo}, linha='{linha}') → ({x_fixo}, {cy})"
                        )
                        safe_click(x_fixo, cy)
                        return True

            logger.debug(f"OCR nao encontrou '{nome}' nesta tentativa. Linhas: "
                         + str([" ".join(ld["palavras"]) for ld in linhas.values()][:5]))

        except Exception as e:
            logger.debug(f"clicar_bookmark_por_nome erro: {e}")

        time.sleep(poll)

    logger.warning(f"Bookmark '{nome}' nao encontrado via OCR apos {timeout}s.")
    return False