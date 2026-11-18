# Clock and availability v1

The comparison caller declares a shared receive-wall clock domain and an
inclusive maximum quote age in nanoseconds. Each stream must explicitly use
that domain. The declaration is an assumption whose justification must be
recorded in evidence. No cross-domain correction is attempted.

Poll sequence declares observation order within a source session. At decision
time, a later poll cannot enter the visible prefix before an earlier poll
whose receipt is still in the future. Equal timestamps resolve by poll
sequence. The latest visible poll is the only candidate. Its pending
processing state blocks earlier quote fallback. An earlier processing
watermark that is still pending prevents later polls from becoming eligible.

Receive and processing regressions are checked against the visible
high-watermarks. A regressed row blocks comparison if latest and breaks
dynamics continuity. Processing before receive is invalid. Source timestamps
are optional and retain millisecond resolution. Source order is checked within
a session. The future-source-time test requires a separate, explicit
declaration that source and receive clocks share a comparable epoch.
Per-process monotonic time is preserved but excluded from wall alignment.

A decision-clock age is elapsed wall time since recorded receipt. Timestamp
error, clock skew and coarseness limit what can be inferred about availability.

The v1.1 measurement rules check comparable source clocks independently of
processing and monotonic clock validity. A future source timestamp is excluded
from the source-order watermark even when another clock is malformed. A
negative receive timestamp cannot initialize the source watermark.
