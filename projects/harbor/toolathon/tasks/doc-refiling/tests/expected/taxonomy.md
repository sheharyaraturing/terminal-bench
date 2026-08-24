# Filing taxonomy

Every document belongs in exactly one of these folders:

- `Finance/Invoices`
- `Finance/Receipts`
- `HR/Contracts`
- `HR/Policies`
- `Legal/NDAs`
- `Legal/Litigation`
- `Operations/Reports`
- `Operations/Logs`

## How to decide

Each document carries a `Document-Type:` header on its first line. That header is
the authority on where the document belongs. Filenames are unreliable — many were
renamed by hand during the migration and no longer describe their contents.

| `Document-Type:` | folder |
| --- | --- |
| Invoice | `Finance/Invoices` |
| Receipt | `Finance/Receipts` |
| Employment Contract | `HR/Contracts` |
| Policy | `HR/Policies` |
| Non-Disclosure Agreement | `Legal/NDAs` |
| Litigation Record | `Legal/Litigation` |
| Operations Report | `Operations/Reports` |
| System Log | `Operations/Logs` |
