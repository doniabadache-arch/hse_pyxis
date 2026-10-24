"""
ui/pages/comparison.py — Comparaison de deux inspections (avant/après).
"""
import streamlit as st
import pandas as pd


def _get_inspections(db, site_name):
    """Récupère la liste des inspections disponibles."""
    if db is None:
        return []
    for method in ("get_all_inspections", "list_inspections",
                   "get_inspections", "fetch_inspections"):
        if hasattr(db, method):
            try:
                res = getattr(db, method)(site_name)
                if res:
                    return res
            except TypeError:
                try:
                    return getattr(db, method)()
                except Exception:
                    pass
            except Exception:
                pass
    return []


def _get_results(db, inspection_id):
    """Récupère les résultats de conformité d'une inspection."""
    if db is None:
        return {}
    for method in ("get_conformity_by_inspection",
                   "get_results_by_inspection",
                   "get_inspection_results"):
        if hasattr(db, method):
            try:
                return getattr(db, method)(inspection_id)
            except Exception:
                pass
    return {}


def _normalize_results(raw):
    """Transforme en dict {item_id: statut} quel que soit le format."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, pd.DataFrame) and not raw.empty:
        id_col = next((c for c in raw.columns
                       if "item" in c.lower() or "id" in c.lower()), raw.columns[0])
        val_col = next((c for c in raw.columns
                        if "conform" in c.lower() or "statut" in c.lower()
                        or "result" in c.lower()), raw.columns[-1])
        return dict(zip(raw[id_col], raw[val_col]))
    if isinstance(raw, list):
        return {r.get("item_id", i): r.get("statut", r.get("result", "—"))
                for i, r in enumerate(raw)}
    return {}


def render_comparison_page(db=None, site_name=None):
    st.header("📊 Comparaison de deux inspections")
    st.caption("Comparez l'évolution de la conformité entre deux inspections "
               "(ex : avant / après actions correctives).")

    inspections = _get_inspections(db, site_name)
    if not inspections:
        st.info("⚠️ Aucune inspection disponible. "
                "Le module est prêt mais la base n'est pas encore branchée.")
        # Aperçu pédagogique avec données fictives
        with st.expander("👀 Aperçu du rendu (données de démonstration)"):
            demo = pd.DataFrame({
                "Item": ["EPI-01", "EPI-02", "CHIM-03", "ELEC-04", "INC-05"],
                "Avant": ["NC", "C", "NC", "NC", "C"],
                "Après": ["C", "C", "C", "NC", "C"],
                "Évolution": ["✅ Amélioré", "➖ Stable", "✅ Amélioré",
                              "➖ Stable", "➖ Stable"],
            })
            st.dataframe(demo, use_container_width=True)
        return

    # Sélection
    c1, c2 = st.columns(2)
    with c1:
        insp_1 = st.selectbox("Inspection 1 (Avant)", inspections,
                              key="comp_1", format_func=str)
    with c2:
        insp_2 = st.selectbox("Inspection 2 (Après)", inspections,
                              key="comp_2", format_func=str)

    if not insp_1 or not insp_2:
        return
    if insp_1 == insp_2:
        st.warning("Veuillez choisir deux inspections différentes.")
        return

    # Résultats
    r1 = _normalize_results(_get_results(db, insp_1))
    r2 = _normalize_results(_get_results(db, insp_2))

    if not r1 and not r2:
        st.warning("Aucun résultat trouvé pour ces inspections.")
        return

    # Comparaison
    all_items = sorted(set(r1) | set(r2))
    rows = []
    n_improved = n_degraded = n_stable = 0
    for item in all_items:
        before = r1.get(item, "—")
        after = r2.get(item, "—")
        if before == "NC" and after == "C":
            evo = "✅ Amélioré"; n_improved += 1
        elif before == "C" and after == "NC":
            evo = "❌ Dégradé"; n_degraded += 1
        elif before == "—" or after == "—":
            evo = "➖ Non comparé"; n_stable += 1
        else:
            evo = "➖ Stable"; n_stable += 1
        rows.append({"Item": item, "Avant": before,
                     "Après": after, "Évolution": evo})

    df = pd.DataFrame(rows)

    # KPIs
    k1, k2, k3 = st.columns(3)
    k1.metric("✅ Améliorés", n_improved)
    k2.metric("❌ Dégradés", n_degraded)
    k3.metric("➖ Stables", n_stable)

    st.dataframe(df, use_container_width=True,
                 column_config={
                     "Évolution": st.column_config.TextColumn(width="medium"),
                 })

    # Export
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 Télécharger la comparaison (CSV)", csv,
                       file_name="comparaison_inspections.csv",
                       mime="text/csv")