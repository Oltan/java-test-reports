package com.testreports.runner;

import io.cucumber.core.cli.Main;
import io.cucumber.plugin.ConcurrentEventListener;
import io.cucumber.plugin.event.EventPublisher;
import io.cucumber.plugin.event.TestCase;
import io.cucumber.plugin.event.TestCaseFinished;
import io.cucumber.plugin.event.TestCaseStarted;
import io.cucumber.plugin.event.TestRunStarted;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.DisabledIfSystemProperty;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.Suite;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Programmatic Cucumber runner that retries only the failed scenario/example locations.
 *
 * <p>Enable with {@code -Dretry.count=N}. The normal {@link CucumberTestRunner} remains
 * responsible for default Cucumber suite execution when retry is not requested.</p>
 */
@Suite
@IncludeEngines("cucumber")
@DisabledIfSystemProperty(named = "retry.count", matches = "^0$")
public class RetryTestRunner {

    private static final String DEFAULT_FEATURES = "src/test/resources/features";
    private static final String DEFAULT_GLUE = "com.testreports.allure,com.testreports.steps";
    private static final Path RETRY_STATE_DIR = Paths.get(System.getProperty("retry.state.dir", "target/retry-state"));

    private static final Pattern SCENARIO_LINE = Pattern.compile("^\\s*Scenario(?: Outline| Template)?\\s*:\\s*(.+)\\s*$");
    private static final Pattern TAG_LINE = Pattern.compile("^\\s*@.+$");
    private static final Pattern ID_TAG = Pattern.compile("@id:([^\\s@]+)");
    private static final Pattern DEP_TAG = Pattern.compile("@dep:([^\\s@]+)");

    @Test
    void runWithRetry() throws IOException {
        int retryCount = Integer.getInteger("retry.count", 0);
        if (retryCount <= 0) {
            System.out.println("[RetryRunner] retry.count=0; retry runner is disabled.");
            return;
        }

        prepareRetryState();

        String featuresRoot = System.getProperty("cucumber.features", DEFAULT_FEATURES);
        List<String> gluePackages = parseGlue(System.getProperty("cucumber.glue", DEFAULT_GLUE));
        String tagExpression = System.getProperty("cucumber.filter.tags", "").trim();

        System.out.println("[RetryRunner] featuresRoot=" + featuresRoot);
        System.out.println("[RetryRunner] glue=" + gluePackages);
        System.out.println("[RetryRunner] tags=" + (tagExpression.isBlank() ? "<none>" : tagExpression));
        System.out.println("[RetryRunner] retry.count=" + retryCount);
        System.out.println("[RetryRunner] retryStateDir=" + RETRY_STATE_DIR.toAbsolutePath());

        List<Path> featureFiles = findFeatureFiles(featuresRoot);
        Assertions.assertFalse(featureFiles.isEmpty(), "No .feature files under: " + featuresRoot);

        List<String> scenarioNames = tagExpression.isBlank()
                ? featureFiles.stream().flatMap(path -> scanScenarios(path).stream()).distinct().toList()
                : discoverMatchingScenarios(gluePackages, tagExpression, featuresRoot);

        if (scenarioNames.isEmpty()) {
            System.out.println("[RetryRunner] No matching scenarios found.");
            return;
        }

        Map<String, ScenarioMeta> metadataByName = buildScenarioMetadataMap(featureFiles);
        List<ScenarioMeta> selected = scenarioNames.stream()
                .map(name -> metadataByName.getOrDefault(name, new ScenarioMeta(name, name, Set.of())))
                .collect(Collectors.toList());

        RetrySummary summary = runSelectedScenarios(topologicalSort(selected), gluePackages, tagExpression, featuresRoot, retryCount);
        printSummary(summary);

        Assertions.assertTrue(summary.failed().isEmpty(), "Failed scenarios: " + summary.failed());
    }

    private static RetrySummary runSelectedScenarios(List<ScenarioMeta> scenarios,
                                                     List<String> gluePackages,
                                                     String tagExpression,
                                                     String featuresRoot,
                                                     int retryCount) throws IOException {
        Map<String, Status> resultsById = new LinkedHashMap<>();
        List<String> passed = new ArrayList<>();
        List<String> failed = new ArrayList<>();
        List<String> skipped = new ArrayList<>();

        for (ScenarioMeta scenario : scenarios) {
            if (!dependenciesPassed(scenario, resultsById, skipped)) {
                continue;
            }

            boolean scenarioPassed = false;
            List<String> failedLocationsForNextAttempt = List.of();

            for (int attempt = 0; attempt <= retryCount; attempt++) {
                FailureCapturePlugin.reset();
                recordAttempt(scenario.name(), attempt, retryCount, failedLocationsForNextAttempt);

                int exitCode = runScenario(gluePackages, tagExpression, featuresRoot, scenario.name(), failedLocationsForNextAttempt);
                List<String> failedLocations = FailureCapturePlugin.getFailedLocations();

                System.out.printf("[RetryRunner] Exit code for '%s' (Attempt %d/%d) = %d%n",
                        scenario.name(), attempt, retryCount, exitCode);
                if (!failedLocations.isEmpty()) {
                    System.out.println("[RetryRunner] Failed locations:");
                    failedLocations.forEach(location -> System.out.println("  - " + location));
                }

                if (exitCode == 0) {
                    scenarioPassed = true;
                    passed.add(scenario.name());
                    System.out.printf("[RetryRunner] PASSED '%s' on Attempt %d/%d%n", scenario.name(), attempt, retryCount);
                    break;
                }

                failedLocationsForNextAttempt = failedLocations;
                if (attempt < retryCount) {
                    System.out.printf("[RetryRunner] FAILED '%s' -> retrying Attempt %d/%d%n",
                            scenario.name(), attempt + 1, retryCount);
                }
            }

            if (scenarioPassed) {
                resultsById.put(scenario.id(), Status.PASS);
            } else {
                resultsById.put(scenario.id(), Status.FAIL);
                failed.add(scenario.name());
                System.out.printf("[RetryRunner] FINAL FAIL '%s'%n", scenario.name());
            }
        }

        return new RetrySummary(passed, failed, skipped);
    }

    private static boolean dependenciesPassed(ScenarioMeta scenario, Map<String, Status> resultsById, List<String> skipped) {
        for (String dependency : scenario.dependencies()) {
            Status dependencyStatus = resultsById.get(dependency);
            if (dependencyStatus != Status.PASS) {
                System.out.printf("[RetryRunner] SKIP '%s' (%s): dependency '%s' status=%s%n",
                        scenario.name(), scenario.id(), dependency, dependencyStatus == null ? "NOT_RUN" : dependencyStatus);
                resultsById.put(scenario.id(), Status.SKIP);
                skipped.add(scenario.name());
                return false;
            }
        }
        return true;
    }

    private static int runScenario(List<String> gluePackages,
                                   String tagExpression,
                                   String featuresRoot,
                                   String scenarioName,
                                   List<String> locationsToRun) {
        List<String> args = baseArgs(gluePackages, tagExpression);
        args.add("--plugin");
        args.add(FailureCapturePlugin.class.getName());

        if (locationsToRun != null && !locationsToRun.isEmpty()) {
            args.addAll(locationsToRun);
        } else {
            args.add("--name");
            args.add("^" + Pattern.quote(scenarioName) + "$");
            args.add(featuresRoot);
        }

        return Main.run(args.toArray(String[]::new), Thread.currentThread().getContextClassLoader());
    }

    private static List<String> discoverMatchingScenarios(List<String> gluePackages, String tagExpression, String featuresRoot) {
        DiscoveryPlugin.reset();
        List<String> args = baseArgs(gluePackages, tagExpression);
        args.add("--plugin");
        args.add(DiscoveryPlugin.class.getName());
        args.add("--dry-run");
        args.add(featuresRoot);

        System.out.println("[RetryRunner] Discovery pass starting (tags=" + tagExpression + ")");
        int exitCode = Main.run(args.toArray(String[]::new), Thread.currentThread().getContextClassLoader());
        System.out.println("[RetryRunner] Discovery pass finished with exit code " + exitCode);
        return DiscoveryPlugin.getDiscoveredScenarioNames();
    }

    private static List<String> baseArgs(List<String> gluePackages, String tagExpression) {
        List<String> args = new ArrayList<>();
        gluePackages.forEach(glue -> {
            args.add("--glue");
            args.add(glue);
        });
        if (!tagExpression.isBlank()) {
            args.add("--tags");
            args.add(tagExpression);
        }
        return args;
    }

    private static List<Path> findFeatureFiles(String featuresRoot) throws IOException {
        try (Stream<Path> stream = Files.walk(Paths.get(featuresRoot))) {
            return stream.filter(path -> path.toString().endsWith(".feature")).sorted().toList();
        }
    }

    private static List<String> scanScenarios(Path featureFile) {
        try {
            return Files.readAllLines(featureFile, StandardCharsets.UTF_8).stream()
                    .map(SCENARIO_LINE::matcher)
                    .filter(java.util.regex.Matcher::matches)
                    .map(matcher -> matcher.group(1).trim())
                    .toList();
        } catch (IOException e) {
            return List.of();
        }
    }

    private static Map<String, ScenarioMeta> buildScenarioMetadataMap(List<Path> featureFiles) {
        Map<String, ScenarioMeta> metadataByName = new LinkedHashMap<>();
        featureFiles.forEach(featureFile -> parseFeatureMetadata(featureFile, metadataByName));
        return metadataByName;
    }

    private static void parseFeatureMetadata(Path featureFile, Map<String, ScenarioMeta> metadataByName) {
        List<String> lines;
        try {
            lines = Files.readAllLines(featureFile, StandardCharsets.UTF_8);
        } catch (IOException e) {
            return;
        }

        Set<String> pendingDependencies = new LinkedHashSet<>();
        String pendingId = null;

        for (String rawLine : lines) {
            String line = rawLine.trim();
            if (TAG_LINE.matcher(line).matches()) {
                java.util.regex.Matcher idMatcher = ID_TAG.matcher(line);
                if (idMatcher.find()) {
                    pendingId = idMatcher.group(1).trim();
                }

                java.util.regex.Matcher dependencyMatcher = DEP_TAG.matcher(line);
                while (dependencyMatcher.find()) {
                    Arrays.stream(dependencyMatcher.group(1).split(","))
                            .map(String::trim)
                            .filter(value -> !value.isEmpty())
                            .forEach(pendingDependencies::add);
                }
                continue;
            }

            java.util.regex.Matcher scenarioMatcher = SCENARIO_LINE.matcher(line);
            if (scenarioMatcher.matches()) {
                String name = scenarioMatcher.group(1).trim();
                metadataByName.put(name, new ScenarioMeta(
                        name,
                        pendingId == null ? name : pendingId,
                        Set.copyOf(pendingDependencies)));
                pendingId = null;
                pendingDependencies.clear();
            }
        }
    }

    private static List<ScenarioMeta> topologicalSort(List<ScenarioMeta> scenarios) {
        Map<String, ScenarioMeta> byId = scenarios.stream()
                .collect(Collectors.toMap(ScenarioMeta::id, scenario -> scenario, (first, ignored) -> first, LinkedHashMap::new));
        List<ScenarioMeta> ordered = new ArrayList<>();
        Set<String> visited = new HashSet<>();
        Set<String> visiting = new HashSet<>();

        for (ScenarioMeta scenario : scenarios) {
            visit(scenario, byId, visited, visiting, ordered);
        }

        return ordered;
    }

    private static void visit(ScenarioMeta scenario,
                              Map<String, ScenarioMeta> byId,
                              Set<String> visited,
                              Set<String> visiting,
                              List<ScenarioMeta> ordered) {
        if (visited.contains(scenario.id())) {
            return;
        }
        if (!visiting.add(scenario.id())) {
            System.err.printf("[RetryRunner] Dependency cycle detected at '%s'%n", scenario.id());
            return;
        }
        for (String dependency : scenario.dependencies()) {
            ScenarioMeta dependencyScenario = byId.get(dependency);
            if (dependencyScenario != null) {
                visit(dependencyScenario, byId, visited, visiting, ordered);
            }
        }
        visiting.remove(scenario.id());
        visited.add(scenario.id());
        ordered.add(scenario);
    }

    private static List<String> parseGlue(String glueProperty) {
        return Arrays.stream(glueProperty.split("[,;]"))
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .toList();
    }

    private static void prepareRetryState() throws IOException {
        if (Files.exists(RETRY_STATE_DIR)) {
            try (Stream<Path> paths = Files.walk(RETRY_STATE_DIR)) {
                paths.sorted((left, right) -> right.compareTo(left))
                        .filter(path -> !path.equals(RETRY_STATE_DIR))
                        .forEach(RetryTestRunner::deleteQuietly);
            }
        }
        Files.createDirectories(RETRY_STATE_DIR);
    }

    private static void recordAttempt(String scenarioName, int attempt, int retryCount, List<String> retryLocations) throws IOException {
        Files.createDirectories(RETRY_STATE_DIR);
        Path attemptFile = RETRY_STATE_DIR.resolve(toSafeSlug(scenarioName) + ".runner-attempt.txt");
        List<String> lines = new ArrayList<>();
        lines.add("scenario=" + scenarioName);
        lines.add("attempt=" + attempt);
        lines.add("retry.count=" + retryCount);
        if (retryLocations != null && !retryLocations.isEmpty()) {
            lines.add("locations=" + String.join(",", retryLocations));
        }
        Files.write(attemptFile, lines, StandardCharsets.UTF_8);
        System.out.printf("[RetryRunner] Attempt %d/%d for '%s'%n", attempt, retryCount, scenarioName);
    }

    private static void deleteQuietly(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // Best effort cleanup; a stale file should not prevent the retry runner from starting.
        }
    }

    private static void printSummary(RetrySummary summary) {
        System.out.println("===================================================");
        System.out.println("[RetryRunner] Final Summary:");
        System.out.println("  PASSED: " + summary.passed().size());
        summary.passed().forEach(name -> System.out.println("    - " + name));
        System.out.println("  FAILED: " + summary.failed().size());
        summary.failed().forEach(name -> System.out.println("    - " + name));
        System.out.println("  SKIPPED: " + summary.skipped().size());
        summary.skipped().forEach(name -> System.out.println("    - " + name));
        System.out.println("===================================================");
    }

    private static String toSafeSlug(String value) {
        if (value == null || value.isBlank()) {
            return "scenario";
        }
        String slug = value.replaceAll("[^A-Za-z0-9]+", "-").replaceAll("^-+", "").replaceAll("-+$", "");
        return slug.isEmpty() ? "scenario" : slug;
    }

    public static final class FailureCapturePlugin implements ConcurrentEventListener {
        private static final Set<String> FAILED_LOCATIONS = new LinkedHashSet<>();
        private static final Object LOCK = new Object();

        @Override
        public void setEventPublisher(EventPublisher publisher) {
            publisher.registerHandlerFor(TestRunStarted.class, ignored -> reset());
            publisher.registerHandlerFor(TestCaseFinished.class, this::captureFailure);
        }

        private void captureFailure(TestCaseFinished event) {
            if (event.getResult().getStatus() != io.cucumber.plugin.event.Status.FAILED) {
                return;
            }
            TestCase testCase = event.getTestCase();
            String location = toLocation(testCase.getUri(), testCase.getLocation().getLine());
            synchronized (LOCK) {
                FAILED_LOCATIONS.add(location);
            }
        }

        public static void reset() {
            synchronized (LOCK) {
                FAILED_LOCATIONS.clear();
            }
        }

        public static List<String> getFailedLocations() {
            synchronized (LOCK) {
                return new ArrayList<>(FAILED_LOCATIONS);
            }
        }

        private static String toLocation(URI uri, int line) {
            try {
                return Paths.get(uri).toString() + ":" + line;
            } catch (Exception e) {
                return uri + ":" + line;
            }
        }
    }

    public static final class DiscoveryPlugin implements ConcurrentEventListener {
        private static final Set<String> DISCOVERED_SCENARIOS = new LinkedHashSet<>();

        @Override
        public void setEventPublisher(EventPublisher publisher) {
            publisher.registerHandlerFor(TestRunStarted.class, ignored -> reset());
            publisher.registerHandlerFor(TestCaseStarted.class, event -> {
                synchronized (DISCOVERED_SCENARIOS) {
                    DISCOVERED_SCENARIOS.add(event.getTestCase().getName());
                }
            });
        }

        public static void reset() {
            synchronized (DISCOVERED_SCENARIOS) {
                DISCOVERED_SCENARIOS.clear();
            }
        }

        public static List<String> getDiscoveredScenarioNames() {
            synchronized (DISCOVERED_SCENARIOS) {
                return new ArrayList<>(DISCOVERED_SCENARIOS);
            }
        }
    }

    private enum Status {PASS, FAIL, SKIP}

    private record ScenarioMeta(String name, String id, Set<String> dependencies) {}

    private record RetrySummary(List<String> passed, List<String> failed, List<String> skipped) {}
}
