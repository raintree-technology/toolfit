import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from toolfit import core


class MetadataPrivacyTests(unittest.TestCase):
    def test_mcp_config_uses_keys_not_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".mcp.json"
            path.write_text(json.dumps({
                "mcpServers": {
                    "postgres": {
                        "command": "npx",
                        "env": {"API_TOKEN": "supersecretvalue"},
                        "args": ["postgres://user:password@example.invalid/database"],
                    }
                }
            }))
            terms = core.metadata_terms(path)
            self.assertIn("postgres", terms)
            self.assertIn("api", terms)
            self.assertNotIn("supersecretvalue", terms)
            self.assertNotIn("password", terms)
            self.assertNotIn("example.invalid", terms)

    def test_package_manifest_keeps_dependency_names_not_script_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "package.json"
            path.write_text(json.dumps({
                "name": "accessible-dashboard",
                "dependencies": {"react": "latest", "playwright": "latest"},
                "scripts": {"test:e2e": "secret-command --token hiddenvalue"},
            }))
            terms = core.metadata_terms(path)
            self.assertIn("react", terms)
            self.assertIn("playwright", terms)
            self.assertIn("test", terms)
            self.assertNotIn("secret-command", terms)
            self.assertNotIn("hiddenvalue", terms)

    def test_sensitive_files_and_symlinks_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("SECRET=do-not-read")
            (root / "package.json").write_text('{"dependencies":{"react":"1"}}')
            (root / "linked.json").symlink_to(root / "package.json")
            context = core.collect_context(root)
            self.assertIn("react", context.terms)
            self.assertNotIn("secret", context.terms)
            self.assertGreaterEqual(context.files_skipped, 2)

    def test_filesystem_root_is_rejected(self):
        with self.assertRaises(ValueError):
            core.collect_context(Path(Path.cwd().anchor))

    def test_agent_configuration_detection_is_opt_in(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            core, "detect_agents", return_value=["Codex"]
        ), mock.patch.object(core, "detected_server_names", return_value={"existing"}):
            default_context = core.collect_context(Path(directory))
            opted_in_context = core.collect_context(Path(directory), include_agent_configs=True)
            self.assertEqual(default_context.detected_agents, [])
            self.assertEqual(default_context.installed_servers, set())
            self.assertEqual(opted_in_context.detected_agents, ["Codex"])
            self.assertEqual(opted_in_context.installed_servers, {"existing"})

    def test_configured_server_names_ignore_server_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                '[mcp_servers.database]\ncommand = "secret-command"\n'
                '[mcp_servers.database.env]\nAPI_TOKEN = "hiddenvalue"\n'
            )
            self.assertEqual(core.configured_server_names(path), {"database"})


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.context = core.ProjectContext(root=Path("/tmp/dashboard"))
        self.context.terms.update(core.tokenize("react typescript playwright accessibility frontend browser testing"))
        core.expand_capabilities(self.context.terms)
        self.rows = [
            {
                "mcp_id": "a" * 16,
                "tool_name": "scan_accessibility",
                "server_name": "browser-a11y",
                "tool_description": "Run browser accessibility tests for React pages with Playwright",
                "task_text": "Test web applications",
                "occupation_title": "Web Developers",
            },
            {
                "mcp_id": "b" * 16,
                "tool_name": "cancel_order",
                "server_name": "commerce",
                "tool_description": "Cancel and refund a customer order",
                "task_text": "Cancel orders",
                "occupation_title": "Online Merchants",
            },
        ]

    def test_relevant_tool_ranks_first(self):
        candidates = core.rank_candidates(self.context, self.rows, limit=2)
        self.assertEqual(candidates[0].row["tool_name"], "scan_accessibility")

    def test_repository_workflow_contributes_to_candidate_fit(self):
        self.context.workflows = {"Test and quality checks": ["test directory"]}
        candidates = core.rank_candidates(self.context, self.rows, limit=2)
        self.assertIn("Test and quality checks", candidates[0].workflow_fit)

    def test_destructive_tool_is_high_risk(self):
        level, signals = core.classify_risk("Delete an order and issue a refund")
        self.assertEqual(level, "high")
        self.assertIn("delete", signals)

    def test_report_does_not_include_absolute_project_path(self):
        candidate = core.rank_candidates(self.context, self.rows, limit=1)[0]
        report = core.render_report(self.context, [candidate])
        self.assertNotIn("/tmp/dashboard", report)
        self.assertIn("ToolFit recommendations for dashboard", report)
        self.assertIn("An MCP tool is a callable function", report)
        self.assertIn("until you delete them", report)
        self.assertIn("Agent configuration check: not requested", report)
        self.assertIn("Considered", report)

    def test_report_distinguishes_checked_agent_configuration(self):
        self.context.agent_configs_checked = True
        self.context.detected_agents = []
        report = core.render_report(self.context, [])
        self.assertIn("no recognized agent folders found", report)

    def test_candidate_assessment_keeps_unverified_compatibility_bounded(self):
        candidate = core.Candidate(
            score=1,
            row={
                "tool_name": "query_database",
                "server_name": "database-reader",
                "tool_description": "Read database records through a local stdio server",
                "github_pushed_at": "2026-08-01T00:00:00Z",
            },
            signals=[],
            risk_level="medium",
            risk_signals=["database"],
        )
        core.assess_candidate(candidate)
        self.assertIn("possible via stdio", candidate.compatibility["Codex"])
        self.assertIn("not tested", candidate.compatibility["Cursor"])
        self.assertEqual(candidate.maintenance, "recently updated")
        self.assertIn("database", candidate.permission_signals)
        self.assertEqual(candidate.security_review, "required before use")

    def test_unknown_transport_does_not_become_compatibility_claim(self):
        candidate = core.Candidate(
            score=1,
            row={"tool_name": "search_docs", "tool_description": "Search documentation"},
            signals=[],
            risk_level="low",
            risk_signals=[],
        )
        core.assess_candidate(candidate)
        self.assertTrue(all(value.startswith("unknown") for value in candidate.compatibility.values()))
        candidate.repository_transport_checked = True
        core.assess_candidate(candidate)
        self.assertIn("attempted repository metadata", candidate.compatibility["Codex"])

    def test_repository_evidence_can_establish_transport_compatibility(self):
        candidate = core.Candidate(
            score=1,
            row={"tool_name": "search_docs", "tool_description": "Search documentation"},
            signals=[],
            risk_level="low",
            risk_signals=[],
            transport_evidence={"stdio": ["README.md", "server.json"]},
        )
        core.assess_candidate(candidate)
        self.assertIn("possible via stdio in README.md, server.json", candidate.compatibility["Codex"])

    def test_review_bundle_is_inert_and_approval_gated(self):
        candidate = core.Candidate(
            score=1,
            row={"tool_name": "search_docs", "server_name": "docs"},
            signals=[],
            risk_level="low",
            risk_signals=[],
        )
        core.assess_candidate(candidate)
        bundle = core.render_review_config(self.context, [candidate])
        self.assertIn(".review", bundle)
        self.assertIn("enabled = false", bundle)
        self.assertIn('default_tools_approval_mode = "prompt"', bundle)
        self.assertIn("REPLACE_WITH_DOCUMENTED_SERVER_READ_ONLY_ARGUMENT", bundle)
        self.assertNotIn("/tmp/dashboard", bundle)
        json_blocks = re.findall(r"```json\n(.*?)\n```", bundle, re.DOTALL)
        toml_blocks = re.findall(r"```toml\n(.*?)\n```", bundle, re.DOTALL)
        self.assertEqual(len(json_blocks), 2)
        self.assertEqual(len(toml_blocks), 2)
        for block in json_blocks:
            json.loads(block)
        for block in toml_blocks:
            tomllib.loads(block)

    def test_review_bundle_does_not_embed_an_untrusted_tool_name_in_config(self):
        candidate = core.Candidate(
            score=1,
            row={"tool_name": "bad```\n[open](https://attacker.invalid)", "server_name": "docs"},
            signals=[],
            risk_level="low",
            risk_signals=[],
        )
        core.assess_candidate(candidate)
        bundle = core.render_review_config(self.context, [candidate])
        self.assertIn('enabled_tools = ["REPLACE_WITH_VERIFIED_READ_ONLY_TOOL"]', bundle)
        self.assertNotIn("enabled_tools = [\"bad```", bundle)

    def test_report_shortens_descriptions_at_a_word_boundary(self):
        candidate = core.Candidate(
            score=1,
            row={"tool_name": "long", "server_name": "example", "tool_description": "word " * 120},
            signals=[],
            risk_level="low",
            risk_signals=[],
        )
        report = core.render_report(self.context, [candidate])
        description_line = next(line for line in report.splitlines() if "Published description:" in line)
        self.assertTrue(description_line.endswith("word…"))

    def test_report_escapes_untrusted_markdown(self):
        candidate = core.Candidate(
            score=1,
            row={
                "tool_name": "[click](https://attacker.invalid)",
                "server_name": "<script>alert(1)</script>",
                "tool_description": "![track](https://attacker.invalid/pixel)",
            },
            signals=["browser"],
            risk_level="low",
            risk_signals=[],
        )
        report = core.render_report(self.context, [candidate])
        self.assertNotIn("![track]", report)
        self.assertNotIn("<script>", report)
        self.assertIn("\\[click\\]", report)

    def test_existing_server_is_recommended_with_configuration_evidence(self):
        self.context.installed_servers.add("browser-a11y")
        candidates = core.rank_candidates(self.context, self.rows, limit=2)
        self.assertEqual(candidates[0].row["server_name"], "browser-a11y")
        self.assertEqual(candidates[0].availability, "configured")
        self.assertIn("not tested", candidates[0].availability_evidence)

    def test_report_signals_do_not_disclose_private_project_terms(self):
        context = core.ProjectContext(root=Path("/tmp/privatecodename"))
        context.terms.update(core.tokenize("privatecodename react browser testing"))
        candidate = core.rank_candidates(context, [{
            "mcp_id": "c" * 16,
            "tool_name": "privatecodename_browser_test",
            "server_name": "testing",
            "tool_description": "Test privatecodename React applications in a browser",
            "task_text": "Browser testing for applications",
            "occupation_title": "Web Developers",
        }], limit=1)[0]
        report = core.render_report(context, [candidate])
        self.assertNotIn("Matching signals: privatecodename", report)


class CatalogTests(unittest.TestCase):
    def test_catalog_download_writes_only_returned_rows(self):
        responses = [
            {"num_rows_total": 2, "rows": [{"row": {"tool_name": "one"}}]},
            {"num_rows_total": 2, "rows": [{"row": {"tool_name": "two"}}]},
        ]
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            core, "_request_json", side_effect=responses
        ):
            destination = Path(directory) / "catalog.jsonl"
            core.download_catalog(destination)
            rows = list(core.iter_catalog(destination))
            self.assertEqual([row["tool_name"] for row in rows], ["one", "two"])

    def test_offline_enrichment_rejects_untrusted_repository_url(self):
        candidate = core.Candidate(
            score=1,
            row={"github_url": "https://attacker.invalid/repository"},
            signals=[],
            risk_level="low",
            risk_signals=[],
        )
        core.enrich_candidates([candidate], offline=True)
        self.assertIsNone(candidate.repository)


class RepositoryCompatibilityTests(unittest.TestCase):
    def test_reads_explicit_transport_evidence_from_public_metadata(self):
        files = {
            "README.md": 'Configure with {"mcpServers":{"example":{"command":"npx"}}}. Supports Streamable HTTP.',
            "package.json": '{"description":"ordinary package"}',
            "server.json": '{"transport":"SSEServerTransport"}',
        }
        with mock.patch.object(
            core,
            "_read_public_github_file",
            side_effect=lambda _repository, _branch, filename: files.get(filename),
        ):
            evidence = core.repository_transport_evidence(
                "https://github.com/example/server",
                "main",
            )
        self.assertEqual(evidence["stdio"], ["README.md"])
        self.assertEqual(evidence["http"], ["README.md"])
        self.assertEqual(evidence["sse"], ["server.json"])

    def test_rejects_unrecognized_repository_urls_before_network_access(self):
        with mock.patch.object(core.urllib.request, "urlopen") as urlopen:
            result = core._read_public_github_file(
                "https://attacker.invalid/example/server",
                "main",
                "README.md",
            )
        self.assertIsNone(result)
        urlopen.assert_not_called()

    def test_reuses_repository_evidence_across_candidate_batches(self):
        def candidate():
            return core.Candidate(
                score=1,
                row={"github_url": "https://github.com/example/server"},
                signals=[],
                risk_level="low",
                risk_signals=[],
            )

        cache = {}
        with mock.patch.object(
            core,
            "github_health",
            return_value={"status": "screened", "default_branch": "main", "warnings": []},
        ) as health, mock.patch.object(
            core,
            "repository_transport_evidence",
            return_value={"stdio": ["README.md"]},
        ) as evidence:
            core.enrich_candidates([candidate()], repository_cache=cache)
            core.enrich_candidates([candidate()], repository_cache=cache)
        health.assert_called_once()
        evidence.assert_called_once()


class WorkflowDetectionTests(unittest.TestCase):
    def test_detects_workflow_surfaces_without_retaining_script_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "package.json").write_text(json.dumps({
                "scripts": {"test:e2e": "secret-command --token hiddenvalue"}
            }))
            context = core.collect_context(root)
            self.assertIn("Test and quality checks", context.workflows)
            self.assertIn("Continuous integration", context.workflows)
            rendered = json.dumps(context.workflows)
            self.assertNotIn("secret-command", rendered)
            self.assertNotIn("hiddenvalue", rendered)


if __name__ == "__main__":
    unittest.main()
