"""Fraction of FLAGGED rows that match the per-vendor outlier rule.

Each vendor is judged against its own mean and population standard deviation
across the months it appears in, so a company-wide baseline lands here as a
wrong row set rather than as a rounding difference.
"""

import rewardkit as rk

rk.register_rows("FLAGGED")
