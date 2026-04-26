package com.testreports.model;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public class AllureResultsParser {

    private static final Pattern DOORS_TAG_PATTERN = Pattern.compile("@DOORS-(\\d+)", Pattern.CASE_INSENSITIVE);

    private final Path resultsDir;
    private final ObjectMapper mapper;

    public AllureResultsParser(Path resultsDir) {
        this.resultsDir = resultsDir;
        this.mapper = new ObjectMapper();
    }

    public List<ScenarioResult> parse() throws IOException {
        List<ScenarioResult> scenarios = new ArrayList<>();

        if (!Files.exists(resultsDir) || !Files.isDirectory(resultsDir)) {
            throw new IOException("Results directory does not exist: " + resultsDir);
        }

        try (Stream<Path> paths = Files.list(resultsDir)) {
            paths.filter(path -> path.getFileName().toString().endsWith("-result.json"))
                 .forEach(file -> {
                     try {
                         ScenarioResult scenario = parseSingleFile(file);
                         if (scenario != null) {
                             scenarios.add(scenario);
                         }
                     } catch (IOException e) {
                     }
                 });
        }

        return scenarios;
    }

    private ScenarioResult parseSingleFile(Path file) throws IOException {
        JsonNode root = mapper.readTree(file.toFile());

        String name = root.has("name") ? root.get("name").asText() : "Unknown Scenario";
        String status = mapStatus(root.has("status") ? root.get("status").asText() : "unknown");
        long start = root.has("start") ? root.get("start").asLong() : 0;
        long stop = root.has("stop") ? root.get("stop").asLong() : 0;
        String duration = formatDuration(stop - start);

        List<StepResult> steps = parseSteps(root);
        List<AttachmentInfo> attachments = parseAttachments(root);
        List<String> tags = parseTags(root);

        String doorsAbsNumber = extractDoorsNumber(tags);

        String id = file.getFileName().toString().replace("-result.json", "");

        return new ScenarioResult(id, name, status, duration, doorsAbsNumber, tags, steps, attachments);
    }

    private String mapStatus(String allureStatus) {
        return switch (allureStatus.toLowerCase()) {
            case "passed" -> "passed";
            case "failed" -> "failed";
            case "broken" -> "failed";
            case "skipped" -> "skipped";
            case "canceled" -> "skipped";
            case "pending" -> "skipped";
            default -> "unknown";
        };
    }

    private List<StepResult> parseSteps(JsonNode root) {
        List<StepResult> steps = new ArrayList<>();
        if (!root.has("steps") || !root.get("steps").isArray()) {
            return steps;
        }

        ArrayNode stepsArray = (ArrayNode) root.get("steps");
        for (JsonNode stepNode : stepsArray) {
            String stepName = stepNode.has("name") ? stepNode.get("name").asText() : "";
            String stepStatus = mapStatus(stepNode.has("status") ? stepNode.get("status").asText() : "unknown");

            String errorMessage = null;
            if (stepNode.has("message") && !stepNode.get("message").isNull()) {
                errorMessage = stepNode.get("message").asText();
            } else if (stepNode.has("statusDetails") && stepNode.get("statusDetails").has("message")) {
                errorMessage = stepNode.get("statusDetails").get("message").asText();
            }

            steps.add(new StepResult(stepName, stepStatus, errorMessage));
        }

        return steps;
    }

    private List<AttachmentInfo> parseAttachments(JsonNode root) {
        List<AttachmentInfo> attachments = new ArrayList<>();
        if (!root.has("attachments") || !root.get("attachments").isArray()) {
            return attachments;
        }

        ArrayNode attachmentsArray = (ArrayNode) root.get("attachments");
        for (JsonNode attachmentNode : attachmentsArray) {
            String name = attachmentNode.has("name") ? attachmentNode.get("name").asText() : "";
            String type = attachmentNode.has("type") ? attachmentNode.get("type").asText() : "";
            String path = attachmentNode.has("source") ? attachmentNode.get("source").asText() : "";

            attachments.add(new AttachmentInfo(name, type, path));
        }

        return attachments;
    }

    private List<String> parseTags(JsonNode root) {
        Set<String> tags = new HashSet<>();

        if (root.has("labels") && root.get("labels").isArray()) {
            ArrayNode labels = (ArrayNode) root.get("labels");
            for (JsonNode label : labels) {
                if (label.has("name") && "tag".equals(label.get("name").asText()) && label.has("value")) {
                    tags.add(label.get("value").asText());
                }
            }
        }

        return new ArrayList<>(tags);
    }

    private String extractDoorsNumber(List<String> tags) {
        for (String tag : tags) {
            Matcher matcher = DOORS_TAG_PATTERN.matcher(tag);
            if (matcher.find()) {
                return matcher.group(1);
            }
        }
        return null;
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
}