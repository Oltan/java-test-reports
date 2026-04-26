package com.testreports.orchestrator;

import com.testreports.doors.DoorsClient;
import com.testreports.model.RunManifest;

import java.nio.file.Path;
import java.util.Objects;
import java.util.logging.Logger;

public class DoorsUpdateStage implements PipelineStage {
    private static final Logger LOGGER = Logger.getLogger(DoorsUpdateStage.class.getName());

    private final DoorsUpdater updater;

    public DoorsUpdateStage() {
        this(null);
    }

    public DoorsUpdateStage(DoorsUpdater updater) {
        this.updater = updater;
    }

    @Override
    public String getName() {
        return "DoorsUpdate";
    }

    @Override
    public boolean isCritical() {
        return false;
    }

    @Override
    public void execute(RunContext ctx) {
        RunManifest manifest = Objects.requireNonNull(ctx.getManifest(), "manifest must be available before DOORS update");
        DoorsUpdater activeUpdater = updater == null ? createUpdater(ctx.getConfig()) : updater;
        if (activeUpdater == null) {
            LOGGER.info("No DOORS executable configured; skipping DOORS update");
            return;
        }
        activeUpdater.update(manifest);
    }

    private DoorsUpdater createUpdater(PipelineConfig config) {
        return config.get(PipelineConfig.DOORS_EXE)
                .map(Path::of)
                .map(DoorsClient::new)
                .<DoorsUpdater>map(client -> client::updateTestRun)
                .orElse(null);
    }

    @FunctionalInterface
    public interface DoorsUpdater {
        void update(RunManifest manifest);
    }
}
