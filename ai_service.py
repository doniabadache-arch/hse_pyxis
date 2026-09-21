"""
ai_service.py — HSE PYXIS
==========================
Service d'intelligence artificielle pour l'audit HSE (moteur Gemini).

Fournit 3 fonctions principales, utilisées respectivement par :
    - Étape 1 (audit_app.render_step_1_audit)   -> verifier_evidence()
    - Étape 4 (ui/pages/report.py)              -> generer_rapport()
    - Étape 5 (audit_app.render_step_5_pdca)    -> generer_plan_pdca()

Configuration
-------------
La clé API est cherchée, dans l'ordre :
    1. Variable d'environnement GEMINI_API_KEY (chargée depuis app1/.env
       via python-dotenv, comme le reste de l'application — cf. ai/config.py
       pour le même principe côté Groq) ;
    2. st.secrets["GEMINI_API_KEY"] (compatibilité Streamlit Cloud).

Principe i18n
-------------
Ce module ne renvoie AUCUN texte déjà traduit à l'UI : il retourne des
codes/booléens bruts (voir is_configured / get_status), et des verdicts
codés ("conforme" | "partiel" | "non_conforme" | "absent"). C'est à l'appelant
(audit_app.py / ui/pages/report.py) de traduire l'affichage via ui.i18n.t().
Seul le contenu généré par le LLM (commentaire IA, rapport, plan PDCA) est
directement rédigé dans la langue demandée par le paramètre `langue`, car ce
texte n'existe dans aucun fichier de locale : c'est un contenu, pas un libellé
d'interface.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Modèle configurable via variable d'environnement (Google renomme parfois
# ses modèles) ; identique dans l'esprit à GROQ_MODEL dans ai/config.py.
GEMINI_MODEL_OVERRIDE = os.getenv("GEMINI_MODEL", "")

_MODEL_CACHE = None


def is_configured() -> bool:
    """Vérifie que la clé API Gemini est disponible (env ou st.secrets)."""
    if GEMINI_API_KEY:
        return True
    try:
        import streamlit as st
        return bool(st.secrets.get("GEMINI_API_KEY"))
    except Exception:
        return False


def get_status() -> dict:
    """État BRUT (non traduit) de la configuration IA — même forme que
    ai.config.get_status(), pour que l'UI (ui/pages/report.py) puisse
    afficher un panneau de statut identique quel que soit le moteur."""
    configured = is_configured()
    key = _resolve_api_key() if configured else ""
    return {
        "configured": configured,
        "model": GEMINI_MODEL_OVERRIDE or _MODEL_CACHE or "gemini (auto)",
        "env_path": str(_ENV_PATH),
        "env_exists": _ENV_PATH.exists(),
        "key_preview": (key[:6] + "..." + key[-4:]) if configured and len(key) > 10 else None,
    }


def _resolve_api_key() -> str:
    if GEMINI_API_KEY:
        return GEMINI_API_KEY
    try:
        import streamlit as st
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        raise RuntimeError(
            "❌ Clé GEMINI_API_KEY introuvable. "
            "Ajoutez-la dans app1/.env (GEMINI_API_KEY=...) "
            "ou dans .streamlit/secrets.toml"
        )


def _get_available_model():
    """Détecte automatiquement un modèle Gemini disponible.
    Google change régulièrement les noms des modèles."""
    global _MODEL_CACHE
    if GEMINI_MODEL_OVERRIDE:
        return GEMINI_MODEL_OVERRIDE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    import google.generativeai as genai

    api_key = _resolve_api_key()
    genai.configure(api_key=api_key)

    candidates = [
        "gemini-3.6-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    try:
        available = [
            m.name.replace("models/", "")
            for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
    except Exception as e:
        raise RuntimeError(f"❌ Impossible de lister les modèles Gemini : {e}")

    for c in candidates:
        if c in available:
            _MODEL_CACHE = c
            return c

    if available:
        _MODEL_CACHE = available[0]
        return available[0]

    raise RuntimeError("❌ Aucun modèle Gemini disponible pour generateContent")


def _get_model():
    import google.generativeai as genai
    model_name = _get_available_model()
    return genai.GenerativeModel(model_name)


# ============================================================
# 1. VÉRIFICATION D'EVIDENCE — utilisée à l'Étape 1
# ============================================================
def verifier_evidence(
    symptome_id: str,
    symptome_description: str,
    evidence_requis: str,
    evidence_text: str,
    image_path: str | None = None,
    conformite: str = "NC",
) -> dict:
    """
    Analyse une preuve (texte + image optionnelle) et vérifie si elle est
    conforme à l'évidence requise.

    Retourne
    --------
    dict : {
        "verdict": "conforme" | "partiel" | "non_conforme" | "absent",
        "score": 0-100,
        "commentaire": "...",
        "suggestions": [...],
        "erreur": None ou "..."
    }
    """
    if not evidence_text and not image_path:
        return {
            "verdict": "absent",
            "score": 0,
            "commentaire": "Aucune évidence fournie pour ce symptôme.",
            "suggestions": [
                f"Ajouter : {evidence_requis}",
                "Renseigner une note descriptive",
                "Joindre un fichier justificatif (photo, PDF, ...)",
            ],
            "erreur": None,
        }

    prompt = f"""Tu es un auditeur HSE expert, certifié ISO 45001 et ISO 14001.

CONTEXTE DE L'AUDIT :
- Symptôme ID : {symptome_id}
- Description : {symptome_description}
- Conformité déclarée : {conformite}

ÉVIDENCE REQUISE :
{evidence_requis}

ÉVIDENCE FOURNIE (note textuelle) :
{evidence_text if evidence_text else "(aucune note textuelle)"}

MISSION :
Analyse si l'évidence fournie est suffisante et pertinente pour justifier la conformité déclarée.
Sois rigoureux mais pragmatique. Ne demande pas plus que ce qui est raisonnablement attendu.

RÉPONDS UNIQUEMENT EN JSON VALIDE (aucun autre texte avant/après) :
{{
  "verdict": "conforme" | "partiel" | "non_conforme",
  "score": <entier 0-100>,
  "commentaire": "<2-3 phrases d'analyse>",
  "suggestions": [
    "<suggestion concrète 1>",
    "<suggestion concrète 2>",
    "<suggestion concrète 3>"
  ]
}}

Critères :
- "conforme" (score 80-100) : l'évidence répond clairement à ce qui est demandé
- "partiel" (score 40-79) : l'évidence répond partiellement, il manque des éléments
- "non_conforme" (score 0-39) : l'évidence ne répond pas au besoin

Retourne UNIQUEMENT le JSON."""

    contents = [prompt]

    if image_path:
        try:
            img_file = Path(image_path)
            if img_file.exists():
                with open(img_file, "rb") as f:
                    img_bytes = f.read()
                ext = img_file.suffix.lower()
                mime = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }.get(ext, "image/jpeg")
                contents.append({"mime_type": mime, "data": img_bytes})
        except Exception:
            pass

    try:
        model = _get_model()
        response = model.generate_content(contents)
        text = response.text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        return {
            "verdict": result.get("verdict", "non_conforme"),
            "score": int(result.get("score", 0)),
            "commentaire": result.get("commentaire", ""),
            "suggestions": result.get("suggestions", []),
            "erreur": None,
        }

    except json.JSONDecodeError as e:
        return {
            "verdict": "non_conforme",
            "score": 0,
            "commentaire": "Erreur de parsing de la réponse IA.",
            "suggestions": [],
            "erreur": f"JSON invalide : {e}",
        }
    except Exception as e:
        return {
            "verdict": "non_conforme",
            "score": 0,
            "commentaire": "Erreur lors de l'appel à l'IA.",
            "suggestions": [],
            "erreur": str(e),
        }


# ============================================================
# 2. RAPPORT D'AUDIT COMPLET — utilisé à l'Étape 4
# ============================================================
def generer_rapport(
    audit_id: str,
    site_name: str,
    nc_pc_items: list[dict],
    stats_summary: dict,
    langue: str = "fr",
    custom_instructions: str = "",
) -> dict:
    """
    Génère un rapport d'audit complet en Markdown.

    `custom_instructions` (optionnel) : instructions additionnelles libres
    saisies par l'utilisateur dans l'UI (Étape 4), ajoutées telles quelles
    à la fin du prompt.

    Retourne
    --------
    dict : {"markdown": "...", "erreur": None ou "..."}
    """
    lang_label = {"fr": "français", "en": "anglais", "ar": "arabe"}.get(langue, "français")

    items_str = "\n".join([
        f"- {it['item_id']} ({it['conformite']}) — "
        f"Sévérité {it['severity']}, Fréquence {it.get('freq_moyenne', 0):.2e}/an, "
        f"Classe {it.get('risk_class', 'N/A')} — {it['symptome'][:100]}"
        for it in nc_pc_items[:30]
    ])

    prompt = f"""Tu es un auditeur HSE senior, expert en ISO 45001, ISO 14001 et analyse de risques industriels.

CONTEXTE DE L'AUDIT :
- ID audit : {audit_id}
- Site : {site_name}
- Nombre total de symptômes audités : {stats_summary.get('total_items', 0)}
- NC (Non Conformes) : {stats_summary.get('n_nc', 0)}
- PC (Partiellement Conformes) : {stats_summary.get('n_pc', 0)}
- C (Conformes) : {stats_summary.get('n_c', 0)}

SYMPTÔMES NC/PC À ANALYSER :
{items_str}

MISSION :
Rédige un rapport d'audit HSE complet et professionnel en **{lang_label}**, au format Markdown.

STRUCTURE ATTENDUE :

# Rapport d'Audit HSE — {site_name}

**Date** : [date du jour]
**Audit ID** : {audit_id}
**Auditeur** : [à compléter]

## 1. Synthèse Exécutive
[3-4 phrases résumant la situation globale, les points critiques, et le niveau de risque général]

## 2. Analyse Quantitative
- Taux de conformité : XX%
- Répartition des risques
- Comparaison avec les standards HSE

## 3. Top 5 Risques Critiques
[Pour chaque risque : ID, description, pourquoi c'est critique, impact potentiel]

## 4. Analyse par Domaine
[Grouper les NC/PC par section et analyser les tendances]

## 5. Recommandations Stratégiques
[4-6 recommandations concrètes et priorisées]

## 6. Conclusion
[Paragraphe de conclusion + prochaines étapes]

RÈGLES :
- Sois factuel, professionnel, et orienté action
- Utilise un ton neutre et objectif
- Mets en évidence les risques critiques
- Ne mentionne PAS les symptômes conformes (C) dans le détail
- Le rapport doit être prêt à être présenté à la direction

Retourne UNIQUEMENT le Markdown du rapport, sans texte avant ou après."""

    if custom_instructions:
        prompt += (
            "\n\n===============================\n"
            "INSTRUCTIONS ADDITIONNELLES DE L'UTILISATEUR\n"
            "===============================\n"
            f"{custom_instructions}\n"
        )

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        return {"markdown": response.text.strip(), "erreur": None}
    except Exception as e:
        return {"markdown": "", "erreur": str(e)}


# ============================================================
# 3. PLAN PDCA — utilisé à l'Étape 5
# ============================================================
def generer_plan_pdca(
    item: dict,
    freq_moyenne: float = 0.0,
    risk_class: str = "N/A",
    langue: str = "fr",
) -> dict:
    """
    Génère un plan PDCA complet pour un symptôme NC/PC.

    Retourne
    --------
    dict : {"markdown": "...", "erreur": None ou "..."}
    """
    lang_label = {"fr": "français", "en": "anglais", "ar": "arabe"}.get(langue, "français")

    prompt = f"""Tu es un expert en management HSE et en amélioration continue (PDCA / Roue de Deming).

CONTEXTE :
- Symptôme ID : {item['item_id']}
- Section : {item.get('section', 'N/A')}
- Équipement : {item.get('equipement', 'N/A')}
- Description : {item['symptome']}
- Sévérité : {item['severity']}/5
- Conformité : {item['conformite']}
- Fréquence moyenne (Monte Carlo) : {freq_moyenne:.2e}/an
- Classe de risque : {risk_class}

MISSION :
Rédige un plan PDCA complet et opérationnel en **{lang_label}** au format Markdown.

STRUCTURE EXACTE À SUIVRE :

# Plan PDCA — {item['item_id']}

## 📋 Résumé du problème
[2-3 phrases : ce qui ne va pas, l'impact potentiel]

## 🎯 PLAN (Planifier)

### Objectif SMART
[Objectif spécifique, mesurable, atteignable, réaliste, temporel]

### Analyse des causes racines (5 Pourquoi)
1. Pourquoi... ?
2. Pourquoi... ?
3. Pourquoi... ?
4. Pourquoi... ?
5. Pourquoi... ? (cause racine)

### Actions à mener
| # | Action | Responsable | Délai | Ressources |
|---|--------|-------------|-------|------------|
| 1 | ...    | ...         | ...   | ...        |
| 2 | ...    | ...         | ...   | ...        |
| 3 | ...    | ...         | ...   | ...        |

### Indicateurs de succès (KPI)
- KPI 1 : ...
- KPI 2 : ...

## 🚀 DO (Déployer)

### Planning de mise en œuvre
- **Semaine 1-2** : [actions]
- **Semaine 3-4** : [actions]
- **Semaine 5-6** : [actions]

### Responsables
- Chef de projet : ...
- Équipe : ...

### Formation / Sensibilisation
[Si nécessaire]

## ✅ CHECK (Vérifier)

### Points de contrôle
- **J+30** : [ce qu'on vérifie]
- **J+60** : [ce qu'on vérifie]
- **J+90** : [ce qu'on vérifie]

### Audit interne
[Comment on vérifie l'efficacité]

### Mesure des KPI
[Comment on mesure]

## 🔄 ACT (Agir)

### Si succès
[Standardiser, documenter, partager]

### Si échec
[Analyser les écarts, ajuster, refaire un cycle]

### Leçons apprises
[À capitaliser pour d'autres symptômes]

### Communication
[Qui informer, comment]

RÈGLES :
- Sois TRÈS concret et opérationnel
- Les actions doivent être réalisables dans les 90 jours
- Adapte le niveau de détail à la sévérité ({item['severity']}/5)
- Utilise un langage professionnel HSE
- Les délais doivent être réalistes

Retourne UNIQUEMENT le Markdown du plan PDCA."""

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        return {"markdown": response.text.strip(), "erreur": None}
    except Exception as e:
        return {"markdown": "", "erreur": str(e)}


# ============================================================
# TEST RAPIDE (optionnel)
# ============================================================
if __name__ == "__main__":
    print("Test du service IA (Gemini)...")
    print("Configuré :", is_configured())
    if is_configured():
        print(f"Modèle détecté : {_get_available_model()}")
    print("✅ Service IA opérationnel")
