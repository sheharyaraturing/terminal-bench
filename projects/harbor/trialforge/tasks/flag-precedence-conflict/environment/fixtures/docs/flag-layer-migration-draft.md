# Flag layer simplification proposal

Status: draft
Approval: pending
Last updated: 2026-07-02
Target release: prod-2026.09.1

The proposed September loader removes the shared staging overlay from
production. Production would load `default.json`, then `prod.json`, and would
not apply cohort overrides. The rollout and approval fields will be completed
during release planning.

The billing PDF cleanup spreadsheet used during discovery still lists
`billing.legacy_invoice_pdf`, which is why the name appears in historical
material even if it is absent from the application build.
