package com.testreports.orchestrator;

public interface PipelineStage {
    String getName();

    boolean isCritical();

    void execute(RunContext ctx) throws Exception;
}
