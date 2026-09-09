# Evaluation

The current evidence supports an experimental discovery release. It does not establish general recommendation quality, compatibility, or safety.

## Available evidence

The automated test suite covers metadata minimization, agent-configuration opt-in, untrusted links and Markdown, catalog limits, workflow detection, risk and permission labels, bounded repository transport evidence, inert review templates, and one positive ranking example. GitHub Actions runs the tests and package-installation check on Python 3.11 through 3.14.

During development, one reviewer inspected recommendations for 17 local repositories. Those repositories influenced the ranker, and the review did not preserve enough privacy-safe item-level evidence for independent reproduction. This document therefore makes no numerical quality claim from that review.

Future evaluation must use this relevance definition:

> A candidate is relevant when its described capability could plausibly assist the repository based on approved metadata. Relevance does not mean that the server is compatible, maintained, safe, or worth installing.

No recommended MCP server has been compatibility-tested or approved through this project. No numerical relevance, compatibility, or safety claim should be made until the release criterion below is satisfied.

Workflow fit now uses concrete repository surfaces such as test and documentation directories, package-script names, continuous-integration configuration, migration directories, and selected `pyproject.toml` tool names. This is stronger evidence than a generic code-language match, but it does not show that a candidate improves the workflow.

## Observed false positives

- General code-review tools can outrank a more specific integration.
- Documentation-heavy repositories can receive irrelevant document-conversion tools.
- Large mixed-purpose repositories activate too many opportunity classes.
- A server listing and an individual tool can both appear because they describe different capability levels.
- ATE's original occupational labels can be implausible even when the underlying MCP tool is useful.

## Release criterion

Version `0.2.0` remains an experimental discovery release. A future relevance claim requires a versioned scanner commit, a documented repository-selection method, a held-out repository set, privacy-safe item-level labels, more than one independent reviewer, disagreement measurement, and a reproducible scoring procedure. A future compatibility claim also requires successful server-level integration tests. A future safety claim requires source review and behavior testing for each recommended MCP server.

## ToolFit expansion

Focused tests cover task-dependent ranking, existing capability priority, source
attribution, bounded registry pagination, failed-cache preservation, marketplace
path containment, skill metadata privacy, plugin configuration matching, and
network-free offline scans. The built-in catalog begins with five entries.

On 2026-09-08, a complete registry download normalized 28,309 records and
produced a three-candidate ranking. The existing ATE cache supplied 18,058
records and also produced a ranking. These checks validate ingestion against
the observed data; they do not validate the publishers or recommended tools.

All 50 local tests passed. A clean temporary installation verified the `toolfit`
and `ate-scan` commands and the bundled catalog. Built-in entries cite primary
documentation. No user study or held-out relevance evaluation has been run for
the expanded ranker.
