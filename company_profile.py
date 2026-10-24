"""
company_profile.py
==================
Profil économique, humain, légal et environnemental de l'entreprise.
"""

from ui.i18n import t

DEFAULT_PROFILE = {
    # Informations générales
    "nom_entreprise": "",
    "domaine_activite": "generique",

    # Dimension 1 : ÉCONOMIQUE
    "taille": "PME",
    "budget_hse": "moyen",          # qualitatif : nul | faible | moyen | eleve | illimite
    "priorite": "securite",
    "delai": "3_mois",

    # Dimension 2 : RESSOURCES HUMAINES
    "niveau_formation": "moyen",
    "turnover": "moyen",
    "formation_disponible": "occasionnelle",
    "budget_formation": "faible",   # qualitatif : nul | faible | moyen | eleve | illimite
    "metiers_specifiques": "",

    # Dimension 3 : LÉGAL & RÉGLEMENTAIRE
    "pays": "Algerie",
    "reglementation_applicable": "Code du travail algérien, décrets HSE",
    "normes_certifiees": "",
    "certifications_visees": "ISO 45001",
    "autorisations_requises": "",
    "conventions_collectives": "",
    "secteur_reglemente": False,

    # Dimension 4 : ENVIRONNEMENTAL & SANTÉ
    "zone_habitee_proche": False,
    "zone_protegee_proche": False,
    "niveau_sonore_actuel": "moyen",
    "emissions_actuelles": "",
    "gestion_dechets": "standard",
    "contraintes_env_particulieres": "",

    # Notes
    "notes": "",
}

# ─────────────────────────────────────────────────────────────
# Libellés & Traductions internes
# ─────────────────────────────────────────────────────────────
DOMAINES_ACTIVITE = {
    "petrole_gaz": "Pétrole & Gaz",
    "mines": "Mines",
    "construction": "Construction",
    "manufacturing": "Manufacturing",
    "pharmacetique": "Pharmaceutique",
    "stockage_transport": "Stockage & Transport",
    "generique": "Générique",
}

_TAILLE_LABEL = {
    "artisan": "Artisan / Très petite entreprise (< 10 personnes)",
    "PME": "PME (10-250 personnes)",
    "ETI": "ETI — Entreprise de Taille Intermédiaire (250-5000 personnes)",
    "grande": "Grande entreprise (> 5000 personnes)",
    "multinationale": "Multinationale",
}

_PRIORITE_LABEL = {
    "securite": "Sécurité des personnes (priorité absolue)",
    "conformite": "Conformité réglementaire",
    "production": "Continuité de production",
    "cout": "Réduction des coûts",
}

_DELAI_LABEL = {
    "immediat": "Immédiat (cette semaine)",
    "1_mois": "Court terme (1 mois)",
    "3_mois": "Moyen terme (3 mois)",
    "1_an": "Long terme (1 an)",
    "long_terme": "Très long terme (> 1 an)",
}

_NIVEAU_FORMATION_LABEL = {
    "faible": "Faible — la plupart des opérateurs ont une formation de base",
    "moyen": "Moyen — opérateurs formés, quelques techniciens qualifiés",
    "eleve": "Élevé — personnel qualifié et expérimenté",
    "expert": "Expert — ingénieurs et techniciens hautement spécialisés",
}

_TURNOVER_LABEL = {
    "faible": "Faible (< 5% / an) — équipe stable",
    "moyen": "Moyen (5-15% / an)",
    "eleve": "Élevé (> 15% / an) — difficulté à retenir le personnel",
}

_FORMATION_DISPO_LABEL = {
    "aucune": "Aucune — pas de budget ni de programme de formation",
    "occasionnelle": "Occasionnelle — formations ponctuelles",
    "reguliere": "Régulière — programme annuel structuré",
}

_NIVEAU_SONORE_LABEL = {
    "faible": "Faible (< 75 dB) — environnement calme",
    "moyen": "Moyen (75-85 dB) — bruit industriel normal",
    "eleve": "Élevé (> 85 dB) — bruit important, protection auditive requise",
}

_GESTION_DECHETS_LABEL = {
    "standard": "Standard — tri basique, élimination réglementaire",
    "renforcee": "Renforcée — filière déchets dangereux, traçabilité",
    "a_ameliorer": "À améliorer — gestion informelle, besoin de structuration",
}


# ============================================================
# BUDGETS QUALITATIFS
# ============================================================
BUDGET_LEVELS = ["nul", "faible", "moyen", "eleve", "illimite"]

_BUDGET_HSE_LABEL = {
    "nul":      "Nul — aucune enveloppe budgétaire dédiée à la HSE",
    "faible":   "Faible — enveloppe très limitée, seuls les achats essentiels sont possibles",
    "moyen":    "Moyen — enveloppe permettant des actions correctives ciblées",
    "eleve":    "Élevé — enveloppe permettant des investissements structurants",
    "illimite": "Illimité — pas de contrainte budgétaire significative",
}

_BUDGET_FORMATION_LABEL = {
    "nul":      "Nul — aucune formation financée, uniquement de l'apprentissage sur le poste",
    "faible":   "Faible — formations ponctuelles de courte durée uniquement",
    "moyen":    "Moyen — programme de formation annuel partiel (quelques thèmes prioritaires)",
    "eleve":    "Élevé — programme de formation complet et certifiant possible",
    "illimite": "Illimité — la formation n'est pas une contrainte",
}


def normalize_budget_level(value, default: str = "moyen") -> str:
    """Garantit un niveau qualitatif valide (migre aussi d'anciennes valeurs numériques)."""
    if isinstance(value, str) and value in BUDGET_LEVELS:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # ancien format chiffré (DZD) → niveau qualitatif
        if value <= 0:
            return "nul"
        if value < 50_000:
            return "faible"
        if value < 500_000:
            return "moyen"
        if value < 5_000_000:
            return "eleve"
        return "illimite"
    return default

_SEP = "━" * 56


def build_company_profile_text(profile: dict) -> str:
    """Transforme le profil entreprise en texte structuré pour le LLM."""
    if not profile:
        profile = DEFAULT_PROFILE

    lines = []

    # INFORMATIONS GÉNÉRALES
    nom = profile.get("nom_entreprise", "").strip()
    domaine = profile.get("domaine_activite", "generique")
    
    if nom or domaine:
        lines.append(_SEP)
        lines.append(f"🏢 {t('company.section_general')}")
        lines.append(_SEP)
        if nom:
            lines.append(f"{t('company.name_label')} : {nom}")
        lines.append(f"{t('company.domain_label')} : {t(f'company.domain_{domaine}')}")
        lines.append("")

    # DIMENSION 1 — ÉCONOMIQUE
    lines.append(_SEP)
    lines.append("📊 DIMENSION 1 — ÉCONOMIQUE")
    lines.append(_SEP)
    lines.append(f"Taille : {_TAILLE_LABEL.get(profile.get('taille'), profile.get('taille', 'N/A'))}")
    lines.append(f"Budget HSE annuel : {_BUDGET_HSE_LABEL[normalize_budget_level(profile.get('budget_hse'), 'moyen')]}")
    lines.append(f"Priorité principale : {_PRIORITE_LABEL.get(profile.get('priorite'), profile.get('priorite', 'N/A'))}")
    lines.append(f"Délai acceptable : {_DELAI_LABEL.get(profile.get('delai'), profile.get('delai', 'N/A'))}")
    lines.append("")
    lines.append("⚠️ IMPLICATIONS BUDGÉTAIRES :")
    lines.append("- Adapte le coût des actions au niveau de budget HSE déclaré.")
    lines.append("- Privilégie la hiérarchie des solutions : coût zéro > coût faible > coût moyen > coût élevé.")
    lines.append("- Si le budget est 'nul' ou 'faible', ne propose QUE des actions à coût zéro ou négligeable.")
    lines.append("- Si le budget est 'illimité', tu peux proposer des investissements lourds si justifiés.")
    lines.append("")

    # DIMENSION 2 — RESSOURCES HUMAINES
    lines.append(_SEP)
    lines.append("👥 DIMENSION 2 — RESSOURCES HUMAINES & COMPÉTENCES")
    lines.append(_SEP)
    lines.append(f"Niveau de formation : {_NIVEAU_FORMATION_LABEL.get(profile.get('niveau_formation'), profile.get('niveau_formation', 'N/A'))}")
    lines.append(f"Turnover : {_TURNOVER_LABEL.get(profile.get('turnover'), profile.get('turnover', 'N/A'))}")
    lines.append(f"Programme de formation : {_FORMATION_DISPO_LABEL.get(profile.get('formation_disponible'), profile.get('formation_disponible', 'N/A'))}")
    lines.append(f"Budget formation annuel : {_BUDGET_FORMATION_LABEL[normalize_budget_level(profile.get('budget_formation'), 'faible')]}")
    metiers = profile.get("metiers_specifiques", "").strip()
    if metiers:
        lines.append(f"Métiers disponibles : {metiers}")
    lines.append("")
    lines.append("⚠️ IMPLICATIONS :")
    lines.append("- Ne propose PAS d'actions nécessitant des compétences absentes sans formation préalable.")
    lines.append("- Si une formation est nécessaire, évalue si le budget formation le permet.")
    lines.append("- Si le turnover est élevé, privilégie les solutions ne dépendant pas d'une personne clé.")
    lines.append("")

    # DIMENSION 3 — LÉGAL & RÉGLEMENTAIRE
    lines.append(_SEP)
    lines.append("⚖️ DIMENSION 3 — CADRE LÉGAL & RÉGLEMENTAIRE")
    lines.append(_SEP)
    lines.append(f"Pays : {profile.get('pays', 'N/A')}")
    lines.append(f"Réglementation applicable : {profile.get('reglementation_applicable', 'N/A')}")
    normes = profile.get("normes_certifiees", "").strip()
    lines.append(f"Normes déjà certifiées : {normes if normes else 'Aucune'}")
    lines.append(f"Certifications visées : {profile.get('certifications_visees', 'N/A')}")
    autorisations = profile.get("autorisations_requises", "").strip()
    if autorisations:
        lines.append(f"Autorisations administratives requises : {autorisations}")
    conventions = profile.get("conventions_collectives", "").strip()
    if conventions:
        lines.append(f"Conventions collectives / accords syndicaux : {conventions}")
    if profile.get("secteur_reglemente"):
        lines.append("⚠️ SECTEUR RÉGLEMENTÉ (SEVESO, ICPE, nucléaire, etc.)")
    lines.append("")
    lines.append("⚠️ IMPLICATIONS :")
    lines.append("- Toute action DOIT être conforme à la réglementation nationale.")
    lines.append("- Toute action DOIT respecter les normes ISO visées.")
    lines.append("- Si une autorisation est requise, la mentionner avec le délai.")
    lines.append("- Ne JAMAIS proposer une action illégale.")
    lines.append("")

    # DIMENSION 4 — ENVIRONNEMENTAL & SANTÉ
    lines.append(_SEP)
    lines.append("🌍 DIMENSION 4 — ENVIRONNEMENT & SANTÉ")
    lines.append(_SEP)
    if profile.get("zone_habitee_proche"):
        lines.append("⚠️ Zone habitée proche — attention au bruit, émissions, horaires.")
    if profile.get("zone_protegee_proche"):
        lines.append("⚠️ Zone protégée proche — impact environnemental critique.")
    lines.append(f"Niveau sonore actuel : {_NIVEAU_SONORE_LABEL.get(profile.get('niveau_sonore_actuel'), profile.get('niveau_sonore_actuel', 'N/A'))}")
    emissions = profile.get("emissions_actuelles", "").strip()
    if emissions:
        lines.append(f"Émissions existantes : {emissions}")
    lines.append(f"Gestion des déchets : {_GESTION_DECHETS_LABEL.get(profile.get('gestion_dechets'), profile.get('gestion_dechets', 'N/A'))}")
    contraintes_env = profile.get("contraintes_env_particulieres", "").strip()
    if contraintes_env:
        lines.append(f"Contraintes environnementales : {contraintes_env}")
    lines.append("")
    lines.append("⚠️ IMPLICATIONS :")
    lines.append("- Toute action NE DOIT PAS créer de nouveau risque (bruit, émissions, déchets).")
    lines.append("- Si une action génère des déchets, préciser la filière d'élimination.")
    lines.append("- Ne JAMAIS résoudre un problème en en créant un autre.")
    lines.append("- Analyser l'impact sur la SANTÉ des travailleurs.")
    lines.append("")

    # NOTES
    notes = profile.get("notes", "").strip()
    if notes:
        lines.append(_SEP)
        lines.append("📝 NOTES COMPLÉMENTAIRES")
        lines.append(_SEP)
        lines.append(notes)
        lines.append("")

    return "\n".join(lines)


def is_profile_complete(profile: dict) -> bool:
    """Vérifie que le profil est suffisamment rempli."""
    if not profile:
        return False
    return bool(
        profile.get("taille")
        and profile.get("budget_hse") in BUDGET_LEVELS
        and profile.get("niveau_formation")
        and profile.get("pays")
    )