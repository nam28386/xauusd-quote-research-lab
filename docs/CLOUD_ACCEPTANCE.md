# Cloud acceptance v1

Run from the checkout root on Python 3.12. The synthetic CI matrix runs preflight,
frozen dependency sync, lint, formatting, tests, build, replay and source audit
on Linux and Windows. Its inputs are local synthetic fixtures. A hosted run
must be inspected per OS for the exact commit under review.

Local MT5 verification remains outside this acceptance process.

Consult [research methods](RESEARCH_METHODS.md) for the hand-audited fixture
expectations. The source audit verifies the allowlisted fixture hash, rejects
unreviewed data file types, and checks Python imports and common sensitive
patterns. Code review remains necessary for provenance and opaque secrets.
