package com.testreports.orchestrator;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Comparator;
import java.util.Objects;
import java.util.stream.Stream;

public class WebDeployStage implements PipelineStage {
    @Override
    public String getName() {
        return "WebDeploy";
    }

    @Override
    public boolean isCritical() {
        return false;
    }

    @Override
    public void execute(RunContext ctx) throws Exception {
        Objects.requireNonNull(ctx.getManifest(), "manifest must be available before web deploy");
        Path manifestPath = ctx.getConfig().path(PipelineConfig.MANIFEST_DIR).resolve(ctx.getRunId() + ".json");
        Path reportDir = ctx.getConfig().path(PipelineConfig.ALLURE_REPORT_DIR);
        Path deployDir = ctx.getConfig().path(PipelineConfig.WEB_DEPLOY_DIR).resolve(ctx.getRunId());

        Files.createDirectories(deployDir);
        Files.copy(manifestPath, deployDir.resolve("manifest.json"), StandardCopyOption.REPLACE_EXISTING);
        if (Files.isDirectory(reportDir)) {
            copyDirectory(reportDir, deployDir.resolve("report"));
        }
    }

    private void copyDirectory(Path source, Path target) throws IOException {
        if (Files.exists(target)) {
            deleteDirectory(target);
        }
        try (Stream<Path> paths = Files.walk(source)) {
            for (Path path : paths.toList()) {
                Path relative = source.relativize(path);
                Path destination = target.resolve(relative);
                if (Files.isDirectory(path)) {
                    Files.createDirectories(destination);
                } else {
                    Files.createDirectories(destination.getParent());
                    Files.copy(path, destination, StandardCopyOption.REPLACE_EXISTING);
                }
            }
        }
    }

    private void deleteDirectory(Path directory) throws IOException {
        try (Stream<Path> paths = Files.walk(directory)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }
}
