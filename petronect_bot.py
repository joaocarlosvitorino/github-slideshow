"""Automation helper for Petronect opportunities using Selenium and a pre-opened Chrome instance.

This script opens the public Petronect listing page, searches for opportunities by the
desired object text (defaults to "Válvula"), iterates through all pages, downloads item
details and attachments, and saves both a per-opportunity workbook and a master log.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import shutil


def _ensure_dependency(module: str, install_hint: str) -> None:
    """Exit with a friendly message if a dependency is missing."""
    if importlib.util.find_spec(module) is None:
        raise SystemExit(
            f"Missing dependency: {module}. Install it with:\n{install_hint}"
        )


_ensure_dependency("selenium", f"{sys.executable} -m pip install selenium==4.15.2")
_ensure_dependency("openpyxl", f"{sys.executable} -m pip install openpyxl")
_ensure_dependency("pandas", f"{sys.executable} -m pip install pandas")

import openpyxl
import pandas as pd
from openpyxl.styles import Font, PatternFill
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

@dataclass
class BotConfig:
    petronect_url: str = (
        "https://www.petronect.com.br/irj/go/km/docs/pccshrcontent/"
        "Site%20Content%20(Legacy)/Portal2018/en/lista_licitacoes_publicadas_ft.html"
    )
    root_path: Path = Path.home() / "petronect"
    delay_seconds: float = 2.0
    chrome_debug_port: int = 9222
    download_age_seconds: int = 90

    def ensure_paths(self) -> None:
        self.root_path.mkdir(parents=True, exist_ok=True)


def log(message: str, level: str = "INFO") -> None:
    icons = {"INFO": "🔵", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{icons.get(level, '•')} [{timestamp}] {message}")


def criar_pasta(config: BotConfig, opp_num: str) -> Path:
    path = config.root_path / opp_num
    path.mkdir(parents=True, exist_ok=True)
    log(f"Pasta: {opp_num}/", "SUCCESS")
    return path


def criar_excel(opp_num: str, folder: Path, data: Dict[str, Dict]) -> Optional[Path]:
    try:
        file_path = folder / f"{opp_num}.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Dados"

        fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        font = Font(color="FFFFFF", bold=True)

        ws["A1"] = "Campo"
        ws["B1"] = "Valor"
        ws["A1"].fill = ws["B1"].fill = fill
        ws["A1"].font = ws["B1"].font = font

        row = 2
        for key, value in data.get("header", {}).items():
            ws[f"A{row}"] = key.replace("_", " ").title()
            ws[f"B{row}"] = value
            row += 1

        if data.get("items"):
            row += 1
            ws[f"A{row}"] = "ITENS"
            ws[f"A{row}"].font = Font(bold=True, size=14)
            row += 1

            for col, header in enumerate(["Item", "Descrição", "Qtd", "Unidade"], 1):
                cell = ws.cell(row, col)
                cell.value = header
                cell.fill = fill
                cell.font = font

            row += 1
            for item in data["items"]:
                ws[f"A{row}"] = item.get("item_number", "")
                ws[f"B{row}"] = item.get("description", "")
                ws[f"C{row}"] = item.get("quantity", "")
                ws[f"D{row}"] = item.get("unit", "")
                row += 1

        for column, width in [("A", 25), ("B", 50), ("C", 15), ("D", 15)]:
            ws.column_dimensions[column].width = width

        wb.save(file_path)
        log(f"Excel: {file_path.name}", "SUCCESS")
        return file_path
    except Exception as exc:  # noqa: BLE001
        log(f"Erro Excel: {exc}", "ERROR")
        return None


def atualizar_master(config: BotConfig, opp_num: str, data: Dict[str, Dict]) -> None:
    try:
        master = config.root_path / "PETRONECT_MASTER.xlsx"

        if master.exists():
            workbook = openpyxl.load_workbook(master)
            ws = workbook.active
        else:
            workbook = openpyxl.Workbook()
            ws = workbook.active
            ws.title = "Oportunidades"

            fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            font = Font(color="FFFFFF", bold=True)

            headers = ["Oportunidade", "Objeto", "Início", "Fim", "Itens", "Data"]
            for col, header in enumerate(headers, 1):
                cell = ws.cell(1, col)
                cell.value = header
                cell.fill = fill
                cell.font = font

        row = ws.max_row + 1
        ws[f"A{row}"] = opp_num
        ws[f"B{row}"] = data.get("header", {}).get("purchasing_object", "")
        ws[f"C{row}"] = data.get("header", {}).get("start_date", "")
        ws[f"D{row}"] = data.get("header", {}).get("end_date", "")
        ws[f"E{row}"] = len(data.get("items", []))
        ws[f"F{row}"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        for column, width in [
            ("A", 20),
            ("B", 40),
            ("C", 15),
            ("D", 15),
            ("E", 10),
            ("F", 18),
        ]:
            ws.column_dimensions[column].width = width

        workbook.save(master)
        log("Master atualizada", "SUCCESS")
    except Exception as exc:  # noqa: BLE001
        log(f"Erro master: {exc}", "ERROR")


class PetronectBot:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.log_file = self.config.root_path / "processed.json"
        self.first_run_file = self.config.root_path / "first_run.flag"
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self.processed: List[str] = self.load_log()
        self.first_run: bool = not self.first_run_file.exists()

    def load_log(self) -> List[str]:
        legacy = Path("processed.json")
        if self.log_file.exists():
            with open(self.log_file) as file:
                return json.load(file)
        if legacy.exists():
            with open(legacy) as file:
                return json.load(file)
        return []

    def save_log(self, opp: str) -> None:
        if opp not in self.processed:
            self.processed.append(opp)
            with open(self.log_file, "w") as file:
                json.dump(self.processed, file, indent=2)

    def conectar_chrome_aberto(self) -> bool:
        try:
            log("Conectando ao Chrome aberto...")

            options = webdriver.ChromeOptions()
            options.add_experimental_option(
                "debuggerAddress", f"localhost:{self.config.chrome_debug_port}"
            )
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 15)

            log("✅ Conectado ao Chrome!", "SUCCESS")
            log(f"Página atual: {self.driver.title}")
            return True

        except Exception as exc:  # noqa: BLE001
            log(f"Erro ao conectar: {exc}", "ERROR")
            log("\n⚠️ Certifique-se de que:")
            log("1. Você iniciou o Chrome com depuração remota (use --open-chrome)")
            log("2. O Chrome ainda está aberto")
            return False

    def navegar_para_lista(self) -> bool:
        if not self.driver:
            log("Driver não inicializado", "ERROR")
            return False

        try:
            log("🔗 Abrindo lista pública do Petronect...")
            self.driver.get(self.config.petronect_url)
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(self.config.delay_seconds)
            log("✅ Página de listagem carregada", "SUCCESS")
            return True
        except Exception as exc:  # noqa: BLE001
            log(f"Erro ao abrir listagem: {exc}", "ERROR")
            return False

    def aplicar_filtro_objeto(self, termo: str = "Válvula") -> None:
        if not self.driver:
            log("Driver não inicializado", "ERROR")
            return

        log(f"🎯 Aplicando filtro de Objeto: {termo}")
        candidatos = [
            "//label[contains(translate(., 'OBJETO', 'objeto'), 'objeto')]/following::input[1]",
            "//input[contains(@name, 'obj') or contains(@id, 'obj')]",
            "//input[contains(@placeholder, 'Objeto') or contains(@aria-label, 'Objeto')]",
            "//input[@type='text']",
        ]
        campo_objeto = None
        for xpath in candidatos:
            try:
                campo_objeto = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                if campo_objeto:
                    break
            except Exception:
                continue

        if not campo_objeto:
            log("⚠️ Campo 'Objeto' não localizado; seguindo sem filtro.", "WARNING")
            return

        try:
            campo_objeto.clear()
            campo_objeto.send_keys(termo)
            time.sleep(0.5)
        except Exception as exc:  # noqa: BLE001
            log(f"Erro ao preencher filtro: {exc}", "ERROR")
            return

        botoes_ok = [
            "//button[normalize-space(text())='OK']",
            "//input[@type='submit' and (contains(@value,'OK') or contains(@value,'Ok'))]",
            "//button[contains(translate(., 'ok', 'OK'), 'OK')]",
        ]
        for xpath in botoes_ok:
            try:
                botao = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                botao.click()
                time.sleep(self.config.delay_seconds)
                log("✅ Filtro aplicado", "SUCCESS")
                return
            except Exception:
                continue

        log("⚠️ Botão de confirmação do filtro não localizado; resultados podem não estar filtrados.", "WARNING")

    def coletar_oportunidades_pagina(self) -> List[str]:
        if not self.driver:
            log("Driver não inicializado", "ERROR")
            return []

        oportunidades: List[str] = []
        try:
            linhas = self.driver.find_elements(By.XPATH, "//table//tr[td]")
            for linha in linhas:
                try:
                    celulas = linha.find_elements(By.TAG_NAME, "td")
                    if not celulas:
                        continue
                    texto = celulas[0].text.strip()
                    numero = re.search(r"\d+", texto)
                    if numero:
                        oportunidades.append(numero.group(0))
                except Exception:
                    continue

            oportunidades_unicas = list(dict.fromkeys(oportunidades))
            log(f"📄 {len(oportunidades_unicas)} oportunidades nesta página", "INFO")
            return oportunidades_unicas
        except Exception as exc:  # noqa: BLE001
            log(f"Erro ao coletar oportunidades: {exc}", "ERROR")
            return []

    def abrir_oportunidade_da_lista(self, opp: str) -> Optional[str]:
        if not self.driver or not self.wait:
            log("Driver não inicializado", "ERROR")
            return None

        seletores = [
            f"//a[contains(text(), '{opp}')]",
            f"//td[contains(text(), '{opp}')]/a",
            f"//td[contains(text(), '{opp}')]",
        ]

        for xpath in seletores:
            try:
                elemento = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                handle_atual = self.driver.current_window_handle
                handles_antes = set(self.driver.window_handles)
                elemento.click()
                time.sleep(self.config.delay_seconds)

                handles_depois = set(self.driver.window_handles)
                novos = handles_depois - handles_antes
                if novos:
                    novo_handle = novos.pop()
                    self.driver.switch_to.window(novo_handle)
                    log(f"🆕 Oportunidade {opp} aberta em nova aba", "INFO")
                    return handle_atual

                log(f"➡️ Navegando para detalhes da oportunidade {opp}", "INFO")
                return handle_atual
            except Exception:
                continue

        log(f"⚠️ Não foi possível abrir a oportunidade {opp}", "WARNING")
        return None

    def voltar_para_lista(self, lista_handle: str) -> None:
        if not self.driver:
            return
        try:
            if lista_handle != self.driver.current_window_handle:
                self.driver.close()
                self.driver.switch_to.window(lista_handle)
            else:
                self.driver.back()
            time.sleep(self.config.delay_seconds)
        except Exception:
            pass

    def _texto_depois_de_label(self, termos: List[str]) -> str:
        if not self.driver:
            return ""
        lower_from = "ABCDEFGHIJKLMNOPQRSTUVWXYZÁÂÃÀÉÊÍÓÔÕÚÇ"
        lower_to = "abcdefghijklmnopqrstuvwxyzáâãàéêíóôõúç"
        for termo in termos:
            xpath = (
                f"//*[contains(translate(normalize-space(text()), '{lower_from}', '{lower_to}'), "
                f"'{termo.lower()}')]/following::*[1]"
            )
            try:
                elemento = self.driver.find_element(By.XPATH, xpath)
                valor = elemento.text.strip()
                if valor:
                    return valor
            except Exception:
                continue
        return ""

    def extrair_dados(self) -> Dict[str, Dict]:
        data: Dict[str, Dict] = {"header": {}, "items": []}
        if not self.driver:
            log("Driver não inicializado", "ERROR")
            return data

        try:
            data["header"]["opportunity_number"] = self._texto_depois_de_label(
                ["opportunity", "oportunidade"]
            )
            data["header"]["purchasing_object"] = self._texto_depois_de_label(
                ["purchasing object", "objeto"]
            )
            data["header"]["start_date"] = self._texto_depois_de_label(
                ["start date", "início", "inicio"]
            )
            data["header"]["end_date"] = self._texto_depois_de_label(["end date", "fim", "encerramento"])

            tabelas = self.driver.find_elements(
                By.XPATH,
                "//table[.//th[contains(translate(normalize-space(.),'ITEM','item'),'item')]]",
            )
            alvo = tabelas[0] if tabelas else None
            if not alvo:
                alvo = self.driver.find_element(By.XPATH, "//table")

            linhas = alvo.find_elements(By.XPATH, ".//tr[position()>1]")
            for linha in linhas:
                celulas = linha.find_elements(By.TAG_NAME, "td")
                if celulas:
                    data["items"].append(
                        {
                            "item_number": celulas[0].text if len(celulas) > 0 else "",
                            "description": celulas[1].text if len(celulas) > 1 else "",
                            "quantity": celulas[2].text if len(celulas) > 2 else "",
                            "unit": celulas[3].text if len(celulas) > 3 else "",
                        }
                    )
            log(f"📋 {len(data['items'])} itens extraídos", "SUCCESS")
            return data

        except Exception as exc:  # noqa: BLE001
            log(f"Erro ao extrair dados: {exc}", "WARNING")
            return data

    def baixar_anexos(self, folder: Path) -> bool:
        if not self.driver:
            log("Driver não inicializado", "ERROR")
            return False

        try:
            try:
                attach_btn = self.driver.find_element(
                    By.XPATH,
                    "//button[contains(translate(., 'ANEXO', 'anexo'), 'anexo') or "
                    "contains(@title, 'Attachment') or contains(@class, 'attach')]",
                )
                attach_btn.click()
                time.sleep(self.config.delay_seconds)
            except Exception:
                log("ℹ️ Botão de anexos não encontrado; tentando links diretos.", "INFO")

            links = self.driver.find_elements(
                By.XPATH,
                "//a[contains(@href, 'download') or contains(translate(text(),'ANEXO','anexo'),'anexo') "
                "or contains(translate(text(),'DOWNLOAD','download'),'download')]",
            )
            log(f"📎 {len(links)} anexos encontrados")

            for index, link in enumerate(links, 1):
                link.click()
                log(f"⬇️ Baixando {index}/{len(links)}...")
                time.sleep(3)

            time.sleep(2)
            downloads = Path.home() / "Downloads"
            now = time.time()

            if downloads.exists():
                for file in downloads.iterdir():
                    if file.suffix.lower() in {".pdf", ".xlsx", ".xls", ".doc", ".docx", ".zip"}:
                        if now - file.stat().st_mtime < self.config.download_age_seconds:
                            try:
                                destination = folder / file.name
                                file.rename(destination)
                                log(f"📥 {file.name}", "SUCCESS")
                            except Exception:
                                pass

            return True
        except Exception as exc:  # noqa: BLE001
            log(f"Anexos: {exc}", "WARNING")
            return False

    def processar_oportunidade(self, opp: str) -> bool:
        log(f"\n{'=' * 60}")
        log(f"🎯 OPORTUNIDADE {opp}")
        log(f"{'=' * 60}")

        if opp in self.processed:
            log("Já processada!", "WARNING")
            return False

        try:
            folder = criar_pasta(self.config, opp)
            data = self.extrair_dados()
            self.baixar_anexos(folder)

            criar_excel(opp, folder, data)
            atualizar_master(self.config, opp, data)

            self.save_log(opp)

            log(f"{'=' * 60}")
            log(f"✅ {opp} CONCLUÍDA!", "SUCCESS")
            log(f"{'=' * 60}\n")

            return True

        except Exception as exc:  # noqa: BLE001
            log(f"❌ Erro: {exc}", "ERROR")
            try:
                if self.driver:
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except Exception:
                pass
            return False

    def processar_oportunidade_da_lista(self, opp: str) -> bool:
        handle_lista = self.abrir_oportunidade_da_lista(opp)
        if not handle_lista:
            return False
        try:
            sucesso = self.processar_oportunidade(opp)
        finally:
            self.voltar_para_lista(handle_lista)
        return sucesso

    def ir_para_proxima_pagina(self) -> bool:
        if not self.driver or not self.wait:
            return False

        seletores = [
            "//a[contains(translate(., 'PRÓXIMA', 'próxima'), 'próxima')]",
            "//a[contains(translate(., 'PROXIMA', 'proxima'), 'proxima')]",
            "//a[contains(translate(., 'NEXT', 'next'), 'next')]",
            "//button[contains(., '>') or contains(., '→')]",
        ]

        for xpath in seletores:
            try:
                botao = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                disabled_attr = botao.get_attribute("disabled")
                if disabled_attr or "disabled" in botao.get_attribute("class", "").lower():
                    continue
                botao.click()
                time.sleep(self.config.delay_seconds)
                log("➡️ Avançando para próxima página", "INFO")
                return True
            except Exception:
                continue
        return False

    def executar_varredura(self, termo_objeto: str = "Válvula") -> None:
        log("\n" + "=" * 80)
        log(f"🚀 Varredura por oportunidades com objeto '{termo_objeto}'")
        log("=" * 80 + "\n")

        if not self.conectar_chrome_aberto():
            log("\n❌ Não foi possível conectar ao Chrome", "ERROR")
            log("Execute o comando: python petronect_bot.py --open-chrome")
            return

        if not self.navegar_para_lista():
            return

        self.aplicar_filtro_objeto(termo_objeto)

        pagina = 1
        sucesso = 0
        falhas = 0

        while True:
            log(f"\n🧭 Página {pagina}")
            opps = self.coletar_oportunidades_pagina()
            if not opps:
                log("ℹ️ Nenhuma oportunidade nesta página.", "WARNING")

            for index, opp in enumerate(opps, 1):
                log(f"\n[{index}/{len(opps)}] Preparando oportunidade {opp}")
                if opp in self.processed:
                    log(f"⏭️ {opp} já registrada no log, pulando.", "INFO")
                    continue
                if self.processar_oportunidade_da_lista(opp):
                    sucesso += 1
                    log(f"✅ Downloads concluídos para {opp}", "SUCCESS")
                else:
                    falhas += 1
                    log(f"❌ Falha ao processar {opp}", "ERROR")

            if not self.ir_para_proxima_pagina():
                break
            pagina += 1

        if self.first_run:
            with open(self.first_run_file, "w") as file:
                json.dump({"date": datetime.now().isoformat(), "processed": len(self.processed)}, file)
            log("\n✅ Primeira execução marcada como completa!", "SUCCESS")

        log("\n🎉 Todas as páginas percorridas e downloads finalizados.", "SUCCESS")
        log("\n" + "=" * 80)
        log("📈 RESUMO FINAL")
        log("=" * 80)
        log(f"✅ Processadas com sucesso: {sucesso}", "SUCCESS")
        log(f"❌ Falhas: {falhas}", "ERROR" if falhas else "INFO")
        log(f"📊 Total no histórico: {len(self.processed)}")
        log("=" * 80 + "\n")


def find_chrome_executable() -> Optional[str]:
    candidates = []
    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
        )
    else:
        candidates.extend(["google-chrome", "chromium-browser", "chromium", "google-chrome-stable"])

    for path in candidates:
        chrome_path = Path(path)
        if chrome_path.is_file():
            return str(chrome_path)
        try:
            resolved = shutil.which(path)  # type: ignore[name-defined]
            if resolved:
                return resolved
        except Exception:
            continue
    return None


def abrir_chrome_debug(config: BotConfig) -> bool:
    chrome_exe = find_chrome_executable()
    if not chrome_exe:
        log("❌ Chrome não encontrado! Informe o caminho com --chrome-path.", "ERROR")
        return False

    user_data = Path.cwd() / "chrome_profile"
    user_data.mkdir(exist_ok=True)

    cmd = [
        chrome_exe,
        f"--remote-debugging-port={config.chrome_debug_port}",
        f"--user-data-dir={user_data}",
        config.petronect_url,
    ]

    log("🚀 Abrindo Chrome...")
    log(f"📍 Porta debug: {config.chrome_debug_port}")
    try:
        subprocess.Popen(cmd)
        log("✅ Chrome aberto!", "SUCCESS")
        log("=" * 60)
        log("👉 Deixe a aba aberta para o controle remoto e execute: python petronect_bot.py --scan")
        log("=" * 60)
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"❌ Erro: {exc}", "ERROR")
        return False


def mostrar_processados() -> None:
    log_file = None
    if Path.home().joinpath("petronect").exists():
        candidato = Path.home() / "petronect" / "processed.json"
        if candidato.exists():
            log_file = candidato
    if Path("processed.json").exists():
        log_file = Path("processed.json")
    if log_file and log_file.exists():
        with open(log_file) as file:
            proc = json.load(file)
        df = pd.DataFrame({"Oportunidades Processadas": proc})
        print(df)
        print(f"\n✅ Total: {len(proc)} oportunidades")
    else:
        print("❌ Nenhuma oportunidade processada ainda")


def mostrar_estrutura(config: BotConfig) -> None:
    print("📁 ESTRUTURA DE PASTAS E ARQUIVOS:\n" + "=" * 80)

    root = config.root_path
    total_pastas = 0
    total_arquivos = 0

    for item in sorted(root.iterdir()):
        if item.is_dir():
            total_pastas += 1
            arquivos = list(item.iterdir())
            print(f"\n📂 {item.name}/ ({len(arquivos)} arquivos)")
            for arquivo in arquivos:
                if arquivo.is_file():
                    total_arquivos += 1
                    size_kb = arquivo.stat().st_size / 1024
                    print(f"   📄 {arquivo.name} ({size_kb:.1f} KB)")
        elif item.suffix.lower() == ".xlsx":
            print(f"\n📊 {item.name}")

    print(f"\n{'=' * 80}")
    print("📊 RESUMO:")
    print(f"   Pastas de oportunidades: {total_pastas}")
    print(f"   Arquivos baixados: {total_arquivos}")
    print("=" * 80)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automação Petronect com Selenium e Chrome já aberto.")
    parser.add_argument("--open-chrome", action="store_true", help="Abre o Chrome em modo depuração remota.")
    parser.add_argument("--scan", action="store_true", help="Executa a varredura das oportunidades.")
    parser.add_argument("--list", action="store_true", dest="list_processed", help="Lista oportunidades já processadas.")
    parser.add_argument(
        "--structure",
        action="store_true",
        help="Mostra a estrutura de pastas e arquivos no diretório de saída.",
    )
    parser.add_argument("--root", type=Path, help="Caminho raiz para salvar dados (padrão: ~/petronect).")
    parser.add_argument("--chrome-port", type=int, default=9222, help="Porta de depuração remota do Chrome.")
    parser.add_argument("--chrome-path", type=Path, help="Caminho completo do executável do Chrome.")
    parser.add_argument(
        "--objeto",
        type=str,
        default="Válvula",
        help="Texto do campo 'Objeto' para filtrar oportunidades (padrão: Válvula).",
    )
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        log(f"Ignorando argumentos desconhecidos (provavelmente do Jupyter/IPython): {unknown}", "WARNING")
    return args


def main() -> None:
    args = parse_args(sys.argv[1:])
    config = BotConfig()
    if args.root:
        config.root_path = args.root
    config.chrome_debug_port = args.chrome_port
    config.ensure_paths()

    if args.chrome_path:
        os.environ["CHROME_EXECUTABLE"] = str(args.chrome_path)

    any_action = False

    if args.open_chrome:
        abrir_chrome_debug(config)
        any_action = True

    if args.scan:
        bot = PetronectBot(config)
        bot.executar_varredura(args.objeto)
        any_action = True

    if args.list_processed:
        mostrar_processados()
        any_action = True

    if args.structure:
        mostrar_estrutura(config)
        any_action = True

    if not any_action:
        log("Nenhuma opção fornecida; executando varredura (--scan) por padrão.", "WARNING")
        bot = PetronectBot(config)
        bot.executar_varredura(args.objeto)


if __name__ == "__main__":
    main()
