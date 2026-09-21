"""
audit_db.py
===========
Unified database for HSE audit prototype (Étapes 0-1-2-3).

Usage:
    from audit_db import AuditDB
    db = AuditDB()
"""

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

# Preuve requise (Evidence) : la source anglaise est déjà en colonne 8 ("evidence")
COL_EVIDENCE_EN = 8    # "evidence"
COL_EVIDENCE_FR = 23   # "evidence_fr"
COL_EVIDENCE_AR = 24   # "evidence_ar"
# Référence technique (colonne Excel "technical referance")
COL_TECHREF_EN = 25    # "technical_reference"
COL_TECHREF_FR = 26    # "technical_reference_fr"
COL_TECHREF_AR = 27    # "technical_reference_ar"

# Toutes les colonnes ajoutées après les 12 colonnes d'origine (ordre = indices 12..22).
CHECKLIST_EXTRA_COLUMNS = (
    "symptome_fr", "symptome_ar",
    "section_name_fr", "section_name_ar",
    "equipement_fr", "equipement_ar",
    "method_fr", "method_ar",
    "hazard_class", "hazard_class_fr", "hazard_class_ar",
    "evidence_fr", "evidence_ar",
    "technical_reference", "technical_reference_fr", "technical_reference_ar",
)
# Colonnes dont l'absence déclenche une resynchronisation depuis l'Excel.
# (les colonnes sources anglaises hazard_class / technical_reference ne sont pas des traductions)
CHECKLIST_TRANSLATION_COLUMNS = tuple(
    c for c in CHECKLIST_EXTRA_COLUMNS if c not in ("hazard_class", "technical_reference")
)


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


def strip_multilingual_suffix(text, fr_options=(), ar_options=()):
    """Ramène un texte de l'Excel au SEUL anglais.

    Certaines versions de la checklist écrivent, dans les colonnes de base
    (section_name, Symptom, Equipement_type, Evidence...), une cellule
    « anglais / français / arabe ». Le texte anglais d'origine peut lui-même
    contenir « / » : on ne coupe donc PAS sur « / », on retire uniquement le
    suffixe « / <français> / <arabe> » quand il correspond exactement aux
    colonnes de traduction de la même ligne (fr_options / ar_options :
    variantes acceptées). Sans correspondance, le texte est renvoyé tel quel.
    """
    value = str(text if text is not None else "").strip()
    if not value:
        return value
    ar_list = [str(a).strip() for a in ar_options if a and str(a).strip()]
    fr_list = [str(f).strip() for f in fr_options if f and str(f).strip()]
    for ar in ar_list:
        tail_ar = f" / {ar}"
        if not value.endswith(tail_ar):
            continue
        head = value[: -len(tail_ar)].rstrip()
        for fr in fr_list:
            tail_fr = f" / {fr}"
            if head.endswith(tail_fr):
                return head[: -len(tail_fr)].strip()
    return value


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


def evidence_of(item, lang="fr"):
    """Preuve requise (colonne Excel Evidence) dans la langue `lang`."""
    return pick_translation(
        lang,
        _cell(item, COL_EVIDENCE_EN),
        _cell(item, COL_EVIDENCE_FR),
        _cell(item, COL_EVIDENCE_AR),
    )


def technical_reference_of(item, lang="fr"):
    """Référence technique (colonne Excel technical referance) dans la langue `lang`."""
    return pick_translation(
        lang,
        _cell(item, COL_TECHREF_EN),
        _cell(item, COL_TECHREF_FR),
        _cell(item, COL_TECHREF_AR),
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


class AuditDB:
    """Unified DB for the HSE audit prototype."""

    def __init__(self, db_path='audit.db'):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with closing(self._connect()) as conn:
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
                    evidence_fr TEXT,
                    evidence_ar TEXT,
                    technical_reference TEXT,
                    technical_reference_fr TEXT,
                    technical_reference_ar TEXT
                )
            ''')

            # Table 2: Audit data
            conn.execute('''
                CREATE TABLE IF NOT EXISTS audit_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL,
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
                    UNIQUE(audit_id, item_id)
                )
            ''')

            # Table 3: MC results
            conn.execute('''
                CREATE TABLE IF NOT EXISTS mc_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL,
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
                    UNIQUE(audit_id, item_id)
                )
            ''')

            # Table 4: Human risk
            conn.execute('''
                CREATE TABLE IF NOT EXISTS human_risk_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL,
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
                    UNIQUE(audit_id, item_id)
                )
            ''')

            # Table 5: Cost-benefit
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cost_benefit_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL,
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
                    UNIQUE(audit_id, item_id)
                )
            ''')

            # Table 6: Dispersion
            conn.execute('''
                CREATE TABLE IF NOT EXISTS dispersion_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL,
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
                    UNIQUE(audit_id, item_id)
                )
            ''')

            # Table 7: AI Evidence Verifications (Étape 1 — ai_service.verifier_evidence)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ai_evidence_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    verdict TEXT,
                    score INTEGER,
                    commentaire TEXT,
                    suggestions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(audit_id, item_id)
                )
            ''')

            # Indexes
            for table in ['audit_data', 'mc_results', 'human_risk_results',
                          'cost_benefit_results', 'dispersion_results',
                          'ai_evidence_verifications']:
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_audit ON {table}(audit_id)")

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
                 evidence_fr, evidence_ar,
                 technical_reference, technical_reference_fr, technical_reference_ar)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', [(it['id'], it['section_name'], it['equipement'], it['symptome'],
                   it['severity'], it['frequency'], it['method'], it['source'], it.get('evidence', ''),
                   int(it['target_human']), int(it['target_env']), int(it['target_asset']),
                   it.get('symptome_fr', ''), it.get('symptome_ar', ''),
                   it.get('section_name_fr', ''), it.get('section_name_ar', ''),
                   it.get('equipement_fr', ''), it.get('equipement_ar', ''),
                   it.get('method_fr', ''), it.get('method_ar', ''),
                   it.get('hazard_class', ''), it.get('hazard_class_fr', ''), it.get('hazard_class_ar', ''),
                   it.get('evidence_fr', ''), it.get('evidence_ar', ''),
                   it.get('technical_reference', ''), it.get('technical_reference_fr', ''),
                   it.get('technical_reference_ar', ''))
                  for it in items])
            conn.commit()

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
        # Colonnes de base « polluées » : texte anglais qui contient déjà sa
        # traduction arabe (Excel trilingue « EN / FR / AR » chargé sans nettoyage).
        for base, ar in (
            ("section_name", "section_name_ar"),
            ("symptome", "symptome_ar"),
            ("equipement", "equipement_ar"),
            ("evidence", "evidence_ar"),
        ):
            condition += f" OR ({ar} IS NOT NULL AND {ar} <> '' AND instr({base}, {ar}) > 0)"
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
    def save_conformity_only(self, audit_id, site_name, item_id, conformite):
        """Sauvegarde juste la conformité (sans écraser les autres champs)."""
        with closing(self._connect()) as conn:
            # Vérifier si le record existe déjà
            cur = conn.execute(
                "SELECT id FROM audit_data WHERE audit_id = ? AND item_id = ?",
                (audit_id, item_id)
            )
            exists = cur.fetchone() is not None

            if exists:
                # UPDATE seulement la conformité (ne touche pas aux autres champs)
                conn.execute('''
                    UPDATE audit_data
                    SET conformite = ?, site_name = ?
                    WHERE audit_id = ? AND item_id = ?
                ''', (conformite, site_name, audit_id, item_id))
            else:
                # INSERT nouveau
                conn.execute('''
                    INSERT INTO audit_data
                    (audit_id, site_name, item_id, conformite)
                    VALUES (?, ?, ?, ?)
                ''', (audit_id, site_name, item_id, conformite))
            conn.commit()

    def get_conformity_by_audit(self, audit_id):
        """Retourne {item_id: conformite} pour un audit."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT item_id, conformite FROM audit_data WHERE audit_id = ?",
                (audit_id,)
            )
            return dict(cur.fetchall())

    # ========== AUDIT DATA ==========
    def save_audit_data(self, audit_id, site_name, item_id, data):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT INTO audit_data
                (audit_id, site_name, item_id, conformite,
                 evidence_text, evidence_file,
                 n_personnes, heures_expo, p_fat,
                 substance, taille_fuite_kg, duree_fuite_s,
                 vitesse_vent_ms, direction_vent_deg, temperature_c,
                 pression_hpa, humidite_pct, latitude, longitude, source_meteo,
                 cout_action, cout_perte, duree_arret_j, cout_indispo_jour,
                 currency, industry)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(audit_id, item_id) DO UPDATE SET
                    conformite        = COALESCE(excluded.conformite, audit_data.conformite),
                    evidence_text     = COALESCE(excluded.evidence_text, audit_data.evidence_text),
                    evidence_file     = COALESCE(excluded.evidence_file, audit_data.evidence_file),
                    n_personnes       = COALESCE(excluded.n_personnes, audit_data.n_personnes),
                    heures_expo       = COALESCE(excluded.heures_expo, audit_data.heures_expo),
                    p_fat             = COALESCE(excluded.p_fat, audit_data.p_fat),
                    substance         = COALESCE(excluded.substance, audit_data.substance),
                    taille_fuite_kg   = COALESCE(excluded.taille_fuite_kg, audit_data.taille_fuite_kg),
                    duree_fuite_s     = COALESCE(excluded.duree_fuite_s, audit_data.duree_fuite_s),
                    vitesse_vent_ms   = COALESCE(excluded.vitesse_vent_ms, audit_data.vitesse_vent_ms),
                    direction_vent_deg = COALESCE(excluded.direction_vent_deg, audit_data.direction_vent_deg),
                    temperature_c     = COALESCE(excluded.temperature_c, audit_data.temperature_c),
                    pression_hpa      = COALESCE(excluded.pression_hpa, audit_data.pression_hpa),
                    humidite_pct      = COALESCE(excluded.humidite_pct, audit_data.humidite_pct),
                    latitude          = COALESCE(excluded.latitude, audit_data.latitude),
                    longitude         = COALESCE(excluded.longitude, audit_data.longitude),
                    source_meteo      = COALESCE(excluded.source_meteo, audit_data.source_meteo),
                    cout_action       = COALESCE(excluded.cout_action, audit_data.cout_action),
                    cout_perte        = COALESCE(excluded.cout_perte, audit_data.cout_perte),
                    duree_arret_j     = COALESCE(excluded.duree_arret_j, audit_data.duree_arret_j),
                    cout_indispo_jour = COALESCE(excluded.cout_indispo_jour, audit_data.cout_indispo_jour),
                    currency          = COALESCE(excluded.currency, audit_data.currency),
                    industry          = COALESCE(excluded.industry, audit_data.industry)
            ''', (
                audit_id, site_name, item_id,
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

    def get_audit_data(self, audit_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM audit_data WHERE audit_id = ?", (audit_id,))
            return cur.fetchall()

    # ========== MC RESULTS ==========
    def save_mc_result(self, audit_id, item_id, r):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO mc_results
                (audit_id, item_id, n_iterations, freq_min, freq_mode, freq_max,
                 freq_moyenne, freq_p05, freq_p50, freq_p95,
                 severite, score_risque,
                 niveau_severite_matrice, niveau_probabilite_matrice,
                 niveau_risque_matrice, couleur_matrice)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (audit_id, item_id, r['n_iterations'],
                  r['freq_min'], r['freq_mode'], r['freq_max'],
                  r['freq_moyenne'], r['freq_p05'], r['freq_p50'], r['freq_p95'],
                  r['severite'], r['score_risque'],
                  r.get('niveau_severite_matrice'), r.get('niveau_probabilite_matrice'),
                  r.get('niveau_risque_matrice'), r.get('couleur_matrice')))
            conn.commit()

    def get_mc_results(self, audit_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM mc_results WHERE audit_id = ?", (audit_id,))
            return cur.fetchall()

    # ========== HUMAN RISK ==========
    def save_human_risk(self, audit_id, item_id, r):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO human_risk_results
                (audit_id, item_id, frequence_par_an, nb_personnes_exposees,
                 duree_exposition_h_an, proba_deces, proba_deces_est_defaut,
                 pll, far, lira)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (audit_id, item_id, r['frequence_par_an'],
                  r['nb_personnes_exposees'], r['duree_exposition_h_an'],
                  r['proba_deces'], int(r['proba_deces_est_defaut']),
                  r['pll'], r['far'], r['lira']))
            conn.commit()

    def get_human_risk(self, audit_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM human_risk_results WHERE audit_id = ?", (audit_id,))
            return cur.fetchall()

    # ========== COST-BENEFIT ==========
    def save_cost_benefit(self, audit_id, item_id, r):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO cost_benefit_results
                (audit_id, item_id, currency, industry, frequence_par_an,
                 cout_action_corrective, cout_perte_potentielle,
                 duree_indisponibilite_j, cout_indisponibilite_par_jour,
                 perte_annuelle_attendue, ratio_benefice_cout, recommandation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (audit_id, item_id, r['currency'], r['industry'],
                  r['frequence_par_an'], r['cout_action_corrective'],
                  r['cout_perte_potentielle'], r['duree_indisponibilite_j'],
                  r['cout_indisponibilite_par_jour'],
                  r['perte_annuelle_attendue'], r['ratio_benefice_cout'],
                  r['recommandation']))
            conn.commit()

    def get_cost_benefit(self, audit_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM cost_benefit_results WHERE audit_id = ?", (audit_id,))
            return cur.fetchall()

    # ========== DISPERSION ==========
    def save_dispersion(self, audit_id, item_id, r):
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO dispersion_results
                (audit_id, item_id, substance, taille_fuite_kg, duree_fuite_s,
                 vitesse_vent_ms, direction_vent_deg, temperature_c,
                 pression_hpa, humidite_pct, latitude, longitude,
                 classe_stabilite, distance_impact_m, source_meteo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (audit_id, item_id, r.get('substance'), r.get('taille_fuite_kg'),
                  r.get('duree_fuite_s'), r.get('vitesse_vent_ms'),
                  r.get('direction_vent_deg'), r.get('temperature_c'),
                  r.get('pression_hpa'), r.get('humidite_pct'),
                  r.get('latitude'), r.get('longitude'),
                  r.get('classe_stabilite'), r.get('distance_impact_m'),
                  r.get('source_meteo')))
            conn.commit()

    def get_dispersion(self, audit_id):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM dispersion_results WHERE audit_id = ?", (audit_id,))
            return cur.fetchall()

    # ========== AI EVIDENCE VERIFICATIONS (Étape 1) ==========
    def save_ai_verification(self, audit_id, item_id, result):
        """Sauvegarde le résultat de la vérification IA d'une évidence."""
        import json
        with closing(self._connect()) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO ai_evidence_verifications
                (audit_id, item_id, verdict, score, commentaire, suggestions)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                audit_id,
                item_id,
                result.get("verdict"),
                result.get("score"),
                result.get("commentaire"),
                json.dumps(result.get("suggestions", []), ensure_ascii=False),
            ))
            conn.commit()

    def get_ai_verification(self, audit_id, item_id):
        """Retourne le résultat IA pour un symptôme donné."""
        import json
        with closing(self._connect()) as conn:
            cur = conn.execute(
                '''SELECT verdict, score, commentaire, suggestions
                   FROM ai_evidence_verifications
                   WHERE audit_id = ? AND item_id = ?''',
                (audit_id, item_id)
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

    def get_all_ai_verifications(self, audit_id):
        """Retourne tous les résultats IA pour un audit."""
        import json
        with closing(self._connect()) as conn:
            cur = conn.execute(
                '''SELECT item_id, verdict, score, commentaire, suggestions
                   FROM ai_evidence_verifications
                   WHERE audit_id = ?''',
                (audit_id,)
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

    # ========== UTILS ==========
    def list_audits(self):
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT DISTINCT audit_id FROM audit_data ORDER BY audit_id")
            return [row[0] for row in cur.fetchall()]

    def delete_audit(self, audit_id):
        with closing(self._connect()) as conn:
            for table in ['audit_data', 'mc_results', 'human_risk_results',
                          'cost_benefit_results', 'dispersion_results',
                          'ai_evidence_verifications']:
                conn.execute(f"DELETE FROM {table} WHERE audit_id = ?", (audit_id,))
            conn.commit()


if __name__ == "__main__":
    db = AuditDB(db_path='audit_test.db')
    print("✅ AuditDB créé avec succès")