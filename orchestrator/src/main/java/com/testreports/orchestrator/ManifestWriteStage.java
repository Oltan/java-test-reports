package com.testreports.orchestrator;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.testreports.model.AllureResultsParser;
import com.testreports.model.AttachmentInfo;
import com.testreports.model.ManifestWriter;
import com.testreports.model.RunManifest;
import com.testreports.model.ScenarioResult;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.logging.Logger;

public class ManifestWriteStage implements PipelineStage {

    private static final Logger LOGGER = Logger.getLogger(ManifestWriteStage.class.getName());

    private final ScenarioResultParser parser;
    private final AttachmentCopier copier;
    private final ManifestPersister persister;

    public ManifestWriteStage() {
        this(new DefaultScenarioResultParser(), new DefaultAttachmentCopier(), new DefaultManifestPersister());
    }

    /** Convenience constructor for tests that stub parser and persister. */
    public ManifestWriteStage(ScenarioResultParser parser, ManifestPersister persister) {
        this(parser, new DefaultAttachmentCopier(), persister);
    }

    public ManifestWriteStage(ScenarioResultParser parser, AttachmentCopier copier, ManifestPersister persister) {
        this.parser = Objects.requireNonNull(parser, "parser must not be null");
        this.copier = Objects.requireNonNull(copier, "copier must not be null");
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
        Path resultsDir  = ctx.getConfig().path(PipelineConfig.ALLURE_RESULTS_DIR);
        Path manifestDir = ctx.getConfig().path(PipelineConfig.MANIFEST_DIR);

        List<ScenarioResult> scenarios = parser.parse(resultsDir);
        scenarios = copier.copy(scenarios, resultsDir, manifestDir, ctx.getRunId());
        RunManifest manifest = persister.write(scenarios, manifestDir, ctx.getRunId());
        ctx.setManifest(manifest);
    }

    // ── Functional interfaces ──────────────────────────────────────────────

    @FunctionalInterface
    public interface ScenarioResultParser {
        List<ScenarioResult> parse(Path resultsDir) throws Exception;
    }

    @FunctionalInterface
    public interface AttachmentCopier {
        /**
         * Copies attachment binaries from {@code resultsDir} to
         * {@code manifestDir/attachments/<runId>/} and rewrites the path field
         * in each {@link AttachmentInfo} to the new relative location so that
         * FastAPI can serve them at {@code /reports/attachments/<runId>/<file>}.
         */
        List<ScenarioResult> copy(
                List<ScenarioResult> scenarios,
                Path resultsDir,
                Path manifestDir,
                String runId) throws Exception;
    }

    @FunctionalInterface
    public interface ManifestPersister {
        RunManifest write(List<ScenarioResult> scenarios, Path outputDir, String runId) throws Exception;
    }

    // ── Default implementations ────────────────────────────────────────────

    private static class DefaultScenarioResultParser implements ScenarioResultParser {
        @Override
        public List<ScenarioResult> parse(Path resultsDir) throws Exception {
            return new AllureResultsParser(resultsDir).parse();
        }
    }

    private static class DefaultAttachmentCopier implements AttachmentCopier {
        @Override
        public List<ScenarioResult> copy(
                List<ScenarioResult> scenarios,
                Path resultsDir,
                Path manifestDir,
                String runId) throws Exception {

            Path attachmentsDir = manifestDir.resolve("attachments").resolve(runId);
            boolean dirCreated = false;

            for (ScenarioResult scenario : scenarios) {
                if (scenario.getAttachments() == null || scenario.getAttachments().isEmpty()) {
                    continue;
                }

                List<AttachmentInfo> updated = new ArrayList<>();
                for (AttachmentInfo att : scenario.getAttachments()) {
                    Path source = resultsDir.resolve(att.getPath());
                    if (Files.exists(source)) {
                        if (!dirCreated) {
                            Files.createDirectories(attachmentsDir);
                            dirCreated = true;
                        }
                        Files.copy(source, attachmentsDir.resolve(att.getPath()), StandardCopyOption.REPLACE_EXISTING);
                        String newPath = "attachments/" + runId + "/" + att.getPath();
                        updated.add(new AttachmentInfo(att.getName(), att.getType(), newPath));
                        LOGGER.fine("Copied attachment: " + att.getPath() + " → " + newPath);
                    } else {
                        LOGGER.warning("Attachment not found, skipping: " + source);
                        updated.add(att);
                    }
                }
                scenario.setAttachments(updated);
            }
            return scenarios;
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
