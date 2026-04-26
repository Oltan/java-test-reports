package com.testreports.jira;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.client.WireMock;

class JiraAuthTest {

    private WireMockServer wireMockServer;
    private JiraClient jiraClient;

    @BeforeEach
    void setUp() {
        wireMockServer = new WireMockServer();
        wireMockServer.start();

        String baseUrl = "http://localhost:" + wireMockServer.port();
        jiraClient = new JiraClient(baseUrl, "test-pat-token");

        wireMockServer.stubFor(WireMock.get("/rest/api/2/myself")
                .willReturn(WireMock.aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"name\": \"test.user\", \"displayName\": \"Test User\", \"email\": \"test@example.com\", \"self\": \"http://localhost/rest/api/2/user?username=test.user\"}")));
    }

    @AfterEach
    void tearDown() {
        wireMockServer.stop();
    }

    @Test
    void getMyself_withPat_shouldReturnUserInfo() throws Exception {
        JiraUserInfo userInfo = jiraClient.getMyself();

        assertNotNull(userInfo);
        assertEquals("test.user", userInfo.getName());
        assertEquals("Test User", userInfo.getDisplayName());
    }

    @Test
    void getMyself_shouldIncludeBasicAuthHeader() throws Exception {
        wireMockServer.stubFor(WireMock.get("/rest/api/2/myself")
                .withHeader("Authorization", WireMock.equalTo("Basic ignored:test-pat-token"))
                .willReturn(WireMock.aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"name\": \"test.user\", \"displayName\": \"Test User\"}")));

        JiraUserInfo userInfo = jiraClient.getMyself();
        assertNotNull(userInfo);
        assertEquals("test.user", userInfo.getName());
    }
}