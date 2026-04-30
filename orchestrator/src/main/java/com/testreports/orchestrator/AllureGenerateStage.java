package com.testreports.orchestrator;

import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

public class AllureGenerateStage implements PipelineStage {
    private final CommandExecutor commandExecutor;

    public AllureGenerateStage() {
        this(new ProcessBuilderCommandExecutor());
    }

    public AllureGenerateStage(CommandExecutor commandExecutor) {
        this.commandExecutor = Objects.requireNonNull(commandExecutor, "commandExecutor must not be null");
    }

    @Override
    public String getName() {
        return "AllureGenerate";
    }

    @Override
    public boolean isCritical() {
        return false;  // allure CLI opsiyonel — yoksa manifest üretimi yine de devam eder
    }

    @Override
    public void execute(RunContext ctx) throws Exception {
        Path resultsDir = ctx.getConfig().path(PipelineConfig.ALLURE_RESULTS_DIR);
        Path reportDir = ctx.getConfig().path(PipelineConfig.ALLURE_REPORT_DIR);
        List<String> command = List.of(
                "allure",
                "generate",
                resultsDir.toString(),
                "--clean",
                "-o",
                reportDir.toString()
        );
        int exitCode = commandExecutor.execute(command);
        if (exitCode != 0) {
            throw new IllegalStateException("allure generate failed with exit code " + exitCode);
        }
    }
}
