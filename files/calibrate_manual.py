# =============================================================================
# calibrate_manual.py — Calibração manual de coordenadas individuais
# =============================================================================
#
# Use este arquivo quando precisar recalibrar apenas um ou alguns pontos
# sem precisar passar por todo o processo de calibração novamente.
#
# USO:
#   python calibrate_manual.py
#
# O script mostra um menu com TODOS os pontos clicáveis do sistema.
# Selecione o que quer recalibrar, posicione o mouse e pressione ENTER.
# O valor atualizado é salvo automaticamente no coordinates.py.
#
# =============================================================================

import time
import re
import sys
from pathlib import Path

try:
    import pyautogui
except ImportError:
    print("Instale o pyautogui: pip install pyautogui")
    sys.exit(1)

COORDINATES_FILE = Path(__file__).parent / "coordinates.py"

# =============================================================================
# Mapa completo de todos os pontos calibráveis
# Formato: (chave_no_arquivo, descrição, instrução_extra)
# =============================================================================
PONTOS = [
    # --- Navegação ---
    (
        "QLIKVIEW_CENTER",
        "Centro da janela do QlikView",
        "Clique no centro da janela do QlikView para dar foco inicial."
    ),
    (
        "ABA_GRAFICOS_RELATORIOS",
        "Aba 'Gráficos | Relatórios'",
        "Posicione sobre a aba 'Gráficos | Relatórios' na barra superior."
    ),

    # --- Blocos de filtro ---
    (
        "BLOCO_PDV",
        "Bloco 'PDV'",
        "Posicione sobre o ícone PDV no menu de blocos (barra de ícones superior)."
    ),
    (
        "BLOCO_TEMPO",
        "Bloco 'Tempo'",
        "Posicione sobre o ícone Tempo no menu de blocos."
    ),
    (
        "BLOCO_AGENTE_DISTRIB",
        "Bloco 'Agente de Distribuição'",
        "Posicione sobre o ícone Agente de Distribuição no menu de blocos."
    ),
    (
        "BLOCO_PRODUTO",
        "Bloco 'Produto'",
        "Posicione sobre o ícone Produto no menu de blocos."
    ),

    # --- Dropdown de bookmarks ---
    (
        "DROPDOWN_BOOKMARK",
        "Dropdown 'Select Bookmark'",
        "Posicione sobre o dropdown 'Select Bookmark' na barra superior do QlikView."
    ),

    # --- Bookmarks individuais ---
    (
        'BOOKMARKS["ST - Grit"]',
        "Bookmark 'ST - Grit'",
        "ANTES: abra o dropdown 'Select Bookmark'. Posicione sobre o item 'ST - Grit'."
    ),
    (
        'BOOKMARKS["ST - Grit - Mateus"]',
        "Bookmark 'ST - Grit - Mateus'",
        "ANTES: abra o dropdown. Posicione sobre 'ST - Grit - Mateus'."
    ),
    (
        'BOOKMARKS["CATEGORIA AR"]',
        "Bookmark 'CATEGORIA AR'",
        "ANTES: abra o dropdown. Posicione sobre 'CATEGORIA AR'."
    ),
    (
        'BOOKMARKS["CATEGORIA AR - MATEUS"]',
        "Bookmark 'CATEGORIA AR - MATEUS'",
        "ANTES: abra o dropdown. Posicione sobre 'CATEGORIA AR - MATEUS'."
    ),
    (
        'BOOKMARKS["ST - DBs"]',
        "Bookmark 'ST - DBs'",
        "ANTES: abra o dropdown. Posicione sobre 'ST - DBs'."
    ),
    (
        'BOOKMARKS["ST - DBs - Mateus"]',
        "Bookmark 'ST - DBs - Mateus'",
        "ANTES: abra o dropdown. Posicione sobre 'ST - DBs - Mateus'."
    ),
    (
        'BOOKMARKS["Produto"]',
        "Bookmark 'Produto'",
        "ANTES: abra o dropdown. Posicione sobre 'Produto'."
    ),
    (
        'BOOKMARKS["Produto - Mateus"]',
        "Bookmark 'Produto - Mateus'",
        "ANTES: abra o dropdown. Posicione sobre 'Produto - Mateus'."
    ),

    # --- Botões de export ---
    (
        "EXPORT_PDV",
        "Botão export Excel — bloco PDV",
        "ANTES: ative o bloco PDV. Posicione sobre o botão de exportar Excel."
    ),
    (
        "EXPORT_PRODUTO",
        "Botão export Excel — bloco Produto",
        "ANTES: ative o bloco Produto. Posicione sobre o botão de exportar Excel."
    ),
    (
        "EXPORT_TEMPO_AGENTE",
        "Botão export Excel — bloco Tempo / Agente Dist.",
        "ANTES: ative o bloco Tempo. Posicione sobre o botão de exportar Excel."
    ),

    # --- Dupla seta ---
    (
        "BOTAO_DUPLA_SETA",
        "Botão dupla seta (»)",
        "ANTES: ative o bloco Produto. Posicione sobre o botão (») à esquerda do export."
    ),

    # --- Diálogos ---
    (
        "LINK_PRESS_HERE",
        "Link 'press here' do diálogo de export",
        "ANTES: provoque o diálogo 'opened in another window'. Posicione sobre o link 'press here'."
    ),
    (
        "DIALOGO_OK",
        "Botão OK do diálogo 'Excel Export'",
        "ANTES: provoque o diálogo de loading. Posicione sobre o botão OK."
    ),
]


# =============================================================================
# Leitura e escrita do coordinates.py
# =============================================================================

def ler_coordenadas() -> dict:
    """Lê o coordinates.py e retorna um dicionário com todos os valores atuais."""
    conteudo = COORDINATES_FILE.read_text(encoding="utf-8")
    coords = {}

    # Coordenadas simples: CHAVE = (x, y)
    for match in re.finditer(r'^\s{4}(\w+)\s*=\s*(\(\d+,\s*\d+\))', conteudo, re.MULTILINE):
        coords[match.group(1)] = match.group(2)

    # Bookmarks: "nome": (x, y)
    bm_section = re.search(r'BOOKMARKS\s*=\s*\{(.+?)\}', conteudo, re.DOTALL)
    if bm_section:
        for match in re.finditer(r'"([^"]+)"\s*:\s*(\(\d+,\s*\d+\))', bm_section.group(1)):
            coords[f'BOOKMARKS["{match.group(1)}"]'] = match.group(2)

    return coords


def salvar_coordenada(chave: str, novo_valor: tuple):
    """Atualiza uma coordenada específica no coordinates.py."""
    conteudo  = COORDINATES_FILE.read_text(encoding="utf-8")
    novo_str  = str(novo_valor)

    if chave.startswith('BOOKMARKS["'):
        # Bookmark: "nome": (x, y)
        nome = chave[len('BOOKMARKS["'):-2]
        padrao      = rf'("{re.escape(nome)}"\s*:\s*)\(\d+,\s*\d+\)'
        substituido = re.sub(padrao, rf'\g<1>{novo_str}', conteudo)
    else:
        # Coordenada simples: CHAVE = (x, y)
        padrao      = rf'(\b{re.escape(chave)}\s*=\s*)\(\d+,\s*\d+\)'
        substituido = re.sub(padrao, rf'\g<1>{novo_str}', conteudo)

    if substituido == conteudo:
        print(f"  ⚠ Chave '{chave}' não encontrada no arquivo para atualizar.")
        return False

    COORDINATES_FILE.write_text(substituido, encoding="utf-8")
    return True


# =============================================================================
# Captura de posição do mouse
# =============================================================================

def capturar_posicao(descricao: str, instrucao: str) -> tuple:
    print(f"\n  📌 {descricao}")
    print(f"  ℹ  {instrucao}")
    input("\n  Pressione ENTER e posicione o mouse sobre o elemento...")
    print("  Capturando em 3 segundos — não mova o mouse!")
    time.sleep(3)
    pos = pyautogui.position()
    print(f"  ✅ Capturado: ({pos.x}, {pos.y})")
    return (pos.x, pos.y)


# =============================================================================
# Menu interativo
# =============================================================================

def exibir_menu(coords_atuais: dict):
    print("\n" + "═" * 65)
    print("  CALIBRAÇÃO MANUAL — Automação Mtrix")
    print("═" * 65)
    print(f"  Arquivo: {COORDINATES_FILE}\n")

    grupos = [
        ("NAVEGAÇÃO", ["QLIKVIEW_CENTER", "ABA_GRAFICOS_RELATORIOS"]),
        ("BLOCOS DE FILTRO", ["BLOCO_PDV", "BLOCO_TEMPO", "BLOCO_AGENTE_DISTRIB", "BLOCO_PRODUTO"]),
        ("DROPDOWN BOOKMARK", ["DROPDOWN_BOOKMARK"]),
        ("BOOKMARKS", [
            'BOOKMARKS["ST - Grit"]', 'BOOKMARKS["ST - Grit - Mateus"]',
            'BOOKMARKS["CATEGORIA AR"]', 'BOOKMARKS["CATEGORIA AR - MATEUS"]',
            'BOOKMARKS["ST - DBs"]', 'BOOKMARKS["ST - DBs - Mateus"]',
            'BOOKMARKS["Produto"]', 'BOOKMARKS["Produto - Mateus"]',
        ]),
        ("BOTÕES DE EXPORT", ["EXPORT_PDV", "EXPORT_PRODUTO", "EXPORT_TEMPO_AGENTE"]),
        ("OUTROS", ["BOTAO_DUPLA_SETA", "LINK_PRESS_HERE", "DIALOGO_OK"]),
    ]

    indice_global = {}
    i = 1
    for grupo, chaves in grupos:
        print(f"  ── {grupo} {'─' * (45 - len(grupo))}")
        for chave in chaves:
            valor_atual = coords_atuais.get(chave, "não encontrado")
            # Label curto para exibição
            label = chave.replace('BOOKMARKS["', '').replace('"]', '') if "BOOKMARKS" in chave else chave
            print(f"  {i:>2}. {label:<38} {valor_atual}")
            indice_global[i] = chave
            i += 1
        print()

    print(f"  {i:>2}. Recalibrar TODOS os pontos")
    indice_global[i] = "__TODOS__"
    print(f"   0. Sair\n")
    return indice_global


def obter_ponto_por_chave(chave: str):
    """Retorna a tupla (chave, descricao, instrucao) para uma chave."""
    for p in PONTOS:
        if p[0] == chave:
            return p
    return None


def main():
    if not COORDINATES_FILE.exists():
        print(f"❌ Arquivo não encontrado: {COORDINATES_FILE}")
        sys.exit(1)

    while True:
        coords_atuais  = ler_coordenadas()
        indice_global  = exibir_menu(coords_atuais)
        total_opcoes   = max(indice_global.keys())

        try:
            escolha = int(input("  Escolha o número do ponto a recalibrar: ").strip())
        except ValueError:
            print("  Entrada inválida.")
            continue

        if escolha == 0:
            print("\n  Saindo. Até logo!\n")
            break

        if escolha not in indice_global:
            print(f"  Opção inválida. Escolha entre 0 e {total_opcoes}.")
            continue

        chave = indice_global[escolha]

        if chave == "__TODOS__":
            print("\n  Iniciando calibração completa de todos os pontos...\n")
            for ponto in PONTOS:
                novo_valor = capturar_posicao(ponto[1], ponto[2])
                if salvar_coordenada(ponto[0], novo_valor):
                    print(f"  💾 Salvo: {ponto[0]} = {novo_valor}")
            print("\n  ✅ Calibração completa finalizada!")
            input("  Pressione ENTER para voltar ao menu...")

        else:
            ponto = obter_ponto_por_chave(chave)
            if not ponto:
                print(f"  ⚠ Ponto '{chave}' não encontrado na lista.")
                continue

            novo_valor = capturar_posicao(ponto[1], ponto[2])

            if salvar_coordenada(chave, novo_valor):
                print(f"  💾 coordinates.py atualizado: {chave} = {novo_valor}")
            else:
                print(f"  ⚠ Não foi possível salvar automaticamente.")
                print(f"     Atualize manualmente: {chave} = {novo_valor}")

            input("\n  Pressione ENTER para voltar ao menu...")


if __name__ == "__main__":
    main()
