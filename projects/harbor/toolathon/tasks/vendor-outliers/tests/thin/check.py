"""Fraction of single-month vendors carried through as INSUFFICIENT_HISTORY.

Graded apart from the exceptions because dropping them is the failure the
policy warns about: they can never be an exception, and they must still appear.
"""

import rewardkit as rk

rk.register_rows("INSUFFICIENT_HISTORY")
