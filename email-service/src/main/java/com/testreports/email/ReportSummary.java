package com.testreports.email;

import java.time.Instant;

public class ReportSummary {
    private String runId;
    private Instant timestamp;
    private int totalScenarios;
    private int passed;
    private int failed;
    private int skipped;
    private String reportUrl;

    public ReportSummary() {
    }

    public ReportSummary(String runId, Instant timestamp, int totalScenarios,
                         int passed, int failed, int skipped, String reportUrl) {
        this.runId = runId;
        this.timestamp = timestamp;
        this.totalScenarios = totalScenarios;
        this.passed = passed;
        this.failed = failed;
        this.skipped = skipped;
        this.reportUrl = reportUrl;
    }

    public String getRunId() {
        return runId;
    }

    public void setRunId(String runId) {
        this.runId = runId;
    }

    public Instant getTimestamp() {
        return timestamp;
    }

    public void setTimestamp(Instant timestamp) {
        this.timestamp = timestamp;
    }

    public int getTotalScenarios() {
        return totalScenarios;
    }

    public void setTotalScenarios(int totalScenarios) {
        this.totalScenarios = totalScenarios;
    }

    public int getPassed() {
        return passed;
    }

    public void setPassed(int passed) {
        this.passed = passed;
    }

    public int getFailed() {
        return failed;
    }

    public void setFailed(int failed) {
        this.failed = failed;
    }

    public int getSkipped() {
        return skipped;
    }

    public void setSkipped(int skipped) {
        this.skipped = skipped;
    }

    public String getReportUrl() {
        return reportUrl;
    }

    public void setReportUrl(String reportUrl) {
        this.reportUrl = reportUrl;
    }
}