package com.testreports.doors;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.testreports.model.RunManifest;
import com.testreports.model.ScenarioResult;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

public class DoorsClient {

    private static final Logger LOGGER = Logger.getLogger(DoorsClient.class.getName());
    private static final Duration DEFAULT_EXECUTION_TIMEOUT = Duration.ofSeconds(120);
    private static final String DXL_RESOURCE = "/DoorsDxlScript.dxl";

    private final Path doorsExePath;
    private final ObjectMapper objectMapper;
    private final Duration executionTimeout;

    public DoorsClient(Path doorsExePath) {
        this(doorsExePath, new ObjectMapper(), DEFAULT_EXECUTION_TIMEOUT);
    }

    DoorsClient(Path doorsExePath, ObjectMapper objectMapper, Duration executionTimeout) {
        this.doorsExePath = Objects.requireNonNull(doorsExePath, "doorsExePath must not be null");
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper must not be null");
        this.executionTimeout = Objects.requireNonNull(executionTimeout, "executionTimeout must not be null");
    }

    public void updateTestRun(RunManifest manifest) {
        Objects.requireNonNull(manifest, "manifest must not be null");

        Path scriptPath = resolveScriptPath();
        List<String> commandPreview = command(scriptPath, Path.of("<temp-json>"));
        if (Boolean.getBoolean("doors.dry.run")) {
            LOGGER.info(() -> "DOORS dry run enabled; would execute: " + String.join(" ", commandPreview));
            return;
        }

        if (shouldSkipForCurrentOperatingSystem()) {
            LOGGER.warning("DOORS requires Windows; skipping batch DXL execution");
            return;
        }

        if (Files.notExists(doorsExePath)) {
            LOGGER.warning(() -> "doors.exe not found at " + doorsExePath + "; skipping DOORS update");
            return;
        }

        Path tempJson = null;
        try {
            tempJson = Files.createTempFile("doors-run-", ".json");
            objectMapper.writeValue(tempJson.toFile(), toDxlPayload(manifest));
            DoorsProcessResult result = execute(command(scriptPath, tempJson));
            validateResult(result);
        } catch (IOException e) {
            throw new UncheckedIOException("Unable to execute DOORS batch DXL", e);
        } finally {
            deleteQuietly(tempJson);
        }
    }

    private DxlPayload toDxlPayload(RunManifest manifest) {
        List<DxlResult> results = new ArrayList<>();
        if (manifest.getScenarios() != null) {
            for (ScenarioResult scenario : manifest.getScenarios()) {
                if (scenario != null && hasText(scenario.getDoorsAbsNumber())) {
                    results.add(new DxlResult(scenario.getDoorsAbsNumber(), scenario.getStatus()));
                }
            }
        }
        return new DxlPayload(manifest.getRunId(), results);
    }

    private DoorsProcessResult execute(List<String> command) throws IOException {
        ProcessBuilder processBuilder = new ProcessBuilder(command);
        Process process = processBuilder.start();

        boolean finished;
        try {
            finished = process.waitFor(executionTimeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw new DoorsTimeoutException("Interrupted while waiting for doors.exe batch DXL execution");
        }

        if (!finished) {
            process.destroyForcibly();
            throw new DoorsTimeoutException("doors.exe batch DXL execution exceeded " + executionTimeout.toSeconds() + " seconds");
        }

        return new DoorsProcessResult(process.exitValue(), readAll(process.getInputStream()), readAll(process.getErrorStream()));
    }

    private void validateResult(DoorsProcessResult result) {
        if (hasText(result.stdout())) {
            LOGGER.info(() -> "DOORS stdout: " + result.stdout());
        }
        if (hasText(result.stderr())) {
            LOGGER.warning(() -> "DOORS stderr: " + result.stderr());
        }

        String combinedOutput = (result.stdout() + "\n" + result.stderr()).toLowerCase(Locale.ROOT);
        if (result.exitCode() != 0 || combinedOutput.contains("error") || combinedOutput.contains("failed")) {
            throw new IllegalStateException("DOORS batch DXL failed with exit code " + result.exitCode()
                    + ", stdout=" + result.stdout() + ", stderr=" + result.stderr());
        }
    }

    private List<String> command(Path scriptPath, Path paramFile) {
        return List.of(
                doorsExePath.toString(),
                "-b",
                scriptPath.toString(),
                "-paramFile",
                paramFile.toString(),
                "-W"
        );
    }

    private Path resolveScriptPath() {
        try (InputStream inputStream = DoorsClient.class.getResourceAsStream(DXL_RESOURCE)) {
            if (inputStream == null) {
                throw new IllegalStateException("Missing DXL resource " + DXL_RESOURCE);
            }
            Path scriptPath = Files.createTempFile("doors-dxl-script-", ".dxl");
            Files.copy(inputStream, scriptPath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            scriptPath.toFile().deleteOnExit();
            return scriptPath;
        } catch (IOException e) {
            throw new UncheckedIOException("Unable to prepare DOORS DXL script", e);
        }
    }

    private boolean shouldSkipForCurrentOperatingSystem() {
        String osName = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (!osName.contains("linux")) {
            return false;
        }

        if (Files.isExecutable(doorsExePath)) {
            LOGGER.warning("DOORS requires Windows; running executable test double on Linux");
            return false;
        }

        return true;
    }

    private String readAll(InputStream inputStream) throws IOException {
        return new String(inputStream.readAllBytes()).trim();
    }

    private void deleteQuietly(Path path) {
        if (path == null) {
            return;
        }
        try {
            Files.deleteIfExists(path);
        } catch (IOException e) {
            LOGGER.log(Level.WARNING, "Unable to delete temporary DOORS parameter file " + path, e);
        }
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private record DxlPayload(String runId, List<DxlResult> results) {
    }

    private record DxlResult(String absNumber, String status) {
    }

    private record DoorsProcessResult(int exitCode, String stdout, String stderr) {
    }
}
