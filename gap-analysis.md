# Blendy Backend — MVP Gap Analysis

**Status:** Draft v6 — updated after the pricing-authority pass
**Date:** 2026-08-14
**Branch:** `blendy-upgrade`
**Scope:** Backend codebase (Django 5.2 + DRF) assessed against `blendy-mvp.md`, with `blendy-suite-prd.md` for context.

**Legend:** ✅ done · 🟡 partially done · ❌ not started

> **v2 note:** Steps 1–4 of the remediation plan (tenancy, stock ledger, agent-surface removal, M-Pesa hardening) are complete and verified.
>
> **v6 note:** **The pricelist is now authoritative for selling prices.** `Product.price` is gone; prices are held per variation on `PricelistItem`, seeded from a `Default Pricelist` created at onboarding. A product cannot be created without at least one priced variation, and an organization with no pricelist cannot transact at all. Sales record the pricelist used and snapshot both selling price and cost, so repricing never rewrites history. Test suite: **109 passing**.
>
> **v5 note:** **The core POS loop now closes end-to-end,** including low-stock alerts (US-3). Stock can be added and corrected through ledger-backed endpoints (US-17, US-19), the stock ledger is no longer writable via the API, and `available_quantity` is read-only so the cache can no longer drift from the ledger. Sale prices are verified server-side against the catalogue, and pricing is keyed per variation. Test suite: **94 passing**.
>
> **v4 note:** `OrganizationBaseModel` is consolidated and `pricing.PricelistItem` is tenanted — which uncovered a live cross-tenant read leak on `/api/pricing/pricelist-items/`, now closed (see §3.4). Test suite: **55 passing**.
>
> **v3 note:** The **M-Pesa fallback path (§2.1) is now implemented** — direct-payment reconciliation, the `AWAITING_DIRECT_PAYMENT` state, and the US-10 pending queues. Anonymous STK-push rate limiting and `Sale` ordering are also done. Test suite: **50 passing**, up from 4 tests of which 2 were failing at v1. The remaining headline gaps are **eTIMS and reporting**.

---

## 0. Framing

This was not a partially-built retail POS. It was the **Mitchy Fits ecommerce / field-sales-agent backend**, being repurposed toward the Blendy MVP.

Evidence at v1: `SalesAgentProfile`, `AgentInventoryItem`, `IssueStockToAgentView`, warehouse `Location`s, `shipping_*` fields on `Sale`, guest checkout, size/colour variations, and `MPESA_ACCOUNT_REFERENCE` defaulting to `"Mitchy Fits"`.

**Decisions taken since v1** (these are now settled, not open questions):

1. **Sellable unit = `ProductVariation`.** `SaleItem` points at a variation, not a product plus a loose size string.
2. **Keep the ecommerce surface** (products, guest checkout, shipping) — it feeds the POS flow. **Strip the field-sales-agent surface.** Done.
3. **Stock model = ledger + cached balance.** `StockMovement` is the append-only source of truth; `InventoryItem.available_quantity` is a cache maintained in the same transaction (ERPNext's Stock Ledger Entry + Bin pattern).
4. **One default `Location` per organization**, auto-seeded. Multi-branch stays possible without a further migration.
5. **The pricelist is authoritative for selling prices.** `Product` carries no price at all; prices live per variation on `PricelistItem`, on a `Default Pricelist` created at onboarding. No pricelist means no transaction.
6. **Cost stays on the item, not the price list.** `ProductVariation.cost_price` is the standing cost and `StockMovement.unit_cost` records each receipt. Putting cost on `PricelistItem` would have duplicated it once per list with nothing keeping the copies in sync — history is protected by snapshotting onto the sale line instead.

---

## 1. Core MVP features

### 1.1 Working

| Area | Status | Location |
|---|---|---|
| Products / categories / variations CRUD | ✅ | `products/` |
| Product image upload, compression, thumbnails | ✅ | `products/models.py` |
| M-Pesa STK push (real OAuth + `stkpush/v1/processrequest`) | ✅ | `payments/services/providers/mpesa.py` |
| Payment model: status, reconciliation, retry counters, idempotency | ✅ | `payments/models.py` |
| Kenyan phone normalisation + Safaricom prefix validation | ✅ | `payments/serializers.py` |
| **Stock ledger as source of truth** | ✅ **new in v2**, enforced in v5 | `inventory/services.py` |
| **Restock + adjustment endpoints** (US-17, US-19) | ✅ **new in v5** | `inventory/views.py` |
| **Low-stock alerts** (US-3) | ✅ **new in v5** | `inventory/views.py` |
| **Server-side sale price verification** | ✅ **new in v5**, repointed at the pricelist in v6 | `sales/serializers.py` |
| **Pricelist authoritative for selling prices** | ✅ **new in v6** | `pricing/services.py` |
| **Sale decrements stock through the ledger** (US-2, US-18) | ✅ **new in v2** | `sales/serializers.py` |
| **Tenant isolation at the data layer** | ✅ **new in v2** | see §3 |
| **M-Pesa callback authentication + amount validation** | ✅ **new in v2** | see §1.4 |
| RBAC *scaffolding* (roles/permissions models exist) | 🟡 not enforced — see §1.3 | `authorization/models.py` |

### 1.2 Still missing entirely ❌

- **eTIMS — zero code.** No model, service, queue, invoice numbering, or KRA credentials anywhere in the repo. `Organization.tax_number` remains the only related field. **Still the largest single gap.** (US-11, US-12)
- **All reporting.** No aggregation endpoint of any kind. (US-13, US-14)
- ~~**Low-stock alerts.** (US-3)~~ ✅ **done in v5** — `GET /api/inventory/stock/low-stock/`, listing variations at or below their `reorder_level`, most urgent first, with the shortfall. The threshold is **inclusive**: MVP scenario 8 expects selling *down to* the threshold to fire it. Delivered as a pollable queue rather than a push, since there is no mail backend or worker in this deployment.
- ~~**Restock / stock-in endpoint.** (US-17)~~ ✅ **done in v5** — `POST /api/inventory/stock/restock/`, ledger-backed, captures optional `unit_cost` per MVP §10.5.
- ~~**Manual stock adjustment with required reason.** (US-19)~~ ✅ **done in v5** — `POST /api/inventory/stock/adjust/`, accepting either a signed delta or a counted figure, with a mandatory reason.
- **Sale void (pre-eTIMS).** (US-20)
- **Credit note (post-eTIMS).** (US-21, US-22)
- **Cash-up / session close.** (US-23, US-24) — `authentication.UserSession` is a *login* session, not a cashier till session.
- **Receipts.** (US-7)

### 1.3 Partially done 🟡

**Roles are declared but not enforced.** Unchanged from v1:
- No owner/cashier roles are defined or seeded.
- `HasUserPermission` matches `Permission.name` rows that nothing seeds.
- Permission checks remain commented out across `products/views.py` (13 occurrences).

`SaleViewSet` and `PaymentViewSet` *are* now locked down (§1.4), but US-15 — cashier restricted from reports, price edits, and user management — is still enforced nowhere.

### 1.4 M-Pesa — resolved and remaining

**Resolved in v2:**

| Was | Now |
|---|---|
| Signature verification commented out; callback forgeable | Callback moved to `/api/payments/webhooks/mpesa/<token>/`, authenticated by constant-time token compare **and** source-IP allowlist (`payments/services/webhooks/security.py`). HMAC retained as defence-in-depth when the header is present. |
| Callback amount never checked against the sale | Success callback with a mismatched amount no longer marks the sale paid — it goes to `MISMATCH` for review. |
| Malformed payload → 500, causing Safaricom retries | Returns 400. |
| `PaymentViewSet.get_permissions()` returned `[]` | `create` open for guest checkout; all other actions require `IsAuthenticated + IsOrganizationUser`. |
| 2 of 4 payment tests erroring | Suite green; webhook and factory tests rewritten against the current payload shape and `ProviderChargeResult` fields. |

> **Deployment prerequisite.** The webhook will not accept callbacks until `MPESA_WEBHOOK_TOKEN` is set and `MPESA_CALLBACK_URL` is re-registered on the Daraja portal with the matching token path. For sandbox testing through a tunnel, set `MPESA_WEBHOOK_ENFORCE_IP=false`. The Safaricom IP ranges defaulted in `settings.py` should be verified against current Daraja documentation before production use.

**Resolved in v3:**
- `MpesaTransaction.transaction_date` was `auto_now_add`, silently overwriting M-Pesa's real timestamp with our receive time. It is now a plain nullable field populated from the callback (`TransactionDate` on STK, `TransTime` on C2B), parsed from EAT into UTC. Fixed here because window-based reconciliation depends on the real transaction time.
- Anonymous STK-push spam: `create` stays open for guest checkout, but anonymous calls are now rate limited per target phone number and per source IP (`payments/throttles.py`). Authenticated till staff are unthrottled.

**Still open ❌:**
- `MpesaPaymentProvider.parse_webhook_payload` is still dead code with a typo'd key (`"phone_number:"`, `mpesa.py:124`). The view does its own parsing; the method should be deleted or fixed.
- The throttles rely on Django's cache. The default `LocMemCache` is **per-process**, so a multi-worker deployment needs redis/memcached before the limits actually hold.

---

## 2. Fallback logic (MVP §8)

### 2.1 STK failure → direct M-Pesa payment + phone/amount reconciliation ✅ **done in v3**

| Was | Now |
|---|---|
| No "awaiting direct payment" state | `AWAITING_DIRECT_PAYMENT` added to `Sale.PAYMENT_STATUS_CHOICES`. A failed/cancelled STK push moves the sale here instead of `FAILED`, keeping it open. |
| Retries eventually killed the sale | Exhausting retries now cancels the **payment attempt only**; the sale stays open for direct payment (`reconcile_payments.py`). Already-`PAID`/`REFUNDED` sales are left alone. |
| No C2B endpoint | `POST /api/payments/webhooks/mpesa-c2b/<token>/`, authenticated by the same token + IP allowlist as the STK callback. Registered separately with Daraja. |
| No phone+amount matcher | `payments/services/reconciliation.py` matches on tenant + normalised phone + amount + recency, then creates a `SUCCEEDED` `Payment` and marks the sale `PAID`. |
| Unmatched payments dropped | Stored as an unmatched `MpesaTransaction` with a `reconciliation_note` explaining why, and surfaced in the pending queue. |
| No pending queue (US-10) | `GET /api/payments/payments/unmatched/` (inbound money that matched nothing) and `GET /api/sales/sales/pending-payments/` (sales still owed). Both tenant-scoped and authenticated. |

**Matching rules as implemented** (all configurable via settings):

- **Tenant** resolved from `BusinessShortCode` → `Organization.mpesa_shortcode`, falling back to the sole organization while a deployment runs one shared shortcode.
- **Window:** 24h (`MPESA_DIRECT_MATCH_WINDOW_HOURS`).
- **Amount:** exact match, tolerance `0.00` (`MPESA_DIRECT_MATCH_TOLERANCE`).
- **Ambiguity:** reconciles only on exactly one candidate. Two or more leaves the payment unmatched with the candidate IDs recorded — money is never attached to a guessed sale.
- **Idempotent:** a repeated confirmation for the same `TransID` never double-credits.

Covered by 19 tests in `payments/tests_fallback.py`, including the end-to-end path (push fails → retries exhaust → customer pays Till → sale settles).

> Note: matching depends on `Sale.customer_phone` being captured at checkout. A sale recorded without a phone number can never be auto-matched and will always land in the manual queue — worth confirming the POS flow always captures it.

### 2.2 eTIMS failure → queue + background retry ❌

Nothing to queue: no invoice model, no worker.

**No async infrastructure exists** — no Celery, redis, or django-q in `requirements.txt`, and no cron/scheduler config in the repo. The only background mechanism is a management command that must be scheduled externally.

The backoff helper (`payments/services/ops/retry.py`) is generic and reusable for eTIMS but is currently coupled to `Payment`.

---

## 3. Multi-tenant isolation — ✅ resolved

All three v1 failures are fixed, with regression tests.

### 3.1 Tenant columns added ✅

`Sale`, `SaleItem`, `Payment`, `MpesaTransaction`, and `Refund` now inherit `OrganizationBaseModel` — a non-null `organization` FK.

Migrations add the column, backfill, *then* enforce non-null. The backfill infers the tenant in order of reliability (products sold → recording user → sole organization) and **raises rather than guessing** when it cannot resolve one. Verified against a copy of the production database: all 68 existing rows attached to `mitchy-fits`, zero nulls.

`organization` is read-only in every serializer, so a client cannot set it.

### 3.2 Base scoping now fails closed ✅

`OrganizationBaseViewSet.get_queryset` returns `.none()` when the request carries no tenant, instead of an unfiltered cross-tenant queryset. Creation without a tenant raises a clean 403 rather than an `IntegrityError`.

Sale and payment viewsets are wired to this base and additionally require `IsAuthenticated + IsOrganizationUser` for everything except guest-checkout `create`.

### 3.3 Latent `FieldError` resolved ✅

`PaymentViewSet` inherited an `organization` filter for a model that had no such field — breaking payment list/retrieve and `update-status` precisely when the tenant header was supplied correctly. Fixed as a consequence of §3.1.

### 3.4 Structural notes — ✅ resolved in v4

- **`OrganizationBaseModel` consolidated** into `organization/models.py`, the app that owns `Organization`. The three private copies are gone and every tenanted model now inherits the single definition. Verified as a pure no-op at the schema level — abstract bases are not part of migration state, so moving it produced no migration. A test asserts all 13 tenanted models subclass it, so a future model cannot look tenanted without being tenanted.
- **`pricing.PricelistItem` is now tenanted**, with the organization backfilled from its parent pricelist.
  > **Correction to the v3 note:** this was *not* low risk. `PricelistItemViewSet` extended plain `ModelViewSet` with an unscoped `PricelistItem.objects.all()`, and the model is exposed directly at `/api/pricing/pricelist-items/`. Any authenticated user sending a valid header for their own organization could read **every tenant's** pricelist items. Reachability was not limited to going through a tenanted `Pricelist`. The viewset now extends `OrganizationBaseViewSet` and guards the `pricelist` FK against cross-tenant attachment, covered by regression tests.

**Still open 🟡:**

- `Location.code` is globally unique rather than unique-per-tenant. Worked around by suffixing the org slug (`MAIN-<slug>`); worth fixing when multi-branch lands.

---

## 4. Open questions

**Resolved since v1:** sellable unit (→ `ProductVariation`), ecommerce-surface retention (→ keep products/checkout, strip agents), stock source of truth (→ ledger + cache), location strategy (→ one auto-seeded default per org).

**Still open:**

1. **Which eTIMS integration mode — OSCU, VSCU, or the eTIMS API?** Not specified in either planning doc, and no KRA credentials exist. Determines whether eTIMS is a straightforward HTTP client or needs a device/control-unit dependency. **This is now the top blocker.**
2. **What runs the background retry loop in production?** No scheduler is configured, and the §8 fallback design depends on one.
3. **Is `Organization` the shop, or a tenant above shops?** Deferred rather than answered — the one-default-`Location` decision means this does not need resolving until multi-branch.

---

## 5. Sequencing — updated

**Completed (v2):**

1. ✅ Tenant columns on sales/payments + fail-closed scoping
2. ✅ Stock ledger as source of truth, wired to the sale flow
3. ✅ Sales-agent surface removed (sequenced *after* step 2, so a working stock-write path existed throughout)
4. ✅ M-Pesa hardening: callback auth, amount validation, viewset permissions
5. ✅ **M-Pesa fallback reconciliation** (§2.1), anonymous STK-push rate limiting, `Sale` ordering

**Remaining, in recommended order:**

6. **eTIMS from zero** — including the queue + retry path, since §8's degraded-mode design is part of the same build. Blocked on open question §4.1. **Now the single largest gap.**
7. **Reporting** — greenfield, low-risk, unblocked. The ledger makes top/slow-moving products straightforward.
8. ~~**Restock + manual adjustment endpoints, and the low-stock alert**~~ ✅ done in v5. The alert now leads somewhere: an owner sees what is low and restocks it in-app.
9. **Void + credit note** — depends on eTIMS submission state existing first.
10. **Cash-up / session close.**
11. **Role seeding + re-enabling the commented-out permission checks in `products/views.py`.**

---

## 6. Implementation notes from the v2 pass

Decisions made during implementation that are not obvious from the diff:

- **Insufficient stock blocks the sale** (400, whole transaction rolls back), per US-2's "prevent or clearly warn".
- **`StockMovement.quantity` is signed** — negative for outflow — so `SUM(quantity)` is the balance. No pre-existing rows constrained this choice (the table was empty).
- **`SaleItem.product_variation` uses `PROTECT`, not `CASCADE`.** Deleting a variation must never silently delete the sales history that references it, which would make revenue reports lie.
- **Sale edits reverse the previous lines' stock** before applying the new ones, otherwise every edit silently lost inventory. This is **interim**: once eTIMS submission exists, an invoiced sale must be corrected by credit note rather than edited at all (MVP §10.3). There is a comment at that spot in `sales/serializers.py` saying so.
- **One pre-existing bug fixed in passing:** `discount` defaulted to a float `0.00`, raising `TypeError` against a `Decimal` whenever a sale line omitted a discount — sale creation was broken for that case.

### v3 notes

- **Phone normalisation was extracted** from `PaymentSerializer` into `payments/services/phone.py`, because the matcher must compare an inbound MSISDN against a stored sale phone using identical rules. The serializer's behaviour and error messages are unchanged; the service raises `ValueError` and the serializer translates it.
- **`MpesaC2BConfirmationView` returns 200 even when it cannot attribute a payment** to a tenant. Safaricom retries non-2xx responses, and an unknown shortcode is an operator configuration problem that retrying will never fix. The condition is reported in the response body.
- **DRF throttle rates are read per request** (`DynamicRateThrottle`). DRF binds `THROTTLE_RATES` as a class attribute at import time, so configured rates would otherwise be snapshotted at startup and ignored thereafter.

### v6 notes — how pricing works now

**Where prices live**

```
ProductVariation            PricelistItem                 SaleItem (snapshot)
  cost_price  100.00   →      price        150.00    →      unit_price     150.00
  (standing cost)             (per list, per variation)     cost_price     100.00
                                                            discount        10.00
                                                            selling_price  140.00
```

- `Product` has **no price field**. Removed in `products.0003`.
- Prices are supplied per variation at product creation as `selling_price`, and written to the organization's default pricelist. The model field is `PricelistItem.price`; `selling_price` is the payload name only, kept distinct so it does not collide with `SaleItem.selling_price` (which is post-discount).
- `Sale.pricelist` records which list a sale was priced from. Null only on sales predating this change.
- A variation with no entry on the pricelist **cannot be sold**, and an organization with no default pricelist **cannot sell anything**. Both are refused, never defaulted.

**Migration path**, verified against a copy of the production database:
1. `pricing.0006` adds `is_default`, creates a `Default Pricelist` per organization, then copies each variation's price across from its product.
2. `products.0003` drops `Product.price` — sequenced *after* the copy, so the data is safely moved before the column disappears.
3. `sales.0006` adds `Sale.pricelist` and `SaleItem.cost_price`.

Because the old price was per *product*, every variation of a product starts at the same price. Splitting them is an owner action; inventing a per-variation split during migration would have been fabricating data.

**Knock-on changes:** `min_price`/`max_price` filters and `?ordering=price` on `/api/products/` are preserved by repointing them at the pricelist price (`Min` annotation across priced variations) rather than being dropped.

### v5 notes

- **The stock ledger viewset is now read-only** (`GET` only). Left writable, a POST recorded a movement that updated no balance — the exact drift the ledger exists to rule out. Writes go through `inventory.services` only, via the restock and adjust endpoints.
- **`available_quantity` is read-only.** It was the only working way to add stock, and it wrote no ledger entry, so cache and ledger diverged on first use.
- **A counted adjustment computes its delta inside the row lock**, so a sale landing between the count being read and applied cannot be silently reverted.
- **Restock/adjust require authentication** but are not yet owner-only. Narrowing them to a role awaits the RBAC seeding work, since `HasUserPermission` matches `Permission` rows that nothing currently creates — gating on it today would 403 every caller.

### Known minor issues, not addressed

- `settings.py` still hardcodes `SECRET_KEY` and `DEBUG = True` with `ALLOWED_HOSTS = ["*"]`. Out of scope here, but must be resolved before any pilot deployment.
- The default `LocMemCache` makes throttling per-process; a shared cache backend is needed in production.
