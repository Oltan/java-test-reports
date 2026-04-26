package com.testreports.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class BugTrackerService {

    private final Path storageFile;
    private final ObjectMapper objectMapper;
    private final Object lock = new Object();

    public BugTrackerService(Path storageFile) {
        this.storageFile = storageFile;
        this.objectMapper = new ObjectMapper();
        this.objectMapper.registerModule(new JavaTimeModule());
        this.objectMapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }

    public Optional<BugMapping> getMapping(String doorsNumber) {
        synchronized (lock) {
            BugTrackerData data = loadData();
            BugMapping mapping = data.mappings.get(doorsNumber);
            return Optional.ofNullable(mapping);
        }
    }

    public void registerMapping(String doorsNumber, String jiraKey, String scenarioName, String runId) {
        synchronized (lock) {
            BugTrackerData data = loadData();
            Instant now = Instant.now();

            BugMapping mapping = data.mappings.get(doorsNumber);
            if (mapping == null) {
                mapping = new BugMapping();
                mapping.setDoorsNumber(doorsNumber);
                mapping.setJiraKey(jiraKey);
                mapping.setStatus("OPEN");
                mapping.setFirstSeen(now);
                mapping.setScenarioName(scenarioName);
                mapping.setRunIds(new ArrayList<>());
                data.mappings.put(doorsNumber, mapping);
            } else {
                mapping.setJiraKey(jiraKey);
                mapping.setScenarioName(scenarioName);
            }

            mapping.addRunId(runId);
            mapping.setLastSeen(now);
            saveData(data);
        }
    }

    public List<BugMapping> getAllMappings() {
        synchronized (lock) {
            BugTrackerData data = loadData();
            return new ArrayList<>(data.mappings.values());
        }
    }

    public void updateStatus(String doorsNumber, String newStatus) {
        synchronized (lock) {
            BugTrackerData data = loadData();
            BugMapping mapping = data.mappings.get(doorsNumber);
            if (mapping != null) {
                mapping.setStatus(newStatus);
                if ("CLOSED".equals(newStatus)) {
                    mapping.setLastSeen(Instant.now());
                }
                saveData(data);
            }
        }
    }

    private BugTrackerData loadData() {
        if (!Files.exists(storageFile)) {
            return new BugTrackerData();
        }
        try {
            String json = Files.readString(storageFile);
            return objectMapper.readValue(json, BugTrackerData.class);
        } catch (IOException e) {
            return new BugTrackerData();
        }
    }

    private void saveData(BugTrackerData data) {
        try {
            String json = objectMapper.writeValueAsString(data);
            Files.writeString(storageFile, json);
        } catch (IOException e) {
            throw new RuntimeException("Failed to save bug tracker data", e);
        }
    }

    public static class BugTrackerData {
        @JsonProperty("version")
        private String version = "1.0";

        @JsonProperty("mappings")
        private Map<String, BugMapping> mappings = new HashMap<>();
    }
}