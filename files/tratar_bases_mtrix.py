import shutil
import pandas as pd
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from files.config import DOWNLOAD_DIR

# ============================================================
# CONFIGURAÇÕES — ajuste apenas esta seção se necessário
# ============================================================

# Pasta onde estão os arquivos exportados da Mtrix
PASTA_BASES = Path(DOWNLOAD_DIR) if DOWNLOAD_DIR else Path.home() / "Downloads"

# Pasta de destino final
PASTA_DESTINO = Path(r"C:\Users\yurib\Downloads\Vestacy\Histórico Mtrix")

# Linhas em branco a remover logo após o cabeçalho (índice 0 = 1ª linha de dados).
# Não existe mais merge com base Mateus — só a limpeza das linhas extras.
# Linhas em branco a remover logo após o cabeçalho.
# "01.01 - Base Grit" NÃO tem linha em branco — só renomeia e move.
LINHAS_EXTRAS = {
    "02.01 - Categorias Ar": [0],
    "05.01 - Produtos":      [0],
    "03.01 - Actual Dbs":    [0, 1, 2, 3],
    "07.01 - Actual Dbs CPF":[0, 1, 2, 3],
}

# Bases a processar (sem versões Mateus separadas — dados já consolidados no filtro)
BASES = [
    "01.01 - Base Grit",
    "02.01 - Categorias Ar",
    "03.01 - Actual Dbs",
    "07.01 - Actual Dbs CPF",
    "05.01 - Produtos",
]

# ============================================================
# FUNÇÕES
# ============================================================

def caminho(nome_base: str) -> Path:
    return PASTA_BASES / f"{nome_base}.xlsx"


def celula_para_texto(cell) -> str:
    """Converte célula para texto preservando precisão numérica."""
    from openpyxl.styles.numbers import is_date_format
    value = cell.value
    if value is None:
        return ""
    fmt = cell.number_format or ""
    if is_date_format(fmt):
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y")
        try:
            from openpyxl.utils.datetime import from_excel
            return from_excel(value).strftime("%d/%m/%Y")
        except Exception:
            return str(value)
    if isinstance(value, float):
        return f"{value:.15g}".replace(".", ",")
    if isinstance(value, int):
        return str(value)
    return str(value)


def carregar_base(nome_base: str) -> pd.DataFrame:
    """Carrega o Excel preservando precisão numérica."""
    arquivo = caminho(nome_base)
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
    wb = load_workbook(arquivo, data_only=True)
    ws = wb.active
    linhas = list(ws.iter_rows())
    if not linhas:
        raise ValueError(f"Arquivo vazio: {arquivo}")
    cabecalho = [cell.value if cell.value is not None else "" for cell in linhas[0]]
    dados = [[celula_para_texto(cell) for cell in row] for row in linhas[1:]]
    df = pd.DataFrame(dados, columns=cabecalho)
    print(f"  Carregado '{nome_base}.xlsx' → {len(df)} linhas")
    return df


def remover_linhas_extras(df: pd.DataFrame, nome_base: str) -> pd.DataFrame:
    """Remove linhas em branco logo abaixo do cabeçalho."""
    indices = LINHAS_EXTRAS.get(nome_base, [])
    if indices:
        validos = [i for i in indices if i < len(df)]
        df = df.drop(index=validos).reset_index(drop=True)
        print(f"  Removidas {len(validos)} linha(s) extras em '{nome_base}'")
    return df


def salvar_base(df: pd.DataFrame, nome_base: str):
    """Salva o DataFrame como texto puro, preservando o arquivo original."""
    arquivo = caminho(nome_base)
    wb = load_workbook(arquivo)
    ws = wb.active
    ws.delete_rows(1, ws.max_row)
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), start=1):
        for c_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx,
                           value=str(value) if pd.notna(value) else "")
            cell.data_type = "s"
    wb.save(arquivo)
    print(f"  Salvo '{nome_base}.xlsx' com {len(df)} linhas")


def mover_para_destino(nome_base: str):
    """Move o arquivo tratado para a pasta de destino."""
    PASTA_DESTINO.mkdir(parents=True, exist_ok=True)
    origem  = caminho(nome_base)
    destino = PASTA_DESTINO / f"{nome_base}.xlsx"
    shutil.move(str(origem), str(destino))
    print(f"  Movido para: {destino}\n")


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():
    print("=" * 60)
    print("TRATAMENTO DAS BASES MTRIX")
    print("=" * 60)

    for nome_base in BASES:
        print(f"\n>>> Processando: '{nome_base}'")

        if nome_base not in LINHAS_EXTRAS:
            # Nenhuma linha extra para remover — move diretamente (sem load/save)
            print(f"  Sem tratamento necessário — movendo direto para destino...")
            mover_para_destino(nome_base)
            continue

        df = carregar_base(nome_base)
        df = remover_linhas_extras(df, nome_base)
        salvar_base(df, nome_base)
        mover_para_destino(nome_base)

    print("=" * 60)
    print(f"Concluído! {len(BASES)} bases salvas em:")
    print(f"  {PASTA_DESTINO}")
    print("=" * 60)


if __name__ == "__main__":
    main()