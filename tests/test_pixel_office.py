"""Check the office the monitor serves: its provenance, its entry point and what publishes into it.

Three things are checked here and nowhere else in Python. First, provenance: every vendored file is
the pinned upstream byte for byte, every local change is a patch that really applies to that byte and
produces the recorded result, and dist is what the recorded build produced. Second, the documented
entry point: `run_progress.py serve` really starts the office, serves what it declares and nothing
else, and takes its child down with it. Third, the semantic publication: a captured check and a
validated review record their own outcome, and neither can claim more than its receipt says.

The office's own state projection is checked by `npm --prefix monitor/pixel-office test`, and the
rendered office by tests/check_original_office_browser.py.
"""

import hashlib
import http.client
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
run_progress = importlib.import_module("run_progress")
from test_run_acceptance import AcceptanceFixture, answer  # noqa: E402 - one acceptance fixture for the whole suite

OFFICE = ROOT / "monitor" / "pixel-office"
NODE = shutil.which("node")
# The whole local change surface: a patch outside this list is a change nobody declared.
DECLARED_PATCHES = {
    "core/asyncapi.yaml",
    "core/src/messages.ts",
    "webview-ui/src/App.tsx",
    "webview-ui/src/components/BottomToolbar.tsx",
    "webview-ui/src/components/ConnectionIndicator.tsx",
    "webview-ui/src/components/SettingsModal.tsx",
    "webview-ui/src/hooks/useExtensionMessages.ts",
    "webview-ui/src/office/components/ToolOverlay.tsx",
    "webview-ui/src/office/engine/characters.ts",
}


def digest_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BuildProvenanceTest(unittest.TestCase):
    """What the office is built from, and that its local changes are exactly the declared ones."""

    @classmethod
    def setUpClass(cls):
        cls.vendor = json.loads((OFFICE / "vendor-manifest.json").read_text(encoding="utf-8"))
        cls.build = json.loads((OFFICE / "dist" / "build-manifest.json").read_text(encoding="utf-8"))

    def test_every_vendored_file_is_the_recorded_upstream_byte_for_byte(self):
        present = sorted(str(path.relative_to(OFFICE / "vendor")).replace(os.sep, "/")
                         for path in (OFFICE / "vendor").rglob("*") if path.is_file())
        self.assertEqual(present, sorted(self.vendor["files"]), "the vendor tree and its manifest disagree")
        for name, entry in self.vendor["files"].items():
            path = OFFICE / "vendor" / name
            self.assertEqual((digest_of(path), path.stat().st_size), (entry["sha256"], entry["bytes"]), name)
        self.assertEqual(self.vendor["commit"], "3537e140c2094761beae748592aeb92ece8edfdd")
        self.assertIn("MIT", self.vendor["license"])
        self.assertTrue((OFFICE / "vendor" / "LICENSE").is_file(), "the upstream licence travels with its sources")
        # The originals the office is really made of, not just the engine it borrows.
        for name in ("webview-ui/src/App.tsx", "webview-ui/src/main.tsx", "webview-ui/src/index.css",
                     "webview-ui/src/office/engine/renderer.ts", "webview-ui/src/office/components/OfficeCanvas.tsx",
                     "webview-ui/src/office/editor/EditorToolbar.tsx", "webview-ui/index.html",
                     "webview-ui/public/fonts/FSPixelSansUnicode-Regular.ttf"):
            self.assertIn(name, self.vendor["files"], name)

    @unittest.skipUnless(shutil.which("git"), "git applies the patches")
    def test_each_patch_applies_to_the_pinned_original_and_produces_the_recorded_result(self):
        recorded = {entry["target"]: entry for entry in self.build["patches"]}
        self.assertEqual(set(recorded), DECLARED_PATCHES, "the declared local change surface moved")
        with tempfile.TemporaryDirectory(prefix="office-patches-") as temporary:
            tree = Path(temporary) / "vendor"
            shutil.copytree(OFFICE / "vendor", tree)
            for target, entry in sorted(recorded.items()):
                patch = OFFICE / "patches" / entry["patch"]
                self.assertTrue(patch.is_file(), entry["patch"])
                self.assertEqual(digest_of(patch), entry["sha256"], "the patch changed since the recorded build")
                self.assertEqual(digest_of(tree / target), entry["original_sha256"],
                                 "the patch is recorded against another original than the vendored one")
                # git resolves patch paths against a repository root, so discovery is stopped at the tree.
                applied = subprocess.run(["git", "apply", "-p1", str(patch)], cwd=tree, capture_output=True,
                                         text=True, env={**os.environ, "GIT_CEILING_DIRECTORIES": temporary})
                self.assertEqual(applied.returncode, 0, applied.stderr)
                self.assertEqual(digest_of(tree / target), entry["patched_sha256"],
                                 "applying the patch did not produce the recorded result")
                self.assertNotEqual(entry["original_sha256"], entry["patched_sha256"],
                                    "a patch that changes nothing would leave an unpatched original in the build")
            for name in self.vendor["files"]:
                if name not in recorded:
                    self.assertEqual(digest_of(tree / name), self.vendor["files"][name]["sha256"],
                                     "a patch changed a file outside its declared target: " + name)

    def test_the_patches_change_state_transport_and_one_journal_entry_only(self):
        """Every hunk is read: the local surface may not grow a second office or a new renderer."""
        for path in sorted((OFFICE / "patches").glob("*.patch")):
            body = path.read_text(encoding="utf-8")
            added = "\n".join(line[1:] for line in body.splitlines() if line.startswith("+") and not line.startswith("+++"))
            for forbidden in ("innerHTML", "document.write", "eval(", "fetch(", "XMLHttpRequest",
                              "localStorage", "sessionStorage", "settings.json", "~/.claude", "~/.codex"):
                self.assertNotIn(forbidden, added, "%s introduces %s" % (path.name, forbidden))
        overlay = (OFFICE / "patches" / "webview-ui__src__office__components__ToolOverlay.tsx.patch").read_text(encoding="utf-8")
        self.assertIn("pipelineStates", overlay, "the overlay renders the pipeline lifecycle")
        toolbar = (OFFICE / "patches" / "webview-ui__src__components__BottomToolbar.tsx.patch").read_text(encoding="utf-8")
        self.assertEqual(toolbar.count("<Button"), 1, "exactly one native entry is added to the toolbar")
        self.assertIn("Journal", toolbar)
        hooks = (OFFICE / "patches" / "webview-ui__src__hooks__useExtensionMessages.ts.patch").read_text(encoding="utf-8")
        added = "\n".join(line[1:] for line in hooks.splitlines() if line.startswith("+") and not line.startswith("+++"))
        for cue in ("os.showWaitingBubble(", "playDoneSound(", "showPermissionBubble("):
            self.assertNotIn(cue, added, "no neutral state may play a finished-turn or approval cue")
        self.assertIn("requestSnapshot", added, "a reconnected client asks for a fresh snapshot")
        self.assertIn("os.setAgentActive(id, working)", added, "only an observed working state animates")
        # This is a check of the declared change surface, not of engine behaviour: the presence of
        # a call proves the patch contains it, nothing more. What the engine really does with a
        # neutral actor is run for real in monitor/pixel-office/test/engine.test.mjs.
        handler = added[added.index("const apply = (state: TransportState)"):]
        for call in ("os.setAgentTool(id, null)", "os.setAgentActive(id, false)"):
            self.assertIn(call, handler, "a lost socket must stop the animation, not only its caption")
        engine = (OFFICE / "patches" / "webview-ui__src__office__engine__characters.ts.patch").read_text(encoding="utf-8")
        added = "\n".join(line[1:] for line in engine.splitlines() if line.startswith("+") and not line.startswith("+++"))
        self.assertIn("if (!ch.isActive)", added, "only an active character advances the typing frames")
        for forbidden in ("wanderTimer", "seatTimer", "findPath", "CharacterState."):
            self.assertNotIn(forbidden, added, "the engine patch touches the animation only, not the movement of the room")
        settings = (OFFICE / "patches" / "webview-ui__src__components__SettingsModal.tsx.patch").read_text(encoding="utf-8")
        for removed in ("Watch All Sessions", "Instant Detection (Hooks)", "Absolute asset directory path"):
            self.assertIn("-", settings)
            self.assertIn(removed, settings, "the inapplicable control is named in the patch that removes it")

    def test_dist_matches_its_recorded_build_inputs_and_outputs(self):
        for name, entry in self.build["outputs"].items():
            path = (OFFICE / "dist" / "office" / name).resolve()
            self.assertEqual((digest_of(path), path.stat().st_size), (entry["sha256"], entry["bytes"]), name)
        for name, expected in self.build["adapterSources"].items():
            self.assertEqual(digest_of(OFFICE / name), expected, name)
        self.assertEqual(self.build["vendorManifestSha256"], digest_of(OFFICE / "vendor-manifest.json"))
        self.assertEqual(self.build["upstream"]["commit"], self.vendor["commit"])
        self.assertIn("not", self.build["note"].lower())
        self.assertIn("byte identical", self.build["note"], "the build never claims to be the published bundle")

    def test_the_built_office_is_the_original_application(self):
        index = (OFFICE / "dist" / "office" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<div id="root">', index, "the original entry point is the office root element")
        bundles = sorted((OFFICE / "dist" / "office" / "assets").glob("*.js"))
        self.assertEqual(len(bundles), 1, bundles)
        source = bundles[0].read_text(encoding="utf-8", errors="replace")
        for present in ("Layout", "Settings", "Journal", "Reconnecting", "pipelineActorState", "requestSnapshot"):
            self.assertIn(present, source, present)
        for absent in ("Watch All Sessions", "Instant Detection (Hooks)", "Absolute asset directory path"):
            self.assertNotIn(absent, source, "an inapplicable control is still in the built office: " + absent)
        css = sorted((OFFICE / "dist" / "office" / "assets").glob("*.css"))
        self.assertEqual(len(css), 1, css)
        self.assertIn("FS Pixel Sans", css[0].read_text(encoding="utf-8"), "the original typography is built in")

    def test_the_decoded_assets_are_the_original_room_and_characters(self):
        assets = json.loads((OFFICE / "dist" / "assets.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(assets), ["carpets", "characters", "floors", "furniture", "layout", "petNames", "pets", "walls"])
        self.assertEqual(len(assets["characters"]), 6)
        self.assertEqual(assets["petNames"], ["Claudio", "Gitcat"])
        self.assertGreater(len(assets["furniture"]["catalog"]), 20)
        layout = assets["layout"]
        self.assertEqual((layout["version"], layout["cols"], layout["rows"]), (1, 21, 22))
        self.assertGreater(len(layout["furniture"]), 20, "the shipped room, not an empty grid")
        known = {entry["id"] for entry in assets["furniture"]["catalog"]}
        for item in layout["furniture"]:
            base = item["type"][:-len(":left")] if item["type"].endswith(":left") else item["type"]
            self.assertIn(base, known, item["type"])


@unittest.skipUnless(NODE and (OFFICE / "dist" / "office" / "index.html").exists()
                     and (OFFICE / "node_modules" / "ws").exists(),
                     "the office needs node, its built bundle and its installed dependencies")
class OfficeServeTest(unittest.TestCase):
    """The documented entry point: one command, one URL, and no child left behind."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="office-serve-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"
        journal = run_progress.ProgressJournal.open(
            self.progress, source="launcher", phase="build", run_id="serve-test", attempt=1, step_id="build-1",
            first=("run", "started", {"model": "claude-serve-test-model", "effort": "max"}))
        journal.record("init", "observed", source="native", model="claude-serve-test-model")
        self.process = subprocess.Popen(
            [sys.executable, "-B", str(ROOT / "scripts" / "run_progress.py"), "serve",
             "--progress-dir", str(self.progress), "--office-state-dir", str(self.directory / "state")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop)
        deadline = time.monotonic() + 90
        self.url = None
        while time.monotonic() < deadline and self.url is None:
            if self.process.poll() is not None:
                self.fail("serve exited %d: %s" % (self.process.returncode, self.process.stderr.read()))
            line = self.process.stdout.readline()
            if line.startswith("http://"):
                self.url = line.strip()
        self.assertIsNotNone(self.url, "serve printed no URL")
        self.port = int(self.url.rsplit(":", 1)[1].rstrip("/"))

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)

    def get(self, path, host=None, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            connection.request(method, path, headers={"Host": host} if host else {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_the_office_serves_its_own_routes_and_the_journal_behind_it(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b'<div id="root">', body)
        status, _, body = self.get("/details")
        self.assertEqual(status, 200)
        self.assertIn("Монитор конвейера", body.decode("utf-8"))
        self.assertNotIn("office-canvas", body.decode("utf-8"), "the journal carries no second office")
        self.assertNotIn("loop-node-build", body.decode("utf-8"), "the retired loop graph is gone")
        status, _, body = self.get("/api/events?cursor=0&limit=10")
        self.assertEqual(status, 200)
        page = json.loads(body)
        self.assertEqual([event["event"] for event in page["events"]], ["run", "init"])
        self.assertEqual(self.get("/fonts/FSPixelSansUnicode-Regular.ttf")[0], 200)
        self.assertEqual(self.get("/assets/characters/char_0.png")[0], 200)

    def test_only_the_intended_routes_are_reachable(self):
        for path in ("/nope", "/vendor/LICENSE", "/package.json", "/src/office-server.mjs",
                     "/dist/assets.json", "/../scripts/run_progress.py", "/assets/index.html",
                     "/api/artifact", "/api/events/extra"):
            with self.subTest(path=path):
                self.assertIn(self.get(path)[0], (400, 404), path)
        self.assertEqual(self.get("/", host="example.com")[0], 403)
        self.assertEqual(self.get("/", method="POST")[0], 405)

    def test_stopping_the_launcher_stops_the_office_with_it(self):
        listing = subprocess.run(["pgrep", "-f", "office-server.mjs"], capture_output=True, text=True)
        self.assertIn(str(self.port), self.url)
        self.assertNotEqual(listing.stdout.strip(), "", "the office runs as a child of this launcher")
        self.stop()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            probe = subprocess.run(["pgrep", "-f", "office-server.mjs --port %d" % self.port],
                                   capture_output=True, text=True)
            if probe.stdout.strip() == "":
                break
            time.sleep(0.2)
        else:
            self.fail("the office survived its launcher")
        with self.assertRaises(OSError):
            self.get("/")


class SemanticPublicationTest(AcceptanceFixture):
    """A captured check and a validated review record their own result, and never more than it."""

    def setUp(self):
        super().setUp()
        self.progress = self.directory / "progress"

    def records(self):
        page = run_progress.read_events(self.progress / "progress.jsonl", limit=run_progress.MAX_LIMIT)
        return page["events"]

    def published(self):
        return [record for record in self.records() if record["source"] == "receipt"]

    def test_a_captured_check_publishes_its_own_result_with_its_receipt(self):
        self.freeze()
        summary = self.check("ok", progress=self.progress)
        self.assertEqual(summary["stage"], "passed")
        self.assertEqual(summary["progress"]["status"], "RECORDED")
        records = self.published()
        self.assertEqual(len(records), 1)
        published = records[0]
        self.assertEqual((published["source"], published["phase"], published["event"], published["status"]),
                         ("receipt", "tests", "phase", "passed"))
        self.assertEqual(published["evidence"], summary["receipt_id"])
        self.assertEqual(published["component"], "ok")
        self.assertEqual(published["run_id"], "acceptance-run")
        self.assertEqual(published["count"], len(self.receipt(self.evidence / "plan.json")["declaration"]["commands"]),
                         "the aggregate needs the number of checks the plan really declares")
        receipt = self.receipt(summary["path"])
        self.assertEqual(published["snapshot"], receipt["snapshot_after"]["digest"],
                         "the record names the candidate tree the command really ran on")
        self.assertIn("tests: этап PASS", run_progress.describe(published))

    def test_a_failed_command_is_a_fail_and_an_unfinished_one_is_unverified(self):
        self.freeze()
        failed = self.check("fail", expect=1, progress=self.progress)
        self.assertEqual(failed["stage"], "failed")
        slow = self.check("slow", expect=1, progress=self.progress)
        self.assertEqual(slow["stage"], "unverified", "a timeout says nothing about the code")
        missing = self.check("missing", expect=1, progress=self.progress)
        self.assertEqual(missing["stage"], "unverified", "a command that never launched is not a verdict")
        touch = self.check("touch", expect=1, progress=self.progress)
        self.assertEqual(touch["stage"], "unverified", "a tree that changed under the command is not a verdict")
        self.assertEqual([record["status"] for record in self.published()],
                         ["failed", "unverified", "unverified", "unverified"])

    def test_a_verified_review_fail_is_published_as_a_fail_although_the_process_succeeded(self):
        self.freeze()
        check = self.check("ok", progress=self.progress)
        process, _ = self.review({"model": MODEL,
                                  "message": answer(overall="FAIL", criteria=(("C1", "FAIL"), ("C2", "PASS"), ("C3", "PASS")),
                                                    findings=(("major", "C1"),))},
                                 checks=[check["path"]], expect=0)
        summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
        self.assertEqual((summary["verified"], summary["verdict"]), (True, "FAIL"))
        self.assertEqual(process.returncode, 0, "a validated review exits 0 whatever its verdict")
        self.assertEqual(summary["progress"], {"status": "RECORDED", "error": None, "stage": "failed"})
        review = [record for record in self.published() if record["phase"] == "review"]
        self.assertEqual(len(review), 1)
        self.assertEqual((review[0]["status"], review[0]["evidence"], review[0]["count"]),
                         ("failed", summary["receipt_id"], 1))
        self.assertEqual(review[0]["model"], MODEL, "the observed model of the reviewer, not the requested one")

    def test_an_unobserved_model_is_left_out_rather_than_invented(self):
        self.freeze()
        check = self.check("ok", progress=self.progress)
        # This fake reports no model in its stream, so the record carries none: the requested profile
        # is not written into a field that means "observed".
        self.review({"message": answer()}, checks=[check["path"]], expect=0)
        review = [record for record in self.published() if record["phase"] == "review"]
        self.assertEqual(review[0]["status"], "passed")
        self.assertNotIn("model", review[0])

    def test_an_unvalidated_review_is_unverified_and_never_a_pass(self):
        self.freeze()
        check = self.check("ok", progress=self.progress)
        process, _ = self.review({"message": "PASS, всё отлично"}, checks=[check["path"]], expect=1)
        summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
        self.assertFalse(summary["verified"])
        self.assertEqual(summary["progress"]["stage"], "unverified")
        self.assertEqual([record["status"] for record in self.published() if record["phase"] == "review"], ["unverified"])

    def test_a_receipt_record_must_name_the_receipt_it_came_from(self):
        with self.assertRaises(ValueError):
            run_progress.validate_event({"schema": 1, "event_id": "e1", "time": "2026-09-08T10:00:00.000Z",
                                         "run_id": "r", "attempt": 1, "step_id": "s", "source": "receipt",
                                         "phase": "tests", "event": "phase", "status": "passed"})
        clean = run_progress.validate_event({"schema": 1, "event_id": "e1", "time": "2026-09-08T10:00:00.000Z",
                                             "run_id": "r", "attempt": 1, "step_id": "s", "source": "receipt",
                                             "phase": "tests", "event": "phase", "status": "passed",
                                             "evidence": "a" * 64, "snapshot": "b" * 64})
        self.assertEqual(clean["evidence"], "a" * 64)
        for event in ("decision", "finding", "run", "cli_exit"):
            with self.assertRaises(ValueError, msg=event):
                run_progress.validate_event({"schema": 1, "event_id": "e1", "time": "2026-09-08T10:00:00.000Z",
                                             "run_id": "r", "attempt": 1, "step_id": "s", "source": "receipt",
                                             "phase": "decision", "event": event, "status": "complete",
                                             "evidence": "a" * 64})

    def test_a_journal_that_cannot_be_written_leaves_the_check_verdict_alone(self):
        self.freeze()
        blocked = self.directory / "blocked"
        blocked.mkdir()
        (blocked / "progress.jsonl").write_text("this is not a progress journal\n", encoding="utf-8")
        summary = self.check("ok", progress=blocked)
        self.assertEqual(summary["passed"], True, "the command passed; observation does not decide that")
        self.assertEqual(summary["progress"]["status"], "UNVERIFIED")
        self.assertIn("not a progress journal", summary["progress"]["error"])

    def test_a_capture_aimed_at_another_runs_directory_publishes_nothing_and_still_passes(self):
        """A monitoring target chosen wrongly costs the records, never the verdict of the command."""
        self.freeze()
        foreign = self.directory / "foreign"
        run_progress.ProgressJournal.open(foreign, source="launcher", phase="build", run_id="another-run",
                                          step_id="build-1", first=("run", "started", {}))
        before = (foreign / "progress.jsonl").read_bytes()
        summary = self.check("ok", progress=foreign)
        self.assertEqual(summary["passed"], True, "the command passed; the wrong journal does not decide that")
        self.assertEqual(summary["progress"]["status"], "UNVERIFIED")
        self.assertIn("another-run", summary["progress"]["error"])
        self.assertEqual((foreign / "progress.jsonl").read_bytes(), before,
                         "no record of this run may land in another run's journal")
        self.assertTrue(self.receipt(summary["path"])["passed"], "the sealed receipt is untouched")

    def test_a_capture_without_a_progress_target_publishes_nothing(self):
        self.freeze()
        summary = self.check("ok")
        self.assertNotIn("progress", summary)
        self.assertEqual(summary["stage"], "passed")
        self.assertFalse((self.progress / "progress.jsonl").exists())


MODEL = importlib.import_module("test_run_acceptance").MODEL


if __name__ == "__main__":
    unittest.main()
