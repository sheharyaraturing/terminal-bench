#!/bin/bash
# ORACLE SOLUTION, the acceptance gate.
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
Priya, you were right to distrust both figures. Retention is 74.4%, not
near-total, and the treated group's advantage reverses sign once the people we
lost are carried in. Detail below, with the numbers on both sides.

SCOPE

We recruited 180 people, 90 into each group, 45 at each of four sites. There are
four scheduled visits per person, baseline, week 4, week 12 and the
end-of-study visit, so 720 visit records in total. There are 133 recorded final
scores.

1. WHY THE DRAFT SAYS RETENTION IS NEAR-TOTAL

The final scores exist only for people who reached the end of the study. Match
the final scores to the recruitment list on the people present in both and you
get 133 people, every one of whom has a final score, and retention comes out at
100%. That figure is an artefact of the match, not a result: the 47 people who
appear on the recruitment list and nowhere in the final scores are silently
discarded before the metric is computed, so the metric cannot come out at
anything other than 100%. It is unfalsifiable rather than good.

Counted properly against everyone recruited, 133 of 180 have a final score on
file: 73.9%.

By group, coverage of the final scores:

  treated group     56 of 90    62.2%
  comparison group  77 of 90    85.6%

2. WHO COMPLETED, AND WHY THE OBVIOUS TEST IS WRONG

Completion has to be decided on attendance at the end-of-study visit, not on a
count of attended visits. Only 128 people attended all four. Six more missed one
intermediate visit and still turned up for the end-of-study visit, they
completed. Counting people with four attended visits therefore undercounts
completers by 6 and would report retention as 71.1%, which is wrong in the other
direction from the draft.

On the end-of-study visit:

  completers  134
  lost         46
  retention   134/180 = 74.4%

  treated group     56 completed, 34 lost    62.2% completion, 37.8% loss
  comparison group  78 completed, 12 lost    86.7% completion, 13.3% loss

3. THE LOSS IS NOT EVEN, AND IT HAS A DIRECTION

Of the 46 people we lost, 34 are in the treated group and 12 in the comparison
group. That is a loss rate of 37.8% against 13.3%, a differential of roughly
24.4 percentage points. This is not attrition scattered across the cohort; it is
concentrated in the group whose result the draft is defending.

Site is not the explanation. Every one of the four sites recruited 45 people, and
what each lost was 12, 12, 11 and 11 in turn, which is 26.7%, 26.7%, 24.4% and
24.4%. Near enough a quarter wherever you look, and nothing separating one place
from another. The group split is nothing like that flat, so what we lost tracks
the group people were in, not the place they were seen.

The direction is signable, and it goes against the draft. The 46 people we lost
average 45.5 at their last recorded measurement, against 62.5 for the 133 people
with a final score, about 17 points lower. The people who left were the poor
responders. Dropping them therefore pushes every group mean upward, and pushes
the group that lost more people upward by more. Within the lost group itself:

  treated group's losses     last measurement averages 43.2
  comparison group's losses  last measurement averages 52.0

So the treated group did not only lose more people, it lost worse-scoring
people. Both effects push in the same direction.

4. THE COMPARISON, BOTH WAYS

As analysed in the draft, finishers with a final score only:

  treated group      n = 56    mean 64.72
  comparison group   n = 77    mean 60.94
  difference (treated minus comparison)   +3.78

Over everybody recruited, with each person we lost carried in at their last
recorded measurement:

  treated group      n = 90    mean 56.59
  comparison group   n = 90    mean 59.60
  difference (treated minus comparison)   -3.01

All 180 people carry a value in the second analysis; 47 of them are carried
forward rather than measured at the end.

The sign reverses. The treated group's 3.78-point lead becomes a 3.01-point
deficit, a swing of about 6.8 points, and the reversal comes from who is
missing rather than from anything about the people we measured. The advantage
does not survive. I would not let the current claim go to the funder.

5. ONE PERSON WITH NO FINAL SCORE IS NOT A LOSS

SUBJ-015, comparison group, first site. Look at that person's visit history and
every one of the four appointments is marked as attended, the closing one
included, and it even carries a measurement of 47.3 taken on the day. What is
absent is only the final score row itself. So the score was never written down
rather than never earned, which is a records failure and not a
withdrawal, and it must not be counted as attrition.

This is exactly the trap in the naive correction. Counting
recruited-minus-final-scores as the loss figure gives 47 people lost, 133
completers and 74.4% turning into 73.9%. The correct figures are 46 lost, 134
completers, 74.4%. One person, but it is the difference between a number that
comes from the data and a number that comes from an absent row.

Everything else is internally consistent, which is what makes that one case
unambiguous rather than one of many: nobody who failed to complete carries a
final score, nobody carries more than one, every recruited person has visit
records, and no unattended visit carries a measurement. SUBJ-015's absent row is
the only data defect in the three sets of records.

WHAT I WOULD PUT IN THE WRITE-UP

Retention is 74.4% overall, 62.2% in the treated group against 86.7% in the
comparison group, not near-total. The attrition is differential and informative
and has to be reported as such. The headline advantage is 3.78 points among
finishers and minus 3.01 points across everyone recruited, so it reverses, and
the reversal has to be stated rather than buried in a sensitivity appendix. Chase
SUBJ-015's missing assessment with the site: it is a data-entry gap, and it is
recoverable.
EOF
