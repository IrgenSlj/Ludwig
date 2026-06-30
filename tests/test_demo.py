"""Public-demo safety + gallery — the security boundary that makes Ludwig deployable.

Pure-Python (no kernel): the safety validator is the RCE gate for the public `exec` path, so the
attacks it must refuse are tested explicitly. Gallery seeds are the trusted server-side programs.
"""
from webapp import gallery, safety


def test_gallery_listing_is_well_formed_and_hides_programs():
    seeds = gallery.listing()
    ids = [s["id"] for s in seeds]
    assert "bracket" in ids and len(ids) == len(set(ids))          # unique ids
    for s in seeds:
        assert s["title"] and s["blurb"]
        assert "program" not in s                                   # the listing never leaks programs
    assert gallery.program_for("bracket").startswith("element = box")
    assert gallery.program_for("does-not-exist") is None
    assert len(gallery.programs()) == len(seeds)


def test_safe_derivative_allows_numeric_edits():
    seeds = gallery.programs()
    bracket = gallery.program_for("bracket")
    assert safety.is_safe_derivative(bracket, seeds)                                    # the seed itself
    assert safety.is_safe_derivative(bracket.replace("80, 40, 6", "120, 40, 6"), seeds)  # one extent
    assert safety.is_safe_derivative(bracket.replace("80, 40, 6", "120, 55, 9"), seeds)  # several extents
    assert safety.is_safe_derivative(gallery.program_for("spacer").replace("10.0", "14.0"), seeds)  # float
    assert safety.is_safe_derivative(gallery.program_for("precast_panel").replace("3000", "3600"), seeds)


def test_safe_derivative_blocks_code_injection():
    seeds = gallery.programs()
    bracket = gallery.program_for("bracket")
    assert not safety.is_safe_derivative('import os; os.system("rm -rf /")', seeds)
    assert not safety.is_safe_derivative(bracket + "import os\n", seeds)                # appended import
    assert not safety.is_safe_derivative(bracket + 'open("/etc/passwd").read()\n', seeds)  # new call
    assert not safety.is_safe_derivative('element = __import__("os").system("id")', seeds)
    assert not safety.is_safe_derivative("", seeds)                                     # empty
    assert not safety.is_safe_derivative("x" * 9000, seeds)                             # oversize
    assert not safety.is_safe_derivative(bracket.replace('"bracket"', '"pwned"'), seeds)  # string change
    # a structural change that only uses allowed toolkit calls is still rejected (extra hole)
    assert not safety.is_safe_derivative(bracket + 'clearance_hole(element, "M8", (0, 0))\n', seeds)
    # one seed's program is not a numeric derivative of a *different* seed
    assert not safety.is_safe_derivative(gallery.program_for("spacer"),
                                         [gallery.program_for("bracket")])
