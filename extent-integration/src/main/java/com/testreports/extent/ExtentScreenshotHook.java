package com.testreports.extent;

import com.aventstack.extentreports.ExtentTest;
import com.testreports.allure.WebDriverHolder;
import io.cucumber.java.After;
import io.cucumber.java.Scenario;
import org.openqa.selenium.OutputType;
import org.openqa.selenium.TakesScreenshot;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebDriverException;

/**
 * Captures a Base64 screenshot on failure and attaches it to the current
 * scenario's ExtentTest node via {@link ExtentTestHolder}.
 *
 * order=99 runs just before Allure's ScreenshotHook (order=100), so both
 * plugins capture the screen in the same browser state.
 */
public class ExtentScreenshotHook {

    @After(order = 99)
    public void captureScreenshot(Scenario scenario) {
        if (!scenario.isFailed()) return;

        WebDriver driver = WebDriverHolder.getDriver();
        if (!(driver instanceof TakesScreenshot takesScreenshot)) return;

        ExtentTest test = ExtentTestHolder.get();
        if (test == null) return;

        try {
            String base64 = takesScreenshot.getScreenshotAs(OutputType.BASE64);
            test.addScreenCaptureFromBase64String(base64, "Failure Screenshot");
        } catch (WebDriverException e) {
            test.warning("Screenshot capture failed: " + e.getMessage());
        }
    }
}
