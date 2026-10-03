"""Generate or verify the source-grounded PDF document corpus."""

# Long document clauses stay intact so their rendered and extracted text remains easy to audit.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
from functools import partial
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from business_brain.data import (
    DocumentManifest,
    build_commerce_inventory_dataset,
    build_finance_dataset,
    build_logistics_dataset,
    build_reference_catalog,
)
from business_brain.data.document_models import (
    DocumentKind,
    DocumentRecord,
    DocumentSource,
)
from business_brain.data.models import Sensitivity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_ROOT = PROJECT_ROOT / "data" / "documents"
AURA_ROOT = DOCUMENT_ROOT / "aura_brands"
REFERENCE_ROOT = DOCUMENT_ROOT / "reference"
MANIFEST_PATH = DOCUMENT_ROOT / "document_manifest.json"
SCHEMA_PATH = PROJECT_ROOT / "data" / "schemas" / "document_manifest.schema.json"

BLUE = colors.HexColor("#17324D")
TEAL = colors.HexColor("#1F6F78")
PALE = colors.HexColor("#EAF2F4")
GRAY = colors.HexColor("#5D6873")
LINE = colors.HexColor("#C9D3DA")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AuraTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=BLUE,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "AuraSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=GRAY,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "AuraH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "AuraH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=TEAL,
            spaceBefore=7,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "AuraBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13,
            textColor=colors.HexColor("#20262C"),
            spaceAfter=7,
        ),
        "small": ParagraphStyle(
            "AuraSmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=GRAY,
        ),
        "right": ParagraphStyle(
            "AuraRight",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT,
        ),
    }


STYLES = _styles()
INVARIANT_CANVAS = partial(canvas.Canvas, invariant=1)


def _page(canvas_obj: canvas.Canvas, doc: SimpleDocTemplate) -> None:
    canvas_obj.saveState()
    width, height = LETTER
    canvas_obj.setStrokeColor(LINE)
    canvas_obj.line(0.65 * inch, height - 0.48 * inch, width - 0.65 * inch, height - 0.48 * inch)
    canvas_obj.setFont("Helvetica-Bold", 7.5)
    canvas_obj.setFillColor(BLUE)
    canvas_obj.drawString(0.65 * inch, height - 0.36 * inch, "AURA BRANDS")
    canvas_obj.setFont("Helvetica", 7.2)
    canvas_obj.setFillColor(GRAY)
    canvas_obj.drawRightString(
        width - 0.65 * inch,
        height - 0.36 * inch,
        "Synthetic portfolio document - not a legal or commercial instrument",
    )
    canvas_obj.line(0.65 * inch, 0.48 * inch, width - 0.65 * inch, 0.48 * inch)
    canvas_obj.drawString(0.65 * inch, 0.31 * inch, "Aura Brands enterprise demo corpus")
    canvas_obj.drawRightString(
        width - 0.65 * inch, 0.31 * inch, f"Page {canvas_obj.getPageNumber()}"
    )
    canvas_obj.restoreState()


def _pdf(title: str, subtitle: str, story: list[object]) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=LETTER,
        leftMargin=0.72 * inch,
        rightMargin=0.72 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.68 * inch,
        title=title,
        author="Aura Brands Demo",
        subject="Synthetic enterprise document corpus",
        invariant=1,
    )
    opening = [
        Spacer(1, 0.12 * inch),
        Paragraph(title, STYLES["title"]),
        Paragraph(subtitle, STYLES["subtitle"]),
    ]
    document.build(
        [*opening, *story],
        onFirstPage=_page,
        onLaterPages=_page,
        canvasmaker=INVARIANT_CANVAS,
    )
    return output.getvalue()


def _section(number: str, heading: str, text: str, clause_id: str | None = None) -> list[object]:
    suffix = f" [{clause_id}]" if clause_id else ""
    return [
        Paragraph(f"{number} {heading}{suffix}", STYLES["h2"]),
        Paragraph(text, STYLES["body"]),
    ]


def _agreement(
    title: str,
    document_id: str,
    counterparty: str,
    effective_date: str,
    sections: list[tuple[str, str, str, str | None]],
) -> bytes:
    facts = Table(
        [
            ["Document ID", document_id, "Effective", effective_date],
            ["Customer", "Aura Brands, Inc.", "Counterparty", counterparty],
        ],
        colWidths=[0.9 * inch, 2.15 * inch, 0.78 * inch, 2.55 * inch],
    )
    facts.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("TEXTCOLOR", (0, 0), (0, -1), BLUE),
                ("TEXTCOLOR", (2, 0), (2, -1), BLUE),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTNAME", (3, 0), (3, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story: list[object] = [facts, Spacer(1, 10)]
    story += _section(
        "1.0",
        "Purpose and Scope",
        "This synthetic agreement defines the commercial and operational terms used by "
        "the Aura Brands demonstration environment. It is designed for retrieval, "
        "reconciliation, authorization, and citation testing.",
    )
    for number, heading, text, clause_id in sections:
        story += _section(number, heading, text, clause_id)
    story += [
        Spacer(1, 14),
        Paragraph("Acknowledgment", STYLES["h1"]),
        Paragraph(
            "The parties acknowledge that this document is synthetic and has no legal effect. "
            "Its terms are authoritative only inside the Aura Brands portfolio dataset.",
            STYLES["body"],
        ),
        Table(
            [
                ["Aura Brands Demo Approver", "Counterparty Demo Approver"],
                ["_____________________", "_____________________"],
            ],
            colWidths=[3.15 * inch, 3.15 * inch],
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        ),
    ]
    return _pdf(title, f"{document_id} | Synthetic agreement", story)


def _money(value: object) -> str:
    return f"${value:,.2f}"


def _invoice_pdf(invoice: object, lines: list[object], supplier_name: str, note: str) -> bytes:
    header = Table(
        [
            [
                Paragraph(f"<b>{supplier_name}</b><br/>Synthetic billing account", STYLES["body"]),
                Paragraph(f"<b>INVOICE</b><br/>{invoice.invoice_number}", STYLES["right"]),
            ],
            [
                Paragraph("Bill to: Aura Brands, Inc.<br/>Commerce Operations", STYLES["body"]),
                Paragraph(
                    f"Invoice date: {invoice.invoice_date}<br/>Due date: {invoice.due_date}<br/>"
                    f"Status: {invoice.invoice_status.value.replace('_', ' ').title()}",
                    STYLES["right"],
                ),
            ],
        ],
        colWidths=[3.3 * inch, 3.1 * inch],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    line_rows = [["Line ID", "Description", "Reference", "Qty", "Unit", "Amount"]]
    for line in lines:
        line_rows.append(
            [
                line.vendor_invoice_line_id,
                Paragraph(line.description, STYLES["small"]),
                line.shipment_id or invoice.purchase_order_id or "-",
                str(line.quantity),
                _money(line.unit_price),
                _money(line.line_amount),
            ]
        )
    line_table = Table(
        line_rows,
        colWidths=[1.15 * inch, 1.55 * inch, 1.12 * inch, 0.5 * inch, 0.72 * inch, 0.82 * inch],
        repeatRows=1,
    )
    line_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FA")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    totals = Table(
        [
            ["Subtotal", _money(invoice.subtotal_amount)],
            ["Tax", _money(invoice.tax_amount)],
            ["Total", _money(invoice.total_amount)],
            ["Outstanding", _money(invoice.outstanding_amount)],
        ],
        colWidths=[1.3 * inch, 1.0 * inch],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, 2), (-1, 2), 0.6, BLUE),
                ("BACKGROUND", (0, 3), (-1, 3), PALE),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story = [
        header,
        Spacer(1, 14),
        line_table,
        Spacer(1, 10),
        totals,
        Spacer(1, 12),
        Paragraph("Reconciliation note", STYLES["h2"]),
        Paragraph(note, STYLES["body"]),
    ]
    return _pdf(
        f"Invoice {invoice.invoice_number}",
        f"{invoice.vendor_invoice_id} | Synthetic accounting document",
        story,
    )


def _policy_pdf(title: str, document_id: str, sections: list[tuple[str, str, str]]) -> bytes:
    story: list[object] = []
    for number, heading, text in sections:
        story += _section(number, heading, text)
    return _pdf(title, f"{document_id} | Synthetic operating document", story)


def _synthetic_pdfs() -> dict[str, tuple[bytes, DocumentKind, Sensitivity, list[str], str]]:
    catalog = build_reference_catalog()
    commerce = build_commerce_inventory_dataset(catalog)
    logistics = build_logistics_dataset(catalog, commerce)
    finance = build_finance_dataset(catalog, commerce, logistics)
    supplier_by_id = {item.supplier_id: item for item in catalog.suppliers}
    invoice_by_id = {item.vendor_invoice_id: item for item in finance.vendor_invoices}
    lines_by_invoice: dict[str, list[object]] = {}
    for line in finance.vendor_invoice_lines:
        lines_by_invoice.setdefault(line.vendor_invoice_id, []).append(line)

    packaging = _agreement(
        "Packaging Manufacturing and Supply Agreement",
        "doc_aur_packaging_agreement",
        "Evergreen Packaging Works",
        "2026-07-01",
        [
            (
                "2.1",
                "Forecasts and Orders",
                "Aura Brands will issue rolling forecasts and binding purchase orders. Standard lead time is 21 calendar days.",
                None,
            ),
            (
                "3.1",
                "Volume Pricing",
                "For aggregate orders from 10,000 through 24,999 units, the contracted wholesale unit price is USD 0.42. Other volumes require a written price schedule.",
                "clause_price_tier_3_1",
            ),
            (
                "4.1",
                "Quality Acceptance",
                "Packaging must meet the approved artwork, dimensions, material, and batch traceability specifications.",
                None,
            ),
            (
                "5.2",
                "Payment Terms",
                "Valid, undisputed invoices are payable Net 60 from the invoice date. The invoice must reference the applicable purchase order.",
                "clause_payment_terms_5_2",
            ),
            (
                "7.1",
                "Confidentiality",
                "Commercial pricing and product forecasts are confidential and restricted to authorized finance and procurement personnel.",
                None,
            ),
        ],
    )
    skincare = _agreement(
        "Skincare Product Supply Agreement",
        "doc_aur_skincare_agreement",
        "Lumina Personal Care Labs",
        "2026-07-01",
        [
            (
                "2.2",
                "Purchase Orders",
                "Accepted purchase orders define the product, quantity, unit cost, destination warehouse, and requested delivery date.",
                None,
            ),
            (
                "5.1",
                "Payment Terms",
                "Valid invoices are payable Net 30 from the invoice date unless a purchase order states a longer period.",
                None,
            ),
            (
                "6.3",
                "Late Payment Charge",
                "An undisputed balance unpaid after its due date may incur a late charge of 1.5 percent per month, calculated on the outstanding balance.",
                "clause_late_payment_6_3",
            ),
            (
                "7.4",
                "Quality and Recall",
                "Supplier will maintain batch records and cooperate with any documented quality investigation or recall.",
                None,
            ),
        ],
    )
    fedex = _agreement(
        "Parcel Carrier Master Service Agreement",
        "doc_aur_fedex_msa",
        "FedEx Demo Carrier",
        "2026-07-15",
        [
            (
                "2.1",
                "Service Levels",
                "Expedited parcels have a two-calendar-day delivery commitment measured from carrier acceptance.",
                None,
            ),
            (
                "3.2",
                "Billing",
                "Each billed shipment must identify its tracking number, base transportation charge, fuel surcharge, and total charge.",
                None,
            ),
            (
                "4.2",
                "Late Delivery Credit",
                "When an eligible shipment misses the promised delivery time, Aura Brands receives a provisional credit equal to 10 percent of the carrier manifest charge, rounded to the nearest cent. Credit rate: 10%.",
                "clause_sla_credit_4_2",
            ),
            (
                "5.1",
                "Disputes",
                "Aura Brands may dispute an overcharge using the tracking number, carrier manifest amount, invoice line, and applicable service credit.",
                None,
            ),
        ],
    )
    northstar = _agreement(
        "Standard Parcel Service Agreement",
        "doc_aur_northstar_msa",
        "NorthStar Parcel",
        "2026-07-15",
        [
            (
                "2.1",
                "Service Commitment",
                "Standard parcels have a four-calendar-day service commitment.",
                None,
            ),
            (
                "3.1",
                "Charge Components",
                "Base transportation and fuel surcharge amounts must be separately itemized.",
                None,
            ),
            (
                "4.1",
                "Exception Reporting",
                "The carrier will provide timestamped delay and delivery exception events.",
                None,
            ),
        ],
    )
    blueline = _agreement(
        "Regional Freight Service Agreement",
        "doc_aur_blueline_msa",
        "BlueLine Regional Freight",
        "2026-07-15",
        [
            (
                "2.1",
                "Service Commitment",
                "Regional freight has a five-calendar-day delivery commitment unless a lane schedule states otherwise.",
                None,
            ),
            (
                "3.3",
                "Weight and Charges",
                "Reported shipment weight and all accessorial charges must be supported by the carrier manifest.",
                None,
            ),
            (
                "5.2",
                "Claims",
                "Billing and service claims must cite the shipment, manifest, invoice, and exception evidence.",
                None,
            ),
        ],
    )

    overdue_invoice = invoice_by_id["vin_aur_00010"]
    overdue_pdf = _invoice_pdf(
        overdue_invoice,
        lines_by_invoice[overdue_invoice.vendor_invoice_id],
        supplier_by_id[overdue_invoice.supplier_id].supplier_name,
        "As of 2026-09-21, USD 4,108.68 remains outstanding. Under clause "
        "clause_late_payment_6_3, the illustrative monthly late charge is USD 61.63.",
    )
    freight_invoice = invoice_by_id["vin_aur_00034"]
    target_lines = [
        item
        for item in lines_by_invoice[freight_invoice.vendor_invoice_id]
        if item.shipment_id == "shp_aur_000021"
    ]
    freight_pdf = _invoice_pdf(
        freight_invoice,
        target_lines,
        supplier_by_id[freight_invoice.supplier_id].supplier_name,
        "This audit excerpt shows the disputed shipment. Its billed charge is USD 40.35 "
        "versus the USD 22.35 manifest charge. The full invoice total is USD 3,173.55. "
        "The overbilling variance is USD 18.00 before the USD 2.24 SLA credit.",
    )

    returns = _policy_pdf(
        "Customer Return and Shipping Delay Policy",
        "doc_aur_return_shipping_policy",
        [
            (
                "1.0",
                "Customer Scope",
                "Support users may disclose public order status, tracking links, expected delivery windows, and this return policy.",
            ),
            (
                "2.0",
                "Delay Advisory",
                "When a carrier exception changes the expected date, support may draft a factual delay advisory without exposing internal carrier costs or contract terms.",
            ),
            (
                "3.0",
                "Returns",
                "Eligible unopened consumer goods may be returned within 30 days of delivery using an issued return authorization.",
            ),
            (
                "4.0",
                "Restricted Information",
                "Supplier pricing, profit margins, financial ledgers, and carrier agreements are not customer-facing information.",
            ),
        ],
    )
    compliance = _policy_pdf(
        "Finance and Statutory Compliance Calendar",
        "doc_aur_compliance_calendar",
        [
            (
                "1.0",
                "Weekly AP Review",
                "Every Monday, accounting reviews invoices due within seven days and all overdue balances.",
            ),
            (
                "2.0",
                "Monthly Carrier Audit",
                "By the fifth business day, accounting reconciles prior-month freight invoices to manifests, delivery events, and SLA credits.",
            ),
            (
                "3.0",
                "Quarterly Close",
                "Finance certifies revenue, refunds, freight expense, COGS, and regional net margin reconciliations.",
            ),
            (
                "4.0",
                "Evidence Retention",
                "Invoices, approvals, dispute notices, purchase orders, and supporting shipment evidence are retained with tenant and sensitivity metadata.",
            ),
        ],
    )
    replenishment = _policy_pdf(
        "Inventory Replenishment and Approval Procedure",
        "doc_aur_inventory_replenishment_sop",
        [
            (
                "1.0",
                "Stockout Review",
                "Logistics reviews available stock, recent demand, delayed inbound quantity, reorder points, and safety stock before proposing replenishment.",
            ),
            (
                "2.0",
                "Draft Purchase Order",
                "The agent may draft a schema-valid purchase order, but it cannot submit the order without the required human approval.",
            ),
            (
                "3.0",
                "Approval Threshold",
                "External purchase order po_aur_approval_00001 for USD 3,536.00 requires Founder or CFO approval before submission.",
            ),
            (
                "4.0",
                "Audit Trail",
                "The approval decision, actor role, timestamp, draft payload, and final status must be retained for crash-safe resumption.",
            ),
        ],
    )
    return {
        "doc_aur_packaging_agreement": (
            packaging,
            DocumentKind.AGREEMENT,
            Sensitivity.EXECUTIVE,
            ["clause_price_tier_3_1", "clause_payment_terms_5_2"],
            "Packaging Manufacturing and Supply Agreement",
        ),
        "doc_aur_skincare_agreement": (
            skincare,
            DocumentKind.AGREEMENT,
            Sensitivity.ACCOUNTING,
            ["clause_late_payment_6_3"],
            "Skincare Product Supply Agreement",
        ),
        "doc_aur_fedex_msa": (
            fedex,
            DocumentKind.AGREEMENT,
            Sensitivity.ACCOUNTING,
            ["clause_sla_credit_4_2"],
            "Parcel Carrier Master Service Agreement",
        ),
        "doc_aur_northstar_msa": (
            northstar,
            DocumentKind.AGREEMENT,
            Sensitivity.OPERATIONS,
            [],
            "Standard Parcel Service Agreement",
        ),
        "doc_aur_blueline_msa": (
            blueline,
            DocumentKind.AGREEMENT,
            Sensitivity.OPERATIONS,
            [],
            "Regional Freight Service Agreement",
        ),
        "doc_aur_invoice_inv_00010": (
            overdue_pdf,
            DocumentKind.INVOICE,
            Sensitivity.ACCOUNTING,
            [],
            "Supplier Invoice INV-AUR-00010",
        ),
        "doc_aur_invoice_frt_00034": (
            freight_pdf,
            DocumentKind.INVOICE,
            Sensitivity.ACCOUNTING,
            [],
            "Freight Invoice FRT-AUR-00034 Audit Excerpt",
        ),
        "doc_aur_return_shipping_policy": (
            returns,
            DocumentKind.POLICY,
            Sensitivity.PUBLIC,
            [],
            "Customer Return and Shipping Delay Policy",
        ),
        "doc_aur_compliance_calendar": (
            compliance,
            DocumentKind.CALENDAR,
            Sensitivity.ACCOUNTING,
            [],
            "Finance and Statutory Compliance Calendar",
        ),
        "doc_aur_inventory_replenishment_sop": (
            replenishment,
            DocumentKind.PROCEDURE,
            Sensitivity.OPERATIONS,
            [],
            "Inventory Replenishment and Approval Procedure",
        ),
    }


def _page_count(content: bytes) -> int:
    return len(PdfReader(BytesIO(content)).pages)


def _record(
    *,
    document_id: str,
    title: str,
    kind: DocumentKind,
    source_type: DocumentSource,
    relative_path: str,
    content: bytes,
    sensitivity: Sensitivity,
    ingest: bool,
    clause_ids: list[str] | None = None,
    source_url: str | None = None,
    license_name: str | None = None,
    attribution: str | None = None,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        title=title,
        document_kind=kind,
        source_type=source_type,
        relative_path=relative_path,
        document_date="2026-09-21" if source_type == DocumentSource.SYNTHETIC else None,
        tenant_id="tenant_aura" if source_type == DocumentSource.SYNTHETIC else None,
        sensitivity=sensitivity,
        ingest=ingest,
        clause_ids=clause_ids or [],
        source_url=source_url,
        license_name=license_name,
        attribution=attribution,
        byte_count=len(content),
        page_count=_page_count(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def render_artifacts() -> dict[Path, bytes]:
    artifacts: dict[Path, bytes] = {}
    records: list[DocumentRecord] = []
    synthetic = _synthetic_pdfs()
    for document_id, (content, kind, sensitivity, clauses, title) in synthetic.items():
        path = AURA_ROOT / f"{document_id}.pdf"
        artifacts[path] = content
        records.append(
            _record(
                document_id=document_id,
                title=title,
                kind=kind,
                source_type=DocumentSource.SYNTHETIC,
                relative_path=path.relative_to(PROJECT_ROOT).as_posix(),
                content=content,
                sensitivity=sensitivity,
                ingest=True,
                clause_ids=clauses,
            )
        )

    references = (
        (
            "doc_ref_cuad_supply",
            "CUAD Supply Agreement Reference",
            "cuad_supply_agreement.pdf",
            "https://huggingface.co/datasets/theatticusproject/cuad/resolve/main/CUAD_v1/full_contract_pdf/Part_I/Supply/AgapeAtpCorp_20191202_10-KA_EX-10.1_11911128_EX-10.1_Supply%20Agreement.pdf",
        ),
        (
            "doc_ref_cuad_transportation",
            "CUAD Transportation Agreement Reference",
            "cuad_transportation_agreement.pdf",
            "https://huggingface.co/datasets/theatticusproject/cuad/resolve/main/CUAD_v1/full_contract_pdf/Part_I/Transportation/ZtoExpressCaymanInc_20160930_F-1_EX-10.10_9752871_EX-10.10_Transportation%20Agreement.pdf",
        ),
    )
    for document_id, title, filename, source_url in references:
        path = REFERENCE_ROOT / filename
        if not path.exists():
            raise ValueError(f"missing downloaded reference: {path.relative_to(PROJECT_ROOT)}")
        content = path.read_bytes()
        records.append(
            _record(
                document_id=document_id,
                title=title,
                kind=DocumentKind.REFERENCE,
                source_type=DocumentSource.PUBLIC_REFERENCE,
                relative_path=path.relative_to(PROJECT_ROOT).as_posix(),
                content=content,
                sensitivity=Sensitivity.PUBLIC,
                ingest=False,
                source_url=source_url,
                license_name="CC BY 4.0",
                attribution="Contract Understanding Atticus Dataset, The Atticus Project",
            )
        )

    manifest = DocumentManifest(
        generated_at="2026-09-22T00:30:00Z",
        document_count=len(records),
        synthetic_count=len(synthetic),
        public_reference_count=len(references),
        documents=sorted(records, key=lambda item: item.document_id),
    )
    manifest_text = json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    schema_text = json.dumps(DocumentManifest.model_json_schema(), indent=2, sort_keys=True) + "\n"
    artifacts[MANIFEST_PATH] = manifest_text.encode()
    artifacts[SCHEMA_PATH] = schema_text.encode()
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    artifacts = render_artifacts()
    if args.check:
        stale = [
            path
            for path, expected in artifacts.items()
            if not path.exists() or path.read_bytes() != expected
        ]
        for path in stale:
            print(f"stale: {path.relative_to(PROJECT_ROOT)}")
        if stale:
            return 1
        print("document corpus artifacts are current")
        return 0
    for path, content in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"wrote: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
