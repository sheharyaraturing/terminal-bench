The vendor register has collected duplicate records over several system migrations, and finance wants one row per real vendor before the next payment run.

`vendor_master.xlsx` is the register. `policy/Data_Governance.docx` is the standard that governs how vendor records are consolidated. `Format_Example.xlsx` carries the header row each deliverable must use.

Produce two workbooks in the workspace root:

- `vendor_master_merged.xlsx` — a sheet named `VendorMaster` holding the register as it stands once the standard has been applied.
- `merge_log.xlsx` — a sheet named `MergeLog` with the columns `Survivor`, `Losers`, `FieldsTaken` and `Status`, carrying one row for each group of records the standard links to one another.
