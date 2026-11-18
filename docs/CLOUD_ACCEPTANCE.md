# Cloud acceptance v1

Run from the checkout root on Python 3.12. The synthetic CI matrix runs preflight,
frozen dependency sync, lint, formatting, tests, build, replay and source audit
on Linux and Windows. Its inputs are local synthetic fixtures. A hosted run
must be inspected per OS for the exact commit under review.

Local MT5 verification remains outside this acceptance process.
