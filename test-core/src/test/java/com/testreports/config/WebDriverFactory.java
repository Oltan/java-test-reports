package com.testreports.config;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.edge.EdgeDriver;
import org.openqa.selenium.edge.EdgeOptions;
import org.openqa.selenium.firefox.FirefoxDriver;
import org.openqa.selenium.firefox.FirefoxOptions;

import java.util.Locale;

/**
 * Creates {@link WebDriver} instances from system properties instead of
 * hardcoded, machine-specific paths.
 *
 * <p>Supported system properties:
 * <ul>
 *   <li>{@code browser} — {@code chrome} (default), {@code firefox} or {@code edge}</li>
 *   <li>{@code browser.headless} — {@code true} (default) or {@code false}</li>
 *   <li>{@code browser.binary} — optional path to the browser binary</li>
 *   <li>{@code webdriver.chrome.driver} (and the firefox/edge equivalents) —
 *       optional driver path, honored natively by Selenium when set; when
 *       absent, Selenium Manager resolves a matching driver automatically</li>
 * </ul>
 */
public class WebDriverFactory {

    public static WebDriver createDriver() {
        String browser = System.getProperty("browser", "chrome").trim().toLowerCase(Locale.ROOT);
        boolean headless = Boolean.parseBoolean(System.getProperty("browser.headless", "true"));
        String binary = System.getProperty("browser.binary");

        switch (browser) {
            case "chrome":
                return createChromeDriver(headless, binary);
            case "firefox":
                return createFirefoxDriver(headless, binary);
            case "edge":
                return createEdgeDriver(headless, binary);
            default:
                throw new IllegalArgumentException(
                        "Unsupported browser '" + browser + "'. Supported values: chrome, firefox, edge.");
        }
    }

    private static WebDriver createChromeDriver(boolean headless, String binary) {
        ChromeOptions options = new ChromeOptions();
        if (binary != null && !binary.isBlank()) {
            options.setBinary(binary);
        }
        if (headless) {
            options.addArguments("--headless=new");
        }
        options.addArguments("--no-sandbox");
        options.addArguments("--disable-gpu");
        options.addArguments("--disable-dev-shm-usage");
        // No System.setProperty here: Selenium honors -Dwebdriver.chrome.driver
        // when provided and otherwise falls back to Selenium Manager.
        return new ChromeDriver(options);
    }

    private static WebDriver createFirefoxDriver(boolean headless, String binary) {
        FirefoxOptions options = new FirefoxOptions();
        if (binary != null && !binary.isBlank()) {
            options.setBinary(binary);
        }
        if (headless) {
            options.addArguments("-headless");
        }
        return new FirefoxDriver(options);
    }

    private static WebDriver createEdgeDriver(boolean headless, String binary) {
        EdgeOptions options = new EdgeOptions();
        if (binary != null && !binary.isBlank()) {
            options.setBinary(binary);
        }
        if (headless) {
            options.addArguments("--headless=new");
        }
        return new EdgeDriver(options);
    }
}
