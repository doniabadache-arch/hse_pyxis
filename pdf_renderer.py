"""
pdf_renderer.py — Génère un PDF signé (QR code) pour les rapports d'inspection.
Dépendances : reportlab, qrcode[pil]
"""
from io import BytesIO
from datetime import datetime
import uuid

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, Image, PageBreak)
    from reportlab.lib.enums import TA_CENTER
    import qrcode
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def _make_qr_image(data: str, size_mm=30):
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=size_mm * mm, height=size_mm * mm)


def render_pdf_report(inspection_id: str,
                      site_name: str = "",
                      inspector_name: str = "",
                      results_df=None,
                      summary: dict | None = None,
                      extra_notes: str = "",
                      language: str = "fr") -> bytes | None:
    """
    Génère un PDF et retourne les bytes. Retourne None si les libs manquent.
    """
    if not _AVAILABLE:
        return None

    reference = f"PYXIS-{inspection_id}-{uuid.uuid4().hex[:8].upper()}"
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Center", parent=styles["Normal"],
                              alignment=TA_CENTER))
    story = []

    # En-tête
    story.append(Paragraph("🛡️ HSE PYXIS", styles["Title"]))
    story.append(Paragraph("Rapport d'inspection HSE", styles["Heading2"]))
    story.append(Spacer(1, 6 * mm))

    # Bloc méta
    meta = [
        ["Référence", reference],
        ["ID Inspection", str(inspection_id)],
        ["Site", site_name or "—"],
        ["Inspecteur", inspector_name or "—"],
        ["Date", datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Langue", language.upper()],
    ]
    t = Table(meta, colWidths=[50 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EDF2F7")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    # Résumé
    if summary:
        story.append(Paragraph("Résumé", styles["Heading3"]))
        rows = [["Indicateur", "Valeur"]] + \
               [[k, str(v)] for k, v in summary.items()]
        st_tbl = Table(rows, colWidths=[80 * mm, 80 * mm])
        st_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(st_tbl)
        story.append(Spacer(1, 6 * mm))

    # Tableau des résultats
    if results_df is not None and not results_df.empty:
        story.append(Paragraph("Résultats détaillés", styles["Heading3"]))
        cols = list(results_df.columns)[:6]
        data = [cols] + results_df[cols].astype(str).values.tolist()[:80]
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 6 * mm))

    if extra_notes:
        story.append(Paragraph("Notes", styles["Heading3"]))
        story.append(Paragraph(extra_notes.replace("\n", "<br/>"),
                               styles["Normal"]))
        story.append(Spacer(1, 6 * mm))

    # QR + signature
    story.append(Paragraph("Vérification & Signature", styles["Heading3"]))
    qr_data = f"{reference}|{inspection_id}|{datetime.now().isoformat()}"
    qr_img = _make_qr_image(qr_data, size_mm=32)
    sig_block = Table([[qr_img,
                        Paragraph(
                            f"<b>Référence :</b> {reference}<br/>"
                            f"<b>Signé électroniquement par :</b> "
                            f"{inspector_name or '—'}<br/>"
                            f"<b>Date :</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}<br/><br/>"
                            f"Scannez le QR pour vérifier l'authenticité.",
                            styles["Normal"])]],
                      colWidths=[40 * mm, 120 * mm])
    sig_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sig_block)

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(18 * mm, 10 * mm,
                          f"HSE PYXIS — {reference}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm,
                               f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()