package com.testreports.jira;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.client.WireMock;

class JiraDuplicateTest {

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
    }

    @AfterEach
    void tearDown() {
        wireMockServer.stop();
    }

    @Test
    void createIssueIfNew_withSameDedupKey_twice_shouldReturnNullOnSecondCall() throws Exception {
        JiraIssueRequest request = new JiraIssueRequest("TEST", "Bug", "Duplicate Test", "h2. Description");

        String key1 = jiraClient.createIssueIfNew("run1-scenario1", request);
        String key2 = jiraClient.createIssueIfNew("run1-scenario1", request);

        assertEquals("TEST-123", key1);
        assertNull(key2);
    }

    @Test
    void createIssueIfNew_withDifferentDedupKeys_shouldCreateBothIssues() throws Exception {
        wireMockServer.stubFor(WireMock.post("/rest/api/2/issue")
                .willReturn(WireMock.aResponse()
                        .withStatus(201)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"id\": \"10002\", \"key\": \"TEST-124\", \"self\": \"http://localhost/rest/api/2/issue/10002\"}")));

        JiraIssueRequest request1 = new JiraIssueRequest("TEST", "Bug", "First Issue", "h2. Description");
        JiraIssueRequest request2 = new JiraIssueRequest("TEST", "Bug", "Second Issue", "h2. Description");

        String key1 = jiraClient.createIssueIfNew("run1-scenario1", request1);
        String key2 = jiraClient.createIssueIfNew("run1-scenario2", request2);

        assertEquals("TEST-123", key1);
        assertEquals("TEST-124", key2);
    }

    @Test
    void createIssueIfNew_withSameDedupKeyDifferentClient_shouldCreateNewIssue() throws Exception {
        JiraIssueRequest request = new JiraIssueRequest("TEST", "Bug", "Duplicate Test", "h2. Description");

        String key1 = jiraClient.createIssueIfNew("run1-scenario1", request);

        JiraClient anotherClient = new JiraClient("http://localhost:" + wireMockServer.port(), "test-pat-token");
        String key2 = anotherClient.createIssueIfNew("run1-scenario1", request);

        assertEquals("TEST-123", key1);
        assertEquals("TEST-123", key2);
    }
}