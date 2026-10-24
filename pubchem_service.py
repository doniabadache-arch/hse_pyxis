"""
pubchem_service.py — HSE PYXIS
================================
Récupération de données chimiques depuis PubChem (NCBI) via l'API
officielle PUG REST / PUG-View, avec la librairie `requests` uniquement
(déjà dans requirements.txt → aucune dépendance supplémentaire).

Documentation : https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest

Toutes les fonctions sont tolérantes aux erreurs : en cas d'échec réseau
ou de substance introuvable elles retournent None / des valeurs vides,
sans jamais lever d'exception vers l'interface.
"""

import re
import time
from typing import Optional
from urllib.parse import quote

import requests

_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest"
_TIMEOUT = 10  # secondes
_MIN_DELAY = 0.25  # PubChem : 5 requêtes/seconde maximum
_HEADERS = {"User-Agent": "HSE-PYXIS/1.0 (academic project)"}
_last_call = 0.0


def _get_json(url: str) -> Optional[dict]:
    """GET JSON avec limitation de débit, timeout et gestion d'erreurs."""
    global _last_call
    wait = _MIN_DELAY - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        _last_call = time.time()
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        _last_call = time.time()
        print(f"[PubChem] {url.split('/rest/')[-1][:80]} : {e}")
        return None


# ============================================================
# RECHERCHE
# ============================================================
def search_cids(name: str, max_results: int = 5) -> list:
    """Retourne la liste des CID correspondant à un nom (ou CAS)."""
    if not name or len(name.strip()) < 2:
        return []
    data = _get_json(
        f"{_BASE}/pug/compound/name/{quote(name.strip(), safe='')}/cids/JSON"
    )
    cids = (data or {}).get("IdentifierList", {}).get("CID", [])
    return [c for c in cids if c and c > 0][:max_results]


def search_by_name(name: str) -> Optional[int]:
    """Recherche un composé par son nom → premier CID."""
    cids = search_cids(name, max_results=1)
    return cids[0] if cids else None


def search_all_matches(name: str, max_results: int = 5) -> list:
    """Retourne plusieurs candidats (cid, nom IUPAC, formule, masse)."""
    cids = search_cids(name, max_results=max_results)
    if not cids:
        return []
    ids = ",".join(str(c) for c in cids)
    data = _get_json(
        f"{_BASE}/pug/compound/cid/{ids}/property/"
        "IUPACName,MolecularFormula,MolecularWeight/JSON"
    )
    rows = (data or {}).get("PropertyTable", {}).get("Properties", [])
    return [
        {
            "cid": r.get("CID"),
            "iupac_name": r.get("IUPACName") or "—",
            "molecular_formula": r.get("MolecularFormula") or "—",
            "molecular_weight": _to_float(r.get("MolecularWeight")) or 0.0,
        }
        for r in rows
    ]


# ============================================================
# PROPRIÉTÉS DE BASE
# ============================================================
def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")


def _extract_cas(synonyms: list) -> Optional[str]:
    for s in synonyms or []:
        s = s.strip()
        if _CAS_RE.match(s):
            return s
    return None


def get_basic_properties(cid: int) -> Optional[dict]:
    """Propriétés de base d'un composé (par CID)."""
    if not cid:
        return None
    data = _get_json(
        f"{_BASE}/pug/compound/cid/{cid}/property/"
        "IUPACName,MolecularFormula,MolecularWeight/JSON"
    )
    rows = (data or {}).get("PropertyTable", {}).get("Properties", [])
    if not rows:
        return None
    r = rows[0]

    syn_data = _get_json(f"{_BASE}/pug/compound/cid/{cid}/synonyms/JSON")
    info = (syn_data or {}).get("InformationList", {}).get("Information", [])
    synonyms = info[0].get("Synonym", []) if info else []

    return {
        "cid": cid,
        "iupac_name": r.get("IUPACName") or "",
        "molecular_formula": r.get("MolecularFormula") or "",
        "molecular_weight": _to_float(r.get("MolecularWeight")),
        "cas_number": _extract_cas(synonyms),
        "synonyms": synonyms[:10],
    }


# ============================================================
# PUG-View : parcours des sections
# ============================================================
def _iter_strings(node):
    """Itère (nom_de_l_information, texte) dans un enregistrement PUG-View."""
    if isinstance(node, dict):
        for info in node.get("Information", []):
            name = info.get("Name", "")
            for val in info.get("Value", {}).get("StringWithMarkup", []):
                yield name, val.get("String", "")
        for sub in node.get("Section", []):
            yield from _iter_strings(sub)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)


def _pug_view(cid: int, heading: str) -> list:
    data = _get_json(
        f"{_BASE}/pug_view/data/compound/{cid}/JSON?heading={quote(heading)}"
    )
    return list(_iter_strings((data or {}).get("Record", {}).get("Section", [])))


# ============================================================
# TOXICITÉ (LD50 / LC50) — extraction « au mieux »
# ============================================================
_NUM = r"([\d][\d.,]*)"


def _num(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def get_toxicity_data(cid: int, molecular_weight: Optional[float] = None) -> dict:
    """LD50 oral / LC50 inhalation (rat) depuis la section Non-Human Toxicity Values."""
    result = {"ld50_oral_mg_kg": None, "lc50_inhalation_mg_m3": None}
    if not cid:
        return result

    for _name, text in _pug_view(cid, "Non-Human Toxicity Values"):
        if result["ld50_oral_mg_kg"] is None:
            m = re.search(
                r"LD50\s+Rat\s+oral\s+" + _NUM + r"\s*(mg/kg|g/kg)", text, re.I
            )
            if m:
                v = _num(m.group(1))
                if v is not None:
                    result["ld50_oral_mg_kg"] = v * (1000.0 if m.group(2).lower() == "g/kg" else 1.0)

        if result["lc50_inhalation_mg_m3"] is None:
            m = re.search(
                r"LC50\s+Rat\s+inhalation\s+" + _NUM + r"\s*(mg/m3|mg/m\^3|mg/l|g/m3|ppm)",
                text, re.I,
            )
            if m:
                v = _num(m.group(1))
                unit = m.group(2).lower()
                if v is not None:
                    if unit == "mg/l" or unit == "g/m3":
                        v *= 1000.0
                    elif unit == "ppm":
                        # ppm → mg/m³ à 25 °C : ppm × M / 24,45
                        v = v * molecular_weight / 24.45 if molecular_weight else None
                    result["lc50_inhalation_mg_m3"] = v
    return result


# ============================================================
# GHS / CODES H
# ============================================================
def get_ghs_hazards(cid: int) -> dict:
    """Classification GHS : codes H et mention d'avertissement."""
    result = {"h_codes": [], "signal_word": None}
    if not cid:
        return result

    h_set = set()
    for name, text in _pug_view(cid, "GHS Classification"):
        if name.lower().startswith("signal"):
            if "danger" in text.lower():
                result["signal_word"] = "Danger"
            elif "warning" in text.lower() and result["signal_word"] != "Danger":
                result["signal_word"] = "Warning"
        for h in re.findall(r"\bH\d{3}\b", text):
            h_set.add(h)
    result["h_codes"] = sorted(h_set)
    return result


# ============================================================
# PROFIL COMPLET
# ============================================================
def get_chemical_profile(name_or_cid) -> Optional[dict]:
    """Profil complet d'une substance (nom, CAS ou CID)."""
    if isinstance(name_or_cid, int):
        cid = name_or_cid
    elif isinstance(name_or_cid, str) and name_or_cid.strip().isdigit():
        cid = int(name_or_cid.strip())
    else:
        cid = search_by_name(name_or_cid or "")
    if not cid:
        return None

    basic = get_basic_properties(cid)
    if not basic:
        return None

    tox = get_toxicity_data(cid, basic.get("molecular_weight"))
    ghs = get_ghs_hazards(cid)

    # Seuil toxique estimé = LC50 inhalation / 10 (approche conservatrice).
    # Pas d'estimation à partir de la LD50 orale (voie d'exposition différente).
    lc50 = tox.get("lc50_inhalation_mg_m3")
    seuil = lc50 / 10.0 if lc50 else None

    return {
        "cid": cid,
        "basic": basic,
        "toxicity": tox,
        "ghs": ghs,
        "seuil_toxique_estime_mg_m3": seuil,
    }


if __name__ == "__main__":
    print("🧪 Test PubChem API...\n")
    for n in ["Benzene", "Hydrogen sulfide", "Ammonia", "Chlorine", "Phenol"]:
        print(f"=== {n} ===")
        p = get_chemical_profile(n)
        if not p:
            print("  ❌ Aucune donnée\n")
            continue
        b, t, g = p["basic"], p["toxicity"], p["ghs"]
        print(f"  CID {b['cid']} | {b['molecular_formula']} | {b['molecular_weight']} g/mol | CAS {b['cas_number']}")
        print(f"  LD50 oral {t['ld50_oral_mg_kg']} mg/kg | LC50 inh. {t['lc50_inhalation_mg_m3']} mg/m³")
        print(f"  Seuil estimé {p['seuil_toxique_estime_mg_m3']} mg/m³ | H : {g['h_codes']} | {g['signal_word']}\n")
