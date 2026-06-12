import time
import shutil
import subprocess
import pyautogui
import pytesseract
import numpy as np
import mss
from PIL import Image
from pathlib import Path
from files.config import DOWNLOAD_DIR, DOWNLOAD_TIMEOUT

# Caminho do executável do Tesseract OCR (instalar em https://github.com/UB-Mannheim/tesseract/wiki)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ============================================================
# CONFIGURAÇÕES
# ============================================================

OPERA_GX_PATH    = r"C:\Users\yurib\AppData\Local\Programs\Opera GX\opera.exe"
POWERBI_URL      = (
    "https://app.powerbi.com/groups/me/apps/176d31c7-71e0-41d0-b515-c068dc750161"
    "/reports/d581fd43-0b4b-4991-8dad-2fe2f5d68339"
    "/bfe3640367de83f3972d?ctid=95e66ecc-f2c2-464b-84d9-8fda407bc923&experience=power-bi"
)
PASTA_DESTINO     = Path(r"C:\Users\yurib\Downloads\Vestacy")
DOWNLOAD_DIR_PATH = Path(DOWNLOAD_DIR) if DOWNLOAD_DIR else Path.home() / "Downloads"


# ============================================================
# COORDENADAS
# ============================================================

COORDS = {

    # One Page — Grid Geral
    "grid_geral_hover":   (1956, 1250),
    "grid_geral_3pontos": (2025, 1223),

    # 02.Faturado — Tabela
    "faturado_hover":     (1954, 764),
    "faturado_3pontos":   (2010, 732),
    "icone_tabela":       (1909, 695),

    # Botão "Exportar" no modal (sempre centralizado na tela) ← CALIBRAR
    "btn_exportar": (1473, 999),
}

# ============================================================
# OCR — CLIQUE POR TEXTO
# ============================================================

def capturar_tela() -> Image.Image:
    """Captura a tela inteira e retorna como imagem PIL."""
    with mss.MSS() as sct:
        raw = sct.grab(sct.monitors[0])
        return Image.frombytes("RGB", raw.size, raw.rgb)


def aguardar_pagina_carregar(
    timeout: int = 60,
    intervalo: float = 1.0,
    estabilidade: float = 0.995,
    janela_estavel: int = 3,
):
    """
    Aguarda a página carregar comparando screenshots consecutivos.
    Só avança quando a tela ficar estável (sem mudanças visuais) por
    `janela_estavel` verificações seguidas.

    - timeout: tempo máximo de espera em segundos
    - intervalo: pausa entre cada captura
    - estabilidade: similaridade mínima (0-1) para considerar estável
    - janela_estavel: quantas verificações estáveis consecutivas exige
    """
    print(f"  Aguardando página carregar (timeout: {timeout}s)...")
    inicio = time.time()
    anterior = np.array(capturar_tela()).astype(np.float32)
    contagem_estavel = 0

    while time.time() - inicio < timeout:
        time.sleep(intervalo)
        atual = np.array(capturar_tela()).astype(np.float32)

        # Similaridade pixel a pixel (1.0 = idêntico)
        diff = np.abs(atual - anterior).mean()
        max_diff = 255.0
        similaridade = 1.0 - (diff / max_diff)

        if similaridade >= estabilidade:
            contagem_estavel += 1
            print(f"  Estável {contagem_estavel}/{janela_estavel} (similaridade: {similaridade:.4f})")
            if contagem_estavel >= janela_estavel:
                print(f"  Página carregada!")
                return
        else:
            contagem_estavel = 0
            print(f"  Carregando... (similaridade: {similaridade:.4f})")

        anterior = atual

    print(f"  AVISO: timeout atingido após {timeout}s. Prosseguindo mesmo assim.")


def clicar_por_texto(texto: str, timeout: int = 8, y_min: int = 0) -> bool:
    """
    Procura o texto na tela via OCR e clica no centro dele.
    - Suporta textos compostos (ex: 'Exportar dados')
    - Tenta por até `timeout` segundos antes de desistir
    - y_min: ignora ocorrências acima dessa coordenada Y (útil para
      evitar menus fixos no topo da página)
    - Retorna True se encontrou e clicou, False caso contrário
    """
    palavras_alvo = texto.lower().split()
    inicio = time.time()

    while time.time() - inicio < timeout:
        img = capturar_tela()

        # Pré-processamento: escala de cinza
        img_proc = img.convert("L")
        img_proc = Image.fromarray(np.array(img_proc))

        dados = pytesseract.image_to_data(
            img_proc,
            lang="por",
            output_type=pytesseract.Output.DICT,
            config="--psm 11",  # detecta palavras esparsas
        )

        textos = [t.lower().strip() for t in dados["text"]]
        n      = len(palavras_alvo)

        # Percorre janelas de n palavras consecutivas
        for i in range(len(textos) - n + 1):
            janela = textos[i : i + n]
            if janela == palavras_alvo:
                # Calcula o centro da região que cobre todas as palavras
                xs  = [dados["left"][i + j]                          for j in range(n)]
                ys  = [dados["top"][i + j]                           for j in range(n)]
                x2s = [dados["left"][i + j] + dados["width"][i + j]  for j in range(n)]
                y2s = [dados["top"][i + j]  + dados["height"][i + j] for j in range(n)]

                cx = (min(xs) + max(x2s)) // 2
                cy = (min(ys) + max(y2s)) // 2

                # Ignora se estiver acima do y_min (ex: menus fixos do topo)
                if cy < y_min:
                    print(f"  '{texto}' encontrado em ({cx}, {cy}) mas ignorado (acima de y_min={y_min}).")
                    continue

                pyautogui.click(cx, cy)
                print(f"  '{texto}' encontrado em ({cx}, {cy}) e clicado.")
                return True

        time.sleep(0.5)

    print(f"  AVISO: texto '{texto}' não encontrado após {timeout}s.")
    return False


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def aguardar_download(nome_arquivo: str, timeout: int = DOWNLOAD_TIMEOUT) -> Path:
    """Aguarda o arquivo aparecer na pasta de downloads e retorna seu Path."""
    destino = DOWNLOAD_DIR_PATH / nome_arquivo
    inicio  = time.time()
    while time.time() - inicio < timeout:
        if destino.exists() and destino.stat().st_size > 0:
            time.sleep(1)
            return destino
        time.sleep(0.5)
    raise TimeoutError(f"Download não detectado após {timeout}s: {nome_arquivo}")


# Posição neutra para resetar hover (canto superior esquerdo, fora de qualquer elemento)
POSICAO_NEUTRA = (10, 400)

# Número máximo de tentativas para cada exportação
MAX_TENTATIVAS_EXPORT = 3


def hover_e_exportar(coord_hover: tuple, coord_3pontos: tuple, nome_arquivo: str) -> Path:
    """
    Sequência padrão de exportação com validação em cada etapa e retentativas:
    neutro → hover tabela → aguarda ••• via OCR → clica ••• →
    aguarda 'Exportar dados' via OCR → clica → aguarda botão 'Exportar' → clica
    """
    for tentativa in range(1, MAX_TENTATIVAS_EXPORT + 1):
        print(f"  Tentativa {tentativa}/{MAX_TENTATIVAS_EXPORT}...")

        # 1. Move para posição neutra primeiro para resetar qualquer hover anterior
        print(f"  Movendo para posição neutra...")
        pyautogui.moveTo(*POSICAO_NEUTRA, duration=0.3)
        time.sleep(0.5)

        # 2. Hover na tabela para exibir os 3 pontinhos
        print(f"  Hovering na tabela...")
        pyautogui.moveTo(*coord_hover, duration=0.8)
        time.sleep(1.5)

        # 3. Move lentamente até os 3 pontinhos (mantém hover ativo)
        print(f"  Movendo para os 3 pontinhos...")
        pyautogui.moveTo(*coord_3pontos, duration=0.5)
        time.sleep(0.8)

        # 4. Clica nos 3 pontinhos
        print(f"  Clicando nos 3 pontinhos...")
        pyautogui.click(*coord_3pontos)
        time.sleep(1)

        # 5. Aguarda e clica em 'Exportar dados' via OCR
        print(f"  Procurando 'Exportar dados' via OCR...")
        if not clicar_por_texto("Exportar dados", timeout=6):
            print(f"  Menu não apareceu. Retentando fluxo...")
            # Pressiona Esc para fechar qualquer menu aberto antes de retentar
            pyautogui.press("escape")
            time.sleep(1)
            continue
        time.sleep(1.5)

        # 6. Aguarda o modal abrir e clica no botão 'Exportar'
        print(f"  Aguardando modal de exportação...")
        time.sleep(2)
        print(f"  Clicando no botão 'Exportar' do modal...")
        pyautogui.click(*COORDS["btn_exportar"])
        time.sleep(1)

        # 7. Aguarda o download completar
        print(f"  Aguardando download: {nome_arquivo}...")
        try:
            arquivo = aguardar_download(nome_arquivo, timeout=60)
            print(f"  Download concluído: {arquivo.name}")
            return arquivo
        except TimeoutError:
            print(f"  Download não detectado. Retentando fluxo...")
            continue

    raise RuntimeError(
        f"Exportação falhou após {MAX_TENTATIVAS_EXPORT} tentativas para '{nome_arquivo}'."
    )


def mover_arquivo(arquivo: Path, nome_destino: str):
    """Move o arquivo para a pasta de destino, substituindo se já existir."""
    PASTA_DESTINO.mkdir(parents=True, exist_ok=True)
    destino = PASTA_DESTINO / nome_destino
    shutil.move(str(arquivo), str(destino))
    print(f"  Movido para: {destino}")


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():
    print("=" * 60)
    print("DOWNLOAD POWER BI")
    print("=" * 60)

    print("\n>>> Abrindo Opera GX com Power BI...")
    subprocess.Popen([OPERA_GX_PATH, POWERBI_URL])
    time.sleep(3)  # pausa mínima para o navegador iniciar
    aguardar_pagina_carregar()

    # ARQUIVO 1 — One Page / Grid Geral
    print("\n>>> Arquivo 1: Grid Geral (One Page)")
    arquivo1 = hover_e_exportar(
        coord_hover   = COORDS["grid_geral_hover"],
        coord_3pontos = COORDS["grid_geral_3pontos"],
        nome_arquivo  = "data.xlsx",
    )

    # ARQUIVO 2 — 02.Faturado
    print("\n>>> Navegando para '02.Faturado'...")
    if not clicar_por_texto("02.Faturado"):
        raise RuntimeError("Não foi possível localizar '02.Faturado' no painel.")
    aguardar_pagina_carregar()

    print("\n>>> Convertendo gráfico para tabela...")
    pyautogui.click(*COORDS["icone_tabela"])
    time.sleep(2)

    print("\n>>> Arquivo 2: Faturado")
    arquivo2 = hover_e_exportar(
        coord_hover   = COORDS["faturado_hover"],
        coord_3pontos = COORDS["faturado_3pontos"],
        nome_arquivo  = "data (1).xlsx",
    )

    # Move ambos os arquivos apenas após os 2 downloads concluídos
    print("\n>>> Movendo arquivos para destino final...")
    mover_arquivo(arquivo1, "data.xlsx")
    mover_arquivo(arquivo2, "data (1).xlsx")

    print("\n" + "=" * 60)
    print("Download Power BI concluído! 2 arquivos salvos em:")
    print(f"  {PASTA_DESTINO}")
    print("=" * 60)


if __name__ == "__main__":
    main()