"""Read the canonical Markdown roles and rules that the launchers send to the models.

One file is the only maintained copy of a role or a rule: the launcher sends its text to the model
and records its path and SHA-256, and the installer renders the same file into the native agent
definition of a client. Nothing here keeps a second body of the same instruction.

The frontmatter is read with a line match rather than a YAML parser, as the rest of this harness
does, so a canonical file stays readable to the clients without adding a dependency.
"""

import hashlib
from pathlib import Path
import re


FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
FIELD = re.compile(r"^(name|description):\s*(.+?)\s*$", re.MULTILINE)


def read_source(path, kind, name=None):
    """Read one canonical instruction file and describe what was read."""
    path = Path(path)
    if not path.is_file():
        raise ValueError("Canonical %s source is missing: %s" % (kind, path))
    data = path.read_bytes()
    return {"kind": kind, "name": name or path.stem, "path": str(path.resolve()),
            "sha256": hashlib.sha256(data).hexdigest(), "text": data.decode("utf-8")}


def load_role(path):
    """Read a canonical role: its native name and description, and the body sent to the model."""
    source = read_source(path, "role")
    match = FRONTMATTER.match(source["text"])
    if not match:
        raise ValueError("Canonical role has no frontmatter: " + source["path"])
    fields = {key: value.strip("\"'") for key, value in FIELD.findall(match.group(1))}
    for field in ("name", "description"):
        if not fields.get(field):
            raise ValueError("Canonical role %s has no %s in its frontmatter" % (source["path"], field))
    source.update(name=fields["name"], description=fields["description"],
                  body=source["text"][match.end():].strip() + "\n")
    return source


def instruction_block(title, source, body=None):
    """The text of one injected instruction, with the source it came from, as the skills are sent."""
    return "\n# " + title + "\nSource: " + source["path"] + "\n\n" + (source["text"] if body is None else body)
