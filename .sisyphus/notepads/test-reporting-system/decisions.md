# Decisions

## test-core Allure Cucumber7 Wiring (2026-04-26)
- Kept the existing Cucumber JSON and `pretty` plugins and prepended `io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm` so existing reports continue to be produced.
- Added runner-level JUnit Platform `@ConfigurationParameter` because it reliably activates Cucumber plugins for the suite runner while keeping `cucumber.properties` documented/configured.
- Managed the existing `slf4j-api` dependency version in the parent POM rather than adding a new module dependency, preserving the declared dependency set while allowing `mvn -pl test-core ...` to build the reactor model.

## doors-service Verification Compatibility (2026-04-26)
- Added `build-helper-maven-plugin` in `doors-service` to include `../report-model/src/main/java` as sources instead of requiring a sibling module artifact. This preserves the required `mvn -q -pl doors-service test` command without relying on prior local installs.
- Kept the public `DoorsClient(Path doorsExePath)` constructor at the required 120-second timeout and added package-private timeout injection only for fast timeout tests.

## orchestrator Pipeline Boundaries (2026-04-26)
- Default CLI pipeline runs the four core stages in the requested order: AllureGenerate → ManifestWrite → WebDeploy → EmailSend. JiraCreate and DoorsUpdate are implemented as optional non-critical stages but are not added to the default CLI path.
- External integrations are injected behind small functional interfaces in stages so unit tests use fake stages/services and make no real process, SMTP, Jira, or DOORS calls.

## test-core Dependency Resolver Scope (2026-04-27)
- Kept dependency parsing in test sources and implemented it with standard Java collections, regex, and file I/O only, matching the unit-test-only requirement and avoiding new Cucumber/runtime dependencies.
- Duplicate `@id:` values throw immediately during parsing because IDs are intended to be unique scenario identifiers; missing dependency IDs remain non-fatal and are only warned during topological sorting.

## test-core Retry Runner Activation (2026-04-27)
- Kept `CucumberTestRunner` as the default Surefire include so existing test-core Cucumber behavior remains unchanged when `retry.count` is absent.
- Added a `retry-runner` Maven profile activated by `-Dretry.count` that overrides Surefire includes to `RetryTestRunner` and limits JUnit Platform execution to `junit-jupiter`, avoiding duplicate execution by the normal suite runner.
- Added explicit `cucumber-core` test-core dependency because the retry runner invokes `io.cucumber.core.cli.Main` directly rather than through the JUnit Platform Cucumber engine.
