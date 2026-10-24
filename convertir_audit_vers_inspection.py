# -*- coding: utf-8 -*-
"""
Convertit « audit » -> « inspection » dans des fichiers texte (FR / EN / AR).

Usage (depuis le dossier du projet) :
    python convertir_audit_vers_inspection.py audit_app.py locales/fr.json locales/en.json locales/ar.json

- Chaque fichier est converti sur place (une copie .bak est gardée).
- audit_app.py est ensuite renommé en inspection_app.py.
- « protection auditive » / « auditifs » (audition) ne sont PAS touchés.
"""
import os, re, shutil, sys

SPECIAL = [("to_audit", "to_inspect"), ("To audit", "To inspect"), ("to audit", "to inspect")]
PAIRS = [
    ("auditeurs", "inspecteurs"), ("auditeur", "inspecteur"), ("auditrices", "inspectrices"), ("auditrice", "inspectrice"),
    ("auditer", "inspecter"),
    ("auditées", "inspectées"), ("auditée", "inspectée"), ("audités", "inspectés"), ("audité", "inspecté"),
    ("auditors", "inspectors"), ("auditor", "inspector"),
    ("audited", "inspected"), ("auditing", "inspection"),
    ("audits", "inspections"), ("audit", "inspection"),
]
D = "[\u064B-\u0652]*"

def conv(s):
    stash = []
    def keep(m):
        stash.append(m.group(0)); return f"\x00{len(stash)-1}\x00"
    s = re.sub(r"auditi[fv]\w*", keep, s, flags=re.I)
    for o, n in SPECIAL:
        s = s.replace(o, n)
    for old, new in PAIRS:
        for o, n in ((old, new), (old.capitalize(), new.capitalize()), (old.upper(), new.upper())):
            s = s.replace(o, n)
    s = re.sub(r"\b(Un|un|Cet|cet|Aucun|aucun)(?= inspection)",
               lambda m: {"un": "une", "Un": "Une", "cet": "cette", "Cet": "Cette", "aucun": "aucune", "Aucun": "Aucune"}[m.group(1)], s)
    s = re.sub(r"\bprochains(?= inspections)", "prochaines", s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], s)
    # arabe : تدقيق -> تفتيش ; المدقِّق -> المفتِّش ; المدقَّق -> المفتَّش
    s = s.replace("تدقيق", "تفتيش")
    s = re.sub(r"(ال|)مد" + D + "ق" + D + "ق" + D,
               lambda m: m.group(1) + ("مفتَّش" if "\u064E" in m.group(0) else "مفتِّش"), s)
    return s

def main(paths):
    for p in paths:
        raw = open(p, "rb").read().decode("utf-8")
        crlf = "\r\n" in raw
        new = conv(raw.replace("\r\n", "\n"))
        if crlf:
            new = new.replace("\n", "\r\n")
        shutil.copy2(p, p + ".bak")
        open(p, "wb").write(new.encode("utf-8"))
        target = p
        if os.path.basename(p) == "audit_app.py":
            target = os.path.join(os.path.dirname(p), "inspection_app.py")
            os.replace(p, target)
        print("OK ->", target)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    main(sys.argv[1:])
