# =============================================================================
# download_watcher.py — Monitoramento e sincronização de downloads
# =============================================================================

import os
import sys
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

EXTENSOES_TEMP = {".crdownload", ".tmp", ".part", ".download"}

# Renomeação: bookmark → nome final do arquivo (sem extensão)
NOMES_ARQUIVO = {
    "ST - Grit":             "01.01 - Base Grit",
    "ST - Grit - Mateus":    "01.01 - Base Grit Mateus",
    "CATEGORIA AR":          "02.01 - Categorias Ar",
    "CATEGORIA AR - MATEUS": "02.01 - Categorias Ar Mateus",
    "ST - DBs":                    "03.01 - Actual Dbs",
    "ST - DBs - Mateus":           "03.01 - Actual Dbs Mateus",
    "Sell Out - DB's - Com CPF":         "07.01 - Actual Dbs CPF",
    "Sell Out - DB's - Com CPF - Mateus":"07.01 - Actual Dbs CPF Mateus",
    "Produto":               "05.01 - Produtos",
    "Produto - Mateus":      "05.01 - Produtos Mateus",
}


# ---------------------------------------------------------------------------
# Detecção da pasta de download
# ---------------------------------------------------------------------------

def get_download_dir() -> Path:
    """
    Retorna a pasta de downloads configurada ou detecta automaticamente.

    Ordem de tentativa:
      1. DOWNLOAD_DIR definido em config.py
      2. Pasta Downloads padrão do Windows (~/Downloads)
      3. Desktop do usuário
      4. Pasta temporária do sistema

    A pasta escolhida é logada para facilitar diagnóstico.
    """
    # Tenta ler do config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    try:
        from config import DOWNLOAD_DIR
        if DOWNLOAD_DIR:
            p = Path(DOWNLOAD_DIR)
            logger.info(f"Pasta de download (config): {p}")
            return p
    except ImportError:
        pass

    # Candidatas automáticas
    candidatas = [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
        Path(os.environ.get("TEMP", "C:/Temp")),
    ]

    for pasta in candidatas:
        if pasta.exists():
            logger.info(f"Pasta de download detectada automaticamente: {pasta}")
            return pasta

    # Fallback final
    fallback = Path.home()
    logger.warning(f"Nenhuma pasta padrão encontrada — usando: {fallback}")
    return fallback


def encontrar_arquivo_recente(
    pastas: list,
    extensoes: set = {".xlsx", ".xls", ".csv"},
    janela_segundos: float = 60
) -> Path | None:
    """
    Procura em várias pastas por um arquivo recente (criado nos últimos
    'janela_segundos' segundos). Útil quando não se sabe onde o QlikView salvou.

    Args:
        pastas:           Lista de Path para monitorar.
        extensoes:        Extensões de arquivo a considerar.
        janela_segundos:  Considera apenas arquivos criados recentemente.

    Returns:
        O arquivo mais recente encontrado, ou None.
    """
    agora    = time.time()
    mais_novo = None
    t_mais_novo = 0

    for pasta in pastas:
        if not pasta.exists():
            continue
        for f in pasta.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in extensoes:
                continue
            if _is_temp(f):
                continue
            try:
                t = f.stat().st_mtime
                if (agora - t) <= janela_segundos and t > t_mais_novo:
                    mais_novo    = f
                    t_mais_novo  = t
            except Exception:
                pass

    return mais_novo


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def snapshot_dir(directory: Path) -> set:
    return {f for f in directory.iterdir() if f.is_file() and not _is_temp(f)}


def _is_temp(path: Path) -> bool:
    return path.suffix.lower() in EXTENSOES_TEMP


def _has_temp(directory: Path) -> bool:
    try:
        return any(_is_temp(f) for f in directory.iterdir() if f.is_file())
    except Exception:
        return False


def _tamanho(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:
        return -1


# ---------------------------------------------------------------------------
# Fase 1: Aguardar início do download
# ---------------------------------------------------------------------------

def aguardar_inicio_download(
    before: set,
    directory: Path,
    timeout: float = 180,
    poll: float    = 1.0
) -> bool:
    """
    Aguarda sinal de início do download (arquivo temp ou novo arquivo).
    Monitora também pastas alternativas onde o QlikView pode salvar.
    """
    # Pastas alternativas para monitorar além da principal
    pastas_extras = [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
    ]
    pastas_extras = [p for p in pastas_extras if p.exists() and p != directory]

    logger.info(
        f"Monitorando início do download (timeout={timeout}s):\n"
        f"  Principal: {directory}\n"
        + ("  Extras: " + ", ".join(str(p) for p in pastas_extras) if pastas_extras else "")
    )

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            # Verifica pasta principal
            atuais  = set(directory.iterdir()) if directory.exists() else set()
            tem_tmp = any(_is_temp(f) for f in atuais if f.is_file())
            novos   = {f for f in atuais if f.is_file() and not _is_temp(f)} - before

            if tem_tmp or novos:
                logger.info(f"✔ Download iniciado detectado em: {directory}")
                return True

            # Verifica pastas extras (QlikView pode salvar em outro lugar)
            arquivo_extra = encontrar_arquivo_recente(pastas_extras, janela_segundos=10)
            if arquivo_extra:
                logger.info(f"✔ Arquivo detectado em pasta alternativa: {arquivo_extra}")
                return True

        except Exception as e:
            logger.debug(f"Erro ao verificar pasta: {e}")

        elapsed = timeout - (deadline - time.time())
        if int(elapsed) % 30 == 0 and int(elapsed) > 0:
            logger.info(f"  ... aguardando download iniciar ({int(elapsed)}s / {timeout}s)")

        time.sleep(poll)

    logger.warning(f"⚠ Download não detectado em {timeout}s.")
    return False


# ---------------------------------------------------------------------------
# Fase 2: Aguardar conclusão do download
# ---------------------------------------------------------------------------

def aguardar_conclusao_download(
    before: set,
    directory: Path,
    timeout: float = 1800,
    poll: float    = 2.0
) -> Path:
    """
    Aguarda o arquivo definitivo aparecer com tamanho estável.
    Também verifica pastas alternativas caso o QlikView tenha salvo em outro lugar.
    """
    pastas_extras = [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
    ]
    pastas_extras = [p for p in pastas_extras if p.exists() and p != directory]

    logger.info(f"Aguardando conclusão do download (timeout={timeout}s)...")
    deadline         = time.time() + timeout
    tamanho_anterior = {}

    while time.time() < deadline:
        time.sleep(poll)

        try:
            # Verifica pasta principal
            if not _has_temp(directory):
                novos = snapshot_dir(directory) - before
                for f in novos:
                    tam = _tamanho(f)
                    if tam > 0 and tam == tamanho_anterior.get(str(f), -1):
                        logger.info(f"✅ Download concluído: {f.name} ({tam:,} bytes)")
                        return f
                    tamanho_anterior[str(f)] = tam

            # Verifica pastas extras
            arquivo_extra = encontrar_arquivo_recente(pastas_extras, janela_segundos=30)
            if arquivo_extra:
                tam = _tamanho(arquivo_extra)
                chave = str(arquivo_extra)
                if tam > 0 and tam == tamanho_anterior.get(chave, -1):
                    logger.info(
                        f"✅ Download concluído em pasta alternativa:\n"
                        f"   {arquivo_extra} ({tam:,} bytes)"
                    )
                    return arquivo_extra
                tamanho_anterior[chave] = tam

        except Exception as e:
            logger.debug(f"Erro ao verificar conclusão: {e}")

    raise TimeoutError(f"Download não concluiu em {timeout}s.")


# ---------------------------------------------------------------------------
# Renomeação
# ---------------------------------------------------------------------------

def renomear_arquivo(arquivo: Path, bookmark: str, destino: Path = None) -> Path:
    """
    Renomeia o arquivo baixado e opcionalmente move para a pasta destino.

    Args:
        arquivo:  Arquivo baixado.
        bookmark: Nome do bookmark para determinar o nome final.
        destino:  Pasta onde salvar (None = mesma pasta do arquivo).
    """
    nome_base = NOMES_ARQUIVO.get(bookmark)
    if not nome_base:
        logger.warning(f"Sem mapeamento para bookmark '{bookmark}' — mantendo nome original.")
        return arquivo

    pasta_final = destino or arquivo.parent
    novo_nome   = pasta_final / f"{nome_base}{arquivo.suffix}"

    if novo_nome.exists():
        novo_nome.unlink()
        logger.info(f"Arquivo anterior removido: {novo_nome.name}")

    arquivo.rename(novo_nome)
    logger.info(f"✏ Renomeado: {arquivo.name} → {novo_nome.name}")
    return novo_nome


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class DownloadSession:
    """
    Gerencia um ciclo completo de download com renomeação automática.

    Args:
        bookmark:       Nome do bookmark (define o nome final do arquivo).
        download_dir:   Pasta monitorada (None = detecta automaticamente).
        timeout:        Tempo máximo total do download.
        inicio_timeout: Tempo máximo para detectar o início.
        destino:        Pasta onde salvar o arquivo renomeado (None = mesma pasta).
    """

    def __init__(
        self,
        bookmark: str,
        download_dir: Path  = None,
        timeout: float      = 1800,
        inicio_timeout: float = 180,
        destino: Path       = None,
    ):
        self.bookmark       = bookmark
        self.download_dir   = download_dir or get_download_dir()
        self.timeout        = timeout
        self.inicio_timeout = inicio_timeout
        self.destino        = destino
        self.iniciou        = False
        self.arquivo_final  : Path = None
        self._snapshot      = None

    def __enter__(self):
        self._snapshot = snapshot_dir(self.download_dir)
        logger.info(
            f"Snapshot pré-download: {len(self._snapshot)} arquivo(s) em {self.download_dir}"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False

        self.iniciou = aguardar_inicio_download(
            before    = self._snapshot,
            directory = self.download_dir,
            timeout   = self.inicio_timeout
        )

        if not self.iniciou:
            return False

        arquivo_bruto = aguardar_conclusao_download(
            before    = self._snapshot,
            directory = self.download_dir,
            timeout   = self.timeout
        )

        self.arquivo_final = renomear_arquivo(
            arquivo   = arquivo_bruto,
            bookmark  = self.bookmark,
            destino   = self.destino
        )
        return False