---
name: record-check
description: Comparing a CoStar or listing record with what the scans measure. Use when the person is a CoStar researcher, an underwriter, or a renter checking what a listing claims.
---
# Record against reality

1. `record_vs_reality` on each scan or on the property: every record fact beside the measured value, with the
   evidence and a verdict (confirmed, contradicted, cannot verify).
2. `listing_claims` when the person has a listing rather than a CoStar record.
3. `derived_fields` proposes the record fields the property lacks, measured from the scan and the aerial photo.
4. `room_labeller` names the rooms of a commercial space from its panoramas and writes the labels into the plan, so
   it asks for approval first. Run it only when room labels decide the answer (offices have none).
5. `field_audit` for a research lead who wants the gaps across a portfolio.

Listed area is usually measured to the outside of the walls, so a measured area a little smaller is expected; the
panel says how much. Never restate an area or a count yourself.
