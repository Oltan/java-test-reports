package com.testreports.orchestrator;

import com.testreports.jira.JiraClient;
import com.testreports.jira.JiraIssueRequest;
import com.testreports.model.RunManifest;
import com.testreports.model.ScenarioResult;

import java.util.Objects;
import java.util.logging.Logger;

public class JiraCreateStage implements PipelineStage {
    private static final Logger LOGGER = Logger.getLogger(JiraCreateStage.class.getName());

    private final JiraIssueCreator issueCreator;

    public JiraCreateStage() {
        this(null);
    }

    public JiraCreateStage(JiraIssueCreator issueCreator) {
        this.issueCreator = issueCreator;
    }

    @Override
    public String getName() {
        return "JiraCreate";
    }

    @Override
    public boolean isCritical() {
        return false;
    }

    @Override
    public void execute(RunContext ctx) throws Exception {
        RunManifest manifest = Objects.requireNonNull(ctx.getManifest(), "manifest must be available before Jira create");
        String project = ctx.getConfig().get(PipelineConfig.JIRA_PROJECT).orElse("");
        if (project.isBlank()) {
            LOGGER.info("No Jira project configured; skipping Jira creation");
            return;
        }
        JiraIssueCreator activeCreator = issueCreator == null ? createIssueCreator(ctx.getConfig()) : issueCreator;
        if (manifest.getScenarios() == null) {
            return;
        }
        for (ScenarioResult scenario : manifest.getScenarios()) {
            if (scenario != null && "failed".equalsIgnoreCase(scenario.getStatus())) {
                String dedupKey = manifest.getRunId() + ":" + scenario.getId();
                activeCreator.createIfNew(dedupKey, request(ctx, scenario));
            }
        }
    }

    private JiraIssueCreator createIssueCreator(PipelineConfig config) {
        String baseUrl = config.get(PipelineConfig.JIRA_BASE_URL)
                .orElseThrow(() -> new IllegalStateException("jira.base.url is required when jira.project is set"));
        String pat = config.get(PipelineConfig.JIRA_PAT)
                .orElseThrow(() -> new IllegalStateException("jira.pat is required when jira.project is set"));
        JiraClient client = new JiraClient(baseUrl, pat);
        return client::createIssueIfNew;
    }

    private JiraIssueRequest request(RunContext ctx, ScenarioResult scenario) {
        String project = ctx.getConfig().getOrDefault(PipelineConfig.JIRA_PROJECT, "");
        String issueType = ctx.getConfig().getOrDefault(PipelineConfig.JIRA_ISSUE_TYPE, "Bug");
        String summary = "Automated test failed: " + scenario.getName();
        String description = "Run: " + ctx.getRunId() + "\n"
                + "Scenario: " + scenario.getName() + "\n"
                + "Scenario ID: " + scenario.getId() + "\n"
                + "Status: " + scenario.getStatus();
        return new JiraIssueRequest(project, issueType, summary, description);
    }

    @FunctionalInterface
    public interface JiraIssueCreator {
        String createIfNew(String dedupKey, JiraIssueRequest request) throws Exception;
    }
}
