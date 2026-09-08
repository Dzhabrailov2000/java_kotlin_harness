"""Run install.sh against an isolated target home: links, idempotence, preservation, argument checks.

The manual catalogue is exercised here too, against that same installed home: /harness is the only
place the descriptions of the installed components are shown, so what it prints is checked on real
installed symlinks rather than on the repository directory.
"""

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
BANNER = ROOT / "claude" / "hooks" / "harness-banner.js"
OBSOLETE_HOOK = "harness-reminder.js"
OBSOLETE_SKILL = "self-correct"
SHARED_SKILLS = ("dev-pipeline", "epic-decomposition", "system-design-tradeoffs")
# The three canonical roles live together; each client renders the ones it runs into its own format.
ROLES = {"pipeline-manager": "manager", "pipeline-reviewer": "reviewer", "pipeline-implementer": "implementer"}
CODEX_ROLES = ("pipeline-manager", "pipeline-reviewer")
CLAUDE_ROLE = "pipeline-implementer"
MARKER = "# generated from the harness role source"


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
        for skill in sorted(path for path in (ROOT / "shared" / "skills").iterdir() if path.is_dir()):
            links[self.target / ".claude" / "skills" / skill.name] = skill
        for name in SHARED_SKILLS:
            links[self.target / ".agents" / "skills" / name] = ROOT / "shared" / "skills" / name
        # The pipeline role is not linked: the client generator writes it with its native profile.
        for file in sorted((ROOT / "claude" / "agents").glob("*.md")):
            links[self.target / ".claude" / "agents" / file.name] = file
        for file in sorted((ROOT / "claude" / "commands").glob("*.md")):
            links[self.target / ".claude" / "commands" / file.name] = file
        for kind in ("hooks", "statusline"):
            for file in sorted(path for path in (ROOT / "claude" / kind).iterdir() if path.is_file()):
                links[self.target / ".claude" / kind / file.name] = file
        return links

    def codex_agent(self, name):
        return self.target / ".codex" / "agents" / (name + ".toml")

    def claude_agent(self, name=CLAUDE_ROLE):
        return self.target / ".claude" / "agents" / (name + ".md")

    def role_source(self, name, root=ROOT):
        return root / "teams" / "dev" / (ROLES[name] + ".md")

    def role_body(self, name, root=ROOT):
        return self.role_source(name, root).read_text(encoding="utf-8").split("---", 2)[2].strip()

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

    def run_banner(self):
        """The /harness command runs exactly this, with the installed home as HOME."""
        completed = subprocess.run(
            ["node", str(BANNER)], cwd=self.directory, capture_output=True, text=True,
            env={**os.environ, "HOME": str(self.target)},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

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
            sorted(path.name for path in (ROOT / "claude" / "commands").glob("*.md")),
        )
        # The three shared methods stay the ones exposed to Codex; the rest of shared/skills does not
        # leak into that client just because it moved under a shared directory.
        self.assertEqual(sorted(path.name for path in (self.target / ".agents" / "skills").iterdir()),
                         sorted(SHARED_SKILLS))
        self.assertFalse((self.target / ".claude" / "settings.json").exists())
        self.assertIn(str(self.target / ".claude"), completed.stdout)
        self.assertNotIn("пропуск", completed.stdout)

    def test_codex_roles_become_native_agents_generated_from_the_canonical_markdown(self):
        completed = self.run_installer("--target-home", str(self.target))
        self.assertEqual(sorted(path.name for path in (self.target / ".codex" / "agents").iterdir()),
                         sorted(name + ".toml" for name in CODEX_ROLES))
        for name in CODEX_ROLES:
            with self.subTest(role=name):
                body = self.role_body(name)
                generated = self.codex_agent(name).read_text(encoding="utf-8")
                self.assertTrue(generated.startswith(MARKER), generated[:120])
                self.assertIn("name = ", generated)
                self.assertIn("description = ", generated)
                self.assertIn("developer_instructions = ", generated)
                self.assertIn(str(self.role_source(name)), generated)
                # The body reaches the definition, with quotes escaped so no line can close the string.
                self.assertIn(body.replace("\\", "\\\\").replace('"', '\\"'), generated)
                self.assertNotIn('"""', generated.split("developer_instructions = ", 1)[1][3:-4])
                self.assertIn("создан: " + str(self.codex_agent(name)), completed.stdout)
        # Idempotent: a second run rewrites nothing it already generated.
        before = self.snapshot()
        again = self.run_installer("--target-home", str(self.target))
        self.assertEqual(self.snapshot(), before)
        self.assertIn("без изменений: " + str(self.codex_agent("pipeline-manager")), again.stdout)

    def test_the_generated_codex_agents_carry_the_selected_profile_and_the_launcher_assembly(self):
        self.run_installer("--target-home", str(self.target))
        manager = self.codex_agent("pipeline-manager").read_text(encoding="utf-8")
        reviewer = self.codex_agent("pipeline-reviewer").read_text(encoding="utf-8")
        for name, generated in (("pipeline-manager", manager), ("pipeline-reviewer", reviewer)):
            with self.subTest(role=name):
                self.assertIn('model = """\ngpt-6-astra"""', generated)
                self.assertIn('model_reasoning_effort = """\nultra"""', generated)
        # The reviewer may only read; the manager gets no permission of its own and keeps its caller's.
        self.assertIn('sandbox_mode = """\nread-only"""', reviewer)
        for absent in ("sandbox_mode", "approval_policy"):
            self.assertNotIn(absent, manager.split("developer_instructions = ", 1)[0])
        # The instructions are the same assembly the launchers send to a root codex exec.
        self.assertIn(str(ROOT / "shared" / "skills" / "dev-pipeline" / "SKILL.md"), manager)
        self.assertIn(str(ROOT / "scripts" / "run_acceptance.py"), manager)
        self.assertIn(str(ROOT / "claude" / "scripts" / "run_claude_task.py"), manager)
        for path in (ROOT / "shared" / "rules" / "review-criteria.md", ROOT / "shared" / "rules" / "simplicity.md"):
            with self.subTest(source=path.name):
                self.assertIn(str(path), reviewer)
                # As in the role body, the quotes of the rule are escaped inside the TOML string.
                text = path.read_text(encoding="utf-8").strip().replace("\\", "\\\\").replace('"', '\\"')
                self.assertIn(text, reviewer)
        self.assertIn("Choose the simplest implementation that fully satisfies the requirements.", reviewer)

    def test_the_claude_role_becomes_a_generated_native_subagent_with_its_profile(self):
        completed = self.run_installer("--target-home", str(self.target))
        generated = self.claude_agent().read_text(encoding="utf-8")
        self.assertTrue(generated.startswith("---\n" + MARKER), generated[:160])
        self.assertIn("создан: " + str(self.claude_agent()), completed.stdout)
        frontmatter, body = generated.split("---", 2)[1], generated.split("---", 2)[2]
        for line in ('name: "pipeline-implementer"',
                     'tools: ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "Skill"]',
                     'model: "claude-opus-5"', 'effort: "max"'):
            with self.subTest(field=line):
                self.assertIn(line, frontmatter)
        self.assertIn(str(self.role_source(CLAUDE_ROLE)), frontmatter)
        # The canonical text stays free of client keys; the profile above exists only here.
        canonical = self.role_source(CLAUDE_ROLE).read_text(encoding="utf-8").split("---", 2)[1]
        for key in ("tools:", "model:", "effort:", "permissionMode:"):
            with self.subTest(absent=key):
                self.assertNotIn(key, canonical)
        # The body is what the launcher sends: the role and the user's policy, each with its source.
        self.assertIn(self.role_body(CLAUDE_ROLE), body)
        self.assertIn((ROOT / "shared" / "rules" / "simplicity.md").read_text(encoding="utf-8").strip(), body)
        self.assertIn(str(ROOT / "shared" / "rules" / "simplicity.md"), body)
        before = self.snapshot()
        again = self.run_installer("--target-home", str(self.target))
        self.assertEqual(self.snapshot(), before)
        self.assertIn("без изменений: " + str(self.claude_agent()), again.stdout)

    def test_a_claude_agent_written_by_somebody_else_is_never_overwritten(self):
        self.run_installer("--target-home", str(self.target))
        own = self.claude_agent()
        own.write_text(own.read_text(encoding="utf-8") + "\n<!-- stale generated content -->\n", encoding="utf-8")
        foreign = self.claude_agent("code-explorer")
        foreign.unlink()
        foreign.write_text("---\nname: code-explorer\n---\nhand written\n", encoding="utf-8")

        completed = self.run_installer("--target-home", str(self.target))

        self.assertEqual(foreign.read_text(encoding="utf-8"), "---\nname: code-explorer\n---\nhand written\n")
        self.assertNotIn("stale generated content", own.read_text(encoding="utf-8"))
        self.assertIn("обновлен: " + str(own), completed.stdout)

    def test_a_codex_agent_written_by_somebody_else_is_never_overwritten(self):
        self.run_installer("--target-home", str(self.target))
        own = self.codex_agent("pipeline-manager")
        foreign = self.codex_agent("pipeline-reviewer")
        foreign.write_text('name = "pipeline-reviewer"\n# hand written by the user\n', encoding="utf-8")
        own.write_text(own.read_text(encoding="utf-8") + "\n# stale generated content\n", encoding="utf-8")

        completed = self.run_installer("--target-home", str(self.target))

        self.assertEqual(foreign.read_text(encoding="utf-8"),
                         'name = "pipeline-reviewer"\n# hand written by the user\n')
        self.assertIn("пропуск (уже существует и создан не установкой): " + str(foreign), completed.stdout)
        # Its own generated file is brought back to the canonical text instead of being left stale.
        self.assertNotIn("# stale generated content", own.read_text(encoding="utf-8"))
        self.assertIn("обновлен: " + str(own), completed.stdout)

    def test_installs_from_a_checkout_whose_path_contains_spaces(self):
        checkout = self.directory / "har ness copy"
        shutil.copytree(ROOT, checkout, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", "monitor", "node_modules"))
        completed = self.run_installer("--target-home", str(self.target), installer=checkout / "install.sh")
        for name in ("scope-fence", "dev-pipeline"):
            link = self.target / ".claude" / "skills" / name
            self.assertEqual(Path(os.readlink(link)), checkout / "shared" / "skills" / name)
        for name, generated in ((CLAUDE_ROLE, self.claude_agent()), ("pipeline-manager", self.codex_agent("pipeline-manager"))):
            with self.subTest(role=name):
                self.assertIn(str(self.role_source(name, checkout)), generated.read_text(encoding="utf-8"))
        self.assertIn(str(checkout / "shared" / "rules" / "simplicity.md"),
                      self.claude_agent().read_text(encoding="utf-8"))
        self.assertNotIn("Ошибка", completed.stdout + completed.stderr)

    def test_links_of_the_previous_layout_of_this_checkout_are_retargeted(self):
        # What an installation of this repository left before the client split: its own links, into
        # this same checkout, at paths the layout no longer has.
        stale = {
            self.target / ".claude" / "skills" / "scope-fence": ROOT / "skills" / "scope-fence",
            self.target / ".agents" / "skills" / "dev-pipeline": ROOT / "skills" / "dev-pipeline",
            self.target / ".claude" / "agents" / "code-reviewer.md": ROOT / "agents" / "code-reviewer.md",
            self.target / ".claude" / "hooks" / "ascii-punctuation.js": ROOT / "hooks" / "ascii-punctuation.js",
        }
        # The role used to be a link into this checkout; the client generator writes a real file there now.
        generated_before = self.claude_agent()
        generated_before.parent.mkdir(parents=True, exist_ok=True)
        generated_before.symlink_to(ROOT / "claude" / "roles" / "pipeline-implementer.md")
        for link, old in stale.items():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(old)
        # A link of another tool, and one into a different checkout of this same harness.
        foreign = {
            self.target / ".claude" / "skills" / "lead-with-outcome": self.directory / "other-tool" / "skill",
            self.target / ".claude" / "agents" / "builder.md": self.directory / "another-checkout" / "agents" / "builder.md",
        }
        for link, target in foreign.items():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target)

        completed = self.run_installer("--target-home", str(self.target))

        for link in stale:
            with self.subTest(retargeted=link):
                self.assertTrue(link.is_symlink())
                self.assertTrue(link.exists(), "the retargeted link resolves in the new layout")
        self.assertFalse(generated_before.is_symlink(), "the stale role link gives way to the generated file")
        self.assertIn(str(self.role_source(CLAUDE_ROLE)), generated_before.read_text(encoding="utf-8"))
        self.assertIn("удален устаревший компонент: " + str(generated_before), completed.stdout)
        for link, target in foreign.items():
            with self.subTest(preserved=link):
                self.assertEqual(Path(os.readlink(link)), target)
                self.assertIn("пропуск (чужая ссылка): " + str(link), completed.stdout)
        self.assert_linked({dest: src for dest, src in self.expected_links().items() if dest not in foreign})

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

    def test_removes_its_own_obsolete_hook_link_and_nothing_else(self):
        self.run_installer("--target-home", str(self.target))
        hooks = self.target / ".claude" / "hooks"
        own_link = hooks / OBSOLETE_HOOK
        # What a previous installation of this repository left behind: its own link to a hook that the
        # repository no longer ships, so the link now dangles.
        own_link.symlink_to(ROOT / "hooks" / OBSOLETE_HOOK)
        foreign_hook = hooks / "vendor-hook.js"
        foreign_hook.write_text("// unrelated hook of another tool\n", encoding="utf-8")
        settings = self.target / ".claude" / "settings.json"
        settings.write_text(json.dumps({"model": "user-choice", "hooks": {"UserPromptSubmit": ["kept"]}}),
                            encoding="utf-8")

        completed = self.run_installer("--target-home", str(self.target))

        self.assertFalse(own_link.is_symlink(), "the dangling link of this installation is removed")
        self.assertFalse(own_link.exists())
        self.assertIn("удален устаревший компонент", completed.stdout)
        self.assertIn("harness-reminder.js", completed.stdout)
        self.assertIn("удали", completed.stdout, "the manual settings.json cleanup is advised, not performed")
        self.assertEqual(foreign_hook.read_text(encoding="utf-8"), "// unrelated hook of another tool\n")
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"], ["kept"])
        self.assert_linked(self.expected_links())
        # Idempotent: with nothing obsolete left there is no removal and no advice about it.
        before = self.snapshot()
        again = self.run_installer("--target-home", str(self.target))
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("устаревш", again.stdout)
        self.assertNotIn("удали", again.stdout)

    def test_removes_its_own_obsolete_skill_links_from_both_clients(self):
        self.run_installer("--target-home", str(self.target))
        # What a previous installation of this repository left behind: its own links to a skill that
        # has since been renamed, so both now dangle.
        own_links = [self.target / ".claude" / "skills" / OBSOLETE_SKILL,
                     self.target / ".agents" / "skills" / OBSOLETE_SKILL]
        for link in own_links:
            link.symlink_to(ROOT / "skills" / OBSOLETE_SKILL)

        completed = self.run_installer("--target-home", str(self.target))

        for link in own_links:
            self.assertFalse(link.is_symlink(), link)
            self.assertFalse(link.exists(), link)
            self.assertIn("удален устаревший компонент: " + str(link), completed.stdout)
        self.assertNotIn("удали", completed.stdout,
                         "the settings.json advice belongs to a removed hook, not to a removed skill")
        self.assert_linked(self.expected_links())
        # Idempotent: with nothing obsolete left there is no removal and no advice about it.
        before = self.snapshot()
        again = self.run_installer("--target-home", str(self.target))
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("устаревш", again.stdout)

    def test_a_foreign_link_or_real_directory_under_the_obsolete_skill_name_is_preserved(self):
        def write_real_skill(path):
            path.mkdir()
            (path / "SKILL.md").write_text("a copy the user keeps\n", encoding="utf-8")

        cases = {
            "a link of another checkout": (lambda path: path.symlink_to(self.directory / "elsewhere"),
                                           "пропуск (чужая ссылка)"),
            "a real skill the user wrote": (write_real_skill, "пропуск (уже существует и не симлинк)"),
        }
        for label, (create, expected) in cases.items():
            for client in (".claude/skills", ".agents/skills"):
                with self.subTest(case=label, client=client):
                    self.target = self.directory / ("home-" + client[1:6] + "-" + label.replace(" ", "-"))
                    path = self.target / client / OBSOLETE_SKILL
                    path.parent.mkdir(parents=True)
                    create(path)
                    state = (path.is_symlink(), os.readlink(path) if path.is_symlink()
                             else (path / "SKILL.md").read_bytes())

                    completed = self.run_installer("--target-home", str(self.target))

                    self.assertIn(expected + ": " + str(path), completed.stdout)
                    self.assertNotIn("удален устаревший", completed.stdout)
                    self.assertEqual((path.is_symlink(), os.readlink(path) if path.is_symlink()
                                      else (path / "SKILL.md").read_bytes()),
                                     state, "an entry this installation does not own is left untouched")
                    self.assert_linked(self.expected_links())

    def test_a_foreign_file_or_link_under_the_obsolete_name_is_preserved(self):
        cases = {
            "a link of another tool": (lambda path: path.symlink_to(self.directory / "elsewhere.js"),
                                       "пропуск (чужая ссылка)"),
            "a real file the user wrote": (lambda path: path.write_text("local hook\n", encoding="utf-8"),
                                           "пропуск (уже существует и не симлинк)"),
        }
        for label, (create, expected) in cases.items():
            with self.subTest(case=label):
                self.target = self.directory / ("home-" + label.replace(" ", "-"))
                hooks = self.target / ".claude" / "hooks"
                hooks.mkdir(parents=True)
                path = hooks / OBSOLETE_HOOK
                create(path)
                state = (path.is_symlink(), os.readlink(path) if path.is_symlink() else path.read_bytes())

                completed = self.run_installer("--target-home", str(self.target))

                self.assertIn(expected, completed.stdout)
                self.assertNotIn("удален устаревший", completed.stdout)
                self.assertEqual((path.is_symlink(), os.readlink(path) if path.is_symlink() else path.read_bytes()),
                                 state, "a component this installation does not own is left untouched")
                self.assert_linked(self.expected_links())

    def test_manual_catalogue_lists_installed_components_with_their_descriptions(self):
        self.run_installer("--target-home", str(self.target))
        output = self.run_banner()
        for kind, name in (("skills", "scope-fence"), ("skills", "dev-pipeline"),
                           ("agents", "builder"), ("agents", "judge"), ("commands", "harness")):
            with self.subTest(component=name):
                source = (ROOT / "shared" / kind / name / "SKILL.md") if kind == "skills" else (ROOT / "claude" / kind / (name + ".md"))
                description = self.description_of(source)
                self.assertTrue(description, source)
                self.assertIn("  - " + name + ": " + description, output)
        self.assertIn("Хуки (события) (0):", output, "no settings.json in this home: no hook events")
        self.assertIn("не поручение применять", output)
        settings = self.target / ".claude" / "settings.json"
        settings.write_text(json.dumps({"hooks": {"PostToolUse": [], "SessionStart": []}}), encoding="utf-8")
        self.assertIn("  - PostToolUse", self.run_banner())

    def test_manual_catalogue_survives_missing_and_invalid_metadata(self):
        self.run_installer("--target-home", str(self.target))
        skills = self.target / ".claude" / "skills"
        (skills / "empty-skill").mkdir()
        (skills / "no-frontmatter").mkdir()
        (skills / "no-frontmatter" / "SKILL.md").write_text("Just instructions, no frontmatter.\n", encoding="utf-8")
        (skills / "dangling").symlink_to(self.directory / "was-removed")
        (self.target / ".claude" / "agents" / "no-description.md").write_text("---\nname: x\n---\nBody.\n",
                                                                              encoding="utf-8")
        (self.target / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")

        output = self.run_banner()

        self.assertIn("  - empty-skill\n", output, "a skill without SKILL.md is listed without a description")
        self.assertIn("  - no-frontmatter\n", output)
        self.assertIn("  - no-description\n", output)
        self.assertNotIn("dangling", output, "a link to nothing is not an installed skill")
        self.assertIn("Хуки (события) (0):", output, "an unreadable settings.json costs the section, not the run")
        self.assertIn("  - scope-fence: ", output, "the readable components are still described")

    def description_of(self, path):
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            if line.startswith("description:"):
                return line.split(":", 1)[1].strip().strip("\"'")
            if line == "---":
                break
        return ""

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
        for name in ("dev-pipeline", "system-design-tradeoffs"):
            (broken_repo / "shared" / "skills" / name).mkdir(parents=True)
            (broken_repo / "shared" / "skills" / name / "SKILL.md").write_text(
                "---\nname: " + name + "\n---\n", encoding="utf-8")
        shutil.copy(INSTALLER, broken_repo / "install.sh")
        completed = self.run_installer(
            "--target-home", str(self.target), installer=broken_repo / "install.sh", expect_success=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("shared/skills/epic-decomposition", completed.stderr)
        self.assertFalse((self.target / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
