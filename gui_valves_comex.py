# gui_valves_comex.py
# GUI: você cola a lista de NCM completos (um por linha) e consulta import/export no ComexStat

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
import pandas as pd

API_BASE = "http://127.0.0.1:8000"

def parse_ncms(text: str) -> list[str]:
    # aceita "8481.80.93" ou "84818093" -> converte para 8 dígitos sem pontos
    ncms = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        s = s.replace(".", "").replace(" ", "")
        if not s.isdigit():
            raise ValueError(f"NCM inválido: {line}")
        if len(s) != 8:
            raise ValueError(f"NCM deve ter 8 dígitos (ex: 84818093). Recebi: {line}")
        ncms.append(s)
    return sorted(list(set(ncms)))

def fetch():
    try:
        ncm_list = parse_ncms(ncm_text.get("1.0", tk.END))
        if not ncm_list:
            messagebox.showwarning("Atenção", "Informe pelo menos um NCM.")
            return

        payload = {
            "operacao": op_var.get(),
            "ano_inicial": int(ano_i.get()),
            "ano_final": int(ano_f.get()),
            "mes_inicial": int(mes_i.get()),
            "mes_final": int(mes_f.get()),
            "ncm_list": ncm_list,
            "detalhar_mes": det_mes.get(),
            "agrupar_por": ["ncm"] + ([extra_group.get()] if extra_group.get() != "nenhum" else []),
            "idioma": "pt",
        }

        r = requests.post(f"{API_BASE}/comex/ncm", json=payload, timeout=180)
        if r.status_code != 200:
            messagebox.showerror("Erro", f"{r.status_code}\n{r.text}")
            return

        data = r.json()["rows"]
        df = pd.DataFrame(data)

        # guarda
        fetch.last_df = df

        preview.delete("1.0", tk.END)
        preview.insert(tk.END, df.head(80).to_string(index=False))

        messagebox.showinfo("OK", f"Consulta concluída. Linhas: {len(df)} | NCMs: {len(ncm_list)}")

    except Exception as e:
        messagebox.showerror("Erro", str(e))

def export_csv():
    df = getattr(fetch, "last_df", None)
    if df is None or df.empty:
        messagebox.showwarning("Atenção", "Nada para exportar. Faça uma consulta primeiro.")
        return

    path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV", "*.csv")],
        title="Salvar CSV"
    )
    if not path:
        return

    df.to_csv(path, index=False, encoding="utf-8-sig")
    messagebox.showinfo("Salvo", f"CSV salvo em:\n{path}")

root = tk.Tk()
root.title("ComexStat – Válvulas por NCM (Import/Export)")
root.geometry("1050x700")

top = ttk.Frame(root, padding=10)
top.pack(fill="x")

op_var = tk.StringVar(value="imp")
det_mes = tk.BooleanVar(value=False)
extra_group = tk.StringVar(value="nenhum")

ttk.Label(top, text="Operação:").grid(row=0, column=0, sticky="w")
ttk.Radiobutton(top, text="Importação", variable=op_var, value="imp").grid(row=0, column=1, sticky="w")
ttk.Radiobutton(top, text="Exportação", variable=op_var, value="exp").grid(row=0, column=2, sticky="w")

ttk.Label(top, text="Ano ini:").grid(row=1, column=0, sticky="w")
ano_i = ttk.Entry(top, width=10); ano_i.insert(0, "2023"); ano_i.grid(row=1, column=1, sticky="w")

ttk.Label(top, text="Ano fim:").grid(row=1, column=2, sticky="w")
ano_f = ttk.Entry(top, width=10); ano_f.insert(0, "2025"); ano_f.grid(row=1, column=3, sticky="w")

ttk.Label(top, text="Mês ini:").grid(row=2, column=0, sticky="w")
mes_i = ttk.Entry(top, width=10); mes_i.insert(0, "1"); mes_i.grid(row=2, column=1, sticky="w")

ttk.Label(top, text="Mês fim:").grid(row=2, column=2, sticky="w")
mes_f = ttk.Entry(top, width=10); mes_f.insert(0, "12"); mes_f.grid(row=2, column=3, sticky="w")

ttk.Checkbutton(top, text="Detalhar por mês", variable=det_mes).grid(row=2, column=4, sticky="w", padx=10)

ttk.Label(top, text="Agrupar extra:").grid(row=3, column=0, sticky="w")
cmb = ttk.Combobox(top, textvariable=extra_group, values=["nenhum", "pais", "uf"], width=12, state="readonly")
cmb.grid(row=3, column=1, sticky="w")

ttk.Label(top, text="NCMs (1 por linha; aceita 8481.80.93):").grid(row=4, column=0, columnspan=5, sticky="w", pady=(8,0))

ncm_text = tk.Text(root, height=8, wrap="none")
ncm_text.pack(fill="x", padx=10)
ncm_text.insert("1.0", "8481.80.93\n8481.80.95\n")  # exemplo

btns = ttk.Frame(root, padding=10)
btns.pack(fill="x")
ttk.Button(btns, text="Buscar", command=fetch).pack(side="left")
ttk.Button(btns, text="Exportar CSV", command=export_csv).pack(side="left", padx=10)

preview = tk.Text(root, wrap="none")
preview.pack(fill="both", expand=True, padx=10, pady=10)

root.mainloop()
