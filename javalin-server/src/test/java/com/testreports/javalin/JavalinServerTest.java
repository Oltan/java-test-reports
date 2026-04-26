package com.testreports.javalin;

import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.*;

class JavalinServerTest {

    private Javalin app;
    private static final String TEST_MANIFESTS_DIR =
            Paths.get("src/test/resources/manifests").toAbsolutePath().toString();

    @BeforeEach
    void setUp() {
        JavalinServer server = new JavalinServer(TEST_MANIFESTS_DIR);
        app = server.app();
    }

    @Test
    void loginReturns200AndToken() {
        JavalinTest.test(app, (server, client) -> {
            String body = "{\"username\":\"admin\",\"password\":\"admin123\"}";
            var response = client.post("/api/v1/auth/login", body);
            assertEquals(200, response.code());
            String responseBody = response.body().string();
            assertTrue(responseBody.contains("\"token\""), "Response should contain token field");
        });
    }

    @Test
    void getRunsWithoutTokenReturns401() {
        JavalinTest.test(app, (server, client) -> {
            var response = client.get("/api/v1/runs");
            assertEquals(401, response.code());
        });
    }

    @Test
    void getRunsWithValidTokenReturns200() {
        JavalinTest.test(app, (server, client) -> {
            String token = obtainToken(client);

            var runsResponse = client.get("/api/v1/runs", req -> {
                req.header("Authorization", "Bearer " + token);
            });
            assertEquals(200, runsResponse.code());

            String runsBody = runsResponse.body().string();
            assertTrue(runsBody.contains("test-001"), "Runs response should contain test-001");
        });
    }

    @Test
    void getRunByIdReturnsCorrectRun() {
        JavalinTest.test(app, (server, client) -> {
            String token = obtainToken(client);

            var response = client.get("/api/v1/runs/test-001", req -> {
                req.header("Authorization", "Bearer " + token);
            });
            assertEquals(200, response.code());

            String body = response.body().string();
            assertTrue(body.contains("test-001"), "Response should contain runId test-001");
        });
    }

    @Test
    void getRunByIdReturns404ForMissingRun() {
        JavalinTest.test(app, (server, client) -> {
            String token = obtainToken(client);

            var response = client.get("/api/v1/runs/nonexistent", req -> {
                req.header("Authorization", "Bearer " + token);
            });
            assertEquals(404, response.code());
        });
    }

    @Test
    void getFailuresReturnsFailedScenarios() {
        JavalinTest.test(app, (server, client) -> {
            String token = obtainToken(client);

            var response = client.get("/api/v1/runs/test-001/failures", req -> {
                req.header("Authorization", "Bearer " + token);
            });
            assertEquals(200, response.code());

            String body = response.body().string();
            assertTrue(body.contains("\"status\":\"failed\""), "Failures response should contain failed scenario");
            assertTrue(body.contains("scenario-002"), "Failures response should contain the failed scenario id");
        });
    }

    @Test
    void loginWithWrongPasswordReturns401() {
        JavalinTest.test(app, (server, client) -> {
            String body = "{\"username\":\"admin\",\"password\":\"wrong\"}";
            var response = client.post("/api/v1/auth/login", body);
            assertEquals(401, response.code());
        });
    }

    private String obtainToken(io.javalin.testtools.HttpClient client) throws Exception {
        String loginBody = "{\"username\":\"admin\",\"password\":\"admin123\"}";
        var loginResponse = client.post("/api/v1/auth/login", loginBody);
        return extractToken(loginResponse.body().string());
    }

    private static String extractToken(String json) {
        int tokenIndex = json.indexOf("\"token\"");
        int colonIndex = json.indexOf(":", tokenIndex);
        int startQuote = json.indexOf("\"", colonIndex);
        int endQuote = json.indexOf("\"", startQuote + 1);
        return json.substring(startQuote + 1, endQuote);
    }
}