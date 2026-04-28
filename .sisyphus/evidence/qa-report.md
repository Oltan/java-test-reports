# QA Report - 2026-04-27

## Maven Validate
**Result:** BUILD SUCCESS
- All 9 modules validated successfully
- Total time: 0.202s

## Java Module Tests

| Module | Result | Details |
|--------|--------|---------|
| allure-integration | PASS | VideoHook disabled (ffmpeg not found) |
| report-model | FAIL | 1 failure: `ManifestTest.testManifestValidatorValidatesSampleFile` - requires SampleManifestGenerator to run first |
| email-service | PASS | SLF4J NOP logger (no providers) |
| jira-service | FAIL | 16 tests, 1 failure (RetryScenario wiremock), 2 errors |
| doors-service | PASS | Windows skipped, dry-run mode on Linux |
| orchestrator | PASS | Pipeline stage execution works |
| test-core (DependencyResolverTest only) | PASS | 5 tests, 0 failures |

## FastAPI Tests
**Result:** 26 passed, 2 failed

### Failures:
1. `test_unauthorized_401` - Expects 401, gets 200 (auth not enforced)
2. `test_runs_without_token` - Expects 401, gets 200 (auth not enforced)

### Warnings:
- JWT key length warning (11 bytes < 32 bytes recommended)

## Server Endpoint Test
**Result:** 200 OK (server running on port 8000)

## Summary
| Check | Status |
|-------|--------|
| mvn validate | ✅ SUCCESS |
| Java module tests | ⚠️ 2 modules with failures |
| FastAPI pytest | ⚠️ 2 auth-related test failures |
| Server endpoint | ✅ 200 OK |
| DependencyResolverTest | ✅ PASS |

## Known Issues
1. **report-model**: ManifestTest requires `SampleManifestGenerator` to run first
2. **jira-service**: WireMock retry scenario mismatch
3. **FastAPI auth**: Unauthorized endpoints return 200 instead of 401