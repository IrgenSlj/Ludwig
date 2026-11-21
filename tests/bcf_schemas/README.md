# BCF 2.1 schemas

`markup.xsd`, `visinfo.xsd`, `version.xsd` and `project.xsd` are copied unmodified from
buildingSMART's BCF-XML repository, branch `release_2_1`, commit
`92fdcf4bfaa8f0576e7562730f341fc7781e2065` (folder `Schemas/`), on 2026-11-20.

(c) buildingSMART International Ltd. Licensed under the Creative Commons
Attribution-NoDerivatives 4.0 International License
(https://creativecommons.org/licenses/by-nd/4.0/). Source:
https://github.com/buildingSMART/BCF-XML

They are used only by `tests/test_bcf_conformance.py`. Do not edit them; replace them with
a newer unmodified copy instead.

`read_with_bcf_client.py` reads a BCF file with bcf-client (GPL-3) in its own process; it is
not imported by Ludwig or by the tests.
