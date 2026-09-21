"""
extract_htm_v2.py
=================
Version améliorée pour ATOFINA FRT files.
Utilise des regex robustes qui gèrent les HTML entities.
"""

import os
import re
import json
import time
import html
import unicodedata
from pathlib import Path
from datetime import datetime

from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================
INPUT_DIR = "anomaly checklist/Produit chimiques"
OUTPUT_TEXT_DIR = "extracted"
OUTPUT_DATA_DIR = "data"
RAW_DATA_FILE = "data/substances_raw.json"
LOG_FILE = "data/extraction_log.txt"

os.makedirs(OUTPUT_TEXT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DATA_DIR, exist_ok=True)


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def make_safe_filename(name):
    safe = re.sub(r'[^\w\s\-]', '_', name)
    safe = re.sub(r'\s+', '_', safe)
    return safe.strip('_')[:120]


# ============================================================
# EXTRACTION AMÉLIORÉE
# ============================================================
def extract_htm(htm_path: Path) -> dict:
    """Extraction avec regex robustes."""

    with open(htm_path, 'r', encoding='utf-8', errors='ignore') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    full_text = soup.get_text(separator=" ", strip=True)

    full_text = re.sub(r'\s+', ' ', full_text)
    full_text = html.unescape(full_text)

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
        "hazard_id": None,
        "packing_group": None,
        "flash_point_c": None,
    }

    # 1. NOM
    m = re.search(
        r'Mati[eè]re\s+dangereuse\s*:\s*([^,]+?)(?:\s*,\s*Etat|$)',
        full_text, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip()
        name = re.sub(r'\s+', ' ', name)
        data["name"] = name

    # 2. UN
    m = re.search(
        r"d'identification\s+de\s+la\s+mati[eè]re\s*:\s*(\d{4})",
        full_text, re.IGNORECASE
    )
    if m:
        data["un"] = m.group(1)

    if not data["un"]:
        m = re.search(r'UN\s+(\d{4})', full_text)
        if m:
            data["un"] = m.group(1)

    # 3. ADR class
    m = re.search(
        r'Classement\s+de\s+la\s+mati[eè]re\s*:\s*([0-9][0-9.,\s]*)',
        full_text, re.IGNORECASE
    )
    if m:
        cls = m.group(1).strip()
        cls_match = re.match(r'(\d+(?:\.\d+)?)', cls)
        if cls_match:
            data["adr_class"] = cls_match.group(1)

    # 4. HAZARD ID
    m = re.search(
        r"d'identification\s+du\s+danger\s*:\s*(\d{2,3})",
        full_text, re.IGNORECASE
    )
    if m:
        data["hazard_id"] = m.group(1)

    # 5. PACKING GROUP
    m = re.search(
        r"Groupe\s+d'emballage\s*:\s*(I{1,3}|IV)",
        full_text, re.IGNORECASE
    )
    if m:
        data["packing_group"] = m.group(1)

    # 6. FLASH POINT
    m = re.search(
        r'flash\s+point\s+([\d.]+)\s*[°]?\s*C',
        full_text, re.IGNORECASE
    )
    if m:
        data["flash_point_c"] = float(m.group(1))

    # 7. CAS
    cas_m = re.search(r'\b(\d{2,7}-\d{2}-\d)\b', full_text)
    if cas_m:
        data["cas"] = cas_m.group(1)

    return data


# ============================================================
# PROCESS
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

    log(f"📁 Found {total} HTM files")
    log(f"🚀 Starting extraction...")

    results = []
    start = time.time()

    for i, file in enumerate(files, 1):
        try:
            data = extract_htm(file)

            safe_name = make_safe_filename(file.stem)
            text_file = Path(OUTPUT_TEXT_DIR) / f"{safe_name}.txt"
            text_file.write_text(data["full_text"], encoding='utf-8')

            results.append(data)

            if i % 20 == 0 or i == total:
                elapsed = time.time() - start
                log(f"   [{i:4d}/{total}] — {elapsed:.1f}s")

        except Exception as e:
            log(f"   ❌ {file.name}: {e}")

    elapsed = time.time() - start
    log(f"✅ Extraction complete: {len(results)}/{total} files in {elapsed:.1f}s")

    return results


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== HTM Extraction Log ===\n")
        f.write(f"Started: {datetime.now().isoformat()}\n\n")

    log("=" * 60)
    log("🔬 HTM Extractor v2 — ATOFINA FRT")
    log("=" * 60)

    results = process_all(INPUT_DIR)

    if not results:
        log("❌ No results.")
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
    log(f"With hazard ID        : {sum(1 for x in results if x['hazard_id'])}")
    log("=" * 60)