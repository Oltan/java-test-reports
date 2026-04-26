package com.testreports.orchestrator;

import java.io.IOException;
import java.util.List;

@FunctionalInterface
public interface CommandExecutor {
    int execute(List<String> command) throws IOException, InterruptedException;
}
