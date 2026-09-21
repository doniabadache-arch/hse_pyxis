"""
matrice_manager.py
==================
Gère la sauvegarde et la lecture de la matrice de risque (Étape 0).

Version corrigée :
- __init__ (double underscores)
- __name__ == "__main__" (double underscores)
- try/except + rollback dans delete_matrix
- UNIQUE(site_name, level) dans les 3 tables
- Indexes dans _init_db()
"""

import sqlite3
from contextlib import closing


# Valeur sentinelle renvoyée quand aucun seuil ne correspond.
# C'est un CODE : l'affichage est traduit par ui.display.tr_risk_level().
RISK_LEVEL_UNDEFINED = "Non défini"


class MatriceManager:
    """Gère la sauvegarde et la lecture de la matrice en base SQLite."""

    # ============================================================
    # CORRECTION 1 : __init__ (double underscores)
    # ============================================================
    def __init__(self, db_path='matrice.db'):
        """Initialise le manager et crée les tables si nécessaire."""
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        """Retourne une connexion à la base de données."""
        return sqlite3.connect(self.db_path)

    # ============================================================
    # CORRECTION 4 + 5 : UNIQUE + Indexes
    # ============================================================
    def _init_db(self):
        """Crée les tables et indexes si ils n'existent pas encore."""
        with closing(self._connect()) as conn:

            # ----- Table Sévérité -----
            conn.execute('''
                CREATE TABLE IF NOT EXISTS severity_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    color TEXT NOT NULL,
                    action TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(site_name, level)
                )
            ''')

            # ----- Table Probabilité -----
            conn.execute('''
                CREATE TABLE IF NOT EXISTS probability_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    frequency_range TEXT NOT NULL,
                    color TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(site_name, level)
                )
            ''')

            # ----- Table Seuils -----
            conn.execute('''
                CREATE TABLE IF NOT EXISTS risk_thresholds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    max_score INTEGER NOT NULL,
                    risk_label TEXT NOT NULL,
                    color TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(site_name, max_score)
                )
            ''')

            # ----- Indexes (pour accélérer les recherches) -----
            conn.execute("CREATE INDEX IF NOT EXISTS idx_severity_site ON severity_config(site_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_probability_site ON probability_config(site_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_thresholds_site ON risk_thresholds(site_name)")

            conn.commit()

    # ============================================================
    # SÉVÉRITÉ
    # ============================================================

    def save_matrix(self, site_name, severity_data):
        """Remplace la matrice d'un site (transaction sûre)."""
        with closing(self._connect()) as conn:
            try:
                conn.execute("DELETE FROM severity_config WHERE site_name = ?", (site_name,))
                conn.executemany(
                    '''INSERT INTO severity_config (site_name, level, label, color, action)
                       VALUES (?, ?, ?, ?, ?)''',
                    [(site_name, row['Level'], row['Label'], row['Color'], row['Action'])
                     for row in severity_data]
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def get_matrix(self, site_name):
        """Retourne les lignes (level, label, color, action) d'un site."""
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                '''SELECT level, label, color, action
                   FROM severity_config WHERE site_name = ? ORDER BY level''',
                (site_name,)
            )
            return cursor.fetchall()

    # ============================================================
    # PROBABILITÉ
    # ============================================================

    def save_probability(self, site_name, probability_data):
        """Remplace les niveaux de probabilité d'un site (transaction sûre)."""
        with closing(self._connect()) as conn:
            try:
                conn.execute("DELETE FROM probability_config WHERE site_name = ?", (site_name,))
                conn.executemany(
                    '''INSERT INTO probability_config (site_name, level, label, frequency_range, color)
                       VALUES (?, ?, ?, ?, ?)''',
                    [(site_name, row['Level'], row['Label'], row['FrequencyRange'], row['Color'])
                     for row in probability_data]
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def get_probability(self, site_name):
        """Retourne les lignes (level, label, frequency_range, color) d'un site."""
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                '''SELECT level, label, frequency_range, color
                   FROM probability_config WHERE site_name = ? ORDER BY level''',
                (site_name,)
            )
            return cursor.fetchall()

    # ============================================================
    # SEUILS
    # ============================================================

    def save_thresholds(self, site_name, threshold_data):
        """Remplace les seuils de risque d'un site (transaction sûre)."""
        with closing(self._connect()) as conn:
            try:
                conn.execute("DELETE FROM risk_thresholds WHERE site_name = ?", (site_name,))
                conn.executemany(
                    '''INSERT INTO risk_thresholds (site_name, max_score, risk_label, color)
                       VALUES (?, ?, ?, ?)''',
                    [(site_name, row['MaxScore'], row['Label'], row['Color'])
                     for row in threshold_data]
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def get_thresholds(self, site_name):
        """Retourne les seuils (max_score, risk_label, color) d'un site."""
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                '''SELECT max_score, risk_label, color
                   FROM risk_thresholds WHERE site_name = ? ORDER BY max_score''',
                (site_name,)
            )
            return cursor.fetchall()

    def risk_level_for_score(self, site_name, score):
        """Traduit un score (sévérité × probabilité) en niveau de risque."""
        for max_score, risk_label, _color in self.get_thresholds(site_name):
            if score <= max_score:
                return risk_label
        return RISK_LEVEL_UNDEFINED

    # ============================================================
    # GESTION DES SITES
    # ============================================================

    def list_sites(self):
        """Retourne la liste des sites qui ont au moins une matrice."""
        with closing(self._connect()) as conn:
            cursor = conn.execute('''
                SELECT DISTINCT site_name FROM severity_config
                UNION
                SELECT DISTINCT site_name FROM probability_config
                ORDER BY site_name
            ''')
            return [row[0] for row in cursor.fetchall()]

    # ============================================================
    # CORRECTION 3 : try/except + rollback dans delete_matrix
    # ============================================================
    def delete_matrix(self, site_name):
        """Supprime toute la configuration d'un site (transaction sûre)."""
        with closing(self._connect()) as conn:
            try:
                conn.execute("DELETE FROM severity_config WHERE site_name = ?", (site_name,))
                conn.execute("DELETE FROM probability_config WHERE site_name = ?", (site_name,))
                conn.execute("DELETE FROM risk_thresholds WHERE site_name = ?", (site_name,))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise


# ============================================================
    # DOONÉES AJOUTÉES — Utilisées par audit_app.py
    # ============================================================

    def site_exists(self, site_name):
        """Retourne True si le site a déjà une configuration."""
        return site_name in self.list_sites()

    def save_full_matrix(self, site_name, severity_data,
                          probability_data, threshold_data):
        """Sauvegarde les 3 tables en une seule transaction logique."""
        self.save_matrix(site_name, severity_data)
        self.save_probability(site_name, probability_data)
        self.save_thresholds(site_name, threshold_data)
        return True

    def get_site_summary(self):
        """Retourne un résumé de tous les sites configurés."""
        sites = self.list_sites()
        return [
            {
                "site_name": s,
                "n_severity": len(self.get_matrix(s)),
                "n_probability": len(self.get_probability(s)),
                "n_thresholds": len(self.get_thresholds(s)),
            }
            for s in sites
        ]
# ============================================================
# CORRECTION 2 : __name__ == "__main__" (double underscores)
# ============================================================

if __name__ == "__main__":
    # ⚠️ On utilise une DB de test pour ne pas toucher aux vraies données
    manager = MatriceManager(db_path='matrice_test.db')

    severity_data = [
        {'Level': 1, 'Label': 'Négligeable',    'Color': '#2ECC71', 'Action': 'Aucune'},
        {'Level': 2, 'Label': 'Mineur',         'Color': '#F1C40F', 'Action': 'Surveillance'},
        {'Level': 3, 'Label': 'Modéré',         'Color': '#E67E22', 'Action': 'Planifiée'},
        {'Level': 4, 'Label': 'Majeur',         'Color': '#E74C3C', 'Action': 'Prioritaire'},
        {'Level': 5, 'Label': 'Catastrophique', 'Color': '#8B0000', 'Action': 'Immédiate'},
    ]

    probability_data = [
        {'Level': 1, 'Label': 'Improbable', 'FrequencyRange': '< 1e-5 /an',       'Color': '#2ECC71'},
        {'Level': 2, 'Label': 'Rare',       'FrequencyRange': '1e-5 à 1e-3 /an', 'Color': '#F1C40F'},
        {'Level': 3, 'Label': 'Possible',   'FrequencyRange': '1e-3 à 1e-1 /an', 'Color': '#E67E22'},
        {'Level': 4, 'Label': 'Fréquent',   'FrequencyRange': '> 1e-1 /an',       'Color': '#E74C3C'},
    ]

    # Score max = 5 (sévérité) × 4 (probabilité) = 20
    threshold_data = [
        {'MaxScore': 5,  'Label': 'Acceptable', 'Color': '#2ECC71'},
        {'MaxScore': 10, 'Label': 'Tolérable',  'Color': '#F1C40F'},
        {'MaxScore': 15, 'Label': 'Élevé',      'Color': '#E67E22'},
        {'MaxScore': 20, 'Label': 'Critique',   'Color': '#E74C3C'},
    ]

    manager.save_matrix('Site Test', severity_data)
    manager.save_probability('Site Test', probability_data)
    manager.save_thresholds('Site Test', threshold_data)

    print("✅ Sauvegarde OK (sévérité + probabilité + seuils)")

    print(f"✅ Sévérité    : {len(manager.get_matrix('Site Test'))} niveaux")
    print(f"✅ Probabilité : {len(manager.get_probability('Site Test'))} niveaux")
    print(f"✅ Seuils      : {len(manager.get_thresholds('Site Test'))} bandes")

    print(f"✅ Score 12 -> {manager.risk_level_for_score('Site Test', 12)}")

    print(f"✅ Sites: {manager.list_sites()}")