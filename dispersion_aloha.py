"""
dispersion_aloha.py
====================
Étape 3 du prototype - cible environnement : étude de dispersion simplifiée type ALOHA.

Modèle retenu : panache gaussien continu (Pasquill-Gifford), formulation de Martin (1976),
couramment utilisée pour des estimations rapides d'impact -- PAS un modèle physique
industriel complet et validé (cf. limites assumées du projet, section 4 du document de
cadrage). Il donne un ordre de grandeur de la distance d'impact, utile pour prioriser,
pas pour du dimensionnement réglementaire fin.

Entrées saisies MANUELLEMENT par l'inspecteur :
- substance            (nom -> propriétés récupérées via chemical_db_interface, déjà en place)
- taille_fuite_kg, duree_fuite_s
- vitesse_vent_m_s, direction_vent_deg
- temperature_c, pression_hpa, humidite_pct, latitude, longitude
  (pression/humidité/coordonnées : en vue du branchement OpenWeather, cf. weather_service.py,
  pas utilisées dans le calcul de dispersion lui-même dans cette version simplifiée)

Étapes du calcul :
1. Débit d'émission moyen Q (g/s) = masse fuite (g) / durée de fuite (s)
2. Classe de stabilité atmosphérique estimée à partir de la vitesse du vent (simplification :
   pas de donnée d'ensoleillement/nébulosité dans cette version -> hypothèse conditions diurnes
   modérées, cf. limites assumées)
3. Coefficients de dispersion sigma_y, sigma_z (Pasquill-Gifford, formulation Martin 1976)
4. Concentration sur l'axe du panache, au niveau du sol : C(x) = Q / (pi * u * sigma_y * sigma_z)
5. Distance d'impact = distance x la plus grande pour laquelle C(x) >= seuil toxique retenu
"""

import numpy as np
from chemical_db_interface import get_chemical_properties

# Coefficients de Martin (1976), conditions rurales -- x en km ; les formules ci-dessous
# donnent nativement sigma_y / sigma_z EN KM (comme dans la littérature d'origine) : la
# conversion en mètres est faite dans sigma_y()/sigma_z() ci-dessous, pas ici.
_COEFFS_PASQUILL_GIFFORD = {
    "A": {"ay": 0.22, "sigma_z": lambda x_km: 0.20 * x_km},
    "B": {"ay": 0.16, "sigma_z": lambda x_km: 0.12 * x_km},
    "C": {"ay": 0.11, "sigma_z": lambda x_km: 0.08 * x_km * (1 + 0.0002 * x_km) ** -0.5},
    "D": {"ay": 0.08, "sigma_z": lambda x_km: 0.06 * x_km * (1 + 0.0015 * x_km) ** -0.5},
    "E": {"ay": 0.06, "sigma_z": lambda x_km: 0.03 * x_km * (1 + 0.0003 * x_km) ** -1},
    "F": {"ay": 0.04, "sigma_z": lambda x_km: 0.016 * x_km * (1 + 0.0003 * x_km) ** -1},
}

_KM_TO_M = 1000.0

# Codes STABLES pour la provenance des données météo (stockés en base).
# Traduits à l'affichage par ui.display.tr_meteo().
SOURCE_METEO_MANUELLE = "manuelle"
SOURCE_METEO_OPENWEATHER = "openweather"
SOURCES_METEO = (SOURCE_METEO_MANUELLE, SOURCE_METEO_OPENWEATHER)

# Les classes de stabilité de Pasquill (A..F) sont une notation internationale :
# elles ne sont volontairement PAS traduites.
CLASSES_STABILITE = tuple(_COEFFS_PASQUILL_GIFFORD.keys())


def determiner_classe_stabilite(vitesse_vent_m_s: float) -> str:
    """Estime la classe de stabilité de Pasquill à partir de la seule vitesse du vent.

    Simplification assumée : en l'absence de données d'ensoleillement/nébulosité dans cette
    version du prototype, on retient une hypothèse de conditions diurnes modérées (ni très
    instable, ni très stable) -- classe D par défaut aux vents forts, A/B aux vents faibles.
    Cette hypothèse est documentée comme limite du prototype.
    """
    u = vitesse_vent_m_s
    if u < 2:
        return "A"
    elif u < 3:
        return "B"
    elif u < 5:
        return "C"
    elif u < 6:
        return "D"
    else:
        return "D"  # conditions neutres, hypothèse la plus courante aux vents forts


def sigma_y(x_km: float, classe: str) -> float:
    """Écart-type latéral du panache, en MÈTRES (conversion depuis la formule native en km)."""
    a = _COEFFS_PASQUILL_GIFFORD[classe]["ay"]
    return a * x_km * (1 + 0.0001 * x_km) ** -0.5 * _KM_TO_M


def sigma_z(x_km: float, classe: str) -> float:
    """Écart-type vertical du panache, en MÈTRES (conversion depuis la formule native en km)."""
    return _COEFFS_PASQUILL_GIFFORD[classe]["sigma_z"](x_km) * _KM_TO_M


def concentration_axe(x_m: float, debit_emission_g_s: float, vitesse_vent_m_s: float, classe: str) -> float:
    """Concentration au niveau du sol, sur l'axe du panache, à la distance x_m (mètres).
    Retourne une concentration en g/m3. x_m = 0 -> renvoie une valeur très grande (source).
    """
    if x_m <= 0:
        return float("inf")
    x_km = x_m / 1000.0
    sy = sigma_y(x_km, classe)
    sz = sigma_z(x_km, classe)
    if sy <= 0 or sz <= 0:
        return float("inf")
    return debit_emission_g_s / (np.pi * vitesse_vent_m_s * sy * sz)


def calculer_distance_impact(debit_emission_g_s: float, vitesse_vent_m_s: float, classe: str,
                              seuil_g_m3: float, x_max_m: float = 20_000, resolution: int = 4000) -> float:
    """Balaye l'axe du panache et retourne la plus grande distance (m) à laquelle la
    concentration reste >= au seuil toxique retenu (distance d'impact estimée).
    """
    distances = np.linspace(1, x_max_m, resolution)
    concentrations = np.array([
        concentration_axe(x, debit_emission_g_s, vitesse_vent_m_s, classe) for x in distances
    ])
    au_dessus_seuil = distances[concentrations >= seuil_g_m3]
    if au_dessus_seuil.size == 0:
        return 0.0  # même à la source, la concentration ne dépasse pas le seuil retenu
    return float(au_dessus_seuil.max())


def evaluer_dispersion(symptom_id: str, substance: str, taille_fuite_kg: float, duree_fuite_s: float,
                        vitesse_vent_m_s: float, direction_vent_deg: float, temperature_c: float,
                        pression_hpa: float | None = None, humidite_pct: float | None = None,
                        latitude: float | None = None, longitude: float | None = None,
                        source_meteo: str = SOURCE_METEO_MANUELLE) -> dict:
    """Fonction principale : assemble récupération des propriétés chimiques + calcul de
    dispersion, et retourne un dict prêt à être persisté (cf. database.save_dispersion_result).
    """
    if duree_fuite_s <= 0:
        raise ValueError("duree_fuite_s doit être > 0")
    if vitesse_vent_m_s <= 0:
        raise ValueError("vitesse_vent_m_s doit être > 0 (le modèle de panache n'est pas défini à vent nul)")

    proprietes = get_chemical_properties(substance)
    seuil_g_m3 = proprietes["seuil_toxique_mg_m3"] / 1000.0  # mg/m3 -> g/m3

    debit_emission_g_s = (taille_fuite_kg * 1000.0) / duree_fuite_s
    classe = determiner_classe_stabilite(vitesse_vent_m_s)
    distance_impact = calculer_distance_impact(debit_emission_g_s, vitesse_vent_m_s, classe, seuil_g_m3)

    return {
        "symptom_id": symptom_id,
        "substance": proprietes["nom"],
        "masse_moleculaire": proprietes["masse_moleculaire"],
        "seuil_toxique": proprietes["seuil_toxique_mg_m3"],
        "taille_fuite_kg": taille_fuite_kg,
        "duree_fuite_s": duree_fuite_s,
        "vitesse_vent_m_s": vitesse_vent_m_s,
        "direction_vent_deg": direction_vent_deg,
        "temperature_c": temperature_c,
        "pression_hpa": pression_hpa,
        "humidite_pct": humidite_pct,
        "latitude": latitude,
        "longitude": longitude,
        "classe_stabilite": classe,
        "distance_impact_m": distance_impact,
        "source_meteo": source_meteo,
    }


if __name__ == "__main__":
    res = evaluer_dispersion(
        symptom_id="SYM-C-01",
        substance="ammoniac",
        taille_fuite_kg=50,
        duree_fuite_s=300,
        vitesse_vent_m_s=3,
        direction_vent_deg=270,
        temperature_c=25,
    )
    print(res)
