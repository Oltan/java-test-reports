package com.testreports.model;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class ManifestValidator {

    private final ObjectMapper objectMapper;

    public ManifestValidator(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public ManifestValidator() {
        this.objectMapper = new ObjectMapper();
        this.objectMapper.findAndRegisterModules();
    }

    public List<String> validate(String jsonFilePath) throws IOException {
        List<String> errors = new ArrayList<>();
        File file = new File(jsonFilePath);

        if (!file.exists()) {
            errors.add("File not found: " + jsonFilePath);
            return errors;
        }

        JsonNode root = objectMapper.readTree(file);

        // Validate required top-level fields
        validateField(root, "runId", errors, true);
        validateField(root, "timestamp", errors, true);
        validateField(root, "totalScenarios", errors, true);
        validateField(root, "passed", errors, true);
        validateField(root, "failed", errors, true);
        validateField(root, "skipped", errors, true);
        validateField(root, "duration", errors, true);
        validateField(root, "scenarios", errors, true);

        // Validate scenarios array
        JsonNode scenarios = root.get("scenarios");
        if (scenarios != null && scenarios.isArray()) {
            if (scenarios.size() != root.get("totalScenarios").asInt()) {
                errors.add("Scenario count mismatch: totalScenarios=" + root.get("totalScenarios").asInt() +
                           " but scenarios array has " + scenarios.size() + " elements");
            }

            for (int i = 0; i < scenarios.size(); i++) {
                JsonNode scenario = scenarios.get(i);
                validateScenario(scenario, i, errors);
            }
        } else if (scenarios == null) {
            errors.add("'scenarios' field is missing or not an array");
        }

        // Validate totals consistency
        int passed = root.has("passed") ? root.get("passed").asInt() : 0;
        int failed = root.has("failed") ? root.get("failed").asInt() : 0;
        int skipped = root.has("skipped") ? root.get("skipped").asInt() : 0;
        int total = root.has("totalScenarios") ? root.get("totalScenarios").asInt() : 0;

        if (passed + failed + skipped != total) {
            errors.add("Sum of passed (" + passed + ") + failed (" + failed + ") + skipped (" + skipped +
                       ") = " + (passed + failed + skipped) + " does not equal totalScenarios (" + total + ")");
        }

        return errors;
    }

    private void validateScenario(JsonNode scenario, int index, List<String> errors) {
        String prefix = "scenarios[" + index + "]";

        validateField(scenario, "id", errors, true, prefix);
        validateField(scenario, "name", errors, true, prefix);
        validateField(scenario, "status", errors, true, prefix);
        validateField(scenario, "duration", errors, true, prefix);

        // Validate status values
        String status = scenario.has("status") ? scenario.get("status").asText() : null;
        if (status != null && !List.of("passed", "failed", "skipped").contains(status)) {
            errors.add(prefix + ".status must be one of: passed, failed, skipped, got: " + status);
        }

        // Validate optional doorsAbsNumber (can be null or string)
        // Validate optional tags array
        JsonNode tags = scenario.get("tags");
        if (tags != null && !tags.isArray()) {
            errors.add(prefix + ".tags must be an array");
        }

        // Validate steps array
        JsonNode steps = scenario.get("steps");
        if (steps != null && steps.isArray()) {
            for (int j = 0; j < steps.size(); j++) {
                JsonNode step = steps.get(j);
                String stepPrefix = prefix + ".steps[" + j + "]";
                validateField(step, "name", errors, true, stepPrefix);
                validateField(step, "status", errors, true, stepPrefix);

                String stepStatus = step.has("status") ? step.get("status").asText() : null;
                if (stepStatus != null && !List.of("passed", "failed", "skipped").contains(stepStatus)) {
                    errors.add(stepPrefix + ".status must be one of: passed, failed, skipped, got: " + stepStatus);
                }
            }
        }

        // Validate attachments array
        JsonNode attachments = scenario.get("attachments");
        if (attachments != null && attachments.isArray()) {
            for (int j = 0; j < attachments.size(); j++) {
                JsonNode attachment = attachments.get(j);
                String attachPrefix = prefix + ".attachments[" + j + "]";
                validateField(attachment, "name", errors, true, attachPrefix);
                validateField(attachment, "type", errors, true, attachPrefix);
                validateField(attachment, "path", errors, true, attachPrefix);

                String type = attachment.has("type") ? attachment.get("type").asText() : null;
                if (type != null && !List.of("image/png", "video/mp4", "text/plain").contains(type)) {
                    errors.add(attachPrefix + ".type must be one of: image/png, video/mp4, text/plain, got: " + type);
                }
            }
        }
    }

    private void validateField(JsonNode node, String fieldName, List<String> errors, boolean required) {
        validateField(node, fieldName, errors, required, "");
    }

    private void validateField(JsonNode node, String fieldName, List<String> errors, boolean required, String prefix) {
        String path = prefix.isEmpty() ? fieldName : prefix + "." + fieldName;

        if (!node.has(fieldName) || node.get(fieldName).isNull()) {
            if (required) {
                errors.add("Missing required field: " + path);
            }
        }
    }

    public boolean isValid(String jsonFilePath) throws IOException {
        return validate(jsonFilePath).isEmpty();
    }
}