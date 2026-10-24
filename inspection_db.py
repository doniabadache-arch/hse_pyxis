"""
inspection_db.py
===========
Unified database for HSE inspection prototype (Étapes 0-1-2-3).

Usage:
    from inspection_db import InspectionDB
    db = InspectionDB()
"""

import json
import os
import shutil
import sqlite3
from contextlib import closing


# ============================================================
# COLONNES DE checklist_items (ordre renvoyé par SELECT *)
# ============================================================
# ⚠️ Les colonnes de traduction sont AJOUTÉES À LA FIN de la table : les
#    indices 0-11 utilisés partout dans l'application (item[3], item[4],
#    item[8], item[9]...) ne bougent donc pas.
COL_SYMPTOME_EN = 3    # "symptome"    = texte source (colonne Excel "Symptom", anglais)
COL_SYMPTOME_FR = 12   # "symptome_fr" = traduction française
COL_SYMPTOME_AR = 13   # "symptome_ar" = traduction arabe

# Colonnes de base (texte source, anglais / code) déjà présentes
COL_SECTION_EN = 1     # "section_name"
COL_EQUIP_EN = 2       # "equipement"
COL_METHOD_RAW = 6     # "method" : CODE métier (Direct / Calcule / Estimated), jamais traduit en base

# Traductions ajoutées à la fin (ordre identique à CREATE TABLE et à la migration)
COL_SECTION_FR = 14    # "section_name_fr"
COL_SECTION_AR = 15    # "section_name_ar"
COL_EQUIP_FR = 16      # "equipement_fr"
COL_EQUIP_AR = 17      # "equipement_ar"
COL_METHOD_FR = 18     # "method_fr"
COL_METHOD_AR = 19     # "method_ar"
COL_HAZARD_EN = 20     # "hazard_class"    (colonne Excel "Hazzard class")
COL_HAZARD_FR = 21     # "hazard_class_fr"
COL_HAZARD_AR = 22     # "hazard_class_ar"

# Toutes les colonnes ajoutées après les 12 colonnes d'origine (ordre = indices 12..22).
CHECKLIST_EXTRA_COLUMNS = (
    "symptome_fr", "symptome_ar",
    "section_name_fr", "section_name_ar",
    "equipement_fr", "equipement_ar",
    "method_fr", "method_ar",
    "hazard_class", "hazard_class_fr", "hazard_class_ar",
)
# Colonnes dont l'absence déclenche une resynchronisation depuis l'Excel.
CHECKLIST_TRANSLATION_COLUMNS = tuple(c for c in CHECKLIST_EXTRA_COLUMNS if c != "hazard_class")

# Colonnes Domaine / Section / Actif (ajoutées APRÈS les 23 colonnes précédentes :
# indices 23..26, donc les indices 0-22 utilisés partout ne bougent pas).
COL_SEC = 23           # "sec"          : numéro de section (colonne Excel "sec")
COL_DOMAIN_CODE = 24   # "domain_code"  : ex. "OIL_GAS" ou "OIL_GAS;PHARMA" ou "ALL"
COL_SYMPTOM_CODE = 25  # "symptom_code" : code court unique (ex. P01_PRV_SET_GT_110)
COL_IS_ACTIVE = 26     # "is_active"    : 1 = ligne active, 0 = ligne masquée
CHECKLIST_DOMAIN_COLUMNS = (
    ("sec", "INTEGER"),
    ("domain_code", "TEXT"),
    ("symptom_code", "TEXT"),
    ("is_active", "INTEGER DEFAULT 1"),
)

# Valeur technique de domain_code : la section sert dans TOUS les domaines.
DOMAIN_ALL = "ALL"


def pick_translation(lang, en, fr, ar):
    """Retourne le texte dans la langue demandée ("fr" | "ar" | "en").

    Repli automatique si la traduction est vide : langue demandée -> anglais
    -> français -> arabe. Ne lève jamais d'exception (valeurs None tolérées).
    """
    by_lang = {"en": en, "fr": fr, "ar": ar}
    for candidate in (lang, "en", "fr", "ar"):
        value = by_lang.get(candidate)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _cell(item, index):
    """item[index] si la colonne existe (ancienne base sans traductions), sinon ''."""
    try:
        return item[index]
    except (IndexError, KeyError, TypeError):
        return ""


def split_domains(value):
    """'OIL_GAS;PHARMA' -> ['OIL_GAS', 'PHARMA'] (valeurs vides ignorées)."""
    return [d.strip() for d in str(value or "").split(";") if d.strip()]


def item_section_id(item):
    """Numéro de section (sec) d'une ligne checklist_items, ou None (ancienne base)."""
    value = _cell(item, COL_SEC)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def item_is_active(item):
    """True si la ligne est active. Ancienne base (colonne vide) -> active."""
    value = _cell(item, COL_IS_ACTIVE)
    if value is None or str(value).strip() == "":
        return True
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return str(value).strip().upper() == "TRUE"


def section_applies_to_domain(section_domain_code, domain_code):
    """True si une section (domain_code = 'A;B' ou 'ALL') sert le domaine donné."""
    codes = split_domains(section_domain_code)
    return DOMAIN_ALL in codes or domain_code in codes


def symptom_of(item, lang="fr"):
    """Symptôme d'une ligne checklist_items (tuple SQLite) dans la langue `lang`."""
    return pick_translation(
        lang,
        _cell(item, COL_SYMPTOME_EN),
        _cell(item, COL_SYMPTOME_FR),
        _cell(item, COL_SYMPTOME_AR),
    )


def symptom_all_text(item):
    """Les 3 versions du symptôme concaténées (pour une recherche multilingue)."""
    parts = (
        _cell(item, COL_SYMPTOME_EN),
        _cell(item, COL_SYMPTOME_FR),
        _cell(item, COL_SYMPTOME_AR),
    )
    return " ".join(str(p) for p in parts if p)


def section_of(item, lang="fr"):
    """Nom de section (colonne Excel section_name) dans la langue `lang`."""
    return pick_translation(
        lang,
        _cell(item, COL_SECTION_EN),
        _cell(item, COL_SECTION_FR),
        _cell(item, COL_SECTION_AR),
    )


def equipment_of(item, lang="fr"):
    """Type d'équipement (colonne Excel Equipement_type) dans la langue `lang`."""
    return pick_translation(
        lang,
        _cell(item, COL_EQUIP_EN),
        _cell(item, COL_EQUIP_FR),
        _cell(item, COL_EQUIP_AR),
    )


def hazard_of(item, lang="fr"):
    """Classe de danger (colonne Excel Hazzard class) dans la langue `lang`."""
    return pick_translation(
        lang,
        _cell(item, COL_HAZARD_EN),
        _cell(item, COL_HAZARD_FR),
        _cell(item, COL_HAZARD_AR),
    )


def method_translation_of(item, lang="fr"):
    """Traduction FR/AR de la méthode de fréquence lue dans l'Excel.

    Renvoie "" pour l'anglais ou si la traduction est absente : l'appelant
    (ui.display.tr_method_of) retombe alors sur les libellés des fichiers locales.
    Le code stocké (item[6]) n'est jamais modifié.
    """
    if lang == "fr":
        value = _cell(item, COL_METHOD_FR)
    elif lang == "ar":
        value = _cell(item, COL_METHOD_AR)
    else:
        return ""
    return str(value).strip() if value is not None else ""


class InspectionDB:
    """Unified DB for the HSE inspection prototype."""

    def __init__(self, db_path='inspection.db'):
        self.db_path = db_path
        self._migrate_legacy_db_file()
        self._init_db()

    def _migrate_legacy_db_file(self):
        """Ancienne base 'audit.db' -> nouvelle base 'inspection.db'.

        L'ancien fichier est COPIÉ (pas supprimé) : il reste comme sauvegarde.
        """
        if os.path.basename(self.db_path) != 'inspection.db' or os.path.exists(self.db_path):
            return
        legacy = os.path.join(os.path.dirname(self.db_path), 'audit.db')
        if os.path.exists(legacy):
            shutil.copy2(legacy, self.db_path)

    @staticmethod
    def _migrate_legacy_schema(conn):
        """Migration d'une base créée avant le renommage « audit » -> « inspection ».

        Sans effet sur une base déjà migrée ou neuve. Renomme les tables
        (audit_data, audit_meta), la colonne audit_id, les index, et met à jour
        les valeurs stockées (ID 'AUDIT-...', conformité 'À auditer').
        """
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for old, new in (('audit_data', 'inspection_data'), ('audit_meta', 'inspection_meta')):
            if old in tables and new not in tables:
                conn.execute(f"ALTER TABLE {old} RENAME TO {new}")
                tables.discard(old)
                tables.add(new)
        for t in ('inspection_data', 'mc_results', 'human_risk_results',
                  'cost_benefit_results', 'dispersion_results',
                  'ai_evidence_verifications', 'inspection_meta'):
            if t not in tables:
                continue
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
            if 'audit_id' in cols and 'inspection_id' not in cols:
                conn.execute(f"ALTER TABLE {t} RENAME COLUMN audit_id TO inspection_id")
            conn.execute(
                f"UPDATE {t} SET inspection_id = 'INSPECTION-' || substr(inspection_id, 7) "
                f"WHERE inspection_id GLOB 'AUDIT-*'")
        if 'inspection_data' in tables:
            conn.execute("UPDATE inspection_data SET conformite = 'À inspecter' WHERE conformite = 'À auditer'")
            conn.execute(
                "UPDATE inspection_data SET evidence_file = "
                "REPLACE(REPLACE(evidence_file, 'audit_evidence', 'inspection_evidence'), 'AUDIT-', 'INSPECTION-') "
                "WHERE evidence_file LIKE '%audit%'")
        # anciens index (ancien nom) : recréés sous le nouveau nom plus bas
        for t in ('audit_data', 'mc_results', 'human_risk_results',
                  'cost_benefit_results', 'dispersion_results',
                  'ai_evidence_verifications'):
            conn.execute(f"DROP INDEX IF EXISTS idx_{t}_audit")
        conn.commit()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with closing(self._connect()) as conn:
            self._migrate_legacy_schema(conn)

            # Table 1: Checklist items
            conn.execute('''
                CREATE TABLE IF NOT EXISTS checklist_items (
                    id TEXT PRIMARY KEY,
                    section_name TEXT,
                    equipement TEXT,
                    symptome TEXT,
                    severity INTEGER,
                    frequency REAL,
                    method TEXT,
                    source TEXT,
                    evidence TEXT,
                    target_human INTEGER DEFAULT 0,
                    target_env INTEGER DEFAULT 0,
                    target_asset INTEGER DEFAULT 0,
                    symptome_fr TEXT,
                    symptome_ar TEXT,
                    section_name_fr TEXT,
                    section_name_ar TEXT,
                    equipement_fr TEXT,
                    equipement_ar TEXT,
                    method_fr TEXT,
                    method_ar TEXT,
                    hazard_class TEXT,
                    hazard_class_fr TEXT,
                    hazard_class_ar TEXT,
                    sec INTEGER,
                    domain_code TEXT,
                    symptom_code TEXT,
                    is_active INTEGER DEFAULT 1
                )
            ''')

            # Table 1b: Domaines (feuille Excel "Domains") — 6 lignes
            conn.execute('''
                CREATE TABLE IF NOT EXISTS domains (
                    domain_code TEXT PRIMARY KEY,
                    name_en TEXT,
                    name_fr TEXT,
                    name_ar TEXT,
                    icon TEXT,
                    display_order INTEGER DEFAULT 0
                )
            ''')

            # Table 1c: Sections (feuille Excel "Sections") — une ligne par section
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sections (
                    section_id INTEGER PRIMARY KEY,
                    name_en TEXT,
                    name_fr TEXT,
                    name_ar TEXT,
                    domain_code TEXT,
                    display_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1
                )
            ''')

            # Table 2: Inspection data
            conn.execute('''
                CREATE TABLE IF NOT EXISTS inspection_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT NOT NULL,
                    site_name TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    conformite TEXT,
                    n_personnes INTEGER,
                    heures_expo REAL,
                    p_fat REAL,
                    substance TEXT,
                    taille_fuite_kg REAL,
                    duree_fuite_s REAL,
                    vitesse_vent_ms REAL,
                    direction_vent_deg REAL,
                    temperature_c REAL,
                    pression_hpa REAL,
                    humidite_pct REAL,
                    latitude REAL,
                    longitude REAL,
                    source_meteo TEXT,
                    cout_action REAL,
                    cout_perte REAL,
                    duree_arret_j REAL,
                    cout_indispo_jour REAL,
                    currency TEXT DEFAULT 'DZD',
                    industry TEXT DEFAULT 'generic',
                    evidence_text TEXT,
                    evidence_file TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(inspection_id, item_id)
                )
            ''')

            # Table 3: MC results
            conn.execute('''
                CREATE TABLE IF NOT EXISTS mc_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    n_iterations INTEGER,
                    freq_min REAL,
                    freq_mode REAL,
                    freq_max REAL,
                    freq_moyenne REAL,
                    freq_p05 REAL,
                    freq_p50 REAL,
                    freq_p95 REAL,
                    severite INTEGER,
                    score_risque REAL,
                    niveau_severite_matrice TEXT,
                    niveau_probabilite_matrice TEXT,
                    niveau_risque_matrice TEXT,
                    couleur_matrice TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(inspection_id, item_id)
                )
            ''')

            # Table 4: Human risk
            conn.execute('''
                CREATE TABLE IF NOT EXISTS human_risk_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    frequence_par_an REAL,
                    nb_personnes_exposees INTEGER,
                    duree_exposition_h_an REAL,
                    proba_deces REAL,
                    proba_deces_est_defaut INTEGER,
                    pll REAL,
                    far REAL,
                    lira REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(inspection_id, item_id)
                )
            ''')

            # Table 5: Cost-benefit
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cost_benefit_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    currency TEXT,
                    industry TEXT,
                    frequence_par_an REAL,
                    cout_action_corrective REAL,
                    cout_perte_potentielle REAL,
                    duree_indisponibilite_j REAL,
                    cout_indisponibilite_par_jour REAL,
                    perte_annuelle_attendue REAL,
                    ratio_benefice_cout REAL,
                    recommandation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(inspection_id, item_id)
                )
            ''')

            # Table 6: Dispersion
            conn.execute('''
                CREATE TABLE IF NOT EXISTS dispersion_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    substance TEXT,
                    taille_fuite_kg REAL,
                    duree_fuite_s REAL,
                    vitesse_vent_ms REAL,
                    direction_vent_deg REAL,
                    temperature_c REAL,
                    pression_hpa REAL,
                    humidite_pct REAL,
                    latitude REAL,
                    longitude REAL,
                    classe_stabilite TEXT,
                    distance_impact_m REAL,
                    source_meteo TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(inspection_id, item_id)
                )
            ''')

            # Table 7: AI Evidence Verifications (Étape 1 — ai_service.verifier_evidence)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ai_evidence_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    verdict TEXT,
                    score INTEGER,
                    commentaire TEXT,
                    suggestions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(inspection_id, item_id)
                )
            ''')

            # Table 8: Métadonnées d'inspection (date d'inspection saisie par l'inspecteur)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS inspection_meta (
                    inspection_id TEXT PRIMARY KEY,
                    inspection_date TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table 9: Paramètres utilisateur (email, préférences, journal des rappels)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table 10: Inspections programmées (calendrier)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_inspections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT,
                    site_name TEXT,
                    scheduled_date TEXT NOT NULL,
                    scheduled_time TEXT,
                    inspector TEXT,
                    inspector_email TEXT,
                    sections TEXT,
                    notes TEXT,
                    status TEXT DEFAULT 'planned',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table 11: Actions correctives
            conn.execute('''
                CREATE TABLE IF NOT EXISTS corrective_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT NOT NULL,
                    item_id TEXT,
                    action TEXT NOT NULL,
                    responsible TEXT,
                    responsible_email TEXT,
                    deadline TEXT,
                    priority TEXT DEFAULT 'medium',
                    status TEXT DEFAULT 'open',
                    completed_at TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sched_date ON scheduled_inspections(scheduled_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_inspection ON corrective_actions(inspection_id)")

            # Indexes
            for table in ['inspection_data', 'mc_results', 'human_risk_results',
                          'cost_benefit_results', 'dispersion_results',
                          'ai_evidence_verifications']:
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_inspection ON {table}(inspection_id)")

            # Migration : bases créées avant l'ajout des traductions (symptôme,
            # section, équipement, méthode, classe de danger).
            # CREATE TABLE IF NOT EXISTS ne modifie pas une table existante,
            # donc on ajoute les colonnes manquantes (à la fin -> indices 0-11 inchangés).
            # L'ordre de CHECKLIST_EXTRA_COLUMNS = celui du CREATE TABLE ci-dessus.
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(checklist_items)")
            }
            for col in CHECKLIST_EXTRA_COLUMNS:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE checklist_items ADD COLUMN {col} TEXT")
            # Idem pour sec / domain_code / symptom_code / is_active (indices 23..26)
            for col, decl in CHECKLIST_DOMAIN_COLUMNS:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE checklist_items ADD COLUMN {col} {decl}")

            conn.commit()

    # ========== CHECKLIST ==========
    def save_checklist_items(self, items):
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM checklist_items")
            conn.executemany('''
                INSERT INTO checklist_items
                (id, section_name, equipement, symptome, severity, frequency,
                 method, source, evidence, target_human, target_env, target_asset,
                 symptome_fr, symptome_ar,
                 section_name_fr, section_name_ar,
                 equipement_fr, equipement_ar,
                 method_fr, method_ar,
                 hazard_class, hazard_class_fr, hazard_class_ar,
                 sec, domain_code, symptom_code, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?)
            ''', [(it['id'], it['section_name'], it['equipement'], it['symptome'],
                   it['severity'], it['frequency'], it['method'], it['source'], it.get('evidence', ''),
                   int(it['target_human']), int(it['target_env']), int(it['target_asset']),
                   it.get('symptome_fr', ''), it.get('symptome_ar', ''),
                   it.get('section_name_fr', ''), it.get('section_name_ar', ''),
                   it.get('equipement_fr', ''), it.get('equipement_ar', ''),
                   it.get('method_fr', ''), it.get('method_ar', ''),
                   it.get('hazard_class', ''), it.get('hazard_class_fr', ''), it.get('hazard_class_ar', ''),
                   it.get('sec'), it.get('domain_code', ''), it.get('symptom_code', ''),
                   1 if it.get('is_active', True) else 0)
                  for it in items])
            conn.commit()

    # ========== DOMAINES & SECTIONS (feuilles Excel "Domains" / "Sections") ==========
    def save_domains(self, domains):
        """Remplace la table domains. domains = liste de dict
        (domain_code, name_en, name_fr, name_ar, icon, display_order)."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM domains")
            conn.executemany(
                "INSERT INTO domains (domain_code, name_en, name_fr, name_ar, icon, display_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(d['domain_code'], d.get('name_en', ''), d.get('name_fr', ''),
                  d.get('name_ar', ''), d.get('icon', ''), int(d.get('display_order') or 0))
                 for d in domains])
            conn.commit()

    def get_domains(self):
        """Domaines triés par display_order -> liste de dict."""
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM domains ORDER BY display_order, domain_code")
            return [dict(r) for r in cur.fetchall()]

    def save_sections(self, sections):
        """Remplace la table sections. sections = liste de dict
        (section_id, name_en, name_fr, name_ar, domain_code, display_order, is_active)."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM sections")
            conn.executemany(
                "INSERT INTO sections (section_id, name_en, name_fr, name_ar, domain_code, "
                "display_order, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(int(s['section_id']), s.get('name_en', ''), s.get('name_fr', ''),
                  s.get('name_ar', ''), s.get('domain_code', ''),
                  int(s.get('display_order') or 0), 1 if s.get('is_active', True) else 0)
                 for s in sections])
            conn.commit()

    def get_sections(self, only_active=True):
        """Sections triées (display_order, section_id) -> liste de dict."""
        query = "SELECT * FROM sections"
        if only_active:
            query += " WHERE is_active = 1"
        query += " ORDER BY display_order, section_id"
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(query).fetchall()]

    def get_sections_for_domain(self, domain_code):
        """Sections à afficher pour un domaine : celles dont domain_code contient ce
        domaine + les sections 'ALL' (communes), 'ALL' en premier."""
        rows = [s for s in self.get_sections()
                if section_applies_to_domain(s['domain_code'], domain_code)]
        rows.sort(key=lambda s: (
            0 if DOMAIN_ALL in split_domains(s['domain_code']) else 1,
            s['display_order'], s['section_id']))
        return rows

    def checklist_needs_catalog_refresh(self):
        """True si la checklist est en base mais sans sec/domain_code (ancienne base),
        ou si les tables domains / sections sont vides : il faut relire l'Excel."""
        with closing(self._connect()) as conn:
            n_items = conn.execute("SELECT COUNT(*) FROM checklist_items").fetchone()[0]
            if n_items == 0:
                return False
            n_missing = conn.execute(
                "SELECT COUNT(*) FROM checklist_items "
                "WHERE sec IS NULL OR domain_code IS NULL OR TRIM(domain_code) = ''"
            ).fetchone()[0]
            n_dom = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
            n_sec = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
            return n_missing > 0 or n_dom == 0 or n_sec == 0

    def get_checklist_items(self):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM checklist_items ORDER BY id")
            return cur.fetchall()

    def checklist_needs_translation_refresh(self):
        """True si la checklist est déjà en base mais qu'au moins un item n'a pas
        toutes ses traductions FR/AR (symptôme, section, équipement, méthode,
        classe de danger) : base créée avec l'ancienne version de l'Excel."""
        condition = " OR ".join(
            f"{col} IS NULL OR TRIM({col}) = ''"
            for col in CHECKLIST_TRANSLATION_COLUMNS
        )
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"SELECT COUNT(*) FROM checklist_items WHERE {condition}"
            )
            return cur.fetchone()[0] > 0

    def get_item(self, item_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM checklist_items WHERE id = ?", (item_id,))
            return cur.fetchone()

    # ========== CONFORMITY ONLY (Étape 1 — sans calcul de risque) ==========
    def save_conformity_only(self, inspection_id, site_name, item_id, conformite):
        """Sauvegarde juste la conformité (sans écraser les autres champs)."""
        with closing(self._connect()) as conn:
            # Vérifier si le record existe déjà
            cur = conn.execute(
                "SELECT id FROM inspection_data WHERE inspection_id = ? AND item_id = ?",
                (inspection_id, item_id)
            )
            exists = cur.fetchone() is not None

            if exists:
                # UPDATE seulement la conformité (ne touche pas aux autres champs)
                conn.execute('''
                    UPDATE inspection_data
                    SET conformite = ?, site_name = ?
                    WHERE inspection_id = ? AND item_id = ?
                ''', (conformite, site_name, inspection_id, item_id))
            else:
                # INSERT nouveau
                conn.execute('''
                    INSERT INTO inspection_data
                    (inspection_id, site_name, item_id, conformite)
                    VALUES (?, ?, ?, ?)
                ''', (inspection_id, site_name, item_id, conformite))
            conn.commit()

    def get_conformity_by_inspection(self, inspection_id):
        """Retourne {item_id: conformite} pour une inspection."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT item_id, conformite FROM inspection_data WHERE inspection_id = ?",
                (inspection_id,)
            )
            return dict(cur.fetchall())

    # ========== INSPECTION DATA ==========
    def save_inspection_data(self, inspection_id, site_name, item_id, data):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT INTO inspection_data
                (inspection_id, site_name, item_id, conformite,
                 evidence_text, evidence_file,
                 n_personnes, heures_expo, p_fat,
                 substance, taille_fuite_kg, duree_fuite_s,
                 vitesse_vent_ms, direction_vent_deg, temperature_c,
                 pression_hpa, humidite_pct, latitude, longitude, source_meteo,
                 cout_action, cout_perte, duree_arret_j, cout_indispo_jour,
                 currency, industry)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(inspection_id, item_id) DO UPDATE SET
                    conformite        = COALESCE(excluded.conformite, inspection_data.conformite),
                    evidence_text     = COALESCE(excluded.evidence_text, inspection_data.evidence_text),
                    evidence_file     = COALESCE(excluded.evidence_file, inspection_data.evidence_file),
                    n_personnes       = COALESCE(excluded.n_personnes, inspection_data.n_personnes),
                    heures_expo       = COALESCE(excluded.heures_expo, inspection_data.heures_expo),
                    p_fat             = COALESCE(excluded.p_fat, inspection_data.p_fat),
                    substance         = COALESCE(excluded.substance, inspection_data.substance),
                    taille_fuite_kg   = COALESCE(excluded.taille_fuite_kg, inspection_data.taille_fuite_kg),
                    duree_fuite_s     = COALESCE(excluded.duree_fuite_s, inspection_data.duree_fuite_s),
                    vitesse_vent_ms   = COALESCE(excluded.vitesse_vent_ms, inspection_data.vitesse_vent_ms),
                    direction_vent_deg = COALESCE(excluded.direction_vent_deg, inspection_data.direction_vent_deg),
                    temperature_c     = COALESCE(excluded.temperature_c, inspection_data.temperature_c),
                    pression_hpa      = COALESCE(excluded.pression_hpa, inspection_data.pression_hpa),
                    humidite_pct      = COALESCE(excluded.humidite_pct, inspection_data.humidite_pct),
                    latitude          = COALESCE(excluded.latitude, inspection_data.latitude),
                    longitude         = COALESCE(excluded.longitude, inspection_data.longitude),
                    source_meteo      = COALESCE(excluded.source_meteo, inspection_data.source_meteo),
                    cout_action       = COALESCE(excluded.cout_action, inspection_data.cout_action),
                    cout_perte        = COALESCE(excluded.cout_perte, inspection_data.cout_perte),
                    duree_arret_j     = COALESCE(excluded.duree_arret_j, inspection_data.duree_arret_j),
                    cout_indispo_jour = COALESCE(excluded.cout_indispo_jour, inspection_data.cout_indispo_jour),
                    currency          = COALESCE(excluded.currency, inspection_data.currency),
                    industry          = COALESCE(excluded.industry, inspection_data.industry)
            ''', (
                inspection_id, site_name, item_id,
                data.get('conformite'),
                data.get('evidence_text'),
                data.get('evidence_file'),
                data.get('n_personnes'),
                data.get('heures_expo'),
                data.get('p_fat'),
                data.get('substance'),
                data.get('taille_fuite_kg'),
                data.get('duree_fuite_s'),
                data.get('vitesse_vent_ms'),
                data.get('direction_vent_deg'),
                data.get('temperature_c'),
                data.get('pression_hpa'),
                data.get('humidite_pct'),
                data.get('latitude'),
                data.get('longitude'),
                data.get('source_meteo'),
                data.get('cout_action'),
                data.get('cout_perte'),
                data.get('duree_arret_j'),
                data.get('cout_indispo_jour'),
                data.get('currency', 'DZD'),
                data.get('industry', 'generic'),
            ))
            conn.commit()

    def get_inspection_data(self, inspection_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM inspection_data WHERE inspection_id = ?", (inspection_id,))
            return cur.fetchall()

    # ========== MC RESULTS ==========
    def save_mc_result(self, inspection_id, item_id, r):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO mc_results
                (inspection_id, item_id, n_iterations, freq_min, freq_mode, freq_max,
                 freq_moyenne, freq_p05, freq_p50, freq_p95,
                 severite, score_risque,
                 niveau_severite_matrice, niveau_probabilite_matrice,
                 niveau_risque_matrice, couleur_matrice)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (inspection_id, item_id, r['n_iterations'],
                  r['freq_min'], r['freq_mode'], r['freq_max'],
                  r['freq_moyenne'], r['freq_p05'], r['freq_p50'], r['freq_p95'],
                  r['severite'], r['score_risque'],
                  r.get('niveau_severite_matrice'), r.get('niveau_probabilite_matrice'),
                  r.get('niveau_risque_matrice'), r.get('couleur_matrice')))
            conn.commit()

    def get_mc_results(self, inspection_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM mc_results WHERE inspection_id = ?", (inspection_id,))
            return cur.fetchall()

    # ========== HUMAN RISK ==========
    def save_human_risk(self, inspection_id, item_id, r):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO human_risk_results
                (inspection_id, item_id, frequence_par_an, nb_personnes_exposees,
                 duree_exposition_h_an, proba_deces, proba_deces_est_defaut,
                 pll, far, lira)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (inspection_id, item_id, r['frequence_par_an'],
                  r['nb_personnes_exposees'], r['duree_exposition_h_an'],
                  r['proba_deces'], int(r['proba_deces_est_defaut']),
                  r['pll'], r['far'], r['lira']))
            conn.commit()

    def get_human_risk(self, inspection_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM human_risk_results WHERE inspection_id = ?", (inspection_id,))
            return cur.fetchall()

    # ========== COST-BENEFIT ==========
    def save_cost_benefit(self, inspection_id, item_id, r):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO cost_benefit_results
                (inspection_id, item_id, currency, industry, frequence_par_an,
                 cout_action_corrective, cout_perte_potentielle,
                 duree_indisponibilite_j, cout_indisponibilite_par_jour,
                 perte_annuelle_attendue, ratio_benefice_cout, recommandation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (inspection_id, item_id, r['currency'], r['industry'],
                  r['frequence_par_an'], r['cout_action_corrective'],
                  r['cout_perte_potentielle'], r['duree_indisponibilite_j'],
                  r['cout_indisponibilite_par_jour'],
                  r['perte_annuelle_attendue'], r['ratio_benefice_cout'],
                  r['recommandation']))
            conn.commit()

    def get_cost_benefit(self, inspection_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM cost_benefit_results WHERE inspection_id = ?", (inspection_id,))
            return cur.fetchall()

    # ========== DISPERSION ==========
    def save_dispersion(self, inspection_id, item_id, r):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO dispersion_results
                (inspection_id, item_id, substance, taille_fuite_kg, duree_fuite_s,
                 vitesse_vent_ms, direction_vent_deg, temperature_c,
                 pression_hpa, humidite_pct, latitude, longitude,
                 classe_stabilite, distance_impact_m, source_meteo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (inspection_id, item_id, r.get('substance'), r.get('taille_fuite_kg'),
                  r.get('duree_fuite_s'), r.get('vitesse_vent_ms'),
                  r.get('direction_vent_deg'), r.get('temperature_c'),
                  r.get('pression_hpa'), r.get('humidite_pct'),
                  r.get('latitude'), r.get('longitude'),
                  r.get('classe_stabilite'), r.get('distance_impact_m'),
                  r.get('source_meteo')))
            conn.commit()

    def get_dispersion(self, inspection_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM dispersion_results WHERE inspection_id = ?", (inspection_id,))
            return cur.fetchall()

    # ========== AI EVIDENCE VERIFICATIONS (Étape 1) ==========
    def save_ai_verification(self, inspection_id, item_id, result):
        """Sauvegarde le résultat de la vérification IA d'une évidence."""
        import json
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO ai_evidence_verifications
                (inspection_id, item_id, verdict, score, commentaire, suggestions)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                inspection_id,
                item_id,
                result.get("verdict"),
                result.get("score"),
                result.get("commentaire"),
                json.dumps(result.get("suggestions", []), ensure_ascii=False),
            ))
            conn.commit()

    def get_ai_verification(self, inspection_id, item_id):
        """Retourne le résultat IA pour un symptôme donné."""
        import json
        with closing(self._connect()) as conn:
            cur = conn.execute(
                '''SELECT verdict, score, commentaire, suggestions
                   FROM ai_evidence_verifications
                   WHERE inspection_id = ? AND item_id = ?''',
                (inspection_id, item_id)
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "verdict": row[0],
                "score": row[1],
                "commentaire": row[2],
                "suggestions": json.loads(row[3]) if row[3] else [],
            }

    def get_all_ai_verifications(self, inspection_id):
        """Retourne tous les résultats IA pour une inspection."""
        import json
        with closing(self._connect()) as conn:
            cur = conn.execute(
                '''SELECT item_id, verdict, score, commentaire, suggestions
                   FROM ai_evidence_verifications
                   WHERE inspection_id = ?''',
                (inspection_id,)
            )
            results = {}
            for row in cur.fetchall():
                results[row[0]] = {
                    "verdict": row[1],
                    "score": row[2],
                    "commentaire": row[3],
                    "suggestions": json.loads(row[4]) if row[4] else [],
                }
            return results

    # ========== SETTINGS ==========
    def save_setting(self, key, value):
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                                  updated_at = CURRENT_TIMESTAMP""",
                (key, None if value is None else str(value)))
            conn.commit()

    def get_setting(self, key, default=None):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row and row[0] is not None else default

    def get_all_settings(self):
        with closing(self._connect()) as conn:
            return {k: v for k, v in conn.execute("SELECT key, value FROM settings")}

    # ========== INSPECTIONS PROGRAMMÉES ==========
    _SCHED_COLS = ("id", "inspection_id", "site_name", "scheduled_date", "scheduled_time",
                   "inspector", "inspector_email", "sections", "notes", "status")

    def _sched_row(self, row):
        d = dict(zip(self._SCHED_COLS, row))
        try:
            d["sections"] = json.loads(d["sections"]) if d["sections"] else []
        except (TypeError, ValueError):
            d["sections"] = []
        return d

    def add_scheduled_inspection(self, inspection_id, site_name, scheduled_date,
                                 scheduled_time=None, inspector=None, inspector_email=None,
                                 sections=None, notes=None, status="planned"):
        """Ajoute une inspection programmée. scheduled_date : AAAA-MM-JJ. Retourne l'id."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """INSERT INTO scheduled_inspections
                   (inspection_id, site_name, scheduled_date, scheduled_time, inspector,
                    inspector_email, sections, notes, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (inspection_id, site_name, scheduled_date, scheduled_time, inspector,
                 inspector_email, json.dumps(sections or [], ensure_ascii=False), notes, status))
            conn.commit()
            return cur.lastrowid

    def get_scheduled_inspections(self, date_from=None, date_to=None, status=None):
        """Liste (dicts) triée par date/heure ; filtres optionnels (dates ISO incluses)."""
        q = "SELECT " + ", ".join(self._SCHED_COLS) + " FROM scheduled_inspections WHERE 1=1"
        args = []
        if date_from:
            q += " AND scheduled_date >= ?"; args.append(date_from)
        if date_to:
            q += " AND scheduled_date <= ?"; args.append(date_to)
        if status:
            q += " AND status = ?"; args.append(status)
        q += " ORDER BY scheduled_date, COALESCE(scheduled_time, '')"
        with closing(self._connect()) as conn:
            return [self._sched_row(r) for r in conn.execute(q, args).fetchall()]

    def get_scheduled_inspection(self, sched_id):
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT " + ", ".join(self._SCHED_COLS) + " FROM scheduled_inspections WHERE id = ?",
                (sched_id,)).fetchone()
            return self._sched_row(row) if row else None

    def update_scheduled_inspection(self, sched_id, **fields):
        """Met à jour des champs (sections acceptée en liste)."""
        allowed = [c for c in self._SCHED_COLS if c != "id"]
        sets, args = [], []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "sections":
                v = json.dumps(v or [], ensure_ascii=False)
            sets.append(f"{k} = ?"); args.append(v)
        if not sets:
            return
        args.append(sched_id)
        with closing(self._connect()) as conn:
            conn.execute(f"UPDATE scheduled_inspections SET {', '.join(sets)} WHERE id = ?", args)
            conn.commit()

    def update_scheduled_inspection_status(self, sched_id, status):
        self.update_scheduled_inspection(sched_id, status=status)

    def delete_scheduled_inspection(self, sched_id):
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM scheduled_inspections WHERE id = ?", (sched_id,))
            conn.commit()

    # ========== ACTIONS CORRECTIVES ==========
    _ACTION_COLS = ("id", "inspection_id", "item_id", "action", "responsible",
                    "responsible_email", "deadline", "priority", "status", "completed_at")

    def add_corrective_action(self, inspection_id, item_id, action, responsible=None,
                              responsible_email=None, deadline=None, priority="medium"):
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """INSERT INTO corrective_actions
                   (inspection_id, item_id, action, responsible, responsible_email,
                    deadline, priority, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'open')""",
                (inspection_id, item_id, action, responsible, responsible_email,
                 deadline, priority))
            conn.commit()
            return cur.lastrowid

    def get_corrective_actions(self, inspection_id=None, status=None):
        """Liste (dicts). inspection_id=None → toutes les inspections."""
        q = "SELECT " + ", ".join(self._ACTION_COLS) + " FROM corrective_actions WHERE 1=1"
        args = []
        if inspection_id:
            q += " AND inspection_id = ?"; args.append(inspection_id)
        if status:
            q += " AND status = ?"; args.append(status)
        q += " ORDER BY COALESCE(deadline, '9999-12-31'), id"
        with closing(self._connect()) as conn:
            return [dict(zip(self._ACTION_COLS, r)) for r in conn.execute(q, args).fetchall()]

    def complete_corrective_action(self, action_id, completed_at=None):
        from datetime import date as _date
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE corrective_actions SET status = 'done', completed_at = ? WHERE id = ?",
                (completed_at or _date.today().isoformat(), action_id))
            conn.commit()

    def delete_corrective_action(self, action_id):
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM corrective_actions WHERE id = ?", (action_id,))
            conn.commit()

    # ========== UTILS ==========
    def list_inspections(self):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT DISTINCT inspection_id FROM inspection_data ORDER BY inspection_id")
            return [row[0] for row in cur.fetchall()]

    def get_inspection_date(self, inspection_id):
        """Date d'inspection (texte ISO AAAA-MM-JJ) ou None."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT inspection_date FROM inspection_meta WHERE inspection_id = ?", (inspection_id,)
            ).fetchone()
            return row[0] if row else None

    def save_inspection_date(self, inspection_id, iso_date):
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO inspection_meta (inspection_id, inspection_date) VALUES (?, ?)
                   ON CONFLICT(inspection_id) DO UPDATE SET inspection_date = excluded.inspection_date,
                                                       updated_at = CURRENT_TIMESTAMP""",
                (inspection_id, iso_date))
            conn.commit()

    def delete_inspection(self, inspection_id):
        with closing(self._connect()) as conn:
            for table in ['inspection_data', 'mc_results', 'human_risk_results',
                          'cost_benefit_results', 'dispersion_results',
                          'ai_evidence_verifications']:
                conn.execute(f"DELETE FROM {table} WHERE inspection_id = ?", (inspection_id,))
            conn.execute("DELETE FROM inspection_meta WHERE inspection_id = ?", (inspection_id,))
            conn.execute("DELETE FROM corrective_actions WHERE inspection_id = ?", (inspection_id,))
            conn.commit()


if __name__ == "__main__":
    db = InspectionDB(db_path='inspection_test.db')
    print("✅ InspectionDB créé avec succès")