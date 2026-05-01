# SurefirePlugin-Master Migration Plan

## TL;DR

> **Quick Summary**: Migrate essential features from `surefirePlugin-master/` (retry, @id/@dep, tag runner, report merger) into the main project's clean architecture, then delete the legacy directory. The old monolithic Extent plugin is NOT migrated — `extent-integration/` remains the single clean plugin.
>
> **Deliverables**:
> - Retry runner fully integrated into `test-core/` (compatible with Allure adapter)
> - `@id/@dep` dependency resolver in `test-core/`
> - Tag runner scripts (`run-by-tags.ps1`, `run-by-tag.sh`) in `scripts/`
> - `ExtentReportMerger` in `report-model/`
> - `surefirePlugin-master/` directory removed
>
> **Estimated Effort**: Medium (~2-3 gün)
> **Parallel Execution**: YES — 3 waves, 4-5 task/wave
> **Critical Path**: T1 (audit) → T2/T3 (migrate core) → T7 (integration test) → T10 (cleanup)

---

## Context

### Original Request
User asked whether surefirePlugin-master features were already migrated to the main project. Investigation shows: **NO, they were not fully migrated.** Parts exist in cleaner forms in the main project, but key features remain only in `surefirePlugin-master/`.

### Current State (surefirePlugin-master/)
- `CucumberRetryRunnerTest.java` (393 lines): Retry with `--retry-count N`, file-based state
- `@id:/@dep:` tag parser + toposort dependency graph
- `run-by-tags.ps1` + `run-by-tag.sh`: Tag-based execution
- `ExtentCucumberPlugin.java` (546 lines): Monolithic plugin with WebDriver management
- `ExtentReportMerger.java`: HTML report merger
- `DiscoveryPlugin.java`: --dry-run scenario discovery
- `FailureCapturePlugin.java`: feature:line capture

### Current State (Main Project)
- `test-core/RetryTestRunner`: Basic retry demo (not production)
- `test-core/DependencyResolver`: Clean dependency parser
- `extent-integration/ExtentCucumberPlugin` (184 lines): Clean plugin, NO WebDriver management
- `allure-integration/`: Screenshot + video hooks (separate from plugins)
- `test-core/cucumber.properties`: Loads both Allure + Extent adapters

### Metis Review Findings
- **DO NOT** migrate old `ExtentCucumberPlugin` wholesale — `extent-integration/` is the single clean plugin
- **DO** migrate missing behaviors: retry, dependency, tag runner, report merger
- **DO NOT** port WebDriver management into plugins — keep it separate
- **Risk**: Allure retry pollution (duplicate JSON files per attempt)
- **Risk**: Duplicate dependency parsing if not consolidated

### Technical Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Extent plugin | Keep `extent-integration/` only | Clean 184-line vs monolithic 546-line |
| WebDriver | Outside plugins | Existing architecture: `allure-integration/` hooks manage media |
| Retry | Migrate to `test-core/` | Must be compatible with Allure adapter |
| Tag runner | Migrate scripts to `scripts/` | Centralize execution scripts |
| Report merger | Migrate to `report-model/` | Shared utility for pipeline |

---

## Work Objectives

### Core Objective
Consolidate test execution features from `surefirePlugin-master/` into the main Maven project, eliminating the separate legacy project while preserving all functionality.

### Concrete Deliverables
- `test-core/RetryTestRunner.java` — production retry with file-based state
- `test-core/DependencyResolver.java` — enhanced with surefirePlugin-master features
- `scripts/run-by-tags.ps1` and `scripts/run-by-tag.sh` — tag-based test runner
- `report-model/ExtentReportMerger.java` — report merging utility
- Deleted `surefirePlugin-master/` directory
- Updated documentation

### Definition of Done
- `mvn -q validate` → BUILD SUCCESS
- `mvn -q -pl test-core test` → PASS (with retry scenarios)
- `mvn -q -pl test-core test -Dcucumber.filter.tags="@smoke"` → PASS (use a passing tag for build verification, not @sample-fail which intentionally fails)
- Allure results generated under `test-core/target/allure-results/`
- Extent report generated under expected path
- Retry scenario passes after N attempts
- Dependency-skipped scenarios behave deterministically
- No references to `surefirePlugin-master/` remain (except migration note)

### Must Have
- Retry runner compatible with Allure Cucumber adapter
- @id/@dep dependency resolution working
- Tag runner scripts functional
- Report merger functional

### Must NOT Have (Guardrails)
- Do NOT port old monolithic Extent plugin
- Do NOT duplicate WebDriver management in plugins
- Do NOT delete surefirePlugin-master/ before validation passes
- Do NOT break existing Allure + Extent dual reporting

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (JUnit 5, existing test-core tests)
- **Automated tests**: Tests-after (existing test infrastructure)
- **Framework**: JUnit 5 (Java), Maven

### QA Policy
Every task MUST include agent-executed QA scenarios.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Audit + Core Migration):
├── Task 1: Audit surefirePlugin-master vs main project [quick]
├── Task 2: Migrate retry runner to test-core [deep]
├── Task 3: Migrate @id/@dep dependency resolver [deep]
├── Task 4: Migrate tag runner scripts [quick]
└── Task 5: Migrate ExtentReportMerger to report-model [quick]

Wave 2 (Integration + Validation):
├── Task 6: Update POM dependencies and config [quick]
├── Task 7: Integration tests for retry + dependency [unspecified-high]
├── Task 8: Validate Allure adapter compatibility [quick]
└── Task 9: Update documentation and scripts [quick]

Wave 3 (Cleanup):
├── Task 10: Delete surefirePlugin-master/ directory [quick]
└── Task 11: Final validation — no references remain [quick]

Wave FINAL (After ALL tasks — Review):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real QA execution (unspecified-high)
└── Task F4: Scope fidelity check (deep)
```

### Critical Path
T1 (audit) → T2 (retry) + T3 (dependency) → T7 (integration test) → T10 (cleanup) → F1-F4

---

## TODOs

- [ ] 1. **Audit surefirePlugin-master vs Main Project**

  **What to do**:
  - Read `surefirePlugin-master/src/test/java/CucumberRetryRunnerTest.java` — document retry mechanism, file-based state, retry-count property
  - Read `surefirePlugin-master/src/test/java/` dependency graph files — document @id/@dep parsing, toposort algorithm
  - Read `surefirePlugin-master/run-by-tags.ps1` and `run-by-tag.sh` — document tag filtering and Maven invocation
  - Read `surefirePlugin-master/src/test/java/ExtentReportMerger.java` — document merge logic
  - Read main project `test-core/RetryTestRunner.java` — compare with surefirePlugin-master version
  - Read main project `test-core/DependencyResolver.java` — compare with surefirePlugin-master version
  - List ALL features in surefirePlugin-master and map to main project equivalents
  - Create migration matrix: which features exist, which need migration, which are redundant

  **Must NOT do**:
  - Do NOT modify any code in this task (pure audit)
  - Do NOT skip reading any file

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: File reading and comparison only

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1)
  - **Blocks**: Tasks 2, 3, 4, 5
  - **Blocked By**: None

  **References**:
  - `surefirePlugin-master/src/test/java/CucumberRetryRunnerTest.java` — Full retry implementation
  - `surefirePlugin-master/src/test/java/` — Dependency graph and toposort
  - `test-core/src/test/java/com/testreports/runner/RetryTestRunner.java` — Existing (incomplete) retry
  - `test-core/src/test/java/com/testreports/runner/DependencyResolver.java` — Existing dependency resolver
  - `surefirePlugin-master/run-by-tags.ps1` — Tag runner script

  **Acceptance Criteria**:
  - [ ] Audit document exists listing all surefirePlugin-master features
  - [ ] Migration matrix shows: migrate / already exists / skip for each feature
  - [ ] Specific line ranges identified for each feature to migrate

  **QA Scenarios**:
  ```
  Scenario: Audit completeness
    Tool: Bash (cat/grep)
    Steps:
      1. grep -r "retry" surefirePlugin-master/src/ > /tmp/retry-audit.txt
      2. grep -r "@id\|@dep" surefirePlugin-master/src/ > /tmp/dep-audit.txt
      3. ls surefirePlugin-master/*.ps1 surefirePlugin-master/*.sh > /tmp/script-audit.txt
    Expected Result: All files found, no errors
    Evidence: .sisyphus/evidence/task-1-audit.txt
  ```

  **Commit**: NO (audit only)

- [ ] 2. **Migrate Retry Runner to test-core**

  **What to do**:
  - Analyze `surefirePlugin-master/CucumberRetryRunnerTest.java` retry logic
  - Merge/improve existing `test-core/RetryTestRunner.java` with production retry features:
    - `--retry-count N` system property support
    - File-based state persistence in `target/retry-state/`
    - Per-example-row retry (Scenario Outline'ların sadece fail olan row'ları)
    - Attempt tracking (Attempt 1/3, 2/3, 3/3)
  - Ensure retry JSON state file format is compatible
  - Handle Allure adapter compatibility: each retry attempt must not pollute `allure-results` with duplicate entries
    - Solution: Clear or prefix attempt-specific Allure results
  - Add `retry-demo.feature` test scenarios if not present

  **Must NOT do**:
  - Do NOT break existing Allure + Extent dual reporting
  - Do NOT change `extent-integration/` plugin
  - Do NOT manage WebDriver inside retry runner

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: Complex logic integration with existing architecture

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T3, T4, T5)
  - **Blocks**: T7 (integration test)
  - **Blocked By**: T1 (audit)

  **References**:
  - `surefirePlugin-master/src/test/java/CucumberRetryRunnerTest.java` — Source retry logic
  - `test-core/src/test/java/com/testreports/runner/RetryTestRunner.java` — Target file
  - `test-core/src/test/resources/cucumber.properties` — Must keep both plugins
  - `test-core/src/test/resources/features/retry-demo.feature` — Test scenarios

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl test-core test -Dcucumber.filter.tags="@retry"` → PASS
  - [ ] Retry state files created under `test-core/target/retry-state/`
  - [ ] Allure results show final state only (not duplicate attempts)
  - [ ] Eventually-passing flaky scenario passes after retry

  **QA Scenarios**:
  ```
  Scenario: Retry runner happy path
    Tool: Bash
    Preconditions: Maven PATH set
    Steps:
      1. mvn -q -pl test-core test -Dcucumber.filter.tags="@retry" -Dretry.count=3
      2. ls test-core/target/retry-state/ > /tmp/retry-state.txt
    Expected Result: BUILD SUCCESS, retry state files exist
    Evidence: .sisyphus/evidence/task-2-retry-happy.txt

  Scenario: Retry with Allure compatibility
    Tool: Bash
    Steps:
      1. mvn -q -pl test-core test -Dcucumber.filter.tags="@retry"
      2. ls test-core/target/allure-results/ | wc -l
      3. grep "status" test-core/target/allure-results/*-result.json | head -5
    Expected Result: One result per scenario (no duplicates), status is final state
    Evidence: .sisyphus/evidence/task-2-allure-compat.txt
  ```

  **Commit**: YES
  - Message: `refactor(surefire): migrate retry runner to test-core`
  - Files: `test-core/src/test/java/com/testreports/runner/RetryTestRunner.java`, `test-core/src/test/resources/features/retry-demo.feature`

- [ ] 3. **Migrate @id/@dep Dependency Resolver**

  **What to do**:
  - Analyze surefirePlugin-master dependency graph implementation
  - Merge with existing `test-core/DependencyResolver.java`:
    - `@id:` tag parser (scenario identity)
    - `@dep:` tag parser (comma-separated dependency list)
    - Toposort (Kahn's algorithm) for execution ordering
    - SKIP behavior: dependency PASS değilse senaryo atlanır
    - Circular dependency detection
  - Handle tag filter interaction: eğer bağımlılık tag filter ile excluded olursa → SKIP
  - Add `dependency-demo.feature` with @id/@dep examples

  **Must NOT do**:
  - Do NOT duplicate existing `DependencyResolver` logic — enhance it
  - Do NOT break existing feature files without @id/@dep

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
  - **Reason**: Graph algorithm integration

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T2, T4, T5)
  - **Blocks**: T7 (integration test)
  - **Blocked By**: T1 (audit)

  **References**:
  - `surefirePlugin-master/src/test/java/` — Dependency graph source
  - `test-core/src/test/java/com/testreports/runner/DependencyResolver.java` — Target
  - `test-core/src/test/resources/features/dependency-demo.feature` — Test scenarios
  - AGENTS.md: `@id:`, `@dep:` tag conventions

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl test-core test -Dcucumber.filter.tags="@dependency"` → PASS
  - [ ] Dependency ordering respected (Setup before Login)
  - [ ] Missing dependency → SKIP with proper message
  - [ ] Circular dependency → error with clear message

  **QA Scenarios**:
  ```
  Scenario: Dependency resolution happy path
    Tool: Bash
    Steps:
      1. mvn -q -pl test-core test -Dcucumber.filter.tags="@dependency"
    Expected Result: BUILD SUCCESS, scenarios execute in dependency order
    Evidence: .sisyphus/evidence/task-3-dep-happy.txt

  Scenario: Missing dependency → SKIP
    Tool: Bash
    Steps:
      1. mvn -q -pl test-core test -Dcucumber.filter.tags="@missing-dep"
    Expected Result: Dependent scenario skipped, clear SKIP reason in output
    Evidence: .sisyphus/evidence/task-3-dep-skip.txt
  ```

  **Commit**: YES
  - Message: `refactor(surefire): migrate @id/@dep dependency resolver to test-core`
  - Files: `test-core/src/test/java/com/testreports/runner/DependencyResolver.java`, `test-core/src/test/resources/features/dependency-demo.feature`

- [ ] 4. **Migrate Tag Runner Scripts**

  **What to do**:
  - Copy and adapt `surefirePlugin-master/run-by-tags.ps1` to `scripts/run-by-tags.ps1`
  - Copy and adapt `surefirePlugin-master/run-by-tag.sh` to `scripts/run-by-tag.sh`
  - Update paths: `surefirePlugin-master/` references → `test-core/`
  - Ensure scripts use correct Maven module (`-pl test-core`)
  - Verify PowerShell and shell syntax correctness
  - Update script comments/documentation

  **Must NOT do**:
  - Do NOT leave old paths pointing to `surefirePlugin-master/`
  - Do NOT break existing `scripts/start-servers.sh` or `start-server.bat`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: File copy + path updates

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T2, T3, T5)
  - **Blocks**: T9 (documentation update)
  - **Blocked By**: T1 (audit)

  **References**:
  - `surefirePlugin-master/run-by-tags.ps1` — Source
  - `surefirePlugin-master/run-by-tag.sh` — Source
  - `scripts/` — Target directory
  - `NASIL_CALISTIRILIR.md` — May reference scripts

  **Acceptance Criteria**:
  - [ ] `scripts/run-by-tags.ps1` exists and references `test-core`
  - [ ] `scripts/run-by-tag.sh` exists and references `test-core`
  - [ ] Scripts have correct Maven syntax (`-pl test-core`)

  **QA Scenarios**:
  ```
  Scenario: PowerShell script syntax check
    Tool: Bash
    Steps:
      1. head -20 scripts/run-by-tags.ps1
    Expected Result: Contains "test-core", valid PowerShell syntax
    Evidence: .sisyphus/evidence/task-4-ps1-check.txt

  Scenario: Shell script syntax check
    Tool: Bash
    Steps:
      1. head -20 scripts/run-by-tag.sh
    Expected Result: Contains "test-core", valid shell syntax
    Evidence: .sisyphus/evidence/task-4-bat-check.txt
  ```

  **Commit**: YES
  - Message: `refactor(surefire): migrate tag runner scripts to scripts/`
  - Files: `scripts/run-by-tags.ps1`, `scripts/run-by-tag.sh`

- [ ] 5. **Migrate ExtentReportMerger to report-model**

  **What to do**:
  - Copy `surefirePlugin-master/ExtentReportMerger.java` to `report-model/src/main/java/`
  - Update package: `com.testreports.model.merger`
  - Adapt to `report-model/` POM dependencies (Jackson, JSoup if needed)
  - Ensure it can merge ExtentReports HTML files produced by `extent-integration/`
  - Add unit tests for merge logic

  **Must NOT do**:
  - Do NOT migrate the entire old Extent plugin — only the merger
  - Do NOT add WebDriver dependencies to report-model

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: File migration with dependency adaptation

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1, with T2, T3, T4)
  - **Blocks**: T7 (integration test)
  - **Blocked By**: T1 (audit)

  **References**:
  - `surefirePlugin-master/src/test/java/ExtentReportMerger.java` — Source
  - `report-model/pom.xml` — Target POM dependencies
  - `extent-integration/pom.xml` — ExtentReports version

  **Acceptance Criteria**:
  - [ ] `report-model/` compiles with new class
  - [ ] Unit test for merge logic passes
  - [ ] Can merge at least 2 Extent HTML reports

  **QA Scenarios**:
  ```
  Scenario: Merger compilation
    Tool: Bash
    Steps:
      1. mvn -q -pl report-model compile
    Expected Result: BUILD SUCCESS
    Evidence: .sisyphus/evidence/task-5-merger-compile.txt
  ```

  **Commit**: YES
  - Message: `refactor(surefire): migrate ExtentReportMerger to report-model`
  - Files: `report-model/src/main/java/com/testreports/model/merger/ExtentReportMerger.java`

- [ ] 6. **Update POM Dependencies and Config**

  **What to do**:
  - Review `test-core/pom.xml` — ensure all retry/dependency dependencies present
  - Check if `surefirePlugin-master` POM has unique dependencies not in parent
  - If so, add those dependencies to parent POM or relevant module POMs
  - Update `test-core/cucumber.properties` if needed (should still load both plugins)
  - Verify no dependency conflicts between migrated code and existing code

  **Must NOT do**:
  - Do NOT add unnecessary dependencies
  - Do NOT break existing module builds

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: POM management

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 2, after Wave 1)
  - **Blocks**: T7 (integration test)
  - **Blocked By**: T2, T3, T5 (core migrations)

  **References**:
  - `test-core/pom.xml`
  - `surefirePlugin-master/pom.xml`
  - `report-model/pom.xml`
  - Parent `pom.xml`

  **Acceptance Criteria**:
  - [ ] `mvn -q validate` → BUILD SUCCESS
  - [ ] All modules compile

  **QA Scenarios**:
  ```
  Scenario: Full validation
    Tool: Bash
    Steps:
      1. export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
      2. mvn -q validate
    Expected Result: BUILD SUCCESS
    Evidence: .sisyphus/evidence/task-6-validate.txt
  ```

  **Commit**: YES
  - Message: `build(surefire): update POM dependencies for migrated features`
  - Files: `test-core/pom.xml`, `report-model/pom.xml` (if changed)

- [ ] 7. **Integration Tests for Retry + Dependency**

  **What to do**:
  - Write JUnit 5 tests for migrated retry runner:
    - Test: Retry count = 3, flaky scenario passes on 3rd attempt
    - Test: Retry count = 0, no retry
    - Test: Per-example-row retry (Scenario Outline)
    - Test: Retry state file persistence
  - Write JUnit 5 tests for migrated dependency resolver:
    - Test: Linear dependency chain (A → B → C)
    - Test: Diamond dependency (A → B, A → C, B+D → E)
    - Test: Missing dependency → SKIP
    - Test: Circular dependency → error
    - Test: Tag filter excludes dependency → SKIP
  - Use existing test infrastructure (JUnit 5, feature files)

  **Must NOT do**:
  - Do NOT write tests that require manual verification
  - Do NOT test old surefirePlugin-master code (test new migrated code)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - **Reason**: Complex test scenarios for retry and graph algorithms

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 2, after T6)
  - **Blocks**: T8 (Allure validation)
  - **Blocked By**: T2, T3, T6

  **References**:
  - `test-core/src/test/java/com/testreports/runner/RetryTestRunner.java` — New retry
  - `test-core/src/test/java/com/testreports/runner/DependencyResolver.java` — New resolver
  - `test-core/src/test/resources/features/retry-demo.feature`
  - `test-core/src/test/resources/features/dependency-demo.feature`

  **Acceptance Criteria**:
  - [ ] `mvn -q -pl test-core test` → ALL tests PASS (existing + new)
  - [ ] Retry tests: 4 scenarios, all pass
  - [ ] Dependency tests: 5 scenarios, all pass

  **QA Scenarios**:
  ```
  Scenario: Full test suite
    Tool: Bash
    Steps:
      1. export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
      2. mvn -q -pl test-core test
    Expected Result: BUILD SUCCESS, all tests pass, no failures
    Evidence: .sisyphus/evidence/task-7-full-test.txt

  Scenario: Retry-specific tests
    Tool: Bash
    Steps:
      1. mvn -q -pl test-core test -Dcucumber.filter.tags="@retry"
    Expected Result: BUILD SUCCESS, retry scenarios pass
    Evidence: .sisyphus/evidence/task-7-retry-test.txt
  ```

  **Commit**: YES
  - Message: `test(surefire): integration tests for retry and dependency migration`
  - Files: `test-core/src/test/java/com/testreports/runner/*Test.java` (new test files)

- [ ] 8. **Validate Allure Adapter Compatibility**

  **What to do**:
  - Run tests with retry enabled and verify Allure results
  - Check `test-core/target/allure-results/` for duplicate entries
  - Verify each scenario has exactly ONE result JSON (final state)
  - If duplicates exist, fix retry runner to clean/prefix attempt results
  - Verify Extent report still generates correctly alongside Allure
  - Test with `@smoke` or `@login` tag (passing scenarios, not intentionally-failing ones)

  **Must NOT do**:
  - Do NOT ignore duplicate Allure results
  - Do NOT break Extent reporting

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: Validation task

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 2, after T7)
  - **Blocks**: T10 (cleanup)
  - **Blocked By**: T7

  **References**:
  - `test-core/target/allure-results/` — Allure output
  - `test-core/target/extent-reports/` — Extent output
  - `allure-integration/` — Screenshot/video hooks
  - `extent-integration/` — Extent plugin

  **Acceptance Criteria**:
  - [ ] Allure results: one JSON per scenario (no duplicates)
  - [ ] Extent report generated successfully
  - [ ] Screenshot/video attachments present in Allure

  **QA Scenarios**:
  ```
  Scenario: Allure result uniqueness
    Tool: Bash
    Steps:
      1. mvn -q -pl test-core test -Dcucumber.filter.tags="@smoke"
      2. ls test-core/target/allure-results/*-result.json | wc -l
      3. ls test-core/target/allure-results/*-result.json | sort | uniq -d | wc -l
    Expected Result: Result count = scenario count, 0 duplicates
    Evidence: .sisyphus/evidence/task-8-allure-check.txt

  Scenario: Extent report generation
    Tool: Bash
    Steps:
      1. ls test-core/target/extent-reports/ 2>/dev/null || echo "NO_EXTENT"
    Expected Result: Extent HTML report exists
    Evidence: .sisyphus/evidence/task-8-extent-check.txt
  ```

  **Commit**: YES (if fixes needed)
  - Message: `fix(surefire): ensure Allure adapter compatibility with retry`
  - Files: `test-core/src/test/java/com/testreports/runner/RetryTestRunner.java` (if fixed)

- [ ] 9. **Update Documentation and Scripts**

  **What to do**:
  - Update `README.md` — remove `surefirePlugin-master` references, add new script locations
  - Update `NASIL_CALISTIRILIR.md` — tag runner usage instructions
  - Update `ENTEGRASYON_REHBERI.md` — migration notes
  - Update `ACCESS_GUIDE.md` if it references surefirePlugin-master
  - Verify `scripts/start-servers.sh` and `start-server.bat` still work
  - Add migration note: `surefirePlugin-master features migrated to main project`

  **Must NOT do**:
  - Do NOT leave stale references to `surefirePlugin-master/`
  - Do NOT break existing documentation for other features

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []
  - **Reason**: Documentation updates

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 2, with T7, T8)
  - **Blocks**: None
  - **Blocked By**: T4 (scripts migrated)

  **References**:
  - `README.md`
  - `NASIL_CALISTIRILIR.md`
  - `ENTEGRASYON_REHBERI.md`
  - `ACCESS_GUIDE.md`
  - `scripts/`

  **Acceptance Criteria**:
  - [ ] No stale `surefirePlugin-master/` references in docs
  - [ ] Tag runner scripts documented
  - [ ] Migration note added

  **QA Scenarios**:
  ```
  Scenario: Documentation consistency
    Tool: Bash (grep)
    Steps:
      1. grep -r "surefirePlugin-master" *.md || echo "CLEAN"
      2. grep -r "run-by-tag" NASIL_CALISTIRILIR.md
    Expected Result: No stale references, tag runner documented
    Evidence: .sisyphus/evidence/task-9-docs-check.txt
  ```

  **Commit**: YES
  - Message: `docs(surefire): update documentation for migration`
  - Files: `README.md`, `NASIL_CALISTIRILIR.md`, `ENTEGRASYON_REHBERI.md`

- [ ] 10. **Delete surefirePlugin-master/ Directory**

  **What to do**:
  - Verify ALL features migrated (T2, T3, T4, T5 complete)
  - Verify ALL tests pass (T7 complete)
  - Verify Allure compatibility OK (T8 complete)
  - Verify documentation updated (T9 complete)
  - Run `git rm -rf surefirePlugin-master/`
  - Commit deletion
  - Add `.gitignore` entry if needed (not needed for deleted dir)

  **Must NOT do**:
  - Do NOT delete before T8 (Allure validation) passes
  - Do NOT delete if any references remain in other files
  - Do NOT delete without commit

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
  - **Reason**: Git operation + validation

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 3, after Wave 2)
  - **Blocks**: T11 (final validation)
  - **Blocked By**: T7, T8, T9

  **References**:
  - `surefirePlugin-master/` — Directory to delete
  - `git status` — Verify deletion

  **Acceptance Criteria**:
  - [ ] Directory no longer exists in filesystem
  - [ ] Git shows deletion in commit
  - [ ] `mvn -q validate` still passes (no broken references)

  **QA Scenarios**:
  ```
  Scenario: Directory deletion
    Tool: Bash
    Preconditions: git rm -rf surefirePlugin-master/ executed but NOT yet committed
    Steps:
      1. test -d surefirePlugin-master/ && echo "EXISTS" || echo "DELETED"
      2. git status --short | grep surefirePlugin-master
    Expected Result: "DELETED", git status shows "D surefirePlugin-master/..." entries
    Evidence: .sisyphus/evidence/task-10-deletion.txt

  Scenario: Commit verification
    Tool: Bash
    Preconditions: Deletion committed
    Steps:
      1. git show --name-status HEAD | grep surefirePlugin-master
    Expected Result: Shows "D" (deleted) entries for surefirePlugin-master files
    Evidence: .sisyphus/evidence/task-10-commit-verify.txt
  ```

  **Commit**: YES
  - Message: `chore(surefire): remove legacy surefirePlugin-master directory`
  - Files: `surefirePlugin-master/` (deleted)

- [ ] 11. **Final Validation — No References Remain**

  **What to do**:
  - Search entire codebase for `surefirePlugin-master` references
  - Check: Java files, POM files, scripts, docs, configs
  - If any found, update/remove them
  - Verify `mvn -q clean verify` passes
  - Verify all modules build
  - Verify FastAPI server unaffected
  - Create migration summary note in `.sisyphus/` or `docs/`

  **Must NOT do**:
  - Do NOT leave any stale references
  - Do NOT skip searching hidden/dot files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Reason**: Systematic search + validation

  **Parallelization**:
  - **Can Run In Parallel**: NO (Wave 3, after T10)
  - **Blocks**: F1-F4 (Final Verification)
  - **Blocked By**: T10

  **References**:
  - Entire codebase
  - `grep` / `find` tools

  **Acceptance Criteria**:
  - [ ] `grep -r "surefirePlugin-master" . --include="*.java" --include="*.xml" --include="*.md" --include="*.sh" --include="*.bat" --include="*.ps1"` → 0 results (except .git history and intentional migration note in `.sisyphus/migration-notes/surefire-master-migration.md`)
  - [ ] `mvn -q clean verify` → BUILD SUCCESS
  - [ ] All modules compile and test

  **QA Scenarios**:
  ```
  Scenario: Zero references check
    Tool: Bash
    Steps:
      1. grep -r "surefirePlugin-master" . --include="*.java" --include="*.xml" --include="*.md" --include="*.sh" --include="*.bat" --include="*.ps1" --include="*.properties" | grep -v ".git/" | grep -v "target/" | grep -v ".sisyphus/" || echo "CLEAN"
    Expected Result: "CLEAN" (`.sisyphus/` directory excluded as it contains planning and migration notes)
    Evidence: .sisyphus/evidence/task-11-zero-refs.txt

  Scenario: Full build verification
    Tool: Bash
    Steps:
      1. export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
      2. mvn -q clean verify
    Expected Result: BUILD SUCCESS, all tests pass
    Evidence: .sisyphus/evidence/task-11-full-build.txt
  ```

  **Commit**: YES (if any fixes needed)
  - Message: `chore(surefire): final cleanup — remove all stale references`
  - Files: Any files with remaining references

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`

  Read the plan end-to-end. For each "Must Have": verify implementation exists.
  - Retry runner in `test-core/`: read file, verify `--retry-count` property support
  - Dependency resolver in `test-core/`: verify `@id/@dep` parsing, toposort, SKIP behavior
  - Tag runner scripts in `scripts/`: verify files exist, correct paths
  - ExtentReportMerger in `report-model/`: verify class exists, compiles
  - `surefirePlugin-master/` deleted: verify directory gone, no references remain
  - For each "Must NOT Have": search codebase for forbidden patterns — old Extent plugin, WebDriver in plugins, stale references
  - Check evidence files exist in `.sisyphus/evidence/`

  Output: `Must Have [5/5] | Must NOT Have [4/4] | Tasks [11/11] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`

  Run `export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH" && mvn -q clean verify`.
  Review all changed files for:
  - Duplicate logic (retry/dependency parsing in multiple places)
  - Unused imports or dead code
  - Hardcoded paths (should use Maven properties)
  - AI slop patterns: excessive comments, generic names

  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`

  Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence.
  Test cross-feature integration:
  - Retry + Allure: verify no duplicate results
  - Dependency + tag filter: verify SKIP behavior
  - Tag runner scripts: verify they invoke correct Maven module
  - Extent report: verify it still generates alongside Allure

  Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`

  For each task: read "What to do", read actual diff (git log/diff).
  Verify 1:1 — everything in spec was built, nothing beyond spec.
  Check "Must NOT do" compliance:
  - Old monolithic Extent plugin NOT migrated
  - WebDriver management NOT moved into plugins
  - surefirePlugin-master/ NOT deleted before validation
  Detect cross-task contamination.

  Output: `Tasks [11/11 compliant] | Must NOT [4/4 compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- Wave 1 commits: `refactor(surefire): migrate {feature} to main project`
- Wave 2 commits: `test(surefire): integration tests for retry + dependency`
- Wave 3 commits: `chore(surefire): remove legacy surefirePlugin-master directory`

## Success Criteria

### Verification Commands
```bash
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn -q validate  # Expected: BUILD SUCCESS
mvn -q -pl test-core test  # Expected: Tests pass
mvn -q -pl test-core test -Dcucumber.filter.tags="@smoke"  # Expected: Tests pass (use a passing tag, not @sample-fail which intentionally fails)
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] No `surefirePlugin-master/` references in codebase
- [ ] Allure + Extent dual reporting still works
