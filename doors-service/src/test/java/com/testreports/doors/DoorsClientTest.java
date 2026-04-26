package com.testreports.doors;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.testreports.model.RunManifest;
import com.testreports.model.ScenarioResult;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DoorsClientTest {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    @TempDir
    Path tempDir;

    @AfterEach
    void clearDryRunProperty() {
        System.clearProperty("doors.dry.run");
    }

    @Test
    void passesExpectedBatchArgumentsToDoorsExecutable() throws Exception {
        Path argsLog = tempDir.resolve("doors-args.txt");
        Path exe = fakeDoorsExe("""
                printf '%s\n' "$@" > '__ARGS_LOG__'
                echo 'SUCCESS: updated DOORS attributes'
                """.replace("__ARGS_LOG__", argsLog.toString()));

        new DoorsClient(exe).updateTestRun(manifestWithDoorResult("DOORS-12345", "passed"));

        List<String> args = Files.readAllLines(argsLog);
        assertEquals("-b", args.get(0));
        assertTrue(args.get(1).endsWith(".dxl"));
        assertEquals("-paramFile", args.get(2));
        assertTrue(args.get(3).endsWith(".json"));
        assertEquals("-W", args.get(4));
    }

    @Test
    void throwsDoorsTimeoutExceptionWhenBatchExecutionExceedsLimit() throws Exception {
        Path exe = fakeDoorsExe("sleep 5");
        DoorsClient client = new DoorsClient(exe, OBJECT_MAPPER, Duration.ofMillis(100));

        assertThrows(DoorsTimeoutException.class,
                () -> client.updateTestRun(manifestWithDoorResult("DOORS-12345", "failed")));
    }

    @Test
    void returnsNormallyWhenFakeExecutableReportsSuccess() throws Exception {
        Path payloadPath = tempDir.resolve("payload.json");
        Path exe = fakeDoorsExe("""
                while [ "$#" -gt 0 ]; do
                  if [ "$1" = '-paramFile' ]; then
                    shift
                    cp "$1" '__PAYLOAD_PATH__'
                  fi
                  shift
                done
                echo 'SUCCESS: completed'
                """.replace("__PAYLOAD_PATH__", payloadPath.toString()));

        assertDoesNotThrow(() -> new DoorsClient(exe).updateTestRun(manifestWithDoorResult("DOORS-98765", "passed")));

        JsonNode payload = OBJECT_MAPPER.readTree(payloadPath.toFile());
        assertEquals("run-1", payload.get("runId").asText());
        assertEquals("DOORS-98765", payload.get("results").get(0).get("absNumber").asText());
        assertEquals("passed", payload.get("results").get(0).get("status").asText());
    }

    @Test
    void missingExecutableIsGracefulWarningOnly() {
        Path missingExe = tempDir.resolve("missing-doors.exe");

        assertDoesNotThrow(() -> new DoorsClient(missingExe).updateTestRun(manifestWithDoorResult("DOORS-12345", "passed")));
    }

    @Test
    void dryRunSkipsProcessExecution() throws Exception {
        System.setProperty("doors.dry.run", "true");
        Path calledMarker = tempDir.resolve("called.txt");
        Path exe = fakeDoorsExe("touch '__CALLED_MARKER__'".replace("__CALLED_MARKER__", calledMarker.toString()));

        new DoorsClient(exe).updateTestRun(manifestWithDoorResult("DOORS-12345", "passed"));

        assertFalse(Files.exists(calledMarker));
    }

    private Path fakeDoorsExe(String body) throws IOException {
        Path exe = tempDir.resolve("doors.exe");
        Files.writeString(exe, "#!/usr/bin/env bash\nset -e\n" + body + "\n");
        assertTrue(exe.toFile().setExecutable(true), "fake doors.exe must be executable");
        assertTrue(Files.isExecutable(exe));
        return exe;
    }

    private RunManifest manifestWithDoorResult(String absNumber, String status) {
        ScenarioResult scenario = new ScenarioResult();
        scenario.setDoorsAbsNumber(absNumber);
        scenario.setStatus(status);

        RunManifest manifest = new RunManifest();
        manifest.setRunId("run-1");
        manifest.setTimestamp(Instant.parse("2026-04-26T00:00:00Z"));
        manifest.setScenarios(List.of(scenario));
        assertNotNull(manifest.getScenarios());
        return manifest;
    }
}
