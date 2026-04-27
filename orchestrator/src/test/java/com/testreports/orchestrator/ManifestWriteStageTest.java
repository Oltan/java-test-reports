package com.testreports.orchestrator;

import com.testreports.model.AttachmentInfo;
import com.testreports.model.RunManifest;
import com.testreports.model.ScenarioResult;
import com.testreports.model.StepResult;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests the attachment-copy logic of ManifestWriteStage via execute().
 * Parser and persister are stubbed so the test is focused on attachment handling.
 */
class ManifestWriteStageTest {

    @TempDir Path resultsDir;
    @TempDir Path manifestDir;

    // ── Helpers ────────────────────────────────────────────────────────────

    private RunContext contextFor(String runId) {
        PipelineConfig config = new PipelineConfig(Map.of(
                PipelineConfig.ALLURE_RESULTS_DIR, resultsDir.toString(),
                PipelineConfig.MANIFEST_DIR,       manifestDir.toString()
        ));
        return new RunContext(runId, null, config);
    }

    private ScenarioResult scenarioWithAttachment(String filename, String mimeType) {
        AttachmentInfo att = new AttachmentInfo("Attachment", mimeType, filename);
        StepResult step = new StepResult("Some step", "failed", "err");
        return new ScenarioResult("sc-1", "Test scenario", "failed",
                "PT2S", null, List.of(), List.of(step), List.of(att));
    }

    /**
     * Builds a stage whose parser returns the given scenarios and whose persister
     * captures them for later inspection (returns a stub manifest).
     */
    private record StageAndCapture(ManifestWriteStage stage, List<ScenarioResult>[] captured) {}

    @SuppressWarnings("unchecked")
    private StageAndCapture stageFor(List<ScenarioResult> scenarios) {
        List<ScenarioResult>[] box = new List[1];
        ManifestWriteStage stage = new ManifestWriteStage(
                dir -> scenarios,
                (list, outDir, runId) -> {
                    box[0] = list;
                    RunManifest m = new RunManifest();
                    m.setRunId(runId);
                    m.setScenarios(list);
                    return m;
                }
        );
        return new StageAndCapture(stage, box);
    }

    // ── Tests ──────────────────────────────────────────────────────────────

    @Test
    void attachmentIsCopiedToManifestDir() throws Exception {
        // Place a dummy PNG in the allure-results directory
        byte[] pngBytes = {(byte) 0x89, 'P', 'N', 'G', 0x0D, 0x0A};
        Files.write(resultsDir.resolve("abc-screenshot.png"), pngBytes);

        ScenarioResult scenario = scenarioWithAttachment("abc-screenshot.png", "image/png");
        var sac = stageFor(List.of(scenario));

        sac.stage().execute(contextFor("run-001"));

        // Binary copied to expected location
        Path dest = manifestDir.resolve("attachments").resolve("run-001").resolve("abc-screenshot.png");
        assertTrue(Files.exists(dest), "Attachment should be copied to " + dest);
        assertArrayEquals(pngBytes, Files.readAllBytes(dest));

        // Path rewritten in the persisted scenarios
        AttachmentInfo att = sac.captured()[0].get(0).getAttachments().get(0);
        assertEquals("attachments/run-001/abc-screenshot.png", att.getPath());
        assertEquals("image/png", att.getType());
        assertEquals("Attachment", att.getName());
    }

    @Test
    void missingAttachmentFileIsSkippedGracefully() throws Exception {
        // No physical file written — attachment source is a ghost
        ScenarioResult scenario = scenarioWithAttachment("ghost.png", "image/png");
        var sac = stageFor(List.of(scenario));

        sac.stage().execute(contextFor("run-002"));

        // Path stays unchanged
        assertEquals("ghost.png", sac.captured()[0].get(0).getAttachments().get(0).getPath());
        // No attachments directory created
        assertFalse(Files.exists(manifestDir.resolve("attachments")));
    }

    @Test
    void scenarioWithNoAttachmentsIsUntouched() throws Exception {
        ScenarioResult scenario = new ScenarioResult("sc-2", "Clean pass", "passed",
                "PT1S", null, List.of(), List.of(), List.of());
        var sac = stageFor(List.of(scenario));

        sac.stage().execute(contextFor("run-003"));

        assertTrue(sac.captured()[0].get(0).getAttachments().isEmpty());
        assertFalse(Files.exists(manifestDir.resolve("attachments")));
    }

    @Test
    void screenshotAndVideoAreBothCopied() throws Exception {
        Files.write(resultsDir.resolve("snap.png"), new byte[]{1, 2, 3});
        Files.write(resultsDir.resolve("clip.mp4"), new byte[]{4, 5, 6});

        AttachmentInfo png = new AttachmentInfo("Screenshot", "image/png",  "snap.png");
        AttachmentInfo mp4 = new AttachmentInfo("Video",      "video/mp4",  "clip.mp4");
        ScenarioResult scenario = new ScenarioResult("sc-3", "Video test", "failed",
                "PT5S", null, List.of(), List.of(), List.of(png, mp4));

        var sac = stageFor(List.of(scenario));
        sac.stage().execute(contextFor("run-004"));

        Path dir = manifestDir.resolve("attachments").resolve("run-004");
        assertTrue(Files.exists(dir.resolve("snap.png")));
        assertTrue(Files.exists(dir.resolve("clip.mp4")));

        List<AttachmentInfo> atts = sac.captured()[0].get(0).getAttachments();
        assertEquals("attachments/run-004/snap.png", atts.get(0).getPath());
        assertEquals("attachments/run-004/clip.mp4", atts.get(1).getPath());
    }

    @Test
    void pathNotRewrittenWhenSourceMissing() throws Exception {
        // Only snap.png exists; clip.mp4 does not
        Files.write(resultsDir.resolve("snap.png"), new byte[]{1});

        AttachmentInfo png = new AttachmentInfo("Screenshot", "image/png",  "snap.png");
        AttachmentInfo mp4 = new AttachmentInfo("Video",      "video/mp4",  "clip.mp4");
        ScenarioResult scenario = new ScenarioResult("sc-4", "Partial", "failed",
                "PT2S", null, List.of(), List.of(), List.of(png, mp4));

        var sac = stageFor(List.of(scenario));
        sac.stage().execute(contextFor("run-005"));

        List<AttachmentInfo> atts = sac.captured()[0].get(0).getAttachments();
        assertEquals("attachments/run-005/snap.png", atts.get(0).getPath()); // rewritten
        assertEquals("clip.mp4",                     atts.get(1).getPath()); // original kept
    }
}
