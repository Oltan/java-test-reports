package com.testreports.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.io.File;
import java.io.IOException;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ManifestTest {

    private final ObjectMapper mapper;

    public ManifestTest() {
        this.mapper = new ObjectMapper();
        this.mapper.registerModule(new JavaTimeModule());
        this.mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }

    @Test
    void testRoundTripSerialization() throws IOException {
        RunManifest original = SampleManifestGenerator.createSampleManifest();

        String json = mapper.writeValueAsString(original);
        assertNotNull(json);
        assertTrue(json.contains("\"runId\":\"run-2026-04-26-001\""));
        assertTrue(json.contains("\"totalScenarios\":2"));

        RunManifest deserialized = mapper.readValue(json, RunManifest.class);
        assertNotNull(deserialized);

        assertEquals(original.getRunId(), deserialized.getRunId());
        assertEquals(original.getTimestamp(), deserialized.getTimestamp());
        assertEquals(original.getTotalScenarios(), deserialized.getTotalScenarios());
        assertEquals(original.getPassed(), deserialized.getPassed());
        assertEquals(original.getFailed(), deserialized.getFailed());
        assertEquals(original.getSkipped(), deserialized.getSkipped());
        assertEquals(original.getDuration(), deserialized.getDuration());
        assertEquals(original.getScenarios().size(), deserialized.getScenarios().size());
    }

    @Test
    void testScenarioSerialization() throws IOException {
        RunManifest manifest = SampleManifestGenerator.createSampleManifest();

        String json = mapper.writeValueAsString(manifest);
        RunManifest deserialized = mapper.readValue(json, RunManifest.class);

        ScenarioResult passedScenario = deserialized.getScenarios().get(0);
        assertEquals("scenario-001", passedScenario.getId());
        assertEquals("User Login Success", passedScenario.getName());
        assertEquals("passed", passedScenario.getStatus());
        assertEquals("PT15.234S", passedScenario.getDuration());
        assertEquals("ABS-12345", passedScenario.getDoorsAbsNumber());
        assertEquals(3, passedScenario.getSteps().size());
        assertEquals(1, passedScenario.getAttachments().size());

        ScenarioResult failedScenario = deserialized.getScenarios().get(1);
        assertEquals("scenario-002", failedScenario.getId());
        assertEquals("Order Submission", failedScenario.getName());
        assertEquals("failed", failedScenario.getStatus());
        assertEquals("Payment processing failed: card declined", failedScenario.getSteps().get(2).getErrorMessage());
    }

    @Test
    void testStepResultSerialization() throws IOException {
        StepResult step = new StepResult("Test Step", "passed", null);
        String json = mapper.writeValueAsString(step);
        StepResult deserialized = mapper.readValue(json, StepResult.class);

        assertEquals("Test Step", deserialized.getName());
        assertEquals("passed", deserialized.getStatus());
        assertNull(deserialized.getErrorMessage());
    }

    @Test
    void testAttachmentInfoSerialization() throws IOException {
        AttachmentInfo attachment = new AttachmentInfo("test.png", "image/png", "screenshots/test.png");
        String json = mapper.writeValueAsString(attachment);
        AttachmentInfo deserialized = mapper.readValue(json, AttachmentInfo.class);

        assertEquals("test.png", deserialized.getName());
        assertEquals("image/png", deserialized.getType());
        assertEquals("screenshots/test.png", deserialized.getPath());
    }

    @Test
    void testTagsRoundTrip() throws IOException {
        ScenarioResult scenario = new ScenarioResult(
            "test-id", "Test Scenario", "passed", "PT10S",
            null, Arrays.asList("tag1", "tag2", "tag3"),
            List.of(), List.of()
        );

        String json = mapper.writeValueAsString(scenario);
        ScenarioResult deserialized = mapper.readValue(json, ScenarioResult.class);

        assertEquals(3, deserialized.getTags().size());
        assertTrue(deserialized.getTags().contains("tag1"));
        assertTrue(deserialized.getTags().contains("tag2"));
        assertTrue(deserialized.getTags().contains("tag3"));
    }

    @Test
    void testNullDoorsAbsNumber() throws IOException {
        ScenarioResult scenario = new ScenarioResult(
            "test-id", "Test", "skipped", "PT1S",
            null, List.of(), List.of(), List.of()
        );

        String json = mapper.writeValueAsString(scenario);
        assertTrue(json.contains("\"doorsAbsNumber\":null"));

        ScenarioResult deserialized = mapper.readValue(json, ScenarioResult.class);
        assertNull(deserialized.getDoorsAbsNumber());
    }

    @Test
    void testManifestValidatorValidatesSampleFile() throws IOException {
        ManifestValidator validator = new ManifestValidator();
        String samplePath = "../../../../manifests/sample-run-001.json";

        File sampleFile = new File(samplePath);
        if (!sampleFile.exists()) {
            fail("Sample manifest file not found. Run SampleManifestGenerator first.");
        }

        List<String> errors = validator.validate(samplePath);
        assertTrue(errors.isEmpty(), "Expected no validation errors, got: " + errors);
    }

    @Test
    void testValidatorRejectsInvalidJson() throws IOException {
        ManifestValidator validator = new ManifestValidator();
        List<String> errors = validator.validate("non-existent-file.json");
        assertFalse(errors.isEmpty());
        assertTrue(errors.stream().anyMatch(e -> e.contains("File not found")));
    }

    @Test
    void testValidatorDetectsMissingFields() throws IOException {
        ManifestValidator validator = new ManifestValidator();

        String invalidJson = "{\"runId\":\"test\",\"timestamp\":\"2026-04-26T10:30:00Z\"}";
        File tempFile = File.createTempFile("invalid", ".json");
        tempFile.deleteOnExit();
        mapper.writeValue(tempFile, mapper.readTree(invalidJson));

        List<String> errors = validator.validate(tempFile.getAbsolutePath());
        assertFalse(errors.isEmpty());
    }
}