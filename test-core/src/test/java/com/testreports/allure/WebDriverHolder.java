package com.testreports.allure;

import org.openqa.selenium.WebDriver;

/**
 * Simple static holder for WebDriver instance.
 * Used by ScreenshotHook to get the current driver for screenshot capture.
 */
public final class WebDriverHolder {

    private static final ThreadLocal<WebDriver> driver = new ThreadLocal<>();

    private WebDriverHolder() {
        // Utility class
    }

    public static void setDriver(WebDriver webDriver) {
        driver.set(webDriver);
    }

    public static WebDriver getDriver() {
        return driver.get();
    }

    public static void removeDriver() {
        driver.remove();
    }
}