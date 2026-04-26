package com.testreports.orchestrator;

import com.testreports.model.RunManifest;

import java.security.SecureRandom;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;
import java.util.Objects;

public class RunContext {
    private static final DateTimeFormatter RUN_ID_TIMESTAMP = DateTimeFormatter
            .ofPattern("yyyyMMdd-HHmmss")
            .withZone(ZoneOffset.UTC);
    private static final SecureRandom RANDOM = new SecureRandom();

    private String runId;
    private RunManifest manifest;
    private final PipelineConfig config;

    public RunContext(String runId, RunManifest manifest, PipelineConfig config) {
        this.runId = normalizeRunId(runId);
        this.manifest = manifest;
        this.config = Objects.requireNonNullElseGet(config, PipelineConfig::defaults);
    }

    public static RunContext auto(PipelineConfig config) {
        return new RunContext("auto", null, config);
    }

    public String getRunId() {
        return runId;
    }

    public void setRunId(String runId) {
        this.runId = normalizeRunId(runId);
    }

    public RunManifest getManifest() {
        return manifest;
    }

    public void setManifest(RunManifest manifest) {
        this.manifest = manifest;
        if (manifest != null && hasText(manifest.getRunId())) {
            this.runId = manifest.getRunId();
        }
    }

    public PipelineConfig getConfig() {
        return config;
    }

    public static String generateRunId() {
        byte[] bytes = new byte[3];
        RANDOM.nextBytes(bytes);
        return RUN_ID_TIMESTAMP.format(Instant.now()) + "-" + HexFormat.of().formatHex(bytes);
    }

    private static String normalizeRunId(String candidate) {
        if (!hasText(candidate) || "auto".equalsIgnoreCase(candidate.trim())) {
            return generateRunId();
        }
        return candidate.trim();
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
