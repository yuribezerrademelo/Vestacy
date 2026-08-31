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
    # Tela de login (https://login.mtrix.com.br)
    # ← CALIBRAR com a página de login aberta no Chrome em tela cheia
    # -------------------------------------------------------------------------
    LOGIN_CAMPO_USUARIO = (1300, 223)   # ← CALIBRAR: campo de usuário
    LOGIN_CAMPO_SENHA   = (1300, 301)   # ← CALIBRAR: campo de senha
    LOGIN_BOTAO_ENTRAR  = (1300, 420)   # ← CALIBRAR: botão "Entrar"
    LOGIN_AMBIENTE      = (1089, 203)   # ← CALIBRAR: item "VESTACY EH - CENSOR"

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
    # Coordenadas de fallback: usadas se o teclado (End+Up) falhar.
    # Recalibrar com calibrate_manual.py se as posições mudarem.
    BOOKMARKS = {
        "ST - Grit":                  (609, 411),   # ← CALIBRAR
        "CATEGORIA AR":               (609, 143),
        "ST - DBs":                   (609, 337),
        "Sell Out - DB's - Com CPF": (609, 362),   # ← CALIBRAR
        "Produto":                    (609, 291),
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
    # -------------------------------------------------------------------------
    # Relatórios Personalizados — fluxo exclusivo do bookmark ST - Grit
    #
    # ← CALIBRAR todos os pontos abaixo com calibrate_manual.py
    # -------------------------------------------------------------------------

    # Bloco "Relatórios Personalizados" na barra de blocos
    BLOCO_RELATORIOS_PERSONALIZADOS = (945, 259)   
    # Botão "PDV" dentro da view de Relatórios Personalizados
    RELAT_PERSONALIZADOS_PDV        = (426, 469)   
    # Cabeçalho "Cód. Cliente" (posição original antes do drag)
    HEADER_COD_CLIENTE              = (553, 572)   
    # Destino do drag de "Cód. Cliente"
    HEADER_COD_CLIENTE_DESTINO      = (339, 572)   
    # Cabeçalho "Ano/Mês (Num)" (após o drag de Cód. Cliente)
    HEADER_ANO_MES                  = (887, 572)   
    # Destino do drag de "Ano/Mês (Num)"
    HEADER_ANO_MES_DESTINO          = (430, 572)   
    # Posição para right-click em "Ano/Mês (Num)" (após os dois drags)
    HEADER_ANO_MES_FINAL            = (430, 572)   
    # "Collapse all" no menu de contexto do right-click
    MENU_COLLAPSE_ALL               = (464, 659)   
    # Botão de exportar Excel na view de Relatórios Personalizados → PDV
    EXPORT_RELAT_PDV                = (975, 548)   
    DIALOGO_OK      = (1909, 695)   # ← CALIBRAR