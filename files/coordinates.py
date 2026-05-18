# =============================================================================
# coordinates.py — Coordenadas de tela calibradas (2560x1440)
# =============================================================================
#
# Coordenadas calibradas em 15/05/2026.
# Para recalibrar um ponto específico, rode:
#
#     python calibrate_manual.py
#
# e siga as instruções na tela.
# =============================================================================


class Coords:

    # -------------------------------------------------------------------------
    # Centro da janela do QlikView (para dar foco inicial)
    # -------------------------------------------------------------------------
    QLIKVIEW_CENTER = (1280, 720)

    # -------------------------------------------------------------------------
    # Aba "Gráficos | Relatórios" na barra superior do QlikView
    # NOTA: a visão de Tabelas já vem ativa por padrão após esse clique.
    # -------------------------------------------------------------------------
    ABA_GRAFICOS_RELATORIOS = (653, 133)

    # -------------------------------------------------------------------------
    # Blocos de filtro (menu de ícones no topo da área de conteúdo)
    # -------------------------------------------------------------------------
    BLOCO_PDV            = (836, 261)
    BLOCO_TEMPO          = (726, 259)
    BLOCO_AGENTE_DISTRIB = (295, 257)
    BLOCO_PRODUTO        = (177, 258)

    # -------------------------------------------------------------------------
    # Dropdown "Select Bookmark" (barra superior do QlikView)
    # -------------------------------------------------------------------------
    DROPDOWN_BOOKMARK = (623, 101)

    # -------------------------------------------------------------------------
    # Posições de cada bookmark dentro da lista dropdown
    # -------------------------------------------------------------------------
    BOOKMARKS = {
        "ST - Grit":             (609, 389),
        "ST - Grit - Mateus":    (609, 411),
        "CATEGORIA AR":          (609, 143),
        "CATEGORIA AR - MATEUS": (609, 170),
        "ST - DBs":              (609, 337),
        "ST - DBs - Mateus":     (609, 362),
        "Produto":               (609, 291),
        "Produto - Mateus":      (609, 314),
    }

    # -------------------------------------------------------------------------
    # Botões de exportar Excel — 3 coordenadas distintas
    #
    #  EXPORT_PDV          → bloco PDV (sem dupla seta, botão deslocado à direita)
    #  EXPORT_PRODUTO      → bloco Produto (altura baixa, posição padrão)
    #  EXPORT_TEMPO_AGENTE → blocos Tempo e Agente de Distribuição (altura maior)
    # -------------------------------------------------------------------------
    EXPORT_PDV          = (992, 412)
    EXPORT_PRODUTO      = (976, 413)
    EXPORT_TEMPO_AGENTE = (977, 383)

    # -------------------------------------------------------------------------
    # Botão dupla seta (») — transpõe Ano/Mês de horizontal para vertical
    # Clicado apenas 1 vez: download 7 (bloco Produto, bookmark "Produto")
    # -------------------------------------------------------------------------
    BOTAO_DUPLA_SETA = (995, 413)

    # -------------------------------------------------------------------------
    # Diálogos do QlikView durante export
    #
    # LINK_PRESS_HERE → link "press here" do diálogo "opened in another window"
    # DIALOGO_OK      → botão OK do diálogo de loading "Excel Export"
    #
    # ← CALIBRAR: provoque os diálogos manualmente e use calibrate_manual.py
    # -------------------------------------------------------------------------
    LINK_PRESS_HERE = (175, 422)   # ← CALIBRAR
    DIALOGO_OK      = (357, 373)   # ← CALIBRAR