#!/bin/bash
# ORACLE SOLUTION — the acceptance gate.
#
# Harbor runs this instead of an agent when invoked with `-a oracle`. Its output
# must satisfy EVERY claim in tests/reward.toml, because "oracle scores 1.0" is
# what proves the task is solvable and the verifier accepts a correct answer.
#
# WRITE TO BOTH PATHS. /logs/agent is what a shared-mode run reads;
# /logs/artifacts is what a SEPARATE verifier reads and the only one recorded
# into the trial. An oracle that only echoes to stdout scores 0.0 under
# environment_mode = "separate".
#
# Every figure below was read back out of the built fixture; see
# environment/fixtures/GROUND_TRUTH.md.

set -euo pipefail
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Marisol — here is the review of the Q2/Q3 posting detail. Headline: the extract
does not foot, but the whole of the difference comes from five entries. Setting
those aside, there are three further findings that a debits-versus-credits check
would never have surfaced, and two things that look like findings and are not.

SCOPE

The extract holds 400 posting lines making up 140 distinct entries, JE-0001
through JE-0140, covering periods 2024-04 to 2024-09 in USD, EUR and GBP.

1. ENTRIES THAT DO NOT FOOT

Exactly five entries have total debits that do not equal total credits:

  JE-0018  2024-04  USD  debits 12,400.00   credits 12,040.00   +360.00
  JE-0047  2024-05  USD  debits  8,750.00   credits  8,750.50     -0.50
  JE-0073  2024-06  USD  debits 45,000.00   credits  4,500.00  +40,500.00
  JE-0098  2024-07  GBP  debits  3,215.75   credits  3,251.75    -36.00
  JE-0121  2024-08  USD  debits 19,880.00   credits 21,000.00   -1,120.00

The largest by a wide margin is JE-0073, out by 40,500.00: the debit is
45,000.00 and the credit 4,500.00, which is a one-decimal-place shift on the
credit side of a bonded-warehouse stock transfer, not a genuine 40,500.00
difference in the underlying transaction. JE-0018 at +360.00 has the signature
of a digit transposition (12,400 against 12,040); JE-0098 at -36.00 likewise
(3,215.75 against 3,251.75). JE-0047 is a half-cent-scale rounding artefact at
-0.50 and JE-0121 is a 1,120.00 over-release of deferred licence revenue.

Aggregate exposure of the five: the signed total of debits minus credits is
39,703.50. Taking absolute values instead gives 42,016.50; the signed figure is
the one that reconciles to the file.

Whole-file totals: debits 3,828,680.79 against credits 3,788,977.29, a
difference of 39,703.50 — exactly the five entries above and nothing else.

Take those five out and the rest of the book is clean: both sides land on
3,739,435.04, a difference of 0.00. So there is no
diffuse balance problem in the extract. Fix the five and the trial balance ties.

2. FINDINGS A DEBITS-VERSUS-CREDITS CHECK CANNOT SEE

2a. JE-0064 was posted after its period had been closed.

JE-0064 is booked to period 2024-05 and was posted on 2024-06-19. Period 2024-05
was closed on 2024-06-07, so the posting landed 12 days after the close. It is
26,750.00 USD, a May sublease charge that was left out of the accrual run,
debited to 5400 Facilities Expense and credited to 2010 Accounts Payable.

This is the only entry in the extract in that position. It matters that the test
is against the close date and not against the period month: five other entries
are also posted outside their own period month and all five are legitimate,
because they were posted before their period's close —

  JE-0029  period 2024-04  posted 2024-05-02  (closed 2024-05-08)
  JE-0058  period 2024-05  posted 2024-06-03  (closed 2024-06-07)
  JE-0082  period 2024-06  posted 2024-07-05  (closed 2024-07-05)
  JE-0091  period 2024-07  posted 2024-08-01  (closed 2024-08-06)
  JE-0112  period 2024-07  posted 2024-08-05  (closed 2024-08-06)

JE-0064 balances perfectly — debits 26,750.00 equal credits 26,750.00 — so no
debits-versus-credits test, and no reading of the journal extract on its own,
could have surfaced it. The close dates are not carried in the posting detail at
all; they live in the period-close register, and the finding only exists once the
two are joined.

2b. JE-0106 is a reversal that does not reverse.

JE-0079 (period 2024-06) booked the Q2 statutory audit fee for Hansen & Roth
GmbH: debit 5210 Professional Fees 18,450.00, credit 2010 Accounts Payable
18,450.00, denominated in EUR. JE-0106 (period 2024-07) was raised as "Reversal
of JE-0079 — invoice cancelled": debit 2010 Accounts Payable 18,450.00, credit
5210 Professional Fees 18,450.00 — denominated in USD.

The amount was reversed; the currency was not carried over. The two entries
therefore do not offset. Both of them balance internally, which is why the
imbalance work in section 1 does not touch them, and why an entry-level
debits-equal-credits control will never flag this.

The residual sits on account 5210 Professional Fees, which nothing else in the
extract touches: a net debit of 18,450.00 EUR that was never cleared, against a
net credit of 18,450.00 USD that was never posted in the first place. In other
words the euro audit-fee expense is still on the books and a dollar expense of
the same face value has been removed that never existed. The pair only appears
to net to zero if the currency is ignored.

For completeness, the other four reversal pairs in the extract are clean, with
matching currencies on both sides: JE-0024/JE-0035 (7,325.00 USD),
JE-0041/JE-0052 (2,140.60 GBP), JE-0088/JE-0095 (5,610.00 USD) and
JE-0109/JE-0117 (9,880.00 EUR).

2c. JE-0138 is a reversal booked to the wrong account.

JE-0131 (period 2024-08) booked a Q3 catch-up depreciation charge on plant and
equipment: debit 6100 Depreciation Expense 15,300.00, credit 2100 Accrued
Liabilities 15,300.00, in USD. JE-0138 (period 2024-09) was raised as "Reversal
of JE-0131": debit 2100 Accrued Liabilities 15,300.00, credit 5400 Facilities Expense
15,300.00, also USD.

The currency matches and the amount matches, and JE-0138 balances internally, so
a currency check, an amount check and an entry-level footing control all pass. But
a correct reversal of JE-0131 would credit 6100, the account the original charged.
JE-0138 credits 5400 instead. So the 15,300.00 depreciation charge on 6100 is
never actually reversed, and 15,300.00 has been wrongly credited to 5400
Facilities Expense. The reversal offsets on paper but not on the account it names.

3. NOT FINDINGS — do not put these in the memo

JE-0055 is not out of balance. Both of its lines carry 0.00 debit and 0.00
credit, against 1600 Prepaid Expenses and 2100 Accrued Liabilities, memo
"Placeholder — annual broker insurance accrual, amount pending confirmation".
Zero equals zero, so it foots; it is a legitimate placeholder awaiting the
broker's number, not an imbalance and not a finding. Any control that flags
zero-amount lines will pick it up, and that control is wrong here.

JE-0082 is not a post-close posting. It is booked to period 2024-06 and posted
on 2024-07-05, and 2024-07-05 is the close date for 2024-06 — not a date after
it. The books were still open that day, so the entry is a normal final close
adjustment (14,200.00 USD of June commission accrual). It sits one day either
side of a genuine breach and should not be reported alongside JE-0064.

RECOMMENDATION

Correct the five imbalances in section 1 — JE-0073 first, it is 96 percent of
the exposure. Re-open 2024-05 or push JE-0064 into an open period, and either
way get it into the auditors' late-entry log. Re-raise the JE-0079 reversal in
EUR and back out JE-0106. Re-book JE-0138 to credit 6100 rather than 5400 so the
depreciation charge is actually reversed. Nothing else in the extract needs an
adjustment.
EOF
