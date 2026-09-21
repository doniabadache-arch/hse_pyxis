"""
chemical_db_interface.py
========================
Interface entre dispersion_aloha.py et la base de données
des substances chimiques (data/substances_clean.json).

Fournit get_chemical_properties(substance_name) qui retourne :
- nom
- masse_moleculaire
- seuil_toxique_mg_m3
- cas
- un
- adr_class

Usage:
    from chemical_db_interface import get_chemical_properties
    props = get_chemical_properties("ammoniac")
"""

import json
from pathlib import Path


# ============================================================
# CHARGEMENT DE LA BASE
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
# SEUILS TOXIQUES PAR DÉFAUT (mg/m³)
# ============================================================
# Sources : ACGIH TLV, OSHA PEL, EPA RMP
# Utilisés si le seuil n'est pas trouvé dans la base

_SEUILS_TOXIQUES_DEFAUT = {
    "ammoniac": 35.0,          # NH3 — ACGIH TLV (25 ppm)
    "ammonia": 35.0,
    "nh3": 35.0,
    "h2s": 14.0,               # H2S — ACGIH TLV (10 ppm)
    "sulfure d'hydrogene": 14.0,
    "hydrogen sulfide": 14.0,
    "chlore": 3.0,             # Cl2 — ACGIH TLV
    "chlorine": 3.0,
    "cl2": 3.0,
    "co": 55.0,                # CO — ACGIH TLV (50 ppm)
    "monoxyde de carbone": 55.0,
    "carbon monoxide": 55.0,
    "co2": 9000.0,             # CO2 — ACGIH TLV (5000 ppm)
    "dioxyde de carbone": 9000.0,
    "carbon dioxide": 9000.0,
    "methane": 0.0,            # CH4 — asphyxiant (pas toxique)
    "ch4": 0.0,
    "benzene": 1.6,            # C6H6 — ACGIH TLV
    "benzène": 1.6,
    "toluene": 75.0,           # C7H8 — ACGIH TLV
    "tolvène": 75.0,
    "so2": 5.2,                # SO2 — ACGIH TLV
    "dioxyde de soufre": 5.2,
    "sulfur dioxide": 5.2,
    "nox": 9.4,                # NO2 — ACGIH TLV
    "no2": 9.4,
    "hcl": 7.0,                # HCl — ACGIH TLV
    "acide chlorhydrique": 7.0,
    "hydrochloric acid": 7.0,
    "generic": 100.0,          # valeur par défaut
}

# Masses molaires par défaut (g/mol)
_MASSES_MOLAIRES_DEFAUT = {
    "ammoniac": 17.03,
    "ammonia": 17.03,
    "nh3": 17.03,
    "h2s": 34.08,
    "sulfure d'hydrogene": 34.08,
    "hydrogen sulfide": 34.08,
    "chlore": 70.90,
    "chlorine": 70.90,
    "cl2": 70.90,
    "co": 28.01,
    "monoxyde de carbone": 28.01,
    "carbon monoxide": 28.01,
    "co2": 44.01,
    "dioxyde de carbone": 44.01,
    "carbon dioxide": 44.01,
    "methane": 16.04,
    "ch4": 16.04,
    "benzene": 78.11,
    "benzène": 78.11,
    "toluene": 92.14,
    "tolvène": 92.14,
    "so2": 64.07,
    "dioxyde de soufre": 64.07,
    "sulfur dioxide": 64.07,
    "no2": 46.01,
    "hcl": 36.46,
    "acide chlorhydrique": 36.46,
    "generic": 50.0,
}


# ============================================================
# NORMALISATION
# ============================================================
def _normalize(name: str) -> str:
    """Normalise un nom de substance pour la recherche."""
    if not name:
        return "generic"
    return name.lower().strip()


def _find_in_db(name: str):
    """Cherche une substance dans substances_clean.json."""
    db = _load_db()
    name_norm = _normalize(name)

    for sub in db:
        sub_name = _normalize(sub.get("name") or "")
        # Match exact
        if sub_name == name_norm:
            return sub
        # Match partiel
        if name_norm in sub_name or sub_name in name_norm:
            return sub

    return None


# ============================================================
# FONCTION PRINCIPALE
# ============================================================
def get_chemical_properties(substance: str) -> dict:
    """
    Retourne les propriétés chimiques d'une substance.

    Parameters
    ----------
    substance : str
        Nom de la substance (ex: "ammoniac", "H2S", "chlore")

    Returns
    -------
    dict avec :
        - nom : str
        - masse_moleculaire : float (g/mol)
        - seuil_toxique_mg_m3 : float (mg/m³)
        - cas : str or None
        - un : str or None
        - adr_class : str or None
        - source : str ("json" ou "default")
    """
    name_norm = _normalize(substance)

    # 1. Chercher dans substances_clean.json
    sub = _find_in_db(substance)

    if sub:
        return {
            "nom": sub.get("name") or substance,
            "masse_moleculaire": _get_masse_molaire(name_norm, sub),
            "seuil_toxique_mg_m3": _get_seuil_toxique(name_norm, sub),
            "cas": sub.get("cas"),
            "un": sub.get("un"),
            "adr_class": sub.get("adr_class"),
            "source": "json",
        }

    # 2. Fallback : valeurs par défaut
    return {
        "nom": substance,
        "masse_moleculaire": _MASSES_MOLAIRES_DEFAUT.get(
            name_norm, _MASSES_MOLAIRES_DEFAUT["generic"]
        ),
        "seuil_toxique_mg_m3": _SEUILS_TOXIQUES_DEFAUT.get(
            name_norm, _SEUILS_TOXIQUES_DEFAUT["generic"]
        ),
        "cas": None,
        "un": None,
        "adr_class": None,
        "source": "default",
    }


def _get_masse_molaire(name_norm: str, sub: dict) -> float:
    """Récupère la masse molaire depuis le JSON ou fallback."""
    # Si présente dans le JSON
    if sub.get("masse_moleculaire"):
        return float(sub["masse_moleculaire"])
    # Sinon, table par défaut
    return _MASSES_MOLAIRES_DEFAUT.get(name_norm, _MASSES_MOLAIRES_DEFAUT["generic"])


def _get_seuil_toxique(name_norm: str, sub: dict) -> float:
    """Récupère le seuil toxique depuis le JSON ou fallback."""
    # Si présent dans le JSON
    if sub.get("seuil_toxique_mg_m3"):
        return float(sub["seuil_toxique_mg_m3"])
    # Sinon, table par défaut
    return _SEUILS_TOXIQUES_DEFAUT.get(name_norm, _SEUILS_TOXIQUES_DEFAUT["generic"])


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================
def list_substances():
    """Retourne la liste des substances disponibles."""
    db = _load_db()
    return [s.get("name") for s in db if s.get("name")]


def reload_db():
    """Force le rechargement de la base."""
    global _CHEMICAL_DB
    _CHEMICAL_DB = None
    return _load_db()


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Test de chemical_db_interface")
    print("=" * 60)

    # Test avec quelques substances
    test_substances = ["ammoniac", "H2S", "chlore", "CO2", "unknown_substance"]

    for sub in test_substances:
        props = get_chemical_properties(sub)
        print(f"\n📌 {sub}:")
        print(f"   nom                 = {props['nom']}")
        print(f"   masse_moleculaire   = {props['masse_moleculaire']} g/mol")
        print(f"   seuil_toxique       = {props['seuil_toxique_mg_m3']} mg/m³")
        print(f"   cas                 = {props['cas']}")
        print(f"   un                  = {props['un']}")
        print(f"   adr_class           = {props['adr_class']}")
        print(f"   source              = {props['source']}")

    print(f"\n📊 Total substances dans la base : {len(list_substances())}")