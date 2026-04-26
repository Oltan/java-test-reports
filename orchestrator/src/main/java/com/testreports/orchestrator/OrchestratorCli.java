package com.testreports.orchestrator;

import java.util.List;

public class OrchestratorCli {
    public static void main(String[] args) {
        int exitCode = new OrchestratorCli().execute(args);
        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }

    int execute(String[] args) {
        String runId = parseRunId(args);
        PipelineConfig config = PipelineConfig.fromEnvironment(System.getenv(), System.getProperties());
        RunContext context = new RunContext(runId, null, config);
        try {
            new PipelineRunner().run(defaultStages(), context);
            return 0;
        } catch (Exception e) {
            e.printStackTrace(System.err);
            return 1;
        }
    }

    List<PipelineStage> defaultStages() {
        return List.of(
                new AllureGenerateStage(),
                new ManifestWriteStage(),
                new WebDeployStage(),
                new EmailSendStage()
        );
    }

    private String parseRunId(String[] args) {
        if (args == null) {
            return "auto";
        }
        for (String arg : args) {
            if (arg != null && arg.startsWith("--run-id=")) {
                return arg.substring("--run-id=".length());
            }
        }
        return "auto";
    }
}
