"""Read a BCF file with bcf-client (IfcOpenShell's BCF library) and print what it found as JSON.

Run as its own process: bcf-client is GPL-3, so it is never imported by Ludwig or its
tests (CLAUDE.md hard rule 8). It is the library the Bonsai viewer reads BCF with.
"""

import json
import sys

from bcf.v2.bcfxml import BcfXml

bcf = BcfXml.load(sys.argv[1])  # kept: the archive closes when this object goes
topics = []
for topic in bcf.topics.values():
    guids = []
    for viewpoint in topic.viewpoints.values():
        components = viewpoint.visualization_info.components
        if components and components.selection:
            guids += [c.ifc_guid for c in components.selection.component]
    topics.append({"guid": topic.markup.topic.guid, "title": topic.markup.topic.title,
                   "type": topic.markup.topic.topic_type, "selected": guids})
json.dump(topics, sys.stdout)
