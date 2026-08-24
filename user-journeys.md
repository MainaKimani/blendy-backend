# Blendy — User Journeys

**Companion to:** [`endpoints-doc.md`](endpoints-doc.md) (reference) · [`blendy-journeys.postman.json`](blendy-journeys.postman.json) (runnable)
**Status:** every journey below was executed against the API and records its real responses.

---

## What this is for

`endpoints-doc.md` answers *"what does this endpoint do?"*. This answers *"what does a shop actually do, in what order, and what happens when it goes wrong?"* — which is the shape you need to build a frontend against.

There are two Postman collections, and they are not interchangeable:

| File | Organised by | Use it to |
|---|---|---|
| `blendy-suite-v1.json` | endpoint (generated from the schema) | look up a single endpoint |
| `blendy-journeys.postman.json` | **workflow** | run a whole journey unattended |

The journeys collection **chains**: every request captures the ids the next one needs into collection variables, and asserts its own outcome. Open a folder, hit **Run**, and it executes top to bottom. A red step tells you exactly what broke.

### Running it

```bash
python manage.py migrate            # seeds the RBAC catalogue
python manage.py createsuperuser    # needed to onboard a shop

MPESA_WEBHOOK_TOKEN=tok-123 MPESA_WEBHOOK_ENFORCE_IP=false python manage.py runserver
```

The two M-Pesa variables let you play Safaricom by hand. The token becomes part of the callback URL (that *is* the authentication — Safaricom does not sign callbacks), and the IP check is off because a local request does not come from Safaricom's egress ranges.

Then in Postman: import the collection, set `superadmin_email` and `superadmin_password`, and **run J1 first** — it creates the shop, catalogue and stock everything else uses.

```bash
# or, without the GUI
npx newman run blendy-journeys.postman.json \
  --env-var superadmin_email=you@example.com \
  --env-var superadmin_password=...
```

---

## The eight journeys

| # | Journey | Covers | Steps |
|---|---|---|---|
| **J1** | Open a shop | onboarding, catalogue, opening stock | 7 |
| **J2** | Sell, and get paid by STK push | the daily loop, happy path | 4 |
| **J3** | STK fails, customer pays the Till | MVP §8, US-9b/9c — the fallback | 6 |
| **J4** | A direct payment that matches nothing | US-10, the unmatched queue | 2 |
| **J5** | Stock runs low and is replenished | US-3, US-17, US-19 | 6 |
| **J6** | Hire a cashier | US-15, role-based access | 8 |
| **J7** | Guest checkout | the anonymous path | 4 |
| **J8** | Guardrails | every refusal a UI must handle | 7 |

J1 is a prerequisite. J2–J8 are independent of each other.

---

## J1 · Open a shop

Everything a shop needs before it can sell anything.

```
superadmin logs in
  → onboard the shop            → organization_id, owner account, Default Pricelist
  → owner logs in               → access token
  → create a category           → category_id
  → create a product            → product_id, variation_id, price on the pricelist
  → receive opening stock       → ledger entry + balance
```

**1. Onboard** — `POST /api/organization/onboard/` *(superadmin only)*

```json
{
  "organization": { "name": "Mama Duka", "slug": "mama-duka", "mpesa_shortcode": "174379" },
  "user": { "email": "owner@mamaduka.test", "username": "owner", "password": "s3cret" }
}
```

One transaction creates the organization, its `Default Pricelist`, its ORG_ADMIN owner, and enables the built-in roles:

```json
{
  "organization": { "id": "fc7d973e-…", "slug": "mama-duka", "mpesa_shortcode": "174379" },
  "user": { "id": "7d937835-…", "email": "owner@mama-duka.test", "assigned_roles": ["ORG_ADMIN"] }
}
```

> **`organization.id` is the header** every later request sends as `X-Organization`. Set `mpesa_shortcode` now — direct-payment reconciliation attributes incoming money by it, and the "only organization" fallback stops being safe the moment there are two shops.

**2. Log in** — `POST /api/auth/login/` → `{ "access": "…", "refresh": "…", "user_id": "…", "email": "…" }`

**3. Confirm the pricelist** — `GET /api/pricing/pricelists/`

```json
{ "total_items": 1, "results": [
  { "id": "3d199fbc-…", "name": "Default Pricelist", "is_default": true, "is_active": true } ] }
```

Worth checking before going further: **without a pricelist the shop cannot price or sell anything.**

**4. Create a category** — `POST /api/products/categories/` with `{"name": "Groceries"}`.

**5. Create a product** — `POST /api/products/`

```json
{
  "name": "Mumias Sugar",
  "category_id": "{{category_id}}",
  "variations": [
    { "sku": "SUG-1KG", "cost_price": "120.00", "selling_price": "165.00", "reorder_level": 10 },
    { "sku": "SUG-2KG", "cost_price": "230.00", "selling_price": "310.00", "reorder_level": 5 }
  ]
}
```

At least one variation is required and each must carry a `selling_price`. The response comes back with a `price`, not a `selling_price`:

```json
{ "id": "5fa6f429-…", "name": "Mumias Sugar",
  "variations": [ { "id": "9abae6c7-…", "sku": "SUG-1KG",
                    "cost_price": "120.00", "price": "165.00", "reorder_level": 10 } ] }
```

> **The asymmetry is the point.** You *write* `selling_price` and it lands on the pricelist; you *read* `price` and it comes back from there. `cost_price` stays on the variation. The product itself has no price field at all.

**6. Receive opening stock** — `POST /api/inventory/stock/restock/`

```json
{ "product_variation": "{{variation_id}}", "quantity": 50,
  "unit_cost": "120.00", "reference_number": "GRN-0012" }
```

```json
{ "movement": { "movement_type": "STOCK_IN", "quantity": 50, "unit_cost": "120.00" },
  "product_variation": "9abae6c7-…", "available_quantity": 50 }
```

`available_quantity` is recomputed from the ledger rather than read from the cache, so it doubles as a check that the two agree.

---

## J2 · Sell, and get paid by STK push

The daily loop.

```
record the sale       → UNPAID, stock decremented
  → trigger STK push  → PENDING, checkout_request_id
  → Safaricom calls back (ResultCode 0)
  → sale is PAID
```

**1. Record the sale** — `POST /api/sales/sales/`

```json
{ "customer_phone": "0712345678",
  "items": [ { "product_variation": "{{variation_id}}", "quantity": 2, "unit_price": "165.00" } ] }
```

```json
{ "id": "f6f4a9d2-…", "payment_status": "UNPAID", "total_amount": "330.00",
  "items": [ { "product_variation": "…", "quantity": 2,
               "unit_price": "165.00", "cost_price": "120.00",
               "discount": "0.00", "selling_price": "165.00", "total_price": "330.00" } ] }
```

`unit_price` is optional — omit it and the pricelist price applies; supply it and it must match **exactly**. All four price fields are per-unit snapshots frozen at the time of sale, so repricing later never rewrites this sale.

**2. Trigger the push** — `POST /api/payments/payments/`

```json
{ "sale": "{{sale_id}}", "provider": "MPESA", "phone_number": "0712345678", "amount": "330.00" }
```

```json
{ "id": "b8c3a929-…", "status": "PENDING", "amount": "330.00",
  "phone_number": "+254712345678",
  "provider_reference": "ws_CO_220820261414576712345678",
  "merchant_reference": "ff3f-441f-8481-9deb5910d96f396280" }
```

> The push is in flight. **The result arrives on the webhook, not in this response** — a UI should show "waiting for the customer" here, not "paid". Keep `provider_reference` and `merchant_reference`; the callback echoes both back.

**3. Safaricom confirms** — `POST /api/payments/webhooks/mpesa/tok-123/`

```json
{ "Body": { "stkCallback": {
    "MerchantRequestID": "{{merchant_request_id}}",
    "CheckoutRequestID": "{{checkout_request_id}}",
    "ResultCode": 0,
    "CallbackMetadata": { "Item": [
      { "Name": "Amount", "Value": 330.00 },
      { "Name": "MpesaReceiptNumber", "Value": "TGH7YU8KLM" },
      { "Name": "TransactionDate", "Value": 20260822131549 },
      { "Name": "PhoneNumber", "Value": 254712345678 } ] } } } }
```

→ `200 { "detail": "Webhook processed" }`

**4. The sale is PAID** — `GET /api/sales/sales/{{sale_id}}/` → `"payment_status": "PAID"`

> **Try changing `Amount` to `300.00` and re-running step 3.** The sale stays `UNPAID` and the payment is flagged `MISMATCH`. A success callback for the wrong amount never marks a sale paid — that is deliberate, and a UI needs to surface it.

---

## J3 · STK push fails, customer pays the Till

**The journey that matters most in a real shop.** A push failing must never block a sale — the customer is standing there with the goods.

```
sale → STK push → callback FAILS (ResultCode 1032)
  → sale becomes AWAITING_DIRECT_PAYMENT, not FAILED
  → appears in the pending-payments queue
  → customer pays the Till from the M-Pesa menu
  → C2B confirmation matched by phone + amount
  → sale is PAID
```

**3. The push fails** — same webhook, non-zero `ResultCode`:

```json
{ "Body": { "stkCallback": {
    "MerchantRequestID": "{{merchant_request_id}}",
    "CheckoutRequestID": "{{checkout_request_id}}",
    "ResultCode": 1032, "ResultDesc": "Request cancelled by user" } } }
```

**4. The sale is queued, not closed** — `GET /api/sales/sales/pending-payments/`

```json
{ "total_items": 1, "results": [ { "id": "8e35a5ef-…",
    "payment_status": "AWAITING_DIRECT_PAYMENT", "customer_phone": "0712345678" } ] }
```

> `AWAITING_DIRECT_PAYMENT` is deliberately distinct from `FAILED`, which is terminal. The cashier hands over the goods and asks the customer to pay the Till.

**5. The customer pays directly** — `POST /api/payments/webhooks/mpesa-c2b/tok-123/`

```json
{ "TransactionType": "Pay Bill", "TransID": "TGH7YU8KLM",
  "TransTime": "20260822131549", "TransAmount": "330.00",
  "BusinessShortCode": "174379", "MSISDN": "254712345678" }
```

```json
{ "ResultCode": 0, "ResultDesc": "Accepted", "matched": true }
```

A direct payment carries no `CheckoutRequestID`, so it is attributed to a tenant by `BusinessShortCode` and matched to an open sale by **payer phone + amount** within a 24-hour window. Matching is idempotent on `TransID` — re-send it and nothing double-counts.

**6.** `GET /api/sales/sales/{{sale_id}}/` → `"payment_status": "PAID"`

---

## J4 · A direct payment that matches nothing

Money arrives that cannot be tied to an open sale — no candidate, or more than one.

**1.** Same C2B endpoint, a payment nothing is waiting for:

```json
{ "TransID": "NOMATCH001", "TransAmount": "999.00",
  "BusinessShortCode": "174379", "MSISDN": "254799999999" }
```

```json
{ "ResultCode": 0, "ResultDesc": "Accepted", "matched": false }
```

Still `200` in Safaricom's expected shape, so it stops retrying — but `matched` is false.

**2. It waits for a human** — `GET /api/payments/payments/unmatched/`

```json
{ "total_items": 1, "results": [ { "phone_number": "254799999999",
    "amount": "999.00", "checkout_request_id": "", "reconciliation_note": "…" } ] }
```

> **Ambiguity is a refusal, not a guess.** Two candidate sales for the same phone and amount produce an unmatched row, not a coin flip. The `reconciliation_note` says which case it was.

---

## J5 · Stock runs low and is replenished

Stock is a **ledger**, not a number. Every change is an entry; the balance is a cache of those entries, updated in the same transaction under a row lock.

```
sell down → low-stock queue fires → physical count corrects → restock clears it
                                                            → ledger explains all of it
```

**2. The low-stock queue** — `GET /api/inventory/stock/low-stock/`

```json
{ "total_items": 1, "results": [ { "product_variation_id": "e62a1cf3-…",
    "name": "Mumias Sugar", "sku": "SUG-1KG", "location_name": "Main Store",
    "available_quantity": 10, "reorder_level": 10, "shortfall": 0 } ] }
```

The threshold is **inclusive** — selling down *to* it fires the alert, not only going under. Ordered most urgent first. There is no push channel, so this is a queue a dashboard polls.

**3. A physical count** — `POST /api/inventory/stock/adjust/`

```json
{ "product_variation": "{{variation_id}}", "counted_quantity": 8,
  "reason": "Monthly count: two bags damaged" }
```

```json
{ "movement": { "movement_type": "ADJUSTMENT", "quantity": -2,
                "notes": "Monthly count: two bags damaged" },
  "available_quantity": 8 }
```

Send **exactly one** of:

| Field | Meaning |
|---|---|
| `counted_quantity` | The figure on the shelf. The difference is computed under the row lock that writes it, so a sale landing mid-count cannot be silently undone. A count is authoritative, so it *may* produce a negative balance. |
| `quantity` | A signed change (`-2` for two broken bags). Cannot take stock below zero. |

`reason` is **never optional** — an unexplained adjustment is exactly what the ledger exists to rule out.

A count that already matched returns `200` with `"movement": null`: nothing moved, so nothing was written.

**5. The ledger** — `GET /api/inventory/stock-movements/` shows `STOCK_IN`, `SALE` and `ADJUSTMENT` entries that sum to the balance.

**6. It cannot be written directly** — `POST` to the same URL returns **405**. Stock moves through restock, adjust and sale only, so the balance can never drift from the entries that explain it.

---

## J6 · Hire a cashier

US-15: *"staff can record sales without seeing full business reports or being able to edit inventory."*

**1. Which roles the shop has enabled** — `GET /api/authorization/organization-roles/`

Onboarding enables `ORG_ADMIN`, `CASHIER` and `VIEWER`. To enable another, `POST {"role_id": "…"}` — the organization comes from the header, never the body.

**2. Create the cashier** — `POST /api/users/`

```json
{ "email": "till@mamaduka.test", "username": "till", "password": "till-pass",
  "organization_role_ids": ["{{cashier_role_id}}"] }
```

```json
{ "id": "6e9fc1b2-…", "username": "till", "assigned_roles": ["CASHIER"] }
```

**3–7. What the cashier can and cannot do** — all measured:

| Action | Result |
|---|---|
| `POST /sales/sales/` | **201** — records a sale |
| `GET /sales/sales/` | **200** |
| `GET /inventory/stock/low-stock/` | **200** — sees what needs reordering |
| `GET /pricing/pricelist-items/` | **200** — sees what things cost |
| `POST /inventory/stock/restock/` | **403** |
| `POST /pricing/pricelists/` | **403** |
| `DELETE /sales/sales/{id}/` | **403** |

> **Moving stock is the sharpest owner/till line.** A cashier sells stock down but cannot restock or adjust it, so the ledger's write path stays with whoever is accountable for the count.

Permissions held: ORG_ADMIN **87** · CASHIER **18** · VIEWER **6**.

---

## J7 · Guest checkout

A walk-in customer with no account. **Two endpoints stay open to anonymous callers** and nothing else does.

| Step | Result |
|---|---|
| `GET /api/products/` | **200** — browse |
| `POST /api/sales/sales/` | **201** — check out |
| `POST /api/payments/payments/` | **201** — pay |
| `GET /api/sales/sales/` | **401** — cannot read the shop's sales |

> Creating a sale is deliberately **not** permission-gated on any role. A customer at the till holds no role at all, so gating it would close guest checkout.

Anonymous payment creation is rate limited — **5/hour per phone number, 20/hour per IP** — because it fires an STK push at a caller-supplied number. Run step 3 six times to see a `429`.

---

## J8 · Guardrails

Every refusal below is an error state a frontend has to handle. All messages are verbatim.

**1. A price that does not match the pricelist** → `400`

```json
{ "items": "unit_price 100.00 does not match the price 165.00 on 'Default Pricelist' for Mumias Sugar." }
```

Prices are never taken on trust. Any concession must be declared in `discount`, where it stays visible, rather than hidden in a reduced unit price.

**2. Selling more than you hold** → `400`

```json
{ "items": "Insufficient stock for Mumias Sugar: requested 99, available 3." }
```

The whole sale fails — there is no partial fulfilment.

**3. A variation with no price** → `400`

```json
{ "variations": [ { "selling_price": ["This field is required."] } ] }
```

**4. A product with no variations** → `400`. A product with nothing priced is not sellable, so it is refused rather than created.

**5. An anonymous caller discounting themselves** → `400`

```json
{ "items": "A discount may only be applied by a signed-in user." }
```

**6. A missing `X-Organization` header** → `403` on writes. On **reads** it returns an empty page rather than an error — the viewsets fail closed, so a forgotten header looks like an empty shop. Worth knowing before you spend an hour debugging a blank product list.

**7. A webhook with the wrong token** → `401 { "detail": "Invalid MPESA webhook token" }`

---

## Building a frontend against this

**Sequence that has to hold:** organization → pricelist → category → product+prices → stock → sale → payment. Each step produces something the next needs, and skipping one produces a `400` rather than a silent success.

**Three states a payment UI must handle**, because they are genuinely different:

| State | What happened | What the UI should say |
|---|---|---|
| `PENDING` | STK push sent | "Check your phone" — do **not** show paid |
| `PAID` | Callback confirmed, amount matched | Done |
| `AWAITING_DIRECT_PAYMENT` | Push failed | "Pay the Till" — hand over the goods, the match happens later |

**Prices are server-authoritative.** Do not let a till compute a total and post it. Post the variation and quantity, and let the server price it — the response carries the numbers to display.

**Stock can fail a sale at the last moment.** Two tills selling the last unit is a real race; the loser gets a `400`. A confirm button must be able to fail.

---

## What is not here yet

No journey exists for **eTIMS invoicing** or **reporting** — neither is built. Also absent: sale void (US-20), credit notes (US-21/22), and cash-up / session close (US-23/24). See `gap-analysis.md`.

## Regenerating

```bash
python build_journey_collection.py      # blendy-journeys.postman.json
```

Every journey in this document was executed against the API and reflects real responses, not intended ones.
