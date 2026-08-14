# Blendy Business Suite — Product Requirements Document (PRD)

**Status:** Draft v1
**Owner:** Maina
**Last updated:** August 2026

---

## 1. Vision

Blendy is a business management suite — inventory, sales/POS, CRM, and compliance — built for small and medium businesses in Kenya, starting with general retail in Nairobi and expanding into health-adjacent retail (pharmacies, clinics, labs).

The long-term vision is a single platform that an SME owner runs their entire storefront operation on: what's in stock, what's being sold, who their customers are, and whether they're compliant with KRA's eTIMS requirements — without needing separate tools or manual reconciliation for any of it.

Blendy is built as a **general-purpose core with vertical go-to-market**: the underlying product (inventory, sales, CRM, compliance, reporting) is generic enough to serve any retail business, but early customer acquisition and messaging will target one vertical at a time — general retail first, healthcare second — so the product can be sharpened against real, specific workflows instead of diluted across everyone at once.

Blendy is also intended to double as the backend for Maina's e-commerce client work, so client builds reuse a proven core rather than bespoke one-off systems each time.

---

## 2. Problem Statement

Kenyan SMEs — particularly owner-operated retail shops — face a cluster of related, compounding problems:

1. **No real-time inventory visibility.** Stock is tracked on paper, in notebooks, or not at all. Stockouts and overstocking both happen because owners can't see what's actually on the shelf.
2. **Manual sales and payment reconciliation.** Most sales are paid via M-Pesa Till/Paybill, but confirming which payments match which sales is a manual, error-prone, end-of-day exercise.
3. **eTIMS compliance is now mandatory and enforced in real time.** As of 2026, KRA cross-validates all declared income and expenses against eTIMS records automatically. Businesses without integrated eTIMS invoicing risk disallowed expense deductions, audit flags, and penalties — this has shifted from a compliance nice-to-have to an existential business risk.
4. **No visibility into business performance.** Owners can't easily answer "what's my best-selling product," "what's my daily revenue trend," or "which staff member is at the till when discrepancies happen."
5. **Staff accountability and shrinkage.** Owner-operators who aren't always on-site have limited visibility into whether staff are recording sales accurately.
6. **Fragmented tooling.** Existing solutions are either generic global tools (Zoho, Odoo, QuickBooks) that don't fit local payment rails and compliance needs, or narrow single-purpose apps (POS-only, or eTIMS-only) that leave the rest of the workflow unsolved.

---

## 3. Target Market

### Primary (Phase 1): General retail SMEs in Nairobi
- Owner-operated shops: mini-marts, electronics stalls, hardware stores, clothing/apparel retail, general stores
- 1–5 staff, single location
- Currently using M-Pesa Till for the majority of payments
- Little to no existing digital inventory/sales system (notebook, spreadsheet, or nothing)
- Newly exposed to eTIMS compliance pressure and unsure how to handle it affordably

### Secondary (Phase 2): Health-adjacent retail
- Pharmacies, small clinics, diagnostic labs
- Same core retail workflow (inventory, sales, customers) plus additional regulatory layers: batch/expiry tracking, prescription logging, pharmacy board and stricter eTIMS scrutiny
- Natural expansion given founder's existing domain experience (Tibu LIMS) and potential warm introductions through existing health-sector relationships

### Tertiary: E-commerce client projects
- Client engagements (e.g. gym wear, household appliances e-commerce sites) that need inventory/sales backends — Blendy's core serves as the reusable foundation instead of bespoke builds per client

---

## 4. Product Pillars

### 4.1 Inventory Management
Track products, stock levels, and movement in real time. Low-stock alerts. Product categorization. Foundation for all other modules (sales can't be recorded accurately without accurate inventory).

**Foundational requirement (added post-ERPNext review — see §12):** stock must be modeled as an append-only ledger of movements (sale, restock, adjustment, return), not a single mutable quantity field. The current quantity is always a derived sum, never directly edited. This is a data-model decision, not a UI feature, and must be in place from the first line of code — see §12 for why.

### 4.2 Sales / Point of Sale (POS)
Fast, low-friction sale recording at the point of transaction — designed for a shop counter, not a back office. Must work well on a phone or tablet given the target customer's hardware reality.

**Foundational requirement (added post-ERPNext review — see §12):** every sale needs a defined correction path — void pre-compliance-submission, credit note post-submission — modeled from day one rather than added reactively after the first pilot-shop mistake.

### 4.3 Payments — M-Pesa Integration
STK push integration for payment collection, with automatic reconciliation between M-Pesa payment confirmations and sale records. This removes the single most repetitive manual task in a Kenyan retail business's day.

### 4.4 Compliance — eTIMS
Automatic, compliant e-invoice generation on every sale, submitted through KRA's eTIMS system. This is a core differentiator and urgency driver — not an add-on.

### 4.5 CRM (Phase 2+)
Customer records, purchase history, and (eventually) loyalty tracking — deferred past MVP since the primary target segment is largely walk-in retail, but relevant for repeat-customer businesses and the healthcare vertical (patient/client history).

### 4.6 Reporting & Analytics
Sales trends, top/slow-moving products, staff-level sales breakdowns. Built for an owner making quick restocking and performance decisions, not a full BI suite.

**Note (added post-ERPNext review — see §12):** margin/profit reporting (as opposed to revenue-only reporting) requires a per-unit cost to exist on stock records. If cost isn't captured at restock time from the start, profit reporting in Phase 2 will require backfilling historical data that was never collected — cheaper to capture cost now even if unused by MVP reports.

### 4.7 Multi-tenant, Multi-user Architecture
Each business is an isolated tenant. Role-based access (owner vs. staff/cashier) from day one, both for accountability and because this is the same architecture that lets Blendy later serve e-commerce client instances and the healthcare vertical without a rebuild.

### 4.8 Vertical Compliance Modules (Phase 2)
Health-specific add-ons — batch/expiry tracking, prescription/patient tie-in, pharmacy-board-aligned reporting — layered on top of the same core rather than built as a separate product.

### 4.9 Accountability & Reconciliation (new pillar — added post-ERPNext review, see §12)
End-of-day/per-session cash-up: a per-cashier, per-day summary reconciling recorded sales against actual collections by payment method (M-Pesa auto-matched, M-Pesa manually matched, cash). This directly serves the staff-accountability/shrinkage problem named in §2.5, which the original pillars didn't have a dedicated feature addressing — reporting (4.6) covers trends, not shift-level reconciliation.

---

## 5. Vertical Strategy

**Phase 1 — General retail, Nairobi.** Build and sell the core product (inventory, POS, M-Pesa, eTIMS, reporting, multi-user) to general retail SMEs. Prove retention and word-of-mouth with a focused set of pilot customers before broadening messaging.

**Phase 2 — Healthcare retail.** Layer in health-specific compliance modules once the core is proven. Leverage existing health-sector relationships and domain knowledge (Tibu LIMS) as a faster path to pilot customers than cold outreach.

**Phase 3 — Horizontal expansion.** Once the core has proven product-market fit in two verticals, expand marketing and onboarding to serve general SMEs across sectors without needing a new vertical-specific build each time.

Architecture principle throughout: **build general, sell vertical.** The codebase should not need a fork per vertical — only a thin, swappable layer of terminology, workflow ordering, and compliance rules changes.

---

## 6. Business Model

- **Core revenue:** SaaS subscription, tiered by business size/feature access (e.g. a lean tier covering inventory + POS + eTIMS, a higher tier adding CRM, multi-branch, and advanced reporting)
- **Secondary revenue:** Blendy's core reused as the backend for e-commerce client projects, either as a licensing/support arrangement or bundled into project delivery pricing
- **Future consideration:** transaction-based or M-Pesa-reconciliation-volume pricing as an alternative/complement to flat subscription, given how central payment reconciliation is to the value proposition

---

## 7. Competitive Landscape (context)

- **Generic global tools** (Zoho, Odoo, QuickBooks): broad feature sets but not tailored to M-Pesa rails or eTIMS specifics, and often priced/positioned for larger businesses
- **Local eTIMS-ready POS/accounting vendors**: growing segment given 2026 compliance pressure; several already market "eTIMS-ready" as a core feature, meaning eTIMS alone is necessary but not sufficient differentiation
- **Differentiation for Blendy**: the combination of M-Pesa-native reconciliation + eTIMS compliance + inventory/sales/CRM in one product, entering through a specific vertical (general retail, then health) rather than a generic "for everyone" pitch

---

## 8. Success Metrics (directional, to refine post-MVP)

- Number of active paying shops using Blendy for daily sales recording
- % of sales that are automatically reconciled (M-Pesa match rate) without manual intervention
- % of sales issued with a compliant eTIMS invoice automatically
- Customer retention / churn after first 90 days
- Qualitative: owner-reported time saved on reconciliation and reporting per week

---

## 9. Key Risks

- **Crowded compliance-tooling space** — eTIMS-ready is becoming table stakes; must not be the sole pitch
- **Trust and cash handling** — SME owners are cautious about tools touching their payment records; onboarding must build trust quickly (fast setup, visible value in week one)
- **Capital/time constraints** — building alongside a full-time job means slower iteration; MVP scope must stay disciplined
- **Regulatory change risk** — eTIMS rules have shifted multiple times since 2022; product must be built to adapt to KRA rule changes without major rework
- **Data-model debt risk (added post-ERPNext review — see §12)** — several ERP fundamentals (stock ledger, sale correction/credit-note flow) are far more expensive to retrofit than to build in from day one; scoping these out of MVP as "not now" is fine, scoping them out of the *data model* is not.

---

## 10. Roadmap (high-level)

| Phase | Focus | Target Customer |
|---|---|---|
| MVP | Inventory, POS, M-Pesa reconciliation, eTIMS invoicing, basic reporting, multi-user, stock ledger, restock entry, sale void/credit-note, end-of-day cash-up | General retail SME, Nairobi |
| Phase 2 | CRM, supplier/purchase orders, multi-branch, health compliance modules, credit/partial-payment sales, margin/profit reporting | General retail expansion + healthcare vertical |
| Phase 3 | Horizontal expansion, e-commerce client reuse formalized, advanced analytics | Broader SME market across verticals |

See `blendy-mvp.md` for detailed MVP scope, user stories, and validation test scenarios.

---

## 11. Explicitly Deferred, Named Risks (previously silent gaps)

Carried over from the MVP review (§12) so the PRD-level roadmap reflects them, not just the MVP doc:

- **Credit sales / "deni" (buy-now-pay-later, partial payment).** Very common in Kenyan retail. Deferred to Phase 2 as a real accounts-receivable subsystem (who owes what, aging, follow-up) rather than a quick bolt-on. Risk: a pilot shop that regularly extends credit to customers may see reduced MVP value until this exists — worth screening for during pilot shop selection (§9 of MVP doc).
- **Units of measure beyond one default per product.** Relevant to hardware/foodstuff retail selling in bulk/loose quantities. Deferred, flagged as a segment-fit risk for pilot selection.
- **Stock valuation method (FIFO recommended).** Not required for MVP's revenue-only reporting, but item cost should be captured at restock time now so Phase 2 profit/margin reporting doesn't require backfilling historical data.

---

## 12. ERPNext Feature Review — What the Original PRD Missed

Cross-checked against ERPNext's core module set (`erpnext-feature-map-and-lessons.md`) and its accounting/inventory fundamentals. Full detail and user-story-level treatment lives in `blendy-mvp.md` §10; this section summarizes the PRD-level implications.

**The gap, in one sentence:** the original PRD scoped features (what the user does) well but didn't address the underlying data-integrity and correction-path plumbing that ERPNext's decade of production use shows is what actually breaks trust in day-2 operation.

**What was added:**
1. **Stock ledger as an architectural principle**, not a checkbox feature — folded into Pillar 4.1. The single most-cited real-world ERPNext support issue is "incorrect stock balances," which stems from systems that update a quantity field directly instead of deriving it from an immutable movement log.
2. **A defined sale-correction path** (void pre-compliance-submission vs. credit note post-submission) — folded into Pillar 4.2. The original PRD's compliance pillar (4.4) covered issuing invoices but not correcting them; under eTIMS, editing/deleting a submitted invoice isn't just bad practice, it risks actual compliance violation.
3. **A new pillar, 4.9 Accountability & Reconciliation** (end-of-day cash-up), because the PRD's own problem statement (§2.5, staff accountability/shrinkage) didn't have a corresponding product pillar — reporting (4.6) covers trend analysis, not shift-level "does the till match the record" reconciliation, which is a different and more urgent job.
4. **Named, rather than silent, deferrals** for credit sales, units of measure, and valuation method (§11) — these were absent from the original PRD entirely; they're still correctly out of MVP scope, but now documented as conscious tradeoffs with stated risk, rather than gaps someone discovers later.
5. **A new roadmap-level risk** (§9) about data-model debt specifically, distinct from the general "capital/time constraints" risk already listed — the point being that deferring a *feature* is cheap, deferring the *underlying data model* for that feature is not.

**What was deliberately not added**, and why it's still correct to exclude from MVP-level PRD scope: full accounting (GL, P&L, balance sheet), manufacturing/BOM, multi-currency, quality management, HR/payroll, and asset management. None of these map to the Phase 1 general-retail persona's actual pain points (§2), and adding them would dilute the vertical-first go-to-market strategy (§5) the PRD already commits to. The ERPNext review confirms these are safe to exclude — the corrections above are specifically the subset of ERPNext's discipline that *does* apply even to a lean MVP, not a case for building more.
