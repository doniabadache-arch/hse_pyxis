"""
extract_htm.py
==============
Extract text and structured data from ATOFINA FRT HTML files.

Usage:
    python extract_htm.py

Input:
    anomaly checklist/Produit chimiques/*.html

Output:
    extracted/*.txt                ← raw text per file
    data/substances_raw.json       ← structured data
    data/extraction_log.txt        ← log file
"""

import os
import re
import json
import time
import unicodedata
from pathlib import Path
from datetime import datetime

from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION — modify paths if needed
# ============================================================
INPUT_DIR = "anomaly checklist/Produit chimiques"
OUTPUT_TEXT_DIR = "extracted"
OUTPUT_DATA_DIR = "data"
RAW_DATA_FILE = "data/substances_raw.json"
LOG_FILE = "data/extraction_log.txt"

# Create output directories
os.makedirs(OUTPUT_TEXT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DATA_DIR, exist_ok=True)


# ============================================================
# UTILITIES
# ============================================================
def normalize_name(name: str) -> str:
    """
    Normalize substance name for comparison:
    - Remove accents (é → e, è → e, à → a)
    - Lowercase
    - Replace non-alphanumeric with underscore
    - Collapse multiple underscores
    """
    if not name:
        return ""

    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = nfkd.encode('ASCII', 'ignore').decode('ASCII')

    normalized = re.sub(r'[^\w]+', '_', ascii_name.lower())
    normalized = re.sub(r'_+', '_', normalized).strip('_')

    return normalized


def make_safe_filename(name: str) -> str:
    """Make a safe filename from a substance name."""
    safe = re.sub(r'[^\w\s\-]', '_', name)
    safe = re.sub(r'\s+', '_', safe)
    return safe.strip('_')[:120]


def log(msg: str, log_file: str = LOG_FILE):
    """Write to log file and print."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================
# EXTRACT FROM ONE HTM FILE
# ============================================================
def extract_htm(htm_path: Path) -> dict:
    """Extract structured data from one ATOFINA FRT HTML file."""

    with open(htm_path, 'r', encoding='utf-8', errors='ignore') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    full_text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    data = {
        "source_file": str(htm_path),
        "source_filename": htm_path.name,
        "format": "HTM",
        "extracted_at": datetime.now().isoformat(),
        "full_text": full_text,

        "name": None,
        "cas": None,
        "un": None,
        "adr_class": None,
        "adr_label": None,
        "hazard_id": None,
        "packing_group": None,
        "flash_point_c": None,
        "transport_road": None,
        "transport_rail": None,
        "transport_sea": None,
        "transport_air": None,
    }

    for i, line in enumerate(lines):
        line_upper = line.upper()

        if "MATIÈRE DANGEREUSE" in line_upper or "MATIERE DANGEREUSE" in line_upper:
            if i + 1 < len(lines):
                name = lines[i + 1].strip()
                name = re.split(r',\s*Etat\s*:', name)[0].strip()
                name = name.rstrip(',').strip()
                data["name"] = name

        if not data["cas"]:
            cas_m = re.search(r'\b(\d{2,7}-\d{2}-\d)\b', line)
            if cas_m:
                data["cas"] = cas_m.group(1)

        if "IDENTIFICATION DE LA MATIÈRE" in line_upper or \
           "IDENTIFICATION DE LA MATIERE" in line_upper:
            m = re.search(r'\b(\d{4})\b', line)
            if m:
                data["un"] = m.group(1)

        if "CLASSEMENT DE LA MATIÈRE" in line_upper or \
           "CLASSEMENT DE LA MATIERE" in line_upper:
            m = re.search(r'\b(\d+[\.\d]*[a-z]?)\b', line)
            if m:
                data["adr_class"] = m.group(1)

        if "IDENTIFICATION DU DANGER" in line_upper:
            m = re.search(r'\b(\d{2,3})\b', line)
            if m:
                data["hazard_id"] = m.group(1)

        if "FLASH POINT" in line_upper or "POINT D'ÉCLAIR" in line_upper or \
           "POINT D'ECLAIR" in line_upper:
            m = re.search(r'([\d.]+)\s*C', line)
            if m:
                data["flash_point_c"] = float(m.group(1))

        if "GROUPE D'EMBALLAGE" in line_upper or \
           "GROUPE D'EMBALLAGE" in line_upper:
            m = re.search(r'\b(I{1,3}|IV)\b', line)
            if m:
                data["packing_group"] = m.group(1)

        if "ADR" in line_upper and "LIQUIDE INFLAMMABLE" in line_upper:
            data["transport_road"] = line
            data["adr_label"] = "Flammable liquid"

        if "RID" in line_upper and "LIQUIDE INFLAMMABLE" in line_upper:
            data["transport_rail"] = line

        if "IMDG" in line_upper:
            data["transport_sea"] = line

        if "IATA" in line_upper:
            data["transport_air"] = line

    return data


# ============================================================
# PROCESS ALL FILES
# ============================================================
def process_all(input_dir: str) -> list:
    dir_path = Path(input_dir)

    if not dir_path.exists():
        log(f"❌ Directory not found: {input_dir}")
        return []

    files = sorted([
        f for f in dir_path.iterdir()
        if f.suffix.lower() in ('.htm', '.html')
    ])

    total = len(files)

    if total == 0:
        log(f"⚠️ No HTM files found in: {input_dir}")
        return []

    log(f"📁 Found {total} HTM files in: {input_dir}")
    log(f"🚀 Starting extraction...")

    results = []
    errors = []
    start_time = time.time()

    for i, file in enumerate(files, 1):
        try:
            data = extract_htm(file)

            safe_name = make_safe_filename(file.stem)
            text_file = Path(OUTPUT_TEXT_DIR) / f"{safe_name}.txt"
            text_file.write_text(data["full_text"], encoding='utf-8')

            results.append(data)

            if i % 10 == 0 or i == total:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                log(f"   [{i:4d}/{total}] {rate:5.1f} files/s — {elapsed:5.1f}s elapsed")

        except Exception as e:
            errors.append({"file": str(file), "error": str(e)})
            log(f"   ❌ Error on {file.name}: {e}")

    elapsed = time.time() - start_time
    log(f"✅ Extraction complete: {len(results)}/{total} files in {elapsed:.1f}s")

    if errors:
        log(f"⚠️ {len(errors)} errors occurred")
        with open("data/extraction_errors.json", "w", encoding="utf-8") as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)

    return results


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== HTM Extraction Log ===\n")
        f.write(f"Started: {datetime.now().isoformat()}\n\n")

    log("=" * 60)
    log("🔬 HTM Extractor — ATOFINA FRT Files")
    log("=" * 60)

    results = process_all(INPUT_DIR)

    if not results:
        log("❌ No results. Check input directory.")
        exit(1)

    with open(RAW_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log(f"\n💾 Saved: {RAW_DATA_FILE}")

    log("\n" + "=" * 60)
    log("📊 SUMMARY")
    log("=" * 60)
    log(f"Total files processed : {len(results)}")
    log(f"With name             : {sum(1 for x in results if x['name'])}")
    log(f"With CAS              : {sum(1 for x in results if x['cas'])}")
    log(f"With UN               : {sum(1 for x in results if x['un'])}")
    log(f"With ADR class        : {sum(1 for x in results if x['adr_class'])}")
    log(f"With flash point      : {sum(1 for x in results if x['flash_point_c'])}")
    log(f"With packing group    : {sum(1 for x in results if x['packing_group'])}")
    log("=" * 60)
    log(f"✅ Done. Log saved: {LOG_FILE}")