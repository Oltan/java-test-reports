package com.testreports.allure;

import io.cucumber.java.After;
import io.cucumber.java.Before;
import io.cucumber.java.Scenario;
import io.qameta.allure.Allure;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Level;
import java.util.logging.Logger;

public class VideoHook {

    private static final Logger LOGGER = Logger.getLogger(VideoHook.class.getName());

    private static final Path VIDEO_DIR = Paths.get("target/videos");
    private static final DateTimeFormatter TIMESTAMP_FORMAT = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");

    private final AtomicReference<Process> ffmpegProcess = new AtomicReference<>();
    private final AtomicReference<Path> currentVideoPath = new AtomicReference<>();

    @Before(order = 1)
    public void startVideoRecording(Scenario scenario) {
        createVideoDirectory();

        String timestamp = LocalDateTime.now().format(TIMESTAMP_FORMAT);
        String sanitizedName = scenario.getName().replaceAll("[^a-zA-Z0-9_-]", "_");
        Path videoPath = VIDEO_DIR.resolve(sanitizedName + "_" + timestamp + ".mp4");

        try {
            ProcessBuilder pb = new ProcessBuilder(
                    "ffmpeg",
                    "-f", "x11grab",
                    "-framerate", "15",
                    "-video_size", "1920x1080",
                    "-i", ":0.0",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    "-y",
                    videoPath.toString()
            );
            pb.redirectErrorStream(true);
            Process process = pb.start();

            if (process.isAlive()) {
                ffmpegProcess.set(process);
                currentVideoPath.set(videoPath);
                LOGGER.info("VideoHook: Started video recording: " + videoPath);
            } else {
                LOGGER.warning("VideoHook: ffmpeg process not alive, possibly not installed");
            }
        } catch (IOException e) {
            if (isFfmpegNotFound(e)) {
                LOGGER.info("VideoHook: ffmpeg not found - video recording disabled");
            } else {
                LOGGER.log(Level.WARNING, "VideoHook: Failed to start video recording: " + e.getMessage());
            }
        }
    }

    @After(order = 200)
    public void stopVideoRecording(Scenario scenario) {
        Process process = ffmpegProcess.getAndSet(null);
        if (process != null && process.isAlive()) {
            process.destroy();
try {
            boolean exited = process.waitFor() != 0;
            if (exited) {
                LOGGER.warning("VideoHook: ffmpeg process exited with non-zero code");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
        }
        }

        Path videoPath = currentVideoPath.getAndSet(null);
        if (videoPath == null) {
            return;
        }

        if (scenario.isFailed()) {
            attachVideo(videoPath);
        } else {
            deleteVideo(videoPath);
        }
    }

    private void createVideoDirectory() {
        try {
            Files.createDirectories(VIDEO_DIR);
        } catch (IOException e) {
            LOGGER.warning("VideoHook: Could not create video directory: " + e.getMessage());
        }
    }

    private boolean isFfmpegNotFound(IOException e) {
        return Optional.ofNullable(e.getCause())
                .map(Throwable::getMessage)
                .map(msg -> msg.contains("No such file") || msg.contains("Cannot find"))
                .orElse(false);
    }

    private void attachVideo(Path videoPath) {
        try {
            if (Files.exists(videoPath)) {
                byte[] videoBytes = Files.readAllBytes(videoPath);
                Allure.addAttachment("Video", "video/mp4", new ByteArrayInputStream(videoBytes), "mp4");
                LOGGER.info("VideoHook: Attached video: " + videoPath);
            }
        } catch (IOException e) {
            LOGGER.log(Level.WARNING, "VideoHook: Failed to attach video: " + e.getMessage());
        }
    }

    private void deleteVideo(Path videoPath) {
        try {
            if (Files.exists(videoPath)) {
                Files.delete(videoPath);
                LOGGER.info("VideoHook: Deleted video: " + videoPath);
            }
        } catch (IOException e) {
            LOGGER.log(Level.WARNING, "VideoHook: Failed to delete video: " + e.getMessage());
        }
    }
}