# Authorization matrix

This is the fail-closed application policy for Project A. Auth0 authenticates a
user and supplies immutable tenant and role claims; the application independently
enforces capabilities, tenant predicates, and sensitivity filters at every data
or action boundary.

| Capability | Founder/CFO | Logistics manager | Staff accountant | Support intern |
| --- | --- | --- | --- | --- |
| Basic assistant | Allow | Allow | Allow | Allow |
| General document search | Allow | Allow | Allow | Allow |
| Supplier price/payment terms | Allow | Deny | Deny | Deny |
| Stockout analytics | Allow | Allow | Deny | Deny |
| Freight reconciliation | Allow | Deny | Allow | Deny |
| Overdue-invoice analytics | Allow | Deny | Allow | Deny |
| Margin analytics | Allow | Deny | Deny | Deny |
| Upload tracking events | Allow | Allow | Deny | Deny |
| Upload vendor invoices | Allow | Deny | Allow | Deny |
| Upload documents | Allow | Allow | Allow | Deny |
| Draft purchase order | Allow | Allow | Deny | Deny |
| Draft carrier dispute | Allow | Deny | Allow | Deny |
| Draft payment reminder | Allow | Deny | Allow | Deny |
| Draft delay advisory | Allow | Allow | Deny | Allow |

Document retrieval is further limited by sensitivity:

| Role | Visible sensitivities |
| --- | --- |
| Founder/CFO | public, support, operations, accounting, executive |
| Logistics manager | public, support, operations |
| Staff accountant | public, accounting |
| Support intern | public, support |

## Enforcement boundaries

- **API:** every `/api/v1` business route requires `AuthContext`; only health is public.
- **Agent/tool:** model-selected intent and route are checked against the capability matrix
  before any tool executes. Tool services repeat authorization independently.
- **SQL:** fixed read-only parameterized statements always receive the authenticated tenant
  and contain explicit tenant predicates on base tables and joins.
- **Qdrant:** both dense and sparse prefetches plus the fusion query carry mandatory tenant
  and sensitivity filters; returned payloads are checked again before use.
- **Documents/uploads:** the authenticated tenant is injected server-side, uploaded tenant
  fields cannot override it, resource roles and document sensitivities are checked at preview,
  read, and commit.
- **Actions/approvals:** server policy determines draft risk, drafter roles, and approver roles;
  tenant and role are checked before and again during durable resume. Approved artifacts remain
  drafts and cannot be externally submitted.

The executable policy lives in `business_brain.security.policy`. Automated tests require every
capability to have a non-empty explicit role set and prevent future API routes from accidentally
being added without authentication.
