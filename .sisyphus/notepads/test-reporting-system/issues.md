# Issues & Gotchas

## ffmpeg Not Available
- `ffmpeg` not installed in WSL environment
- Cannot `sudo apt install` due to missing password prompt
- **Workaround**: Task 2 (video) will use ProcessBuilder that fails gracefully; 
  video validation tests will be skipped until ffmpeg is installed

## Allure test-core Integration Gotchas (2026-04-26)
- `mvn -pl test-core ...` reads the full reactor model; `allure-integration` had an unmanaged existing `org.slf4j:slf4j-api` dependency, causing project-building failure until the parent dependencyManagement supplied a version.
- Playwright MCP expected Chrome at `/opt/google/chrome/chrome`, but the environment only has Chrome for Testing at `/tmp/chrome-linux64/chrome`; temporary `playwright-core` plus explicit `executablePath` was used for the browser render check.

## doors-service Maven Reactor Gotcha (2026-04-26)
- `mvn -q -pl doors-service test` does not build sibling module artifacts unless `-am` is used. Because the verification command is fixed without `-am`, a normal `report-model` dependency fails if `report-model` is not already installed locally.
- Java LSP diagnostics could not run in this environment because `jdtls` is configured but not installed; Maven compilation/test was used as verification.

## test-core Dependency Resolver Verification Gotchas (2026-04-27)
- Java LSP diagnostics still cannot run because `jdtls` is configured but not installed; Maven test compilation was the available verification path.
- Fixed verification command `mvn -pl test-core test -Dtest=DependencyResolverTest` can fail in a fresh local repository because `test-core` depends on sibling `extent-integration` and Maven does not build it without `-am`; installing `extent-integration` with `mvn -pl extent-integration -am install -DskipTests` resolves the local SNAPSHOT prerequisite.

## test-core Retry Runner Gotchas (2026-04-27)
- Java LSP diagnostics remain unavailable because `jdtls` is configured but not installed; Maven compilation/test was used for verification.
- `mvn -pl test-core ...` requires sibling `allure-integration` and `extent-integration` SNAPSHOT artifacts in the local Maven repository when not using `-am`; installed both with `mvn -pl allure-integration,extent-integration install -DskipTests` before running the fixed command.
- A class annotated with `@Suite` is also discovered by the JUnit Suite engine; the retry Maven profile limits execution to the `junit-jupiter` engine so the programmatic `@Test` method runs without a duplicate empty-suite failure.

## Markdown Guide Verification Gotcha (2026-04-27)
- LSP diagnostics are unavailable for `.md` files in this environment because no Markdown LSP server is configured; prose guide verification used targeted content scans instead.
