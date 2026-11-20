# scr-py

A lightweight command-line tool to query and download judgment PDFs from the official Supreme Court of India (e-SCR) and High Court portals without needing a browser, Selenium, or Playwright.

## Features

- **No Third-Party Python Dependencies**: Runs entirely on the Python 3 standard library (`urllib`, `http.cookiejar`, `json`, `re`, `argparse`).
- **Official Court Portals**:
  - Supreme Court of India (e-SCR): `https://scr.sci.gov.in/scrsearch/`
  - High Courts of India (eCourts Judgments): `https://judgments.ecourts.gov.in/pdfsearch/`
- **Smart Query Parsing**:
  - **Supreme Court Neutral Citations**: e.g., `2026 INSC 5`, `2024 INSC 123`
  - **SCR Reporter Citations**: e.g., `[1978] 2 S.C.R. 621`, `1973 Supp SCR 1`, `2006 3 SCR 1`
  - **Supreme Court Case Numbers**: e.g., `WP (C) 123/2021`, `SLP (Crl) 1234/2022`, `CA 36/2026`, `Diary No. 12345/2023` (automatically handles case type mapping and fallback searches)
  - **High Court Neutral Citations**: e.g., `2024:DHC:1234`, `2024:BHC-OS:567` (auto-detected even without flags)
  - **Keyword & Full-Text Search**: Supports phrase, all-word, or any-word matching with optional year filters.
- **Dual Invocation**:
  - Run as `scr` (or `scr.py`) to default to Supreme Court searches.
  - Run as `hc` (or `hc.py`) to default to High Court searches across India.
- **Seamless Captcha Flow**:
  - Downloads the portal captcha and automatically opens it in Preview on macOS (or displays the path on other systems).
  - Prompts you for the 6 characters in the terminal with automatic retry on mismatch.
- **Terminal Ergonomics**:
  - Long search results page through `less` (`-FRX`) automatically.
  - Interactive selection prompt to pick which judgment to download.
  - Automated/non-interactive mode with `-i <index>` or `--list` to inspect without downloading.
  - Clean output filenames derived from citation, case number, and case title.
  - Page-1 citation verification using `pdftotext` if available.

---

## Installation

### Prerequisites

- Python 3.8+
- *(Optional)* `pdftotext` (from Poppler) to verify citation text on page 1 of downloaded PDFs.

### Setup

Clone the repository and make the script executable:

```bash
git clone git@github.com:krsnajani/scr-py.git
cd scr-py
chmod +x scr.py
```

To use `scr` and `hc` globally from anywhere, symlink them into a directory on your `PATH` (such as `~/bin` or `/usr/local/bin`):

```bash
ln -s "$(pwd)/scr.py" ~/bin/scr
ln -s "$(pwd)/scr.py" ~/bin/hc
```

---

## Usage

### Supreme Court Queries

```bash
# Neutral citation
scr "2026 INSC 5"

# SCR reporter citation (volume and page)
scr "[1978] 2 S.C.R. 621"
scr "1973 Supp SCR 1"

# Case numbers (WP, SLP, Civil Appeal, Criminal Appeal, etc.)
scr "WP (C) 123/2021"
scr "SLP 1234/2022"
scr "Civil Appeal 36/2026"
scr "Diary No. 12345/2023"

# Keyword / Topic search
scr "Kesavananda Bharati"
scr "right to privacy" -y 2017
```

### High Court Queries

```bash
# High Court neutral citations (auto-detected)
scr "2024:DHC:1234"

# Using the 'hc' command alias or symlink
hc "2024:BHC-OS:567"
hc "patent infringement" -y 2023

# Using explicit --hc flag with scr
scr --hc "arbitration award"
```

---

## Command Options

| Flag | Description |
|---|---|
| `query` | Citation, case number, or text query (positional argument) |
| `--hc`, `--high-court` | Search High Court portal |
| `--sc`, `--supreme-court` | Search Supreme Court portal |
| `-s`, `--string` | Search explicitly as free text / keyword |
| `-c`, `--citation` | Search explicitly as a citation |
| `-C`, `--case` | Search explicitly as a case number (Supreme Court only) |
| `-m`, `--mode` | Search mode for text queries: `phrase` (default), `any`, `all` |
| `-y`, `--year` | Filter results by year (e.g. `-y 2023`) |
| `-n`, `--results` | Limit number of search results (default: all matching hits) |
| `-a`, `--all` | Retrieve all matching results |
| `--no-pager` | Disable terminal pager (`less`) and output directly |
| `-o`, `--outdir` | Output folder for downloaded PDFs (default: `/Users/Shared/CASES`) |
| `-i`, `--index` | Download specific hit index without interactive prompt |
| `--list` | List search results without downloading |

---

## Environment Variables

- `SCR_CAPTCHA_IMG`: Custom path where the captcha image will be saved.
- `SCR_CAPTCHA_ANSWER`: Path to a file containing a pre-solved captcha answer (useful for automated/headless scripts).
- `SCR_NO_OPEN`: Set to `1` to prevent automatically launching `Preview` on macOS.
- `PAGER`: Custom terminal pager command (defaults to `less -FRX`).
