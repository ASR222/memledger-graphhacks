# INC-42 review: payments-api latency

Ruled out DB pool exhaustion: the pool was a symptom, not the cause.

Root cause is deploy v2.3.1 (09:52 IST), which introduced an N+1 query in the charges endpoint.

Mitigation: roll back to v2.3.0. Owner: payments team.
