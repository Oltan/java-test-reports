package com.testreports.orchestrator;

import java.nio.file.Path;
import java.util.Collections;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Properties;

public class PipelineConfig {
    public static final String ALLURE_RESULTS_DIR = "allure.results.dir";
    public static final String ALLURE_REPORT_DIR = "allure.report.dir";
    public static final String MANIFEST_DIR = "manifest.dir";
    public static final String WEB_DEPLOY_DIR = "web.deploy.dir";
    public static final String REPORT_BASE_URL = "report.base.url";
    public static final String EMAIL_RECIPIENT = "email.recipient";
    public static final String SMTP_HOST = "smtp.host";
    public static final String SMTP_PORT = "smtp.port";
    public static final String SMTP_USERNAME = "smtp.username";
    public static final String SMTP_PASSWORD = "smtp.password";
    public static final String SMTP_FROM = "smtp.from";
    public static final String JIRA_BASE_URL = "jira.base.url";
    public static final String JIRA_PAT = "jira.pat";
    public static final String JIRA_PROJECT = "jira.project";
    public static final String JIRA_ISSUE_TYPE = "jira.issue.type";
    public static final String DOORS_EXE = "doors.exe";

    private final Map<String, String> values;

    public PipelineConfig(Map<String, String> values) {
        Map<String, String> merged = new HashMap<>(defaultValues());
        if (values != null) {
            values.forEach((key, value) -> {
                if (key != null && value != null && !value.isBlank()) {
                    merged.put(key, value);
                }
            });
        }
        this.values = Collections.unmodifiableMap(merged);
    }

    public static PipelineConfig defaults() {
        return new PipelineConfig(Map.of());
    }

    public static PipelineConfig fromEnvironment(Map<String, String> environment, Properties properties) {
        Map<String, String> values = new HashMap<>();
        defaultValues().keySet().forEach(key -> {
            String propertyValue = properties == null ? null : properties.getProperty(key);
            String envValue = environment == null ? null : environment.get(toEnvKey(key));
            if (propertyValue != null && !propertyValue.isBlank()) {
                values.put(key, propertyValue);
            } else if (envValue != null && !envValue.isBlank()) {
                values.put(key, envValue);
            }
        });
        return new PipelineConfig(values);
    }

    public Optional<String> get(String key) {
        String value = values.get(key);
        return value == null || value.isBlank() ? Optional.empty() : Optional.of(value);
    }

    public String getOrDefault(String key, String defaultValue) {
        return get(key).orElse(defaultValue);
    }

    public Path path(String key) {
        return Path.of(getOrDefault(key, defaultValues().get(key)));
    }

    public int intValue(String key, int defaultValue) {
        return get(key).map(value -> {
            try {
                return Integer.parseInt(value);
            } catch (NumberFormatException e) {
                return defaultValue;
            }
        }).orElse(defaultValue);
    }

    public Map<String, String> asMap() {
        return values;
    }

    private static Map<String, String> defaultValues() {
        return Map.ofEntries(
                Map.entry(ALLURE_RESULTS_DIR, "target/allure-results"),
                Map.entry(ALLURE_REPORT_DIR, "target/allure-report"),
                Map.entry(MANIFEST_DIR, "manifests"),
                Map.entry(WEB_DEPLOY_DIR, "target/web-deploy"),
                Map.entry(REPORT_BASE_URL, ""),
                Map.entry(EMAIL_RECIPIENT, ""),
                Map.entry(SMTP_HOST, ""),
                Map.entry(SMTP_PORT, "587"),
                Map.entry(SMTP_USERNAME, ""),
                Map.entry(SMTP_PASSWORD, ""),
                Map.entry(SMTP_FROM, "reports@example.invalid"),
                Map.entry(JIRA_BASE_URL, ""),
                Map.entry(JIRA_PAT, ""),
                Map.entry(JIRA_PROJECT, ""),
                Map.entry(JIRA_ISSUE_TYPE, "Bug"),
                Map.entry(DOORS_EXE, "")
        );
    }

    private static String toEnvKey(String key) {
        return "ORCHESTRATOR_" + key.toUpperCase(Locale.ROOT).replace('.', '_');
    }
}
