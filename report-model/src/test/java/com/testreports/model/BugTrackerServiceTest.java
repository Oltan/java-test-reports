package com.testreports.model;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class BugTrackerServiceTest {

    @TempDir
    Path tempDir;

    @Test
    void testRegisterNewMappingThenGetMapping() throws IOException {
        Path storageFile = tempDir.resolve("bug-tracker.json");
        BugTrackerService service = new BugTrackerService(storageFile);

        service.registerMapping("DOORS-12345", "JIRA-100", "Login Scenario", "run-001");

        Optional<BugMapping> result = service.getMapping("DOORS-12345");

        assertTrue(result.isPresent());
        BugMapping mapping = result.get();
        assertEquals("DOORS-12345", mapping.getDoorsNumber());
        assertEquals("JIRA-100", mapping.getJiraKey());
        assertEquals("OPEN", mapping.getStatus());
        assertEquals("Login Scenario", mapping.getScenarioName());
        assertEquals(1, mapping.getRunIds().size());
        assertTrue(mapping.getRunIds().contains("run-001"));
        assertNotNull(mapping.getFirstSeen());
        assertNotNull(mapping.getLastSeen());
    }

    @Test
    void testRegisterSameDoorsNumberOverwrites() throws IOException {
        Path storageFile = tempDir.resolve("bug-tracker.json");
        BugTrackerService service = new BugTrackerService(storageFile);

        service.registerMapping("DOORS-12345", "JIRA-100", "Scenario One", "run-001");
        service.registerMapping("DOORS-12345", "JIRA-101", "Scenario Two", "run-002");

        Optional<BugMapping> result = service.getMapping("DOORS-12345");

        assertTrue(result.isPresent());
        BugMapping mapping = result.get();
        assertEquals("JIRA-101", mapping.getJiraKey());
        assertEquals("Scenario Two", mapping.getScenarioName());
        assertEquals(2, mapping.getRunIds().size());
        assertTrue(mapping.getRunIds().contains("run-001"));
        assertTrue(mapping.getRunIds().contains("run-002"));
    }

    @Test
    void testGetMappingForNonExistentReturnsEmpty() throws IOException {
        Path storageFile = tempDir.resolve("bug-tracker.json");
        BugTrackerService service = new BugTrackerService(storageFile);

        Optional<BugMapping> result = service.getMapping("NON-EXISTENT");

        assertFalse(result.isPresent());
        assertTrue(result.isEmpty());
    }

    @Test
    void testUpdateStatusChangesStatus() throws IOException {
        Path storageFile = tempDir.resolve("bug-tracker.json");
        BugTrackerService service = new BugTrackerService(storageFile);

        service.registerMapping("DOORS-12345", "JIRA-100", "Login Scenario", "run-001");
        service.updateStatus("DOORS-12345", "IN_PROGRESS");

        Optional<BugMapping> result = service.getMapping("DOORS-12345");

        assertTrue(result.isPresent());
        assertEquals("IN_PROGRESS", result.get().getStatus());
    }

    @Test
    void testGetAllMappingsReturnsAll() throws IOException {
        Path storageFile = tempDir.resolve("bug-tracker.json");
        BugTrackerService service = new BugTrackerService(storageFile);

        service.registerMapping("DOORS-11111", "JIRA-100", "Scenario A", "run-001");
        service.registerMapping("DOORS-22222", "JIRA-200", "Scenario B", "run-002");
        service.registerMapping("DOORS-33333", "JIRA-300", "Scenario C", "run-003");

        List<BugMapping> allMappings = service.getAllMappings();

        assertEquals(3, allMappings.size());
    }

    @Test
    void testCorruptJsonFileStartsFresh() throws IOException {
        Path storageFile = tempDir.resolve("bug-tracker.json");
        Files.writeString(storageFile, "{ invalid json }");

        BugTrackerService service = new BugTrackerService(storageFile);

        Optional<BugMapping> result = service.getMapping("DOORS-12345");
        assertFalse(result.isPresent());

        service.registerMapping("DOORS-12345", "JIRA-100", "New Scenario", "run-001");

        Optional<BugMapping> newResult = service.getMapping("DOORS-12345");
        assertTrue(newResult.isPresent());
        assertEquals("DOORS-12345", newResult.get().getDoorsNumber());
    }

    @Test
    void testRegisterMappingCreatesFileIfNotExists() throws IOException {
        Path storageFile = tempDir.resolve("bug-tracker.json");
        assertFalse(Files.exists(storageFile));

        BugTrackerService service = new BugTrackerService(storageFile);
        service.registerMapping("DOORS-12345", "JIRA-100", "Test", "run-001");

        assertTrue(Files.exists(storageFile));
        String content = Files.readString(storageFile);
        assertTrue(content.contains("\"version\":\"1.0\""));
        assertTrue(content.contains("DOORS-12345"));
    }
}