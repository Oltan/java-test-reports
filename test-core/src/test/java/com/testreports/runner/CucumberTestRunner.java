package com.testreports.runner;

import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;
import org.junit.jupiter.api.condition.DisabledIfSystemProperty;

@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")
@DisabledIfSystemProperty(named = "retry.count", matches = "^[1-9].*$")
public class CucumberTestRunner {
}
