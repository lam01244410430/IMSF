# Local knowledge graph verification - 2026-11-06

Scope: user-requested Graphify analysis of the current working tree. No application code, schema, or architecture was changed. Existing changes were preserved.

- Detected 99 supported files: 30 code and 69 documents, approximately 17,081 words.
- Exported 414 nodes, 515 edges, and 56 communities to `../graphify-out/`.
- All 69 documents have at least one semantic node; this is not exhaustive semantic coverage evidence.
- Validated unique exported node IDs, exported edge endpoints, community labels, parseable JSON, an HTML document, and the incremental manifest. Hashes are recorded in `../graphify-out/verification.json`.
- Extraction diagnostics: 72 dangling-endpoint edges and 23 same-endpoint edge collapses; no missing endpoint fields or self-loops. The exported graph contains placeholder nodes created by Graphify, so endpoint validity does not resolve extraction-level warnings.
- Seven Mermaid files were unclassified and were not extracted. The ignored local environment file was not included.
- Gemini extraction used existing environment configuration. Two rate-limited chunks were retried successfully. Reported total: 80,326 input and 32,369 output tokens; failed requests may have unreported usage.
- Application tests were not rerun because this task generated analysis artifacts and engineering records only. P02-02 remains in progress; this graph is not runtime acceptance evidence for ID-01 or other product requirements.
- Graphify output is not ignored by Git. No commit, push, deployment, or migration was performed.
- Project-record additions after extraction are newer than this snapshot and will require a later graph update.

Review: a separate read-only validation pass checked exported structural consistency and artifact presence. Browser rendering and exhaustive semantic fact checking were not performed.
