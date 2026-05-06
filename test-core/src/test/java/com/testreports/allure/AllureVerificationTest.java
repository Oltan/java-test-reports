package com.testreports.allure;

import io.qameta.allure.Allure;
import io.qameta.allure.model.Status;
import io.qameta.allure.model.StepResult;
import io.qameta.allure.model.Attachment;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

/**
 * Simple verification test that generates dummy Allure result JSON.
 * This validates the Allure integration setup without requiring real test execution.
 */
public class AllureVerificationTest {

    @Test
    public void verifyAllureSetup() throws IOException {
        // Create a step
        Allure.step("Test step", () -> {
            // Step implementation
        });

        // Add attachment
        Allure.addAttachment("screenshot", "image/png", "base64content", "png");

        // Create a manual test result
        String testUuid = UUID.randomUUID().toString();
        StepResult stepResult = new StepResult()
                .setName("Manual Step")
                .setStatus(Status.PASSED);

        Allure.getLifecycle().startStep(testUuid, stepResult);
        Allure.getLifecycle().stopStep();

        // Ensure target directory exists
        Path resultsDir = Path.of("target/allure-results");
        Files.createDirectories(resultsDir);

        System.out.println("Allure verification test completed. Results will be generated in: " + resultsDir.toAbsolutePath());
    }

    @Test
    public void verifyAllureAttachment() {
        Allure.step("Adding test attachment", () -> {
            Allure.addAttachment("test-log", "text/plain", "Sample log content", "txt");
        });

        Allure.addAttachment("metadata", "application/json", "{\"key\": \"value\"}");
    }
}
