package com.testreports.extent;

import com.aventstack.extentreports.ExtentReports;
import com.aventstack.extentreports.reporter.ExtentSparkReporter;
import com.aventstack.extentreports.reporter.configuration.Theme;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ExtentReportManager {

    private static volatile ExtentReports instance;

    private ExtentReportManager() {}

    public static ExtentReports getInstance() {
        if (instance == null) {
            synchronized (ExtentReportManager.class) {
                if (instance == null) {
                    instance = create();
                }
            }
        }
        return instance;
    }

    private static ExtentReports create() {
        Properties props = loadProperties();
        String out       = props.getProperty("extent.reporter.spark.out",   "target/extent-reports/index.html");
        String name      = props.getProperty("extent.reporter.spark.name",  "Test Execution Report");
        String themeStr  = props.getProperty("extent.reporter.spark.theme", "DARK").toUpperCase();

        ExtentSparkReporter spark = new ExtentSparkReporter(out);
        spark.config().setReportName(name);
        spark.config().setEncoding("UTF-8");
        try {
            spark.config().setTheme(Theme.valueOf(themeStr));
        } catch (IllegalArgumentException e) {
            spark.config().setTheme(Theme.DARK);
        }

        ExtentReports reports = new ExtentReports();
        reports.attachReporter(spark);
        reports.setSystemInfo("Framework", "Cucumber 7 + JUnit Platform");
        return reports;
    }

    private static Properties loadProperties() {
        Properties p = new Properties();
        try (InputStream is = ExtentReportManager.class
                .getClassLoader().getResourceAsStream("extent.properties")) {
            if (is != null) p.load(is);
        } catch (IOException ignored) {}
        return p;
    }

    /** Writes the report to disk. Called by the plugin's TestRunFinished handler. */
    public static void flush() {
        ExtentReports r = instance;
        if (r != null) r.flush();
    }

    /** Resets the singleton — for testing only. */
    static void reset() {
        instance = null;
    }
}
