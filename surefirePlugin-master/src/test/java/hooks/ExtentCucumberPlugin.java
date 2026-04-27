package hooks;

import Utils.CaptureScreen;
import com.aventstack.extentreports.ExtentReports;
import com.aventstack.extentreports.ExtentTest;
import com.aventstack.extentreports.Status;
import com.aventstack.extentreports.service.ExtentService;
import io.cucumber.plugin.ConcurrentEventListener;
import io.cucumber.plugin.event.*;
import io.github.bonigarcia.wdm.WebDriverManager;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Cucumber 7+ için ExtentReports eklentisi
 * Her senaryonun yalnızca en güncel denemesini (yeniden deneme geçmişi olmadan) kaydeder.
 * <p>
 * NOTE: Scenarios whose name starts with "Background_" are ignored and NOT added to the report.
 */
public class ExtentCucumberPlugin implements ConcurrentEventListener {

    private static final ExtentReports extent = ExtentService.getInstance();
    private static final ConcurrentMap<String, ExtentTest> scenarioTests = new ConcurrentHashMap<>();
    private static final ConcurrentMap<String, ExtentTest> currentRuns = new ConcurrentHashMap<>();
    private static final ConcurrentMap<String, Integer> attemptCounter = new ConcurrentHashMap<>();
    // Per-example row nodes and final statuses
    private static final ConcurrentMap<String, ExtentTest> exampleTests = new ConcurrentHashMap<>();
    private static final ConcurrentMap<String, Status> exampleFinalStatus = new ConcurrentHashMap<>();
    private static final ConcurrentMap<String, Set<String>> scenarioExampleKeys = new ConcurrentHashMap<>();
    private static final AtomicBoolean driverClosed = new AtomicBoolean(false);
    // Prefix for scenarios to ignore in the report (hardcoded per request). Change here to make configurable.
    private static final String IGNORE_SCENARIO_PREFIX = "Background_";
    private static boolean initialized = false;
    private static boolean lastScenarioFailed = false;
    // Single owner driver
    private static volatile WebDriver driver;
    // Rapor ve video yolları: target/extent-report altında
    private static Path reportHtmlPath;                 // target/extent-report/<TAG>-yyyyMMdd_HHmmss.html
    private static Path reportDir;                      // target/extent-report
    private static Path videosDir;                      // target/extent-report/videos

    static {
        // JVM shutdown hook: safety net on abnormal termination
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            if (driverClosed.get()) return;
            WebDriver d = driver;
            if (d != null) {
                try {
                    d.quit();
                    System.out.println("Driver quit at JVM shutdown");
                } catch (Exception e) {
                    System.err.println("Failed to quit driver at shutdown: " + e.getMessage());
                } finally {
                    driver = null;
                    driverClosed.set(true);
                }
            }
        }, "webdriver-shutdown-hook"));
    }

    // Expose the single driver to hooks/steps
    public static WebDriver getDriver() {
        return driver;
    }

    // Call ONCE at the end of the entire outer run (e.g., from CucumberRetryRunnerTest)
    public static void shutdownDriverNow() {
        if (driverClosed.compareAndSet(false, true)) {
            WebDriver d = driver;
            driver = null;
            if (d != null) {
                try {
                    d.quit();
                    System.out.println("Driver quit at suite end");
                } catch (Exception e) {
                    System.err.println("Suite end: driver quit failed: " + e.getMessage());
                }
            }
        }
    }

    private static String exampleKeyOf(TestCase tc) {
        try {
            Path p = Paths.get(tc.getUri());
            return p.toString() + ":" + tc.getLocation().getLine();
        } catch (Exception e) {
            return String.valueOf(tc.getUri()) + ":" + tc.getLocation().getLine();
        }
    }

    private static String pickPrimaryTag(List<String> rawTags) {
        if (rawTags == null || rawTags.isEmpty()) return "AllFeatures";
        List<String> cleaned = new ArrayList<>();
        for (String t : rawTags) {
            if (t == null) continue;
            String name = t.startsWith("@") ? t.substring(1) : t;
            cleaned.add(name);
        }
        Set<String> blacklist = new HashSet<>(Arrays.asList("wip", "ignore", "skip", "skipped", "disabled"));
        for (String t : cleaned) {
            if (!blacklist.contains(t.toLowerCase())) {
                return t;
            }
        }
        return cleaned.get(0);
    }

    private static String toSafeSlug(String s) {
        if (s == null) return "";
        String replaced = s.replaceAll("[^A-Za-z0-9]+", "-");
        return replaced.replaceAll("^-+", "").replaceAll("-+$", "");
    }

    private static String sanitize(String s) {
        return s == null ? "" : s.replaceAll("[^\\p{IsLetter}\\p{IsDigit}._-]", "_");
    }

    private static String escapeHtml(String input) {
        if (input == null) return "";
        StringBuilder out = new StringBuilder(Math.max(16, input.length()));
        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);
            switch (c) {
                case '<':
                    out.append("&lt;");
                    break;
                case '>':
                    out.append("&gt;");
                    break;
                case '&':
                    out.append("&amp;");
                    break;
                case '"':
                    out.append("&quot;");
                    break;
                case '\'':
                    out.append("&#39;");
                    break;
                default:
                    out.append(c);
            }
        }
        return out.toString();
    }

    /**
     * Public helper for external runners to record scenarios that were skipped
     * without being executed by Cucumber (e.g. skipped due to dependency).
     * <p>
     * This creates an ExtentTest entry (if not present), marks it SKIP and adds an informational message.
     * <p>
     * Usage: hooks.ExtentCucumberPlugin.recordScenarioSkipped(scenarioName, "reason text");
     */
    public static void recordScenarioSkipped(String scenarioName, String reason) {
        try {
            if (shouldIgnoreScenario(scenarioName)) {
                return; // do not create entries for ignored scenarios
            }

            ExtentTest scenarioTest = scenarioTests.computeIfAbsent(scenarioName, name -> {
                ExtentTest t = extent.createTest(name);
                if (reason != null && !reason.isBlank()) {
                    t.info("Marked SKIPPED by runner: " + escapeHtml(reason));
                } else {
                    t.info("Marked SKIPPED by runner");
                }
                return t;
            });

            // create a synthetic attempt entry so the report structure is similar to real attempts
            String attemptKey = scenarioName + "#skipped";
            ExtentTest attempt = currentRuns.computeIfAbsent(attemptKey, k -> {
                ExtentTest node = scenarioTest.createNode("skipped");
                return node;
            });

            attempt.getModel().setStatus(Status.SKIP);
            scenarioTest.getModel().setStatus(Status.SKIP);

            // flush immediately so the entry appears in the report even if run finishes soon after
            extent.flush();
        } catch (Exception e) {
            System.err.println("Failed to record skipped scenario in Extent: " + e.getMessage());
        }
    }

    private static boolean shouldIgnoreScenario(String scenarioName) {
        return scenarioName != null && scenarioName.startsWith(IGNORE_SCENARIO_PREFIX);
    }

    @Override
    public void setEventPublisher(EventPublisher publisher) {
        publisher.registerHandlerFor(TestCaseStarted.class, this::handleTestCaseStarted);
        publisher.registerHandlerFor(TestStepFinished.class, this::handleTestStepFinished);
        publisher.registerHandlerFor(TestCaseFinished.class, this::handleTestCaseFinished);
        publisher.registerHandlerFor(TestRunFinished.class, this::handleTestRunFinished);
    }

    private void handleTestCaseStarted(TestCaseStarted event) {
        if (!initialized) {
            Object outObj = ExtentService.getProperty("extent.reporter.spark.out");
            String out = (outObj instanceof String) ? ((String) outObj) : null;
            if (out == null || out.isBlank()) {
                out = "target/extent-report/";
            }

            Path outPath = Paths.get(out);
            if (!outPath.isAbsolute()) {
                outPath = Paths.get("").toAbsolutePath().resolve(outPath);
            }
            outPath = outPath.normalize();

            if (out.toLowerCase(Locale.ROOT).endsWith(".html")) {
                reportHtmlPath = outPath;
                reportDir = outPath.getParent();
            } else {
                reportDir = outPath;
                reportHtmlPath = reportDir.resolve("index.html");
            }

            try {
                if (reportDir != null) Files.createDirectories(reportDir);
            } catch (Exception ignored) {
            }

            videosDir = reportDir.resolve("videos");
            try {
                Files.createDirectories(videosDir);
            } catch (Exception ignored) {
            }

            initialized = true;
        }

        String scenarioName = event.getTestCase().getName();

        // Skip scenarios that start with the designated ignore prefix
        if (shouldIgnoreScenario(scenarioName)) {
            return;
        }

        String exampleKey = exampleKeyOf(event.getTestCase());
        int attempt = attemptCounter.merge(exampleKey, 1, Integer::sum);

        if (driver == null) {
            System.out.println("Creating new driver (attempt " + attempt + ")");
            WebDriverManager.chromedriver().setup();
            driver = new ChromeDriver();
            // Once a new driver is created, it's not closed yet
            driverClosed.set(false);
            try {
                Thread.sleep(5000); // wait for visibility in recording
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        ExtentTest scenarioTest = scenarioTests.computeIfAbsent(scenarioName, name -> {
            ExtentTest test = extent.createTest(name);

            Object prop = ExtentService.getProperty("report.include.tags");
            String propStr = (prop != null) ? prop.toString() : System.getProperty("report.include.tags", "false");
            boolean includeTags = Boolean.parseBoolean(propStr);

            if (includeTags) {
                for (String tag : event.getTestCase().getTags()) {
                    test.assignCategory(tag); // use 'test', not 'scenarioTest'
                }
            }
            return test;
        });

        scenarioExampleKeys
                .computeIfAbsent(scenarioName, k -> Collections.newSetFromMap(new ConcurrentHashMap<>()))
                .add(exampleKey);

        int exampleLine = event.getTestCase().getLocation().getLine();
        String rowContent = "";
        try {
            Path featurePath = Paths.get(event.getTestCase().getUri());
            List<String> flines = Files.readAllLines(featurePath, java.nio.charset.StandardCharsets.UTF_8);
            if (exampleLine > 0 && exampleLine <= flines.size()) {
                rowContent = flines.get(exampleLine - 1).trim();
            }
        } catch (Exception ignored) {
        }
        String fileName = "";
        try {
            fileName = Paths.get(event.getTestCase().getUri()).getFileName().toString();
        } catch (Exception ignored) {
        }
        String rowLabel = String.format("(%s:%d): %s",
                fileName, exampleLine, rowContent.isEmpty() ? ("line " + exampleLine) : rowContent);
        ExtentTest exampleNode = exampleTests.computeIfAbsent(exampleKey, k -> scenarioTest.createNode(rowLabel));

        ExtentTest attemptNode = exampleNode.createNode("Deneme #" + attempt);
        currentRuns.put(exampleKey, attemptNode);
    }

    private void handleTestStepFinished(TestStepFinished event) {
        if (!(event.getTestStep() instanceof PickleStepTestStep)) {
            return; // skip hooks
        }

        String scenarioName = event.getTestCase().getName();
        // Do not log steps for ignored scenarios
        if (shouldIgnoreScenario(scenarioName)) {
            return;
        }

        PickleStepTestStep step = (PickleStepTestStep) event.getTestStep();
        String stepText = step.getStep().getKeyword() + step.getStep().getText();
        String exampleKey = exampleKeyOf(event.getTestCase());
        ExtentTest test = currentRuns.get(exampleKey);
        if (test == null) {
            ExtentTest scenarioTest = scenarioTests.computeIfAbsent(scenarioName, extent::createTest);
            test = scenarioTest.createNode("İzlenemeyen Deneme");
            currentRuns.put(exampleKey, test);
        }

        switch (event.getResult().getStatus()) {
            case PASSED:
                test.log(Status.PASS, "<div style='background-color:#d4edda;padding:4px;border-radius:4px;'>"
                        + escapeHtml(stepText) + "</div>");
                break;
            case FAILED:
                Throwable error = event.getResult().getError();

                StringBuilder details = new StringBuilder();
                details.append("<div style='background-color:#f8d7da;padding:6px;border-radius:4px;'>")
                        .append("<b>").append(escapeHtml(stepText)).append("</b>");

                if (error != null) {
                    details.append("<div style='max-height:200px;overflow-y:auto;"
                                    + "background-color:#fff;border:1px solid #f5c2c7;"
                                    + "margin-top:8px;padding:6px;border-radius:4px;'>")
                            .append("<pre style='white-space:pre-wrap;margin:0;'>")
                            .append(escapeHtml(error.toString()));

                    for (StackTraceElement element : error.getStackTrace()) {
                        details.append("\n    at ").append(escapeHtml(element.toString()));
                    }

                    details.append("</pre></div>");
                }

                details.append("</div>");

                test.log(Status.FAIL, details.toString());

                try {
                    String base64Screenshot = CaptureScreen.captureAsBase64(driver);
                    test.addScreenCaptureFromBase64String(base64Screenshot);
                } catch (Exception e) {
                    test.warning("Ekran görüntüsü alınamadı: " + escapeHtml(e.getMessage()));
                }

                break;
            case SKIPPED:
                test.log(Status.SKIP, "<div style='background-color:#fff3cd;padding:4px;border-radius:4px;'>"
                        + escapeHtml(stepText) + "</div>");
                break;
            default:
                test.log(Status.WARNING, "Unknown status for step: " + "<div style='background-color:#e2e3e5;padding:4px;border-radius:4px;'>"
                        + escapeHtml(stepText) + "</div>");
        }
    }

    private void handleTestCaseFinished(TestCaseFinished event) {
        String scenarioName = event.getTestCase().getName();
        String exampleKey = exampleKeyOf(event.getTestCase());

        // If this scenario should be ignored, ensure there's no residue and skip reporting
        if (shouldIgnoreScenario(scenarioName)) {
            currentRuns.remove(exampleKey);
            exampleTests.remove(exampleKey);
            exampleFinalStatus.remove(exampleKey);
            attemptCounter.remove(exampleKey);
            scenarioExampleKeys.remove(scenarioName);
            return;
        }

        ExtentTest attemptTest = currentRuns.get(exampleKey);
        ExtentTest scenarioTest = scenarioTests.get(scenarioName);

        if (attemptTest == null) {
            ExtentTest root = (scenarioTest != null) ? scenarioTest : extent.createTest(scenarioName);
            attemptTest = root.createNode("Untracked Attempt (finish)");
            currentRuns.put(exampleKey, attemptTest);
        }
        if (scenarioTest == null) {
            scenarioTest = extent.createTest(scenarioName);
            scenarioTests.put(scenarioName, scenarioTest);
        }

        Status caseExtentStatus;
        switch (event.getResult().getStatus()) {
            case PASSED:
                caseExtentStatus = Status.PASS;
                attemptTest.getModel().setStatus(Status.PASS);
                break;
            case FAILED:
                caseExtentStatus = Status.FAIL;
                attemptTest.getModel().setStatus(Status.FAIL);

                try {
                    Path discovered = findLatestVideoFor(scenarioName);
                    if (discovered != null) {
                        String rel = toRelativeUrl(reportDir, discovered);

                        String html =
                                "<details style='margin-top:8px'>" +
                                        "<summary><b>Ekran kaydına buradan ulaşabilirsiniz</b></summary>" +
                                        "<video controls style='width:100%;max-width:980px;display:block;margin-top:8px'>" +
                                        "<source src='" + rel + "' type='video/mp4'>" +
                                        "Your browser does not support the video tag." +
                                        "</video>" +
                                        "<div style='margin-top:6px'><a href='" + rel + "' download>Download MP4</a></div>" +
                                        "</details>";

                        attemptTest.info(html);
                    } else {
                        attemptTest.info("Eşleşen ekran kaydı dizin altında bulunamadı " +
                                videosDir.toAbsolutePath() + " for: " + escapeHtml(scenarioName));
                    }
                } catch (Exception e) {
                    attemptTest.warning("Ekran kaydı eklenemedi: " + escapeHtml(e.getMessage()));
                }

                lastScenarioFailed = true;
                break;
            case SKIPPED:
                caseExtentStatus = Status.SKIP;
                attemptTest.getModel().setStatus(Status.SKIP);
                break;
            default:
                caseExtentStatus = Status.WARNING;
                attemptTest.getModel().setStatus(Status.WARNING);
        }

        // Update example node final status to latest attempt
        ExtentTest exampleNode = exampleTests.get(exampleKey);
        if (exampleNode != null) {
            exampleNode.getModel().setStatus(caseExtentStatus);
        }
        exampleFinalStatus.put(exampleKey, caseExtentStatus);

        // Recompute scenario aggregated status from its examples' latest statuses.
        recomputeScenarioStatus(scenarioName);
    }

    private void handleTestRunFinished(TestRunFinished event) {
        // Do NOT quit the driver here because CucumberRetryRunnerTest runs Cucumber per-scenario.
        try {
            extent.flush();
        } catch (Exception e) {
            System.err.println("Extent flush error: " + e.getMessage());
        }
    }

    private Path findLatestVideoFor(String scenarioName) {
        if (!Files.isDirectory(videosDir)) return null;
        final String needle = sanitize(scenarioName).toLowerCase();
        try (java.util.stream.Stream<Path> stream = Files.list(videosDir)) {
            return stream
                    .filter(p -> {
                        String fn = p.getFileName().toString().toLowerCase();
                        return fn.endsWith(".mp4") && fn.contains(needle);
                    })
                    .sorted((a, b) -> {
                        try {
                            return Files.getLastModifiedTime(b).compareTo(Files.getLastModifiedTime(a));
                        } catch (IOException e) {
                            return 0;
                        }
                    })
                    .findFirst()
                    .orElse(null);
        } catch (IOException e) {
            return null;
        }
    }

    private String toRelativeUrl(Path fromDir, Path target) {
        try {
            Path absFrom = fromDir.toAbsolutePath().normalize();
            Path absTarget = target.toAbsolutePath().normalize();
            Path rel = absFrom.relativize(absTarget);
            return rel.toString().replace('\\', '/');
        } catch (Exception e) {
            return target.toAbsolutePath().normalize().toString().replace('\\', '/');
        }
    }

    // Recompute scenario status from example rows' latest statuses:
    // - PASS if all example rows' latest status is PASS
    // - FAIL if any example row's latest status is FAIL
    // - otherwise SKIP/WARNING based on presence
    private void recomputeScenarioStatus(String scenarioName) {
        ExtentTest scenarioTest = scenarioTests.get(scenarioName);
        if (scenarioTest == null) return;
        Set<String> keys = scenarioExampleKeys.get(scenarioName);
        if (keys == null || keys.isEmpty()) return;

        boolean anyFail = false;
        boolean anySkip = false;
        boolean anyWarn = false;
        boolean anyPass = false;

        for (String k : keys) {
            Status s = exampleFinalStatus.get(k);
            if (s == null) continue;
            switch (s) {
                case FAIL -> anyFail = true;
                case SKIP -> anySkip = true;
                case WARNING -> anyWarn = true;
                case PASS -> anyPass = true;
                default -> {
                }
            }
        }

        Status agg;
        if (anyFail) {
            agg = Status.FAIL;
        } else if (anySkip) {
            agg = Status.SKIP;
        } else if (anyWarn) {
            agg = Status.WARNING;
        } else if (anyPass) {
            agg = Status.PASS;
        } else {
            agg = Status.PASS;
        }
        scenarioTest.getModel().setStatus(agg);
    }
}