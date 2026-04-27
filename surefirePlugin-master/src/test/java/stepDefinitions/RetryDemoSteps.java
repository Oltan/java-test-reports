package stepDefinitions;

import io.cucumber.java.Before;
import io.cucumber.java.Scenario;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Step definitions:
 * - "Health endpoint returns OK" -> passes immediately
 * - "Background job eventually succeeds" -> fails once, then passes on retry.
 *   Durable across JVM restarts by writing a marker under target/flaky-state/.
 */
public class RetryDemoSteps {

    private static final Path STATE_DIR = Paths.get("target", "flaky-state");
    private String scenarioName;

    @Before
    public void rememberScenario(Scenario scenario) {
        this.scenarioName = scenario.getName();
        try {
            Files.createDirectories(STATE_DIR);
        } catch (IOException ignored) {}
    }

    // ── Always-passing scenario ────────────────────────────────────────────────

    @Given("I ping the health endpoint")
    public void i_ping_the_health_endpoint() {
        System.out.println("Pinging fake health…");
    }

    @Then("I get status {string}")
    public void i_get_status_ok(String expected) {
        String actual = "OK"; // simulate success
        System.out.println("Health status = " + actual);
        assertEquals(expected, actual, "Health status mismatch");
    }

    // ── Flaky-once scenario (passes on second try) ────────────────────────────

    @Given("a background job starts")
    public void a_background_job_starts() {
        System.out.println("Starting background job (simulated) …");
    }

    @Then("it completes after one retry")
    public void it_completes_after_one_retry() {
        Path marker = STATE_DIR.resolve(toSafeSlug(scenarioName) + ".first-fail");

        // If marker does not exist -> create it and FAIL (first attempt)
        if (!Files.exists(marker)) {
            writeMarker(marker, "failed-once");
            throw new AssertionError(
                    "Simulated one-time flake for scenario '" + scenarioName + "'. Will pass on retry.");
        }

        // If marker exists -> remove it and PASS (second attempt)
        try {
            Files.deleteIfExists(marker);
        } catch (IOException ignored) {}
        System.out.println("Second attempt detected -> passing now.");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static void writeMarker(Path file, String content) {
        try {
            Files.write(file, content.getBytes(StandardCharsets.UTF_8),
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        } catch (IOException e) {
            // If we can't persist state, still fail the first time to be explicit
            throw new RuntimeException("Could not write retry marker: " + file, e);
        }
    }

    /**
     * Make a safe file name: replace non A-Za-z0-9 with '-', then trim dashes.
     */
    private static String toSafeSlug(String s) {
        if (s == null || s.isBlank()) return "scenario";
        String r = s.replaceAll("[^A-Za-z0-9]+", "-");
        r = r.replaceAll("^-+", "").replaceAll("-+$", "");
        return r.isEmpty() ? "scenario" : r;
    }
}
