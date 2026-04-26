# Test Raporlama Sistemi — Learnings

## Toolchain
- Java 21 (OpenJDK)
- Maven 3.9.9 (`/home/ol_ta/tools/apache-maven-3.9.9`)
- Allure 2.33.0 (`/home/ol_ta/tools/allure-2.33.0`)
- Python 3.12.3
- ffmpeg: NOT INSTALLED — will need to install or work around
- Git: initialized

## Conventions
- Working dir: `/mnt/c/Users/ol_ta/desktop/java_reports`
- Java packages under `com.testreports.*`
- Maven groupId: `com.testreports`
- All paths relative to project root

## PATH Setup
```bash
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:/home/ol_ta/tools/allure-2.33.0/bin:$PATH"
```

## Multi-Module Maven Project Setup
- Parent POM: groupId=com.testreports, artifactId=test-reports, version=1.0.0-SNAPSHOT
- Java 21 source/target, UTF-8 encoding
- Modules listed in <modules> (fastapi-server is NOT included - it's Python)
- Dependencies managed via <dependencyManagement> in parent POM
- Each child module: parent reference + <dependencies> using managed versions
- Orchestrator module depends on other modules for stage coordination

## Dependencies Configured
- Cucumber 7.x (cucumber-java, cucumber-junit-platform)
- Selenium 4.x (selenium-java)
- JUnit 5 (junit-jupiter-api/engine, junit-platform-*)
- Allure 2.x (allure-cucumber7-jvm, allure-junit-platform)
- Jackson 2.x (jackson-databind, jackson-datatype-jsr310)
- Simple Java Mail 8.x
- Javalin 6.x
- Thymeleaf 3.x
- WireMock 3.x (for testing)
- GreenMail 2.x (for email testing)

## Allure Integration Verification (2026-04-26)
- Created `allure-integration/src/test/resources/allure.properties` with:
  - `allure.results.directory=target/allure-results`
  - `allure.report.directory=target/allure-report`
- Created `AllureVerificationTest.java` in `com.testreports.allure` package
  - Uses `io.qameta.allure.Allure` API for step and attachment generation
  - Tests passed, result JSONs generated in `target/allure-results/`
- `allure generate --clean target/allure-results -o target/allure-report` works correctly
- `target/allure-report/index.html` verified to exist
- ffmpeg still NOT installed — handle gracefully in video capture code
- Created `scripts/generate-sample-report.sh` for one-step report generation

## Jira Service Module (2026-04-26)
- Jira REST API v2 uses wiki-renderer format (NOT ADF) for Server/DC
- Wiki syntax: `h2.` for headings, `*bold*`, `- list`
- PAT Basic Auth: use `HttpClient.newBuilder().authenticator()` with custom Authenticator
- Auth header format: `Basic <base64-encoded-username:password>`
- Jira attachment endpoint `POST /rest/api/2/issue/{key}/attachments` returns JSON array
- WireMock stubbing: use `WireMock.urlPathMatching()` for dynamic paths
- Child modules need explicit test dependencies (junit-jupiter-api/engine) even when parent has dependencyManagement

## run-manifest.json Schema Implementation (2026-04-26)
- Created Java DTOs in `com.testreports.model` package:
  - `RunManifest.java` - top-level with runId, timestamp, totals, scenarios list
  - `ScenarioResult.java` - scenario with steps, attachments, tags, doorsAbsNumber
  - `StepResult.java` - step with name, status, errorMessage
  - `AttachmentInfo.java` - attachment with name, type (image/png, video/mp4, text/plain), path
- Jackson `@JsonProperty` annotations for all fields
- `Instant` timestamp uses `@JsonFormat(shape = STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss'Z'", timezone = "UTC")`
- `ManifestValidator.java` - validates JSON structure, field types, status values, attachment types
- `SampleManifestGenerator.java` - generates `manifests/sample-run-001.json` with 1 pass + 1 fail scenario
- `ManifestTest.java` - 9 tests for serialization round-trip, validation, null handling
- Python Pydantic models in `fastapi-server/models.py` with identical structure
- Python tests in `fastapi-server/tests/test_schema.py` - 8 tests, all pass
- `report-model/pom.xml` added junit-jupiter-api/engine with test scope
- Maven test passes: `mvn -q -pl report-model test` → BUILD SUCCESS
- Python tests pass: `pytest tests/test_schema.py` → 8 passed

## Cucumber Test Project Setup (2026-04-26)

### Dependencies Issue
- `cucumber-junit-platform` artifact does NOT exist in Maven Central
- Correct artifact name is `cucumber-junit-platform-engine`
- Updated parent POM dependencyManagement and test-core dependencies

### Allure + Cucumber Gherkin Version Conflict
- `allure-cucumber7-jvm:2.25.0` depends on `gherkin:26.2.0`
- `cucumber-java:7.18.0` depends on `gherkin:24.1.0`
- Conflict causes Maven resolve failure
- Fix: exclude gherkin from allure-cucumber7-jvm:
```xml
<exclusions>
    <exclusion>
        <groupId>io.cucumber</groupId>
        <artifactId>gherkin</artifactId>
    </exclusion>
</exclusions>
```

### Chrome/Chromium on WSL2
- Windows Chrome at `/mnt/c/Program Files/Google/Chrome/Application/chrome.exe` not directly accessible
- Linux Chrome for Testing (148.0.7778.56) downloaded to `/tmp/chrome-linux64/`
- Linux chromedriver downloaded to `/tmp/chromedriver-linux64/`
- Chrome crashpad handler permissions issue → used `--single-process --no-zygote` flags
- Chrome stable on WSL requires additional args to avoid subprocess spawn failures

### JUnit Platform Suite Configuration
- `@Suite` + `@IncludeEngines("cucumber")` + `@SelectClasspathResource("features")`
- Surefire must be configured to include the runner class:
```xml
<includes>
    <include>**/CucumberTestRunner.java</include>
</includes>
```
- Runner class name ending in `Test` or `Tests` required for Surefire detection
- Need `junit-platform-suite` dependency for `@Suite` annotations

### Cucumber Filter Tags
- `-Dcucumber.filter.tags="@sample-fail"` only runs scenarios with that tag
- `-Dcucumber.filter.tags="not @sample-fail"` excludes those scenarios
- Tag expressions work at runtime via system properties

## test-core Allure Cucumber7 Wiring (2026-04-26)
- For the JUnit Platform Cucumber suite, `@ConfigurationParameter(key = PLUGIN_PROPERTY_NAME, value = "io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,...")` reliably activates Allure output.
- `test-core/src/test/resources/allure.properties` with `allure.results.directory=target/allure-results` writes module-local results under `test-core/target/allure-results` when Maven runs from the repository root.
- `@sample-fail` intentionally exits Maven with a test error, so verification must use `|| true`; Allure still records `*-result.json` with scenario name, status, steps, timestamps, and feature tags.
- Allure report generation works with `/home/ol_ta/tools/allure-2.33.0/bin/allure generate --clean test-core/target/allure-results -o test-core/target/allure-report`.

## DOORS Service Batch Wrapper (2026-04-26)
- `doors-service` uses `com.testreports.doors.DoorsClient` to serialize a reduced handoff JSON: `runId` plus `results[{absNumber,status}]` from `RunManifest.scenarios[].doorsAbsNumber`.
- WSL/Linux cannot run real IBM DOORS, but executable fake `doors.exe` test doubles are allowed so ProcessBuilder behavior is testable.
- `mvn -q -pl doors-service test` passes after making doors-service self-contained for report-model sources and adding JUnit/Surefire config.

## Orchestrator Pipeline Runner (2026-04-26)
- Orchestrator package is `com.testreports.orchestrator` with a small `PipelineStage` interface for mockable stages.
- Critical stages are Allure report generation and manifest writing; web deploy, email, Jira, and DOORS are non-critical and should be logged then skipped/continued on failure.
- `ManifestWriteStage` delegates parsing to `AllureResultsParser` and initial manifest creation to `ManifestWriter`, then aligns the output filename/runId with the orchestrator `RunContext` when `--run-id` is provided.
- Child modules that need normal JUnit discovery must override parent Surefire includes with `**/*Test.java`; parent default only targets the Cucumber runner.

## 2026-04-26 F4 Scope Fidelity Check
- Found all 18 plan task headings and all requested key implementation marker files.
- Parent + module POM count is 9; user module-only command returns 8 because parent pom.xml is not under */pom.xml.
- Must-not-have scan: no spring-boot, DB dependency pattern, or hardcoded credential pattern found; jira-service contains an explanatory `not ADF` comment; README contains `mvn allure:serve`, which violates static-generation intent.
- Git history is not exactly one commit per wave: phase0/wave1/wave3 are split across multiple commits; JiraClient.java was introduced during phase0 rather than the later Jira client wave.
- `mvn -q validate` completed with exit code 0; LSP diagnostics unavailable because jdtls/biome are not installed.
