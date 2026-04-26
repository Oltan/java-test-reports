package com.testreports.jira;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Jira REST API v2 client for Jira Data Center / Server.
 * Uses PAT Basic Authentication and wiki-renderer format.
 */
public class JiraClient {

    private final String baseUrl;
    private final String patToken;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    public JiraClient(String baseUrl, String patToken) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.patToken = patToken;
        this.objectMapper = new ObjectMapper();
        this.httpClient = HttpClient.newBuilder()
                .authenticator(new BasicAuthenticator("ignored", patToken))
                .build();
    }

    /**
     * Creates a new Jira issue.
     */
    public JiraIssueResponse createIssue(JiraIssueRequest request) throws Exception {
        String json = objectMapper.writeValueAsString(request);

        HttpRequest httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/rest/api/2/issue"))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        HttpResponse<String> response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 201) {
            throw new JiraApiException("Failed to create issue: " + response.statusCode() + " - " + response.body());
        }

        return objectMapper.readValue(response.body(), JiraIssueResponse.class);
    }

    /**
     * Uploads an attachment to an existing issue.
     */
    public List<JiraAttachmentResponse> attachFile(String issueKey, Path file) throws Exception {
        String fileName = file.getFileName().toString();
        byte[] fileContent = java.nio.file.Files.readAllBytes(file);

        String boundary = "Boundary-" + System.currentTimeMillis();
        String CRLF = "\r\n";

        StringBuilder body = new StringBuilder();
        body.append("--").append(boundary).append(CRLF);
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"").append(fileName).append("\"").append(CRLF);
        body.append("Content-Type: application/octet-stream").append(CRLF);
        body.append(CRLF);
        body.append(new String(fileContent)).append(CRLF);
        body.append("--").append(boundary).append("--").append(CRLF);

        HttpRequest httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/rest/api/2/issue/" + issueKey + "/attachments"))
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .header("X-Atlassian-Token", "no-check")
                .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
                .build();

        HttpResponse<String> response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new JiraApiException("Failed to attach file: " + response.statusCode() + " - " + response.body());
        }

        return objectMapper.readValue(response.body(), new TypeReference<List<JiraAttachmentResponse>>() {});
    }

    /**
     * Gets the current authenticated user's information.
     */
    public JiraUserInfo getMyself() throws Exception {
        HttpRequest httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/rest/api/2/myself"))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new JiraApiException("Failed to get myself: " + response.statusCode() + " - " + response.body());
        }

        return objectMapper.readValue(response.body(), JiraUserInfo.class);
    }

    private static class BasicAuthenticator extends java.net.Authenticator {
        private final String password;

        BasicAuthenticator(String username, String password) {
            this.password = password;
        }

        @Override
        protected java.net.PasswordAuthentication getPasswordAuthentication() {
            String encoded = Base64.getEncoder().encodeToString(("ignored:" + password).getBytes());
            return new java.net.PasswordAuthentication("ignored", encoded.toCharArray());
        }
    }
}