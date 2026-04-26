package com.testreports.config;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;

public class WebDriverFactory {

    private static final String CHROME_PATH = "/tmp/chrome-linux64/chrome";
    private static final String CHROMEDRIVER_PATH = "/tmp/chromedriver-linux64/chromedriver";

    public static WebDriver createDriver() {
        ChromeOptions options = new ChromeOptions();
        options.setBinary(CHROME_PATH);
        options.addArguments("--headless=new");
        options.addArguments("--disable-gpu");
        options.addArguments("--no-sandbox");
        options.addArguments("--disable-dev-shm-usage");
        options.addArguments("--remote-debugging-port=9222");
        options.addArguments("--disable-crash-reporter");
        options.addArguments("--disable-breakpad");
        options.addArguments("--disable-in-process-stack-traces");
        options.addArguments("--no-zygote");
        options.addArguments("--single-process");
        options.addArguments("--user-data-dir=/tmp/chrome-test-data");

        System.setProperty("webdriver.chrome.driver", CHROMEDRIVER_PATH);

        return new ChromeDriver(options);
    }
}