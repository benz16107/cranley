"""Real scan ids and their expected values for tests. They live in the data folder, never in git (CoStar terms):
$THRESHOLD_DATA_DIR/fixtures/test_sids.json, one key per test. A missing file or key means the test skips."""
import json

from threshold.config import DATA


def real(key: str, default=None):
    f = DATA / "fixtures" / "test_sids.json"
    return json.loads(f.read_text()).get(key, default) if f.exists() else default
