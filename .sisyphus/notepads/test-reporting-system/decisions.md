# Decisions

## test-core Allure Cucumber7 Wiring (2026-04-26)
- Kept the existing Cucumber JSON and `pretty` plugins and prepended `io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm` so existing reports continue to be produced.
- Added runner-level JUnit Platform `@ConfigurationParameter` because it reliably activates Cucumber plugins for the suite runner while keeping `cucumber.properties` documented/configured.
- Managed the existing `slf4j-api` dependency version in the parent POM rather than adding a new module dependency, preserving the declared dependency set while allowing `mvn -pl test-core ...` to build the reactor model.

## doors-service Verification Compatibility (2026-04-26)
- Added `build-helper-maven-plugin` in `doors-service` to include `../report-model/src/main/java` as sources instead of requiring a sibling module artifact. This preserves the required `mvn -q -pl doors-service test` command without relying on prior local installs.
- Kept the public `DoorsClient(Path doorsExePath)` constructor at the required 120-second timeout and added package-private timeout injection only for fast timeout tests.
