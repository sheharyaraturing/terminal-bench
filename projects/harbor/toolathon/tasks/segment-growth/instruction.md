Finance needs the planning-round year-over-year segment growth book before the FY26-P1 planning review.

Use the authoritative planning inputs and methodology available in the workspace, including any applicable revenue corrections. Produce `growth.xlsx` in the workspace root.

The workbook must contain exactly one sheet named `Growth`. Its first column must be `Segment`, followed by the required planning growth years. Preserve the authoritative segment order and required year columns even where no figure can be calculated.

Follow the governing methodology exactly, including source precedence, applicability dates, calculation-rule precedence, missing-value treatment, and rounding.

For `ROUND_HALF_UP`, perform the growth arithmetic using exact decimal values before rounding. Do not calculate the percentage using binary floating-point and then convert the result to a decimal. Convert the revenue values to exact decimals first, perform the division and multiplication using decimal arithmetic, then round the final percentage to one decimal place.

Do not infer conventional finance rules where the workspace defines them. Historical material may be present in the workspace and is not necessarily authoritative.
