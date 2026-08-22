# Blendy Backend — N+1 Query Report

**Status:** v4 — **all six fixes implemented, plus all three adjacent defects**
**Date:** 2026-08-22
**Branch:** `blendy-upgrade`
**Scope:** Every list/detail endpoint exposed by `blendy_backend/urls.py`, plus the sale write path and the RBAC permission check.
**Suite:** 141 passing (was 109) · no migration drift · `manage.py check` clean

> **v2 note:** Every endpoint in §1 now serves a **constant** number of queries regardless of row count. `/api/products/` went from **323 queries for 20 products to 9**. The measurements below are re-taken with `uom` and `currency` populated, which is the realistic case and harsher than the v1 figures. Fourteen `assertNumQueries`-style regression tests now guard the flat profile (§6).
>
> **v4 note:** The defects found alongside the performance work are now **also fixed** — the `*_id` fields that returned names (§5.1), the role-assignment endpoint that raised `FieldError` on every request (§5.2), and the organization-role endpoint whose create could never succeed (§5.4). Fixing the second exposed a third N+1 that had been invisible because the endpoint never ran a query at all (§5.3).

---

## 0. Method

These numbers are measured, not estimated.

A probe seeded one tenant with **N products × 2 variations**, each priced on the default pricelist and stocked through the ledger, plus one sale of 2 lines and one payment per product. It then counted queries per endpoint with `CaptureQueriesContext` at n=1 and n=20, and grouped the normalised SQL so every query could be attributed to the serializer field or model property that issued it.

The before/after columns in §1 are both measured against the same seed, with the fixes stashed and unstashed — apples to apples.

**One methodological correction from v1.** The original probe left `uom` and `currency` null on every variation, so the nested `UOMSerializer` / `CurrencySerializer` cost nothing. That understated the problem and, worse, **hid an N+1 entirely**: `/api/inventory/stock/low-stock/` looked flat at 3 queries but actually costs 23 for 20 rows once units of measure are recorded, because `ProductVariation.name` reads `self.uom.symbol` (§2.8). All figures below have both fields populated, and the regression tests in §6 populate them too, for exactly this reason.

---

## 1. Results

| Endpoint | before n=1 | before n=20 | **after n=1** | **after n=20** |
|---|---|---|---|---|
| `GET /api/products/` | 19 | **323** | **9** | **9** |
| `GET /api/products/with-price/` | 15 | 243 | **8** | **8** |
| `GET /api/products/variations/` | 15 | 123 | **5** | **5** |
| `GET /api/sales/sales/` | 9 | 123 | **7** | **7** |
| `GET /api/sales/sales/pending-payments/` | 9 | 123 | **7** | **7** |
| `GET /api/sales/sale-items/` | 5 | 23 | **3** | **3** |
| `GET /api/payments/payments/` | 4 | 23 | **4** | **4** |
| `GET /api/inventory/stock/low-stock/` | 5 | 23 | **3** | **3** |
| `GET /api/inventory/stock-movements/` | 3 | 3 | 3 | 3 |
| `GET /api/inventory/inventory-items/` | 3 | 3 | 3 | 3 |
| `GET /api/pricing/pricelist-items/` | 3 | 3 | 3 | 3 |
| `GET /api/authorization/user-role-assignments/` | *500* | *500* | **11** | **11** |
| `GET /api/authorization/organization-roles/` | 2 | 2 | 4 | 4 |

Every row is now **flat** — identical at 1 row and at 20.

Two more, measured separately:

| Path | before | after |
|---|---|---|
| RBAC check, user holding 10 roles | 23 queries | **4** |
| `POST /api/sales/sales/`, marginal cost per line | 10.0 | **7.0** |

---

## 2. What was wrong, and what changed

### 2.1 `ProductVariationSerializer.get_price` — was 3 queries per variation ✅
`products/serializers.py`

```python
def get_price(self, obj):
    pricelist = get_default_pricelist(obj.organization)      # (1) FK fetch  (2) pricelist SELECT
    return get_price(pricelist, obj) if pricelist is not None else None   # (3) item SELECT
```

Three separate costs: `obj.organization` was a **foreign-key traversal**, the default pricelist was **re-resolved for every variation** despite being identical for the whole response, and the price was fetched one row at a time.

**Now:** the pricelist is resolved once into serializer context, keyed by tenant id (a response may legitimately span tenants). `obj.organization_id` replaces `obj.organization`, so no FK fetch. The price is read from a prefetched `pricelist_items` in Python — free when prefetched, and the same single query it always was when not.

`ProductVariationWithPriceSerializer.get_price` already used `organization_id` correctly; it now shares the same prefetch-served lookup.

### 2.2 `ProductSerializer` image and size methods bypassed the prefetch ✅
`products/serializers.py`

```python
obj.variations.values_list("size", flat=True)    # values_list always hits the DB
obj.images.filter(is_primary=True).first()       # .filter() re-queries
obj.images.filter(is_primary=False)              # .filter() re-queries
```

Three extra queries per product. **`prefetch_related` alone would not have fixed these** — `.values_list()` and `.filter()` on a related manager both bypass the prefetch cache and issue fresh SQL. A fix touching only `get_queryset` would have looked right and measured unchanged.

**Now:** all three iterate `obj.images.all()` / `obj.variations.all()` and filter in Python, with a comment saying why, so the next person does not "tidy" it back into a `.filter()`.

### 2.3 Querysets carried no `select_related` / `prefetch_related` ✅

| Queryset | Added |
|---|---|
| `products/views.py` `ProductViewSet` | `select_related("category")` + `prefetch_related("images", "variations__uom", "variations__currency", "variations__pricelist_items")` |
| `products/views.py` `ProductVariationViewSet` | `select_related("product", "uom", "currency")` + `prefetch_related("pricelist_items")` |
| `products/views.py` `ProductWithPriceViewSet` | same as `ProductViewSet` (it shares the serializer shape) |
| `sales/views.py` `SaleViewSet` | `prefetch_related("items__product_variation", "payments__transactions")` |
| `sales/views.py` `SaleItemViewSet` | `select_related("product_variation")` |
| `payments/views.py` `PaymentViewSet` | `prefetch_related("transactions")` alongside the existing `select_related("sale")` |

`ProductVariation.name` is a property reading `self.product.name` and `self.uom.symbol`, so `select_related("product", "uom")` is what keeps `/variations/` flat — not merely a nested-serializer concern.

### 2.4 `Sale.total_amount` double-queried the lines ✅
`sales/models.py`

Each sale cost **two** `SaleItem` queries — once for the nested `items` serializer and once for `total_amount`'s `self.items.all()`.

Self-correcting: with `prefetch_related("items")` both calls hit the same cache. No change to the model was needed.

### 2.5 `SaleItemSerializer.product` traversed a FK per line ✅
`sales/serializers.py`

```python
product = serializers.PrimaryKeyRelatedField(source="product_variation.product", read_only=True)
```

One query per line to fetch a whole `Product` row and emit its id.

**Now:** `serializers.UUIDField(source="product_variation.product_id")` — `product_id` is a local column on the variation, so nothing is fetched. The rendered JSON is byte-identical; only the pre-render Python type changes (`UUID` → `str`), and nothing in the codebase reads it.

### 2.6 `has_perm` — was 3 queries per role assignment, per request ✅
`users/models.py`, `users/permissions.py`

```python
for assignment in self.role_assignments.filter(...):
    for permission in assignment.organization_role.role.permissions.all():
```

Three queries per iteration, and it **returned early on the first match** — so the cost depended on role ordering, and the worst case was a permission the user did *not* hold, which is exactly the path a denied request takes. Measured at 23 queries for a user holding 10 roles.

**Now:** `CustomUser.get_permission_names()` resolves the whole set in **one** query.

The cache placement is the part worth knowing. Caching on the user instance is what Django's own `PermissionsMixin` does, and it was the first thing tried — but it **fails a test that revokes a role and re-checks**, because `force_authenticate` reuses one user object across requests. That is not just a test artefact: any code holding a user object across a permission change would keep the stale answer, and the failure mode is granting access that has since been revoked. The cache therefore lives on the **request** (`HasUserPermission._permission_names`), where it cannot outlive the check it was resolved for. Several permission checks in one request still share it.

### 2.7 Sale write path — was 10 queries per line ✅
`sales/serializers.py`, `pricing/services.py`

Avoidable costs removed:
- **`get_default_location()` re-queried per line** (`inventory/services.py`) — the same location, resolved from scratch inside every `record_movement` call. Now resolved once per sale and passed in, including on the edit-reversal path.
- **`require_price()` re-queried per line** — replaced by `pricing.services.get_prices()`, one query for the whole basket.
- **The response re-queried the created sale** — a freshly created `Sale` has no prefetch cache, so rendering it walked back to the database for its lines, again for `total_amount`, and once per line for the variation. `prefetch_related_objects()` now populates those caches in a fixed number of queries.

**10.0 → 7.0 per line.** The remaining seven are close to the floor: four writes (line insert, locking read of the balance, ledger insert, balance update), the savepoint pair that `record_movement`'s `@transaction.atomic` opens, and one `PrimaryKeyRelatedField` validation lookup.

**The locking queries were deliberately left alone.** `SELECT … FOR UPDATE` on `InventoryItem` is the oversell guard. It is not overhead.

### 2.8 `/api/inventory/stock/low-stock/` — an N+1 v1 reported as clean ✅
`inventory/views.py`

v1 of this report called this endpoint "already flat" and "the one deliberate case". That was wrong, and it was wrong because of the seed: `LowStockItemSerializer` exposes `product_variation.name`, and that property reads `self.uom.symbol`. The view's `select_related` covered `product_variation__product` but not `__uom`, so with units of measure recorded it cost **23 queries for 20 rows**, not 3.

**Now:** `product_variation__uom` is joined too. Back to 3, flat.

The lesson is in the method, not the code: a seed that leaves optional fields null will certify an N+1 as clean.

---

## 3. Files changed

| File | Change |
|---|---|
| `products/serializers.py` | pricelist resolved once per response; image/size methods serve from prefetch; unused imports dropped |
| `products/views.py` | prefetching on all three product viewsets |
| `sales/serializers.py` | basket-wide price and location resolution; `product` reads `product_id`; response prefetched |
| `sales/views.py` | prefetching on both sale viewsets |
| `payments/views.py` | `transactions` prefetched |
| `pricing/services.py` | new `get_prices()` — batch lookup for a basket |
| `inventory/views.py` | `product_variation__uom` joined for low-stock |
| `users/models.py` | `get_permission_names()` — one query, uncached by design |
| `users/permissions.py` | request-scoped permission cache |
| `products/serializers.py` | `*_id` fields read their id columns (§5.1) |
| `authorization/views.py` | role assignments scoped through `organization_role`, read-only, prefetched, ordered (§5.2, §5.3); organization roles given a working create, prefetched, ordered (§5.4) |
| `authorization/serializers.py` | writable `role_id` on `OrganizationRoleSerializer` (§5.4) |
| `blendy_backend/tests_query_counts.py` | **new** — 14 query-count regression tests |
| `products/tests_id_fields.py` | **new** — 4 tests |
| `authorization/tests.py` | **new** — 14 scoping, write-path and N+1 tests |

No migrations. No model-field changes.

**One visible API change:** `product_id`, `uom_id` and `currency_id` on a variation now return ids instead of names (§5.1). Everything else is either identical output or the removal of endpoints that returned `500` (§5.2).

---

## 4. Why `/api/products/` was fixed first

`ProductViewSet.get_permissions` returns `[]` for `list` and `retrieve`. The worst N+1 in the codebase — **323 queries for 20 products** — was reachable **without a token and without an `X-Organization` header**. It was not merely the slowest endpoint; it was the slowest endpoint anyone on the internet could trigger at will.

---

## 5. Defects found alongside the performance work — now fixed

None was an N+1. All were found because the probe exercised endpoints the suite never touched.

### 5.1 `product_id`, `uom_id` and `currency_id` returned names, not ids ✅

`ProductVariationSerializer` declared:

```python
product_id  = serializers.UUIDField(read_only=True, source="product")
uom_id      = serializers.UUIDField(read_only=True, source="uom")
currency_id = serializers.UUIDField(read_only=True, source="currency")
```

`UUIDField.to_representation` is `str(value)`, and `value` here was the **model instance**, not its id — so `str()` fell through to `__str__`, which returns the name. Measured against `/api/products/variations/` before the fix:

```
actual product id   : 492f062b-05bf-412f-9500-9be5b4107afd
response product_id : 'Sugar'
response uom_id     : 'Kilogram'
response currency_id: 'Shilling'
```

Three fields named `*_id` that had never once returned an id — and each cost a foreign-key fetch per row to produce the wrong value.

**Now:** the `source` is dropped, so each field reads its own `*_id` column. No fetch, correct value.

**This changed response content.** Any client that was reading `product_id` as a display name will now receive a UUID. That is the point of the fix, but it is the one change in this whole pass that is visible to a consumer, so it is called out here rather than buried. `uom_id` and `currency_id` are nullable and render as `null` when unset — covered by a test, since `UUIDField` on a null relation is exactly the kind of thing that breaks quietly.

Covered by `products/tests_id_fields.py` (4 tests), each asserting both that the value *is* the id and that it is *not* the name.

### 5.2 `GET /api/authorization/user-role-assignments/` raised `FieldError` ✅

```
FieldError: Cannot resolve keyword 'organization' into field.
Choices are: assigned_at, id, organization_role, organization_role_id, user, user_id
```

`UserRoleAssignmentViewSet` extends `OrganizationBaseViewSet`, whose `get_queryset` filters on `organization=…` — but `UserRoleAssignment` has no `organization` column. It is tenanted **transitively**, through `organization_role`.

The inherited scoping was not merely wrong, it was **inert**: the filter referenced a field that does not exist, so every request raised before a single row was read. The tenant isolation the base class was assumed to be providing had never once been applied to this model.

`POST` was broken too, differently: `serializer.save(organization=…)` passed a phantom keyword to `UserRoleAssignment.objects.create()` and raised `TypeError`.

**Now:**

- `get_queryset` filters on `organization_role__organization`, and still fails closed — no tenant means no rows, never all rows.
- The viewset is **read-only** (`http_method_names = ["get", "head", "options"]`), matching the precedent set by `StockMovementViewSet`. The create path could not work regardless: both of the serializer's relations are read-only, so there was nothing to write. Roles are already assigned through `/api/users/` via `organization_role_ids`, which resolves the role *inside the caller's tenant* before assigning it — so nothing is lost, and there is no second privilege-granting write path to keep in step with the first.
- `order_by("-assigned_at", "id")` was added, because paginating an unordered queryset can drop or repeat rows between pages.

### 5.3 The N+1 that was hiding behind the 500 ✅

Fixing the scoping made the endpoint reachable — and it was immediately an N+1, at roughly **8 queries per row**. `UserRoleAssignmentSerializer` nests the user (whose own `assigned_roles` walks back through *its* assignments), the organization role, that role's permissions, and the organization.

Measured with the scoping fixed but no prefetching: **91 queries for 11 rows**. With `select_related` and `prefetch_related` in place: a flat **11**, verified by stripping the prefetching back out and confirming the regression test fails.

This is why the fix and its test landed together. A scoping fix that quietly shipped an 8-per-row N+1 would have traded a loud failure for a silent one.

### 5.4 `POST /api/authorization/organization-roles/` could never succeed ✅

The same shape as §5.2: `OrganizationRoleSerializer` declared both `role` and `organization` read-only so the response could nest them in full, which left nothing writable. A create wrote no role and died on the not-null column.

Its `GET` worked, because `OrganizationRole` *does* have an `organization` column — so unlike §5.2 this one was not raising in anyone's face, which is why it survived unnoticed.

**It could not be made read-only.** This is the *only* path that links a Role to an Organization: onboarding creates the ORG_ADMIN link and registration creates the Viewer one, and nothing else in the codebase creates another. Closing it would have meant an owner could never enable a role beyond those two, leaving the assignment flow on `/api/users/` — which only ever *reads* existing `OrganizationRole` rows — with nothing to offer. That is the opposite of §5.2, where a working, tenant-checked alternative already existed.

**Now:**

- A writable `role_id` field, so a caller supplies the role while the organization still comes from the tenant header. A body that names a different `organization` is ignored, not honoured — covered by a test.
- Enabling the same role twice returns **400**, not a 500. `organization` is set server-side, so DRF cannot build the `UniqueTogetherValidator` for it and the database constraint surfaced raw.
- `select_related` / `prefetch_related` for the nested role, its permissions and the organization, plus an explicit ordering.

The eight tests include the loop that matters end to end: enable a role, assign it to a cashier through `/api/users/`, and confirm the permission resolves. The duplicate guard was verified by removing it and watching the test fail on the raw `IntegrityError`.

## 6. Regression protection

**32 new tests**: `blendy_backend/tests_query_counts.py` (14, cross-app, so they live with the project rather than inside any one app), `products/tests_id_fields.py` (4), `authorization/tests.py` (14).

The assertion is **"same query count at 1 row as at 15"**, not "fewer than some number". An absolute ceiling drifts every time an unrelated query is added somewhere in the stack; the invariant that actually matters is that the slope is flat. A generous ceiling sits alongside it purely to catch fixed-cost blow-up.

Three properties the tests encode on purpose:

1. **`uom` and `currency` are populated in the seed.** Leaving them null is what hid §2.8.
2. **The RBAC test puts the needed permission on the *last* role.** The old implementation returned early on the first match, so granting it first would have measured its best case rather than its real one. A second test asserts a *denied* request costs no more than an allowed one.
3. **Failure messages name the cause, not the number** — "an N+1 has been reintroduced", "something that should be resolved once for the basket is being resolved per line again" — so a future failure is actionable without re-deriving this report.
4. **The tests were checked against reverted fixes.** The role-assignment N+1 test was run with the prefetching stripped back out, to confirm it fails (91 queries for 11 rows) rather than passing for the wrong reason; the duplicate-role guard was likewise removed and its test watched to fail on the raw `IntegrityError`. A test that has never been seen to fail is decoration.

---

## 7. Nothing left open

The three defects logged in earlier revisions of this report are all closed. `OrganizationRoleViewSet` was the last of them (§5.4).

One design note rather than a defect: `Role` is global and `role_id` accepts any of them, so an org admin can enable any globally defined role for their own organization. Permissions stay scoped to that organization — `get_permission_names()` filters on `organization_role__organization` — so this grants nothing outside the caller's own tenant. It is nonetheless worth deciding, when the RBAC seeding work (US-15) lands, whether the catalogue of roles an org admin may enable should be narrower than "every role in the system".
