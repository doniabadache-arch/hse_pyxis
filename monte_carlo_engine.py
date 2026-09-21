"""
monte_carlo_engine.py
======================
Étape 3 du prototype (partie fréquence) : moteur Monte Carlo triangulaire, vectorisé NumPy.

Pour chaque symptôme flaggé NC (non conforme) ou PC (partiellement conforme) lors de
l'audit (étape 1), on simule sa fréquence de défaillance annuelle par une loi triangulaire
(min, mode, max) — ces trois paramètres proviennent du référentiel checklist
(checklist_loader.py), lui-même basé sur des sources génériques publiques (IOGP RADD, HCRD,
EGIG, etc., cf. description du projet).

Deux paliers d'itérations, conformément au document de cadrage :
- 10 000 itérations -> mode "aperçu rapide" (utilisé pendant l'ajustement des paramètres)
- 100 000 itérations -> mode "calcul final" (résultat transmis au rapport, étape 4)

Une graine aléatoire fixe (seed) garantit la reproductibilité des résultats.
"""

import numpy as np

SEED = 42
N_ITER_APERCU = 10_000
N_ITER_FINAL = 100_000


def simuler_frequence_triangulaire(freq_min: float, freq_mode: float, freq_max: float,
                                    n_iterations: int = N_ITER_FINAL, seed: int = SEED) -> np.ndarray:
    """Tire n_iterations échantillons de fréquence annuelle selon une loi triangulaire(min, mode, max).

    Vectorisé avec NumPy (pas de boucle Python) pour rester compatible avec un hébergement
    gratuit aux ressources limitées.
    """
    if not (freq_min <= freq_mode <= freq_max):
        raise ValueError("Il faut freq_min <= freq_mode <= freq_max")
    rng = np.random.default_rng(seed)
    return rng.triangular(left=freq_min, mode=freq_mode, right=freq_max, size=n_iterations)


def resumer_distribution(echantillons: np.ndarray) -> dict:
    """Résume une distribution simulée par sa moyenne et ses percentiles clés (P05, P50, P95)."""
    return {
        "freq_moyenne": float(np.mean(echantillons)),
        "freq_p05": float(np.percentile(echantillons, 5)),
        "freq_p50": float(np.percentile(echantillons, 50)),
        "freq_p95": float(np.percentile(echantillons, 95)),
    }


def test_convergence(freq_min: float, freq_mode: float, freq_max: float, seed: int = SEED) -> dict:
    """Compare les résultats à 10 000 et 100 000 itérations pour justifier que 100 000
    itérations suffisent à stabiliser l'estimation (cf. hypothèses du moteur Monte Carlo).
    """
    echant_10k = simuler_frequence_triangulaire(freq_min, freq_mode, freq_max, N_ITER_APERCU, seed)
    echant_100k = simuler_frequence_triangulaire(freq_min, freq_mode, freq_max, N_ITER_FINAL, seed)
    res_10k = resumer_distribution(echant_10k)
    res_100k = resumer_distribution(echant_100k)
    ecart_relatif_moyenne = abs(res_100k["freq_moyenne"] - res_10k["freq_moyenne"]) / res_100k["freq_moyenne"]
    return {
        "resultat_10k": res_10k,
        "resultat_100k": res_100k,
        "ecart_relatif_moyenne_pct": round(ecart_relatif_moyenne * 100, 3),
        "converge": ecart_relatif_moyenne < 0.05,  # seuil indicatif : écart < 5%
    }


def calculer_score_risque(freq_moyenne: float, severite: float) -> float:
    """Score de risque simple = fréquence moyenne x sévérité, utilisé uniquement pour CLASSER
    les symptômes entre eux (top 10). Le positionnement officiel sur la matrice entreprise
    (couleur/niveau affiché au responsable HSE) est fait séparément par risk_matrix.py,
    à partir de la fréquence et de la sévérité brutes — pas de ce score composite.
    """
    return freq_moyenne * severite


def evaluer_symptomes_nc_pc(symptomes: list[dict], matrix_config, n_iterations: int = N_ITER_FINAL,
                             seed: int = SEED, top_n: int = 10) -> list[dict]:
    """Évalue par Monte Carlo tous les symptômes NC/PC fournis, les positionne sur la matrice
    de risque de l'entreprise, et retourne les `top_n` symptômes les plus risqués (triés).

    Paramètres
    ----------
    symptomes : liste de dicts, chacun devant contenir au minimum :
        symptom_id, symptom (libellé), freq_min, freq_mode, freq_max, severite
        (ces champs viennent typiquement de checklist_loader.get_symptom_reference)
    matrix_config : instance de risk_matrix.RiskMatrixConfig (matrice active de l'entreprise)
    n_iterations : N_ITER_APERCU (aperçu rapide) ou N_ITER_FINAL (calcul final pour le rapport)
    top_n : nombre de symptômes les plus critiques à retourner (10 par défaut)
    """
    resultats = []
    for s in symptomes:
        echantillons = simuler_frequence_triangulaire(
            s["freq_min"], s["freq_mode"], s["freq_max"], n_iterations=n_iterations, seed=seed
        )
        stats = resumer_distribution(echantillons)
        position = matrix_config.positionner(s["severite"], stats["freq_moyenne"])
        score = calculer_score_risque(stats["freq_moyenne"], s["severite"])

        resultats.append({
            "symptom_id": s["symptom_id"],
            "symptom": s.get("symptom"),
            "n_iterations": n_iterations,
            "freq_min": s["freq_min"], "freq_mode": s["freq_mode"], "freq_max": s["freq_max"],
            **stats,
            "severite": s["severite"],
            "score_risque": score,
            "niveau_severite_matrice": position["label_severite"],
            "niveau_probabilite_matrice": position["label_probabilite"],
            "niveau_risque_matrice": position["niveau_risque"],
            "couleur_matrice": position["couleur"],
        })

    resultats.sort(key=lambda r: r["score_risque"], reverse=True)
    return resultats[:top_n]


if __name__ == "__main__":
    # Petit test autonome avec des valeurs types du référentiel (ex. SYM-P-01)
    from risk_matrix import matrice_exemple_5x5

    exemple = [
        {"symptom_id": "SYM-P-01", "symptom": "PRV hors calibration", "freq_min": 0.006,
         "freq_mode": 0.012, "freq_max": 0.024, "severite": 5},
        {"symptom_id": "SYM-P-04", "symptom": "Suintement sur virole", "freq_min": 0.000167,
         "freq_mode": 0.0005, "freq_max": 0.0015, "severite": 5},
    ]
    top = evaluer_symptomes_nc_pc(exemple, matrice_exemple_5x5(), n_iterations=N_ITER_FINAL)
    for r in top:
        print(r["symptom_id"], r["niveau_risque_matrice"], round(r["freq_moyenne"], 5))
