from threshold.tools.step_free_route import targets

from ..conftest import OFFICE, make_plan


def test_office_labels_count_as_bathroom_and_kitchen():
    p = make_plan("toffice", OFFICE)
    assert [r["id"] for r in targets(p, ["Bathroom", "Bedroom", "Kitchen"])] == ["wc", "kit"]
