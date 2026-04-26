package com.testreports.jira;

import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;

class JiraDryRunTest {

    @Test
    void createIssue_withDryRun_shouldNotMakeHttpCall() throws Exception {
        JiraClient client = new JiraClient("http://localhost:9999", "test-pat-token", true);

        ByteArrayOutputStream errContent = new ByteArrayOutputStream();
        System.setErr(new PrintStream(errContent));

        try {
            JiraIssueRequest request = new JiraIssueRequest("TEST", "Bug", "Dry Run Test", "h2. Description");
            JiraIssueResponse response = client.createIssue(request);

            assertNotNull(response);
            assertNull(response.getKey());
            assertNull(response.getId());
            assertTrue(errContent.toString().contains("[DRY-RUN] Would create issue: Dry Run Test"));
        } finally {
            System.setErr(System.err);
        }
    }

    @Test
    void attachFile_withDryRun_shouldLogAndReturnEmptyList() throws Exception {
        JiraClient client = new JiraClient("http://localhost:9999", "test-pat-token", true);

        ByteArrayOutputStream errContent = new ByteArrayOutputStream();
        System.setErr(new PrintStream(errContent));

        Path tempFile = Files.createTempFile("test", ".log");
        Files.writeString(tempFile, "test log content");

        try {
            var responses = client.attachFile("TEST-123", tempFile);

            assertNotNull(responses);
            assertTrue(responses.isEmpty());
            assertTrue(errContent.toString().contains("[DRY-RUN] Would attach file to issue: TEST-123"));
        } finally {
            Files.deleteIfExists(tempFile);
            System.setErr(System.err);
        }
    }

    @Test
    void createIssueIfNew_withDryRun_shouldNotCreateIssue() throws Exception {
        JiraClient client = new JiraClient("http://localhost:9999", "test-pat-token", true);

        ByteArrayOutputStream errContent = new ByteArrayOutputStream();
        System.setErr(new PrintStream(errContent));

        try {
            JiraIssueRequest request = new JiraIssueRequest("TEST", "Bug", "Dry Run Dedup Test", "h2. Description");
            String key1 = client.createIssueIfNew("dedup-key-1", request);
            String key2 = client.createIssueIfNew("dedup-key-1", request);

            assertNull(key1);
            assertNull(key2);
            assertTrue(errContent.toString().contains("[DRY-RUN] Would create issue: Dry Run Dedup Test"));
        } finally {
            System.setErr(System.err);
        }
    }
}