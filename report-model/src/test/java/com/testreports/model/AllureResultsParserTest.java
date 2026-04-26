package com.testreports.model;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class AllureResultsParserTest {

    @TempDir
    Path tempDir;

    @Test
    void testParseLoginFailedScenario() throws IOException {
        Path resourcesPath = Path.of("src/test/resources/allure-results");
        AllureResultsParser parser = new AllureResultsParser(resourcesPath);

        List<ScenarioResult> scenarios = parser.parse();

        ScenarioResult failedScenario = scenarios.stream()
            .filter(s -> s.getName().equals("Hatalı giriş"))
            .findFirst()
            .orElseThrow();

        assertEquals("failed", failedScenario.getStatus());
        assertEquals(4, failedScenario.getSteps().size());

        assertEquals("Kullanıcı yanlış şifre girer", failedScenario.getSteps().get(2).getName());
        assertEquals("passed", failedScenario.getSteps().get(2).getStatus());

        assertEquals("Beklenen hata mesajı gösterilmedi", failedScenario.getSteps().get(3).getErrorMessage());

        assertEquals(1, failedScenario.getAttachments().size());
        assertEquals("Ekran görüntüsü", failedScenario.getAttachments().get(0).getName());

        assertTrue(failedScenario.getTags().contains("@DOORS-12345"));
        assertTrue(failedScenario.getTags().contains("@sample-fail"));
        assertEquals("12345", failedScenario.getDoorsAbsNumber());
    }

    @Test
    void testParseLoginSuccessScenario() throws IOException {
        Path resourcesPath = Path.of("src/test/resources/allure-results");
        AllureResultsParser parser = new AllureResultsParser(resourcesPath);

        List<ScenarioResult> scenarios = parser.parse();

        ScenarioResult passedScenario = scenarios.stream()
            .filter(s -> s.getName().equals("Başarılı giriş"))
            .findFirst()
            .orElseThrow();

        assertEquals("passed", passedScenario.getStatus());
        assertEquals(4, passedScenario.getSteps().size());
        assertTrue(passedScenario.getSteps().stream().allMatch(s -> "passed".equals(s.getStatus())));

        assertTrue(passedScenario.getTags().contains("@DOORS-67890"));
        assertEquals("67890", passedScenario.getDoorsAbsNumber());
    }

    @Test
    void testParseSkippedScenario() throws IOException {
        Path resourcesPath = Path.of("src/test/resources/allure-results");
        AllureResultsParser parser = new AllureResultsParser(resourcesPath);

        List<ScenarioResult> scenarios = parser.parse();

        ScenarioResult skippedScenario = scenarios.stream()
            .filter(s -> s.getName().equals("Senaryo atlandı"))
            .findFirst()
            .orElseThrow();

        assertEquals("skipped", skippedScenario.getStatus());
        assertTrue(skippedScenario.getSteps().isEmpty());
    }

    @Test
    void testAllScenariosHaveIds() throws IOException {
        Path resourcesPath = Path.of("src/test/resources/allure-results");
        AllureResultsParser parser = new AllureResultsParser(resourcesPath);

        List<ScenarioResult> scenarios = parser.parse();

        assertEquals(3, scenarios.size());
        for (ScenarioResult scenario : scenarios) {
            assertNotNull(scenario.getId());
            assertFalse(scenario.getId().isEmpty());
        }
    }

    @Test
    void testDoorsNumberExtracted() throws IOException {
        Path resourcesPath = Path.of("src/test/resources/allure-results");
        AllureResultsParser parser = new AllureResultsParser(resourcesPath);

        List<ScenarioResult> scenarios = parser.parse();

        ScenarioResult doorsScenario = scenarios.stream()
            .filter(s -> s.getDoorsAbsNumber() != null)
            .findFirst()
            .orElseThrow();

        assertEquals("12345", doorsScenario.getDoorsAbsNumber());
    }

    @Test
    void testNonExistentDirectoryThrows() {
        Path nonExistent = Path.of("/non/existent/path");
        AllureResultsParser parser = new AllureResultsParser(nonExistent);

        assertThrows(IOException.class, parser::parse);
    }
}