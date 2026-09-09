import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from toolfit.cli import main


class CliTests(unittest.TestCase):
    def test_offline_scan_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "web-dashboard"
            project.mkdir()
            (project / "package.json").write_text(
                '{"dependencies":{"react":"1","playwright":"1"}}'
            )
            catalog = root / "catalog.jsonl"
            catalog.write_text(
                '{"mcp_id":"aaaaaaaaaaaaaaaa","tool_name":"scan_accessibility",'
                '"server_name":"a11y","tool_description":"browser accessibility testing for react and playwright",'
                '"task_text":"Test web applications","occupation_title":"Web Developers"}\n'
            )
            output = root / "result.md"
            result = main([
                str(project), "--catalog", str(catalog), "--offline", "--output", str(output)
            ])
            self.assertEqual(result, 0)
            self.assertIn("scan\\_accessibility", output.read_text())

    def test_offline_scan_writes_inert_review_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "web-dashboard"
            project.mkdir()
            (project / "package.json").write_text(
                '{"dependencies":{"react":"1","playwright":"1"},"scripts":{"test":"playwright test"}}'
            )
            catalog = root / "catalog.jsonl"
            catalog.write_text(
                '{"mcp_id":"aaaaaaaaaaaaaaaa","tool_name":"scan_accessibility",'
                '"server_name":"a11y","tool_description":"browser accessibility testing through a local stdio server",'
                '"task_text":"Test web applications","occupation_title":"Web Developers"}\n'
            )
            review = root / "mcp-review.md"
            result = main([
                str(project), "--catalog", str(catalog), "--offline", "--review-config", str(review)
            ])
            self.assertEqual(result, 0)
            rendered = review.read_text()
            self.assertIn(".codex/config.toml.review", rendered)
            self.assertIn("enabled = false", rendered)
            self.assertIn("REPLACE_WITH_DOCUMENTED_SERVER_READ_ONLY_ARGUMENT", rendered)

    def test_report_and_review_bundle_require_different_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "same.md"
            error = io.StringIO()
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(error):
                main([directory, "--output", str(destination), "--review-config", str(destination)])
            self.assertIn("[ATE100]", error.getvalue())

    def test_missing_offline_catalog_gives_recovery_action(self):
        with tempfile.TemporaryDirectory() as directory:
            error = io.StringIO()
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(error):
                main([
                    directory,
                    "--catalog",
                    str(Path(directory) / "missing.jsonl"),
                    "--offline",
                ])
            rendered = error.getvalue()
            self.assertIn("[ATE101]", rendered)
            self.assertIn("Run without --offline", rendered)

    def test_invalid_project_gives_recovery_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.jsonl"
            catalog.write_text("")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                result = main([
                    str(root / "missing-project"),
                    "--catalog",
                    str(catalog),
                    "--offline",
                ])
            self.assertEqual(result, 2)
            self.assertIn("[ATE103]", error.getvalue())
            self.assertIn("[ATE105]", error.getvalue())

    def test_unwritable_output_gives_recovery_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            catalog = root / "catalog.jsonl"
            catalog.write_text(
                '{"mcp_id":"aaaaaaaaaaaaaaaa","tool_name":"scan_accessibility",'
                '"server_name":"a11y","tool_description":"browser accessibility testing for react applications",'
                '"task_text":"Test web applications","occupation_title":"Web Developers"}\n'
            )
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                result = main([
                    str(project),
                    "--catalog",
                    str(catalog),
                    "--offline",
                    "--output",
                    str(root / "missing" / "report.md"),
                ])
            self.assertEqual(result, 2)
            self.assertIn("[ATE106]", error.getvalue())
            self.assertIn("may be incomplete", error.getvalue())
            self.assertIn("writable output path", error.getvalue())

    def test_unwritable_review_bundle_does_not_change_client_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            (project / "package.json").write_text('{"dependencies":{"react":"1","playwright":"1"}}')
            catalog = root / "catalog.jsonl"
            catalog.write_text(
                '{"mcp_id":"aaaaaaaaaaaaaaaa","tool_name":"scan_accessibility",'
                '"server_name":"a11y","tool_description":"browser accessibility testing for react applications",'
                '"task_text":"Test web applications","occupation_title":"Web Developers"}\n'
            )
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                result = main([
                    str(project),
                    "--catalog",
                    str(catalog),
                    "--offline",
                    "--review-config",
                    str(root / "missing" / "review.md"),
                ])
            self.assertEqual(result, 2)
            self.assertIn("[ATE107]", error.getvalue())
            self.assertIn("No client configuration was changed", error.getvalue())

    def test_invalid_catalog_shape_gives_recovery_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            catalog = root / "catalog.jsonl"
            catalog.write_text('"not an object"\n')
            error = io.StringIO()
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(error):
                main([str(project), "--catalog", str(catalog), "--offline"])
            self.assertIn("[ATE104]", error.getvalue())
            self.assertIn("valid ATE JSONL", error.getvalue())


if __name__ == "__main__":
    unittest.main()
