package com.testreports.runner;

import org.junit.platform.suite.api.ConfigurationParameter;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;
import org.junit.jupiter.api.condition.DisabledIfSystemProperty;

import static io.cucumber.junit.platform.engine.Constants.GLUE_PROPERTY_NAME;
import static io.cucumber.junit.platform.engine.Constants.PLUGIN_PROPERTY_NAME;

@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")
@DisabledIfSystemProperty(named = "retry.count", matches = "^[1-9].*$")
@ConfigurationParameter(key = PLUGIN_PROPERTY_NAME, value = "io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm,com.testreports.extent.ExtentCucumberPlugin,json:target/cucumber-report.json,pretty")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "com.testreports.allure,com.testreports.extent,com.testreports.steps")
public class CucumberTestRunner {
}
