"""What-if renovations: typed edits to a copy of a scan's plan, a derived `w_` scan every tool runs on, the checks
that flip, and a cost from takeoff quantities.

    apply(plan, edits) -> (edited plan, diff)      edits.py
    store.save(base, edits) -> (plan, diff)       writes $THRESHOLD_DATA_DIR/whatif/<w_sid>.json, served as a scan
    propose(plan, goal) -> [{edit, target, why}]  candidate edits from the failing checks
    compare.run / compare.flips                   the goal's tools before and after
    cost.line(change, after)                      dollars, with the unit costs as sourced assumptions
"""
from .edits import EDITS, AnyEdit, EditError, apply, derived_sid, parse
from .propose import propose

__all__ = ["EDITS", "AnyEdit", "EditError", "apply", "derived_sid", "parse", "propose"]
