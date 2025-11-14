# Your GitHub Learning Lab Repository for Introducing GitHub

Welcome to **your** repository for your GitHub Learning Lab course. This repository will be used during the different activities that I will be guiding you through. See a word you don't understand? We've included an emoji 📖 next to some key terms. Click on it to see its definition.

Oh! I haven't introduced myself...

I'm the GitHub Learning Lab bot and I'm here to help guide you in your journey to learn and master the various topics covered in this course. I will be using Issue and Pull Request comments to communicate with you. In fact, I already added an issue for you to check out.

![issue tab](https://lab.github.com/public/images/issue_tab.png)

I'll meet you over there, can't wait to get started!

This course is using the :sparkles: open source project [reveal.js](https://github.com/hakimel/reveal.js/). In some cases we’ve made changes to the history so it would behave during class, so head to the original project repo to learn more about the cool people behind this project.

## FBPI PDF Collector

This repository now includes a helper script located at `script/download_fbpi_pdfs.py` that automates the workflow requested by João Vitorino:

* Connects to the Outlook mailbox `joao.vitorino@fbvalve.com` via IMAP (`outlook.office365.com`) and downloads PDF attachments whose names start with `FBPI`.
* Recursively scans the primary Windows folders (Documents, Downloads, Desktop) for PDF files that start with the same prefix.
* Skips files that have already been copied, preventing duplicates in `C:\Users\joaoc\Downloads\FB-PI-CI`.
* Provides an `--interactive` mode so you can repeat the scan with a different prefix or destination folder without restarting the script.

Set the credentials with environment variables before execution to avoid exposing the password in plain text:

```powershell
$env:FBPI_EMAIL = "joao.vitorino@fbvalve.com"
$env:FBPI_EMAIL_PASSWORD = "Dag16332"
python script/download_fbpi_pdfs.py --interactive
```

When running outside of Windows or from a notebook environment, adjust the paths passed to `--local-dirs` and `--dest` accordingly.
