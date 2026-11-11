import hashlib
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_fixtures_match_recorded_checksums():
    block = (FIXTURES / "README.md").read_text().split("## Checksums")[1]
    recorded = dict(
        (name, digest) for digest, name in re.findall(r"^([0-9a-f]{64})  (\S+)$", block, re.M)
    )
    assert recorded
    for name, digest in recorded.items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest, name
