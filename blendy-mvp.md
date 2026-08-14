# Blendy MVP — Scope, User Stories & Validation Plan

**Status:** Draft v1
**Owner:** Maina
**Target customer:** General retail SME / store business, Nairobi
**Companion doc:** `blendy-suite.md` (holistic PRD)

---

## 1. MVP Goal

Prove that a Nairobi general retail shop owner will adopt Blendy over their current notebook/spreadsheet/nothing setup, and stay active, because it removes real daily friction — specifically around stock visibility, M-Pesa payment reconciliation, and eTIMS compliance.

**MVP success = a pilot shop uses Blendy daily for at least 4 consecutive weeks without reverting to their old method, and reports it saved them meaningful time or reduced a specific pain point (reconciliation, compliance risk, or stock visibility).**

---

## 2. In Scope (v1)

1. Inventory management (add/edit products, stock levels, low-stock alerts)
2. Sales / POS (fast sale entry, works on phone/tablet)
3. M-Pesa STK push + automatic payment reconciliation
4. eTIMS-compliant invoice generation on every sale
5. Basic sales reporting (daily/weekly revenue, top/slow-moving products)
6. Multi-user accounts with owner/cashier roles
7. **Stock ledger (append-only movement log)** underlying every stock change — sale, manual adjustment, restock — not just a mutable "current quantity" field
8. **Manual stock adjustment / restock entry** — a lightweight way to increase stock when new inventory arrives, without full supplier/PO management
9. **Sale void (pre-eTIMS-submission) and returns/credit note (post-submission)** — with correct stock reversal and, where the original invoice was already submitted to eTIMS, a compliant credit note rather than editing or deleting the original
10. **End-of-day cash-up / session close** — a simple per-cashier, per-day summary (expected vs. actual, split by payment method) for accountability

> These four items were not in the original MVP scope but are added per the ERPNext-informed review below (§10) — they're foundational plumbing that is expensive to retrofit later, not "extra" features.

## 3. Explicitly Out of Scope (v1)

- CRM / customer loyalty tracking
- Supplier and purchase-order management (beyond the lightweight manual restock entry in §2)
- Multi-branch support
- Full accounting/expense tracking beyond sales (no general ledger, no P&L/balance sheet — see §10 for the specific accounting primitive that IS needed even so)
- Barcode scanner hardware integration
- Health/pharmacy-specific compliance modules (Phase 2)
- **Credit sales / "deni" (buy-now-pay-later) and partial payment** — flagged as a known gap, not a blind spot: very common in Kenyan retail, but full accounts-receivable tracking is a real accounting subsystem. Deferred to Phase 2, but see §10 for the risk this creates.
- Units of measure beyond a single default per product (e.g. selling loose/bulk items in different units) — deferred, but a known limitation for some general retail (e.g. hardware, foodstuffs sold by weight)

---

## 4. Primary Persona

**Name (archetype):** Nairobi shop owner-operator
**Business:** Mini-mart, electronics stall, hardware, or clothing retail
**Team:** 1–3 staff, owner not always on-site
**Current tools:** Notebook or spreadsheet, M-Pesa Till for most payments
**Pain today:** Can't tell what's in stock without a physical count; reconciles M-Pesa payments against sales manually at day's end; unsure how to comply with eTIMS; no visibility into which products sell well; limited trust in staff-recorded sales when not present

---

## 5. User Stories

### Inventory
- **US-1:** As a shop owner, I want to add a product with a name, price, and starting stock quantity, so that I can start tracking what I sell.
- **US-2:** As a shop owner, I want stock levels to automatically decrease when a sale is recorded, so that I always see accurate current stock without manual counting.
- **US-3:** As a shop owner, I want to be alerted when a product's stock falls below a threshold I set, so that I can reorder before running out.
- **US-4:** As a shop owner, I want to edit a product's price or details, so that I can respond to supplier price changes without re-adding the product.

### Sales / POS
- **US-5:** As a cashier, I want to search for or select a product and quantity to record a sale in under a few taps, so that I don't slow down the customer at checkout.
- **US-6:** As a cashier, I want to record a sale with multiple products in one transaction, so that I can handle a customer buying several items at once.
- **US-7:** As a shop owner, I want every recorded sale to generate a receipt the customer can see or receive, so that transactions feel legitimate and trackable.

### M-Pesa & Payments
- **US-8:** As a cashier, I want to trigger an M-Pesa STK push to the customer's phone for the sale total, so that I don't have to manually verify a Till payment.
- **US-9:** As a shop owner, I want a completed M-Pesa payment to automatically match to its corresponding sale record, so that I never have to manually reconcile payments against sales at the end of the day.
- **US-10:** As a shop owner, I want to see any sales with unmatched or pending payments flagged clearly, so that I can follow up on the rare mismatch instead of discovering it days later.

### eTIMS Compliance
- **US-11:** As a shop owner, I want every sale to automatically generate a KRA-compliant eTIMS invoice, so that I don't have to manually issue invoices or risk non-compliance.
- **US-12:** As a shop owner, I want to see confirmation that an invoice was successfully submitted to eTIMS (or a clear error if it failed), so that I'm never unknowingly non-compliant.

### Reporting
- **US-13:** As a shop owner, I want to see today's and this week's total revenue at a glance, so that I can track performance without doing manual math.
- **US-14:** As a shop owner, I want to see my top-selling and slowest-moving products over a time period, so that I know what to restock and what to discount or drop.

### Multi-user / Roles
- **US-15:** As a shop owner, I want to create staff accounts with cashier-only access, so that staff can record sales without seeing full business reports or being able to edit inventory.
- **US-16:** As a shop owner, I want to see which staff member recorded each sale, so that I have accountability if there's a discrepancy.

### Stock Integrity & Restocking
- **US-17:** As a shop owner, I want to record new stock arriving (e.g. from a supplier restock) as a distinct "stock in" entry, so that my stock levels stay accurate without re-adding products from scratch.
- **US-18:** As a shop owner, I want every stock change — sale, restock, manual correction — recorded as an individual, timestamped, attributed entry, so that if a stock number ever looks wrong I can trace exactly what caused it instead of just seeing an unexplained current total.
- **US-19:** As a shop owner, I want to manually adjust a product's stock count (e.g. after a physical count finds a discrepancy) with a required reason note, so that shrinkage or counting errors are visible and explainable rather than silently overwriting history.

### Sale Corrections & Returns
- **US-20:** As a cashier, I want to void a sale before it's been submitted to eTIMS (e.g. I entered it by mistake), so that a genuine error doesn't become a compliance record.
- **US-21:** As a shop owner, I want to process a customer return/refund on a sale that's already been invoiced through eTIMS, so that the correction is handled as a proper credit note rather than editing or deleting a submitted invoice.
- **US-22:** As a shop owner, I want a returned item's stock to automatically increase back, so that inventory stays accurate after a return.

### End-of-Day / Session
- **US-23:** As a shop owner, I want to see a per-cashier, per-day summary of sales by payment method (M-Pesa vs. cash vs. pending) at close of business, so that I can confirm what was actually collected versus what was recorded.
- **US-24:** As a cashier, I want to formally "close" my session/day, so that there's a clear record of when my shift's transactions end and the next cashier's begin.

---

## 6. Acceptance Criteria (sample — key stories)

**US-2 (stock auto-decrement):**
- Given a product has 10 units in stock, when a sale of 3 units is recorded, then stock should show 7 units immediately after the sale is confirmed.
- Given a product has 0 units in stock, the system should prevent or clearly warn against recording a sale for that product.

**US-9 (auto payment reconciliation):**
- Given an STK push is sent for a sale of KES 500, when the customer completes payment via M-Pesa, then the sale record should update to "Paid" within the M-Pesa callback window without manual action.
- Given a payment fails or times out, the sale should remain marked "Pending" and be visible in a pending-payments view.

**US-11 (eTIMS invoice generation):**
- Given a sale is marked "Paid," an eTIMS-compliant invoice should be generated and submitted automatically.
- Given eTIMS submission fails (e.g. network/API issue), the system should retry and/or flag the invoice as failed for manual follow-up, never silently drop it.

**US-15 (role-based access):**
- Given a cashier-role user logs in, they should be able to record sales and view current stock, but not access revenue reports, edit product prices, or manage other users.

**US-18 (stock ledger / traceability):**
- Given any stock change occurs (sale, restock, manual adjustment, return), an individual ledger entry should be created recording the quantity delta, reason/source, timestamp, and the user who caused it — the current stock level is always a derived sum of this ledger, never a directly-edited field.

**US-20 / US-21 (void vs. credit note):**
- Given a sale has not yet been submitted to eTIMS, the cashier (or owner) can void it outright; the sale and any stock decrement are fully reversed and no eTIMS record is created.
- Given a sale has already been submitted to eTIMS, it can no longer be voided or edited — only reversed via a linked credit note, which itself is submitted to eTIMS and restores stock.

**US-23 (end-of-day cash-up):**
- Given a cashier has recorded sales during a session, the end-of-day summary shows total sales by payment method (M-Pesa auto-reconciled, M-Pesa manually matched, cash, still pending) and flags any sale still in a "Pending" state at close.

---

## 7. Test Scenarios to Validate the Build

### Functional / technical validation
1. Add a new product, confirm it appears in inventory with correct stock and price.
2. Record a single-item sale; confirm stock decrements and a receipt is generated.
3. Record a multi-item sale; confirm all items decrement correctly and total is accurate.
4. Trigger STK push for a sale; complete payment on a test line; confirm auto-reconciliation within expected time.
5. Simulate a failed/timed-out M-Pesa payment; confirm the sale is flagged as pending, not silently marked paid.
6. Confirm an eTIMS invoice is generated and submitted for a completed sale; verify against KRA's eTIMS sandbox/test environment if available.
7. Simulate an eTIMS submission failure; confirm the system flags it rather than failing silently.
8. Set a low-stock threshold; sell down to that threshold; confirm the alert fires.
9. Log in as a cashier-role user; confirm restricted access matches acceptance criteria.
10. Generate a daily and weekly sales report; confirm totals match the sum of recorded sales for that period.
11. Record a restock ("stock in") entry for a product; confirm stock increases and a distinct ledger entry is created (separate from any sale-driven decrement).
12. Deliberately create a stock discrepancy, then perform a manual adjustment with a reason note; confirm the ledger reflects the adjustment and reason rather than silently overwriting the prior total.
13. Void a sale before eTIMS submission; confirm stock is restored and no eTIMS invoice was created.
14. Process a return on a sale already submitted to eTIMS; confirm a credit note is generated and submitted, stock is restored, and the original invoice remains untouched (not edited/deleted).
15. Close a cashier's end-of-day session; confirm the summary correctly totals sales by payment method and flags any still-pending sale.

### Market / adoption validation (with real pilot shop)
1. **Onboarding time test:** Can a real shop owner add their first 10-20 products and complete their first sale within a single sitting, without heavy hand-holding? (Signals whether onboarding friction is low enough for organic adoption.)
2. **Daily-use test:** Does the pilot shop use Blendy for the majority of their sales (not just occasionally) within the first week? (Signals real behavior change vs. novelty use.)
3. **Reconciliation time-saved test:** Ask the owner to estimate time spent on end-of-day reconciliation before and after Blendy. (Validates the core value proposition quantitatively.)
4. **Compliance confidence test:** Ask the owner directly whether they feel more confident about eTIMS compliance after using Blendy for a set period. (Validates the compliance-urgency hypothesis.)
5. **Retention test:** Does the shop keep using Blendy after 4 weeks without prompting, or revert to their old method? (Core MVP success signal.)
6. **Referral signal:** Does the pilot owner mention or recommend Blendy to another shop owner unprompted? (Early word-of-mouth signal for vertical GTM viability.)

---

## 8. Fallback / Degraded-Mode Handling

### M-Pesa STK push failure
If the STK push fails or times out, the sale is not blocked. The customer can instead pay via the M-Pesa app or *334# toolkit directly to the shop's Till/Paybill. The system then performs **manual/deferred reconciliation** by matching the incoming M-Pesa payment to the open sale using the customer's phone number and the amount paid. The sale stays in a "Pending" state until this match succeeds, and is flagged for the owner/cashier to review if no match is found within a reasonable window.

**New/updated user story:**
- **US-9b:** As a cashier, when an STK push fails, I want to still complete the sale by having the customer pay directly via the M-Pesa app or Till, so that a failed push never blocks a transaction.
- **US-9c:** As the system, when a direct M-Pesa payment comes in matching an open sale's phone number and amount, I want to automatically reconcile it to that sale, so that the owner doesn't have to manually match payments even in the fallback path.

**Acceptance criteria:**
- Given an STK push fails or times out, the cashier can mark the sale as "awaiting direct payment" and complete the transaction (hand over goods) without the app blocking them.
- Given a direct M-Pesa payment arrives with a phone number and amount matching an open/pending sale, the system automatically reconciles it and marks the sale "Paid."
- Given no matching payment arrives within a defined window, the sale remains visible in a "Pending" queue for manual review/matching by the owner.

### eTIMS submission failure
eTIMS availability is decoupled from the sale itself: as long as the sale/payment transaction completes, the shop can hand over the product immediately. The eTIMS invoice is generated and queued, then **synced to KRA in the background** via a retry mechanism once the eTIMS service is reachable again — the customer and cashier are never blocked waiting on eTIMS.

**New/updated user story:**
- **US-12b:** As the system, when eTIMS is temporarily unreachable at the time of sale, I want to queue the invoice and retry submission in the background, so that sales are never delayed or blocked by eTIMS downtime.
- **US-12c:** As a shop owner, I want to see which invoices are still pending eTIMS sync versus confirmed, so that I know if anything needs my attention once connectivity/service is restored.

**Acceptance criteria:**
- Given eTIMS is unreachable at time of sale, the sale completes normally and the invoice is queued locally with a "Pending Sync" status.
- Given eTIMS becomes reachable again, queued invoices are automatically retried and submitted without manual intervention.
- Given an invoice fails repeatedly beyond a retry threshold, it is surfaced to the owner as needing manual attention rather than retried silently forever.

### Additional test scenarios (fallback paths)
11. Simulate an STK push failure; complete payment via direct M-Pesa app payment; confirm the system reconciles it to the correct open sale by phone number and amount.
12. Simulate an eTIMS outage during a sale; confirm the sale completes and the invoice queues as "Pending Sync."
13. Restore eTIMS availability after an outage; confirm queued invoices sync automatically without manual resubmission.

---

## 9. Open Questions to Resolve Before/During Build

- Which specific pilot shop(s) will test the MVP, and how will they be recruited?
- What's the pricing model for the pilot phase — free pilot, discounted, or full price from day one?
- What device(s) will the pilot shop actually use day-to-day (Android phone, tablet, shared counter device)? This affects UI priorities.

---

## 10. ERPNext-Informed MVP Additions — What Was Missing and Why

Reviewed against ERPNext's core module set (`erpnext-feature-map-and-lessons.md`). The original MVP scope covered the "happy path" of a sale well, but was missing several pieces of foundational plumbing that ERPNext's decade-plus of production use shows are expensive to bolt on after the fact — exactly the risk you flagged wanting to avoid on the first build.

**1. Stock ledger as an append-only log, not a mutable quantity field (US-17, US-18, US-19).**
The original MVP only said "stock levels automatically decrease." That's a field update, not a ledger. Without an underlying log of every individual stock movement (sale, restock, adjustment) with timestamp/reason/user, you cannot answer "why does this product show 7 units instead of 10" — you can only see the current number. This is the single most-cited source of day-2 support pain in real ERPNext deployments (incorrect stock balances). Retrofitting an audit trail onto a system that started with a plain quantity field means migrating or reconstructing history you never captured — effectively impossible to do well after the fact. This has to be the data model from day one, even though the UI can stay as simple as "add product" and "record sale."

**2. A restock/stock-in path, independent of full supplier management (US-17).**
The original MVP explicitly excludes supplier/PO management, which is a reasonable scope cut — but it left *no way for stock to ever increase* after the initial product add. Every real shop restocks constantly. You don't need ERPNext's full Material Request → PO → Receipt chain for v1, but you do need *a* "stock in" entry (quantity, optional cost, optional note), or the low-stock alert (US-3) has nowhere to lead — the owner sees "low stock" and has no in-app action to resolve it.

**3. Void vs. return/credit-note as two distinct flows (US-20, US-21, US-22).**
The original MVP has no mechanism for correcting a sale at all. ERPNext's model — and Kenyan tax law — draws a hard line here: before an invoice reaches KRA, you can void/delete freely; after it's submitted to eTIMS, you cannot edit or delete it, you must issue a credit note that itself gets submitted. Getting this distinction wrong isn't just a UX gap, it's a compliance risk: an app that lets a cashier "just edit" a sale after eTIMS submission could put the shop in violation. This needs to be modeled before the first pilot shop's first mistaken entry, not after.

**4. End-of-day cash-up / session close (US-23, US-24).**
The MVP's fallback design (§8) already allows cash and direct M-Pesa payments alongside STK push — which is good and realistic — but there was no mechanism for the owner to actually reconcile "what should be in the till" against "what's recorded" at the end of a shift. Given that staff accountability and shrinkage were named explicitly in the PRD's problem statement, this is a direct MVP-goal gap, not a nice-to-have: it's the moment where the owner either trusts the system's numbers or doesn't.

**5. Deliberately still deferred, but now explicit rather than silent gaps:**
- **Credit/partial-payment sales ("deni").** Extremely common in Kenyan retail but genuinely a real accounts-receivable subsystem (tracking who owes what, aging, follow-up) — right to defer past MVP, but it should be a known, named risk rather than an oversight, since a pilot shop that regularly extends credit may not get full value from Blendy until this exists.
- **Valuation method (FIFO recommended for retail).** Not needed for MVP's revenue-only reporting, but the moment margin/profit reporting is added (Phase 2), the item cost model needs to already support FIFO lot tracking — bolting this onto stock entries that never recorded a cost per unit will be painful. Recommendation: capture unit cost on every restock entry now, even if MVP reporting doesn't yet use it, so Phase 2 profit reporting doesn't require backfilling.
- **Units of measure.** Fine to defer, but worth flagging for hardware/foodstuff retail specifically (loose/bulk items) as a segment-fit risk if the pilot shop sells by weight or bulk unit.
