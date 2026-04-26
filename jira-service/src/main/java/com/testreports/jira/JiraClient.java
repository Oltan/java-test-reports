package com.testreports.jira;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.util.Base64;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Jira REST API v2 client for Jira Data Center / Server.
 * Uses PAT Basic Authentication and wiki-renderer format.
 */
public class JiraClient {

    private static final int MAX_RETRIES = 3;
    private static final long[] RETRY_DELAYS = {1000, 2000, 4000};

    private final String baseUrl;
    private final String patToken;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final boolean dryRun;
    private final Set<String> createdIssueKeys;

    public JiraClient(String baseUrl, String patToken) {
        this(baseUrl, patToken, Boolean.getBoolean("jira.dry-run"));
    }

    public JiraClient(String baseUrl, String patToken, boolean dryRun) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.patToken = patToken;
        this.dryRun = dryRun;
        this.objectMapper = new ObjectMapper();
        this.createdIssueKeys = new HashSet<>();
        this.httpClient = HttpClient.newBuilder()
                .authenticator(new BasicAuthenticator("ignored", patToken))
                .build();
    }

    /**
     * Creates a new Jira issue.
     */
    public JiraIssueResponse createIssue(JiraIssueRequest request) throws Exception {
        if (dryRun) {
            System.err.println("[DRY-RUN] Would create issue: " + request.getFields().getSummary());
            return new JiraIssueResponse();
        }

        String json = objectMapper.writeValueAsString(request);

        HttpRequest httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/rest/api/2/issue"))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        HttpResponse<String> response = sendWithRetry(httpRequest);

        if (response.statusCode() != 201) {
            throw new JiraApiException("Failed to create issue: " + response.statusCode() + " - " + response.body());
        }

        return objectMapper.readValue(response.body(), JiraIssueResponse.class);
    }

    private HttpResponse<String> sendWithRetry(HttpRequest request) throws Exception {
        int attempt = 0;
        while (true) {
            try {
                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                int status = response.statusCode();

                if (response.statusCode() == 200 || response.statusCode() == 201) {
                    return response;
                }

                if (status == 429 || status >= 500) {
                    if (attempt < MAX_RETRIES - 1) {
                        long delay = RETRY_DELAYS[attempt];
                        System.err.println("[RETRY] Attempt " + (attempt + 1) + " failed with status " + status + ". Retrying in " + delay + "ms...");
                        Thread.sleep(delay);
                        attempt++;
                        continue;
                    }
                }

                return response;
            } catch (IOException e) {
                if (attempt < MAX_RETRIES - 1) {
                    long delay = RETRY_DELAYS[attempt];
                    System.err.println("[RETRY] Attempt " + (attempt + 1) + " failed with IOException: " + e.getMessage() + ". Retrying in " + delay + "ms...");
                    Thread.sleep(delay);
                    attempt++;
                    continue;
                }
                throw e;
            }
        }
    }

    /**
     * Creates a new Jira issue if no issue with the given dedupKey has been created in this session.
     * Returns the existing issue key if already created, otherwise creates and returns new issue key.
     */
    public String createIssueIfNew(String dedupKey, JiraIssueRequest request) throws Exception {
        if (createdIssueKeys.contains(dedupKey)) {
            return null;
        }

        JiraIssueResponse response = createIssue(request);
        createdIssueKeys.add(dedupKey);
        return response.getKey();
    }

    /**
     * Uploads an attachment to an existing issue.
     */
    public List<JiraAttachmentResponse> attachFile(String issueKey, Path file) throws Exception {
        if (dryRun) {
            System.err.println("[DRY-RUN] Would attach file to issue: " + issueKey);
            return List.of();
        }

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

        HttpResponse<String> response = sendWithRetry(httpRequest);

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