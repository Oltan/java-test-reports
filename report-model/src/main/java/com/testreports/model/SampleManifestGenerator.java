package com.testreports.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.io.File;
import java.io.IOException;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.logging.Logger;

public class SampleManifestGenerator {

    private static final Logger LOGGER = Logger.getLogger(SampleManifestGenerator.class.getName());

    private static final String OUTPUT_PATH = "../manifests/sample-run-001.json";

    public static void main(String[] args) {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

        RunManifest manifest = createSampleManifest();

        try {
            File outputDir = new File("../manifests");
            if (!outputDir.exists()) {
                outputDir.mkdirs();
            }

            File outputFile = new File(OUTPUT_PATH);
            mapper.writeValue(outputFile, manifest);
            LOGGER.info("Sample manifest written to: " + outputFile.getAbsolutePath());
        } catch (IOException e) {
            System.err.println("Failed to write sample manifest: " + e.getMessage());
            System.exit(1);
        }
    }

    public static RunManifest createSampleManifest() {
        StepResult step1 = new StepResult("Navigate to login page", "passed", null);
        StepResult step2 = new StepResult("Enter credentials", "passed", null);
        StepResult step3 = new StepResult("Click login button", "passed", null);

        StepResult failStep1 = new StepResult("Navigate to checkout", "passed", null);
        StepResult failStep2 = new StepResult("Fill shipping details", "passed", null);
        StepResult failStep3 = new StepResult("Submit order", "failed", "Payment processing failed: card declined");

        AttachmentInfo screenshot1 = new AttachmentInfo("login-success.png", "image/png", "screenshots/login-success.png");
        AttachmentInfo screenshot2 = new AttachmentInfo("order-failure.png", "image/png", "screenshots/order-failure.png");
        AttachmentInfo logFile = new AttachmentInfo("test-output.log", "text/plain", "logs/test-output.log");

        ScenarioResult passedScenario = new ScenarioResult(
            "scenario-001",
            "User Login Success",
            "passed",
            "PT15.234S",
            "ABS-12345",
            Arrays.asList("login", "smoke", "critical"),
            Arrays.asList(step1, step2, step3),
            List.of(screenshot1)
        );

        ScenarioResult failedScenario = new ScenarioResult(
            "scenario-002",
            "Order Submission",
            "failed",
            "PT42.891S",
            "ABS-12346",
            Arrays.asList("checkout", "regression"),
            Arrays.asList(failStep1, failStep2, failStep3),
            Arrays.asList(screenshot2, logFile)
        );

        return new RunManifest(
            "run-2026-04-26-001",
            Instant.parse("2026-04-26T10:30:00Z"),
            2,
            1,
            1,
            0,
            "PT58.125S",
            Arrays.asList(passedScenario, failedScenario)
        );
    }
}