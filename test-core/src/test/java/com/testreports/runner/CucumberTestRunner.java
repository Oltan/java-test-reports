package com.testreports.runner;

import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;
import org.junit.jupiter.api.condition.DisabledIfSystemProperty;

// Plugin/glue defaults live in src/test/resources/cucumber.properties so that
// -Dcucumber.plugin / -Dcucumber.glue system properties can override them.
// (@ConfigurationParameter would take precedence over system properties.)
@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")
@DisabledIfSystemProperty(named = "retry.count", matches = "^[1-9].*$")
public class CucumberTestRunner {
}
