# Support Contact Coverage — Q1 2025 run (closed)

Retained for continuity. **Period covered: 2025-01-01 to 2025-03-31.** Computed from the `2025-01-06` export — `customers_2025-01-06.csv` (91 data rows) and `tickets_2025-01-06.csv` (214 data rows) — which was archived to cold storage when the Q1 run was signed off.

| Figure | Q1 2025 |
|---|---|
| `customers_total` | 91 |
| `customers_with_contact` | 73 |
| `value` | 18 |
| `contact_rate` | 0.8022 |
| `orphan_tickets` | 2 |
| `soft_deleted_tickets` | 6 |
| `out_of_period_tickets` | 41 |

Notes carried over from that run:

- Customer Operations asked why the orphan count was non-zero. The answer was a ticket queue that accepts a free-text account reference, so a mistyped reference lands in the extract with no matching customer.
- The soft-delete convention was confirmed with the support tooling team in February 2025 and has not changed since.
- Q1's `contact_rate` was rounded under the same convention as section 6 of `Definitions.md`.
