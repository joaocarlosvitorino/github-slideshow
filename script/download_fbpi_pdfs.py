"""Utility to collect FBPI-prefixed PDF files from Outlook e-mail and local folders.

This script automates three primary actions:

1. Connects to an Outlook mailbox via IMAP and downloads PDF attachments whose
   file names start with a configurable prefix (defaults to "FBPI").
2. Scans one or more local directories recursively, copying matching PDF files
   into a destination directory.
3. Optionally repeats the search with a new prefix and/or destination without
   restarting the script, honoring the requirement to skip files that were
   already copied previously.

Example usage (values can also be provided via environment variables):

    export FBPI_EMAIL="joao.vitorino@fbvalve.com"
    export FBPI_EMAIL_PASSWORD="<sua-senha>"
    python script/download_fbpi_pdfs.py \
        --local-dirs "C:/Users/joaoc/Documents" "C:/Users/joaoc/Downloads" \
        --dest "C:/Users/joaoc/Downloads/FB-PI-CI" \
        --interactive

The script was designed to run inside a standard Python environment, including
Jupyter Notebook or Google Colab.  When running on Windows, make sure paths use
the appropriate drive letters (e.g., ``C:/Users/...``) and that the destination
folder exists or can be created.
"""

from __future__ import annotations

import argparse
import getpass
import imaplib
import os
import shutil
from email import message_from_bytes
from typing import Iterable, List, Sequence


OUTLOOK_IMAP_SERVER = "outlook.office365.com"
DEFAULT_PREFIX = "FBPI"


def connect_to_mailbox(server: str, email_address: str, password: str) -> imaplib.IMAP4_SSL:
    """Create an IMAP connection to the Outlook mailbox."""

    connection = imaplib.IMAP4_SSL(server)
    connection.login(email_address, password)
    connection.select("INBOX")
    return connection


def attachment_matches(filename: str, prefix: str) -> bool:
    """Return True if the attachment matches the required prefix and file type."""

    return filename.upper().startswith(prefix.upper()) and filename.lower().endswith(".pdf")


def ensure_destination(dest: str) -> str:
    os.makedirs(dest, exist_ok=True)
    return os.path.abspath(dest)


def download_matching_attachments(
    server: str,
    email_address: str,
    password: str,
    dest: str,
    prefix: str,
    skip_existing: bool = True,
) -> List[str]:
    """Download Outlook attachments that match the prefix and extension."""

    saved_files: List[str] = []
    mailbox = connect_to_mailbox(server, email_address, password)
    try:
        _, ids = mailbox.search(None, "ALL")
        id_list = ids[0].split()

        for email_id in reversed(id_list):
            _, payload = mailbox.fetch(email_id, "(RFC822)")
            raw_email = payload[0][1]
            message = message_from_bytes(raw_email)

            if not message.is_multipart():
                continue

            for part in message.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is None:
                    continue

                filename = part.get_filename()
                if not filename or not attachment_matches(filename, prefix):
                    continue

                destination_path = os.path.join(dest, filename)
                if skip_existing and os.path.exists(destination_path):
                    print(f"[E-MAIL] Ignorando (já existe): {destination_path}")
                    continue

                with open(destination_path, "wb") as file_handle:
                    file_handle.write(part.get_payload(decode=True))

                saved_files.append(destination_path)
                print(f"[E-MAIL] Salvo: {destination_path}")
    finally:
        mailbox.logout()

    return saved_files


def copy_local_pdfs(
    directories: Sequence[str],
    dest: str,
    prefix: str,
    skip_existing: bool = True,
) -> List[str]:
    """Copy PDF files from the supplied directories, honoring the prefix."""

    copied_files: List[str] = []
    for directory in directories:
        if not os.path.isdir(directory):
            print(f"[LOCAL] Diretório inexistente, ignorando: {directory}")
            continue

        for root, _, files in os.walk(directory):
            for file_name in files:
                if not attachment_matches(file_name, prefix):
                    continue

                source_path = os.path.join(root, file_name)
                destination_path = os.path.join(dest, file_name)

                if skip_existing and os.path.exists(destination_path):
                    print(f"[LOCAL] Ignorando (já existe): {destination_path}")
                    continue

                shutil.copy2(source_path, destination_path)
                copied_files.append(destination_path)
                print(f"[LOCAL] Copiado: {source_path} -> {destination_path}")

    return copied_files


def run_once(
    imap_server: str,
    email_address: str,
    password: str,
    directories: Sequence[str],
    dest: str,
    prefix: str,
) -> None:
    ensure_destination(dest)
    print(f"\nProcurando anexos com prefixo '{prefix}' e salvando em {dest}\n")
    download_matching_attachments(imap_server, email_address, password, dest, prefix)
    copy_local_pdfs(directories, dest, prefix)


def interactive_loop(
    imap_server: str,
    email_address: str,
    password: str,
    directories: Sequence[str],
    dest: str,
    prefix: str,
) -> None:
    current_dest = dest
    current_prefix = prefix

    while True:
        run_once(imap_server, email_address, password, directories, current_dest, current_prefix)

        again = input("\nDeseja procurar novamente com outro prefixo/pasta? (s/n): ").strip().lower()
        if again != "s":
            break

        new_prefix = input(f"Informe o novo prefixo (ENTER para manter '{current_prefix}'): ").strip()
        if new_prefix:
            current_prefix = new_prefix

        new_dest = input(f"Informe a nova pasta destino (ENTER para manter '{current_dest}'): ").strip()
        if new_dest:
            current_dest = ensure_destination(new_dest)


def parse_arguments(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=os.environ.get("FBPI_EMAIL"), help="Endereço de e-mail Outlook")
    parser.add_argument(
        "--password",
        default=os.environ.get("FBPI_EMAIL_PASSWORD"),
        help="Senha do e-mail (recomenda-se usar variável de ambiente)",
    )
    parser.add_argument(
        "--imap-server",
        default=OUTLOOK_IMAP_SERVER,
        help="Servidor IMAP (padrão: outlook.office365.com)",
    )
    parser.add_argument(
        "--dest",
        default=os.environ.get("FBPI_DEST", r"C:/Users/joaoc/Downloads/FB-PI-CI"),
        help="Pasta destino para salvar os PDFs",
    )
    parser.add_argument(
        "--prefix",
        default=os.environ.get("FBPI_PREFIX", DEFAULT_PREFIX),
        help="Prefixo que os arquivos devem possuir",
    )
    parser.add_argument(
        "--local-dirs",
        nargs="*",
        default=(os.environ.get("FBPI_LOCAL_DIRS") or "C:/Users/joaoc/Documents;C:/Users/joaoc/Downloads;C:/Users/joaoc/Desktop").split(";"),
        help="Lista de diretórios locais para varredura",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Habilita modo interativo para repetir buscas sem reiniciar",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_arguments()

    email_address = args.email or input("Informe o e-mail do Outlook: ").strip()
    password = args.password or getpass.getpass("Senha do Outlook: ")

    directories = [directory for directory in args.local_dirs if directory.strip()]
    destination = ensure_destination(args.dest)

    if args.interactive:
        interactive_loop(args.imap_server, email_address, password, directories, destination, args.prefix)
    else:
        run_once(args.imap_server, email_address, password, directories, destination, args.prefix)


if __name__ == "__main__":
    main()
