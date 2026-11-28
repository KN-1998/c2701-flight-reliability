# Historical figures for C2701

All three figures use the verified historical 2023–2025 BTS tables from the v6 code handoff. Percentages are rounded only for display. Axis differences are percentage points unless stated otherwise. The results describe the reporting-carrier sample and the matched populations shown.

| Figure | Suggested English caption | Input tables relative to implementation_v6 |
|---|---|---|
| fig01_reliability_definitions | Strict reliability by arrival-delay threshold and by denominator, 10 selected departure airports. Panel A shows the proportion of retained scheduled segments that completed normally with arrival delay strictly below the displayed threshold. Unknown outcomes contribute to the denominator and yield a lower bound. Panel B holds the 15-minute threshold fixed and contrasts all planned segments with the subset completed normally. The row order is the strict 15-minute point estimate. | historical_airport_scorecard.csv |
| fig02_airport_composition | Decomposition of selected 15-minute differences and shared-support coverage. Panel A shows ATL minus SFO and SEA minus SFO in the full sample, in shared cells with observed weights, and in the same cells under common reference weights. Whiskers are experimental 7-day paired date-block intervals. Panel B shows each airport's retained share in the common cells, with the all-segment fraction (42.45%) marked by the vertical dotted line. The intervals are conditional on fixed reference weights and are not causal, rank, or multiplicity-adjusted guarantees. | comparison_2023_2025/pairwise_comparisons.csv, comparison_2023_2025/common_support_coverage.csv |
| fig03_traveler_scorecard | Comparison of EWR and LGA departures to DEN in historical common support. Panel A uses 12 carrier, season and six-hour departure cells in the pooled sample of 24,023 planned segments. Panel B uses the nine qualifying cells and fixed weights shared across all years. Points are EWR minus LGA differences in cancellation or in normally completed flights delayed at least 60 minutes per planned segment. Whiskers are experimental 7-day paired date-block intervals. Pooled and fixed-annual panels use different support definitions. The findings help readers compare historical scenarios and do not estimate the risks of a specific 2027 flight. | traveler_card/matched_comparisons.csv, traveler_card/support_coverage.csv |

The MATLAB function is called from a folder on MATLAB's path. Both arguments may be absolute paths or paths relative to MATLAB's current folder.

    render_historical_figures("path/to/modeling/results/implementation_v6", "path/to/output")

The function reads existing score tables and renders vector PDF and 320 dpi PNG. It does not adjust, select or refit any model.

