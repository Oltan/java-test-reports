package com.testreports.jira;

/**
 * DTO for Jira issue creation request.
 * Uses wiki-renderer format (not ADF).
 */
public class JiraIssueRequest {

    private Fields fields;

    public JiraIssueRequest() {
    }

    public JiraIssueRequest(String project, String issuetype, String summary, String description) {
        this.fields = new Fields();
        this.fields.project = new Project();
        this.fields.project.key = project;
        this.fields.issuetype = new Issuetype();
        this.fields.issuetype.name = issuetype;
        this.fields.summary = summary;
        this.fields.description = description;
    }

    public Fields getFields() {
        return fields;
    }

    public void setFields(Fields fields) {
        this.fields = fields;
    }

    public static class Fields {
        private Project project;
        private Issuetype issuetype;
        private String summary;
        private String description;

        public Project getProject() {
            return project;
        }

        public void setProject(Project project) {
            this.project = project;
        }

        public Issuetype getIssuetype() {
            return issuetype;
        }

        public void setIssuetype(Issuetype issuetype) {
            this.issuetype = issuetype;
        }

        public String getSummary() {
            return summary;
        }

        public void setSummary(String summary) {
            this.summary = summary;
        }

        public String getDescription() {
            return description;
        }

        public void setDescription(String description) {
            this.description = description;
        }
    }

    public static class Project {
        public String key;
    }

    public static class Issuetype {
        public String name;
    }
}