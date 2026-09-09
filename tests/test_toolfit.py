import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from toolfit import available, catalogs, core
from toolfit.cli import main


def row(name, kind="tool", description="Python testing quality checks for code", **extra):
    return catalogs.normalize({"name": name, "kind": kind, "description": description, **extra})


class ToolFitTests(unittest.TestCase):
    def test_task_selects_different_capabilities_for_same_project(self):
        context = core.ProjectContext(root=Path('/tmp/project'))
        rows = [row('Release checks', description='Verify release artifacts and deployment checks'),
                row('Database reader', description='Read database schema and query SQL records')]
        context.task_terms = core.tokenize('release')
        self.assertEqual([c.row['tool_name'] for c in core.rank_candidates(context, rows)], ['Release checks'])
        context.task_terms = core.tokenize('database')
        self.assertEqual([c.row['tool_name'] for c in core.rank_candidates(context, rows)], ['Database reader'])

    def test_declared_tool_precedes_new_tool_without_claiming_installation(self):
        context = core.ProjectContext(root=Path('/tmp/project'), declared_packages={'ruff'})
        context.task_terms = core.tokenize('python testing')
        candidates = core.rank_candidates(context, [row('New tool'), row('Ruff', package_names='ruff')])
        self.assertEqual(candidates[0].row['tool_name'], 'Ruff')
        self.assertEqual(candidates[0].availability, 'declared')
        self.assertIn('not tested', candidates[0].availability_evidence)

    def test_unrelated_installed_tool_does_not_displace_task_match(self):
        context = core.ProjectContext(root=Path('/tmp/project'), declared_packages={'ruff'})
        context.task_terms = core.tokenize('database')
        candidates = core.rank_candidates(context, [row('Ruff', package_names='ruff'),
            row('Database reader', description='Read database records and schema definitions')])
        self.assertEqual([c.row['tool_name'] for c in candidates], ['Database reader'])

    def test_non_mcp_candidates_get_requirements_and_no_mcp_templates(self):
        context = core.ProjectContext(root=Path('/tmp/project'), task_terms=core.tokenize('testing'))
        candidates = core.rank_candidates(context, [row('Native tests', kind='native')])
        core.enrich_candidates(candidates, offline=True)
        self.assertEqual(list(candidates[0].compatibility), ['Requirements'])
        self.assertNotIn('```', core.render_review_config(context, candidates))

    def test_deduplication_preserves_publishers_and_source_evidence(self):
        context = core.ProjectContext(root=Path('/tmp/project'), task_terms=core.tokenize('testing'))
        rows = [row('check', github_url='https://github.com/one/check', source_name='First'),
                row('check', github_url='https://github.com/one/check', source_name='Second'),
                row('check', github_url='https://github.com/two/check', source_name='Third')]
        candidates = core.rank_candidates(context, rows)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(len(candidates[0].provenance), 2)

    def test_python_dependencies_and_skills_preserve_metadata_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'pyproject.toml').write_text('[project]\ndependencies = ["ruff>=1", "pytest"]\n[project.scripts]\ncheck="private-command:main"\n')
            skills = root/'.agents/skills/release'
            skills.mkdir(parents=True)
            (skills/'SKILL.md').write_text('---\nname: release-check\ndescription: Verify release artifacts before deployment\n---\nPRIVATE_BODY_SECRET\n')
            context = core.collect_context(root, task='release')
            self.assertEqual(context.declared_packages, {'ruff', 'pytest'})
            candidates = core.rank_candidates(context, context.available_rows)
            self.assertEqual(candidates[0].availability, 'present')
            report = core.render_report(context, candidates)
            self.assertNotIn('PRIVATE_BODY_SECRET', report)
            self.assertNotIn('private-command', report)

    def test_home_skills_remain_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root/'home'
            project = root/'project'
            project.mkdir()
            skill = home/'.codex/skills/check'
            skill.mkdir(parents=True)
            (skill/'SKILL.md').write_text('---\nname: check\ndescription: Python testing and quality checks\n---\n')
            with mock.patch.object(Path, 'home', return_value=home):
                self.assertFalse(core.collect_context(project).available_rows)
                self.assertEqual(len(core.collect_context(project, include_agent_configs=True).available_rows), 1)

    def test_builtin_and_local_catalog_cli_are_offline_and_task_aware(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root/'project'
            project.mkdir()
            (project/'example.py').write_text('do not execute')
            catalog = root/'catalog.jsonl'
            catalog.write_text(json.dumps({'name':'Python helper','kind':'plugin',
                'description':'Python testing checks and code quality review'})+'\n')
            output = io.StringIO()
            with mock.patch('urllib.request.urlopen') as network, mock.patch.object(catalogs, 'registry_page') as registry, contextlib.redirect_stdout(output):
                result = main([str(project), '--catalog', str(catalog), '--source', 'builtin', '--task', 'python testing', '--offline'])
            self.assertEqual(result, 0)
            network.assert_not_called()
            registry.assert_not_called()
            self.assertIn('Python unittest', output.getvalue())
            self.assertIn('Python helper', output.getvalue())
            self.assertIn('built in', output.getvalue())

    def test_source_failure_is_visible_in_partial_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output, errors = io.StringIO(), io.StringIO()
            with mock.patch('toolfit.cli.cache_path', return_value=Path(directory)/'missing'), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                result = main([directory, '--source', 'builtin', '--source', 'registry', '--offline'])
            self.assertEqual(result, 0)
            self.assertIn('registry: unavailable', output.getvalue())
            self.assertIn('[ATE102]', errors.getvalue())

    def test_builtin_language_requirements_prevent_cross_language_noise(self):
        context = core.ProjectContext(root=Path('/tmp/project'), task_terms=core.tokenize('python testing'))
        context.terms.update(core.tokenize('python code'))
        candidates = core.rank_candidates(context, catalogs.builtin_rows())
        names = [c.row['tool_name'] for c in candidates]
        self.assertIn('Ruff', names)
        self.assertIn('Python unittest', names)
        self.assertNotIn('Biome', names)
        self.assertNotIn('Playwright', names)

    def test_reports_link_sources_and_preserve_unknown_dates(self):
        context = core.ProjectContext(root=Path('/tmp/project'), task_terms=core.tokenize('testing'))
        candidate = core.rank_candidates(context, [row('Checks', source_url='https://example.com/checks', source_name='Example')])[0]
        report = core.render_report(context, [candidate])
        self.assertIn('[Example](https://example.com/checks)', report)
        self.assertIn('Source updated: unknown', report)
        self.assertNotIn('](javascript:', core._source_link('bad', 'javascript:alert(1)'))
        self.assertNotIn('user:password', core._source_link('bad', 'https://user:password@example.com'))


class CatalogTests(unittest.TestCase):
    def page(self, cursor=None):
        return {'servers':[{'server':{'name':'org.example/check','description':'Python testing quality checks',
            'packages':[{'identifier':'example-check','transport':{'type':'stdio'}}],
            'remotes':[{'type':'streamable-http','url':'https://not-contacted.invalid'}]},
            '_meta':{'io.modelcontextprotocol.registry/official':{'status':'active','isLatest':True,'publishedAt':'2026-09-01'}}}],
            'metadata':{'nextCursor':cursor}}

    def test_registry_pagination_dates_and_atomic_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'registry.jsonl'
            with mock.patch.object(catalogs,'registry_page',side_effect=[self.page('opaque'),self.page()]) as fetch:
                catalogs.download_registry(path)
            self.assertEqual(fetch.call_args_list, [mock.call(''),mock.call('opaque')])
            rows=list(catalogs.read_catalog(path))
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['source_updated_at'],'2026-09-01')
            self.assertIn('stdio', rows[0]['transports'])
            self.assertNotIn('not-contacted', path.read_text())
            previous=path.read_bytes()
            with mock.patch.object(catalogs,'registry_page',side_effect=[self.page('same'), self.page('same')]), self.assertRaises(ValueError):
                catalogs.download_registry(path)
            self.assertEqual(path.read_bytes(),previous)

    def test_registry_redirects_and_malformed_rows_are_rejected(self):
        with self.assertRaises(ValueError):
            catalogs.NoRedirect().redirect_request(None,None,302,'',{},'https://private.invalid')
        for value in ['not an object', {'name': []}, {'kind': 'executable'}, {'access':{'secret':'value'}}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                catalogs.normalize(value)

    def test_catalog_line_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'catalog.jsonl'
            path.write_text('x'*(core.MAX_FILE_BYTES+1))
            with self.assertRaises(ValueError):
                list(catalogs.read_catalog(path))

    def test_marketplace_listing_is_not_installed_and_config_requires_exact_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest=root/'.agents/plugins'
            manifest.mkdir(parents=True)
            (manifest/'marketplace.json').write_text(json.dumps({'name':'example','plugins':[{'name':'checks','source':{'source':'local','path':'./plugins/checks'}}]}))
            plugin=root/'plugins/checks/.codex-plugin'
            plugin.mkdir(parents=True)
            (plugin/'plugin.json').write_text(json.dumps({'description':'Python testing quality checks','hooks':{'secret':'IGNORE_THIS'}}))
            rows=list(catalogs.marketplace_rows(root))
            context=core.ProjectContext(root=root,task_terms=core.tokenize('testing'))
            self.assertEqual(core.rank_candidates(context,rows)[0].availability,'new')
            config=root/'.codex'
            config.mkdir()
            (config/'config.toml').write_text('[plugins."checks@example"]\nenabled=true\n[plugins."disabled@example"]\nenabled=false\n')
            context=core.collect_context(root,task='testing')
            self.assertEqual(core.rank_candidates(context,rows)[0].availability,'configured')
            self.assertNotIn('IGNORE_THIS',json.dumps(rows))
            self.assertNotIn('disabled@example', context.enabled_plugins)

    def test_marketplace_cannot_follow_escaping_paths_or_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'catalog'
            root.mkdir()
            outside=Path(directory)/'private.json'
            outside.write_text('{}')
            with self.assertRaises(ValueError):
                catalogs.read_metadata(root/'../private.json',root)
            (root/'linked.json').symlink_to(outside)
            with self.assertRaises(ValueError):
                catalogs.read_metadata(root/'linked.json',root)


if __name__ == '__main__':
    unittest.main()
