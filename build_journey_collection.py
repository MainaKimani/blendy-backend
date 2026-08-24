"""Build blendy-journeys.postman.json — the workflow collection.

This is the companion to `convert_swagger_to_postman.py`, and they answer
different questions:

* `blendy-suite-v1.json` is generated from the schema and lists **every**
  endpoint. Use it to look one up.
* `blendy-journeys.postman.json` is this file's output: a small number of
  **ordered workflows** that chain into each other. Every request captures the
  ids the next one needs, so a whole journey runs unattended in Postman's
  Collection Runner (or `newman run`) with nothing to copy by hand.

Each request also asserts its own outcome, which makes the collection a
smoke test as well as a walkthrough: a red run tells you which step broke.

    python build_journey_collection.py

Prerequisites for a run, in order:
  1. `python manage.py migrate` (seeds the RBAC catalogue)
  2. `python manage.py createsuperuser`
  3. set `superadmin_email` / `superadmin_password` on the collection
  4. run journey J1 first — it creates the shop every later journey uses
"""

import json

OUT = "blendy-journeys.postman.json"

# Every journey runs against a local sandbox where the M-Pesa callbacks are
# driven by hand rather than by Safaricom, so the IP allowlist is off:
#   MPESA_WEBHOOK_TOKEN=tok-123 MPESA_WEBHOOK_ENFORCE_IP=false python manage.py runserver
WEBHOOK_TOKEN_VAR = "{{mpesa_webhook_token}}"


def js(*lines):
    return list(lines)


def request(name, method, path, *, body=None, description="", tests=None,
            auth=None, headers=None, org_header=True):
    hdrs = []
    if body is not None:
        hdrs.append({"key": "Content-Type", "value": "application/json"})
    if org_header:
        hdrs.append({"key": "X-Organization", "value": "{{organization_id}}"})
    hdrs.extend(headers or [])

    req = {
        "method": method,
        "header": hdrs,
        "url": {
            "raw": "{{base_url}}/api" + path,
            "host": ["{{base_url}}"],
            "path": ["api"] + [p for p in path.strip("/").split("/") if p],
        },
        "description": description,
    }
    if body is not None:
        req["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    if auth is not None:
        req["auth"] = auth

    item = {"name": name, "request": req, "response": []}
    if tests:
        item["event"] = [
            {"listen": "test", "script": {"type": "text/javascript", "exec": tests}}
        ]
    return item


NO_AUTH = {"type": "noauth"}


def journeys():
    return [
        # ------------------------------------------------------------ J1
        {
            "name": "J1 · Open a shop",
            "description": (
                "Everything a new shop needs before it can sell anything: an "
                "organization, an owner, a priced catalogue, and stock on the "
                "shelf.\n\n**Run this first.** Every later journey uses the "
                "organization, variation and token it captures."
            ),
            "item": [
                request(
                    "1. Log in as superadmin", "POST", "/auth/login/",
                    body={"email": "{{superadmin_email}}", "password": "{{superadmin_password}}"},
                    org_header=False, auth=NO_AUTH,
                    description="Only a superadmin may onboard an organization.",
                    tests=js(
                        "pm.test('logged in', () => pm.response.to.have.status(200));",
                        "pm.collectionVariables.set('access_token', pm.response.json().access);",
                    ),
                ),
                request(
                    "2. Onboard the shop", "POST", "/organization/onboard/",
                    body={
                        "organization": {"name": "Mama Duka", "slug": "mama-duka",
                                         "mpesa_shortcode": "174379"},
                        "user": {"email": "owner@mamaduka.test", "username": "owner",
                                 "password": "s3cret", "first_name": "Amina"},
                    },
                    org_header=False,
                    description=(
                        "Creates the organization, its Default Pricelist, its "
                        "ORG_ADMIN owner, and enables the built-in roles — one "
                        "transaction.\n\nThe returned organization id is what "
                        "every later request sends as X-Organization."
                    ),
                    tests=js(
                        "pm.test('shop created', () => pm.response.to.have.status(201));",
                        "const b = pm.response.json();",
                        "pm.collectionVariables.set('organization_id', b.organization.id);",
                        "pm.test('owner is ORG_ADMIN', () =>",
                        "    pm.expect(b.user.assigned_roles).to.include('ORG_ADMIN'));",
                    ),
                ),
                request(
                    "3. Log in as the owner", "POST", "/auth/login/",
                    body={"email": "owner@mamaduka.test", "password": "s3cret"},
                    org_header=False, auth=NO_AUTH,
                    tests=js(
                        "pm.test('owner logged in', () => pm.response.to.have.status(200));",
                        "pm.collectionVariables.set('access_token', pm.response.json().access);",
                        "pm.collectionVariables.set('owner_token', pm.response.json().access);",
                    ),
                ),
                request(
                    "4. Confirm the default pricelist", "GET", "/pricing/pricelists/",
                    description=(
                        "Onboarding created it. Without a pricelist the shop "
                        "cannot price or sell anything, so this is worth "
                        "checking before going further."
                    ),
                    tests=js(
                        "pm.test('reachable', () => pm.response.to.have.status(200));",
                        "const r = pm.response.json().results;",
                        "pm.test('Default Pricelist exists', () =>",
                        "    pm.expect(r.some(p => p.is_default)).to.be.true);",
                        "pm.collectionVariables.set('pricelist_id', r.find(p => p.is_default).id);",
                    ),
                ),
                request(
                    "5. Create a category", "POST", "/products/categories/",
                    body={"name": "Groceries", "description": "Dry goods"},
                    tests=js(
                        "pm.test('created', () => pm.response.to.have.status(201));",
                        "pm.collectionVariables.set('category_id', pm.response.json().id);",
                    ),
                ),
                request(
                    "6. Create a product with priced variations", "POST", "/products/",
                    body={
                        "name": "Mumias Sugar",
                        "description": "Refined white sugar",
                        "category_id": "{{category_id}}",
                        "variations": [
                            {"sku": "SUG-1KG", "cost_price": "120.00",
                             "selling_price": "165.00", "reorder_level": 10},
                            {"sku": "SUG-2KG", "cost_price": "230.00",
                             "selling_price": "310.00", "reorder_level": 5},
                        ],
                    },
                    description=(
                        "At least one variation is required and each must carry "
                        "a selling_price.\n\n`cost_price` stays on the variation; "
                        "`selling_price` is written to the Default Pricelist. "
                        "You write `selling_price` and read back `price`."
                    ),
                    tests=js(
                        "pm.test('created', () => pm.response.to.have.status(201));",
                        "const b = pm.response.json();",
                        "pm.collectionVariables.set('product_id', b.id);",
                        "pm.collectionVariables.set('variation_id', b.variations[0].id);",
                        "pm.test('price came back from the pricelist', () =>",
                        "    pm.expect(b.variations[0].price).to.eql('165.00'));",
                        "pm.test('product itself carries no price', () =>",
                        "    pm.expect(b).to.not.have.property('price'));",
                    ),
                ),
                request(
                    "7. Receive opening stock", "POST", "/inventory/stock/restock/",
                    body={"product_variation": "{{variation_id}}", "quantity": 50,
                          "unit_cost": "120.00", "reference_number": "GRN-0012",
                          "notes": "Opening stock"},
                    description=(
                        "Writes a STOCK_IN entry to the ledger and updates the "
                        "cached balance in the same transaction. "
                        "`available_quantity` in the response is recomputed from "
                        "the ledger, so it doubles as a check that the two agree."
                    ),
                    tests=js(
                        "pm.test('stocked', () => pm.response.to.have.status(201));",
                        "pm.test('balance is 50', () =>",
                        "    pm.expect(pm.response.json().available_quantity).to.eql(50));",
                    ),
                ),
            ],
        },
        # ------------------------------------------------------------ J2
        {
            "name": "J2 · Sell, and get paid by STK push",
            "description": (
                "The daily loop, happy path. The customer's phone prompts, they "
                "enter their PIN, Safaricom calls back, the sale is PAID."
                "\n\nStep 3 stands in for Safaricom. Point `base_url` at a local "
                "server started with `MPESA_WEBHOOK_TOKEN=tok-123 "
                "MPESA_WEBHOOK_ENFORCE_IP=false`."
            ),
            "item": [
                request(
                    "1. Record the sale", "POST", "/sales/sales/",
                    body={"customer_phone": "0712345678",
                          "items": [{"product_variation": "{{variation_id}}",
                                     "quantity": 2, "unit_price": "165.00"}]},
                    description=(
                        "`unit_price` is optional — omit it and the pricelist "
                        "price applies. Supply it and it must match exactly.\n\n"
                        "Creating the sale decrements stock through the ledger "
                        "in the same transaction."
                    ),
                    tests=js(
                        "pm.test('sale recorded', () => pm.response.to.have.status(201));",
                        "const b = pm.response.json();",
                        "pm.collectionVariables.set('sale_id', b.id);",
                        "pm.test('total is 330.00', () => pm.expect(b.total_amount).to.eql('330.00'));",
                        "pm.test('starts UNPAID', () => pm.expect(b.payment_status).to.eql('UNPAID'));",
                        "pm.test('cost snapshotted onto the line', () =>",
                        "    pm.expect(b.items[0].cost_price).to.eql('120.00'));",
                    ),
                ),
                request(
                    "2. Trigger the STK push", "POST", "/payments/payments/",
                    body={"sale": "{{sale_id}}", "provider": "MPESA",
                          "phone_number": "0712345678", "amount": "330.00"},
                    description=(
                        "`amount` must equal the sale total. The phone number is "
                        "normalised to +254 and checked against Safaricom "
                        "prefixes.\n\nThe result arrives on the webhook, not in "
                        "this response — the payment comes back PENDING."
                    ),
                    tests=js(
                        "pm.test('push sent', () => pm.response.to.have.status(201));",
                        "const b = pm.response.json();",
                        "pm.collectionVariables.set('payment_id', b.id);",
                        "pm.collectionVariables.set('checkout_request_id', b.provider_reference);",
                        "pm.collectionVariables.set('merchant_request_id', b.merchant_reference);",
                        "pm.test('pending until the callback', () =>",
                        "    pm.expect(b.status).to.eql('PENDING'));",
                    ),
                ),
                request(
                    "3. Safaricom confirms success", "POST",
                    f"/payments/webhooks/mpesa/{WEBHOOK_TOKEN_VAR}/",
                    body={"Body": {"stkCallback": {
                        "MerchantRequestID": "{{merchant_request_id}}",
                        "CheckoutRequestID": "{{checkout_request_id}}",
                        "ResultCode": 0,
                        "ResultDesc": "The service request is processed successfully.",
                        "CallbackMetadata": {"Item": [
                            {"Name": "Amount", "Value": 330.00},
                            {"Name": "MpesaReceiptNumber", "Value": "TGH7YU8KLM"},
                            {"Name": "TransactionDate", "Value": 20260822131549},
                            {"Name": "PhoneNumber", "Value": 254712345678}]}}}},
                    org_header=False, auth=NO_AUTH,
                    description=(
                        "**Safaricom calls this, not your client.** The token in "
                        "the URL is the shared secret, since Safaricom does not "
                        "sign callbacks.\n\nChange `Amount` to 300.00 and re-run: "
                        "the sale stays UNPAID and the payment is flagged "
                        "MISMATCH. A success callback for the wrong amount never "
                        "marks a sale paid."
                    ),
                    tests=js(
                        "pm.test('processed', () => pm.response.to.have.status(200));",
                    ),
                ),
                request(
                    "4. The sale is now PAID", "GET", "/sales/sales/{{sale_id}}/",
                    tests=js(
                        "pm.test('readable', () => pm.response.to.have.status(200));",
                        "pm.test('PAID', () =>",
                        "    pm.expect(pm.response.json().payment_status).to.eql('PAID'));",
                    ),
                ),
            ],
        },
        # ------------------------------------------------------------ J3
        {
            "name": "J3 · STK push fails, customer pays the Till",
            "description": (
                "MVP §8 / US-9b / US-9c — the fallback that matters most in a "
                "real shop.\n\nThe push fails, but the sale is **not** closed. It "
                "moves to AWAITING_DIRECT_PAYMENT, the customer pays the Till "
                "from the M-Pesa menu, and the incoming C2B confirmation is "
                "matched back to the sale by phone number and amount."
            ),
            "item": [
                request(
                    "1. Record the sale", "POST", "/sales/sales/",
                    body={"customer_phone": "0712345678",
                          "items": [{"product_variation": "{{variation_id}}",
                                     "quantity": 2, "unit_price": "165.00"}]},
                    tests=js(
                        "pm.test('recorded', () => pm.response.to.have.status(201));",
                        "pm.collectionVariables.set('sale_id', pm.response.json().id);",
                    ),
                ),
                request(
                    "2. Trigger the STK push", "POST", "/payments/payments/",
                    body={"sale": "{{sale_id}}", "provider": "MPESA",
                          "phone_number": "0712345678", "amount": "330.00"},
                    tests=js(
                        "pm.test('sent', () => pm.response.to.have.status(201));",
                        "const b = pm.response.json();",
                        "pm.collectionVariables.set('checkout_request_id', b.provider_reference);",
                        "pm.collectionVariables.set('merchant_request_id', b.merchant_reference);",
                    ),
                ),
                request(
                    "3. The push fails", "POST",
                    f"/payments/webhooks/mpesa/{WEBHOOK_TOKEN_VAR}/",
                    body={"Body": {"stkCallback": {
                        "MerchantRequestID": "{{merchant_request_id}}",
                        "CheckoutRequestID": "{{checkout_request_id}}",
                        "ResultCode": 1032,
                        "ResultDesc": "Request cancelled by user"}}},
                    org_header=False, auth=NO_AUTH,
                    description="Any non-zero ResultCode. 1032 is a user cancel.",
                    tests=js("pm.test('processed', () => pm.response.to.have.status(200));"),
                ),
                request(
                    "4. The sale is queued, not closed", "GET",
                    "/sales/sales/pending-payments/",
                    description=(
                        "The owner's queue for anything still owed — sales "
                        "awaiting a direct payment, and sales never paid at all."
                    ),
                    tests=js(
                        "pm.test('reachable', () => pm.response.to.have.status(200));",
                        "const rows = pm.response.json().results;",
                        "pm.test('our sale is awaiting a direct payment', () =>",
                        "    pm.expect(rows.some(s => s.id === pm.collectionVariables.get('sale_id')",
                        "        && s.payment_status === 'AWAITING_DIRECT_PAYMENT')).to.be.true);",
                    ),
                ),
                request(
                    "5. Customer pays the Till directly", "POST",
                    f"/payments/webhooks/mpesa-c2b/{WEBHOOK_TOKEN_VAR}/",
                    body={"TransactionType": "Pay Bill", "TransID": "TGH7YU8KLM",
                          "TransTime": "20260822131549", "TransAmount": "330.00",
                          "BusinessShortCode": "174379", "MSISDN": "254712345678"},
                    org_header=False, auth=NO_AUTH,
                    description=(
                        "A direct payment has no CheckoutRequestID, so it is "
                        "attributed to a tenant by BusinessShortCode and matched "
                        "to an open sale by MSISDN + TransAmount inside a 24-hour "
                        "window.\n\nMatching is idempotent on TransID — re-run "
                        "this and nothing double-counts."
                    ),
                    tests=js(
                        "pm.test('acknowledged', () => pm.response.to.have.status(200));",
                        "pm.test('matched to the sale', () =>",
                        "    pm.expect(pm.response.json().matched).to.be.true);",
                    ),
                ),
                request(
                    "6. The sale is reconciled to PAID", "GET",
                    "/sales/sales/{{sale_id}}/",
                    tests=js(
                        "pm.test('PAID', () =>",
                        "    pm.expect(pm.response.json().payment_status).to.eql('PAID'));",
                    ),
                ),
            ],
        },
        # ------------------------------------------------------------ J4
        {
            "name": "J4 · A direct payment that matches nothing",
            "description": (
                "US-10. Money arrives that cannot be tied to an open sale — no "
                "candidate, or more than one. It is **not** dropped and **not** "
                "guessed at: it waits in a queue with a note saying why."
            ),
            "item": [
                request(
                    "1. Unattributable money arrives", "POST",
                    f"/payments/webhooks/mpesa-c2b/{WEBHOOK_TOKEN_VAR}/",
                    body={"TransactionType": "Pay Bill", "TransID": "NOMATCH001",
                          "TransTime": "20260822140000", "TransAmount": "999.00",
                          "BusinessShortCode": "174379", "MSISDN": "254799999999"},
                    org_header=False, auth=NO_AUTH,
                    description=(
                        "Still answers 200 in Safaricom's expected shape, so it "
                        "stops retrying — but `matched` is false."
                    ),
                    tests=js(
                        "pm.test('acknowledged', () => pm.response.to.have.status(200));",
                        "pm.test('not matched', () =>",
                        "    pm.expect(pm.response.json().matched).to.be.false);",
                    ),
                ),
                request(
                    "2. It waits for a human", "GET", "/payments/payments/unmatched/",
                    tests=js(
                        "pm.test('reachable', () => pm.response.to.have.status(200));",
                        "pm.test('the payment is queued', () =>",
                        "    pm.expect(pm.response.json().results.some(",
                        "        t => t.mpesa_receipt_number === 'NOMATCH001'",
                        "          || t.checkout_request_id === '')).to.be.true);",
                    ),
                ),
            ],
        },
        # ------------------------------------------------------------ J5
        {
            "name": "J5 · Stock runs low and is replenished",
            "description": (
                "US-3, US-17, US-19. Stock is a ledger, not a number: every "
                "change is an entry, and the balance is a cache of those entries."
            ),
            "item": [
                request(
                    "1. Sell down toward the threshold", "POST", "/sales/sales/",
                    body={"items": [{"product_variation": "{{variation_id}}",
                                     "quantity": 38}]},
                    description="Leaves the variation at or below its reorder_level of 10.",
                    tests=js("pm.test('sold', () => pm.response.to.have.status(201));"),
                ),
                request(
                    "2. The low-stock queue picks it up", "GET",
                    "/inventory/stock/low-stock/",
                    description=(
                        "The threshold is **inclusive** — selling down *to* it "
                        "fires the alert, not only going under. Most urgent first."
                    ),
                    tests=js(
                        "pm.test('reachable', () => pm.response.to.have.status(200));",
                        "pm.test('our variation is listed', () =>",
                        "    pm.expect(pm.response.json().results.some(",
                        "        r => r.product_variation_id === pm.collectionVariables.get('variation_id')",
                        "    )).to.be.true);",
                    ),
                ),
                request(
                    "3. A physical count finds fewer", "POST",
                    "/inventory/stock/adjust/",
                    body={"product_variation": "{{variation_id}}",
                          "counted_quantity": 8,
                          "reason": "Monthly count: two bags damaged"},
                    description=(
                        "Send **exactly one** of `counted_quantity` (the figure "
                        "on the shelf) or `quantity` (a signed change).\n\n"
                        "`reason` is never optional — an unexplained adjustment "
                        "is what the ledger exists to rule out.\n\nThe difference "
                        "is computed under the row lock that writes it, so a sale "
                        "landing mid-count cannot be silently undone."
                    ),
                    tests=js(
                        "pm.test('adjusted', () => pm.response.to.have.status(201));",
                        "pm.test('balance is now 8', () =>",
                        "    pm.expect(pm.response.json().available_quantity).to.eql(8));",
                        "pm.test('recorded as a negative movement', () =>",
                        "    pm.expect(pm.response.json().movement.quantity).to.be.below(0));",
                    ),
                ),
                request(
                    "4. Restock clears the alert", "POST",
                    "/inventory/stock/restock/",
                    body={"product_variation": "{{variation_id}}", "quantity": 40,
                          "unit_cost": "122.00", "reference_number": "GRN-0013"},
                    tests=js(
                        "pm.test('restocked', () => pm.response.to.have.status(201));",
                        "pm.test('balance is 48', () =>",
                        "    pm.expect(pm.response.json().available_quantity).to.eql(48));",
                    ),
                ),
                request(
                    "5. The ledger explains every change", "GET",
                    "/inventory/stock-movements/",
                    description=(
                        "Append-only and read-only. A POST here returns 405 — "
                        "stock moves through the restock, adjust and sale paths "
                        "only, so the balance can never drift from the entries "
                        "that explain it."
                    ),
                    tests=js(
                        "pm.test('readable', () => pm.response.to.have.status(200));",
                        "const kinds = pm.response.json().results.map(m => m.movement_type);",
                        "pm.test('shows stock in, sale and adjustment', () => {",
                        "    pm.expect(kinds).to.include('STOCK_IN');",
                        "    pm.expect(kinds).to.include('SALE');",
                        "    pm.expect(kinds).to.include('ADJUSTMENT');",
                        "});",
                    ),
                ),
                request(
                    "6. The ledger cannot be written directly", "POST",
                    "/inventory/stock-movements/",
                    body={"product_variation": "{{variation_id}}",
                          "movement_type": "STOCK_IN", "quantity": 1000},
                    tests=js(
                        "pm.test('refused with 405', () => pm.response.to.have.status(405));",
                    ),
                ),
            ],
        },
        # ------------------------------------------------------------ J6
        {
            "name": "J6 · Hire a cashier",
            "description": (
                "US-15. A cashier records sales and sees stock, but cannot "
                "change prices, move stock, or manage staff."
            ),
            "item": [
                request(
                    "1. See which roles the shop has enabled", "GET",
                    "/authorization/organization-roles/",
                    description=(
                        "Onboarding enables ORG_ADMIN, CASHIER and VIEWER. To "
                        "enable another, POST {\"role_id\": \"...\"} here — the "
                        "organization comes from the header, never the body."
                    ),
                    tests=js(
                        "pm.test('reachable', () => pm.response.to.have.status(200));",
                        "const row = pm.response.json().results.find(r => r.role.name === 'CASHIER');",
                        "pm.test('CASHIER is enabled', () => pm.expect(row).to.not.be.undefined);",
                        "pm.collectionVariables.set('cashier_role_id', row.id);",
                    ),
                ),
                request(
                    "2. Create the cashier", "POST", "/users/",
                    body={"email": "till@mamaduka.test", "username": "till",
                          "password": "till-pass",
                          "organization_role_ids": ["{{cashier_role_id}}"]},
                    tests=js(
                        "pm.test('created', () => pm.response.to.have.status(201));",
                        "pm.test('holds CASHIER', () =>",
                        "    pm.expect(pm.response.json().assigned_roles).to.include('CASHIER'));",
                    ),
                ),
                request(
                    "3. Log in as the cashier", "POST", "/auth/login/",
                    body={"email": "till@mamaduka.test", "password": "till-pass"},
                    org_header=False, auth=NO_AUTH,
                    tests=js(
                        "pm.test('logged in', () => pm.response.to.have.status(200));",
                        "pm.collectionVariables.set('access_token', pm.response.json().access);",
                    ),
                ),
                request(
                    "4. The cashier records a sale", "POST", "/sales/sales/",
                    body={"items": [{"product_variation": "{{variation_id}}",
                                     "quantity": 1}]},
                    tests=js("pm.test('allowed', () => pm.response.to.have.status(201));"),
                ),
                request(
                    "5. …and can see the stock position", "GET",
                    "/inventory/stock/low-stock/",
                    tests=js("pm.test('allowed', () => pm.response.to.have.status(200));"),
                ),
                request(
                    "6. …but cannot move stock", "POST",
                    "/inventory/stock/restock/",
                    body={"product_variation": "{{variation_id}}", "quantity": 100},
                    description=(
                        "The sharpest owner/till line: a cashier sells stock "
                        "down but cannot restock or adjust it, so the ledger's "
                        "write path stays with whoever is accountable for the count."
                    ),
                    tests=js("pm.test('refused', () => pm.response.to.have.status(403));"),
                ),
                request(
                    "7. …and cannot change prices", "POST", "/pricing/pricelists/",
                    body={"name": "Cheap"},
                    tests=js("pm.test('refused', () => pm.response.to.have.status(403));"),
                ),
                request(
                    "8. Log back in as the owner", "POST", "/auth/login/",
                    body={"email": "owner@mamaduka.test", "password": "s3cret"},
                    org_header=False, auth=NO_AUTH,
                    description="Restores the owner token for the remaining journeys.",
                    tests=js(
                        "pm.collectionVariables.set('access_token', pm.response.json().access);",
                    ),
                ),
            ],
        },
        # ------------------------------------------------------------ J7
        {
            "name": "J7 · Guest checkout",
            "description": (
                "A walk-in customer with no account. Two endpoints stay open to "
                "anonymous callers — creating a sale and paying for it — and "
                "nothing else does."
            ),
            "item": [
                request(
                    "1. Browse the catalogue anonymously", "GET", "/products/",
                    auth=NO_AUTH,
                    tests=js(
                        "pm.test('open', () => pm.response.to.have.status(200));",
                    ),
                ),
                request(
                    "2. Check out anonymously", "POST", "/sales/sales/",
                    body={"customer_name": "Walk-in", "customer_phone": "0722000111",
                          "items": [{"product_variation": "{{variation_id}}",
                                     "quantity": 1}]},
                    auth=NO_AUTH,
                    description=(
                        "Deliberately not permission-gated on any role: a "
                        "customer at the till holds no role at all."
                    ),
                    tests=js(
                        "pm.test('checked out', () => pm.response.to.have.status(201));",
                        "pm.collectionVariables.set('guest_sale_id', pm.response.json().id);",
                    ),
                ),
                request(
                    "3. Pay anonymously", "POST", "/payments/payments/",
                    body={"sale": "{{guest_sale_id}}", "provider": "MPESA",
                          "phone_number": "0722000111", "amount": "165.00"},
                    auth=NO_AUTH,
                    description=(
                        "Rate limited when anonymous — 5/hour per phone number, "
                        "20/hour per IP — because it fires an STK push at a "
                        "caller-supplied number. Run it six times to see a 429."
                    ),
                    tests=js("pm.test('accepted', () => pm.response.to.have.status(201));"),
                ),
                request(
                    "4. …but cannot read the shop's sales", "GET", "/sales/sales/",
                    auth=NO_AUTH,
                    tests=js(
                        "pm.test('refused', () => pm.expect(pm.response.code).to.be.oneOf([401, 403]));",
                    ),
                ),
            ],
        },
        # ------------------------------------------------------------ J8
        {
            "name": "J8 · Guardrails",
            "description": (
                "The refusals worth knowing before you build a UI, since each "
                "one is an error state a form has to handle."
            ),
            "item": [
                request(
                    "1. A price that does not match the pricelist", "POST",
                    "/sales/sales/",
                    body={"items": [{"product_variation": "{{variation_id}}",
                                     "quantity": 1, "unit_price": "100.00"}]},
                    description=(
                        "Prices are never taken on trust. Any concession must be "
                        "declared in `discount`, where it stays visible, rather "
                        "than hidden in a reduced unit price."
                    ),
                    tests=js(
                        "pm.test('rejected', () => pm.response.to.have.status(400));",
                        "pm.test('names the pricelist', () =>",
                        "    pm.expect(pm.response.text()).to.include('Default Pricelist'));",
                    ),
                ),
                request(
                    "2. Selling more than you hold", "POST", "/sales/sales/",
                    body={"items": [{"product_variation": "{{variation_id}}",
                                     "quantity": 99999}]},
                    tests=js(
                        "pm.test('rejected', () => pm.response.to.have.status(400));",
                        "pm.test('says how much is left', () =>",
                        "    pm.expect(pm.response.text()).to.include('Insufficient stock'));",
                    ),
                ),
                request(
                    "3. A product whose variation has no price", "POST", "/products/",
                    body={"name": "Unpriced Thing", "category_id": "{{category_id}}",
                          "variations": [{"sku": "NOPRICE", "cost_price": "10.00"}]},
                    description="A product with no priced variation is not sellable, so it is refused rather than created.",
                    tests=js(
                        "pm.test('rejected', () => pm.response.to.have.status(400));",
                        "pm.test('points at selling_price', () =>",
                        "    pm.expect(pm.response.text()).to.include('selling_price'));",
                    ),
                ),
                request(
                    "4. A product with no variations at all", "POST", "/products/",
                    body={"name": "Empty", "category_id": "{{category_id}}",
                          "variations": []},
                    tests=js("pm.test('rejected', () => pm.response.to.have.status(400));"),
                ),
                request(
                    "5. An anonymous caller granting themselves a discount",
                    "POST", "/sales/sales/",
                    body={"items": [{"product_variation": "{{variation_id}}",
                                     "quantity": 1, "unit_price": "165.00",
                                     "discount": "50.00", "selling_price": "115.00"}]},
                    auth=NO_AUTH,
                    description="Guest checkout stays open, but it cannot discount itself.",
                    tests=js(
                        "pm.test('rejected', () => pm.response.to.have.status(400));",
                        "pm.test('says why', () =>",
                        "    pm.expect(pm.response.text()).to.include('signed-in user'));",
                    ),
                ),
                request(
                    "6. A missing X-Organization header", "GET", "/sales/sales/",
                    org_header=False,
                    description=(
                        "On a write this is a 403. On a **read** the queryset "
                        "resolves to no tenant and returns an empty page rather "
                        "than an error — the viewsets fail closed, so a forgotten "
                        "header looks like an empty shop."
                    ),
                    tests=js(
                        "pm.test('not another tenant\\'s data', () =>",
                        "    pm.expect(pm.response.code).to.be.oneOf([200, 401, 403]));",
                        "if (pm.response.code === 200) {",
                        "    pm.test('empty rather than everything', () =>",
                        "        pm.expect(pm.response.json().total_items).to.eql(0));",
                        "}",
                    ),
                ),
                request(
                    "7. A webhook with the wrong token", "POST",
                    "/payments/webhooks/mpesa-c2b/wrong-token/",
                    body={"TransID": "X", "TransAmount": "1.00",
                          "MSISDN": "254700000000", "BusinessShortCode": "174379"},
                    org_header=False, auth=NO_AUTH,
                    tests=js(
                        "pm.test('rejected', () => pm.response.to.have.status(401));",
                    ),
                ),
            ],
        },
        # ------------------------------------------------------------ J9
        {
            "name": "J9 · HQ: support a shop without the superadmin flag",
            "description": (
                "Blendy's own staff. HQ is an organization like any other as far "
                "as RBAC is concerned, which is what lets platform staff use the "
                "same roles a shop's staff use.\n\n"
                "**Setup.** `python manage.py bootstrap_hq` prints the HQ id — "
                "put it in `hq_organization_id`. HQ is deliberately absent from "
                "`GET /api/organization/`, which lists customers only.\n\n"
                "Run **J1** first; this journey supports the shop J1 created."
            ),
            "item": [
                request(
                    "1. Log in as superadmin", "POST", "/auth/login/",
                    body={"email": "{{superadmin_email}}", "password": "{{superadmin_password}}"},
                    org_header=False, auth=NO_AUTH,
                    description="The flag is retained as break-glass. Everything after this step uses roles instead.",
                    tests=js(
                        "pm.test('logged in', () => pm.response.to.have.status(200));",
                        "pm.collectionVariables.set('access_token', pm.response.json().access);",
                    ),
                ),
                request(
                    "2. Find HQ", "GET", "/organization/platform/",
                    org_header=False,
                    description=(
                        "HQ is deliberately absent from `GET /api/organization/`, "
                        "which lists customers only \u2014 so this is how platform "
                        "staff learn the id they send as X-Organization when "
                        "working on HQ itself. Open to any holder of a "
                        "`platform.*` permission."
                    ),
                    tests=js(
                        "pm.test('found', () => pm.response.to.have.status(200));",
                        "const hq = pm.response.json();",
                        "pm.test('it really is the platform org', () =>",
                        "    pm.expect(hq.is_platform).to.be.true);",
                        "pm.collectionVariables.set('hq_organization_id', hq.id);",
                    ),
                ),
                request(
                    "3. Which roles does HQ have?", "GET",
                    "/authorization/organization-roles/",
                    headers=[{"key": "X-Organization", "value": "{{hq_organization_id}}"}],
                    org_header=False,
                    description="PLATFORM_ADMIN and SUPPORT_AGENT are enabled on HQ only — never on a shop.",
                    tests=js(
                        "pm.test('reachable', () => pm.response.to.have.status(200));",
                        "const rows = pm.response.json().results;",
                        "const admin = rows.find(r => r.role.name === 'PLATFORM_ADMIN');",
                        "const agent = rows.find(r => r.role.name === 'SUPPORT_AGENT');",
                        "pm.test('platform roles enabled on HQ', () => {",
                        "    pm.expect(admin).to.not.be.undefined;",
                        "    pm.expect(agent).to.not.be.undefined;",
                        "});",
                        "pm.collectionVariables.set('platform_admin_role_id', admin.id);",
                        "pm.collectionVariables.set('support_agent_role_id', agent.id);",
                    ),
                ),
                request(
                    "4. Hire a platform admin", "POST", "/users/",
                    body={"email": "admin@blendy.test", "username": "admin@blendy.test",
                          "password": "hq-pass",
                          "organization_role_ids": ["{{platform_admin_role_id}}"]},
                    headers=[{"key": "X-Organization", "value": "{{hq_organization_id}}"}],
                    org_header=False,
                    tests=js(
                        "pm.test('hired', () => pm.response.to.have.status(201));",
                        "pm.test('holds PLATFORM_ADMIN', () =>",
                        "    pm.expect(pm.response.json().assigned_roles).to.include('PLATFORM_ADMIN'));",
                    ),
                ),
                request(
                    "5. Hire a support agent", "POST", "/users/",
                    body={"email": "agent@blendy.test", "username": "agent@blendy.test",
                          "password": "hq-pass",
                          "organization_role_ids": ["{{support_agent_role_id}}"]},
                    headers=[{"key": "X-Organization", "value": "{{hq_organization_id}}"}],
                    org_header=False,
                    tests=js("pm.test('hired', () => pm.response.to.have.status(201));"),
                ),
                request(
                    "6. Log in as the platform admin", "POST", "/auth/login/",
                    body={"email": "admin@blendy.test", "password": "hq-pass"},
                    org_header=False, auth=NO_AUTH,
                    tests=js(
                        "pm.collectionVariables.set('access_token', pm.response.json().access);",
                    ),
                ),
                request(
                    "7. Onboard a shop — no flag involved", "POST",
                    "/organization/onboard/",
                    body={
                        "organization": {"name": "Duka Mbili", "slug": "duka-mbili"},
                        "user": {"email": "owner@dukambili.test",
                                 "username": "owner@dukambili.test", "password": "s3cret"},
                    },
                    org_header=False,
                    description=(
                        "This used to require `is_superuser_admin`. It now needs "
                        "`platform.onboard_organization`, which is grantable and "
                        "revocable per person."
                    ),
                    tests=js("pm.test('onboarded', () => pm.response.to.have.status(201));"),
                ),
                request(
                    "8. Read the shop's sales to help them", "GET", "/sales/sales/",
                    description=(
                        "Crossing the tenant boundary. The shop's own staff are "
                        "unaffected; this request is what the access log exists "
                        "to record."
                    ),
                    tests=js(
                        "pm.test('support can see the shop', () => pm.response.to.have.status(200));",
                    ),
                ),
                request(
                    "9. Log in as the support agent", "POST", "/auth/login/",
                    body={"email": "agent@blendy.test", "password": "hq-pass"},
                    org_header=False, auth=NO_AUTH,
                    tests=js(
                        "pm.collectionVariables.set('access_token', pm.response.json().access);",
                    ),
                ),
                request(
                    "10. Support reads…", "GET", "/inventory/stock/low-stock/",
                    tests=js("pm.test('allowed', () => pm.response.to.have.status(200));"),
                ),
                request(
                    "11. …but cannot touch", "POST", "/inventory/stock/restock/",
                    body={"product_variation": "{{variation_id}}", "quantity": 100},
                    description=(
                        "`platform.access_tenants` is a read grant. Writing needs "
                        "`platform.act_as_tenant`, which SUPPORT_AGENT does not "
                        "hold — and it holds no tenant write permission either, "
                        "so both layers refuse independently."
                    ),
                    tests=js("pm.test('refused', () => pm.response.to.have.status(403));"),
                ),
                request(
                    "12. Support cannot read the access log", "GET",
                    "/organization/platform-access-log/",
                    org_header=False,
                    description="Reading who watched whom is an administrator's business.",
                    tests=js("pm.test('refused', () => pm.response.to.have.status(403));"),
                ),
                request(
                    "13. Log back in as the platform admin", "POST", "/auth/login/",
                    body={"email": "admin@blendy.test", "password": "hq-pass"},
                    org_header=False, auth=NO_AUTH,
                    tests=js(
                        "pm.collectionVariables.set('access_token', pm.response.json().access);",
                    ),
                ),
                request(
                    "14. Every crossing is on the record", "GET",
                    "/organization/platform-access-log/",
                    org_header=False,
                    description=(
                        "Grants *and* denials, including the support agent's "
                        "refused write above. Read-only for everyone — POST, "
                        "PATCH and DELETE all return 405, superadmin included."
                    ),
                    tests=js(
                        "pm.test('readable', () => pm.response.to.have.status(200));",
                        "const rows = pm.response.json().results;",
                        "pm.test('the refused write is recorded', () =>",
                        "    pm.expect(rows.some(r => r.granted === false)).to.be.true);",
                        "pm.test('the granted read is recorded', () =>",
                        "    pm.expect(rows.some(r => r.granted === true)).to.be.true);",
                    ),
                ),
                request(
                    "15. The shop can see it too", "GET",
                    "/organization/access-log/",
                    description=(
                        "The tenant-facing half. The same records, shown to the "
                        "organization they are about \u2014 an assurance worth "
                        "little if it depended on us answering.\n\n"
                        "Run this as the shop owner from J1 to see the real "
                        "thing: Blendy staff are named, while a *different* "
                        "customer whose access was refused appears without being "
                        "identified. Naming them would hand one shop another "
                        "shop's staff email."
                    ),
                    tests=js(
                        "pm.test('platform admin can read it as the tenant', () =>",
                        "    pm.response.to.have.status(200));",
                        "const rows = pm.response.json().results;",
                        "pm.test('blendy staff are named', () =>",
                        "    pm.expect(rows.some(r => r.actor_is_platform",
                        "        && String(r.actor).includes('@'))).to.be.true);",
                    ),
                ),
                request(
                    "16. The log cannot be forged", "POST",
                    "/organization/platform-access-log/",
                    body={"actor_email": "someone-else@example.com"},
                    org_header=False,
                    tests=js("pm.test('no write path exists', () => pm.response.to.have.status(405));"),
                ),
            ],
        },
    ]


def build():
    collection = {
        "info": {
            "name": "Blendy · User Journeys",
            "description": (
                "Ordered workflows that chain into each other — run a folder "
                "top to bottom in the Collection Runner and it executes "
                "unattended.\n\n"
                "**Run J1 first.** It creates the shop, catalogue and stock that "
                "every later journey uses, and captures the ids into collection "
                "variables.\n\n"
                "**Setup**\n"
                "1. `python manage.py migrate` — seeds the RBAC catalogue\n"
                "2. `python manage.py createsuperuser`\n"
                "3. Start the server with the webhook token set:\n"
                "   `MPESA_WEBHOOK_TOKEN=tok-123 MPESA_WEBHOOK_ENFORCE_IP=false "
                "python manage.py runserver`\n"
                "4. Set `superadmin_email` and `superadmin_password` below\n\n"
                "Every request asserts its own outcome, so a red run tells you "
                "which step broke rather than leaving you to compare payloads."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}],
        },
        "variable": [
            {"key": "base_url", "value": "http://127.0.0.1:8000",
             "description": "Where the API is running."},
            {"key": "superadmin_email", "value": "",
             "description": "From manage.py createsuperuser. Needed to onboard a shop."},
            {"key": "superadmin_password", "value": "", "type": "secret"},
            {"key": "mpesa_webhook_token", "value": "tok-123",
             "description": "Must equal MPESA_WEBHOOK_TOKEN on the server."},
            {"key": "access_token", "value": "", "description": "Set by every login step."},
            {"key": "owner_token", "value": "", "description": "Kept so J6 can switch back."},
            {"key": "organization_id", "value": "", "description": "Captured in J1. Sent as X-Organization."},
            {"key": "pricelist_id", "value": ""},
            {"key": "category_id", "value": ""},
            {"key": "product_id", "value": ""},
            {"key": "variation_id", "value": "", "description": "The sellable unit every journey trades in."},
            {"key": "sale_id", "value": ""},
            {"key": "guest_sale_id", "value": ""},
            {"key": "payment_id", "value": ""},
            {"key": "checkout_request_id", "value": "", "description": "Echoed back on the STK callback."},
            {"key": "merchant_request_id", "value": ""},
            {"key": "cashier_role_id", "value": ""},
            {"key": "hq_organization_id", "value": "",
             "description": "Captured by J9 step 2 from GET /api/organization/platform/. HQ is not listed by GET /api/organization/, which returns customers only."},
            {"key": "platform_admin_role_id", "value": ""},
            {"key": "support_agent_role_id", "value": ""},
        ],
        "item": journeys(),
    }

    with open(OUT, "w") as handle:
        json.dump(collection, handle, indent=2)

    steps = sum(len(j["item"]) for j in collection["item"])
    print(f"Wrote {OUT}: {len(collection['item'])} journeys, {steps} steps.")


if __name__ == "__main__":
    build()
