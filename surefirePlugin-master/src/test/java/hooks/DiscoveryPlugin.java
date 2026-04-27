package hooks;

import io.cucumber.plugin.ConcurrentEventListener;
import io.cucumber.plugin.event.EventPublisher;
import io.cucumber.plugin.event.TestCaseStarted;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * Discovery-only plugin.
 * When Cucumber is run with --dry-run and optional --tags, this plugin collects
 * the names of the scenarios that would run. Use it to drive a retry runner so
 * you don't invoke Cucumber for scenarios that don't match the tag filter.
 */
public class DiscoveryPlugin implements ConcurrentEventListener {

    // Preserve insertion order and deduplicate by scenario name
    private static final Set<String> DISCOVERED = new LinkedHashSet<>();

    @Override
    public void setEventPublisher(EventPublisher publisher) {
        publisher.registerHandlerFor(io.cucumber.plugin.event.TestRunStarted.class, event -> {
            synchronized (DISCOVERED) {
                DISCOVERED.clear();
            }
        });

        publisher.registerHandlerFor(TestCaseStarted.class, event -> {
            String name = event.getTestCase().getName();
            synchronized (DISCOVERED) {
                DISCOVERED.add(name);
            }
        });
    }

    public static List<String> getDiscoveredScenarioNames() {
        synchronized (DISCOVERED) {
            return new ArrayList<>(DISCOVERED);
        }
    }
}