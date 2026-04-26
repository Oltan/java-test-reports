package com.testreports.javalin;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.testreports.model.RunManifest;
import com.testreports.model.ScenarioResult;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class ManifestService {

    private final Path manifestsDir;
    private final ObjectMapper objectMapper;

    public ManifestService(String manifestsDirPath) {
        this.manifestsDir = Paths.get(manifestsDirPath);
        this.objectMapper = new ObjectMapper();
        this.objectMapper.registerModule(new JavaTimeModule());
    }

    public List<RunManifest> getAllRuns() {
        return loadManifests();
    }

    public Optional<RunManifest> getRun(String runId) {
        return loadManifests().stream()
                .filter(m -> m.getRunId().equals(runId))
                .findFirst();
    }

    public Optional<List<ScenarioResult>> getFailures(String runId) {
        return getRun(runId).map(m ->
                m.getScenarios().stream()
                        .filter(s -> "failed".equals(s.getStatus()))
                        .toList()
        );
    }

    private List<RunManifest> loadManifests() {
        if (!Files.isDirectory(manifestsDir)) {
            return new ArrayList<>();
        }

        List<RunManifest> manifests = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(manifestsDir, "*.json")) {
            for (Path file : stream) {
                try {
                    RunManifest manifest = objectMapper.readValue(file.toFile(), RunManifest.class);
                    manifests.add(manifest);
                } catch (IOException e) {
                    throw new RuntimeException("Failed to read manifest file: " + file, e);
                }
            }
        } catch (IOException e) {
            throw new RuntimeException("Failed to read manifests directory: " + manifestsDir, e);
        }

        manifests.sort(Comparator.comparing(RunManifest::getTimestamp).reversed());
        return manifests;
    }
}