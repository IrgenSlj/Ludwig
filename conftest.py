"""Make the repo root importable so `import ir`, `import cli`, etc. resolve under pytest
regardless of invocation directory."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
