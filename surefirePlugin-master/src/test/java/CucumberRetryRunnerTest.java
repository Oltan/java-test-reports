import io.cucumber.core.cli.Main;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Runs Cucumber scenarios one-by-one and retries failed ones up to -Dretry.count times.
 * Adds scenario dependency logic using @id: and @dep: tags.
 * <p>
 * Defaults:
 * - Features root:   src/test/resources/features
 * - Glue packages:   stepDefinitions, hooks   (can be overridden via -Dcucumber.glue)
 * - Tag filter:      (from -Dcucumber.filter.tags)
 * <p>
 * Discovery pass:
 * - If a tag filter is provided, we first run a --dry-run with hooks.DiscoveryPlugin
 * to collect only matching scenarios. We then retry only those scenarios.
 * <p>
 * Dependency conventions in .feature files:
 * - Scenario identity:   @id:YourUniqueId     (falls back to scenario name if absent)
 * - Dependencies:        @dep:IdA,IdB         (comma-separated)
 * <p>
 * Behavior:
 * - After building the scenario list (either from discovery or scanning), we parse feature files
 * to extract (id, deps) per scenario, order by dependencies (toposort), then execute with retries.
 * - If any dependency did not PASS (or was not selected in this run), the scenario is skipped.
 * <p>
 * Add-on:
 * - On retry, only failed example rows (uri:line) of a Scenario Outline are re-executed
 * instead of re-running the whole outline.
 */
public class CucumberRetryRunnerTest {

    private static final String DEFAULT_FEATURES = "src/test/resources/features";
    private static final String[] DEFAULT_GLUE = {"stepDefinitions", "hooks"};

    private static final Pattern SCENARIO_LINE = Pattern.compile("^\\s*Scenario(?: Outline| Template)?\\s*:\\s*(.+)\\s*$");

    // Dependency parsing patterns
    private static final Pattern TAG_LINE = Pattern.compile("^\\s*@.+$");
    private static final Pattern ID_TAG = Pattern.compile("@id:([^\\s@]+)");
    private static final Pattern DEP_TAG = Pattern.compile("@dep:([^\\s@]+)");

    private static List<String> discoverMatchingScenarios(List<String> gluePkgs, String tagExpr, String featuresRoot) {
        List<String> args = getBaseArgs(gluePkgs, tagExpr, featuresRoot);
        // Add discovery-only plugin and dry-run
        args.add("--plugin");
        args.add("hooks.DiscoveryPlugin");
        args.add("--dry-run");
        System.out.println("[RetryRunner] Discovery pass starting (tags=" + tagExpr + ") …");
        int code = Main.run(args.toArray(new String[0]), Thread.currentThread().getContextClassLoader());
        System.out.println("[RetryRunner] Discovery pass finished with exit code " + code);
        return hooks.DiscoveryPlugin.getDiscoveredScenarioNames();
    }

    private static int runScenario(List<String> gluePkgs,
                                   String tagExpr,
                                   String featuresRoot,
                                   String scenarioName,
                                   List<String> locationsToRun) {
        List<String> args = getBaseArgs(gluePkgs, tagExpr, featuresRoot);

        // Always capture failures so we can select only failed rows for retry
        args.add("--plugin");
        args.add("hooks.FailureCapturePlugin");

        // Your reporting/other plugins may be added via glue/hooks. If you prefer explicit:
        args.add("--plugin");
        args.add("hooks.ExtentCucumberPlugin");

        if (locationsToRun != null && !locationsToRun.isEmpty()) {
            // Run exact feature locations (uri:line or path:line)
            args.addAll(locationsToRun);
        } else {
            // First attempt: run by scenario name filter across the features root
            args.add("--name");
            args.add(scenarioName);
            args.add(featuresRoot);
        }

        return Main.run(args.toArray(new String[0]), Thread.currentThread().getContextClassLoader());
    }

    private static List<String> getBaseArgs(List<String> gluePkgs, String tagExpr, String featuresRoot) {
        List<String> args = new ArrayList<>();
        // Glue
        for (String g : gluePkgs) {
            args.add("--glue");
            args.add(g);
        }
        // Tags
        if (tagExpr != null && !tagExpr.isBlank()) {
            args.add("--tags");
            args.add(tagExpr);
        }
        // Default features root as a search base (used when running by --name)
        // When running by locations, we pass absolute/relative paths instead.
        return args;
    }

    // --- Discovery -------------------------------------------------

    private static List<Path> findFeatureFiles(String root) throws IOException {
        try (Stream<Path> s = Files.walk(Paths.get(root))) {
            return s.filter(p -> p.toString().endsWith(".feature")).sorted().toList();
        }
    }

    // --- Execution helper (NEW: supports rerun by locations) -------

    private static List<String> scanScenarios(Path featureFile) {
        List<String> names = new ArrayList<>();
        try {
            List<String> lines = Files.readAllLines(featureFile, StandardCharsets.UTF_8);
            for (String line : lines) {
                var m = SCENARIO_LINE.matcher(line);
                if (m.matches()) {
                    names.add(m.group(1).trim());
                }
            }
        } catch (IOException ignored) {
        }
        return names;
    }

    // --- Args/base config ------------------------------------------

    private static Map<String, ScenarioMeta> buildScenarioMetadataMap(List<Path> featureFiles) {
        Map<String, ScenarioMeta> map = new LinkedHashMap<>();
        for (Path f : featureFiles) {
            parseFeatureForMeta(f, map);
        }
        return map;
    }

    // --- Feature/scenario parsing & topo sort (unchanged) ----------

    private static void parseFeatureForMeta(Path featureFile, Map<String, ScenarioMeta> out) {
        List<String> lines;
        try {
            lines = Files.readAllLines(featureFile, StandardCharsets.UTF_8);
        } catch (IOException e) {
            return;
        }
        Set<String> pendingDeps = new LinkedHashSet<>();
        String pendingId = null;

        for (String raw : lines) {
            String line = raw.trim();
            if (TAG_LINE.matcher(line).matches()) {
                var idm = ID_TAG.matcher(line);
                if (idm.find()) pendingId = idm.group(1).trim();

                var depm = DEP_TAG.matcher(line);
                while (depm.find()) {
                    String[] parts = depm.group(1).split(",");
                    for (String p : parts) {
                        String d = p.trim();
                        if (!d.isEmpty()) pendingDeps.add(d);
                    }
                }
            } else {
                var sm = SCENARIO_LINE.matcher(line);
                if (sm.matches()) {
                    String scenarioName = sm.group(1).trim();
                    String id = (pendingId != null ? pendingId : scenarioName);
                    out.put(scenarioName, new ScenarioMeta(scenarioName, id, Set.copyOf(pendingDeps), featureFile));
                    pendingDeps.clear();
                    pendingId = null;
                }
            }
        }
    }

    private static List<ScenarioMeta> topoSortByDependencies(List<ScenarioMeta> metas) {
        Map<String, ScenarioMeta> byId = metas.stream().collect(Collectors.toMap(m -> m.id, m -> m, (a, b) -> a, LinkedHashMap::new));
        List<ScenarioMeta> ordered = new ArrayList<>();
        Set<String> visited = new HashSet<>();
        Set<String> visiting = new HashSet<>();

        for (ScenarioMeta m : metas) {
            dfs(m, byId, visited, visiting, ordered);
        }
        return ordered;
    }

    private static void dfs(ScenarioMeta m,
                            Map<String, ScenarioMeta> byId,
                            Set<String> visited,
                            Set<String> visiting,
                            List<ScenarioMeta> out) {
        if (visited.contains(m.id)) return;
        if (visiting.contains(m.id)) {
            System.err.println("[RetryRunner] Detected cycle at: " + m.id + " deps=" + m.deps);
            return;
        }
        visiting.add(m.id);
        for (String dep : m.deps) {
            ScenarioMeta depMeta = byId.get(dep);
            if (depMeta != null) {
                dfs(depMeta, byId, visited, visiting, out);
            }
        }
        visiting.remove(m.id);
        visited.add(m.id);
        out.add(m);
    }

    @Test
    void runWithImmediateRetries() throws IOException {
        final String featuresRoot = System.getProperty("cucumber.features", DEFAULT_FEATURES);

        // Multiple glue packages (comma/semicolon separated)
        final String glueProp = System.getProperty("cucumber.glue", String.join(",", DEFAULT_GLUE));
        final List<String> gluePkgs = Arrays.stream(glueProp.split("[,;]")).map(String::trim).filter(s -> !s.isEmpty()).toList();

        final String tagExpr = System.getProperty("cucumber.filter.tags", "").trim();
        final int maxRetries = Integer.getInteger("retry.count", 0);

        System.out.println("[RetryRunner] featuresRoot=" + featuresRoot);
        System.out.println("[RetryRunner] glue=" + gluePkgs);
        System.out.println("[RetryRunner] tags=" + (tagExpr.isEmpty() ? "<none>" : tagExpr));
        System.out.println("[RetryRunner] retry.count=" + maxRetries);

        // 1) Find all feature files
        List<Path> featureFiles = findFeatureFiles(featuresRoot);
        if (featureFiles.isEmpty()) {
            System.err.println("No .feature files under: " + featuresRoot);
            hooks.ExtentCucumberPlugin.shutdownDriverNow();
            Assertions.fail("No .feature files under: " + featuresRoot);
            return;
        }

        // 2) Build scenario list
        List<String> scenarioNames;
        if (!tagExpr.isEmpty()) {
            // Discovery pass using Cucumber --dry-run and DiscoveryPlugin
            scenarioNames = discoverMatchingScenarios(gluePkgs, tagExpr, featuresRoot);
            if (scenarioNames.isEmpty()) {
                System.out.println("[RetryRunner] Discovery found 0 matching scenarios for tags: " + tagExpr);
                // Clean shutdown and consider this run successful (nothing to run)
                hooks.ExtentCucumberPlugin.shutdownDriverNow();
                return;
            }
            System.out.println("[RetryRunner] Discovery found " + scenarioNames.size() + " matching scenarios.");
        } else {
            // No tag filter: scan all scenarios by file parsing
            scenarioNames = featureFiles.stream().flatMap(p -> scanScenarios(p).stream()).distinct().collect(Collectors.toList());

            if (scenarioNames.isEmpty()) {
                System.err.println("No scenarios found under: " + featuresRoot);
                hooks.ExtentCucumberPlugin.shutdownDriverNow();
                Assertions.fail("No scenarios found under: " + featuresRoot);
                return;
            }
        }

        // 2b) Build metadata from feature files (id + deps) and order by dependencies
        Map<String, ScenarioMeta> metaByName = buildScenarioMetadataMap(featureFiles);
        List<ScenarioMeta> selectedMetas = scenarioNames.stream()
                .map(n -> metaByName.getOrDefault(n, new ScenarioMeta(n, n, Set.of(), null)))
                .collect(Collectors.toList());

        List<ScenarioMeta> ordered = topoSortByDependencies(selectedMetas);

        // 3) Execute scenarios with dependency enforcement and retries
        Map<String, Status> results = new LinkedHashMap<>();
        List<String> stillFailing = new ArrayList<>();
        List<String> passedScenarios = new ArrayList<>();
        List<String> skippedScenarios = new ArrayList<>();

        for (ScenarioMeta meta : ordered) {
            // Check dependencies
            boolean depsOk = true;
            for (String dep : meta.deps) {
                Status depStatus = results.get(dep);
                if (depStatus == null) {
                    System.out.printf("[RetryRunner] SKIP '%s' (%s) because dependency '%s' is not part of this run or has not executed%n",
                            meta.name, meta.id, dep);
                    results.put(meta.id, Status.SKIP);
                    skippedScenarios.add(meta.name);
                    hooks.ExtentCucumberPlugin.recordScenarioSkipped(meta.name,
                            "dependency not executed: " + dep);
                    depsOk = false;
                    break;
                }
                if (depStatus != Status.PASS) {
                    System.out.printf("[RetryRunner] SKIP '%s' (%s) because dependency '%s' status=%s%n",
                            meta.name, meta.id, dep, depStatus);
                    results.put(meta.id, Status.SKIP);
                    skippedScenarios.add(meta.name);
                    hooks.ExtentCucumberPlugin.recordScenarioSkipped(meta.name,
                            "dependency status != PASS: " + dep + " status=" + depStatus);
                    depsOk = false;
                    break;
                }
            }
            if (!depsOk) continue;

            boolean passed = false;

            // NEW: track failed example locations to rerun only those
            List<String> failedLocationsForNextAttempt = null;

            // Try each scenario up to (maxRetries+1) times
            for (int attempt = 1; attempt <= maxRetries + 1; attempt++) {
                hooks.FailureCapturePlugin.reset();

                int exitCode = runScenario(gluePkgs, tagExpr, featuresRoot, meta.name, failedLocationsForNextAttempt);
                System.out.printf("[RetryRunner] Exit code for '%s' (attempt %d) = %d%n", meta.name, attempt, exitCode);

                List<String> failedLocs = hooks.FailureCapturePlugin.getFailedLocations();
                if (!failedLocs.isEmpty()) {
                    System.out.println("[RetryRunner] Failed locations:");
                    for (String loc : failedLocs) System.out.println("  - " + loc);
                }

                if (exitCode == 0) {
                    System.out.printf("[RetryRunner] PASSED (%s) on attempt %d%n", meta.name, attempt);
                    passed = true;
                    passedScenarios.add(meta.name);
                    break;
                } else if (attempt <= maxRetries) {
                    // On next retry, only rerun failed locations (example rows)
                    failedLocationsForNextAttempt = failedLocs.isEmpty() ? null : failedLocs;
                    if (failedLocationsForNextAttempt != null) {
                        System.out.printf("[RetryRunner] FAILED (%s) -> retrying attempt %d/%d with %d failed example row(s)%n",
                                meta.name, attempt, maxRetries, failedLocationsForNextAttempt.size());
                    } else {
                        System.out.printf("[RetryRunner] FAILED (%s) -> retrying attempt %d/%d%n",
                                meta.name, attempt, maxRetries);
                    }
                }
            }

            if (passed) {
                results.put(meta.id, Status.PASS);
            } else {
                results.put(meta.id, Status.FAIL);
                stillFailing.add(meta.name);
                System.out.printf("[RetryRunner] FINAL FAIL (%s)%n", meta.name);
            }
        }

        // 4) Final summary
        System.out.println("===================================================");
        System.out.println("[RetryRunner] Final Summary:");
        System.out.println("  PASSED: " + passedScenarios.size());
        for (String s : passedScenarios) {
            System.out.println("    - " + s);
        }
        System.out.println("  FAILED: " + stillFailing.size());
        for (String s : stillFailing) {
            System.out.println("    - " + s);
        }
        System.out.println("  SKIPPED (dependency): " + skippedScenarios.size());
        for (String s : skippedScenarios) {
            System.out.println("    - " + s);
        }
        System.out.println("===================================================");

        // 5) Quit the driver ONCE at the end of the entire run
        hooks.ExtentCucumberPlugin.shutdownDriverNow();

        // 6) Assertion to set build status
        Assertions.assertTrue(stillFailing.isEmpty(), "Failed scenarios: " + stillFailing);
    }

    enum Status {PASS, FAIL, SKIP}

    static final class ScenarioMeta {
        final String name;       // scenario name (as used by --name filter)
        final String id;         // stable identifier (from @id:... or fallback to name)
        final Set<String> deps;  // dependency IDs
        final Path featureFile;

        ScenarioMeta(String name, String id, Set<String> deps, Path featureFile) {
            this.name = name;
            this.id = id;
            this.deps = deps;
            this.featureFile = featureFile;
        }
    }
}