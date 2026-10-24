"""
ghs_service.py — Récupération des infos GHS (pictogrammes, H/P phrases)
depuis PubChem. Cache local pour éviter les appels répétés.
"""
import json
import time
from pathlib import Path
import requests

CACHE_FILE = Path(__file__).parent / "ghs_cache.json"
CACHE_TTL = 60 * 60 * 24 * 7  # 7 jours
TIMEOUT = 10
BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


# ─────────────────────────────────────────────────────────
# Cache
# ─────────────────────────────────────────────────────────
def _load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False),
                              encoding="utf-8")
    except Exception:
        pass


def _cache_get(key):
    cache = _load_cache()
    entry = cache.get(key)
    if entry and time.time() - entry.get("_ts", 0) < CACHE_TTL:
        return entry.get("data")
    return None


def _cache_set(key, data):
    cache = _load_cache()
    cache[key] = {"_ts": time.time(), "data": data}
    _save_cache(cache)


# ─────────────────────────────────────────────────────────
# PubChem helpers
# ─────────────────────────────────────────────────────────
def _get_cid(name: str):
    url = f"{BASE}/compound/name/{requests.utils.quote(name)}/cids/JSON"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            cids = r.json().get("IdentifierList", {}).get("CID", [])
            return cids[0] if cids else None
    except Exception:
        pass
    return None


def _get_ghs_section(cid: int):
    url = (f"{BASE}/view/data/compound/{cid}/JSON"
           f"?heading=GHS+Classification")
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────
def _walk_strings(node, out):
    """Parcourt récursivement un dict PubChem et collecte les 'String'."""
    if isinstance(node, dict):
        if "String" in node and isinstance(node["String"], str):
            out.append(node["String"])
        for v in node.values():
            _walk_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_strings(v, out)


def _extract_h_phrases(data):
    strings = []
    _walk_strings(data, strings)
    seen, res = set(), []
    for s in strings:
        if s.startswith("H") and len(s) < 200:
            token = s.split()[0].rstrip(":")
            if token.startswith("H") and token not in seen:
                seen.add(token)
                res.append(s)
    return res


def _extract_p_phrases(data):
    strings = []
    _walk_strings(data, strings)
    seen, res = set(), []
    for s in strings:
        if s.startswith("P") and len(s) < 200:
            token = s.split()[0].rstrip(":")
            if token.startswith("P") and token not in seen:
                seen.add(token)
                res.append(s)
    return res


def _extract_pictograms(data, cid):
    """Retourne les URLs des pictogrammes GHS trouvés dans la section."""
    strings = []
    _walk_strings(data, strings)
    pict_names = set()
    known = {"Flame", "Corrosion", "Skull", "Exclamation",
             "Health Hazard", "Flame Over Circle", "Exploding Bomb",
             "Gas Cylinder", "Environment", "Biohazard"}
    for s in strings:
        for k in known:
            if k.lower() in s.lower():
                pict_names.add(k)
    # URLs officielles PubChem des pictogrammes
    urls = []
    for name in pict_names:
        slug = name.replace(" ", "_")
        urls.append(
            f"https://pubchem.ncbi.nlm.nih.gov/images/ghs/{slug}.svg"
        )
    return urls


# ─────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────
def get_ghs_info(substance_name: str) -> dict | None:
    """
    Retourne :
      {
        "cid": int,
        "pictograms": [url,...],
        "h_phrases": [str,...],
        "p_phrases": [str,...],
        "sds_url": str,
        "source": "pubchem"
      }
    ou None si introuvable.
    """
    if not substance_name or len(substance_name.strip()) < 2:
        return None
    key = substance_name.strip().lower()
    cached = _cache_get(key)
    if cached is not None:
        return cached

    cid = _get_cid(substance_name)
    if not cid:
        _cache_set(key, None)
        return None

    ghs_data = _get_ghs_section(cid)
    if not ghs_data:
        result = {
            "cid": cid,
            "pictograms": [],
            "h_phrases": [],
            "p_phrases": [],
            "sds_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
                       f"#section=Safety-and-Hazards",
            "source": "pubchem",
        }
        _cache_set(key, result)
        return result

    result = {
        "cid": cid,
        "pictograms": _extract_pictograms(ghs_data, cid),
        "h_phrases": _extract_h_phrases(ghs_data),
        "p_phrases": _extract_p_phrases(ghs_data),
        "sds_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
                   f"#section=Safety-and-Hazards",
        "source": "pubchem",
    }
    _cache_set(key, result)
    return result


def render_ghs_block(substance_name: str, st_module=None):
    """
    Bloc Streamlit prêt à l'emploi. Usage :
        from ghs_service import render_ghs_block
        render_ghs_block(substance_env)
    """
    st = st_module
    if st is None:
        import streamlit as st  # noqa
    info = get_ghs_info(substance_name)
    if not info:
        st.caption(f"ℹ️ Pas d'information GHS trouvée pour « {substance_name} ».")
        return
    st.markdown("### ⚠️ Classification GHS")
    if info.get("cid"):
        st.caption(f"PubChem CID : {info['cid']}")
    if info["pictograms"]:
        cols = st.columns(min(len(info["pictograms"]), 5))
        for i, url in enumerate(info["pictograms"]):
            try:
                cols[i % len(cols)].image(url, width=70)
            except Exception:
                cols[i % len(cols)].caption("⚠️")
    if info["h_phrases"]:
        st.markdown("**Phrases H :**")
        for h in info["h_phrases"][:15]:
            st.caption(f"• {h}")
    if info["p_phrases"]:
        st.markdown("**Phrases P :**")
        for p in info["p_phrases"][:15]:
            st.caption(f"• {p}")
    st.link_button("📄 Fiche de sécurité (PubChem)", info["sds_url"])