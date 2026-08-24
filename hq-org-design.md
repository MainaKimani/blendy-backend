# Design — HQ Organization and Platform Access

**Status:** v4 — T1–T8 built, plus all three follow-ups
**Date:** 2026-08-24
**Branch:** `blendy-upgrade`
**Scope:** A platform-level organization for Blendy's own staff, the roles they hold, and the audited path by which they reach a tenant's data.

---

## 1. Problem

Today "platform staff" means one boolean on one user:

```
createsuperuser -> is_superuser_admin=True  is_superuser=True  organization=None
```

That user sits outside every organization. It works for the one thing it was built for — onboarding a shop — and stops there:

| | Today |
|---|---|
| Onboard an organization | ✅ |
| Create staff inside a named shop | ✅ |
| **Read a shop's sales/stock/prices to support them** | ❌ `403` |
| **Create another platform user** | ❌ shell only |
| **Distinguish support from billing from engineering** | ❌ one boolean |

The third row is the operational blocker: we can create a shop and then cannot help it. `IsOrganizationUser` compares `user.organization` to `request.organization`, and a superadmin's is `None`, so it never matches — for any tenant.

The fourth is a bootstrap dead end: `is_superuser_admin` is absent from `CustomUserSerializer.fields`, so `POST /api/users/ {"is_superuser_admin": true}` returns **201 with the flag silently `False`**.

As more organizations onboard, we need a place to manage them — support, troubleshooting, and later subscriptions — rather than a shell.

## 2. Decisions

### 2.1 HQ is a real Organization

Rather than a second, parallel notion of "platform user", HQ becomes an `Organization` flagged `is_platform`.

**The reason is the existing RBAC.** Permissions already resolve per organization:

```python
self.role_assignments.filter(
    organization_role__organization_id=self.organization_id
)
```

So platform staff get roles through machinery we already have — `SUPPORT_AGENT` and `PLATFORM_ADMIN` as `Role` rows enabled for HQ, assigned through the same `/api/users/` flow a shop uses for its cashiers. **Permission resolution needs no change at all.**

The alternative — keeping platform staff outside the tenant model and adding flags — means building a second permission system that will drift from the first. We would be maintaining RBAC for tenants and booleans for ourselves.

### 2.2 `is_superuser_admin` stays, as break-glass

The flag is retained as an **unconditional bypass**, matching Django's own `is_superuser` convention. HQ roles are the granular, delegable layer above it.

- A superadmin need not belong to HQ, though normally will.
- Every existing superadmin surface — `IsSuperAdminUser`, `/organization/onboard/` — keeps working untouched.
- Retiring the flag is explicitly **not** in scope.

Practically: the flag is how you get in when the role system itself is what's broken. Day-to-day work should go through roles, because those are auditable and revocable per person.

### 2.3 Cross-tenant access is one gate, then the existing checks

A single new permission, `platform.access_tenants`, widens `IsOrganizationUser`. Once a caller is across the boundary, the **normal per-action permissions decide what they may do**.

```
IsOrganizationUser        →  member of this org
                          OR is_superuser_admin
                          OR holds platform.access_tenants      ← the new gate
                             (+ platform.act_as_tenant to write)

HasUserPermission(...)    →  unchanged
```

So `SUPPORT_AGENT` holds `platform.access_tenants` plus the tenant `view_*` set. **Read-only falls out for free** — they hold no `add_`/`change_`/`delete_`, so the existing checks refuse writes without any new machinery.

This is the whole point of reusing the catalogue rather than inventing a platform-specific one.

## 3. Model changes

```python
class Organization(models.Model):
    is_platform = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_platform"],
                condition=models.Q(is_platform=True),
                name="only_one_platform_organization",
            )
        ]
```

A partial unique constraint, so there can only ever be one HQ. The database enforces it rather than a convention.

```python
class PlatformAccessLog(models.Model):
    actor, organization, method, path, status_code, created_at
```

Deliberately **not** an `OrganizationBaseModel`: it records access *to* a tenant by someone outside it, so tenant-scoping it would let the subject edit the record of who read their data.

## 4. What breaks the moment HQ exists

Three call sites assume every `Organization` is a customer. All three are regressions, not enhancements, and are contained in **T3** before anything else ships.

**4.1 C2B reconciliation — live bug**

```python
organizations = list(Organization.objects.all()[:2])
if len(organizations) == 1:
    return organizations[0]
```

Creating HQ makes that count 2, so the single-shortcode fallback stops firing and direct-payment reconciliation breaks for single-tenant deployments. Worse, `[0]` is arbitrarily ordered — it could return HQ and attribute a shop's money to us.

**4.2 `is_platform` would be client-writable**

`OrganizationSerializer` uses `fields = '__all__'`. Anyone able to create an organization could mint a second platform org. Must be read-only; the unique constraint is the backstop.

**4.3 HQ would be seeded as a shop**

`enable_default_roles()` iterates `Organization.objects.all()`, so HQ would get `CASHIER` and `VIEWER`. Onboarding would also give it a `Default Pricelist`. Harmless but incoherent — an HQ that looks like it might sell sugar.

## 5. Audit

**Ships in the same change as cross-tenant access, never after.** Once reads are live without logging, the window in which we cannot answer *"who looked at my takings?"* is permanent. For a Kenyan SME asking that about their own revenue, "we didn't record it" is not an acceptable answer.

Recorded by middleware rather than the permission class, so it captures denials as well as grants, and cannot be bypassed by a view that forgets to call it. Exposed read-only to HQ under `platform.view_access_log`.

## 6. Tasks

| | Task | Size | Depends | |
|---|---|---|---|---|
| **T1** | `Organization.is_platform` + single-HQ constraint + read-only in serializer | S | — | ✅ |
| **T2** | Create HQ: data migration + `manage.py bootstrap_hq` | S | T1 | ✅ |
| **T3** | Keep HQ out of tenant surfaces *(the three regressions in §4)* | M | T1 | ✅ |
| **T4** | `platform.*` permissions, `SUPPORT_AGENT` / `PLATFORM_ADMIN` roles | M | T1, T3 | ✅ |
| **T5** | Cross-tenant gate in `IsOrganizationUser` | M/L | T4 | ✅ |
| **T6** | `PlatformAccessLog` + middleware + endpoint | M | T5 | ✅ |
| **T7** | HQ staff management; `PLATFORM_ADMIN` may onboard | S/M | T4 | ✅ |
| **T8** | Docs, journeys, regenerate swagger + collections | S | all | ✅ |
| **T9** | `GET /api/organization/platform/` — HQ discoverable through the API | S | T4 | ✅ |
| **T10** | Access log retention: window, floor, `prune_access_log` | S | T6 | ✅ |
| **T11** | Tenant-facing access log, with cross-tenant identities withheld | S | T6 | ✅ |

```
T1 ──┬── T2
     └── T3 ──── T4 ──┬── T5 ── T6   (one PR)
                      └── T7
                                └── T8
```

**T1–T3 change no behaviour for any shop.** That is the safe foundation and lands on its own.

Tests belong inside each task, not in a phase at the end.

## 7. Risk

**T5 is the one to review.** It relaxes the tenant boundary that several previous passes were spent tightening. Mitigations:

- The gate is a **permission**, not a flag — auditable, revocable per person, and grantable to a support agent without granting write.
- Writes need a second permission (`platform.act_as_tenant`) that `SUPPORT_AGENT` does not hold.
- Every crossing is logged (T6).
- A test matrix across member / HQ support / HQ admin / superadmin / outsider, for read and write, on every app.

## 8. Out of scope

- **Subscriptions and billing** — Phase 2. Note `subscription_plan`, `subscription_expires_at` and `status=SUSPENDED` are declared today and **read by nothing**; a suspended organization trades normally. Enforcing `status` is independent of this work and worth doing early.
- **Support tickets and chat** — needs T1–T6 first. Afterwards a ticket is straightforward: `organization` is the shop it concerns, the shop sees its own through normal scoping, HQ sees all through T5.
- **Retiring `is_superuser_admin`** — see §2.2.

## 9. Found while building

Three defects surfaced that the design did not anticipate. All are fixed.

**One shop could administer another.** `CustomUserViewSet` applied `IsOrganizationUser` only to `update`, while its queryset and `perform_create` both took the organization from the header. The admin of one shop could list and create users inside another by changing it. Pre-existing, unrelated to HQ, and closed in T7.

**`ProductVariationViewSet` filtered by the caller's own organization** on top of the tenant header. Identical for a member, so invisible — but platform staff acting as a tenant got an empty list. Found by the T5 matrix.

**`ORG_ADMIN` is derived from a pool**, so adding `platform.*` to the catalogue would have handed every shop owner cross-tenant access. Caught by splitting the pools in T4; three existing tests failed at exactly the right moment.

## 10. Open questions

1. **HQ naming.** The migration creates it as "Blendy HQ" / `blendy-hq`. Configurable via `bootstrap_hq --name`.
2. **Should HQ staff appear in a shop's `/api/users/` listing?** Proposed: no — they are not that shop's staff. Their access shows in the audit log instead.
3. ~~**Retention on `PlatformAccessLog`.**~~ **Settled (T10).** 365 days by default, with a 30-day floor the prune command refuses to go below. Pruning is a cron job; nothing prunes itself.
4. ~~**HQ's id is not discoverable through the API.**~~ **Settled (T9).** `GET /api/organization/platform/`, open to any holder of a `platform.*` permission — a support agent needs it as much as an admin does.
5. ~~**Should a shop see who accessed *their* data?**~~ **Settled (T11).** `GET /api/organization/access-log/`, held by ORG_ADMIN. Blendy staff are named; another customer whose access was refused appears but is not identified, which required recording `actor_is_platform` at write time rather than deriving it on read.
6. **Should a shop be notified, rather than having to look?** The log answers the question only if someone thinks to ask it. There is no mail backend or worker in this deployment, so this would start as a digest endpoint rather than a push. Not built.
