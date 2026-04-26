package com.testreports.jira;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.client.WireMock;

class JiraRetryTest {

    private WireMockServer wireMockServer;
    private JiraClient jiraClient;

    @BeforeEach
    void setUp() {
        wireMockServer = new WireMockServer();
        wireMockServer.start();

        String baseUrl = "http://localhost:" + wireMockServer.port();
        jiraClient = new JiraClient(baseUrl, "test-pat-token");
    }

    @AfterEach
    void tearDown() {
        wireMockServer.stop();
    }

    @Test
    void createIssue_whenServerFailsTwice_thenSucceedsOnThirdAttempt() throws Exception {
        wireMockServer.stubFor(WireMock.post("/rest/api/2/issue")
                .inScenario("RetryScenario")
                .whenScenarioStateIs("START")
                .willReturn(WireMock.aResponse()
                        .withStatus(500)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"error\":\"Server Error\"}"))
                .willSetStateTo("ONE_FAILURE"));

        wireMockServer.stubFor(WireMock.post("/rest/api/2/issue")
                .inScenario("RetryScenario")
                .whenScenarioStateIs("ONE_FAILURE")
                .willReturn(WireMock.aResponse()
                        .withStatus(500)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"error\":\"Server Error\"}"))
                .willSetStateTo("TWO_FAILURES"));

        wireMockServer.stubFor(WireMock.post("/rest/api/2/issue")
                .inScenario("RetryScenario")
                .whenScenarioStateIs("TWO_FAILURES")
                .willReturn(WireMock.aResponse()
                        .withStatus(201)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"id\": \"10001\", \"key\": \"TEST-123\", \"self\": \"http://localhost/rest/api/2/issue/10001\"}")));

        JiraIssueRequest request = new JiraIssueRequest("TEST", "Bug", "Retry Test", "h2. Description");
        JiraIssueResponse response = jiraClient.createIssue(request);

        assertNotNull(response);
        assertEquals("TEST-123", response.getKey());
        assertEquals("10001", response.getId());
    }

    @Test
    void createIssue_whenAllAttemptsFail_thenThrowsException() throws Exception {
        wireMockServer.stubFor(WireMock.post("/rest/api/2/issue")
                .willReturn(WireMock.aResponse()
                        .withStatus(500)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"error\":\"Server Error\"}")));

        JiraIssueRequest request = new JiraIssueRequest("TEST", "Bug", "All Fail Test", "h2. Description");

        assertThrows(Exception.class, () -> {
            jiraClient.createIssue(request);
        });
    }

    @Test
    void createIssue_whenRateLimited_thenRetries() throws Exception {
        wireMockServer.stubFor(WireMock.post("/rest/api/2/issue")
                .inScenario("RateLimitScenario")
                .whenScenarioStateIs("START")
                .willReturn(WireMock.aResponse()
                        .withStatus(429)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"error\":\"Rate Limited\"}"))
                .willSetStateTo("AFTER_RATE_LIMIT"));

        wireMockServer.stubFor(WireMock.post("/rest/api/2/issue")
                .inScenario("RateLimitScenario")
                .whenScenarioStateIs("AFTER_RATE_LIMIT")
                .willReturn(WireMock.aResponse()
                        .withStatus(201)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"id\": \"10002\", \"key\": \"TEST-124\", \"self\": \"http://localhost/rest/api/2/issue/10002\"}")));

        JiraIssueRequest request = new JiraIssueRequest("TEST", "Bug", "Rate Limit Test", "h2. Description");
        JiraIssueResponse response = jiraClient.createIssue(request);

        assertNotNull(response);
        assertEquals("TEST-124", response.getKey());
    }
}