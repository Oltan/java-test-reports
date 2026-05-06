package com.testreports.allure;

import io.cucumber.plugin.ConcurrentEventListener;
import io.cucumber.plugin.event.EventPublisher;
import io.cucumber.plugin.event.TestCase;
import io.cucumber.plugin.event.TestCaseFinished;
import io.cucumber.plugin.event.TestRunStarted;
import io.qameta.allure.Allure;

import java.net.URI;

/**
 * Captures failed test case location (feature:line) and adds it as an Allure label.
 */
public class FailureLocationCapture implements ConcurrentEventListener {

    private static final Object LOCK = new Object();

    @Override
    public void setEventPublisher(EventPublisher publisher) {
        publisher.registerHandlerFor(TestRunStarted.class, event -> reset());
        publisher.registerHandlerFor(TestCaseFinished.class, this::onTestCaseFinished);
    }

    void onTestCaseFinished(TestCaseFinished event) {
        if (event.getResult().getStatus() == io.cucumber.plugin.event.Status.FAILED) {
            TestCase testCase = event.getTestCase();
            String location = toLocation(testCase.getUri(), testCase.getLocation().getLine());
            synchronized (LOCK) {
                Allure.label("failure_location", location);
                Allure.description("Failed at: " + location);
            }
        }
    }

    private static String toLocation(URI uri, int line) {
        return uri.toString() + ":" + line;
    }

    public static void reset() {
    }
}