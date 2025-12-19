"""Automation helper for Petronect email opportunities using Selenium and a pre-opened Chrome instance.

This script is a command-line friendly version of the notebook-style code provided by the user.
It keeps the original behaviors (connect to an already-open Chrome with remote debugging,
scrape Petronect opportunity data, save spreadsheets, and track processed opportunities),
while adding safer defaults, clearer logging, and CLI commands.
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

@dataclass
class BotConfig:
    petronect_url: str = "https://www.petronect.com.br/irj/portal/anonymous/en"
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


def extrair_opp_numero(texto: str) -> Optional[str]:
    patterns = [
        r"public\s+opportunity\s+(\d+)",
        r"oportunidade\s+(?:pública\s+)?(\d+)",
        r"opportunity[:\s]+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, texto, re.I)
        if match:
            return match.group(1)
    return None


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
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self.processed: List[str] = self.load_log()
        self.first_run: bool = not Path("first_run.flag").exists()

    def load_log(self) -> List[str]:
        if Path("processed.json").exists():
            with open("processed.json") as file:
                return json.load(file)
        return []

    def save_log(self, opp: str) -> None:
        if opp not in self.processed:
            self.processed.append(opp)
            with open("processed.json", "w") as file:
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
            log("3. Você já fez login no email")
            return False

    def buscar_emails_petronect(self) -> List[str]:
        opps: List[str] = []
        if not self.driver or not self.wait:
            log("Driver não inicializado", "ERROR")
            return opps

        try:
            if "titan" not in self.driver.current_url.lower():
                log("Navegando para o email...", "WARNING")
                self.driver.get("https://titan.hostgator.com.br/mail/")
                time.sleep(3)

            log("Buscando emails Petronect...")
            try:
                prioritarios = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//span[contains(text(), 'Prioritarios') or contains(text(), 'Priority')]")
                    )
                )
                prioritarios.click()
                time.sleep(self.config.delay_seconds)
                log("Pasta Prioritários aberta", "SUCCESS")
            except Exception:
                log("Não foi possível abrir Prioritários. Tentando buscar na pasta atual...", "WARNING")

            try:
                emails = self.driver.find_elements(
                    By.XPATH,
                    "//*[contains(text(), 'Servicos de Notificacao Petronect') or contains(text(), 'Petronect')]",
                )

                log(f"📧 {len(emails)} emails Petronect encontrados")

                max_emails = len(emails) if self.first_run else min(10, len(emails))
                log(f"Processando {max_emails} emails...")

                for index, email in enumerate(emails[:max_emails], 1):
                    try:
                        log(f"Email {index}/{max_emails}...", "INFO")
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", email)
                        time.sleep(0.5)
                        email.click()
                        time.sleep(self.config.delay_seconds)

                        body = self.driver.find_element(
                            By.XPATH,
                            "//div[contains(@class, 'email') or contains(@class, 'message') or contains(@class, 'body')]",
                        )
                        texto = body.text
                        opp = extrair_opp_numero(texto)

                        if opp:
                            if opp not in self.processed:
                                opps.append(opp)
                                log(f"✅ Oportunidade {opp}", "SUCCESS")
                            else:
                                log(f"⏭️ {opp} já processada")
                        else:
                            log("⚠️ Número não encontrado", "WARNING")

                        self.driver.back()
                        time.sleep(1)

                    except Exception as exc:  # noqa: BLE001
                        log(f"Erro no email {index}: {exc}", "WARNING")
                        continue

                log(f"🎯 {len(opps)} novas oportunidades encontradas", "SUCCESS")
                return opps

            except Exception as exc:  # noqa: BLE001
                log(f"Erro ao buscar emails: {exc}", "ERROR")
                return opps

        except Exception as exc:  # noqa: BLE001
            log(f"Erro geral na busca: {exc}", "ERROR")
            return opps

    def acessar_petronect(self, opp: str) -> bool:
        if not self.driver or not self.wait:
            log("Driver não inicializado", "ERROR")
            return False

        try:
            log(f"Acessando Petronect: {opp}")
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])

            self.driver.get(self.config.petronect_url)
            time.sleep(self.config.delay_seconds)

            btn = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(text(), 'Open for proposals') or contains(text(), 'abrir Propostas')]")
                )
            )
            btn.click()
            time.sleep(self.config.delay_seconds)

            search = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//input[contains(@placeholder, 'Search') or contains(@placeholder, 'Buscar')]")
                )
            )
            search.clear()
            search.send_keys(str(opp))
            search.send_keys(Keys.ENTER)
            time.sleep(1)

            search_btn = self.driver.find_element(
                By.XPATH, "//button[@type='submit' or contains(@class, 'search')]"
            )
            search_btn.click()
            time.sleep(self.config.delay_seconds)

            log("Petronect OK", "SUCCESS")
            return True

        except Exception as exc:  # noqa: BLE001
            log(f"Erro Petronect: {exc}", "ERROR")
            return False

    def extrair_dados(self) -> Dict[str, Dict]:
        data: Dict[str, Dict] = {"header": {}, "items": []}
        if not self.driver or not self.wait:
            log("Driver não inicializado", "ERROR")
            return data

        try:
            info_btn = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@title, 'Information') or contains(@class, 'info')]")
                )
            )
            info_btn.click()
            time.sleep(self.config.delay_seconds)

            try:
                data["header"]["opportunity_number"] = self.driver.find_element(
                    By.XPATH, "//label[contains(text(), 'Opportunity')]/following-sibling::*"
                ).text
            except Exception:
                pass

            try:
                data["header"]["purchasing_object"] = self.driver.find_element(
                    By.XPATH, "//label[contains(text(), 'Purchasing')]/following-sibling::*"
                ).text
            except Exception:
                pass

            try:
                data["header"]["start_date"] = self.driver.find_element(
                    By.XPATH, "//label[contains(text(), 'Start')]/following-sibling::*"
                ).text
            except Exception:
                pass

            try:
                data["header"]["end_date"] = self.driver.find_element(
                    By.XPATH, "//label[contains(text(), 'End')]/following-sibling::*"
                ).text
            except Exception:
                pass

            try:
                rows = self.driver.find_elements(By.XPATH, "//table//tr[position()>1]")
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if cells:
                        data["items"].append(
                            {
                                "item_number": cells[0].text if len(cells) > 0 else "",
                                "description": cells[1].text if len(cells) > 1 else "",
                                "quantity": cells[2].text if len(cells) > 2 else "",
                                "unit": cells[3].text if len(cells) > 3 else "",
                            }
                        )
                log(f"📋 {len(data['items'])} itens extraídos", "SUCCESS")
            except Exception:
                log("⚠️ Não foi possível extrair itens", "WARNING")

            return data

        except Exception as exc:  # noqa: BLE001
            log(f"Erro ao extrair dados: {exc}", "WARNING")
            return data

    def baixar_anexos(self, folder: Path) -> bool:
        if not self.driver:
            log("Driver não inicializado", "ERROR")
            return False

        try:
            attach_btn = self.driver.find_element(
                By.XPATH, "//button[contains(@title, 'Attachment') or contains(@class, 'attach')]"
            )
            attach_btn.click()
            time.sleep(self.config.delay_seconds)

            links = self.driver.find_elements(By.XPATH, "//a[contains(@href, 'download')]")
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

            if not self.acessar_petronect(opp):
                if self.driver:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                return False

            data = self.extrair_dados()
            self.baixar_anexos(folder)

            criar_excel(opp, folder, data)
            atualizar_master(self.config, opp, data)

            self.save_log(opp)

            if self.driver:
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])

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

    def executar_varredura(self) -> None:
        log("\n" + "=" * 80)
        if self.first_run:
            log("🚀 PRIMEIRA EXECUÇÃO - Varredura completa desde Junho/2024")
        else:
            log("🔄 Varredura incremental - Apenas novos emails")
        log("=" * 80 + "\n")

        if not self.conectar_chrome_aberto():
            log("\n❌ Não foi possível conectar ao Chrome", "ERROR")
            log("Execute o comando: python petronect_bot.py --open-chrome")
            return

        opps = self.buscar_emails_petronect()
        if not opps:
            log("\nℹ️ Nenhuma nova oportunidade encontrada", "WARNING")
            return

        log(f"\n📊 {len(opps)} oportunidades para processar\n")

        sucesso = 0
        falhas = 0

        for index, opp in enumerate(opps, 1):
            log(f"\n[{index}/{len(opps)}]")
            if self.processar_oportunidade(opp):
                sucesso += 1
            else:
                falhas += 1
            time.sleep(self.config.delay_seconds)

        if self.first_run:
            with open("first_run.flag", "w") as file:
                json.dump({"date": datetime.now().isoformat(), "processed": len(opps)}, file)
            log("\n✅ Primeira execução marcada como completa!", "SUCCESS")

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
        "https://titan.hostgator.com.br/mail/",
    ]

    log("🚀 Abrindo Chrome...")
    log(f"📍 Porta debug: {config.chrome_debug_port}")
    try:
        subprocess.Popen(cmd)
        log("✅ Chrome aberto!", "SUCCESS")
        log("=" * 60)
        log("👉 Faça login no email manualmente e execute: python petronect_bot.py --scan")
        log("=" * 60)
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"❌ Erro: {exc}", "ERROR")
        return False


def mostrar_processados() -> None:
    if Path("processed.json").exists():
        with open("processed.json") as file:
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
        bot.executar_varredura()
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
        bot.executar_varredura()


if __name__ == "__main__":
    main()
