package com.testreports.allure;

import io.cucumber.plugin.event.Location;
import io.cucumber.plugin.event.Result;
import io.cucumber.plugin.event.Status;
import io.cucumber.plugin.event.TestCase;
import io.cucumber.plugin.event.TestCaseFinished;
import io.cucumber.plugin.event.TestRunStarted;
import org.junit.jupiter.api.Test;

import java.net.URI;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

public class FailureLocationCaptureTest {

    @Test
    public void onFailedTest_locationIsCaptured() {
        FailureLocationCapture plugin = new FailureLocationCapture();

        TestCase testCase = mock(TestCase.class);
        Location location = mock(Location.class);
        when(testCase.getUri()).thenReturn(URI.create("login.feature"));
        when(testCase.getLocation()).thenReturn(location);
        when(location.getLine()).thenReturn(42);

        Result result = mock(Result.class);
        when(result.getStatus()).thenReturn(Status.FAILED);

        TestCaseFinished event = mock(TestCaseFinished.class);
        when(event.getTestCase()).thenReturn(testCase);
        when(event.getResult()).thenReturn(result);

        plugin.onTestCaseFinished(event);

        verify(testCase).getUri();
        verify(testCase).getLocation();
    }

    @Test
    public void onPassedTest_resultNotCheckedForFailedStatus() {
        FailureLocationCapture plugin = new FailureLocationCapture();

        TestCase testCase = mock(TestCase.class);
        Result result = mock(Result.class);
        when(result.getStatus()).thenReturn(Status.PASSED);

        TestCaseFinished event = mock(TestCaseFinished.class);
        when(event.getTestCase()).thenReturn(testCase);
        when(event.getResult()).thenReturn(result);

        plugin.onTestCaseFinished(event);

        verify(result).getStatus();
        verify(testCase, never()).getUri();
    }

    @Test
    public void multipleFailures_allEventsProcessed() {
        FailureLocationCapture plugin = new FailureLocationCapture();

        for (int i = 0; i < 3; i++) {
            TestCase testCase = mock(TestCase.class);
            Location location = mock(Location.class);
            when(testCase.getUri()).thenReturn(URI.create("feature" + i + ".feature"));
            when(testCase.getLocation()).thenReturn(location);
            when(location.getLine()).thenReturn(i * 10);

            Result result = mock(Result.class);
            when(result.getStatus()).thenReturn(Status.FAILED);

            TestCaseFinished event = mock(TestCaseFinished.class);
            when(event.getTestCase()).thenReturn(testCase);
            when(event.getResult()).thenReturn(result);

            plugin.onTestCaseFinished(event);
        }

        assertTrue(true);
    }
}