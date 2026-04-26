package com.testreports.orchestrator;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.logging.Logger;

public class ProcessBuilderCommandExecutor implements CommandExecutor {
    private static final Logger LOGGER = Logger.getLogger(ProcessBuilderCommandExecutor.class.getName());

    @Override
    public int execute(List<String> command) throws IOException, InterruptedException {
        ProcessBuilder processBuilder = new ProcessBuilder(command);
        processBuilder.redirectErrorStream(true);
        Process process = processBuilder.start();
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
        int exitCode = process.waitFor();
        if (!output.isBlank()) {
            LOGGER.info(output);
        }
        return exitCode;
    }
}
