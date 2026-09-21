"""
risk_matrix.py
==============
Bridge : lit la matrice configurée (Étape 0, matrice.db) et la rend
utilisable par monte_carlo_engine.py (Étape 3).

Usage:
    from risk_matrix import RiskMatrixConfig
    config = RiskMatrixConfig(site_name="Site A")
    position = config.positionner(severite=5, frequence=0.012)
"""

import re
from matrice_manager import MatriceManager


class RiskMatrixConfig:
    """Charge la matrice de risque d'un site depuis matrice.db."""

    def __init__(self, site_name, matrice_db='matrice.db'):
        self.site_name = site_name
        self.manager = MatriceManager(db_path=matrice_db)
        self._load()

    def _load(self):
        self.severity_levels = self.manager.get_matrix(self.site_name)
        self.probability_levels = self.manager.get_probability(self.site_name)
        self.thresholds = self.manager.get_thresholds(self.site_name)

        if not self.severity_levels or not self.probability_levels:
            raise ValueError(
                f"⚠️ Matrice non configurée pour le site '{self.site_name}'. "
                f"Lancez d'abord matrix_app.py."
            )

    def _parse_freq_range(self, range_str):
        """Parse une plage de fréquence."""
        if not range_str:
            return (0, float('inf'))
        s = range_str.replace('/an', '').replace('par an', '').strip()

        # "1e-5 à 1e-3"
        m = re.match(r'([\d.eE+-]+)\s*à\s*([\d.eE+-]+)', s)
        if m:
            return (float(m.group(1)), float(m.group(2)))

        # "< 1e-5"
        m = re.match(r'<\s*([\d.eE+-]+)', s)
        if m:
            return (0, float(m.group(1)))

        # "> 1e-1"
        m = re.match(r'>\s*([\d.eE+-]+)', s)
        if m:
            return (float(m.group(1)), 1.0)

        # Fallback
        m = re.search(r'([\d.eE+-]+)', s)
        if m:
            v = float(m.group(1))
            return (v * 0.5, v * 2)

        return (0, float('inf'))

    def _freq_to_prob_level(self, freq):
        """Retourne (level, label, color) pour une fréquence."""
        for row in self.probability_levels:
            level, label, freq_range, color = row
            fmin, fmax = self._parse_freq_range(freq_range)
            if fmin <= freq < fmax:
                return level, label, color
        # Fallback: premier niveau
        first = self.probability_levels[0]
        return first[0], first[1], first[3]

    def _severity_to_level(self, severite):
        """Retourne (level, label, color) pour une sévérité."""
        for row in self.severity_levels:
            level, label, color, action = row
            if level == severite:
                return level, label, color
        # Closest
        levels = [r[0] for r in self.severity_levels]
        closest = min(levels, key=lambda x: abs(x - severite))
        for row in self.severity_levels:
            if row[0] == closest:
                return row[0], row[1], row[2]
        return severite, f"Niveau {severite}", "#888888"

    def positionner(self, severite, frequence):
        """Positionne (severite, frequence) sur la matrice."""
        sev_level, sev_label, sev_color = self._severity_to_level(severite)
        prob_level, prob_label, prob_color = self._freq_to_prob_level(frequence)
        score = sev_level * prob_level

        niveau_risque = "Non défini"
        couleur = "#888888"
        for max_score, risk_label, risk_color in self.thresholds:
            if score <= max_score:
                niveau_risque = risk_label
                couleur = risk_color
                break

        return {
            "label_severite": sev_label,
            "label_probabilite": prob_label,
            "niveau_risque": niveau_risque,
            "couleur": couleur,
            "score": score,
            "severite_level": sev_level,
            "probabilite_level": prob_level,
        }


def matrice_exemple_5x5():
    """Matrice par défaut 5×5 — pour tests unitaires (sans DB)."""
    class _DefaultConfig:
        def positionner(self, severite, frequence):
            if frequence < 1e-5:
                prob = 1
            elif frequence < 1e-3:
                prob = 2
            elif frequence < 1e-1:
                prob = 3
            elif frequence < 1:
                prob = 4
            else:
                prob = 5

            sev = min(5, max(1, int(severite)))
            score = sev * prob
            if score <= 5:
                label = "Faible"
            elif score <= 10:
                label = "Moyen"
            elif score <= 15:
                label = "Élevé"
            else:
                label = "Très élevé"

            return {
                "label_severite": f"Niveau {sev}",
                "label_probabilite": f"Niveau {prob}",
                "niveau_risque": label,
                "couleur": "#888888",
                "score": score,
                "severite_level": sev,
                "probabilite_level": prob,
            }

    return _DefaultConfig()


if __name__ == "__main__":
    sites = MatriceManager().list_sites()
    print(f"Sites disponibles: {sites}")
    if sites:
        config = RiskMatrixConfig(site_name=sites[0])
        print(config.positionner(severite=5, frequence=0.012))
    else:
        print("⚠️ Aucun site configuré. Test avec matrice exemple:")
        config = matrice_exemple_5x5()
        print(config.positionner(severite=5, frequence=0.012))