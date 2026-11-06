# Graph Report - 家庭财务收支与物资全生命周期智能管理系统 V1.0  (2026-11-06)

## Corpus Check
- Corpus is ~17,081 words - fits in a single context window. You may not need a graph.

## Summary
- 414 nodes · 515 edges · 56 communities (22 shown, 34 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 36 edges (avg confidence: 0.86)
- Token cost: 80,326 input · 32,369 output

## Community Hubs (Navigation)
- Application Health and Configuration
- Identity Persistence and Ownership
- Architecture and Delivery Evidence
- Database Migration Verification
- Engineering Skills and Standards
- Identity Cryptography and Validation
- PostgREST Sandbox Configuration
- Continuous Integration Pipeline
- Development Database Configuration
- Identity Integration Ports
- Delivery Roadmap and Risks
- Planned Domain Modules
- Rate Limit Persistence
- Design and Domain Vocabulary
- Household Roles and Gates
- Project Governance and Scope
- Linear Design Reference
- Inventory and Recipe Algorithms
- Engineering Progress Records
- Modular Monolith Architecture
- Architecture Decision Tracking
- Household Inventory Decisions
- Authentication API Design
- Localization Decision
- Recipe Allocation Decision
- Business Process References
- Copyright Documentation
- Deployment Documentation
- Security Documentation
- Testing Documentation
- Security Reporting
- HTTP Framework References
- Database Initialization Script
- Project Changelog
- Ledger Decision
- Authentication Decision
- Deployment Operations
- FEFO Allocation
- Project Glossary
- Inventory Movements
- REST API Contracts
- PostgreSQL Storage
- Pytest Framework
- Open Decisions
- Project Identity
- Known Issues
- Engineering Metrics
- Recovery Requirement
- Valuation Requirement

## God Nodes (most connected - your core abstractions)
1. `Base` - 19 edges
2. `SqlAlchemyIdentityRepository` - 18 edges
3. `Agents Operating Rules` - 15 edges
4. `Key` - 12 edges
5. `Traceability Matrix` - 9 edges
6. `PostgreSQL V1 Schema Specification` - 8 edges
7. `get_settings()` - 7 edges
8. `SQLAlchemy` - 7 edges
9. `readiness()` - 6 edges
10. `User` - 6 edges

## Surprising Connections (you probably didn't know these)
- `test_upgrade_downgrade_upgrade()` --uses--> `Base`  [INFERRED]
  tests/test_migration.py → app/db/base.py
- `code-reviewer` --references--> `Agents Operating Rules`  [EXTRACTED]
  .agents/skills/code-reviewer/SKILL.md → .project/multi-agent-coding.md
- `database-engineer` --references--> `Agents Operating Rules`  [EXTRACTED]
  .agents/skills/database-engineer/SKILL.md → .project/multi-agent-coding.md
- `devops-release` --references--> `Agents Operating Rules`  [EXTRACTED]
  .agents/skills/devops-release/SKILL.md → .project/multi-agent-coding.md
- `documentation-engineer` --references--> `Agents Operating Rules`  [EXTRACTED]
  .agents/skills/documentation-engineer/SKILL.md → .project/multi-agent-coding.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Algorithm Dependent Skills** — agents_skills_inventory_lifecycle_skill_inventory_lifecycle, agents_skills_recipe_engine_skill_recipe_engine, memory_bank_6_algorithms_md [EXTRACTED 0.90]
- **Checkout Coordination Flow** — checkout_application_service, finance_module, inventory_module [EXTRACTED 0.90]
- **Inventory Management Concepts** — memory_bank_14_glossary_inventory_lot, memory_bank_14_glossary_inventory_movement, memory_bank_14_glossary_disposal, memory_bank_14_glossary_fefo, memory_bank_14_glossary_waste_cost [EXTRACTED 0.90]
- **Inventory Management Flow** — memory_bank_5_api_contracts_inventory, memory_bank_6_algorithms_fefo, memory_bank_6_algorithms_freshness [EXTRACTED 0.90]
- **Phase 02 Execution Flow** — p02_01, p02_02, project_status [EXTRACTED 0.90]
- **Project Governance and Task Lifecycle** — project_decisionlog, project_multiagentcoding, project_taskboard, memorybank_15openquestions [EXTRACTED 0.90]
- **Authentication Security Stack** — memory_bank_5_api_contracts_auth, memory_bank_7_security_policy_argon2id, memory_bank_7_security_policy_jwt [EXTRACTED 0.95]
- **Database Design Context** — docs_database_readme, docs_database_schema_v1, docs_diagrams_database_erd, memory_bank_3_database_design [EXTRACTED 1.00]
- **Linear Design System** — docs_design_references_awesome_design_md_linear_design_analysis_colors, docs_design_references_awesome_design_md_linear_design_analysis_typography, docs_design_references_awesome_design_md_linear_design_analysis_components [EXTRACTED 1.00]
- **Project Implementation Phases** — project_task_board_p00_01, project_task_board_p01_01, project_task_board_p02_01, project_task_board_p02_02, project_task_board_p03_01, project_task_board_p04_01, project_task_board_p05_01, project_task_board_p06_01, project_task_board_p07_01, project_task_board_p08_01, project_task_board_p09_01, project_task_board_p10_01 [EXTRACTED 1.00]
- **Role-Based Access Control Hierarchy** — role_owner, role_admin, role_finance_manager, role_inventory_manager, role_member, role_viewer [EXTRACTED 1.00]
- **System Requirements** — requirement_id_01, requirement_fin_01, requirement_inv_01, requirement_life_01, requirement_waste_01, requirement_rec_01, requirement_ux_01, requirement_ops_01 [EXTRACTED 1.00]
- **Core Technology Stack** — fastapi_backend, react_client, postgresql_db [EXTRACTED 1.00]
- **Data Integrity and Traceability** — docs_architecture_decisions_adr0002householddatamodel_adr0002, docs_architecture_decisions_adr0003financialledger_adr0003, docs_architecture_decisions_adr0004inventorylotmodel_adr0004 [INFERRED 0.70]
- **Project Governance and Documentation** — readme, contributing, project_status, security [INFERRED 0.80]
- **Agent Skill Definitions** — _agents_skills_code_reviewer_skill_code_reviewer, _agents_skills_database_engineer_skill_database_engineer, _agents_skills_devops_release_skill_devops_release, _agents_skills_documentation_engineer_skill_documentation_engineer [INFERRED 0.90]
- **Agent Skills** — agents_skills_fastapi_engineer_skill, agents_skills_finance_domain_skill, agents_skills_harness_author_skill, agents_skills_i18n_accessibility_skill [INFERRED 0.90]
- **Architecture Decision Records** — docs_architecture_decisions_adr0006authenticationandauthorization_adr0006, docs_architecture_decisions_adr0007internationalization_adr0007, docs_architecture_decisions_adr0008reciperanking_adr0008 [INFERRED 0.90]
- **Project Governance and Tracking** — _project_build_log_build_log, _project_current_phase_current_phase [INFERRED 0.90]
- **Project Governance and Planning** — memory_bank_1_project_brief, memory_bank_10_implementation_roadmap, project_task_board [INFERRED 0.90]

## Communities (56 total, 34 thin omitted)

### Community 0 - "Application Health and Configuration"
Cohesion: 0.08
Nodes (12): liveness(), readiness(), get_settings(), Settings, dispose_engine(), get_engine(), get_session_factory(), create_app() (+4 more)

### Community 1 - "Identity Persistence and Ownership"
Cohesion: 0.13
Nodes (16): Base, normalize_email(), AuditLog, AuthAuditEvent, AuthChallenge, AuthSession, Household, HouseholdInvitation (+8 more)

### Community 2 - "Architecture and Delivery Evidence"
Cohesion: 0.06
Nodes (31): ADR-0002, ADR-0003, ADR-0004, ADR-0005, ADR-0006, ADR-0007, ADR-0008, Alembic (+23 more)

### Community 3 - "Database Migration Verification"
Cohesion: 0.10
Nodes (11): do_run_migrations(), run_async_migrations(), run_migrations_online(), SQLAlchemy, disposable_database_url(), identity_database(), migrate(), table_names() (+3 more)

### Community 4 - "Engineering Skills and Standards"
Cohesion: 0.07
Nodes (33): code-reviewer, database-engineer, devops-release, documentation-engineer, System Architect Skill, Test Engineer Skill, Agents Operating Rules, fastapi-engineer (+25 more)

### Community 5 - "Identity Cryptography and Validation"
Cohesion: 0.09
Nodes (7): ChallengePurpose, RoleCode, UserState, validate_password(), Argon2PasswordHasher, IdentitySecurity, token_digest()

### Community 6 - "PostgREST Sandbox Configuration"
Cohesion: 0.08
Nodes (24): condition, environment, healthcheck, image, ports, volumes, db, PGRST_DB_ANON_ROLE (+16 more)

### Community 7 - "Continuous Integration Pipeline"
Cohesion: 0.09
Nodes (22): env, image, options, ports, DATABASE_URL, POSTGRES_HOST_AUTH_METHOD, jobs, test (+14 more)

### Community 8 - "Development Database Configuration"
Cohesion: 0.13
Nodes (14): environment, healthcheck, image, ports, pull_policy, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER (+6 more)

### Community 9 - "Identity Integration Ports"
Cohesion: 0.16
Nodes (3): EmailProvider, IdentityRepository, PasswordHasher

### Community 10 - "Delivery Roadmap and Risks"
Cohesion: 0.15
Nodes (14): Release Checklist, Risk Register, P00-01: Repository discovery and governance, P01-01: ADRs, ERD, PostgreSQL schema specification, contracts, and traceability, P02-01: Toolchain, minimal service, Compose, Alembic, and CI, P02-02: Identity, households, and RBAC, P03-01: Ledger, payments, reversals, and reconciliation, P04-01: Products, lots, movements, and checkout (+6 more)

### Community 11 - "Planned Domain Modules"
Cohesion: 0.27
Nodes (10): Checkout Application Service, ADR-0001 modular monolith, Finance Module, Identity Module, Inventory Module, Lifecycle Module, PostgreSQL Logical Design, Business Rules (+2 more)

### Community 13 - "Design and Domain Vocabulary"
Cohesion: 0.22
Nodes (9): Linear Design Reference, Awesome DESIGN.md, UI and UX Guidelines, Copyright Documentation Plan, Disposal, Household, Inventory Lot, Ledger Entry (+1 more)

### Community 14 - "Household Roles and Gates"
Cohesion: 0.29
Nodes (7): Pre-Phase-02 Gates Resolved, ADMIN Role, FINANCE_MANAGER Role, INVENTORY_MANAGER Role, MEMBER Role, OWNER Role, VIEWER Role

### Community 15 - "Project Governance and Scope"
Cohesion: 0.47
Nodes (6): AGENTS.md, Contributing, Implementation Roadmap, Project Brief, Task Board, README

### Community 16 - "Linear Design Reference"
Cohesion: 0.33
Nodes (6): Linear Colors, Linear Components, Linear Typography, Linear Design Analysis, Awesome DESIGN.md references, Linear App Website

### Community 17 - "Inventory and Recipe Algorithms"
Cohesion: 0.40
Nodes (5): Inventory API Group, Recipes API Group, FEFO Allocation Algorithm, Freshness Algorithm, Recipe Scoring Algorithm

### Community 18 - "Engineering Progress Records"
Cohesion: 0.50
Nodes (4): Build Log, Current Phase, Awesome DESIGN.md, verification-2026-11-06.md

### Community 19 - "Modular Monolith Architecture"
Cohesion: 0.50
Nodes (4): FastAPI Modular Monolith, Architecture Baseline, PostgreSQL 16+, React Client

### Community 20 - "Architecture Decision Tracking"
Cohesion: 0.67
Nodes (3): Architecture Decision Records (ADRs), Open Questions, Decision Log

### Community 21 - "Household Inventory Decisions"
Cohesion: 0.67
Nodes (3): ADR-0002 household data model, ADR-0004 inventory lot model, ADR-0005 lifecycle state model

### Community 22 - "Authentication API Design"
Cohesion: 0.67
Nodes (3): Auth API Group, Argon2id Hashing, JWT Authentication

## Knowledge Gaps
- **98 isolated node(s):** `family-finance-inventory`, `memory-bank/3-database-design.md`, `memory-bank/12-deployment-operations.md`, `memory-bank/13-copyright-documentation.md`, `memory-bank/4-business-rules.md` (+93 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 212 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **34 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SQLAlchemy` connect `Database Migration Verification` to `Application Health and Configuration`, `Identity Persistence and Ownership`, `Architecture and Delivery Evidence`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `SqlAlchemyIdentityRepository` (e.g. with `AuthChallenge` and `AuthSession`) actually correct?**
  _`SqlAlchemyIdentityRepository` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `family-finance-inventory`, `memory-bank/3-database-design.md`, `memory-bank/12-deployment-operations.md` to the rest of the system?**
  _98 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Application Health and Configuration` be split into smaller, more focused modules?**
  _Cohesion score 0.08250355618776671 - nodes in this community are weakly interconnected._
- **Why does `PostgreSQL V1 Schema Specification` connect `Architecture and Delivery Evidence` to `Database Migration Verification`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Should `Identity Persistence and Ownership` be split into smaller, more focused modules?**
  _Cohesion score 0.12612612612612611 - nodes in this community are weakly interconnected._
- **Should `Architecture and Delivery Evidence` be split into smaller, more focused modules?**
  _Cohesion score 0.06218487394957983 - nodes in this community are weakly interconnected._
## Build Audit

- Graphify version: 0.9.103.
- Semantic backend: Gemini, using the existing environment configuration.
- Semantic source coverage: 69/69 documents have at least one node; this does not prove exhaustive extraction.
- Seven Mermaid diagrams and other unsupported files were not extracted.
- Existing working-tree changes were preserved.
- `graphify-out/` is not ignored and appears in Git status; choose which outputs to share.
- Token totals include the initial low-coverage request and successful retry requests; failed requests may have unreported provider usage.

```text
[graphify] MultiDiGraph edge-collapse diagnostic
input: <in-memory>
input_stage: provided JSON (normal graph.json is post-build)
effective_directed: <direct-call>
nodes: 386
unverified_code_nodes: 0
raw_edges: 549
valid_candidate_edges: 477
missing_endpoint_edges: 0
dangling_endpoint_edges: 72
external_reference_edges: 0
self_loop_edges: 0
exact_duplicate_edges: 0
directed_unique_endpoint_pairs: 454
directed_same_endpoint_collapsed_edges: 23
undirected_unique_endpoint_pairs: 454
undirected_same_endpoint_collapsed_edges: 23
same_endpoint_group_count: 19
relation_variant_groups: 16
source_file_variant_groups: 0
source_location_variant_groups: 3
context_variant_groups: 0
post_build_graph_type: Graph
post_build_edges: 515
producer_suppression_sites: 12
producer_suppression_examples:
  - L1859 seen_ids arity=unknown
  - L2554 seen_ids arity=unknown
  - L2556 seen_doc_refs arity=unknown
  - L3223 seen_ids arity=unknown
  - L3370 seen_ids arity=unknown
  - L4784 seen_keys arity=unknown
  - L4970 seen_keys arity=unknown
  - L8790 seen_ids arity=unknown
examples:
  - github_workflows_ci_test_steps -> github_workflows_ci_steps_name edges=4 relations=['contains'] locations=['L30', 'L32', 'L34', 'L36'] contexts=['']
  - github_workflows_ci_test_steps -> github_workflows_ci_steps_run edges=4 relations=['contains'] locations=['L31', 'L33', 'L35', 'L37'] contexts=['']
  - github_workflows_ci_test_steps -> github_workflows_ci_steps_uses edges=2 relations=['contains'] locations=['L26', 'L27'] contexts=['']
  - app_core_config_get_settings -> app_core_config_settings edges=2 relations=['calls', 'references'] locations=['L15', 'L16'] contexts=['call', 'return_type']
  - app_identity_infrastructure_models_user -> app_db_base_base edges=2 relations=['inherits', 'uses'] locations=['L21'] contexts=['']
note: normal graph.json is post-build; raw producer loss must be measured earlier.
```
