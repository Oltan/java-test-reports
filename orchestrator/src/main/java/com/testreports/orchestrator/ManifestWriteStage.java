package com.testreports.orchestrator;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.testreports.model.AllureResultsParser;
import com.testreports.model.ManifestWriter;
import com.testreports.model.RunManifest;
import com.testreports.model.ScenarioResult;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public class ManifestWriteStage implements PipelineStage {
    private final ScenarioResultParser parser;
    private final ManifestPersister persister;

    public ManifestWriteStage() {
        this(new DefaultScenarioResultParser(), new DefaultManifestPersister());
    }

    public ManifestWriteStage(ScenarioResultParser parser, ManifestPersister persister) {
        this.parser = Objects.requireNonNull(parser, "parser must not be null");
        this.persister = Objects.requireNonNull(persister, "persister must not be null");
    }

    @Override
    public String getName() {
        return "ManifestWrite";
    }

    @Override
    public boolean isCritical() {
        return true;
    }

    @Override
    public void execute(RunContext ctx) throws Exception {
        Path resultsDir = ctx.getConfig().path(PipelineConfig.ALLURE_RESULTS_DIR);
        Path manifestDir = ctx.getConfig().path(PipelineConfig.MANIFEST_DIR);
        List<ScenarioResult> scenarios = parser.parse(resultsDir);
        RunManifest manifest = persister.write(scenarios, manifestDir, ctx.getRunId());
        ctx.setManifest(manifest);
    }

    @FunctionalInterface
    public interface ScenarioResultParser {
        List<ScenarioResult> parse(Path resultsDir) throws Exception;
    }

    @FunctionalInterface
    public interface ManifestPersister {
        RunManifest write(List<ScenarioResult> scenarios, Path outputDir, String runId) throws Exception;
    }

    private static class DefaultScenarioResultParser implements ScenarioResultParser {
        @Override
        public List<ScenarioResult> parse(Path resultsDir) throws Exception {
            return new AllureResultsParser(resultsDir).parse();
        }
    }

    private static class DefaultManifestPersister implements ManifestPersister {
        private final ObjectMapper mapper;

        DefaultManifestPersister() {
            this.mapper = new ObjectMapper();
            this.mapper.registerModule(new JavaTimeModule());
            this.mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        }

        @Override
        public RunManifest write(List<ScenarioResult> scenarios, Path outputDir, String runId) throws Exception {
            ManifestWriter writer = new ManifestWriter(outputDir);
            String generatedRunId = writer.write(scenarios, new ManifestWriter.RunMetadata(Instant.now(), null));
            Path generatedPath = outputDir.resolve(generatedRunId + ".json");
            RunManifest manifest = mapper.readValue(generatedPath.toFile(), RunManifest.class);

            if (runId != null && !runId.isBlank() && !runId.equals(generatedRunId)) {
                manifest.setRunId(runId);
                Path requestedPath = outputDir.resolve(runId + ".json");
                Files.createDirectories(outputDir);
                mapper.writeValue(requestedPath.toFile(), manifest);
                Files.deleteIfExists(generatedPath);
            }
            return manifest;
        }
    }
}
