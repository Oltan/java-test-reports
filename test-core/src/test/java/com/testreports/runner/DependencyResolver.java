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

/**
 * Single home for scenario dependency logic: parsing {@code @id:X} / {@code @dep:a,b} tags out of
 * Gherkin feature files and ordering scenarios topologically by their declared dependencies.
 */
public final class DependencyResolver {

    private static final Logger LOGGER = Logger.getLogger(DependencyResolver.class.getName());

    private static final Pattern TAG_LINE = Pattern.compile("^\\s*@.+$");
    private static final Pattern ID_TAG = Pattern.compile("@id:([^\\s@]+)");
    private static final Pattern DEP_TAG = Pattern.compile("@dep:([^\\s@]+)");
    private static final Pattern SCENARIO_LINE = Pattern.compile("^\\s*Scenario(?: Outline| Template)?\\s*:\\s*(.+)\\s*$");

    private DependencyResolver() {
    }

    /**
     * Metadata for a single scenario. {@code id} is the explicit {@code @id:} tag value, falling
     * back to the scenario name when no {@code @id:} tag is present.
     */
    public record ScenarioMeta(String name, String id, Set<String> dependencies) {
    }

    /**
     * Result of a lenient topological sort.
     *
     * @param ordered every node of the graph exactly once: acyclic nodes first in dependency
     *                order, then any cycle-affected nodes appended in graph insertion order
     * @param cyclic  the nodes that could not be ordered (members of a dependency cycle, or
     *                nodes that transitively depend on one); empty when the graph is acyclic
     */
    public record SortOutcome(List<String> ordered, List<String> cyclic) {
        public boolean hasCycle() {
            return !cyclic.isEmpty();
        }
    }

    /**
     * Parses all {@code .feature} files under {@code featuresDir} into a dependency graph keyed by
     * explicit {@code @id:} tag. Scenarios without an {@code @id:} tag are omitted, and a duplicate
     * explicit id is rejected.
     */
    public static Map<String, Set<String>> parseFeatureFiles(Path featuresDir) throws IOException {
        Map<String, Set<String>> graph = new LinkedHashMap<>();

        for (ParsedScenario scenario : parseScenarios(featuresDir)) {
            if (scenario.explicitId() == null) {
                continue;
            }
            if (graph.containsKey(scenario.explicitId())) {
                throw new IllegalArgumentException("Duplicate scenario id '" + scenario.explicitId() + "' in " + scenario.file());
            }
            graph.put(scenario.explicitId(), new LinkedHashSet<>(scenario.dependencies()));
        }

        return graph;
    }

    /**
     * Parses all {@code .feature} files under {@code featuresDir} into scenario metadata keyed by
     * scenario name (file order, first occurrence wins for position, last occurrence wins for
     * value). Unlike {@link #parseFeatureFiles(Path)}, every scenario is included; the id falls
     * back to the scenario name when no {@code @id:} tag is present.
     */
    public static Map<String, ScenarioMeta> parseScenarioMetadata(Path featuresDir) throws IOException {
        Map<String, ScenarioMeta> metadataByName = new LinkedHashMap<>();

        for (ParsedScenario scenario : parseScenarios(featuresDir)) {
            String id = scenario.explicitId() == null ? scenario.name() : scenario.explicitId();
            metadataByName.put(scenario.name(), new ScenarioMeta(scenario.name(), id, Set.copyOf(scenario.dependencies())));
        }

        return metadataByName;
    }

    /**
     * Strict topological sort: throws {@link IllegalStateException} when the graph contains a
     * dependency cycle.
     */
    public static List<String> topologicalSort(Map<String, Set<String>> graph) {
        SortOutcome outcome = sort(graph);
        if (outcome.hasCycle()) {
            throw new IllegalStateException("Dependency cycle detected: " + findCycle(graph, graph.keySet()));
        }
        return outcome.ordered();
    }

    /**
     * Lenient topological sort: instead of throwing on a cycle, returns all nodes (cycle-affected
     * nodes last, in graph insertion order) together with the set of nodes that could not be
     * ordered. Callers can decide how to surface the cycle to the user.
     */
    public static SortOutcome topologicalSortLenient(Map<String, Set<String>> graph) {
        return sort(graph);
    }

    private static SortOutcome sort(Map<String, Set<String>> graph) {
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

        if (ordered.size() == graph.size()) {
            return new SortOutcome(List.copyOf(ordered), List.of());
        }

        Set<String> sorted = new HashSet<>(ordered);
        List<String> cyclic = graph.keySet().stream().filter(id -> !sorted.contains(id)).toList();
        List<String> all = new ArrayList<>(ordered);
        all.addAll(cyclic);
        return new SortOutcome(List.copyOf(all), cyclic);
    }

    private record ParsedScenario(Path file, String name, String explicitId, Set<String> dependencies) {
    }

    private static List<ParsedScenario> parseScenarios(Path featuresDir) throws IOException {
        List<ParsedScenario> scenarios = new ArrayList<>();

        try (Stream<Path> paths = Files.walk(featuresDir)) {
            List<Path> featureFiles = paths
                    .filter(Files::isRegularFile)
                    .filter(path -> path.toString().endsWith(".feature"))
                    .sorted()
                    .toList();

            for (Path featureFile : featureFiles) {
                parseFeatureFile(featureFile, scenarios);
            }
        }

        return scenarios;
    }

    private static void parseFeatureFile(Path featureFile, List<ParsedScenario> sink) throws IOException {
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

            Matcher scenarioMatcher = SCENARIO_LINE.matcher(line);
            if (scenarioMatcher.matches()) {
                String name = scenarioMatcher.group(1).trim();
                sink.add(new ParsedScenario(featureFile, name, pendingId, new LinkedHashSet<>(pendingDependencies)));
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
