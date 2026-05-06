package com.testreports.steps;

import io.cucumber.java.Before;
import io.cucumber.java.Scenario;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.assertTrue;

public class RetryDemoSteps {

    private static final Path STATE_DIR = Paths.get(System.getProperty("retry.state.dir", "target/retry-state"));

    private String scenarioName;

    @Before
    public void rememberScenario(Scenario scenario) throws IOException {
        scenarioName = scenario.getName();
        Files.createDirectories(STATE_DIR);
    }

    @Given("a stable step")
    public void aStableStep() {
        assertTrue(true, "Stable retry demo step should always pass");
    }

    @Then("it should pass")
    public void itShouldPass() {
        assertTrue(true, "Stable retry demo assertion should always pass");
    }

    @Given("a flaky step that fails once")
    public void aFlakyStepThatFailsOnce() throws IOException {
        int attempt = readAttemptCount() + 1;
        writeAttemptCount(attempt);

        if (attempt == 1) {
            throw new AssertionError("Simulated flaky failure for '" + scenarioName + "' on first attempt");
        }
    }

    @Then("it should eventually pass")
    public void itShouldEventuallyPass() throws IOException {
        assertTrue(readAttemptCount() > 1, "Flaky scenario should pass only after a retry");
    }

    private int readAttemptCount() throws IOException {
        Path file = stateFile();
        if (!Files.exists(file)) {
            return 0;
        }
        String value = Files.readString(file, StandardCharsets.UTF_8).trim();
        return value.isEmpty() ? 0 : Integer.parseInt(value);
    }

    private void writeAttemptCount(int attempt) throws IOException {
        Files.writeString(stateFile(), Integer.toString(attempt), StandardCharsets.UTF_8);
    }

    private Path stateFile() {
        return STATE_DIR.resolve(toSafeSlug(scenarioName) + ".txt");
    }

    private static String toSafeSlug(String value) {
        if (value == null || value.isBlank()) {
            return "scenario";
        }
        String slug = value.replaceAll("[^A-Za-z0-9]+", "-").replaceAll("^-+", "").replaceAll("-+$", "");
        return slug.isEmpty() ? "scenario" : slug;
    }
}
