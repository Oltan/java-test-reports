package com.testreports.allure;

import io.cucumber.java.After;
import io.cucumber.java.Scenario;
import io.qameta.allure.Allure;
import org.openqa.selenium.OutputType;
import org.openqa.selenium.TakesScreenshot;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebDriverException;

import java.io.ByteArrayInputStream;

public class ScreenshotHook {

    @After(order = 100)
    public void captureScreenshot(Scenario scenario) {
        if (!scenario.isFailed()) {
            return;
        }

        WebDriver driver = WebDriverHolder.getDriver();
        if (driver == null) {
            System.err.println("ScreenshotHook: WebDriver is null, cannot capture screenshot");
            return;
        }

        if (!(driver instanceof TakesScreenshot)) {
            System.err.println("ScreenshotHook: WebDriver does not support screenshots");
            return;
        }

        try {
            byte[] screenshot = ((TakesScreenshot) driver).getScreenshotAs(OutputType.BYTES);
            Allure.addAttachment("Screenshot", "image/png", new ByteArrayInputStream(screenshot), "png");
        } catch (WebDriverException e) {
            System.err.println("ScreenshotHook: Failed to capture screenshot: " + e.getMessage());
        }
    }
}