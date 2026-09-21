"""
cost_benefit.py
================
Étape 3 du prototype — cible matériel : analyse coût-bénéfice.

Pour chaque symptôme concernant la cible matériel (target asset = True),
l'inspecteur saisit MANUELLEMENT :
- cout_action_corrective        : coût de l'action corrective proposée
- cout_perte_potentielle        : coût du dommage matériel si la défaillance survient
- duree_indisponibilite_j       : durée d'indisponibilité en cas de défaillance (jours)
- cout_indisponibilite_par_jour : coût d'indisponibilité par jour (production perdue, etc.)

La fréquence annuelle (frequence_par_an) provient du moteur Monte Carlo (étape 3).

Principe :
    perte_annuelle_attendue = frequence_par_an × (cout_perte_potentielle
                                                  + duree_indisponibilite_j × cout_indisponibilite_par_jour)
    ratio_benefice_cout     = perte_annuelle_attendue / cout_action_corrective

Un ratio > 1 signifie que la perte annuelle évitée dépasse le coût de l'action corrective :
l'action est financièrement justifiée. Ce ratio reste une aide à la décision, pas une
décision automatique — il est transmis au rapport (étape 4) avec les autres résultats.

⚠️ IMPORTANT (Section 4 — Limites assumées) :
Le LLM n'effectue aucun calcul de risque et ne valide seul aucune non-conformité.
Ce module est une aide à la décision soumise à validation humaine.
"""

from typing import Dict, Optional


# ============================================================
# 1. DEVISES / CURRENCIES
# ============================================================
# Taux de change approximatifs (à mettre à jour périodiquement)
# Base : 1 EUR = X

CURRENCIES = {
    "EUR": {"symbol": "€",   "label": "Euro",              "rate_to_eur": 1.0},
    "USD": {"symbol": "$",   "label": "Dollar US",         "rate_to_eur": 0.92},
    "DZD": {"symbol": "DA",  "label": "Dinar algérien",    "rate_to_eur": 0.0069},
}

DEFAULT_CURRENCY = "DZD"  # ✅ Dinar algérien par défaut (contexte algérien)


def get_currency_label(code: str) -> str:
    """Retourne le label d'une devise."""
    return CURRENCIES.get(code, CURRENCIES["DZD"])["label"]


def get_currency_symbol(code: str) -> str:
    """Retourne le symbole d'une devise."""
    return CURRENCIES.get(code, CURRENCIES["DZD"])["symbol"]


def convert_to_eur(amount: float, currency: str) -> float:
    """Convertit un montant vers EUR (pour comparaison interne)."""
    rate = CURRENCIES.get(currency, CURRENCIES["DZD"])["rate_to_eur"]
    return amount * rate


def convert_from_eur(amount_eur: float, currency: str) -> float:
    """Convertit un montant EUR vers une devise cible."""
    rate = CURRENCIES.get(currency, CURRENCIES["DZD"])["rate_to_eur"]
    if rate <= 0:
        return amount_eur
    return amount_eur / rate


def format_amount(amount: float, currency: str) -> str:
    """Formate un montant avec symbole et séparateurs de milliers."""
    symbol = get_currency_symbol(currency)
    return f"{amount:,.0f} {symbol}"


# ============================================================
# 2. VALEURS PAR DÉFAUT (selon l'industrie)
# ============================================================
# Coût d'indisponibilité par jour (en EUR, converti automatiquement)
# Sources : benchmarks industriels (Oil & Gas, Pharma, Manufacturing)

DEFAULT_INDISPONIBILITE_PAR_JOUR_EUR = {
    "oil_gas":       50000.0,   # 50 000 €/jour
    "petrochemical": 40000.0,   # 40 000 €/jour
    "pharma":       100000.0,   # 100 000 €/jour
    "manufacturing": 10000.0,   # 10 000 €/jour
    "mining":        30000.0,   # 30 000 €/jour
    "generic":       15000.0,   # 15 000 €/jour (par défaut)
}


def get_default_indisponibilite(industry: str = "generic") -> float:
    """Retourne le coût d'indisponibilité par jour par défaut (EUR)."""
    return DEFAULT_INDISPONIBILITE_PAR_JOUR_EUR.get(
        industry, DEFAULT_INDISPONIBILITE_PAR_JOUR_EUR["generic"]
    )


# ============================================================
# 3. VALIDATION
# ============================================================
def validate_inputs(frequence_par_an: float,
                    cout_action_corrective: float,
                    cout_perte_potentielle: float,
                    duree_indisponibilite_j: float,
                    cout_indisponibilite_par_jour: float) -> None:
    """Valide les entrées — lève ValueError si invalide."""
    if frequence_par_an < 0:
        raise ValueError(f"fréquence doit être >= 0, reçu : {frequence_par_an}")
    if cout_action_corrective < 0:
        raise ValueError(f"coût action doit être >= 0, reçu : {cout_action_corrective}")
    if cout_perte_potentielle < 0:
        raise ValueError(f"coût perte doit être >= 0, reçu : {cout_perte_potentielle}")
    if duree_indisponibilite_j < 0:
        raise ValueError(f"durée indispo doit être >= 0, reçu : {duree_indisponibilite_j}")
    if cout_indisponibilite_par_jour < 0:
        raise ValueError(f"coût indispo/jour doit être >= 0, reçu : {cout_indisponibilite_par_jour}")


# ============================================================
# 4. CALCULS
# ============================================================
def calculer_perte_annuelle_attendue(frequence_par_an: float,
                                      cout_perte_potentielle: float,
                                      duree_indisponibilite_j: float,
                                      cout_indisponibilite_par_jour: float) -> float:
    """
    Calcule la perte annuelle attendue (en unité monétaire).

    perte_annuelle = f × (cout_perte + duree_indispo × cout_indispo/jour)
    """
    cout_total_par_evenement = (
        cout_perte_potentielle
        + duree_indisponibilite_j * cout_indisponibilite_par_jour
    )
    return frequence_par_an * cout_total_par_evenement


def calculer_ratio_benefice_cout(perte_annuelle_attendue: float,
                                  cout_action_corrective: float) -> float:
    """
    Calcule le ratio bénéfice/coût.

    ratio > 1 : perte évitée > coût action → action justifiée
    ratio < 1 : coût action > perte évitée → arbitrage nécessaire
    """
    if cout_action_corrective <= 0:
        return float("inf")
    return perte_annuelle_attendue / cout_action_corrective


# ============================================================
# 5. RECOMMANDATION TEXTUELLE
# ============================================================
# Codes STABLES stockés en base et traduits à l'affichage par
# ui.display.tr_reco(). Ne jamais stocker de phrase traduite ici :
# un audit enregistré en français doit rester lisible en arabe.
RECOMMANDATION_CODES = (
    "CB_STRONGLY_RECOMMENDED",
    "CB_RECOMMENDED",
    "CB_TO_REVIEW",
    "CB_NOT_PRIORITY",
)


def recommandation_code(ratio: float) -> str:
    """Retourne un CODE de recommandation basé sur le ratio bénéfice/coût.

    ⚠️ Aide à la décision — pas une décision automatique.
    """
    if ratio >= 2:
        return "CB_STRONGLY_RECOMMENDED"
    if ratio >= 1:
        return "CB_RECOMMENDED"
    if ratio >= 0.5:
        return "CB_TO_REVIEW"
    return "CB_NOT_PRIORITY"


# Textes français — conservés pour les scripts hors Streamlit (démo, exports
# techniques). L'interface utilise ui.display.tr_reco(code).
RECOMMANDATION_TEXTES_FR = {
    "CB_STRONGLY_RECOMMENDED": ("✅ Action corrective FORTEMENT recommandée "
                                "(perte évitée ≥ 2× le coût de l'action)"),
    "CB_RECOMMENDED": ("✅ Action corrective recommandée "
                       "(perte évitée ≥ coût de l'action)"),
    "CB_TO_REVIEW": ("⚠️ Action à EXAMINER "
                     "(perte évitée < coût, mais proche) — arbitrage HSE requis"),
    "CB_NOT_PRIORITY": ("❌ Action NON PRIORITAIRE sur le seul critère coût-bénéfice "
                        "— à réévaluer selon d'autres critères (sécurité, image, réglementaire)"),
}


def recommandation_textuelle(ratio: float) -> str:
    """Version texte française (rétro-compatibilité / usage hors interface)."""
    return RECOMMANDATION_TEXTES_FR[recommandation_code(ratio)]


# ============================================================
# 6. FONCTION PRINCIPALE
# ============================================================
def evaluer_cout_benefice(
    symptom_id: str,
    frequence_par_an: float,
    cout_action_corrective: float,
    cout_perte_potentielle: float,
    duree_indisponibilite_j: float,
    cout_indisponibilite_par_jour: float,
    currency: str = DEFAULT_CURRENCY,
    industry: str = "generic",
) -> Dict:
    """
    Calcule la perte annuelle attendue et le ratio bénéfice/coût.

    Parameters
    ----------
    symptom_id : str
        ID du symptôme (ex: SYM-P-04)
    frequence_par_an : float
        Fréquence annuelle (issue du Monte Carlo)
    cout_action_corrective : float
        Coût de l'action corrective
    cout_perte_potentielle : float
        Coût du dommage matériel si défaillance
    duree_indisponibilite_j : float
        Durée d'indisponibilité (jours)
    cout_indisponibilite_par_jour : float
        Coût d'indisponibilité par jour
    currency : str
        Devise (EUR, USD, DZD) — défaut : DZD
    industry : str
        Secteur (oil_gas, pharma...) — pour valeurs par défaut

    Returns
    -------
    dict prêt à être persisté (cf. database.save_cost_benefit_result)
    """
    # Validation
    validate_inputs(
        frequence_par_an, cout_action_corrective,
        cout_perte_potentielle, duree_indisponibilite_j,
        cout_indisponibilite_par_jour
    )

    # Calcul perte annuelle
    perte_annuelle = calculer_perte_annuelle_attendue(
        frequence_par_an,
        cout_perte_potentielle,
        duree_indisponibilite_j,
        cout_indisponibilite_par_jour,
    )

    # Ratio
    ratio = calculer_ratio_benefice_cout(perte_annuelle, cout_action_corrective)

    # Conversion en EUR (pour comparaison interne)
    perte_annuelle_eur = convert_to_eur(perte_annuelle, currency)
    cout_action_eur = convert_to_eur(cout_action_corrective, currency)

    return {
        "symptom_id": symptom_id,
        "currency": currency,
        "currency_label": get_currency_label(currency),
        "industry": industry,

        # Inputs (dans la devise choisie)
        "frequence_par_an": frequence_par_an,
        "cout_action_corrective": cout_action_corrective,
        "cout_perte_potentielle": cout_perte_potentielle,
        "duree_indisponibilite_j": duree_indisponibilite_j,
        "cout_indisponibilite_par_jour": cout_indisponibilite_par_jour,

        # Outputs
        "perte_annuelle_attendue": perte_annuelle,
        "perte_annuelle_attendue_formatee": format_amount(perte_annuelle, currency),
        "cout_action_formatee": format_amount(cout_action_corrective, currency),
        "ratio_benefice_cout": ratio,
        # Code stable (traduit à l'affichage par ui.display.tr_reco)
        "recommandation": recommandation_code(ratio),
        "recommandation_texte_fr": recommandation_textuelle(ratio),

        # Équivalents EUR (pour comparaison interne)
        "perte_annuelle_eur": perte_annuelle_eur,
        "cout_action_eur": cout_action_eur,
    }


# ============================================================
# 7. TEST / DEMO
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("💰 ANALYSE COÛT-BÉNÉFICE — Démonstration")
    print("=" * 70)

    # --- Exemple 1 : SYM-P-04 (Vessel) ---
    print("\n📌 Exemple 1 : SYM-P-04 (Vessel)")
    res1 = evaluer_cout_benefice(
        symptom_id="SYM-P-04",
        frequence_par_an=0.0005,
        cout_action_corrective=15000,
        cout_perte_potentielle=200000,
        duree_indisponibilite_j=10,
        cout_indisponibilite_par_jour=5000,
        currency="EUR",
        industry="oil_gas",
    )
    for k, v in res1.items():
        print(f"   {k:35s} = {v}")

    # --- Exemple 2 : même cas en DZD ---
    print("\n📌 Exemple 2 : même cas en DZD")
    res2 = evaluer_cout_benefice(
        symptom_id="SYM-P-04",
        frequence_par_an=0.0005,
        cout_action_corrective=15000 * 145,   # 15000 EUR ≈ 2 175 000 DZD
        cout_perte_potentielle=200000 * 145,  # 200 000 EUR ≈ 29 000 000 DZD
        duree_indisponibilite_j=10,
        cout_indisponibilite_par_jour=5000 * 145,
        currency="DZD",
        industry="oil_gas",
    )
    for k, v in res2.items():
        print(f"   {k:35s} = {v}")

    # --- Exemple 3 : avec valeurs par défaut ---
    print("\n📌 Exemple 3 : valeurs par défaut (coût indispo/jour)")
    default_indispo = get_default_indisponibilite("oil_gas")
    print(f"   Coût indispo/jour par défaut (oil_gas) = {default_indispo} EUR")

    res3 = evaluer_cout_benefice(
        symptom_id="SYM-R-07",
        frequence_par_an=0.0475,
        cout_action_corrective=50000,
        cout_perte_potentielle=500000,
        duree_indisponibilite_j=15,
        cout_indisponibilite_par_jour=default_indispo,
        currency="DZD",
        industry="oil_gas",
    )
    print(f"\n   Ratio bénéfice/coût = {res3['ratio_benefice_cout']:.2f}")
    print(f"   Recommandation     = {res3['recommandation']}")

    print("\n" + "=" * 70)
