# Automação Mtrix — QlikView

Script de automação para download de relatórios do sistema Mtrix (QlikView).

---

## Estrutura do projeto

```
mtrix_automation/
├── main.py              # Orquestrador principal — rode este
├── config.py            # Configurações: credenciais, URLs, ordem dos downloads
├── coordinates.py       # Coordenadas de tela — DEVE ser calibrado
├── screen_utils.py      # Utilitários: espera, clique, drag-and-drop
├── download_watcher.py  # Sincronização de downloads
├── calibrate.py         # Helper para capturar coordenadas reais
├── requirements.txt     # Dependências Python
└── .env                 # Credenciais (NÃO commitar no Git)
```

---

## Instalação

```bash
# 1. Criar ambiente virtual (recomendado)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Instalar o navegador do Playwright
playwright install chromium
```

---

## Configuração

### 1. Credenciais (.env)

Crie um arquivo `.env` na raiz do projeto:

```
MTRIX_USER=seu_usuario
MTRIX_PASS=sua_senha
```

> ⚠️ Nunca coloque as credenciais diretamente no código ou commite o `.env`.

### 2. Calibração de coordenadas (OBRIGATÓRIO)

As coordenadas em `coordinates.py` são estimativas. Você **deve** calibrá-las
para a sua tela antes da primeira execução.

**Passo a passo:**

```bash
python calibrate.py
```

O script vai guiar você por cada elemento que precisa ser calibrado.
Siga as instruções na tela e cole os resultados em `coordinates.py`.

**Elementos a calibrar:**
- Aba "Gráficos | Relatórios"
- Botão "Tabelas"
- Blocos de filtro (PDV, Tempo, Agente de Distribuição, Produto)
- Dropdown "Select Bookmark"
- Cada item dentro do dropdown (8 bookmarks)
- Botão de exportar Excel
- Origem e destino do drag-and-drop

---

## Execução

```bash
python main.py
```

O script vai:
1. Abrir o Chrome e fazer login automaticamente
2. Selecionar o ambiente "VESTACY EH - CENSOR"
3. Navegar para Gráficos | Relatórios → Tabelas
4. Executar 8 downloads em sequência, aguardando cada um completar

**Não mova o mouse durante a execução.** Para abortar, mova o mouse
rapidamente para o canto superior-esquerdo da tela (failsafe do PyAutoGUI).

---

## Fluxo de downloads

| # | Bloco              | Bookmark             | Drag-and-drop |
|---|--------------------|----------------------|---------------|
| 1 | PDV                | ST - Grit            | Não           |
| 2 | PDV                | ST - Grit - Mateus   | Não           |
| 3 | Tempo              | CATEGORIA AR         | Não           |
| 4 | Tempo              | CATEGORIA AR - MATEUS| Não           |
| 5 | Agente de Distrib. | ST - DBs             | Não           |
| 6 | Agente de Distrib. | ST - DBs - Mateus    | Não           |
| 7 | Produto            | Produto              | **Sim**       |
| 8 | Produto            | Produto - Mateus     | Não           |

---

## Diagnóstico de erros

Se um download falhar, o script salva automaticamente um screenshot:
```
erro_download_7_Produto.png
```

Todos os logs ficam em:
```
automacao.log
```

---

## Problemas comuns

**"Elemento não encontrado"**
→ As coordenadas estão incorretas. Rode `calibrate.py` novamente.

**Download não detectado**
→ Verifique se a pasta de downloads em `config.py` está correta.
→ Aumente `DOWNLOAD_TIMEOUT` se a conexão for lenta.

**QlikView não responde ao clique**
→ Aumente o valor de `pyautogui.PAUSE` em `screen_utils.py` (linha 18).
→ Verifique se a janela do QlikView está em foco.

**Drag-and-drop não funciona**
→ Aumente o valor de `steps` em `realizar_drag_and_drop()` no `main.py`.
→ Tente aumentar a `duration` do drag.