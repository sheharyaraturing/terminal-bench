# Internal retention-platform fork

This repository is a synthetic internal fork used for the retention-control exercise. Its root imports the audited `qfs_filelock.py` source and MIT license from Qumulo/filelock commit `debde74347f4147d0d2c745b1e4d98c1c64dfa74`. `UPSTREAM_PROVENANCE.md` records the source hashes. Unrelated upstream deployment examples and tests are intentionally absent from this sanitized fixture.

Everything under `platform_retention/`, `policies/`, `reports/` and `deploy/` was authored for this exercise. Those files do not describe Qumulo software and must not be read as an allegation about the upstream project. Any behavior introduced by those synthetic additions is attributable to the internal exercise code, not to Qumulo/filelock.
