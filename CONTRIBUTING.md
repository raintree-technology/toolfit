# Contributing

Contributions should improve recommendation relevance, privacy, compatibility evidence, or repository screening without executing recommended tools.

Before opening a pull request:

1. Add focused tests for behavior changes.
2. Run `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
3. Confirm that no fixture contains a real credential, private path, or copied third-party dataset row.
4. Explain any new network request and the exact data it transmits.
5. Preserve the experimental status unless evidence supports a stronger claim.

Do not add downloaded catalogs, third-party dataset descriptions, scan reports, or private repository metadata to this repository.

For built-in catalog entries, write an original description, cite primary documentation, record the review date, and state applicability and access requirements.
