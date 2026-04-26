package com.testreports.orchestrator;

public class StageExecutionException extends Exception {
    private final String stageName;

    public StageExecutionException(String stageName, Throwable cause) {
        super("Critical pipeline stage failed: " + stageName, cause);
        this.stageName = stageName;
    }

    public String getStageName() {
        return stageName;
    }
}
