package com.testreports.extent;

import com.aventstack.extentreports.ExtentReports;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ExtentReportManagerTest {

    @AfterEach
    void resetSingleton() {
        ExtentReportManager.reset();
    }

    @Test
    void instanceIsNotNull() {
        assertNotNull(ExtentReportManager.getInstance());
    }

    @Test
    void sameInstanceReturnedOnEveryCall() {
        ExtentReports first  = ExtentReportManager.getInstance();
        ExtentReports second = ExtentReportManager.getInstance();
        assertSame(first, second, "getInstance() must return the same singleton");
    }

    @Test
    void flushDoesNotThrowWhenInstanceExists() {
        ExtentReportManager.getInstance();
        assertDoesNotThrow(ExtentReportManager::flush);
    }

    @Test
    void flushDoesNotThrowWhenNoInstanceYet() {
        assertDoesNotThrow(ExtentReportManager::flush);
    }

    @Test
    void resetClearsTheSingleton() {
        ExtentReports first = ExtentReportManager.getInstance();
        ExtentReportManager.reset();
        ExtentReports second = ExtentReportManager.getInstance();
        assertNotSame(first, second, "reset() should force a new instance to be created");
    }
}
