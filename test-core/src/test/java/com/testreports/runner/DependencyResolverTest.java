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
