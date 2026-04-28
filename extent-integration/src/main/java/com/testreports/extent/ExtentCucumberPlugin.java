package com.testreports.extent;

import com.aventstack.extentreports.ExtentReports;
import com.aventstack.extentreports.ExtentTest;
import com.aventstack.extentreports.GherkinKeyword;
import com.aventstack.extentreports.Status;
import io.cucumber.plugin.ConcurrentEventListener;
import io.cucumber.plugin.event.EventPublisher;
import io.cucumber.plugin.event.PickleStepTestStep;
import io.cucumber.plugin.event.Result;
import io.cucumber.plugin.event.TestCase;
import io.cucumber.plugin.event.TestCaseFinished;
import io.cucumber.plugin.event.TestCaseStarted;
import io.cucumber.plugin.event.TestRunFinished;
import io.cucumber.plugin.event.TestSourceRead;
import io.cucumber.plugin.event.TestStepFinished;
import io.cucumber.plugin.event.TestStepStarted;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Cucumber 7 plugin that builds a proper Feature → Scenario → Step hierarchy
 * in the ExtentReports Spark report.
 *
 * The classic mistake that causes "scenarios where features should be" is calling
 * {@code extent.createTest(scenario.getName())} directly — that produces a top-level
 * node for every scenario.  This plugin instead calls
 * {@code featureNode.createNode("Scenario", scenario.getName())} so each scenario
 * is a child of its Feature.
 */
public class ExtentCucumberPlugin implements ConcurrentEventListener {

    private static final ExtentReports EXTENT = ExtentReportManager.getInstance();

    // Feature URI → feature-level ExtentTest (shared across threads, ConcurrentHashMap)
    private final Map<URI, ExtentTest> featureNodes = new ConcurrentHashMap<>();
    // Feature URI → display name parsed from source
    private final Map<URI, String> featureNames = new ConcurrentHashMap<>();
    // Thread ID → current scenario node
    private final Map<Long, ExtentTest> scenarioNodes = new ConcurrentHashMap<>();
    // Thread ID → current step node
    private final Map<Long, ExtentTest> stepNodes = new ConcurrentHashMap<>();

    @Override
    public void setEventPublisher(EventPublisher publisher) {
        publisher.registerHandlerFor(TestSourceRead.class,   this::onSourceRead);
        publisher.registerHandlerFor(TestCaseStarted.class,  this::onCaseStarted);
        publisher.registerHandlerFor(TestStepStarted.class,  this::onStepStarted);
        publisher.registerHandlerFor(TestStepFinished.class, this::onStepFinished);
        publisher.registerHandlerFor(TestCaseFinished.class, this::onCaseFinished);
        publisher.registerHandlerFor(TestRunFinished.class,  this::onRunFinished);
    }

    // ── Handlers ──────────────────────────────────────────────────────────────

    private void onSourceRead(TestSourceRead event) {
        featureNames.put(event.getUri(), parseFeatureName(event.getSource(), event.getUri()));
    }

    private void onCaseStarted(TestCaseStarted event) {
        TestCase tc = event.getTestCase();
        URI uri = tc.getUri();
        String featureName = featureNames.getOrDefault(uri, uriBasename(uri));

        // computeIfAbsent ensures only one Feature node per URI even under parallel load
        ExtentTest feature = featureNodes.computeIfAbsent(uri,
                k -> gherkinNode(EXTENT, "Feature", featureName));

        ExtentTest scenario = gherkinChildNode(feature, "Scenario", tc.getName());
        tc.getTags().forEach(tag -> scenario.assignCategory(tag.replace("@", "")));

        scenarioNodes.put(tid(), scenario);
        ExtentTestHolder.set(scenario);     // expose to @After screenshot hooks
    }

    private void onStepStarted(TestStepStarted event) {
        if (!(event.getTestStep() instanceof PickleStepTestStep step)) return;
        ExtentTest scenario = scenarioNodes.get(tid());
        if (scenario == null) return;

        String kw = normalizeKeyword(step.getStep().getKeyword());
        stepNodes.put(tid(), gherkinChildNode(scenario, kw, step.getStep().getText()));
    }

    private void onStepFinished(TestStepFinished event) {
        if (!(event.getTestStep() instanceof PickleStepTestStep)) return;
        ExtentTest stepNode = stepNodes.remove(tid());
        if (stepNode == null) return;

        markResult(stepNode, event.getResult());
    }

    private void onCaseFinished(TestCaseFinished event) {
        scenarioNodes.remove(tid());
        ExtentTestHolder.clear();

        // If a scenario fails with no steps (undefined / missing step def),
        // mark it directly so the report reflects the failure.
        Result r = event.getResult();
        if (r.getStatus() == io.cucumber.plugin.event.Status.FAILED
                && r.getError() != null) {
            ExtentTest scenario = scenarioNodes.get(tid());
            if (scenario != null) scenario.fail(r.getError().getMessage());
        }
    }

    private void onRunFinished(TestRunFinished event) {
        ExtentReportManager.flush();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void markResult(ExtentTest node, Result result) {
        switch (result.getStatus()) {
            case PASSED            -> node.pass("Passed");
            case FAILED, UNDEFINED, AMBIGUOUS -> {
                Throwable err = result.getError();
                if (err != null) node.fail(err);
                else             node.fail("Step failed");
            }
            case SKIPPED, PENDING  -> node.skip("Skipped");
        }
    }

    /**
     * Creates a top-level ExtentTest with a Gherkin keyword icon.
     * Falls back to a plain node if the keyword is unrecognised.
     */
    private static ExtentTest gherkinNode(ExtentReports reports, String keyword, String name) {
        try {
            return reports.createTest(new GherkinKeyword(keyword), name);
        } catch (ClassNotFoundException e) {
            return reports.createTest(name);
        }
    }

    /** Creates a child node of {@code parent} with a Gherkin keyword icon. */
    private static ExtentTest gherkinChildNode(ExtentTest parent, String keyword, String name) {
        try {
            return parent.createNode(new GherkinKeyword(keyword), name);
        } catch (ClassNotFoundException e) {
            return parent.createNode(name);
        }
    }

    /**
     * Normalise raw Cucumber step keywords (e.g. "Given ", "* ") to the
     * strings that ExtentReports recognises.
     */
    private static String normalizeKeyword(String raw) {
        String kw = raw == null ? "" : raw.trim();
        return switch (kw) {
            case "Given", "When", "Then", "And", "But" -> kw;
            default -> "And";  // covers "*" and any unknown keyword
        };
    }

    private static String parseFeatureName(String source, URI uri) {
        if (source != null) {
            for (String line : source.split("\n")) {
                String t = line.trim();
                if (t.startsWith("Feature:")) {
                    return t.substring("Feature:".length()).trim();
                }
            }
        }
        return uriBasename(uri);
    }

    private static String uriBasename(URI uri) {
        String path = uri.getPath();
        if (path == null) {
            return "unknown";
        }
        String file = path.substring(path.lastIndexOf('/') + 1);
        return file.replaceFirst("\\.feature$", "");
    }

    private static long tid() {
        return Thread.currentThread().getId();
    }
}
