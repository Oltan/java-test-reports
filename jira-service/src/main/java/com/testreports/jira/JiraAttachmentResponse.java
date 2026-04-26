package com.testreports.jira;

/**
 * DTO for Jira attachment response.
 */
public class JiraAttachmentResponse {

    private String id;
    private String filename;
    private String mimeType;
    private String self;

    public JiraAttachmentResponse() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getFilename() {
        return filename;
    }

    public void setFilename(String filename) {
        this.filename = filename;
    }

    public String getMimeType() {
        return mimeType;
    }

    public void setMimeType(String mimeType) {
        this.mimeType = mimeType;
    }

    public String getSelf() {
        return self;
    }

    public void setSelf(String self) {
        this.self = self;
    }
}