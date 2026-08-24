#!/bin/bash
set -euo pipefail

# ORACLE SOLUTION — the acceptance gate harbor runs instead of an agent under `-a oracle`; its output must satisfy every claim in tests/reward.toml, and every number below was derived from the pinned bundle at 7aa490cb and the eight CSVs at /data, with NOTES.md recording how so it can be re-derived rather than trusted.

mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Short version: hold the bump for a beat, then take it — but not for the reason the
ticket says. We are sitting on a real bug today, and the changelog entry everyone is
quoting is not the one that fixes it.

WHAT ACTUALLY CHANGED, AND WHERE

Three commits in the history touch how a number gets parsed out of a text value, all
of them in agate/data_types/number.py:

  fff4714  "Handle percents and currency symbols when casting numbers." (#217)
           Christopher Groskopf, 8 Sep 2015
  ed3b6f8  "Fix stripping currency symbols." (#333)
           Christopher Groskopf, 27 Oct 2015
  01c0591  "Parse negative currency text as Number." (#595)
           Neil Bedi, 31 Mar 2016

The subject line on the first one is wrong, and that is the whole story. fff4714
introduces the CURRENCY_SYMBOLS list and adds the stripping inside Number.test() —
the method that decides whether a column *looks* numeric. It does not touch
Number.cast(), the method that actually converts a value. Read the diff rather than
the subject: the only hunk in that commit lands inside test(), immediately after
`d = d.strip()`.

ed3b6f8 is the commit that adds the identical three lines to cast(). Checking the
file at the release tags settles it beyond argument:

  0.8.0  cast():  d = d.strip()                     <- no % or currency handling
  1.0.0  cast():  d = d.strip()                     <- still none
  1.0.1  cast():  d = d.strip(); d = d.strip('%'); then the currency loop

FIRST RELEASES, AND A TRAP

  #217 / fff4714  first shipped in 0.8.0   (9 September 2015)
  #333 / ed3b6f8  first shipped in 1.0.1   (29 October 2015)
  #595 / 01c0591  first shipped in 1.4.0   (26 May 2016)

Watch the ordering. Listing the tags that contain a commit gives them in string
order, so #217 appears to start at 0.10.0 and #595 at 1.10.0. Both are wrong —
0.10.0 sorts before 0.8.0 lexically and comes after it semantically. The CHANGELOG
sections confirm the real dates.

AND THE COMMIT THAT MAKES IT UNREPEATABLE

One more worth knowing about, because it changes how far I want to bump:

  d8dfc3a  "Collapse DataType.test." (#382)
           Christopher Groskopf, 4 Nov 2015, first shipped in 1.1.0

This one deletes Number.test() altogether and replaces the per-type test methods
with a single generic one on the base class:

    def test(self, d):
        try:
            self.cast(d)
        except CastError:
            return False
        return True

From 1.1.0 onward test() is a thin wrapper around cast(), so the two cannot
disagree by construction. ed3b6f8 patched the symptom in 1.0.1; d8dfc3a removes
the possibility in 1.1.0.

THE BROKEN WINDOW

Between those two commits the library will tell you a column is a Number and then
refuse to convert it. test() strips the dollar sign, decides "numeric", and cast()
then sees the raw "$15.00", hands it to parse_decimal untouched, and raises a cast
error on every row. That is not "currency was unsupported" — unsupported would be
honest. The two halves disagree with each other.

Five releases carry that asymmetry: 0.8.0, 0.9.0, 0.10.0, 0.11.0, 1.0.0.

We pin 0.9.0. We are inside it.

WHAT IT COSTS US, CONCRETELY

Applying test() and 0.9.0's cast() across all eight CSVs: 7 columns are classified
numeric and then fail to convert, on every single row — 343 values in total.

  Barber Shop.csv
    Price                                31 of 31 rows

  Pet Care 2023 Weekly Financials.csv
    Daily Care Weekly Revenue            52 of 52
    Grooming Services Weekly Revenue     52 of 52
    Training Services Weekly Revenue     52 of 52
    Total Weekly Revenue  Week           52 of 52
    Total Weekly Expenses                52 of 52
    Weekly Profits                       52 of 52

  31 + (6 x 52) = 343.

On 1.0.1 or later every one of those converts cleanly: 0 failures.

THE TWO COLUMNS THAT LOOK LIKE MONEY AND ARE NOT ON THE LIST

I want to be precise here, because a grep for "$" gives a longer list and the longer
list is wrong.

  Top Movies.csv, Gross — values like "$28.34M". The magnitude suffix survives the
  currency strip, so test() itself returns false and the column is never classified
  numeric at all. It lands as text on every version, before and after the fix. The
  bump does not rescue it.

  fantasy sports.csv, Salary(USD) — same shape, values like "$4M", same outcome.

These two are not "affected but fixed". They were never in the numeric set. If we
want them as numbers, that is our parsing problem, not the library's.

THE COMMIT THAT BUYS US NOTHING

01c0591 / #595, the negative-currency fix in 1.4.0, changes nothing for us. It only
matters when a value carries a leading minus in front of a currency symbol, and
there are zero such values across the eight CSVs. It belongs in the upgrade notes as
"no effect here", not on the list of reasons to bump.

WHERE THAT LEAVES THE WAREHOUSE

Here I have to talk you out of the conclusion you are about to draw.

The seven columns are text in turing.db — barber_shop.price and the six pet-care
revenue, expense and profit columns hold the raw "$15.00" and " $ 5,824.00 " strings.
That looks like proof of the cast failure. It is not.

Every column in the warehouse is text. All 72 of them, across all eight tables.
crime_records.suspect_age is text. top_movies.imdb_rating is text.
covid_19_impacts_on_hospitals.icu_capacity is text. Columns that convert perfectly
well on any version of the library are typed exactly the same as the seven that
cannot convert on ours.

So the warehouse tells us nothing about this bug either way. Whatever writes
turing.db is not applying inferred types at all — it stores strings and stops. Our
seven columns would look identical in there whether we were pinned to 0.9.0 or to
1.14.2. The evidence for the regression is the code and the CSVs, not the schema.

The practical consequence is unchanged and worth stating plainly: every downstream
sum over those columns is either casting in SQL or quietly wrong. But that is true
of the numeric columns too, and fixing the library does not fix it.

RECOMMENDATION

Take the bump, but land it as a data migration, not a version change.

  1. Anything at or above 1.0.1 fixes the seven columns. There is no reason to stop
     short of a current release; nothing between 1.0.1 and today re-breaks this.
     If you want the guarantee rather than the patch, 1.1.0 is the floor — that is
     where test() became a wrapper around cast() and the two stopped being able to
     disagree at all.
  2. The seven columns must be re-typed in the warehouse as part of the same change.
     Upgrading the library alone leaves 343 text values sitting in tables that
     downstream code will keep casting by hand.
  3. Do not put #595 in the justification. It is real, it is just not ours.
  4. Gross and Salary(USD) stay text either way. If someone wants those numeric,
     that is a separate ticket about expanding magnitude suffixes.
EOF
