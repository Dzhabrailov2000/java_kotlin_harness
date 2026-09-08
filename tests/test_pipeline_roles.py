"""The three canonical roles and the entry that routes a task to them.

Two properties are checked here because nothing else can check them: the role text is one maintained
copy that carries no client configuration, and the entry skill sends a code development request to a
manager without sending every document and report there too. Both are instructions rather than code,
so the test reads the files the launchers and the installers actually load.
"""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from role_text import load_role


TEAM = ROOT / "teams" / "dev"
ACTORS = ("manager", "implementer", "reviewer")
ENTRY = ROOT / "shared" / "skills" / "dev-pipeline" / "SKILL.md"
# Keys a client understands and the role text must therefore not carry.
CLIENT_KEYS = ("model:", "tools:", "effort:", "permissionMode:", "sandbox", "approval", "mcpServers:")


class CanonicalRoleTest(unittest.TestCase):
    def test_the_pipeline_has_exactly_three_actors_in_one_place(self):
        self.assertEqual(sorted(path.name for path in TEAM.glob("*.md")),
                         sorted(name + ".md" for name in ACTORS))

    def test_a_role_names_itself_and_carries_no_client_configuration(self):
        for name in ACTORS:
            with self.subTest(actor=name):
                role = load_role(TEAM / (name + ".md"))
                self.assertTrue(role["name"] and role["description"], role["path"])
                frontmatter = (TEAM / (name + ".md")).read_text(encoding="utf-8").split("---", 2)[1]
                self.assertEqual(sorted(line.split(":", 1)[0] for line in frontmatter.strip().splitlines()),
                                 ["description", "name"])
                for key in CLIENT_KEYS:
                    self.assertNotIn(key, frontmatter, "the profile belongs to the client adapter")

    def test_no_second_maintained_copy_of_a_role_body(self):
        bodies = {name: load_role(TEAM / (name + ".md"))["body"].strip() for name in ACTORS}
        for path in ROOT.rglob("*.md"):
            if TEAM in path.parents or ".git" in path.parts or "monitor" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for name, body in bodies.items():
                with self.subTest(actor=name, file=path.relative_to(ROOT)):
                    self.assertNotIn(body, text, "a role has one maintained text; the rest are links")


class EntryRoutingTest(unittest.TestCase):
    def setUp(self):
        self.text = ENTRY.read_text(encoding="utf-8")

    def section(self, title):
        start = self.text.index("## " + title)
        end = self.text.find("\n## ", start + 1)
        return self.text[start:end if end != -1 else len(self.text)]

    def test_the_general_use_cases_are_stated_before_the_dispatch(self):
        # A report does not get its own manager, so the loop this session runs comes first and the
        # dispatch command lives after it, in a section that names the mode it belongs to.
        self.assertLess(self.text.index("## When to apply"), self.text.index("## Entry: who runs this task"))
        self.assertLess(self.text.index("## When NOT to apply"), self.text.index("## Entry: who runs this task"))
        entry = self.section("Entry: who runs this task")
        self.assertLess(entry.index("A document, a report, research"), entry.index("A code development request"))
        self.assertLess(entry.index("The session that read this skill runs\nthe loop itself"),
                        entry.index("run_codex_manager.py"))

    def test_the_dispatch_is_one_manager_for_a_code_request_and_the_actors_do_not_re_enter(self):
        entry = self.section("Entry: who runs this task")
        self.assertIn("python3 codex/scripts/run_codex_manager.py", entry)
        self.assertIn("hand it, once, to one fresh manager", entry)
        self.assertIn("another manager context is a recursion", entry)
        self.assertIn("The external implementer and the terminal reviewer\nnever enter the loop either", entry)
        # The description a client shows before opening the file has to carry the same distinction.
        description = self.text.split("---", 2)[1]
        self.assertIn("Documents, research and reports are verified in the session that reads this", description)
        self.assertIn("a code development request is instead handed once to a fresh manager context", description)


if __name__ == "__main__":
    unittest.main()
