"""Run install.sh against an isolated target home: links, idempotence, preservation, argument checks."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
SHARED_SKILLS = ("self-correct", "epic-decomposition", "system-design-tradeoffs")


class InstallTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="install-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        # Every run names its own isolated target: the real home is never test data.
        self.target = self.directory / "home"

    def run_installer(self, *arguments, installer=INSTALLER, expect_success=True):
        completed = subprocess.run(
            ["bash", str(installer), *arguments], cwd=self.directory, capture_output=True, text=True,
        )
        if expect_success:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def expected_links(self):
        links = {}
        for skill in sorted(path for path in (ROOT / "skills").iterdir() if path.is_dir()):
            links[self.target / ".claude" / "skills" / skill.name] = skill
        for name in SHARED_SKILLS:
            links[self.target / ".agents" / "skills" / name] = ROOT / "skills" / name
        for kind in ("agents", "commands"):
            for file in sorted((ROOT / kind).glob("*.md")):
                links[self.target / ".claude" / kind / file.name] = file
        for kind in ("hooks", "statusline"):
            for file in sorted(path for path in (ROOT / kind).iterdir() if path.is_file()):
                links[self.target / ".claude" / kind / file.name] = file
        return links

    def assert_linked(self, links):
        for destination, source in links.items():
            self.assertTrue(destination.is_symlink(), destination)
            self.assertEqual(Path(os.readlink(destination)), source, destination)
            self.assertTrue(destination.exists(), destination)

    def snapshot(self):
        entries = {}
        for path in sorted(self.target.rglob("*")):
            relative = str(path.relative_to(self.target))
            if path.is_symlink():
                entries[relative] = ("link", os.readlink(path))
            elif path.is_file():
                entries[relative] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
            else:
                entries[relative] = ("dir", None)
        return entries

    def test_installs_every_component_and_shared_methods_for_both_clients(self):
        completed = self.run_installer("--target-home", str(self.target))
        links = self.expected_links()
        self.assert_linked(links)
        for name in SHARED_SKILLS:
            self.assertIn(self.target / ".claude" / "skills" / name, links)
            self.assertIn(self.target / ".agents" / "skills" / name, links)
            self.assertTrue((self.target / ".agents" / "skills" / name / "SKILL.md").is_file())
        # The /epic command depends on this method, so a portable install must provide it.
        self.assertTrue((self.target / ".claude" / "skills" / "epic-decomposition" / "SKILL.md").is_file())
        self.assertEqual(
            sorted(path.name for path in (self.target / ".claude" / "commands").iterdir()),
            sorted(path.name for path in (ROOT / "commands").glob("*.md")),
        )
        self.assertFalse((self.target / ".claude" / "settings.json").exists())
        self.assertIn(str(self.target / ".claude"), completed.stdout)
        self.assertNotIn("пропуск", completed.stdout)

    def test_second_run_changes_nothing(self):
        self.run_installer("--target-home", str(self.target))
        before = self.snapshot()
        completed = self.run_installer("--target-home", str(self.target))
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("пропуск", completed.stdout)
        self.assert_linked(self.expected_links())

    def test_preserves_existing_real_components_and_settings(self):
        real_skill = self.target / ".claude" / "skills" / "epic-decomposition"
        real_skill.mkdir(parents=True)
        (real_skill / "SKILL.md").write_text("local copy with private examples\n", encoding="utf-8")
        foreign_skill = self.target / ".claude" / "skills" / "vendor-diagrams"
        foreign_skill.mkdir()
        (foreign_skill / "SKILL.md").write_text("unrelated skill\n", encoding="utf-8")
        real_agent = self.target / ".claude" / "agents" / "code-reviewer.md"
        real_agent.parent.mkdir(parents=True)
        real_agent.write_text("customised reviewer\n", encoding="utf-8")
        settings = self.target / ".claude" / "settings.json"
        settings.write_text(json.dumps({"model": "user-choice", "hooks": {"Stop": []}}), encoding="utf-8")
        codex_skill = self.target / ".agents" / "skills" / "system-design-tradeoffs"
        codex_skill.mkdir(parents=True)
        (codex_skill / "SKILL.md").write_text("codex copy\n", encoding="utf-8")
        preserved = [real_skill / "SKILL.md", foreign_skill / "SKILL.md", real_agent, settings,
                     codex_skill / "SKILL.md"]
        before = {path: path.read_bytes() for path in preserved}

        completed = self.run_installer("--target-home", str(self.target))

        for path in preserved:
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(path.read_bytes(), before[path], path)
        for kept in (real_skill, real_agent, codex_skill):
            self.assertFalse(kept.is_symlink(), kept)
            self.assertIn(str(kept), completed.stdout)
        self.assertEqual(completed.stdout.count("пропуск"), 3)
        skipped = {real_skill, real_agent, codex_skill}
        self.assert_linked({dest: src for dest, src in self.expected_links().items() if dest not in skipped})
        self.assertTrue((self.target / ".agents" / "skills" / "epic-decomposition").is_symlink())

    def test_accepts_equals_form_and_relative_target(self):
        self.run_installer("--target-home=" + str(self.target))
        self.assert_linked(self.expected_links())
        relative_target = self.directory / "relative-home"
        self.target = relative_target
        self.run_installer("--target-home", "relative-home")
        self.assert_linked(self.expected_links())

    def test_rejects_invalid_arguments_before_touching_anything(self):
        cases = (
            ["--target-home"],
            ["--target-home", ""],
            ["--target-home="],
            ["--bogus", "--target-home", str(self.target)],
            ["--target-home", str(self.target), "--bogus"],
            ["--target-home", str(self.target), "positional"],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                completed = self.run_installer(*arguments, expect_success=False)
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertIn("Ошибка", completed.stderr)
                self.assertFalse(self.target.exists(), arguments)

    def test_rejects_target_that_is_a_file(self):
        self.target.write_text("not a directory\n", encoding="utf-8")
        completed = self.run_installer("--target-home", str(self.target), expect_success=False)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "not a directory\n")

    def test_refuses_repository_without_required_shared_method(self):
        broken_repo = self.directory / "repo"
        for name in ("self-correct", "system-design-tradeoffs"):
            (broken_repo / "skills" / name).mkdir(parents=True)
            (broken_repo / "skills" / name / "SKILL.md").write_text("---\nname: " + name + "\n---\n", encoding="utf-8")
        shutil.copy(INSTALLER, broken_repo / "install.sh")
        completed = self.run_installer(
            "--target-home", str(self.target), installer=broken_repo / "install.sh", expect_success=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("skills/epic-decomposition", completed.stderr)
        self.assertFalse((self.target / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
