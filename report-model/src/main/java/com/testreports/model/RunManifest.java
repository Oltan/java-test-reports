package com.testreports.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import java.util.List;

public class RunManifest {

    @JsonProperty("runId")
    private String runId;

    @JsonProperty("timestamp")
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd'T'HH:mm:ss'Z'", timezone = "UTC")
    private Instant timestamp;

    @JsonProperty("totalScenarios")
    private int totalScenarios;

    @JsonProperty("passed")
    private int passed;

    @JsonProperty("failed")
    private int failed;

    @JsonProperty("skipped")
    private int skipped;

    @JsonProperty("duration")
    private String duration;

    @JsonProperty("scenarios")
    private List<ScenarioResult> scenarios;

    public RunManifest() {
    }

    public RunManifest(String runId, Instant timestamp, int totalScenarios,
                       int passed, int failed, int skipped, String duration,
                       List<ScenarioResult> scenarios) {
        this.runId = runId;
        this.timestamp = timestamp;
        this.totalScenarios = totalScenarios;
        this.passed = passed;
        this.failed = failed;
        this.skipped = skipped;
        this.duration = duration;
        this.scenarios = scenarios;
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

    public String getDuration() {
        return duration;
    }

    public void setDuration(String duration) {
        this.duration = duration;
    }

    public List<ScenarioResult> getScenarios() {
        return scenarios;
    }

    public void setScenarios(List<ScenarioResult> scenarios) {
        this.scenarios = scenarios;
    }
}