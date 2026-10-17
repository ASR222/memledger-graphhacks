"""Every Cypher query MemLedger depends on. The README lists these."""

# ---------------------------------------------------------------- schema

# Run once per tenant graph. Re-running raises "already indexed"; ignore it.
INDEXES = [
    "CREATE INDEX FOR (f:Fact) ON (f.id)",
    "CREATE INDEX FOR (f:Fact) ON (f.subject, f.predicate, f.status)",
    "CREATE INDEX FOR (s:Source) ON (s.id)",
    "CREATE INDEX FOR (a:Agent) ON (a.id)",
    "CREATE INDEX FOR (e:Entity) ON (e.name)",
    "CREATE INDEX FOR (ep:Episode) ON (ep.id)",
    "CREATE INDEX FOR (ep:Episode) ON (ep.session)",
    "CREATE FULLTEXT INDEX FOR (ep:Episode) ON (ep.text)",
]

# Seed the tenant's agents and sources. Idempotent.
# Agents go through FOREACH: on FalkorDB 6.x a second UNWIND...MERGE after an
# aggregating WITH runs only once (1 of N Sources created).
SEED = """
FOREACH (a IN $agents | MERGE (x:Agent {id:a.id}) SET x.role = a.role)
WITH 1 AS _
UNWIND $sources AS s MERGE (y:Source {id:s.id})
ON CREATE SET y.kind = s.kind, y.trust = s.trust, y.compromised = false
"""

# ---------------------------------------------------------------- writes

# Store one agent turn as an Episode (persistent conversation history).
LOG_EPISODE = """
MATCH (a:Agent {id:$agent}), (src:Source {id:$source})
CREATE (ep:Episode {id:$id, session:$session, at:$now, text:$text})
CREATE (a)-[:LOGGED {at:$now}]->(ep)
CREATE (ep)-[:FROM_SOURCE]->(src)
RETURN ep.id AS id
"""

# Create a Fact with full provenance. For single-valued predicates
# ($single = true): an active new fact closes every active fact with the same
# subject+predicate and a different object (SUPERSEDES); a quarantined new fact
# only records CONFLICTS_WITH against them. Multi-valued facts never conflict.
WRITE_FACT = """
MATCH (a:Agent {id:$agent}), (src:Source {id:$source}), (ep:Episode {id:$episode})
MERGE (e:Entity {name:$subject})
CREATE (f:Fact {id:$id, subject:$subject, predicate:$predicate, object:$object,
                valid_from:$now, status:$status, trust:src.trust})
CREATE (a)-[:WROTE {at:$now}]->(f)
CREATE (f)-[:FROM_SOURCE]->(src)
CREATE (f)-[:DERIVED_FROM]->(ep)
CREATE (f)-[:ABOUT]->(e)
WITH f
OPTIONAL MATCH (old:Fact {subject:$subject, predicate:$predicate, status:'active'})
WHERE $single AND old.id <> f.id AND old.object <> $object
FOREACH (o IN CASE WHEN old IS NULL OR $status <> 'active' THEN [] ELSE [old] END |
  SET o.status = 'closed', o.valid_to = $now
  CREATE (f)-[:SUPERSEDES]->(o))
FOREACH (o IN CASE WHEN old IS NULL OR $status <> 'quarantined' THEN [] ELSE [old] END |
  CREATE (f)-[:CONFLICTS_WITH {at:$now}]->(o))
WITH f, count(old) AS n
RETURN f.id AS id,
       CASE WHEN $status = 'active' THEN n ELSE 0 END AS closed,
       CASE WHEN $status = 'quarantined' THEN n ELSE 0 END AS conflicts
"""

# Record that a fact was concluded from earlier facts. Revocation follows these.
LINK_PARENTS = """
MATCH (f:Fact {id:$id})
UNWIND $parents AS pid
MATCH (p:Fact {id:pid})
CREATE (f)-[:DERIVED_FROM]->(p)
RETURN count(p) AS linked
"""

# Another agent or source asserts a triple that already exists: add provenance,
# create no new Fact.
CORROBORATE = """
MATCH (f:Fact {id:$id}), (src:Source {id:$source}), (a:Agent {id:$agent})
MERGE (f)-[:FROM_SOURCE]->(src)
CREATE (a)-[:WROTE {at:$now, corroborates:true}]->(f)
RETURN f.id AS id
"""

# Move a quarantined fact to active and, for single-valued predicates,
# supersede whatever it contradicts.
PROMOTE = """
MATCH (q:Fact {id:$id, status:'quarantined'})
SET q.status = 'active', q.promoted_at = $now
WITH q
OPTIONAL MATCH (old:Fact {subject:q.subject, predicate:q.predicate, status:'active'})
WHERE q.predicate IN $single_preds AND old.id <> q.id AND old.object <> q.object
FOREACH (o IN CASE WHEN old IS NULL THEN [] ELSE [old] END |
  SET o.status = 'closed', o.valid_to = $now
  CREATE (q)-[:SUPERSEDES]->(o))
RETURN q.id AS id, count(old) AS closed
"""

# Explicit retraction ("ruled out X"): close the matching active fact without
# a replacement and record who retracted it, from which episode.
RETRACT = """
MATCH (f:Fact {subject:$subject, predicate:$predicate, object:$object, status:'active'})
MATCH (a:Agent {id:$agent}), (ep:Episode {id:$episode})
SET f.status = 'closed', f.valid_to = $now, f.retracted = true
CREATE (a)-[:RETRACTED {at:$now}]->(f)
CREATE (ep)-[:RETRACTS]->(f)
RETURN f.id AS id
"""

# Blast-radius revocation. Mark the source compromised, then revoke every live
# fact that reaches it through FROM_SOURCE / DERIVED_FROM within 6 hops.
REVOKE = """
MATCH (s:Source {id:$source})
SET s.compromised = true
WITH s
MATCH (s)<-[:FROM_SOURCE|DERIVED_FROM*1..6]-(f:Fact)
WHERE f.status IN ['active','quarantined']
WITH DISTINCT f
SET f.revoked_from = f.status, f.status = 'revoked', f.valid_to = $now
WITH f
OPTIONAL MATCH (a:Agent)-[w:WROTE]->(f)
WHERE w.corroborates IS NULL
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
       f.object AS object, a.id AS writer
"""

# ---------------------------------------------------------------- reads

# Trust and compromise flag for one source.
SOURCE_INFO = """
MATCH (s:Source {id:$id})
RETURN s.trust AS trust, s.compromised AS compromised
"""

# Facts with this exact triple that are still live.
FIND_SAME = """
MATCH (f:Fact {subject:$subject, predicate:$predicate, object:$object})
WHERE f.status IN ['active','quarantined']
RETURN f.id AS id, f.status AS status
"""

# Status, subject and predicate of the facts a new fact is derived from.
PARENT_STATUS = """
UNWIND $ids AS pid
OPTIONAL MATCH (p:Fact {id:pid})
RETURN pid AS id, p.status AS status, p.subject AS subject, p.predicate AS predicate
"""

# Values already used for a subject, per predicate (revoked values excluded).
# Fed to the extractor so it reuses existing spellings.
KNOWN_VALUES = """
MATCH (f:Fact {subject:$subject})
WHERE f.status <> 'revoked'
RETURN f.predicate AS predicate, collect(DISTINCT f.object) AS values
"""

# Quarantined claims that contradict a current belief.
DISPUTES = """
MATCH (q:Fact {status:'quarantined'})-[:CONFLICTS_WITH]->(a:Fact {status:'active'})
RETURN q.id AS id, q.subject AS subject, q.predicate AS predicate,
       q.object AS claimed, a.id AS against, a.object AS believed
ORDER BY q.valid_from
"""

# Current beliefs about one entity. The only read path agents use.
READ_ACTIVE = """
MATCH (f:Fact {status:'active'})-[:ABOUT]->(e:Entity {name:$entity})
OPTIONAL MATCH (a:Agent)-[w:WROTE]->(f)
WHERE w.corroborates IS NULL
RETURN f.id AS id, f.predicate AS predicate, f.object AS object,
       f.valid_from AS since, a.id AS writer
ORDER BY f.valid_from DESC
"""

# Every current belief in the tenant (Comms uses this for status updates).
ALL_ACTIVE = """
MATCH (f:Fact {status:'active'})
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
       f.object AS object, f.valid_from AS since
ORDER BY f.subject, f.predicate
"""

# What the team believed at time $t. Closed and revoked facts appear if they
# were valid then. Quarantined facts never appear.
AS_OF = """
MATCH (f:Fact)
WHERE coalesce(f.promoted_at, f.valid_from) <= $t
  AND (f.valid_to IS NULL OR f.valid_to > $t)
  AND f.status <> 'quarantined'
  AND coalesce(f.revoked_from, 'active') <> 'quarantined'
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate, f.object AS object
ORDER BY f.subject, f.predicate
"""

# Every version of one subject+predicate, oldest first (the supersession chain).
FACT_VERSIONS = """
MATCH (f:Fact {subject:$subject, predicate:$predicate})
RETURN f.id AS id, f.object AS object, f.status AS status,
       f.valid_from AS valid_from, f.valid_to AS valid_to
ORDER BY f.valid_from
"""

# Why is this believed? Writer, sources, everything upstream, values replaced.
WHY = """
MATCH (f:Fact {id:$id})
OPTIONAL MATCH (a:Agent)-[w:WROTE]->(f)
OPTIONAL MATCH (f)-[:FROM_SOURCE]->(s:Source)
OPTIONAL MATCH (f)-[:DERIVED_FROM*1..6]->(up)
OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Fact)
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
       f.object AS object, f.status AS status,
       collect(DISTINCT a.id) AS agents,
       collect(DISTINCT s.id) AS sources,
       collect(DISTINCT up.id) AS upstream,
       collect(DISTINCT old.object) AS replaced
"""

# Each path from a fact to a source behind it, as node-id lists (UI highlighting).
WHY_PATHS = """
MATCH p = (f:Fact {id:$id})-[:FROM_SOURCE|DERIVED_FROM*1..6]->(s:Source)
RETURN [n IN nodes(p) | coalesce(n.id, n.name)] AS path
"""

# Active facts built on a belief that has since been closed (stale reasoning).
STALE = """
MATCH (f:Fact {status:'active'})-[:DERIVED_FROM*1..6]->(p:Fact {status:'closed'})
OPTIONAL MATCH (p)<-[:SUPERSEDES]-(n:Fact)
RETURN DISTINCT f.id AS id, f.predicate AS predicate, f.object AS object,
       p.id AS based_on, p.object AS based_on_value, n.object AS now_believed
"""

# Conversation history for one session.
HISTORY = """
MATCH (a:Agent)-[:LOGGED]->(ep:Episode {session:$session})
RETURN ep.id AS id, a.id AS agent, ep.at AS at, ep.text AS text
ORDER BY ep.at
"""

# Whole graph for the UI (demo-sized graphs only).
NODES = """
MATCH (n)
RETURN ID(n) AS nid, labels(n)[0] AS label, properties(n) AS props
"""
EDGES = """
MATCH (a)-[r]->(b)
RETURN ID(a) AS src, type(r) AS type, ID(b) AS dst
"""

# ---------------------------------------------------------------- trust (TRU.md)

# Every source with its trust and how many facts cite it directly, by status.
TRUST_TABLE = """
MATCH (s:Source)
OPTIONAL MATCH (s)<-[:FROM_SOURCE]-(f:Fact)
RETURN s.id AS id, s.kind AS kind, s.trust AS trust, s.compromised AS compromised,
       sum(CASE WHEN f.status = 'active' THEN 1 ELSE 0 END) AS active,
       sum(CASE WHEN f.status = 'quarantined' THEN 1 ELSE 0 END) AS quarantined,
       sum(CASE WHEN f.status = 'revoked' THEN 1 ELSE 0 END) AS revoked
ORDER BY s.trust DESC, s.id
"""

# Dry run of REVOKE: the same traversal, read-only. `direct` is true when the
# source itself asserted the fact; false when the fact was concluded from one
# that did. `hops` is the shortest provenance distance.
BLAST_RADIUS = """
MATCH p = (s:Source {id:$source})<-[:FROM_SOURCE|DERIVED_FROM*1..6]-(f:Fact)
WHERE f.status IN ['active','quarantined']
WITH s, f, min(length(p)) AS hops
OPTIONAL MATCH (f)-[d:FROM_SOURCE]->(s)
WITH f, hops, count(d) > 0 AS direct
OPTIONAL MATCH (a:Agent)-[w:WROTE]->(f)
WHERE w.corroborates IS NULL
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate,
       f.object AS object, f.status AS status, a.id AS writer, hops, direct
ORDER BY hops, f.valid_from
"""

# Change a source's trust. Affects future writes only.
SET_TRUST = """
MATCH (s:Source {id:$id})
SET s.trust = $trust
RETURN s.id AS id, s.trust AS trust
"""

# Quarantined facts, newest first, with the source that put them there.
QUARANTINE = """
MATCH (f:Fact {status:'quarantined'})-[:FROM_SOURCE]->(s:Source)
OPTIONAL MATCH (a:Agent)-[w:WROTE]->(f)
WHERE w.corroborates IS NULL
RETURN f.id AS id, f.subject AS subject, f.predicate AS predicate, f.object AS object,
       f.valid_from AS since, collect(DISTINCT s.id) AS sources, a.id AS writer
ORDER BY f.valid_from DESC
"""

# ---------------------------------------------------------------- agents (AGT.md)

# Create a source only if it doesn't exist. Never touches an existing source,
# so it cannot un-compromise one.
ENSURE_SOURCE = """
MERGE (s:Source {id:$id})
ON CREATE SET s.kind = $kind, s.trust = $trust, s.compromised = false
RETURN s.id AS id, s.trust AS trust, s.compromised AS compromised
"""

# Record a handoff between agents carrying fact ids (shared state, not text).
HANDOFF = """
MATCH (a:Agent {id:$from}), (b:Agent {id:$to})
CREATE (h:Handoff {id:$id, session:$session, at:$now, note:$note, delivered:false})
CREATE (a)-[:SENT]->(h)
CREATE (h)-[:TO]->(b)
WITH h
OPTIONAL MATCH (f:Fact) WHERE f.id IN $facts
FOREACH (x IN CASE WHEN f IS NULL THEN [] ELSE [f] END | CREATE (h)-[:CARRIES]->(x))
RETURN h.id AS id, count(f) AS facts
"""

# The kind of a source, used by Team.route to pick the agent that handles it.
SOURCE_KIND = """
MATCH (s:Source {id:$id}) RETURN s.kind AS kind
"""

# Handoffs waiting for an agent, oldest first, with the current status of each
# carried fact (a fact may have been revoked since it was handed over).
PENDING_HANDOFFS = """
MATCH (a:Agent)-[:SENT]->(h:Handoff {delivered:false})-[:TO]->(:Agent {id:$to})
OPTIONAL MATCH (h)-[:CARRIES]->(f:Fact)
RETURN h.id AS id, a.id AS sender, h.note AS note, h.at AS at, h.session AS session,
       collect({id:f.id, predicate:f.predicate, object:f.object, status:f.status}) AS facts
ORDER BY h.at
"""

# Mark handoffs as read.
DELIVER_HANDOFFS = """
MATCH (h:Handoff) WHERE h.id IN $ids
SET h.delivered = true, h.delivered_at = $now
RETURN count(h) AS delivered
"""

# ---------------------------------------------------------------- tenancy (TEN.md)

# Node counts by label.
LABEL_COUNTS = """
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY label
"""

# Fact counts by status.
FACT_STATUS_COUNTS = """
MATCH (f:Fact) RETURN f.status AS status, count(f) AS n ORDER BY status
"""

# Single-valued (subject, predicate) pairs with more than one active fact.
# Must always be empty (Mem.md invariant I1); used to check it under load.
I1_VIOLATIONS = """
MATCH (f:Fact {status:'active'})
WHERE f.predicate IN $single_preds
WITH f.subject AS subject, f.predicate AS predicate, collect(f.object) AS objects
WHERE size(objects) > 1
RETURN subject, predicate, objects
"""
