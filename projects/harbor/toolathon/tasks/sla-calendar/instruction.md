The service desk needs its response-time report for the tickets in the export.

`tickets.xlsx` holds them. `sop/Support_SLA.docx` is the authority on how a response deadline is set and when a ticket counts as breached; the reference data that SOP depends on sits in the workspace alongside it.

Produce two files in the workspace root:

- `sla_report.xlsx`, with the columns `Ticket`, `Severity`, `Deadline` and `Breached`.
- `sla_exceptions.csv`, with the columns `Ticket` and `Reason`.

The SOP defines every term used above, including which tickets belong in each file and how each value is written.
