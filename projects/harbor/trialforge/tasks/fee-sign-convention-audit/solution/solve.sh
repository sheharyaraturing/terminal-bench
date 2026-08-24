#!/bin/bash
set -euo pipefail

# Reference answer for this task. Every figure below is taken from the ledger at
# /data/CoinbaseTradeHistory.csv and the matching table in /data/db/turing.db.
#
# Write to BOTH paths: /logs/agent is what a shared-mode run reads, /logs/artifacts
# is what the SEPARATE verifier reads (see task.toml [verifier].environment_mode).
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Verdict up front: the fee data is fine and the P&L pack is wrong. The fee column
reconciles against the subtotal and total on all 111 rows, and the 40 negative values
that look alarming are a sign convention, not corruption. What is broken is the cell
that adds that column up. Fees actually paid over the ledger are about $218.71; the
pack reports about $102.47, understating the figure by about $116.24. That
understatement, not the smaller period error below, is the finding that matters.

1. THE LEDGER AND THE SIGN MIX

The trade ledger runs to 111 rows. Summing the fee column straight down gives
$102.47, and that is the number in the committee pack. It is too small, and the
reason is visible the moment you look at the signs rather than the total: 40 of the
111 rows carry a NEGATIVE fee value.

Breaking the column down by sign:

    negative fee     40 rows
    zero fee         48 rows
    positive fee     23 rows
                    ---
                    111 rows

2. THE NEGATIVES ARE NOT SCATTERED. THEY ARE ONE TRANSACTION TYPE.

This is the diagnostic part. The negatives are not spread across the ledger — every
single one of the 40 is transaction type "Advance Trade Sell", without exception. No
other transaction type ever carries a negative fee. Symmetrically, all 23 rows with
a positive fee are "Advance Trade Buy" rows, and nothing else.

So the partition is clean:

    Advance Trade Sell    42 rows -> 40 negative, 2 zero
    Advance Trade Buy     30 rows -> 23 positive, 7 zero
    everything else       39 rows -> all zero

The sign is a function of the side of the trade. That is a property of a booking
rule, not a property of a corrupted file.

3. IT IS A CONVENTION, NOT CORRUPTION

The data is not broken. On a buy you pay the gross amount plus the fee, so the fee
adds to what leaves your account and is booked positive. On a sell the fee is
deducted from the proceeds, so it is booked with the sign of a deduction — negative
— and the settled amount comes out lower than the gross. Both sides then satisfy
the same identity:

    Total = Subtotal + Fees

A buy: subtotal 1046.27, fee +5.76, total 1052.03. A sell: the fee carries a minus
and the total lands below the subtotal. Nothing is invalid, nothing needs flipping,
nothing needs cleaning. Whoever calls these 40 rows corrupt and "fixes" the signs
will break the reconciliation that currently works perfectly.

4. THE IDENTITY HOLDS ON EVERY ROW

I checked all 111 rows, not a sample. Total = Subtotal + Fees holds to the cent on
every one of them, with no exceptions and no rows set aside. The check comes back
clean. Compare the stored values rather than raw floating point. Naive float equality
reports breaks that are not there, 17 rows in Python and the same 17 via CAST AS REAL in
SQLite, and every one of those residuals is around 1e-13.

5. WHY THE NAIVE SUM IS WRONG, AND WHAT THE TRUE FIGURE IS

Because sells book their fees negative, adding the column down nets sell-side fees
against buy-side fees. The sum does not answer "how much did we pay in fees" — it
answers "what was the net signed movement attributable to fees", which is not a
number anybody asked for.

    Fees paid (sum of absolute values)      $218.71
    Naive signed sum (what the pack shows)  $102.47
    Understatement                          $116.24

The gap is exactly twice the sell-side fee total: the sells carry $58.12 of fees,
the signed sum subtracts them once instead of adding them once, so the error is
2 x 58.12 = 116.24. The buy side contributes $160.59 of positive fees, and
160.59 - 58.12 = 102.47, which is the number in the pack. That arithmetic is the
proof that the sheet is netting rather than totalling.

6. WHERE THE PACK'S NUMBER CAME FROM

The pack extract carries one row per period. Adding those period rows together
gives $102.47, which is exactly the signed sum of the fee column in the export.
That is the whole story of the pack's "total fees paid" line: someone added the fee
column up with the signs left in. The desk's own notes say the line is taken
"straight from the export with no adjustment", and that the fee line has never been
agreed to the general ledger, which is how it went unnoticed.

The bottom line ties, but do not stop there. Checked month by month the pack does
not agree with the export:

    Period     pack      export     diff
    2023-03   -9.72     -10.72     +1.00
    2023-04  -12.44     -11.44     -1.00

A dollar is sitting in the wrong month. The two errors point in opposite directions
so they cancel in the total, which is exactly why a check on the bottom line alone
reports the pack as tying. Every other period agrees to the cent.

7. THE ZERO-FEE ROWS

48 of the 111 rows carry a fee of exactly zero. They are not a mystery — they
cluster in the movements where no spread is charged:

    Receive              17
    Withdrawal           12
    Advance Trade Buy     7
    Deposit               6
    Send                  4
    Advance Trade Sell    2
                         --
                         48

The 39 Receive / Withdrawal / Deposit / Send rows are zero-fee without exception:
those are transfers and cash movements, not trades. The remaining 9 zero-fee rows
are trades too small to attract a spread.

8. FEES AS A PROPORTION OF THE SUBTOTAL

Absolute size tells you nothing here. The largest fee in the ledger is $35.71, on a
buy with a subtotal of $5,952, which is 0.60% and entirely ordinary. What matters is
the fee measured against the subtotal it sits on. Across the 106 rows with a non-zero
subtotal, that ratio spans

    -0.00800  ..  +0.01250      (-0.80%  ..  +1.25%)

so every fee, negatives included, sits within 1.25% of its own subtotal. The two rows
at the top of that range are $0.01 charged on an $0.80 buy, which is rounding on a
sub-dollar trade rather than a pricing error. Five further rows have a subtotal of
zero, dust-sized quantities, so the ratio is undefined for them rather than extreme;
all five carry a zero fee.

The nine zero-fee trade rows fit the same picture: eight have a subtotal of $0.02 or
less and the ninth is $1.12, all small enough that the spread rounds to nothing.

9. WHAT WE ACTUALLY PAY, AS A RATE

The per-row spread above says fees are proportionate. It does not say what the desk
pays. For that you have to weigh the fees against the amounts traded:

    side     rows   traded        fees      effective rate
    buys       30   27,588.64    160.59     58 bps  (0.58%)
    sells      42   12,925.81     58.12     45 bps  (0.45%)
    blended    72   40,514.45    218.71     54 bps  (0.54%)

We are not paying the same on both sides. Buying runs 13 basis points dearer than
selling, about a third more per dollar transacted, which is worth knowing before
anyone quotes a single "our fee rate is X" number to the committee.

10. THE SHAPE OF THE LEDGER

Assets — 8 distinct:

    BTC   47 rows
    ETH   41 rows
    USD   18 rows
    XLM    1        USDC   1        EOS    1        DAI    1        BAT    1

Transaction types — 6 distinct, summing to 111:

    Advance Trade Sell   42
    Advance Trade Buy    30
    Receive              17
    Withdrawal           12
    Deposit               6
    Send                  4

Only two of those eight assets are actually traded. BTC and ETH appear on buys and
sells; the other six never touch a trade row. USD sits on 6 Deposit and 12 Withdrawal
rows, which are fiat cash movements in and out of the account. XLM, USDC, EOS, DAI and
BAT appear once each, all on Receive rows. Anything that counts those 23 rows as
trading activity will overstate volume.

11. WHERE THE DEFECT LIVES

In the reporting, not the fee data. The fee column reconciles on all 111 rows and its
signs are correct as recorded, so there is nothing to correct there. The defect is in
the aggregation that builds the "total fees paid" cell: it sums a signed column as if
the sign carried no meaning. Flipping the signs at source would be actively harmful,
destroying a working reconciliation and leaving the reporting bug in place.

THE RULE FOR WHOEVER REBUILDS THAT CELL

"Fees paid" is SUM(ABS(fee)). The signed sum, SUM(fee), is only ever the net cash
effect of fees and belongs in cash reconciliation, never in a fees-paid line. One
column, two meanings — label them separately and never let one stand in for the
other.

12. AGREEING THE EXPORT TO THE GENERAL LEDGER

The accounts team's fee postings (account 6200) are in the warehouse. Comparing
the export's gross fees month by month against them, they agree everywhere except
three periods:

    period    export gross    GL       break
    2023-01       9.20        7.40     -1.80
    2023-09      95.47       94.57     -0.90
    2023-11       0.00       10.00    +10.00

Each resolves differently. There is no single book of record here.

2023-01 - the export is right. The GL feed removed a line it took for a repeated
sell, but the two identical 2023-01-14 21:05:35 ETH sells (0.19565707 ETH, fee
-1.80, twice) are two genuine fills of one order, not a duplicate. The cash chain
proves it: 1 ETH was received at 21:01:47, three sells at 21:05:35 dispose of
0.60868586 + 0.19565707 + 0.19565707 = exactly 1.00000000 ETH, and the USD
withdrawal two minutes later is 1,524.05 = 927.67 + 298.19 + 298.19, the three
sell proceeds together. Drop either twin and only 0.80 ETH is sold and the
withdrawal no longer ties. So January's fees are 9.20, the GL's 7.40 is short, and
the ledger total stands at 218.71 - it must NOT be lowered to 216.91.

2023-09 - the GL is wrong. The export's 95.47 is correct; the GL's 94.57 is a
posting slip, the 0.90 difference being a transposition. Nothing in the export
needs changing.

2023-11 - neither export figure is wrong. The ledger has no November trading at
all, so the GL's 10.00 in the fee account is a non-trading charge (a bank/wire
fee) booked there by mistake, not a fee the export dropped.

Also note the 15.87 that shows up in two periods is not the sheet copying down:
it is an ETH buy in one month and a BTC buy in another, two distinct trades that
happen to carry the same fee.


13. FEE CHARGED VS THE CONTRACTED RATE CARD

The rate card caps the all-in fee at 0.65% of the fill subtotal, with a $0.01
minimum charge. Checking fee/subtotal on every trade fill, four fills are charged
over the cap:

    date         side            subtotal    fee     rate     over cap
    2023-08-26   BTC sell          256.32    -2.05    0.80%     0.38
    2023-09-01   ETH buy            20.33     0.16    0.79%     0.03
    2023-10-16   ETH buy         1,983.33    15.86    0.80%     2.97
    2023-12-20   BTC buy         1,983.33    15.86    0.80%     2.97

Recoverable overcharge above the cap: 2.97 + 2.97 + 0.38 + 0.03 = 6.35.

The two fills that show 1.25% - a $0.01 fee on an $0.80 subtotal - are NOT
overcharges: 0.65% of $0.80 is half a cent, which rounds below the $0.01 minimum
charge, so the cent is the floor kicking in, not a rate breach. The blended and
per-side effective rates (0.54%, 0.58%, 0.45%) all sit under the cap, so the
overcharge is invisible unless every fill is checked one at a time.


14. GL DETAIL - LINE LEVEL, NOT JUST THE TOTAL

The monthly postings agreed. The line detail behind them agrees too, every month
except April 2023. April's detail sums to 11.44 and carries 21 lines, exactly like
the export - the total ties. But line by line it does not: the detail shows a 3.51
where the export has a 3.15, and an extra 0.03 in place of the export's 0.39. The
two keying slips are equal and opposite (+0.36 and -0.36), which is why the monthly
total still ties and a totals-only check misses it. Only a line-by-line match finds
the two mis-keyed lines.


15. WIRE FEES - THE VENUE ACCOUNT ACTIVITY STATEMENT

The venue bills USD wire withdrawal fees separately, on a monthly account activity
statement, not in the trade export. The rate card sets them at $25.00 per wire. The
export carries exactly 12 USD wire withdrawals, so at the agreed rate the wire fees
we owe come to 12 x 25.00 = $300.00.

The statement itself lists 13 wire charges of $25.00 each, $325.00 in total. Tied
back to the export one date at a time, 12 of the 13 match a USD withdrawal exactly:

    2022-12-28  2023-01-14  2023-02-10  2023-03-23  2023-04-24  2023-04-29
    2023-05-18  2023-05-25  2023-06-03  2023-06-10  2023-08-14  2023-08-26

The thirteenth, dated 2023-07-19, has no withdrawal behind it - July's only account
activity is a deposit and two sends, no wire out. That $25.00 is billed for a wire we
never sent, so it does not tie and should be disputed rather than paid. Treating all
13 as valid overstates the wire fees by that $25.00.


16. WHAT COMES BACK, AND THE ALL-IN COST

Two amounts are recoverable from the venue, and they must not be mixed up with the
wires we legitimately owe:

    Overcharged fills above the cap     6.35
    Wire charge with no withdrawal     25.00
                                      ------
    Recoverable from the venue         31.35

The $300.00 of wires we did send at the agreed rate are ours to pay and are NOT part
of that 31.35. Adding them in, giving 331.35, is the error to avoid.

For the committee's one-line figure, the all-in fee cost for the period combines the
two sources of fee we actually owe:

    Trade fees (sum of absolute fees)  218.71
    Wire fees at the agreed rate       300.00
                                      -------
    All-in fee cost                    518.71

The disputed 2023-07-19 wire is excluded, so the all-in is 518.71, not 543.71, and
the trade-fee figure stays 218.71 - the January line is not removed.

EOF
