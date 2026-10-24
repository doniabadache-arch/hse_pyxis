"""
chemical_db_interface.py — HSE PYXIS v2
========================================
Interface intelligente pour les propriétés chimiques.

Recherche en 5 niveaux (du plus fiable au moins fiable) :
    1. Base locale — correspondance exacte
    2. PubChem — recherche multi-essais (nom direct, traduction, fuzzy)
    3. Base locale — correspondance partielle
    4. Table TLV interne (substances courantes)
    5. Valeur conservatrice par défaut

Chaque résultat indique clairement sa source et sa fiabilité.

Usage:
    from chemical_db_interface import get_chemical_properties
    props = get_chemical_properties("Acide sulfurique")
    props = get_chemical_properties("H2SO4")
    props = get_chemical_properties("Sulfuric acid")
"""

import json
import re
import time
import unicodedata
from pathlib import Path


# ============================================================
# CHARGEMENT DE LA BASE LOCALE
# ============================================================
_CHEMICAL_DB = None
_CHEMICAL_DB_PATH = Path("data/substances_clean.json")


def _load_db():
    """Charge substances_clean.json (une seule fois)."""
    global _CHEMICAL_DB
    if _CHEMICAL_DB is not None:
        return _CHEMICAL_DB

    if not _CHEMICAL_DB_PATH.exists():
        _CHEMICAL_DB = []
        return _CHEMICAL_DB

    with open(_CHEMICAL_DB_PATH, "r", encoding="utf-8") as f:
        _CHEMICAL_DB = json.load(f)

    return _CHEMICAL_DB


# ============================================================
# NORMALISATION AVANCÉE
# ============================================================
def _normalize(name: str) -> str:
    """Normalise un nom : minuscules, sans accents, sans tirets/espaces."""
    if not name:
        return ""
    # Suppression des accents
    s = unicodedata.normalize('NFKD', name)
    s = s.encode('ascii', 'ignore').decode('ascii')
    # Minuscules + suppression de tout sauf lettres/chiffres
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '', s)
    return s


def _normalize_with_separators(name: str) -> str:
    """Normalise mais garde les séparateurs (pour comparaison humaine)."""
    if not name:
        return ""
    s = unicodedata.normalize('NFKD', name)
    s = s.encode('ascii', 'ignore').decode('ascii')
    return s.lower().strip()


# ============================================================
# TABLE TLV INTERNE (mg/m³) — Substances courantes
# ============================================================
# Sources : ACGIH TLV, OSHA PEL, INRS (France)
# Utilisée si le seuil n'est PAS trouvé ailleurs
#
# Format : {"nom_normalise": (seuil_mg_m3, masse_molaire_g_mol)}
_SEUILS_TLV = {
    # ─── Gaz industriels ───
    "ammoniac":          (35.0, 17.03),
    "ammonia":           (35.0, 17.03),
    "nh3":               (35.0, 17.03),
    "h2s":               (14.0, 34.08),
    "hydrogensulfide":   (14.0, 34.08),
    "sulfuredhydrogene": (14.0, 34.08),
    "sulfuretdhydrogene":(14.0, 34.08),
    "chlore":            (3.0, 70.90),
    "chlorine":          (3.0, 70.90),
    "cl2":               (3.0, 70.90),
    "co":                (55.0, 28.01),
    "monoxydedecarbone": (55.0, 28.01),
    "carbonmonoxide":    (55.0, 28.01),
    "co2":               (9000.0, 44.01),
    "dioxydedecarbone":  (9000.0, 44.01),
    "carbondioxide":     (9000.0, 44.01),
    "methane":           (0.0, 16.04),  # Asphyxiant
    "ch4":               (0.0, 16.04),
    "so2":               (5.2, 64.07),
    "dioxydedesoufre":   (5.2, 64.07),
    "sulfurdioxide":     (5.2, 64.07),
    "no2":               (9.4, 46.01),
    "dioxydedazote":     (9.4, 46.01),
    "nitrogendioxide":   (9.4, 46.01),
    "nox":               (9.4, 46.01),

    # ─── Acides ───
    "acidesulfurique":   (1.0, 98.08),
    "sulfuricacid":      (1.0, 98.08),
    "h2so4":             (1.0, 98.08),
    "acidechlorhydrique":(7.0, 36.46),
    "hydrochloricacid":  (7.0, 36.46),
    "hcl":               (7.0, 36.46),
    "acidenitrique":     (5.0, 63.01),
    "nitricacid":        (5.0, 63.01),
    "hno3":              (5.0, 63.01),
    "acideacetique":     (25.0, 60.05),
    "aceticacid":        (25.0, 60.05),
    "acidefluorhydrique":(2.5, 20.01),
    "hydrofluoricacid":  (2.5, 20.01),
    "hf":                (2.5, 20.01),
    "acideformique":     (9.0, 46.03),
    "formicacid":        (9.0, 46.03),
    "acidephosphorique": (1.0, 98.00),
    "phosphoricacid":    (1.0, 98.00),

    # ─── Solvants ───
    "benzene":           (1.6, 78.11),
    "benzene":           (1.6, 78.11),
    "toluene":           (75.0, 92.14),
    "toluene":           (75.0, 92.14),
    "xylene":            (435.0, 106.17),
    "xylene":            (435.0, 106.17),
    "acetone":           (1780.0, 58.08),
    "acetone":           (1780.0, 58.08),
    "methanol":          (262.0, 32.04),
    "ethanol":           (1880.0, 46.07),
    "propanol":          (492.0, 60.10),
    "isopropanol":       (983.0, 60.10),
    "alcoolisopropylique":(983.0, 60.10),
    "hexane":            (176.0, 86.18),
    "heptane":           (1640.0, 100.20),
    "pentane":           (2950.0, 72.15),
    "cyclohexane":       (344.0, 84.16),
    "trichlorethylene":  (269.0, 131.39),
    "trichloroethylene": (269.0, 131.39),
    "perchloroethylene": (339.0, 165.83),
    "dichloromethane":   (174.0, 84.93),
    "chloroform":        (49.0, 119.38),

    # ─── Alcools & Éthers ───
    "glycol":            (None, 62.07),  # Ethylene glycol
    "ethyleneglycol":    (None, 62.07),

    # ─── Aldéhydes ───
    "formaldehyde":      (0.37, 30.03),
    "formaldehyde":      (0.37, 30.03),
    "acetaldehyde":      (45.0, 44.05),

    # ─── Phénols & Divers ───
    "phenol":            (19.0, 94.11),
    "phenol":            (19.0, 94.11),
    "styrene":           (213.0, 104.15),
    "styrene":           (213.0, 104.15),
    "acrylonitrile":     (4.3, 53.06),
    "acrylonitrile":     (4.3, 53.06),
    "acrylamide":        (0.03, 71.08),
    "acrylamide":        (0.03, 71.08),
    "epichlorhydrine":   (3.8, 92.52),
    "epichlorohydrin":   (3.8, 92.52),

    # ─── Pesticides / Divers ───
    "phosgene":          (0.4, 98.92),
    "phosgene":          (0.4, 98.92),
    "cyanure":           (5.0, 26.02),
    "cyanide":           (5.0, 26.02),
    "hcn":               (5.0, 27.03),
    "acidecyanhydrique": (5.0, 27.03),
    "hydrogencyanide":   (5.0, 27.03),
}


# ============================================================
# TABLE DE TRADUCTION FR → EN (pour PubChem)
# ============================================================
_FR_EN_DICT = {
    "acide": "acid",
    "sulfurique": "sulfuric",
    "chlorhydrique": "hydrochloric",
    "nitrique": "nitric",
    "acetique": "acetic",
    "formique": "formic",
    "phosphorique": "phosphoric",
    "fluorhydrique": "hydrofluoric",
    "cyanhydrique": "hydrocyanic",
    "ammoniac": "ammonia",
    "chlore": "chlorine",
    "soufre": "sulfur",
    "azote": "nitrogen",
    "carbone": "carbon",
    "monoxyde": "monoxide",
    "dioxyde": "dioxide",
    "hydrogene": "hydrogen",
    "oxyde": "oxide",
    "sodium": "sodium",
    "potassium": "potassium",
    "calcium": "calcium",
    "methane": "methane",
    "ethane": "ethane",
    "propane": "propane",
    "butane": "butane",
    "benzene": "benzene",
    "toluene": "toluene",
    "methanol": "methanol",
    "ethanol": "ethanol",
    "propanol": "propanol",
    "alcool": "alcohol",
    "isopropylique": "isopropyl",
    "phenol": "phenol",
    "formaldehyde": "formaldehyde",
    "acetone": "acetone",
    "hexane": "hexane",
    "heptane": "heptane",
    "pentane": "pentane",
}


def _translate_fr_to_en(name: str) -> str:
    """Traduit un nom français en anglais (mot par mot)."""
    if not name:
        return ""
    words = re.split(r'[\s\-]+', name.lower().strip())
    translated = [_FR_EN_DICT.get(w, w) for w in words]
    return " ".join(translated)


# ============================================================
# RECHERCHE DANS LA BASE LOCALE
# ============================================================
def _find_exact_in_db(name: str):
    """Recherche EXACTE (nom normalisé identique)."""
    if not name:
        return None
    db = _load_db()
    key = _normalize(name)
    for sub in db:
        sub_name = sub.get("name")
        if sub_name and _normalize(sub_name) == key:
            return sub
    return None


def _find_partial_in_db(name: str):
    """Recherche PARTIELLE (nom inclus dans un autre)."""
    if not name:
        return None
    key = _normalize(name)
    # Minimum 6 caractères pour éviter les faux positifs (ex: "chlore" → "trichlorethylene")
    if len(key) < 6:
        return None

    db = _load_db()
    best_match = None
    best_score = 0

    for sub in db:
        sub_name = sub.get("name")
        if not sub_name:
            continue
        sub_key = _normalize(sub_name)
        if not sub_key:
            continue

        # Le nom cherché est inclus dans le nom DB (ex: "sulfurique" dans "acidesulfurique")
        if key in sub_key:
            # Score = ratio de correspondance
            score = len(key) / len(sub_key)
            if score > best_score:
                best_score = score
                best_match = sub

    # Ne retourner que si le score est acceptable (>50% de correspondance)
    return best_match if best_score > 0.5 else None


# ============================================================
# PUBLICATION CHEMICHIQUE (PubChem)
# ============================================================
_PROPS_CACHE = {}
_CACHE_TTL = 3600  # 1 heure
_NEGATIVE_TTL = 300  # 5 minutes


def _fetch_pubchem(name: str):
    """
    Interroge PubChem avec plusieurs stratégies :
    1. Nom direct
    2. Traduction FR → EN
    3. Version simplifiée du nom
    """
    if not name or len(name.strip()) < 2:
        return None

    try:
        from pubchem_service import get_chemical_profile
    except ImportError:
        return None

    strategies = [
        name.strip(),  # 1. Original
        _translate_fr_to_en(name.strip()),  # 2. Traduit FR→EN
    ]

    # 3. Ajouter la version sans parenthèses/concentration
    simplified = re.sub(r'\([^)]*\)', '', name).strip()
    simplified = re.sub(r'\d+%?', '', simplified).strip()
    if simplified and simplified not in strategies:
        strategies.append(simplified)

    for strategy in strategies:
        if not strategy or len(strategy) < 2:
            continue
        try:
            profile = get_chemical_profile(strategy)
            if profile and profile.get("basic"):
                return profile
        except Exception as e:
            print(f"[PubChem] '{strategy}' → {e}")
            continue

    return None


# ============================================================
# FONCTION PRINCIPALE
# ============================================================
def get_chemical_properties(substance: str) -> dict:
    """
    Récupère les propriétés chimiques d'une substance avec recherche multi-niveaux.

    Parameters
    ----------
    substance : str
        Nom de la substance (FR / EN / formule / nom commercial / CAS)

    Returns
    -------
    dict avec :
        - nom : str
        - masse_moleculaire : float (g/mol)
        - seuil_toxique_mg_m3 : float (mg/m³)
        - cas, un, adr_class : str or None
        - source : "json" | "pubchem" | "tlv" | "default"
        - confidence : "high" | "medium" | "low"
        - matched_as : str (ce qui a été trouvé)
        - + champs PubChem si disponibles (cid, ld50, h_codes, etc.)
    """
    if not substance or not substance.strip():
        return _default_result(substance)

    cache_key = _normalize(substance)
    cached = _PROPS_CACHE.get(cache_key)
    if cached:
        expiry, result = cached
        if expiry is None or time.time() < expiry:
            return dict(result)

    pubchem_failed = False

    # ══════════════════════════════════════════════════════════
    # NIVEAU 1 : Recherche exacte dans la base locale
    # ══════════════════════════════════════════════════════════
    sub = _find_exact_in_db(substance)
    if sub:
        result = _build_from_local(sub, substance, "json")
        _PROPS_CACHE[cache_key] = (None, result)
        return dict(result)

    # ══════════════════════════════════════════════════════════
    # NIVEAU 2 : PubChem (avec traduction automatique)
    # ══════════════════════════════════════════════════════════
    pc = _fetch_pubchem(substance)
    if pc and pc.get("basic"):
        result = _build_from_pubchem(pc, substance)
        _PROPS_CACHE[cache_key] = (None, result)
        return dict(result)

    pubchem_failed = True

    # ══════════════════════════════════════════════════════════
    # NIVEAU 3 : Recherche partielle dans la base locale
    # ══════════════════════════════════════════════════════════
    sub_partial = _find_partial_in_db(substance)
    if sub_partial:
        result = _build_from_local(sub_partial, substance, "json")
        result["confidence"] = "medium"
        _PROPS_CACHE[cache_key] = (None, result)
        return dict(result)

    # ══════════════════════════════════════════════════════════
    # NIVEAU 4 : Table TLV interne
    # ══════════════════════════════════════════════════════════
    tlv_result = _lookup_tlv(substance)
    if tlv_result:
        _PROPS_CACHE[cache_key] = (None, tlv_result)
        return dict(tlv_result)

    # ══════════════════════════════════════════════════════════
    # NIVEAU 5 : Valeur conservatrice par défaut
    # ══════════════════════════════════════════════════════════
    result = _default_result(substance)
    expiry = time.time() + _NEGATIVE_TTL if pubchem_failed else None
    _PROPS_CACHE[cache_key] = (expiry, result)
    return dict(result)


# ============================================================
# CONSTRUCTEURS DE RÉSULTATS
# ============================================================
def _build_from_local(sub: dict, original_name: str, source_label: str) -> dict:
    """Construit un résultat depuis la base locale."""
    name = sub.get("name") or original_name

    # Chercher masse et seuil dans TLV
    tlv = _lookup_tlv(name)
    masse = sub.get("masse_moleculaire") or (tlv["masse_moleculaire"] if tlv else None)
    seuil = sub.get("seuil_toxique_mg_m3") or (tlv["seuil_toxique_mg_m3"] if tlv else None)

    confidence = "high"
    source = source_label
    if not masse or not seuil:
        confidence = "medium"

    return {
        "nom": name,
        "masse_moleculaire": masse or 50.0,
        "seuil_toxique_mg_m3": seuil or 100.0,
        "cas": sub.get("cas"),
        "un": sub.get("un"),
        "adr_class": sub.get("adr_class"),
        "source": source,
        "confidence": confidence,
        "matched_as": name,
        "seuil_toxique_estimated": seuil is None,
        "masse_estimated": masse is None,
    }


def _build_from_pubchem(profile: dict, original_name: str) -> dict:
    """Construit un résultat depuis PubChem."""
    basic = profile["basic"]
    tox = profile.get("toxicity", {})
    ghs = profile.get("ghs", {})
    seuil_estim = profile.get("seuil_toxique_estime_mg_m3")

    return {
        "nom": basic.get("iupac_name") or original_name,
        "masse_moleculaire": basic.get("molecular_weight") or 50.0,
        "seuil_toxique_mg_m3": seuil_estim or 100.0,
        "cas": basic.get("cas_number"),
        "un": None,
        "adr_class": None,
        "source": "pubchem",
        "confidence": "high" if basic.get("cas_number") else "medium",
        "matched_as": basic.get("iupac_name") or original_name,
        "seuil_toxique_estimated": seuil_estim is None,
        "masse_estimated": False,
        # Champs supplémentaires PubChem
        "cid": basic.get("cid"),
        "molecular_formula": basic.get("molecular_formula"),
        "ld50_oral_mg_kg": tox.get("ld50_oral_mg_kg"),
        "lc50_inhalation_mg_m3": tox.get("lc50_inhalation_mg_m3"),
        "h_codes": ghs.get("h_codes", []),
        "signal_word": ghs.get("signal_word"),
    }


def _lookup_tlv(name: str):
    """Cherche dans la table TLV interne."""
    if not name:
        return None
    key = _normalize(name)
    if key in _SEUILS_TLV:
        seuil, masse = _SEUILS_TLV[key]
        return {
            "nom": name,
            "seuil_toxique_mg_m3": seuil,
            "masse_moleculaire": masse,
            "cas": None,
            "un": None,
            "adr_class": None,
            "source": "tlv",
            "confidence": "medium",
            "matched_as": name,
            "seuil_toxique_estimated": False,
            "masse_estimated": False,
        }
    return None


def _default_result(name: str) -> dict:
    """Résultat conservateur par défaut."""
    return {
        "nom": name or "Substance inconnue",
        "masse_moleculaire": 50.0,
        "seuil_toxique_mg_m3": 100.0,
        "cas": None,
        "un": None,
        "adr_class": None,
        "source": "default",
        "confidence": "low",
        "matched_as": name or "—",
        "seuil_toxique_estimated": True,
        "masse_estimated": True,
    }


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================
def list_substances():
    """Liste des substances nommées dans la base locale."""
    db = _load_db()
    return [s.get("name") for s in db if s.get("name")]


def reload_db():
    """Force le rechargement."""
    global _CHEMICAL_DB
    _CHEMICAL_DB = None
    _PROPS_CACHE.clear()
    return _load_db()


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("🧪 Test chemical_db_interface (recherche intelligente)")
    print("=" * 70)

    tests = [
        # Noms exacts (local)
        "AMINO-2 BUTANE",
        "ACIDE SULFURIQUE",
        # Noms français (TLV)
        "ammoniac",
        "chlore",
        "acide sulfurique",
        "acide chlorhydrique",
        "monoxyde de carbone",
        "dioxyde de carbone",
        # Formules
        "H2S",
        "NH3",
        "CO",
        "CO2",
        "H2SO4",
        # Noms anglais (PubChem)
        "Benzene",
        "Phenol",
        "Acetone",
        "Sulfuric acid",
        # Noms commerciaux / cas
        "108-95-2",  # CAS du phénol
        # Inconnu
        "xyz_unknown_123",
    ]

    for test in tests:
        props = get_chemical_properties(test)
        print(f"\n📌 Demande : « {test} »")
        print(f"   Nom trouvé       : {props['nom']}")
        print(f"   Source           : {props['source']}")
        print(f"   Confiance        : {props['confidence']}")
        print(f"   Masse molaire    : {props['masse_moleculaire']} g/mol")
        print(f"   Seuil toxique    : {props['seuil_toxique_mg_m3']} mg/m³")
        if props.get("cas"):
            print(f"   CAS              : {props['cas']}")
        if props.get("h_codes"):
            print(f"   H-codes          : {', '.join(props['h_codes'])}")

    print(f"\n📊 Total substances nommées dans la base : {len(list_substances())}")