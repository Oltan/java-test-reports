package com.testreports.orchestrator;

import java.util.List;
import java.util.Objects;
import java.util.logging.Level;
import java.util.logging.Logger;

public class PipelineRunner {
    private static final Logger LOGGER = Logger.getLogger(PipelineRunner.class.getName());

    public void run(List<PipelineStage> stages, RunContext ctx) throws Exception {
        Objects.requireNonNull(stages, "stages must not be null");
        Objects.requireNonNull(ctx, "ctx must not be null");

        for (PipelineStage stage : stages) {
            Objects.requireNonNull(stage, "pipeline stage must not be null");
            LOGGER.info(() -> "Starting stage: " + stage.getName());
            try {
                stage.execute(ctx);
                LOGGER.info(() -> "Finished stage: " + stage.getName());
            } catch (Exception e) {
                if (e instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
                if (stage.isCritical()) {
                    LOGGER.log(Level.SEVERE, "Critical stage failed: " + stage.getName(), e);
                    throw new StageExecutionException(stage.getName(), e);
                }
                LOGGER.log(Level.WARNING, "Non-critical stage failed; continuing: " + stage.getName(), e);
            }
        }
    }
}
