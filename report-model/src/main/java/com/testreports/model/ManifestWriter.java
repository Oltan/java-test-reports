package com.testreports.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.HexFormat;

public class ManifestWriter {

    private static final DateTimeFormatter DATE_FORMAT = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneOffset.UTC);
    private static final SecureRandom RANDOM = new SecureRandom();

    private final Path outputDir;
    private final ObjectMapper mapper;

    public ManifestWriter(Path outputDir) {
        this.outputDir = outputDir;
        this.mapper = new ObjectMapper();
        this.mapper.registerModule(new JavaTimeModule());
        this.mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }

    public String write(List<ScenarioResult> scenarios, RunMetadata metadata) throws IOException {
        String runId = generateRunId();

        int passed = 0;
        int failed = 0;
        int skipped = 0;
        long totalDuration = 0;

        for (ScenarioResult scenario : scenarios) {
            switch (scenario.getStatus().toLowerCase()) {
                case "passed" -> passed++;
                case "failed" -> failed++;
                default -> skipped++;
            }

            if (scenario.getDuration() != null) {
                totalDuration += parseDuration(scenario.getDuration());
            }
        }

        Instant timestamp = metadata != null && metadata.timestamp() != null
            ? metadata.timestamp()
            : Instant.now();

        String duration = formatDuration(totalDuration);

        RunManifest manifest = new RunManifest(
            runId,
            timestamp,
            scenarios.size(),
            passed,
            failed,
            skipped,
            duration,
            scenarios
        );

        if (!Files.exists(outputDir)) {
            Files.createDirectories(outputDir);
        }

        Path manifestPath = outputDir.resolve(runId + ".json");
        mapper.writeValue(manifestPath.toFile(), manifest);

        return runId;
    }

    private String generateRunId() {
        String timestamp = DATE_FORMAT.format(Instant.now());
        byte[] bytes = new byte[3];
        RANDOM.nextBytes(bytes);
        String hex = HexFormat.of().formatHex(bytes);
        return timestamp + "-" + hex;
    }

    private long parseDuration(String duration) {
        if (duration == null || duration.isEmpty()) {
            return 0;
        }

        if (duration.startsWith("PT")) {
            long totalMillis = 0;
            String remaining = duration.substring(2);

            int hoursIndex = remaining.indexOf('H');
            int minutesIndex = remaining.indexOf('M');
            int secondsIndex = remaining.indexOf('S');

            if (hoursIndex > 0) {
                totalMillis += Long.parseLong(remaining.substring(0, hoursIndex)) * 3600000L;
                remaining = remaining.substring(hoursIndex + 1);
            }
            if (minutesIndex > 0) {
                totalMillis += Long.parseLong(remaining.substring(0, minutesIndex)) * 60000L;
                remaining = remaining.substring(minutesIndex + 1);
            }
            if (secondsIndex > 0) {
                totalMillis += Long.parseLong(remaining.substring(0, secondsIndex)) * 1000L;
            }

            return totalMillis;
        }

        return 0;
    }

    private String formatDuration(long millis) {
        if (millis <= 0) {
            return "PT0S";
        }
        long seconds = millis / 1000;
        long minutes = seconds / 60;
        long hours = minutes / 60;

        StringBuilder sb = new StringBuilder("PT");
        if (hours > 0) {
            sb.append(hours).append("H");
        }
        if (minutes % 60 > 0) {
            sb.append(minutes % 60).append("M");
        }
        if (seconds % 60 > 0 || (hours == 0 && minutes == 0)) {
            sb.append(seconds % 60).append("S");
        }

        return sb.toString();
    }

    public record RunMetadata(Instant timestamp, Long durationMs) {}
}