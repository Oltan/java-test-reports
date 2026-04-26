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
