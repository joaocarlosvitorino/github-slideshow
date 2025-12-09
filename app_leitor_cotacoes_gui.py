import os
import re
from typing import Dict, List, Tuple

import pandas as pd
import pdfplumber
from tkinter import Tk, ttk, filedialog, messagebox, StringVar, N, S, E, W

# Caminho raiz definido pelo usuário para armazenar PDFs e planilhas
PASTA_RAIZ = r"C:\Users\joaoc\OneDrive\00-MBA_BIG_DATA_AI\PROJETO HISTORICO DE PROPOSTAS ENVIADAS\PROJETO CODEX"

# Nome padrão da planilha principal
PLANILHA_PADRAO = "ALL QUOTES.xlsx"

# Ordem exata das colunas
CABECALHO_COLUNAS = [
    "Index",
    "File Name",
    "Quotation No",
    "Revision",
    "DATE",
    "To",
    "Company",
    "Address",
    "Phone",
    "Customer RefCode",
    "Project",
    "End User",
    "Representative",
    "SHIPPING METHOD",
    "SHIPPING TERM",
    "LEAD TIME",
    "PAYMENT TERM",
    "VALIDITY PERIOD",
    "NO ",
    "TAG NO.",
    "FULL DESCRIPTION",
    "MODEL Number",
    "Deviation :",
    "QTY",
    "UNIT PRICE",
    "TOTAL",
    "SUBTOTAL:",
    "PACKING CHARGE",
    "LOCAL CHARGE",
    "DOCUMENT CHARGE",
    "TOTAL FINAL",
    "CURRENCY",
    "PO",
]


# ------------------------ Funções auxiliares de parsing ------------------------


def extrair_cabecalho(texto: str) -> Dict[str, str]:
    """Extrai campos do cabeçalho usando expressões regulares simples."""
    padroes = {
        "Quotation No": r"Quotation\s*No\.?\s*[:\-]?\s*(.+)",
        "Revision": r"Revision\s*[:\-]?\s*(.+)",
        "DATE": r"Date\s*[:\-]?\s*(.+)",
        "To": r"To\s*[:\-]?\s*(.+)",
        "Company": r"Company\s*[:\-]?\s*(.+)",
        "Address": r"Address\s*[:\-]?\s*(.+)",
        "Phone": r"Phone\s*[:\-]?\s*(.+)",
        "Customer RefCode": r"Customer\s*RefCode\s*[:\-]?\s*(.+)",
        "Project": r"Project\s*[:\-]?\s*(.+)",
        "End User": r"End\s*User\s*[:\-]?\s*(.+)",
        "Representative": r"Representative\s*[:\-]?\s*(.+)",
        "SHIPPING METHOD": r"Shipping\s*Method\s*[:\-]?\s*(.+)",
        "SHIPPING TERM": r"Shipping\s*Term\s*[:\-]?\s*(.+)",
        "LEAD TIME": r"Lead\s*Time\s*[:\-]?\s*(.+)",
        "PAYMENT TERM": r"Payment\s*Term\s*[:\-]?\s*(.+)",
        "VALIDITY PERIOD": r"Validity\s*Period\s*[:\-]?\s*(.+)",
        "PO": r"PO\s*[:\-]?\s*(.+)",
    }
    resultado = {chave: "" for chave in padroes}
    for chave, regex in padroes.items():
        encontrado = re.search(regex, texto, re.IGNORECASE)
        if encontrado:
            resultado[chave] = encontrado.group(1).strip()
    return resultado


def normalizar_valor(valor: str) -> str:
    """Remove caracteres não numéricos exceto ponto e vírgula."""
    if not valor:
        return ""
    valor = valor.replace("\n", " ").strip()
    match = re.findall(r"[0-9.,]+", valor)
    return match[0] if match else valor


def extrair_resumo_financeiro(texto: str) -> Dict[str, str]:
    """Extrai valores de subtotal e totais no rodapé."""
    campos = {
        "SUBTOTAL:": r"Subtotal\s*[:\-]?\s*([0-9.,]+)",
        "PACKING CHARGE": r"Packing\s*Charge\s*[:\-]?\s*([0-9.,]+)",
        "LOCAL CHARGE": r"Local\s*Charge\s*[:\-]?\s*([0-9.,]+)",
        "DOCUMENT CHARGE": r"Document\s*Charge\s*[:\-]?\s*([0-9.,]+)",
        "TOTAL FINAL": r"Total\s*Final\s*[:\-]?\s*([0-9.,]+)",
        "CURRENCY": r"Currency\s*[:\-]?\s*([A-Z]{3}|USD|EUR|BRL|[A-Za-z]+)",
    }
    retorno = {chave: "" for chave in campos}
    for chave, regex in campos.items():
        encontrado = re.search(regex, texto, re.IGNORECASE)
        if encontrado:
            retorno[chave] = encontrado.group(1).strip()
    return retorno


def detectar_tabela_itens(pagina) -> List[List[str]]:
    """Tenta localizar tabela de itens na página."""
    tabelas = pagina.extract_tables() or []
    for tabela in tabelas:
        if not tabela:
            continue
        cabecalho = [c.strip().lower() if c else "" for c in tabela[0]]
        if any("no" == c or c.startswith("no") for c in cabecalho) and any(
            "qty" in c for c in cabecalho
        ):
            return tabela
    return []


def extrair_itens_tabela(tabela: List[List[str]]) -> List[Dict[str, str]]:
    """Extrai itens a partir de uma tabela identificada."""
    if not tabela or len(tabela) < 2:
        return []
    cabecalho = [col.strip().lower() if col else "" for col in tabela[0]]

    def pegar_valor(linha: List[str], chave: str) -> str:
        if chave in cabecalho:
            idx = cabecalho.index(chave)
            return (linha[idx] or "").strip()
        return ""

    itens = []
    for linha in tabela[1:]:
        if not any(linha):
            continue
        item = {
            "NO ": pegar_valor(linha, "no"),
            "TAG NO.": pegar_valor(linha, "tag no."),
            "FULL DESCRIPTION": pegar_valor(linha, "full description"),
            "MODEL Number": pegar_valor(linha, "model number"),
            "Deviation :": pegar_valor(linha, "deviation :"),
            "QTY": normalizar_valor(pegar_valor(linha, "qty")),
            "UNIT PRICE": normalizar_valor(pegar_valor(linha, "unit price")),
            "TOTAL": normalizar_valor(pegar_valor(linha, "total")),
        }
        itens.append(item)
    return itens


# ------------------------ Funções principais ------------------------


def carregar_planilha_existente(caminho_planilha: str) -> pd.DataFrame:
    """Carrega a planilha existente ou cria uma nova com cabeçalho padrão."""
    if os.path.exists(caminho_planilha):
        try:
            df = pd.read_excel(caminho_planilha, engine="openpyxl")
            df = df[CABECALHO_COLUNAS]
            return df
        except Exception as exc:  # noqa: BLE001
            print(f"Erro ao ler planilha existente: {exc}")
            messagebox.showerror(
                "Erro",
                f"Falha ao ler a planilha existente. Será criada uma nova.\n{exc}",
            )
    return pd.DataFrame(columns=CABECALHO_COLUNAS)


def extrair_dados_de_pdf(caminho_pdf: str) -> List[Dict[str, str]]:
    """Extrai dados completos de um PDF de proposta."""
    itens_proposta: List[Dict[str, str]] = []
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            texto_completo = "\n".join(page.extract_text() or "" for page in pdf.pages)
            cabecalho = extrair_cabecalho(texto_completo)
            resumo = extrair_resumo_financeiro(texto_completo)
            nome_arquivo = os.path.basename(caminho_pdf)

            tabela_encontrada = []
            for pagina in pdf.pages:
                tabela_encontrada = detectar_tabela_itens(pagina)
                if tabela_encontrada:
                    break
            itens_tabela = extrair_itens_tabela(tabela_encontrada)

            for item in itens_tabela:
                registro = {
                    "Index": None,
                    "File Name": nome_arquivo,
                    "Quotation No": cabecalho.get("Quotation No", ""),
                    "Revision": cabecalho.get("Revision", ""),
                    "DATE": cabecalho.get("DATE", ""),
                    "To": cabecalho.get("To", ""),
                    "Company": cabecalho.get("Company", ""),
                    "Address": cabecalho.get("Address", ""),
                    "Phone": cabecalho.get("Phone", ""),
                    "Customer RefCode": cabecalho.get("Customer RefCode", ""),
                    "Project": cabecalho.get("Project", ""),
                    "End User": cabecalho.get("End User", ""),
                    "Representative": cabecalho.get("Representative", ""),
                    "SHIPPING METHOD": cabecalho.get("SHIPPING METHOD", ""),
                    "SHIPPING TERM": cabecalho.get("SHIPPING TERM", ""),
                    "LEAD TIME": cabecalho.get("LEAD TIME", ""),
                    "PAYMENT TERM": cabecalho.get("PAYMENT TERM", ""),
                    "VALIDITY PERIOD": cabecalho.get("VALIDITY PERIOD", ""),
                    "NO ": item.get("NO ", ""),
                    "TAG NO.": item.get("TAG NO.", ""),
                    "FULL DESCRIPTION": item.get("FULL DESCRIPTION", ""),
                    "MODEL Number": item.get("MODEL Number", ""),
                    "Deviation :": item.get("Deviation :", ""),
                    "QTY": item.get("QTY", ""),
                    "UNIT PRICE": item.get("UNIT PRICE", ""),
                    "TOTAL": item.get("TOTAL", ""),
                    "SUBTOTAL:": resumo.get("SUBTOTAL:", ""),
                    "PACKING CHARGE": resumo.get("PACKING CHARGE", ""),
                    "LOCAL CHARGE": resumo.get("LOCAL CHARGE", ""),
                    "DOCUMENT CHARGE": resumo.get("DOCUMENT CHARGE", ""),
                    "TOTAL FINAL": resumo.get("TOTAL FINAL", ""),
                    "CURRENCY": resumo.get("CURRENCY", ""),
                    "PO": cabecalho.get("PO", ""),
                }
                itens_proposta.append(registro)
    except Exception as exc:  # noqa: BLE001
        print(f"Erro ao processar {caminho_pdf}: {exc}")
        messagebox.showerror("Erro", f"Falha ao ler o PDF {caminho_pdf}.\n{exc}")
    return itens_proposta


def atualizar_planilha(caminho_planilha: str, df_atualizado: pd.DataFrame) -> None:
    """Salva o DataFrame na planilha Excel."""
    try:
        df_atualizado.to_excel(caminho_planilha, index=False)
    except Exception as exc:  # noqa: BLE001
        print(f"Erro ao salvar planilha: {exc}")
        messagebox.showerror(
            "Erro",
            f"Não foi possível salvar a planilha em {caminho_planilha}.\n{exc}",
        )


def processar_pdfs(caminhos_pdfs: List[str], caminho_planilha: str) -> Tuple[pd.DataFrame, List[Dict[str, str]], List[str]]:
    """Processa PDFs, atualiza planilha e retorna novos dados e duplicados."""
    df_existente = carregar_planilha_existente(caminho_planilha)
    linhas_iniciais = len(df_existente)
    novos_registros: List[Dict[str, str]] = []
    arquivos_duplicados: List[str] = []

    arquivos_existentes = set(df_existente["File Name"].dropna().unique())

    for caminho_pdf in caminhos_pdfs:
        nome_pdf = os.path.basename(caminho_pdf)
        if nome_pdf in arquivos_existentes:
            arquivos_duplicados.append(nome_pdf)
            continue
        itens = extrair_dados_de_pdf(caminho_pdf)
        novos_registros.extend(itens)

    proximo_indice = int(df_existente["Index"].max() or 0) + 1
    for registro in novos_registros:
        registro["Index"] = proximo_indice
        proximo_indice += 1

    if novos_registros:
        df_novos = pd.DataFrame(novos_registros, columns=CABECALHO_COLUNAS)
        df_final = pd.concat([df_existente, df_novos], ignore_index=True)
    else:
        df_final = df_existente.copy()

    if not df_final.empty:
        df_final.sort_values("Index", inplace=True)

    atualizar_planilha(caminho_planilha, df_final)

    linhas_finais = len(df_final)
    print(
        f"Linhas iniciais: {linhas_iniciais} | Novas: {len(novos_registros)} | Finais: {linhas_finais}"
    )

    return df_final, novos_registros, arquivos_duplicados


# ------------------------ Interface gráfica ------------------------


class AplicacaoGUI:
    def __init__(self, master: Tk):
        self.master = master
        master.title("Leitor de Propostas FBV")
        master.geometry("1200x700")

        self.caminho_planilha = os.path.join(PASTA_RAIZ, PLANILHA_PADRAO)

        # Variáveis de exibição
        self.linhas_iniciais_var = StringVar(value="0")
        self.linhas_adicionadas_var = StringVar(value="0")
        self.linhas_finais_var = StringVar(value="0")
        self.pdfs_processados_var = StringVar(value="0")
        self.pdfs_ignorados_var = StringVar(value="0")

        self._construir_layout()

    def _construir_layout(self) -> None:
        botoes_frame = ttk.Frame(self.master, padding=10)
        botoes_frame.grid(row=0, column=0, sticky=W)

        ttk.Button(
            botoes_frame,
            text="Selecionar diretório com PDFs",
            command=self.selecionar_diretorio,
        ).grid(row=0, column=0, padx=5, pady=5)

        ttk.Button(
            botoes_frame,
            text="Selecionar arquivos PDFs",
            command=self.selecionar_arquivos,
        ).grid(row=0, column=1, padx=5, pady=5)

        resumo_frame = ttk.Frame(self.master, padding=10)
        resumo_frame.grid(row=1, column=0, sticky=W)

        self._criar_label_resumo(resumo_frame, "Linhas iniciais", self.linhas_iniciais_var, 0)
        self._criar_label_resumo(resumo_frame, "Linhas adicionadas", self.linhas_adicionadas_var, 1)
        self._criar_label_resumo(resumo_frame, "Linhas finais", self.linhas_finais_var, 2)
        self._criar_label_resumo(resumo_frame, "PDFs processados", self.pdfs_processados_var, 3)
        self._criar_label_resumo(resumo_frame, "PDFs ignorados", self.pdfs_ignorados_var, 4)

        tabela_frame = ttk.Frame(self.master, padding=10)
        tabela_frame.grid(row=2, column=0, sticky=(N, S, E, W))
        self.master.rowconfigure(2, weight=1)
        self.master.columnconfigure(0, weight=1)

        colunas = [
            "Index",
            "File Name",
            "Quotation No",
            "NO ",
            "FULL DESCRIPTION",
            "MODEL Number",
            "QTY",
            "UNIT PRICE",
            "TOTAL",
            "TOTAL FINAL",
            "CURRENCY",
        ]
        self.tree = ttk.Treeview(tabela_frame, columns=colunas, show="headings")
        for col in colunas:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, anchor="center")

        barra_vertical = ttk.Scrollbar(tabela_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=barra_vertical.set)
        self.tree.grid(row=0, column=0, sticky=(N, S, E, W))
        barra_vertical.grid(row=0, column=1, sticky=(N, S))

        tabela_frame.rowconfigure(0, weight=1)
        tabela_frame.columnconfigure(0, weight=1)

    def _criar_label_resumo(self, frame: ttk.Frame, texto: str, variavel: StringVar, coluna: int) -> None:
        ttk.Label(frame, text=f"{texto}:").grid(row=0, column=coluna * 2, padx=5, pady=2, sticky=W)
        ttk.Label(frame, textvariable=variavel, foreground="blue").grid(
            row=0, column=coluna * 2 + 1, padx=5, pady=2, sticky=W
        )

    def selecionar_diretorio(self) -> None:
        diretorio = filedialog.askdirectory(initialdir=PASTA_RAIZ, title="Selecione o diretório com PDFs")
        if not diretorio:
            return
        pdfs = [
            os.path.join(diretorio, f)
            for f in os.listdir(diretorio)
            if f.lower().endswith(".pdf")
        ]
        if not pdfs:
            messagebox.showinfo("Informação", "Nenhum PDF encontrado no diretório selecionado.")
            return
        self._processar_lista_pdfs(pdfs)

    def selecionar_arquivos(self) -> None:
        arquivos = filedialog.askopenfilenames(
            initialdir=PASTA_RAIZ,
            title="Selecione os PDFs",
            filetypes=[("Arquivos PDF", "*.pdf")],
        )
        if not arquivos:
            return
        self._processar_lista_pdfs(list(arquivos))

    def _processar_lista_pdfs(self, pdfs: List[str]) -> None:
        df_existente = carregar_planilha_existente(self.caminho_planilha)
        self.linhas_iniciais_var.set(str(len(df_existente)))

        df_final, novos_registros, duplicados = processar_pdfs(pdfs, self.caminho_planilha)

        self.linhas_adicionadas_var.set(str(len(novos_registros)))
        self.linhas_finais_var.set(str(len(df_final)))
        self.pdfs_processados_var.set(str(len(pdfs) - len(duplicados)))
        self.pdfs_ignorados_var.set(str(len(duplicados)))

        # Limpa tabela e insere novas linhas
        for item in self.tree.get_children():
            self.tree.delete(item)

        for registro in novos_registros:
            valores = [
                registro.get("Index"),
                registro.get("File Name"),
                registro.get("Quotation No"),
                registro.get("NO "),
                registro.get("FULL DESCRIPTION"),
                registro.get("MODEL Number"),
                registro.get("QTY"),
                registro.get("UNIT PRICE"),
                registro.get("TOTAL"),
                registro.get("TOTAL FINAL"),
                registro.get("CURRENCY"),
            ]
            self.tree.insert("", "end", values=valores)

        if duplicados:
            messagebox.showinfo(
                "Duplicados",
                "Os seguintes PDFs já estavam na planilha e foram ignorados:\n" + "\n".join(duplicados),
            )


# ------------------------ Execução do aplicativo ------------------------


def main() -> None:
    raiz = Tk()
    app = AplicacaoGUI(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
