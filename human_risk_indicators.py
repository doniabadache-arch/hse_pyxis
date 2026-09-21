"""
s)human_risk_indicators.py
=========================
Étape 3 du prototype - cible humaine : calcul du PLL, FAR et LIRA.

Entrées saisies MANUELLEMENT par l'inspecteur pour chaque symptôme concernant la cible
humaine (target human = True dans le référentiel checklist) :
- nb_personnes_exposees   : nombre de personnes se trouvant à proximité du danger
- duree_exposition_h_an   : durée d'exposition par personne (heures / an)
- proba_deces             : probabilité de décès sachant l'événement (0-1). Une valeur par
                              défaut est proposée (PROBA_DECES_DEFAUT) mais reste modifiable.

La fréquence annuelle (frequence_par_an) provient du moteur Monte Carlo (monte_carlo_engine.py),
typiquement la moyenne de la distribution simulée (freq_moyenne).

Formules (process safety, usage courant en analyse quantitative des risques) :

    PLL  (Potential Loss of Life, pertes de vie attendues / an)
         = f x Pf x N

    FAR  (Fatal Accident Rate, décès pour 10^8 heures d'exposition)
         = (PLL / heures_personnes_totales) x 10^8
           où heures_personnes_totales = N x duree_exposition_h_an

    LIRA (Location Individual Risk per Annum, risque individuel de localisation / an)
         = f x Pf x (duree_exposition_h_an / 8760)
           (8760 = nombre d'heures dans une année ; ne dépend PAS de N,
           c'est un risque INDIVIDUEL au poste/à la localisation)

Avec f = fréquence annuelle de l'événement, Pf = probabilité de décès sachant l'événement.
"""

HEURES_PAR_AN = 8760

# Valeur par défaut de la probabilité de décès sachant l'événement redouté.
# Volontairement conservatrice (à ajuster par l'inspecteur selon le type d'événement :
# incendie, explosion, exposition toxique, etc. -> une explosion majeure peut justifier
# une valeur bien plus haute, un incident mineur une valeur bien plus basse).
PROBA_DECES_DEFAUT = 0.1


def calculer_pll(frequence_par_an: float, proba_deces: float, nb_personnes_exposees: int) -> float:
    """PLL = f x Pf x N (pertes de vie potentielles attendues par an)."""
    return frequence_par_an * proba_deces * nb_personnes_exposees


def calculer_far(pll: float, nb_personnes_exposees: int, duree_exposition_h_an: float) -> float:
    """FAR = (PLL / heures-personnes totales) x 10^8."""
    heures_personnes_totales = nb_personnes_exposees * duree_exposition_h_an
    if heures_personnes_totales <= 0:
        return 0.0
    return (pll / heures_personnes_totales) * 1e8


def calculer_lira(frequence_par_an: float, proba_deces: float, duree_exposition_h_an: float) -> float:
    """LIRA = f x Pf x (duree_exposition_h_an / 8760) -- risque individuel, indépendant de N."""
    fraction_temps = duree_exposition_h_an / HEURES_PAR_AN
    return frequence_par_an * proba_deces * fraction_temps


def evaluer_risque_humain(symptom_id: str, frequence_par_an: float, nb_personnes_exposees: int,
                           duree_exposition_h_an: float, proba_deces: float | None = None) -> dict:
    """Calcule PLL, FAR et LIRA pour un symptôme donné et retourne un dict prêt à être
    persisté (cf. database.save_human_risk_result).
    """
    proba_deces_est_defaut = proba_deces is None
    if proba_deces is None:
        proba_deces = PROBA_DECES_DEFAUT
    if not (0 <= proba_deces <= 1):
        raise ValueError("proba_deces doit être comprise entre 0 et 1")

    pll = calculer_pll(frequence_par_an, proba_deces, nb_personnes_exposees)
    far = calculer_far(pll, nb_personnes_exposees, duree_exposition_h_an)
    lira = calculer_lira(frequence_par_an, proba_deces, duree_exposition_h_an)

    return {
        "symptom_id": symptom_id,
        "frequence_par_an": frequence_par_an,
        "nb_personnes_exposees": nb_personnes_exposees,
        "duree_exposition_h_an": duree_exposition_h_an,
        "proba_deces": proba_deces,
        "proba_deces_est_defaut": proba_deces_est_defaut,
        "pll": pll,
        "far": far,
        "lira": lira,
    }


# Repères indicatifs pour l'interprétation du LIRA, largement utilisés en process safety
# (ex. Pays-Bas, UK HSE) -- fournis à titre informatif pour l'UI, pas figés dans le calcul.
SEUILS_LIRA_INDICATIFS = {
    "inacceptable": 1e-3,     # > 1e-3 /an : généralement jugé inacceptable
    "tolerable_alarp": 1e-6,  # entre 1e-6 et 1e-3 /an : zone ALARP (à réduire autant que possible)
    "negligeable": 1e-6,      # < 1e-6 /an : généralement jugé négligeable
}

# Codes STABLES (indépendants de la langue) renvoyés par niveau_lira().
# L'affichage est traduit par ui.display.tr_lira().
NIVEAUX_LIRA = ("LIRA_UNACCEPTABLE", "LIRA_ALARP", "LIRA_NEGLIGIBLE")


def niveau_lira(lira: float) -> str:
    """Classe une valeur LIRA et retourne un CODE (pas un texte traduit)."""
    if lira > SEUILS_LIRA_INDICATIFS["inacceptable"]:
        return "LIRA_UNACCEPTABLE"
    if lira > SEUILS_LIRA_INDICATIFS["negligeable"]:
        return "LIRA_ALARP"
    return "LIRA_NEGLIGIBLE"


if __name__ == "__main__":
    res = evaluer_risque_humain(
        symptom_id="SYM-P-01",
        frequence_par_an=0.012,
        nb_personnes_exposees=3,
        duree_exposition_h_an=500,
    )
    print(res)
    
    