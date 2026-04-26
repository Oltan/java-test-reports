package com.testreports.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ManifestWriterTest {

    private final ObjectMapper mapper;

    public ManifestWriterTest() {
        this.mapper = new ObjectMapper();
        this.mapper.registerModule(new JavaTimeModule());
        this.mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }

    @Test
    void testWriteAndReadManifest(@TempDir Path tempDir) throws IOException {
        AllureResultsParser parser = new AllureResultsParser(Path.of("src/test/resources/allure-results"));
        List<ScenarioResult> scenarios = parser.parse();

        ManifestWriter writer = new ManifestWriter(tempDir);
        ManifestWriter.RunMetadata metadata = new ManifestWriter.RunMetadata(Instant.now(), null);

        String runId = writer.write(scenarios, metadata);

        assertNotNull(runId);
        assertTrue(runId.matches("\\d{8}-\\d{6}-[0-9a-f]{6}"));

        Path manifestPath = tempDir.resolve(runId + ".json");
        assertTrue(Files.exists(manifestPath));

        RunManifest manifest = mapper.readValue(manifestPath.toFile(), RunManifest.class);

        assertEquals(runId, manifest.getRunId());
        assertEquals(3, manifest.getTotalScenarios());
        assertEquals(1, manifest.getPassed());
        assertEquals(1, manifest.getFailed());
        assertEquals(1, manifest.getSkipped());
        assertNotNull(manifest.getTimestamp());
        assertNotNull(manifest.getDuration());
    }

    @Test
    void testManifestContainsAllScenarios(@TempDir Path tempDir) throws IOException {
        AllureResultsParser parser = new AllureResultsParser(Path.of("src/test/resources/allure-results"));
        List<ScenarioResult> scenarios = parser.parse();

        ManifestWriter writer = new ManifestWriter(tempDir);
        String runId = writer.write(scenarios, null);

        Path manifestPath = tempDir.resolve(runId + ".json");
        RunManifest manifest = mapper.readValue(manifestPath.toFile(), RunManifest.class);

        assertEquals(3, manifest.getScenarios().size());

        boolean hasFailed = manifest.getScenarios().stream().anyMatch(s -> "failed".equals(s.getStatus()));
        boolean hasPassed = manifest.getScenarios().stream().anyMatch(s -> "passed".equals(s.getStatus()));
        boolean hasSkipped = manifest.getScenarios().stream().anyMatch(s -> "skipped".equals(s.getStatus()));

        assertTrue(hasFailed);
        assertTrue(hasPassed);
        assertTrue(hasSkipped);
    }

    @Test
    void testManifestScenarioHasDoorsNumber(@TempDir Path tempDir) throws IOException {
        AllureResultsParser parser = new AllureResultsParser(Path.of("src/test/resources/allure-results"));
        List<ScenarioResult> scenarios = parser.parse();

        ManifestWriter writer = new ManifestWriter(tempDir);
        String runId = writer.write(scenarios, null);

        Path manifestPath = tempDir.resolve(runId + ".json");
        RunManifest manifest = mapper.readValue(manifestPath.toFile(), RunManifest.class);

        ScenarioResult doorsScenario = manifest.getScenarios().stream()
            .filter(s -> s.getDoorsAbsNumber() != null)
            .findFirst()
            .orElseThrow();

        assertEquals("12345", doorsScenario.getDoorsAbsNumber());
    }

    @Test
    void testManifestScenarioHasCorrectSteps(@TempDir Path tempDir) throws IOException {
        AllureResultsParser parser = new AllureResultsParser(Path.of("src/test/resources/allure-results"));
        List<ScenarioResult> scenarios = parser.parse();

        ManifestWriter writer = new ManifestWriter(tempDir);
        String runId = writer.write(scenarios, null);

        Path manifestPath = tempDir.resolve(runId + ".json");
        RunManifest manifest = mapper.readValue(manifestPath.toFile(), RunManifest.class);

        ScenarioResult failedScenario = manifest.getScenarios().stream()
            .filter(s -> "failed".equals(s.getStatus()))
            .findFirst()
            .orElseThrow();

        assertEquals(4, failedScenario.getSteps().size());
        assertEquals("Beklenen hata mesajı gösterilmedi", failedScenario.getSteps().get(3).getErrorMessage());
    }

    @Test
    void testRunIdFormat() throws IOException {
        Path tempDir = Files.createTempDirectory("manifest-test");
        ManifestWriter writer = new ManifestWriter(tempDir);

        String runId1 = writer.write(List.of(), null);
        String runId2 = writer.write(List.of(), null);

        assertTrue(runId1.matches("\\d{8}-\\d{6}-[0-9a-f]{6}"));
        assertTrue(runId2.matches("\\d{8}-\\d{6}-[0-9a-f]{6}"));
        assertNotEquals(runId1, runId2);
    }
}