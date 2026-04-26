package com.testreports.jira;

import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.client.WireMock;

class JiraClientTest {

    private WireMockServer wireMockServer;
    private JiraClient jiraClient;

    @BeforeEach
    void setUp() {
        wireMockServer = new WireMockServer();
        wireMockServer.start();

        String baseUrl = "http://localhost:" + wireMockServer.port();
        jiraClient = new JiraClient(baseUrl, "test-pat-token");

        wireMockServer.stubFor(WireMock.post("/rest/api/2/issue")
                .willReturn(WireMock.aResponse()
                        .withStatus(201)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"id\": \"10001\", \"key\": \"TEST-123\", \"self\": \"http://localhost/rest/api/2/issue/10001\"}")));

        wireMockServer.stubFor(WireMock.get("/rest/api/2/myself")
                .willReturn(WireMock.aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"name\": \"test.user\", \"displayName\": \"Test User\", \"email\": \"test@example.com\", \"self\": \"http://localhost/rest/api/2/user?username=test.user\"}")));

        wireMockServer.stubFor(WireMock.post(WireMock.urlPathMatching("/rest/api/2/issue/[^/]+/attachments"))
                .willReturn(WireMock.aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("[{\"id\": \"10002\", \"filename\": \"test.log\", \"mimeType\": \"text/plain\", \"self\": \"http://localhost/rest/api/2/attachment/10002\"}]")));
    }

    @AfterEach
    void tearDown() {
        wireMockServer.stop();
    }

    @Test
    void createIssue_shouldReturnIssueResponse() throws Exception {
        JiraIssueRequest request = new JiraIssueRequest("TEST", "Bug", "Test Summary", "h2. Description\n\n*bold* text");

        JiraIssueResponse response = jiraClient.createIssue(request);

        assertNotNull(response);
        assertEquals("TEST-123", response.getKey());
        assertEquals("10001", response.getId());
        assertNotNull(response.getSelf());
    }

    @Test
    void getMyself_shouldReturnUserInfo() throws Exception {
        JiraUserInfo userInfo = jiraClient.getMyself();

        assertNotNull(userInfo);
        assertEquals("test.user", userInfo.getName());
        assertEquals("Test User", userInfo.getDisplayName());
        assertEquals("test@example.com", userInfo.getEmail());
    }

    @Test
    void attachFile_shouldReturnAttachmentResponse() throws Exception {
        Path tempFile = Files.createTempFile("test", ".log");
        Files.writeString(tempFile, "test log content");

        try {
            List<JiraAttachmentResponse> responses = jiraClient.attachFile("TEST-123", tempFile);

            assertNotNull(responses);
            assertEquals(1, responses.size());
            assertEquals("10002", responses.get(0).getId());
            assertEquals("test.log", responses.get(0).getFilename());
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }
}