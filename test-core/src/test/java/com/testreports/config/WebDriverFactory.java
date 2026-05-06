package com.testreports.config;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;

public class WebDriverFactory {

    private static final String CHROME_PATH = "/usr/bin/google-chrome-stable";
    private static final String CHROMEDRIVER_PATH = "/tmp/chromedriver-linux64/chromedriver";

    public static WebDriver createDriver() {
        ChromeOptions options = new ChromeOptions();
        options.setBinary(CHROME_PATH);
        options.addArguments("--headless=new");
        options.addArguments("--no-sandbox");
        options.addArguments("--disable-gpu");
        options.addArguments("--disable-dev-shm-usage");

        System.setProperty("webdriver.chrome.driver", CHROMEDRIVER_PATH);

        return new ChromeDriver(options);
    }
}