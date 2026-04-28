package com.testreports.runner;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.Set;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public final class DependencyResolver {

    private static final Logger LOGGER = Logger.getLogger(DependencyResolver.class.getName());

    private static final Pattern TAG_LINE = Pattern.compile("^\\s*@.+$");
    private static final Pattern ID_TAG = Pattern.compile("@id:([^\\s@]+)");
    private static final Pattern DEP_TAG = Pattern.compile("@dep:([^\\s@]+)");
    private static final Pattern SCENARIO_LINE = Pattern.compile("^\\s*Scenario(?: Outline| Template)?\\s*:.+$");

    private DependencyResolver() {
    }

    public static Map<String, Set<String>> parseFeatureFiles(Path featuresDir) throws IOException {
        Map<String, Set<String>> graph = new LinkedHashMap<>();

        try (Stream<Path> paths = Files.walk(featuresDir)) {
            List<Path> featureFiles = paths
                    .filter(Files::isRegularFile)
                    .filter(path -> path.toString().endsWith(".feature"))
                    .sorted()
                    .toList();

            for (Path featureFile : featureFiles) {
                parseFeatureFile(featureFile, graph);
            }
        }

        return graph;
    }

    public static List<String> topologicalSort(Map<String, Set<String>> graph) {
        Map<String, Integer> indegree = new LinkedHashMap<>();
        Map<String, Set<String>> dependents = new HashMap<>();

        for (String id : graph.keySet()) {
            indegree.put(id, 0);
            dependents.put(id, new LinkedHashSet<>());
        }

        for (Map.Entry<String, Set<String>> entry : graph.entrySet()) {
            String id = entry.getKey();
            for (String dependency : entry.getValue()) {
                if (!graph.containsKey(dependency)) {
                    LOGGER.warning("Unresolved dependency '" + dependency + "' referenced by scenario '" + id + "'; ignoring it for ordering.");
                    continue;
                }

                dependents.get(dependency).add(id);
                indegree.compute(id, (key, value) -> value + 1);
            }
        }

        Queue<String> ready = new ArrayDeque<>();
        for (Map.Entry<String, Integer> entry : indegree.entrySet()) {
            if (entry.getValue() == 0) {
                ready.add(entry.getKey());
            }
        }

        List<String> ordered = new ArrayList<>();
        while (!ready.isEmpty()) {
            String id = ready.remove();
            ordered.add(id);

            for (String dependent : dependents.getOrDefault(id, Set.of())) {
                int updated = indegree.compute(dependent, (key, value) -> value - 1);
                if (updated == 0) {
                    ready.add(dependent);
                }
            }
        }

        if (ordered.size() != graph.size()) {
            throw new IllegalStateException("Dependency cycle detected: " + findCycle(graph, indegree.keySet()));
        }

        return ordered;
    }

    private static void parseFeatureFile(Path featureFile, Map<String, Set<String>> graph) throws IOException {
        String pendingId = null;
        Set<String> pendingDependencies = new LinkedHashSet<>();

        for (String rawLine : Files.readAllLines(featureFile, StandardCharsets.UTF_8)) {
            String line = rawLine.trim();

            if (TAG_LINE.matcher(line).matches()) {
                Matcher idMatcher = ID_TAG.matcher(line);
                if (idMatcher.find()) {
                    pendingId = idMatcher.group(1).trim();
                }

                Matcher dependencyMatcher = DEP_TAG.matcher(line);
                while (dependencyMatcher.find()) {
                    for (String dependency : dependencyMatcher.group(1).split(",")) {
                        String normalizedDependency = dependency.trim();
                        if (!normalizedDependency.isEmpty()) {
                            pendingDependencies.add(normalizedDependency);
                        }
                    }
                }
                continue;
            }

            if (SCENARIO_LINE.matcher(line).matches()) {
                if (pendingId != null) {
                    if (graph.containsKey(pendingId)) {
                        throw new IllegalArgumentException("Duplicate scenario id '" + pendingId + "' in " + featureFile);
                    }
                    graph.put(pendingId, new LinkedHashSet<>(pendingDependencies));
                }
                pendingId = null;
                pendingDependencies.clear();
                continue;
            }

            if (!line.isEmpty() && !line.startsWith("#")) {
                pendingId = null;
                pendingDependencies.clear();
            }
        }
    }

    private static String findCycle(Map<String, Set<String>> graph, Set<String> nodes) {
        Set<String> visited = new HashSet<>();
        Set<String> visiting = new HashSet<>();
        List<String> stack = new ArrayList<>();

        for (String node : nodes) {
            List<String> cycle = findCycleFrom(node, graph, visited, visiting, stack);
            if (!cycle.isEmpty()) {
                return String.join(" -> ", cycle);
            }
        }

        return "remaining nodes " + nodes;
    }

    private static List<String> findCycleFrom(
            String node,
            Map<String, Set<String>> graph,
            Set<String> visited,
            Set<String> visiting,
            List<String> stack
    ) {
        if (visited.contains(node)) {
            return List.of();
        }

        if (visiting.contains(node)) {
            int start = stack.indexOf(node);
            List<String> cycle = new ArrayList<>(stack.subList(start, stack.size()));
            cycle.add(node);
            return cycle;
        }

        visiting.add(node);
        stack.add(node);
        for (String dependency : graph.getOrDefault(node, Set.of())) {
            if (!graph.containsKey(dependency)) {
                continue;
            }
            List<String> cycle = findCycleFrom(dependency, graph, visited, visiting, stack);
            if (!cycle.isEmpty()) {
                return cycle;
            }
        }
        stack.remove(stack.size() - 1);
        visiting.remove(node);
        visited.add(node);
        return List.of();
    }
}
