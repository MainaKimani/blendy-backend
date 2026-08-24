# Blendy Backend — API Documentation

**Version:** v1 · **Base path:** `/api` · **Branch:** `blendy-upgrade`
**Interactive:** `/api/swagger/` (Swagger UI) · `/api/redoc/` · `swagger.json` (OpenAPI 2.0)
**Postman:** `blendy-suite-v1.json`

---

## Part 1 — What this backend does

Blendy is a **point-of-sale and inventory system for Kenyan retail SMEs** — a shop owner runs a till, tracks stock, and takes M-Pesa payments. This service is the backend for that.

It is **multi-tenant**: one deployment serves many shops, and every piece of data belongs to exactly one organization.

### What it does today

| Capability | Notes |
|---|---|
| **Catalogue** | Products, categories, variations, images, units of measure, currencies |
| **Pricing** | Pricelists as the single source of selling prices |
| **Stock** | An append-only ledger with a cached balance, restock and adjustment endpoints, low-stock alerts |
| **Sales** | Till and guest-checkout sales, priced and verified server-side against the pricelist |
| **Payments** | M-Pesa STK push, plus reconciliation of direct Till payments when a push fails |
| **Identity** | JWT auth, organizations, users, and a role/permission model |
| **Platform** | An HQ organization whose staff can support any shop, with every crossing on the record |

### What it does not do yet

- **eTIMS** — no KRA invoicing. The largest remaining gap.
- **Reporting** — no sales or margin reports (US-13/14). The data to build them is recorded; the endpoints are not written.
- **Void, credit note, cash-up** (US-20 to US-24).
- **Reports themselves** — the `reports.*` permissions exist so a cashier can be denied them, but no reporting endpoint is written yet.

### The five ideas worth understanding first

**1. Tenancy travels in a header.** Every tenant-scoped request carries `X-Organization: <organization-uuid>`. Middleware resolves it; the viewsets **fail closed**, so a request without it reads back an empty list rather than another tenant's data.

**2. The sellable unit is the variation, not the product.** "Mumias Sugar" is a product; "Mumias Sugar 1kg" is a `ProductVariation`. Stock is held against variations, prices are set against variations, and a sale line points at a variation.

**3. The pricelist is authoritative.** A product carries no price. Every organization gets a `Default Pricelist` at onboarding, and prices live on it as `PricelistItem` rows. **An organization without a pricelist cannot transact at all**, and a variation with no entry on the list cannot be sold. A sale records which pricelist it used and snapshots the prices, so repricing never rewrites history.

**4. Stock is a ledger, not a number.** `StockMovement` is append-only and is the source of truth; `InventoryItem.available_quantity` is a cache updated in the same transaction under a row lock. The ledger endpoint is **read-only** — stock moves only through the restock, adjust and sale paths, so the balance can never drift from the entries that explain it.

**5. A failed STK push does not close the sale.** It moves to `AWAITING_DIRECT_PAYMENT`, and if the customer pays the Till directly, the C2B webhook matches that payment back to the sale by phone number and amount. Anything it cannot match unambiguously is queued for a human rather than guessed at.

---

## Part 2 — Conventions

### Authentication

```http
POST /api/auth/login/
Content-Type: application/json

{ "email": "owner@mamaduka.co.ke", "password": "s3cret" }
```

Returns `access` and `refresh` tokens, plus `user_id` and `email`. Send the access token on every subsequent request:

```
Authorization: Bearer <access>
```

`POST /api/token/refresh/` exchanges a refresh token for a new access token.

**Two endpoints stay open to anonymous callers**, so a customer can check out without an account: creating a sale, and creating a payment against it. Anonymous payment creation is rate-limited by phone number and IP, because it triggers an STK push to a caller-supplied number.

### Tenancy

```
X-Organization: edd08673-f90e-45d0-838d-00066e3ec92a
```

Required on everything except `/auth/`, `/token/`, `/organization/`, `/users/register/`, the global `/authorization/permissions/` and `/authorization/roles/` catalogues, and the M-Pesa webhooks.

Omitting it does **not** produce a clear error on reads — the queryset resolves to no tenant and returns an empty page. On writes it is a `403`.

### Pagination

Every list response has the same envelope:

```json
{
  "links": { "next": null, "previous": null },
  "total_items": 1,
  "total_pages": 1,
  "current_page": 1,
  "page_size": 20,
  "results": [ ... ]
}
```

Controlled with `?page=` and `?page_size=` (max 100). Note the count is `total_items`, not DRF's usual `count`.

### Errors

| Status | Meaning |
|---|---|
| `400` | Validation failed. Body is `{"field": ["message"]}` or `{"field": "message"}`. |
| `401` | Missing, expired or invalid JWT. |
| `403` | Authenticated but not permitted — including a missing or mismatched `X-Organization`. |
| `404` | Not found **or** belongs to another tenant. The two are deliberately indistinguishable. |
| `405` | The method is not allowed on this endpoint (the stock ledger and role assignments are read-only). |
| `429` | Rate limit — anonymous payment creation only. |

### Types

Ids are UUIDs. Money is a **string** with two decimals (`"165.00"`), never a float. Timestamps are ISO-8601 UTC.

---

## Part 3 — Getting started

The order matters: each step produces something the next one needs.

```
1. POST /api/organization/onboard/     → organization id + owner  (superadmin only)
2. POST /api/auth/login/               → access token
3. POST /api/products/categories/      → category id
4. POST /api/products/                 → product + priced variations
5. POST /api/inventory/stock/restock/  → stock on hand
6. POST /api/sales/sales/              → a sale
7. POST /api/payments/payments/        → STK push to the customer
```

Steps 1 and 2 are once per shop. Steps 3–5 are setup. Steps 6–7 are the daily loop.

---

## Part 4 — Endpoint reference

Every example below is a **real** request and response captured from the running API.

### 4.1 Organizations

#### `POST /api/organization/onboard/` — create a shop
Superadmin only. Creates the organization, its `Default Pricelist`, and its ORG_ADMIN user in one transaction.

**Request**
```json
{
  "organization": { "name": "Mama Duka", "slug": "mama-duka" },
  "user": {
    "email": "owner@mamaduka.co.ke",
    "username": "owner",
    "password": "s3cret",
    "first_name": "Amina"
  }
}
```

**`201`**
```json
{
  "organization": {
    "id": "edd08673-f90e-45d0-838d-00066e3ec92a",
    "name": "Mama Duka",
    "slug": "mama-duka",
    "mpesa_shortcode": null,
    "subscription_plan": "FREE",
    "status": "ACTIVE",
    "created_at": "2026-08-22T10:15:47.159812Z"
  },
  "user": {
    "id": "7b524d12-272e-47ec-8963-dd5a2cfdcaa1",
    "username": "owner",
    "email": "owner@mamaduka.co.ke",
    "organization": "edd08673-f90e-45d0-838d-00066e3ec92a",
    "assigned_roles": ["ORG_ADMIN"]
  }
}
```

The `organization.id` is what every later request sends as `X-Organization`.

> **Set `mpesa_shortcode`** before onboarding a second shop. Direct-payment reconciliation attributes an incoming C2B payment by shortcode, and falls back to "the only organization" when it is unset — a fallback that stops being safe the moment there are two.

| Endpoint | Method | Notes |
|---|---|---|
| `/organization/` | `GET` `POST` | Superadmin. A create here also gets a `Default Pricelist`. |
| `/organization/{id}/` | `GET` `PUT` `PATCH` `DELETE` | Superadmin or org admin. |

### 4.2 Catalogue

#### `POST /api/products/categories/`

**Request** `{ "name": "Groceries", "description": "Dry goods" }`

**`201`**
```json
{
  "id": "5a23d66c-17d7-47ff-a709-5a398c0aa587",
  "name": "Groceries",
  "description": "Dry goods",
  "is_active": true,
  "organization": "edd08673-f90e-45d0-838d-00066e3ec92a"
}
```

#### `POST /api/products/` — create a product with its priced variations

**At least one variation is required, and every variation must carry a `selling_price`.** A product with no priced variation is not sellable, so it is refused rather than created.

`cost_price` stays on the variation. `selling_price` is written to the organization's `Default Pricelist` — it is **not** a field on the variation.

**Request**
```json
{
  "name": "Mumias Sugar",
  "description": "Refined white sugar",
  "category_id": "5a23d66c-17d7-47ff-a709-5a398c0aa587",
  "variations": [
    { "sku": "SUG-1KG", "cost_price": "120.00", "selling_price": "165.00",
      "measurement": "1.0", "reorder_level": 10 },
    { "sku": "SUG-2KG", "cost_price": "230.00", "selling_price": "310.00",
      "measurement": "2.0", "reorder_level": 5 }
  ]
}
```

**`201`** (abridged)
```json
{
  "id": "9eeca18b-7c0b-48f5-864c-de3cd93c5671",
  "name": "Mumias Sugar",
  "category": { "id": "5a23d66c-...", "name": "Groceries", "...": "..." },
  "variations": [
    {
      "id": "20063147-c9a6-4f8b-bd18-6522b6f424d3",
      "name": "Mumias Sugar-1.00",
      "sku": "SUG-1KG",
      "cost_price": "120.00",
      "price": "165.00",
      "reorder_level": 10,
      "product_id": "9eeca18b-7c0b-48f5-864c-de3cd93c5671"
    }
  ],
  "images": [], "available_sizes": [], "primary_image": null
}
```

Note the asymmetry: you **write** `selling_price`, you **read** `price`. The write goes to the pricelist; the read comes back from it. `name` is derived from the product name, pack size, colour, size and unit.

**`400` — an unpriced variation**
```json
{ "variations": [ { "selling_price": ["This field is required."] } ] }
```

| Endpoint | Method | Notes |
|---|---|---|
| `/products/` | `GET` | Filter `?category=`, `?min_price=`, `?max_price=`, `?is_active=`; search `?search=`; sort `?ordering=price\|-created_at`. **Open to anonymous callers.** |
| `/products/{id}/` | `GET` `PUT` `PATCH` `DELETE` | |
| `/products/with-price/?pricelist_id=` | `GET` | Prices resolved against a *named* list instead of the default. Unpriced variations come back `null` — they do not inherit a sibling's price. |
| `/products/variations/` | `GET` `POST` | `POST` accepts a single object or a list. Requires `product_id` and `selling_price`. |
| `/products/images/` | `GET` `POST` | Multipart. Compression and thumbnails are automatic. |
| `/products/categories/`, `/products/uoms/`, `/products/currencies/` | full CRUD | |

### 4.3 Pricing

| Endpoint | Method | Notes |
|---|---|---|
| `/pricing/pricelists/` | full CRUD | `Default Pricelist` is flagged `is_default`, not matched by name — renaming it is safe. |
| `/pricing/pricelist-items/` | full CRUD | One price per (pricelist, variation). |

**`POST /api/pricing/pricelist-items/`**
```json
{ "pricelist": "<pricelist-uuid>", "product_variation": "<variation-uuid>", "price": "180.00" }
```

Attaching an item to another tenant's pricelist is a `403`, not a silent success.

> Gated behind `pricing.*` permissions. ORG_ADMIN holds them; CASHIER holds only the `view_` half — see [Roles and permissions](#48-roles-and-permissions).

### 4.4 Inventory

Stock only ever moves through the two write endpoints below. The ledger itself is read-only.

#### `POST /api/inventory/stock/restock/` — stock arriving (US-17)

**Request**
```json
{
  "product_variation": "20063147-c9a6-4f8b-bd18-6522b6f424d3",
  "quantity": 50,
  "unit_cost": "120.00",
  "reference_number": "GRN-0012",
  "notes": "Opening stock"
}
```

**`201`**
```json
{
  "movement": {
    "id": "d938d6fd-4047-43a5-ab63-6b238a1f728a",
    "movement_type": "STOCK_IN",
    "quantity": 50,
    "unit_cost": "120.00",
    "reference_number": "GRN-0012",
    "notes": "Opening stock",
    "location": "29015fdf-d669-48dc-bfa4-feac7d63b3dc",
    "created_by": "7b524d12-272e-47ec-8963-dd5a2cfdcaa1"
  },
  "product_variation": "20063147-c9a6-4f8b-bd18-6522b6f424d3",
  "available_quantity": 50
}
```

`quantity` is always positive here. `location` is optional — omitting it uses the organization's default, created automatically. `available_quantity` is recomputed **from the ledger**, not read from the cache, so it doubles as a check that the two agree.

#### `POST /api/inventory/stock/adjust/` — correct a figure (US-19)

Send **exactly one** of:

- `quantity` — a signed change (`-2` for two broken bags). Cannot take the balance below zero.
- `counted_quantity` — the figure counted on the shelf. The difference is computed under the same row lock that writes it, so a sale landing mid-count cannot be silently undone. A count is authoritative, so it *may* produce a negative balance.

`reason` is **required**. An unexplained adjustment is precisely what the ledger exists to rule out.

**Request** `{ "product_variation": "2006...", "counted_quantity": 48, "reason": "Monthly count: two bags damaged" }`

**`201`**
```json
{
  "movement": {
    "movement_type": "ADJUSTMENT",
    "quantity": -2,
    "notes": "Monthly count: two bags damaged"
  },
  "product_variation": "20063147-c9a6-4f8b-bd18-6522b6f424d3",
  "available_quantity": 48
}
```

**`200`** with `"movement": null` when the count already matched — nothing moved, so nothing was written.

#### `GET /api/inventory/stock/low-stock/` — the reorder queue (US-3)

Variations at **or below** their `reorder_level`. The threshold is inclusive: selling *down to* it fires the alert, not only going under.

**`200`**
```json
{
  "total_items": 1,
  "results": [
    {
      "product_variation_id": "20063147-c9a6-4f8b-bd18-6522b6f424d3",
      "name": "Mumias Sugar-1.00",
      "sku": "SUG-1KG",
      "location_name": "Main Store",
      "available_quantity": 0,
      "reorder_level": 10,
      "shortfall": 10
    }
  ]
}
```

Most urgent first. There is no push channel in this deployment, so this is a queue a dashboard polls, in the same shape as the two payment queues.

| Endpoint | Method | Notes |
|---|---|---|
| `/inventory/stock-movements/` | `GET` **only** | The ledger. `POST` returns `405` — a movement that changed no balance is the drift this design rules out. |
| `/inventory/inventory-items/` | `GET` `POST` `PUT` `PATCH` `DELETE` | `available_quantity` is **read-only**; write to it through the endpoints above. |
| `/inventory/locations/` | full CRUD | One default location per organization, auto-created. |
| `/inventory/stock-takes/`, `/inventory/stock-take-items/` | full CRUD | Scaffolding; not wired to the ledger yet. |

### 4.5 Sales

#### `POST /api/sales/sales/` — record a sale

**Open to anonymous callers** (guest checkout). Creating a sale decrements stock through the ledger in the same transaction; insufficient stock fails the whole sale.

**Request**
```json
{
  "customer_phone": "0712345678",
  "items": [
    { "product_variation": "20063147-c9a6-4f8b-bd18-6522b6f424d3",
      "quantity": 2, "unit_price": "165.00" }
  ]
}
```

`unit_price` may be omitted — it then defaults to the pricelist price. If supplied it must match **exactly**.

**`201`**
```json
{
  "id": "291c9e5c-0d5b-4022-97c2-f78a18d0d4bf",
  "sale_date": "2026-08-22T10:15:47.489699Z",
  "status": "PENDING",
  "payment_status": "UNPAID",
  "customer_phone": "0712345678",
  "shipping_fee": "0.00",
  "items": [
    {
      "id": "b46b2ad2-c7c2-4351-a7cc-0be594de2783",
      "product": "9eeca18b-7c0b-48f5-864c-de3cd93c5671",
      "product_variation": "20063147-c9a6-4f8b-bd18-6522b6f424d3",
      "quantity": 2,
      "unit_price": "165.00",
      "cost_price": "120.00",
      "discount": "0.00",
      "selling_price": "165.00",
      "total_price": "330.00"
    }
  ],
  "payments": [],
  "total_amount": "330.00"
}
```

**The four price fields on a line, all per unit and all snapshots:**

| Field | Meaning |
|---|---|
| `unit_price` | The pricelist price at the time of sale. Must match the list exactly. |
| `discount` | The concession granted. Defaults to `0.00`. |
| `selling_price` | What was actually charged. Must equal `unit_price - discount` exactly. |
| `cost_price` | What the item cost, copied from the variation. |

`total_price` is `quantity × selling_price`. All four are frozen at the time of sale, so later repricing never rewrites a past sale — which is what makes historic margin computable.

**Discounts.** Any concession must be declared in `discount`, where it stays visible, rather than hidden in a reduced `unit_price`. A discount **may only be applied by a signed-in user** — guest checkout stays open but cannot grant itself money off.

```json
{ "items": [ { "product_variation": "2006...", "quantity": 1,
               "unit_price": "165.00", "discount": "15.00",
               "selling_price": "150.00" } ] }
```

**`400` — price does not match the list**
```json
{ "items": "unit_price 100.00 does not match the price 165.00 on 'Default Pricelist' for Mumias Sugar-1.00." }
```

Other refusals, all `400`: a variation with no price on the list; an organization with no default pricelist; a discount exceeding the unit price; a `selling_price` that does not equal `unit_price - discount`; insufficient stock.

#### `GET /api/sales/sales/pending-payments/` — money still owed (US-10)

Sales whose `payment_status` is `AWAITING_DIRECT_PAYMENT` (an STK push failed and the customer was asked to pay the Till) or `UNPAID`. Same envelope as the sale listing.

| Endpoint | Method | Notes |
|---|---|---|
| `/sales/sales/` | `GET` | Authenticated. Newest first. |
| `/sales/sales/{id}/` | `GET` `PUT` `PATCH` `DELETE` | Editing the lines returns the old lines' stock to the ledger first. |
| `/sales/sale-items/` | full CRUD | |

**`payment_status` values:** `UNPAID` · `AWAITING_DIRECT_PAYMENT` · `PAID` · `FAILED` · `CANCELLED` · `REFUNDED`.
`AWAITING_DIRECT_PAYMENT` is deliberately distinct from `FAILED`, which is terminal.

### 4.6 Payments

#### `POST /api/payments/payments/` — trigger an STK push

**Open to anonymous callers**, and rate-limited when anonymous: 5/hour per phone number, 20/hour per IP (configurable via `THROTTLE_STK_PUSH_PHONE` / `THROTTLE_STK_PUSH_IP`). Authenticated till staff are not throttled.

**Request**
```json
{ "sale": "291c9e5c-0d5b-4022-97c2-f78a18d0d4bf",
  "provider": "MPESA", "phone_number": "0712345678", "amount": "330.00" }
```

`amount` must equal the sale total. Phone numbers are normalised to `+254…` and validated against known Safaricom prefixes. `Idempotency-Key` is honoured as a request header for safe retries.

**`201`**
```json
{
  "id": "1f58c5e1-79b4-4e8f-b0b1-1943aa641a1a",
  "provider": "MPESA",
  "status": "PENDING",
  "amount": "330.00",
  "currency": "KES",
  "phone_number": "+254712345678",
  "provider_reference": "ws_CO_220820261315488712345678",
  "merchant_reference": "ff3f-441f-8481-9deb5910d96f385984",
  "idempotency_key": "48677cb424f444d68b647349d88f2326",
  "reconciliation_status": "PENDING",
  "retry_count": 0, "max_retries": 5,
  "sale": "291c9e5c-0d5b-4022-97c2-f78a18d0d4bf",
  "transactions": []
}
```

The push is now in flight. The result arrives on the webhook below, not in this response.

#### `POST /api/payments/webhooks/mpesa/{token}/` — STK result

**Called by Safaricom, not by your clients.** Safaricom does not sign callbacks, so the trust boundary is the secret `{token}` in the URL plus a source-IP allowlist. The token must match `MPESA_WEBHOOK_TOKEN` and the callback URL registered with Daraja.

```json
{ "Body": { "stkCallback": {
    "MerchantRequestID": "ff3f-441f-...",
    "CheckoutRequestID": "ws_CO_2208...",
    "ResultCode": 0,
    "ResultDesc": "The service request is processed successfully.",
    "CallbackMetadata": { "Item": [
      { "Name": "Amount", "Value": 330.00 },
      { "Name": "MpesaReceiptNumber", "Value": "TGH7YU8KLM" },
      { "Name": "TransactionDate", "Value": 20260822131549 },
      { "Name": "PhoneNumber", "Value": 254712345678 }
    ] } } } }
```

| Outcome | Effect |
|---|---|
| `ResultCode: 0`, amount matches | Payment `SUCCEEDED`, sale `PAID`, `reconciliation_status: MATCHED` |
| `ResultCode: 0`, amount **differs** | Payment stays `PENDING`, sale stays `UNPAID`, flagged `MISMATCH`. **A success callback for the wrong amount never marks a sale paid.** |
| Anything else | Payment `FAILED`, sale → `AWAITING_DIRECT_PAYMENT` so it stays open for a direct Till payment |

Responses: `200` processed · `400` malformed (returned rather than a `500`, so Safaricom stops retrying) · `401` bad token or IP · `404` no matching payment.

#### `POST /api/payments/webhooks/mpesa-c2b/{token}/` — direct Till payment (US-9c)

Registered separately with Daraja. A direct payment has no `CheckoutRequestID`, so it is attributed to a tenant by `BusinessShortCode` and matched to an open sale by **payer phone number + amount**, within a 24-hour window (`MPESA_DIRECT_MATCH_WINDOW_HOURS`).

```json
{ "TransID": "TGH7YU8KLM", "TransAmount": "330.00", "MSISDN": "254712345678",
  "BusinessShortCode": "174379", "TransTime": "20260822131549" }
```

Always answers `200` in Safaricom's expected shape, with `"matched": true|false`. Matching is idempotent on `TransID`. **Zero candidates or more than one is a refusal, not a guess** — the payment lands on the unmatched queue with a note saying which.

#### `GET /api/payments/payments/unmatched/` — money that arrived but did not land

Direct payments that could not be tied to a sale. Nothing is dropped; each waits here with its `reconciliation_note` for an owner to reconcile by hand.

| Endpoint | Method | Notes |
|---|---|---|
| `/payments/payments/` | `GET` | Authenticated. |
| `/payments/payments/{id}/update-status/` | `POST` | Manual override: `{"status": "SUCCEEDED"}`. Moves the sale with it. |
| `/payments/refunds/` | full CRUD | Cannot exceed the payment amount. |

### 4.7 Authentication and users

| Endpoint | Method | Notes |
|---|---|---|
| `/auth/login/` | `POST` | `{email, password}` → `{access, refresh, user_id, email}` |
| `/token/refresh/` | `POST` | `{refresh}` → `{access}` |
| `/auth/password-change/`, `/auth/password-reset/` | `POST` | |
| `/auth/sessions/` | full CRUD | Session records. |
| `/users/` | `GET` `POST` | Admin only. Pass `organization_role_ids` to assign roles. |
| `/users/{id}/` | `GET` `PUT` `PATCH` `DELETE` | `PATCH` with `organization_role_ids` replaces the user's roles. |
| `/users/register/` | `POST` | Self-registration; needs `X-Organization`. |
| `/authorization/permissions/`, `/authorization/roles/` | full CRUD | **Global** catalogues, superadmin only. |
| `/authorization/organization-roles/` | `GET` `POST` `PUT` `PATCH` `DELETE` | Which roles a shop has enabled. The **only** way to link a role to an organization. |
| `/authorization/user-role-assignments/` | `GET` **only** | Who holds what. Read-only: assignment happens via `/users/`. |

See [4.8](#48-roles-and-permissions) for what the built-in roles hold. **Enabling a role for a shop, then assigning it:**

```http
POST /api/authorization/organization-roles/
{ "role_id": "<role-uuid>" }
```
The organization comes from the header, never the body. Enabling the same role twice returns `400`, not a `500`.

```http
PATCH /api/users/<user-id>/
{ "organization_role_ids": ["<organization-role-uuid>"] }
```

### 4.8 Roles and permissions

Access is `Permission` → `Role` → `OrganizationRole` → `UserRoleAssignment` → user. Permissions and roles are **global**; enabling a role for a shop and assigning a user to it are **per-organization**. A user's permissions are always resolved within their own organization, so holding CASHIER at one shop grants nothing at another.

The catalogue lives in `authorization/rbac.py` and is applied by migration. Re-apply after editing it:

```bash
python manage.py seed_rbac        # idempotent
```

#### Built-in roles

All three are enabled for every organization at onboarding, so an owner can hire a cashier without first enabling the role, and self-registration always has a role to assign.

| Role | Holds | Purpose |
|---|---|---|
| `ORG_ADMIN` | all 83 permissions | The shop owner. Full access **within their own organization**. |
| `CASHIER` | 18 permissions | Records sales and takes payment (US-15). |
| `VIEWER` | 6 permissions | Browses the catalogue. Assigned automatically by self-registration. |

**ORG_ADMIN is derived from the catalogue, not listed.** A permission added and forgotten in a hand-written list would lock the owner out of their own shop, which is the failure this seeding exists to fix.

**What a cashier can do:** create and view sales and sale lines; create and view payments; view products, variations, categories, images, units and currencies; **view** pricelists and prices; view stock balances, the ledger, locations, and the low-stock queue.

**What a cashier cannot do**, per US-15's acceptance criteria — *"record sales and view current stock, but not access revenue reports, edit product prices, or manage other users"*:

| Denied | Why |
|---|---|
| `pricing.add/change/delete_*` | A cashier must see what something costs to sell it, and must not be able to change it. |
| `products.change_*`, `products.delete_*` | Catalogue is the owner's. |
| `users.*`, `authorization.*` | No staff management. |
| `reports.view_sales_report`, `reports.view_margin_report` | Declared before the endpoints exist, because the restriction is defined by what a cashier must **not** hold — you cannot withhold a permission that has no name. |
| `sales.void_sale` | A void reverses a sale and its stock; that is an owner's decision (US-20). |
| `inventory.restock_stock`, `inventory.adjust_stock` | Moving stock is not a till action. |

#### VIEWER, and why it holds so little

`POST /api/users/register/` is open to anonymous callers and needs only an organization id, so **anyone who learns a shop's UUID can obtain this role.** Its scope is set by that fact rather than by what "viewer" might mean elsewhere.

It holds the six `products.view_*` permissions and nothing else. Deliberately excluded:

| Excluded | Why |
|---|---|
| Sales, payments, stock | A self-registered stranger must not read the shop's takings or stock position. |
| **Pricelists** | Tempting to include, since `/api/products/` already exposes prices anonymously — but only from the **default** list. A shop running a second list (wholesale, staff) would leak it through `/api/pricing/pricelist-items/`. |

What remains is the catalogue, which `/api/products/` already serves anonymously. **VIEWER therefore grants nothing that is not already public** — it exists so registration's role assignment does what it says, and becomes meaningful the moment catalogue reads are gated.

Before seeding, `RegisterView` looked up the literal name `"Viewer"` and swallowed `Role.DoesNotExist`, so every self-registered user ended up with no role at all and that code had never once run. It now references the `VIEWER` constant, so a rename in the catalogue cannot break it silently again.

#### Effective access

Measured, not asserted — this is the real response of each endpoint to each role.

|  | OWNER | CASHIER | VIEWER | anonymous |
|---|---|---|---|---|
| `GET /products/` | 200 | 200 | 200 | 200 |
| `POST /sales/sales/` *(checkout)* | 201 | 201 | 201 | **201** |
| `GET /sales/sales/` | 200 | 200 | 403 | 401 |
| `GET /inventory/inventory-items/` | 200 | 200 | 403 | 401 |
| `GET /inventory/stock/low-stock/` | 200 | 200 | 403 | 401 |
| `POST /inventory/stock/restock/` | 201 | **403** | 403 | 401 |
| `GET /pricing/pricelist-items/` | 200 | 200 | 403 | 401 |
| `POST /pricing/pricelists/` | 201 | 403 | 403 | 401 |

Permissions held: OWNER 87 · CASHIER 18 · VIEWER 6 · anonymous 0.

**Creating a sale is deliberately not permission-gated**, on any role. A customer at the till holds no role at all, so gating it would close guest checkout. Everything that *reads* or *mutates* an existing sale is gated.

Moving stock is the clearest line between owner and till: a cashier sells stock down but cannot restock or adjust it, so the ledger's write path stays with the person accountable for the count.

#### Permission names

`app.action_model`, matching Django's convention: `pricing.view_pricelist`, `sales.add_sale`. Beyond CRUD there are seven named actions — `inventory.restock_stock`, `inventory.adjust_stock`, `inventory.view_lowstock`, `payments.reconcile_payment`, `sales.void_sale`, `reports.view_sales_report`, `reports.view_margin_report`.

**Where permissions are enforced:** the sales, inventory and pricing endpoints check them. Products stay open (anonymous browsing is intentional), and payments gate on membership alone for now. A permission no view checks is **inert, not wrong** — `reports.*` and `sales.void_sale` exist so roles can be defined against features that are not built yet.

#### Superadmins bypass everything

`is_superuser` or `is_superuser_admin` short-circuits the check before any role is consulted. Platform operators are not modelled as a role.

#### Adding a custom role

```http
POST /api/authorization/organization-roles/     { "role_id": "<role-uuid>" }
PATCH /api/users/<user-id>/                     { "organization_role_ids": ["<organization-role-uuid>"] }
```

The `Role` itself is global and superadmin-managed (`/api/authorization/roles/`); enabling it for a shop and assigning staff to it are the owner's.

### 4.9 Platform (HQ)

Blendy's own staff work from an **HQ organization** — a real `Organization` flagged `is_platform`, so platform roles run through the same RBAC a shop's staff use rather than a second, parallel system.

HQ is **not** a customer: it is absent from `GET /api/organization/`, gets no default pricelist, and never has `CASHIER` or `VIEWER` enabled. There can only be one; a partial unique constraint enforces that in the database.

```bash
python manage.py bootstrap_hq                       # creates HQ, prints its id
python manage.py bootstrap_hq --promote you@blendy.test
```

#### `GET /api/organization/platform/`

HQ's id, without going to the shell. Platform staff need it to send as
`X-Organization` when working on HQ itself — managing their own accounts, for
instance.

```json
{ "id": "4447d480-…", "name": "Blendy HQ", "slug": "blendy-hq", "is_platform": true }
```

Open to **any** holder of a `platform.*` permission, not only administrators: a
support agent needs the id as much as an admin does, and gating it on the
superadmin flag would send them back to the shell. A shop's `ORG_ADMIN` holds
all 87 tenant permissions and no platform one, so it is a `403` for them.

`404` with a pointer to `bootstrap_hq` when no HQ exists.

#### Platform roles

| Role | Holds | Can |
|---|---|---|
| `SUPPORT_AGENT` | 24 | Read **any** organization. Change nothing. |
| `PLATFORM_ADMIN` | 92 | Everything above, plus write, onboard shops, manage staff, read the access log. |

`SUPPORT_AGENT` is read-only without any read-only code: it holds `platform.access_tenants` plus the tenant `view_*` set and **no** write permission, so the ordinary per-action checks refuse writes on their own.

#### Platform permissions

| | |
|---|---|
| `platform.access_tenants` | the gate — read an organization you are not in |
| `platform.act_as_tenant` | write to it; deliberately a second, separate grant |
| `platform.onboard_organization` | create a customer |
| `platform.manage_platform_staff` | add and remove Blendy staff |
| `platform.view_access_log` | see who accessed what, across every organization |

The tenant-facing counterpart, `organization.view_access_log`, is a **tenant** permission — held by `ORG_ADMIN` by derivation, and scoped to that shop's own rows.

**No tenant role holds any of these.** `ORG_ADMIN` is derived from the *tenant* pool only — were it derived from the whole catalogue, every shop owner would silently gain `access_tenants` and with it read access to every other shop.

#### Crossing into a tenant

Platform staff still send `X-Organization: <the shop>`. Three ways in:

1. **Membership** — ordinary shop users.
2. **`platform.access_tenants`** — reads; writes additionally need `platform.act_as_tenant`.
3. **`is_superuser_admin`** — retained as break-glass, in the spirit of Django's `is_superuser`.

Without a header it still fails closed: platform staff must name the shop they are entering.

Measured:

|  | OWNER | SUPPORT | PLATFORM_ADMIN | superadmin |
|---|---|---|---|---|
| `GET /sales/sales/` | 200 | **200** | 200 | 200 |
| `POST /inventory/stock/restock/` | 201 | **403** | 201 | 201 |

> **One exception.** `POST /api/sales/sales/` is `AllowAny` for guest checkout, so it never consults this gate — a support agent has exactly the power an anonymous caller already has, no more. Unlike an anonymous caller, their request is logged.

#### `GET /api/organization/platform-access-log/`

Every request that reaches an organization the caller is not in, **granted or refused**, including one shop probing another.

```json
{ "actor_email": "agent@blendy.test", "organization_slug": "mama-duka",
  "method": "POST", "path": "/api/inventory/stock/restock/",
  "status_code": 403, "granted": false, "created_at": "…" }
```

Filter with `?organization=`, `?actor=`, `?granted=`, `?method=`.

Three properties worth knowing:

- **Read-only by construction.** `POST`, `PATCH` and `DELETE` return `405` for everyone, superadmin included. The only way a row changes is a migration.
- **Gated on `platform.view_access_log`**, which only `PLATFORM_ADMIN` holds. A shop's `ORG_ADMIN` has all 87 tenant permissions and still cannot read it.
- **Actor email and organization slug are denormalised**, so the record still answers "who looked at my data?" after the staff account is deleted.

A member's requests to their own organization are **not** logged — that would bury the rows that matter.

#### `GET /api/organization/access-log/` — the shop's own view

The tenant-facing half. A shop whose figures Blendy staff can read should be able to see when that happened **without asking us** — an assurance worth little if it depends on us answering.

Same records, scoped to the caller's own organization, read-only. Held by `ORG_ADMIN` via `organization.view_access_log`; a cashier does not hold it, because who has been looking at the books is the owner's business.

```json
{ "actor": "agent@blendy.test", "actor_is_platform": true,
  "method": "GET", "path": "/api/sales/sales/",
  "status_code": 200, "granted": true, "created_at": "…" }
```

**The care is in what it withholds.** Blendy staff are named — that is the honest answer to "who looked at my data?", and what makes the support relationship legible. A *different customer* whose access was refused still appears, because a refused attempt is worth knowing about, but is not identified:

```json
{ "actor": "an account outside this organization", "actor_is_platform": false,
  "status_code": 403, "granted": false }
```

Naming them would hand one shop another shop's staff email — leaking across exactly the boundary this log exists to watch. The raw email is absent from the payload, not merely relabelled; HQ's view still shows it in full.

`actor_is_platform` is recorded at write time rather than derived on read, for the same reason the email is denormalised: the actor may later be deleted or change organizations, and a record whose meaning shifts afterwards is not an audit trail.

Filter with `?granted=`, `?method=`, `?actor_is_platform=`. `DELETE` and `POST` return `405` — a shop cannot tidy away the record of who watched it any more than we can.

#### Retention

Entries are kept for **365 days** by default (`PLATFORM_ACCESS_LOG_RETENTION_DAYS`). The window is long on purpose: a shop noticing something odd in last quarter's figures should still be able to ask who looked.

There is no worker in this deployment, so pruning is a cron job:

```bash
0 3 * * 0  python manage.py prune_access_log
python manage.py prune_access_log --dry-run       # report only
python manage.py prune_access_log --days 180      # override the window
```

**The command refuses to prune below 30 days** (`PLATFORM_ACCESS_LOG_MINIMUM_RETENTION_DAYS`), checked before anything is deleted:

```
CommandError: Refusing to prune to 1 days: the minimum retention is 30.
An audit trail that can be trimmed to yesterday is not one.
```

Trimming the log to yesterday is exactly what someone covering their tracks would want, so a too-small window is refused rather than obeyed. The floor can be lowered by an explicit, reviewed settings change.

Denials are pruned on the same schedule as grants — one policy, no special cases.

#### Onboarding without the flag

```http
POST /api/organization/onboard/
```
Now requires `platform.onboard_organization` rather than `is_superuser_admin`. The flag still passes, because `HasUserPermission` short-circuits for superadmins.

---

## Known limitations

These are current behaviour, documented so they are not rediscovered as bugs.

**1. `uom_id` and `currency_id` are ignored when creating variations inline.** In a nested `POST /api/products/` they are read-only on the nested serializer, so they are silently dropped and the variation comes back with `"uom": null`. Set them afterwards via `PATCH /api/products/variations/{id}/`.

**2. A missing `X-Organization` reads as empty, not as an error.** Intentional — the viewsets fail closed rather than leaking across tenants — but it does mean a forgotten header looks like an empty shop.

**3. `mpesa_shortcode` must be set before a second shop exists.** C2B reconciliation falls back to "the only organization" when no shortcode matches. That fallback is safe for exactly one tenant.

**4. Pruning the access log is a shell operation.** There is no scheduler, so `prune_access_log` has to be run from cron. Nothing prunes itself.

**5. Products and payments do not check the catalogue yet.** Sales, inventory and pricing do. The product endpoints are open by design (anonymous browsing), and the payment endpoints gate on `IsAuthenticated` + `IsOrganizationUser` alone — so any member of an organization can read its payment records. Extending enforcement there is a further decision; note that `POST /api/payments/payments/` must stay open for guest checkout.

**6. Stock-take endpoints are scaffolding.** `/inventory/stock-takes/` stores rows but is not wired to the ledger. Use `/inventory/stock/adjust/` with `counted_quantity` for a real count.

---

## Regenerating this documentation

```bash
python manage.py generate_swagger swagger.json --overwrite   # OpenAPI 2.0
python convert_swagger_to_postman.py                          # Postman collection
```

The schema's security definitions and the `X-Organization` header come from `SWAGGER_SETTINGS` and `blendy_backend/schema.py` — drf-yasg cannot infer either, since tenancy lives in middleware rather than in any view.

The Postman collection is built to be runnable, not just readable: collection-level bearer auth reading `{{access_token}}`, a login request that captures that token automatically, `X-Organization: {{organization_id}}` on every tenant-scoped request, and request bodies with server-assigned fields stripped out.

**Set `base_url` and `organization_id`, run the login request, and the rest of the collection is armed.**
