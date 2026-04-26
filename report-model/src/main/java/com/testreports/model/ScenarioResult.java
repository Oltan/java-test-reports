package com.testreports.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class ScenarioResult {

    @JsonProperty("id")
    private String id;

    @JsonProperty("name")
    private String name;

    @JsonProperty("status")
    private String status;

    @JsonProperty("duration")
    private String duration;

    @JsonProperty("doorsAbsNumber")
    private String doorsAbsNumber;

    @JsonProperty("tags")
    private List<String> tags;

    @JsonProperty("steps")
    private List<StepResult> steps;

    @JsonProperty("attachments")
    private List<AttachmentInfo> attachments;

    public ScenarioResult() {
    }

    public ScenarioResult(String id, String name, String status, String duration,
                         String doorsAbsNumber, List<String> tags,
                         List<StepResult> steps, List<AttachmentInfo> attachments) {
        this.id = id;
        this.name = name;
        this.status = status;
        this.duration = duration;
        this.doorsAbsNumber = doorsAbsNumber;
        this.tags = tags;
        this.steps = steps;
        this.attachments = attachments;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getDuration() {
        return duration;
    }

    public void setDuration(String duration) {
        this.duration = duration;
    }

    public String getDoorsAbsNumber() {
        return doorsAbsNumber;
    }

    public void setDoorsAbsNumber(String doorsAbsNumber) {
        this.doorsAbsNumber = doorsAbsNumber;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<StepResult> getSteps() {
        return steps;
    }

    public void setSteps(List<StepResult> steps) {
        this.steps = steps;
    }

    public List<AttachmentInfo> getAttachments() {
        return attachments;
    }

    public void setAttachments(List<AttachmentInfo> attachments) {
        this.attachments = attachments;
    }
}