"""
clean_duplicates.py
===================
Detect and merge duplicate substances from extracted HTM data.

Duplicates occur because:
- Accented vs non-accented names (é vs e)
- Different capitalizations
- Trailing punctuation

Usage:
    python clean_duplicates.py

Input:
    data/substances_raw.json

Output:
    data/substances_clean.json      ← deduplicated data
    data/duplicates_report.txt      ← detailed report
"""

import os
import re
import json
import unicodedata
from pathlib import Path
from datetime import datetime
from collections import defaultdict


# ============================================================
# CONFIG
# ============================================================
INPUT_FILE = "data/substances_raw.json"
OUTPUT_FILE = "data/substances_clean.json"
REPORT_FILE = "data/duplicates_report.txt"


# ============================================================
# NORMALIZATION
# ============================================================
def normalize_for_comparison(name: str) -> str:
    """
    Aggressive normalization for duplicate detection.

    Steps:
    1. Remove accents (é → e)
    2. Lowercase
    3. Remove all non-alphanumeric (spaces, dashes, commas)
    4. Collapse everything

    Example:
        "2-Bromoisobutyrate de méthyle" → "2bromoisobutyratedemethyle"
        "2-bromoisobutyrate de methyle" → "2bromoisobutyratedemethyle"
        → SAME KEY
    """
    if not name:
        return ""

    # 1. Remove accents
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = nfkd.encode('ASCII', 'ignore').decode('ASCII')

    # 2. Lowercase
    lower = ascii_name.lower()

    # 3. Remove all non-alphanumeric
    clean = re.sub(r'[^a-z0-9]', '', lower)

    return clean


def merge_records(records: list) -> dict:
    """
    Merge multiple records of the same substance.

    Strategy:
    - Keep the first one as base
    - Fill missing fields from others
    - Keep the longest full_text
    - Track source files
    """
    base = records[0].copy()

    # Track all source files
    all_sources = [r["source_file"] for r in records]
    base["source_files"] = all_sources

    # Merge fields
    for r in records[1:]:
        for key, val in r.items():
            if key in ("source_file", "source_filename", "full_text"):
                continue
            if val and not base.get(key):
                base[key] = val

    # Keep longest full_text
    longest_text = max(records, key=lambda r: len(r.get("full_text", "")))
    base["full_text"] = longest_text["full_text"]

    # Remove single source_file (replaced by source_files)
    base.pop("source_file", None)

    return base


# ============================================================
# DETECT DUPLICATES
# ============================================================
def detect_duplicates(records: list) -> tuple:
    """
    Group records by normalized name.

    Returns:
    - (unique_records, duplicate_groups)
    """

    # Group by normalized name
    groups = defaultdict(list)

    for r in records:
        # Try name first
        name = r.get("name") or Path(r["source_filename"]).stem
        key = normalize_for_comparison(name)

        if not key:
            # Fallback to filename
            key = normalize_for_comparison(Path(r["source_filename"]).stem)

        groups[key].append(r)

    # Separate unique vs duplicates
    unique = []
    duplicates = []

    for key, group in groups.items():
        if len(group) == 1:
            # Unique
            record = group[0].copy()
            record["source_files"] = [record["source_file"]]
            record.pop("source_file", None)
            unique.append(record)
        else:
            # Duplicate — merge
            merged = merge_records(group)
            merged["normalized_key"] = key
            unique.append(merged)
            duplicates.append({
                "key": key,
                "count": len(group),
                "files": [r["source_filename"] for r in group],
                "names": [r.get("name") for r in group],
                "merged_name": merged.get("name"),
            })

    return unique, duplicates


# ============================================================
# WRITE REPORT
# ============================================================
def write_report(duplicates: list, unique_count: int, total_count: int):
    """Write a detailed duplicates report."""

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("DUPLICATES REPORT\n")
        f.write("=" * 70 + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        f.write(f"Total records (raw)    : {total_count}\n")
        f.write(f"Unique substances      : {unique_count}\n")
        f.write(f"Duplicate groups       : {len(duplicates)}\n")
        f.write(f"Records removed        : {total_count - unique_count}\n\n")

        if not duplicates:
            f.write("✅ No duplicates found.\n")
            return

        f.write("=" * 70 + "\n")
        f.write("DUPLICATE GROUPS\n")
        f.write("=" * 70 + "\n\n")

        # Sort by count (most duplicates first)
        sorted_dups = sorted(duplicates, key=lambda d: -d["count"])

        for i, dup in enumerate(sorted_dups, 1):
            f.write(f"\n{i}. Key: {dup['key']}\n")
            f.write(f"   Count: {dup['count']}\n")
            f.write(f"   Merged name: {dup['merged_name']}\n")
            f.write(f"   Files:\n")
            for file in dup["files"]:
                f.write(f"      - {file}\n")
            f.write(f"   Names found:\n")
            for name in dup["names"]:
                f.write(f"      - {name}\n")
            f.write("-" * 70 + "\n")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":

    print("=" * 60)
    print("🧹 Duplicate Cleaner")
    print("=" * 60)

    # Load
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Input file not found: {INPUT_FILE}")
        print(f"   Run extract_htm.py first.")
        exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_records = json.load(f)

    total_count = len(raw_records)
    print(f"\n📖 Loaded: {total_count} raw records")

    # Detect duplicates
    print(f"\n🔍 Detecting duplicates...")
    unique, duplicates = detect_duplicates(raw_records)

    print(f"   ✅ Unique substances: {len(unique)}")
    print(f"   ⚠️ Duplicate groups: {len(duplicates)}")
    print(f"   🗑️  Records removed: {total_count - len(unique)}")

    # Show duplicate examples
    if duplicates:
        print(f"\n📋 Duplicate examples (top 5):")
        for dup in sorted(duplicates, key=lambda d: -d["count"])[:5]:
            print(f"\n   Key: {dup['key']}")
            print(f"   Count: {dup['count']}")
            for file in dup["files"]:
                print(f"      - {file}")

    # Save cleaned data
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Saved: {OUTPUT_FILE}")

    # Write report
    write_report(duplicates, len(unique), total_count)
    print(f"📄 Report: {REPORT_FILE}")

    print("\n" + "=" * 60)
    print("✅ Done")
    print("=" * 60)