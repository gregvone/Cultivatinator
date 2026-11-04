"""Recorded physical provenance only; possible genetic parents never imply transfers."""

import hashlib
import json
from sqlalchemy import select
from .models import FruitingContainer, Spawn, LineOrigin, LineParent
from .preparation_models import PreparedMaterial, MaterialTransfer
from .reports import source_identities


def provenance(session):
    identities = source_identities(session)
    prepared = {
        ("physical", p.physical_id) if p.physical_id else ("spawn", p.spawn_id): p.id
        for p in session.scalars(select(PreparedMaterial))
        if p.physical_id or p.spawn_id
    }
    transfers = {t.prepared_id: t for t in session.scalars(select(MaterialTransfer))}
    origins = {
        o.line_id: [o.origin_type, o.revision, o.spore_id, o.fruiting_id]
        for o in session.scalars(select(LineOrigin))
    }
    parents = {}
    for p in session.scalars(select(LineParent)):
        parents.setdefault(p.line_id, []).append([p.parent_id, p.confidence])

    def chain(kind, code, seen=None):
        seen = set() if seen is None else set(seen)
        key = (kind, code)
        if key in seen or len(seen) >= 256:
            return [f"{kind}:{code}"], True
        seen.add(key)
        roots = [f"{kind}:{code}"]
        transfer = transfers.get(prepared.get(key))
        if transfer and transfer.physical_source_id:
            upstream, uncertain = chain("physical", transfer.physical_source_id, seen)
            return roots + upstream, uncertain
        if transfer and transfer.spore_source_id:
            roots.append("spore:" + transfer.spore_source_id)
        return roots, False

    result = {}
    for fr in session.scalars(select(FruitingContainer)):
        rows = identities.get(fr.id, [])
        leaves = []
        cyclic = False
        for r in rows:
            roots, bad = chain("spawn", r["spawn_id"]) if r["spawn_id"] else ([], False)
            if r["line_id"]:
                roots.append("line:" + r["line_id"])
            leaves.append(sorted(set(roots)))
            cyclic |= bad
        lines = sorted({r["line_id"] for r in rows if r["line_id"]})
        facts = dict(
            fruiting_id=fr.id,
            batch_id=fr.batch_id,
            spawn_ids=sorted({r["spawn_id"] for r in rows if r["spawn_id"]}),
            line_ids=lines,
            leaves=sorted(leaves),
            ambiguous=cyclic
            or not rows
            or any(not r["line_id"] for r in rows)
            or any(p[1] == "possible" for line in lines for p in parents.get(line, [])),
            ancestry={
                line: [origins.get(line), sorted(parents.get(line, []))]
                for line in lines
            },
        )
        facts["fingerprint"] = hashlib.sha256(
            json.dumps(facts, sort_keys=True).encode()
        ).hexdigest()
        result[fr.id] = facts
    return result


def proposal(facts, rules, category):
    matched = []
    uncovered = False
    for leaf in facts["leaves"]:
        hits = [r for r in rules if f"{r['kind']}:{r['source_id']}" in leaf]
        if not hits:
            uncovered = True
        matched.extend(hits)
    if not matched:
        return None
    groups = sorted({r["group_id"] for r in matched})
    reasons = []
    if uncovered:
        reasons.append("Some source materials are not assigned")
    if len(groups) != 1:
        reasons.append("Sources point to conflicting groups")
    if facts["ambiguous"]:
        reasons.append("Unknown or cyclic provenance")
    if category == "genetics" and len(facts["line_ids"]) != 1:
        reasons.append(
            "Mixed genetic lines cannot enter a pure genetics group automatically"
        )
    if category == "conditions":
        reasons.append(
            "Shared environmental treatment unit requires trial review in 2H.3"
        )
    return dict(
        group_ids=groups,
        reason="; ".join(reasons),
        automatic=not reasons,
        allocated_at=max(r["recorded_at"] for r in matched),
        rule_ids=sorted({r["id"] for r in matched}),
    )
