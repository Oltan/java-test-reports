package com.testreports.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BugMapping {

    @JsonProperty("doorsNumber")
    private String doorsNumber;

    @JsonProperty("jiraKey")
    private String jiraKey;

    @JsonProperty("status")
    private String status;

    @JsonProperty("firstSeen")
    private Instant firstSeen;

    @JsonProperty("lastSeen")
    private Instant lastSeen;

    @JsonProperty("scenarioName")
    private String scenarioName;

    @JsonProperty("runIds")
    private List<String> runIds;

    @JsonProperty("resolution")
    private String resolution;

    public BugMapping() {
        this.runIds = new ArrayList<>();
    }

    public BugMapping(String doorsNumber, String jiraKey, String status, Instant firstSeen,
                      Instant lastSeen, String scenarioName, List<String> runIds, String resolution) {
        this.doorsNumber = doorsNumber;
        this.jiraKey = jiraKey;
        this.status = status;
        this.firstSeen = firstSeen;
        this.lastSeen = lastSeen;
        this.scenarioName = scenarioName;
        this.runIds = runIds != null ? runIds : new ArrayList<>();
        this.resolution = resolution;
    }

    public String getDoorsNumber() {
        return doorsNumber;
    }

    public void setDoorsNumber(String doorsNumber) {
        this.doorsNumber = doorsNumber;
    }

    public String getJiraKey() {
        return jiraKey;
    }

    public void setJiraKey(String jiraKey) {
        this.jiraKey = jiraKey;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Instant getFirstSeen() {
        return firstSeen;
    }

    public void setFirstSeen(Instant firstSeen) {
        this.firstSeen = firstSeen;
    }

    public Instant getLastSeen() {
        return lastSeen;
    }

    public void setLastSeen(Instant lastSeen) {
        this.lastSeen = lastSeen;
    }

    public String getScenarioName() {
        return scenarioName;
    }

    public void setScenarioName(String scenarioName) {
        this.scenarioName = scenarioName;
    }

    public List<String> getRunIds() {
        return runIds;
    }

    public void setRunIds(List<String> runIds) {
        this.runIds = runIds;
    }

    public String getResolution() {
        return resolution;
    }

    public void setResolution(String resolution) {
        this.resolution = resolution;
    }

    public void addRunId(String runId) {
        if (this.runIds == null) {
            this.runIds = new ArrayList<>();
        }
        if (!this.runIds.contains(runId)) {
            this.runIds.add(runId);
        }
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        BugMapping that = (BugMapping) o;
        return Objects.equals(doorsNumber, that.doorsNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(doorsNumber);
    }
}