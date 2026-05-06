package com.testreports.allure;

import io.cucumber.java.Scenario;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

public class AllureHooksTest {

    @Test
    public void screenshotHook_doesNotAttachOnPassedScenario() {
        WebDriverHolder.removeDriver();

        Scenario scenario = mock(Scenario.class);
        when(scenario.isFailed()).thenReturn(false);

        ScreenshotHook hook = new ScreenshotHook();
        hook.captureScreenshot(scenario);

        verify(scenario).isFailed();
    }

    @Test
    public void videoHook_noExceptionWhenFfmpegNotFound() {
        VideoHook hook = new VideoHook();
        AtomicReference<Process> processRef = new AtomicReference<>();

        assertDoesNotThrow(() -> {
            Scenario scenario = mock(Scenario.class);
            when(scenario.getName()).thenReturn("test-scenario");
            hook.startVideoRecording(scenario);
            hook.stopVideoRecording(scenario);
        });
    }
}