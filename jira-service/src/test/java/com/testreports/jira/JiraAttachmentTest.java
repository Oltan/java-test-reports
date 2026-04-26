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

class JiraAttachmentTest {

    private WireMockServer wireMockServer;
    private JiraClient jiraClient;

    @BeforeEach
    void setUp() {
        wireMockServer = new WireMockServer();
        wireMockServer.start();

        String baseUrl = "http://localhost:" + wireMockServer.port();
        jiraClient = new JiraClient(baseUrl, "test-pat-token");

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
    void attachFile_shouldReturnAttachmentResponse() throws Exception {
        Path tempFile = Files.createTempFile("test", ".log");
        Files.writeString(tempFile, "test log content");

        try {
            List<JiraAttachmentResponse> responses = jiraClient.attachFile("TEST-123", tempFile);

            assertNotNull(responses);
            assertEquals(1, responses.size());
            assertEquals("10002", responses.get(0).getId());
            assertEquals("test.log", responses.get(0).getFilename());
            assertEquals("text/plain", responses.get(0).getMimeType());
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }

    @Test
    void attachFile_shouldIncludeXAtlassianTokenHeader() throws Exception {
        wireMockServer.stubFor(WireMock.post(WireMock.urlPathMatching("/rest/api/2/issue/[^/]+/attachments"))
                .withHeader("X-Atlassian-Token", WireMock.equalTo("no-check"))
                .willReturn(WireMock.aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("[{\"id\": \"10003\", \"filename\": \"report.html\", \"mimeType\": \"text/html\", \"self\": \"http://localhost/rest/api/2/attachment/10003\"}]")));

        Path tempFile = Files.createTempFile("report", ".html");
        Files.writeString(tempFile, "<html><body>Report</body></html>");

        try {
            List<JiraAttachmentResponse> responses = jiraClient.attachFile("TEST-456", tempFile);

            assertNotNull(responses);
            assertEquals(1, responses.size());
            assertEquals("10003", responses.get(0).getId());
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }
}