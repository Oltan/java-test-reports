package com.testreports.runner;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DependencyResolverTest {

    @TempDir
    Path tempDir;

    @Test
    void parseFeatureFilesFindsIdsAndDependencies() throws IOException {
        writeFeature("sample.feature", """
                Feature: Sample

                  @id:Setup
                  Scenario: Setup data
                    Given setup exists

                  @id:Login @dep:Setup
                  Scenario: Login
                    Given a user logs in

                  @id:Dashboard @dep:Login,Setup
                  Scenario: Dashboard
                    Given dashboard is opened
                """);

        Map<String, Set<String>> graph = DependencyResolver.parseFeatureFiles(tempDir);

        assertEquals(Set.of(), graph.get("Setup"));
        assertEquals(linkedSet("Setup"), graph.get("Login"));
        assertEquals(linkedSet("Login", "Setup"), graph.get("Dashboard"));
    }

    @Test
    void topologicalSortProducesDependencyOrder() {
        Map<String, Set<String>> graph = new LinkedHashMap<>();
        graph.put("Dashboard", linkedSet("Login", "Setup"));
        graph.put("Login", linkedSet("Setup"));
        graph.put("Setup", Set.of());

        List<String> order = DependencyResolver.topologicalSort(graph);

        assertTrue(order.indexOf("Setup") < order.indexOf("Login"));
        assertTrue(order.indexOf("Login") < order.indexOf("Dashboard"));
        assertEquals(Set.of("Setup", "Login", "Dashboard"), new LinkedHashSet<>(order));
    }

    @Test
    void topologicalSortThrowsWhenCycleExists() {
        Map<String, Set<String>> graph = new LinkedHashMap<>();
        graph.put("A", linkedSet("B"));
        graph.put("B", linkedSet("C"));
        graph.put("C", linkedSet("A"));

        IllegalStateException exception = assertThrows(
                IllegalStateException.class,
                () -> DependencyResolver.topologicalSort(graph)
        );

        assertTrue(exception.getMessage().contains("Dependency cycle detected"));
        assertTrue(exception.getMessage().contains("A"));
        assertTrue(exception.getMessage().contains("B"));
        assertTrue(exception.getMessage().contains("C"));
    }

    @Test
    void missingDependencyWarnsAndDoesNotBlockOrdering() {
        Logger logger = Logger.getLogger(DependencyResolver.class.getName());
        RecordingHandler handler = new RecordingHandler();
        logger.addHandler(handler);

        try {
            Map<String, Set<String>> graph = new LinkedHashMap<>();
            graph.put("Login", linkedSet("MissingSetup"));
            graph.put("Dashboard", linkedSet("Login"));

            List<String> order = DependencyResolver.topologicalSort(graph);

            assertEquals(List.of("Login", "Dashboard"), order);
            assertTrue(handler.messages.stream().anyMatch(message -> message.contains("Unresolved dependency 'MissingSetup'")));
        } finally {
            logger.removeHandler(handler);
        }
    }

    @Test
    void topologicalSortReturnsAllItemsWhenNoDependenciesExist() {
        Map<String, Set<String>> graph = new LinkedHashMap<>();
        graph.put("Setup", Set.of());
        graph.put("Login", Set.of());
        graph.put("Dashboard", Set.of());

        List<String> order = DependencyResolver.topologicalSort(graph);

        assertEquals(List.of("Setup", "Login", "Dashboard"), order);
    }

    @Test
    void parseScenarioMetadataIncludesAllScenariosAndDefaultsIdToName() throws IOException {
        writeFeature("metadata.feature", """
                @FeatureLevelTag
                Feature: Metadata sample

                  @id:Setup
                  Scenario: Setup data
                    Given setup exists

                  @smoke @id:Login @dep:Setup @DOORS-1
                  Scenario: Login
                    Given a user logs in

                  Scenario: Untagged scenario
                    Given nothing special
                """);

        Map<String, DependencyResolver.ScenarioMeta> metadata = DependencyResolver.parseScenarioMetadata(tempDir);

        assertEquals(List.of("Setup data", "Login", "Untagged scenario"), new ArrayList<>(metadata.keySet()));

        assertEquals("Setup", metadata.get("Setup data").id());
        assertEquals(Set.of(), metadata.get("Setup data").dependencies());

        assertEquals("Login", metadata.get("Login").id());
        assertEquals(Set.of("Setup"), metadata.get("Login").dependencies());

        // Scenarios without an @id tag fall back to the scenario name as id.
        assertEquals("Untagged scenario", metadata.get("Untagged scenario").id());
        assertEquals(Set.of(), metadata.get("Untagged scenario").dependencies());
    }

    @Test
    void topologicalSortLenientMatchesStrictSortWhenGraphIsAcyclic() {
        Map<String, Set<String>> graph = new LinkedHashMap<>();
        graph.put("Dashboard", linkedSet("Login", "Setup"));
        graph.put("Login", linkedSet("Setup"));
        graph.put("Setup", Set.of());

        DependencyResolver.SortOutcome outcome = DependencyResolver.topologicalSortLenient(graph);

        assertFalse(outcome.hasCycle());
        assertEquals(List.of(), outcome.cyclic());
        assertEquals(DependencyResolver.topologicalSort(graph), outcome.ordered());
    }

    @Test
    void topologicalSortLenientKeepsCycleMembersAtEndInsteadOfThrowing() {
        Map<String, Set<String>> graph = new LinkedHashMap<>();
        graph.put("A", linkedSet("B"));
        graph.put("B", linkedSet("A"));
        graph.put("C", linkedSet("A"));
        graph.put("D", Set.of());

        DependencyResolver.SortOutcome outcome = DependencyResolver.topologicalSortLenient(graph);

        assertTrue(outcome.hasCycle());
        // Cycle members and their transitive dependents cannot be ordered.
        assertEquals(List.of("A", "B", "C"), outcome.cyclic());
        // Every node still appears exactly once: sortable nodes first, then the cyclic remainder.
        assertEquals(List.of("D", "A", "B", "C"), outcome.ordered());
    }

    private void writeFeature(String fileName, String content) throws IOException {
        Files.writeString(tempDir.resolve(fileName), content, StandardCharsets.UTF_8);
    }

    private static Set<String> linkedSet(String... values) {
        return new LinkedHashSet<>(List.of(values));
    }

    private static final class RecordingHandler extends Handler {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (record.getLevel().intValue() >= Level.WARNING.intValue()) {
                messages.add(record.getMessage());
            }
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }
    }
}
