"""A stand-in model for tests: reads the prompt, answers from the canned file named in argv."""

import sys
from pathlib import Path

prompt = sys.stdin.read()
answers = Path(sys.argv[1]).read_text().split("\n=====\n")
if "Explain this" in prompt:
    print(answers[0])
elif "Map the columns" in prompt:
    print(answers[1])
else:
    print(answers[2])
