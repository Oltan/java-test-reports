package hooks;

import io.cucumber.plugin.ConcurrentEventListener;
import io.cucumber.plugin.event.*;
import java.net.URI;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

/**
 * Captures failed test case locations (feature-file path with :line).
 * Used by the retry runner to rerun only failed example rows for Scenario Outlines.
 */
public class FailureCapturePlugin implements ConcurrentEventListener {

    private static final Set<String> FAILED_LOCATIONS = new LinkedHashSet<>();
    private static final Object LOCK = new Object();

    @Override
    public void setEventPublisher(EventPublisher publisher) {
        publisher.registerHandlerFor(TestRunStarted.class, event -> reset());
        publisher.registerHandlerFor(TestCaseFinished.class, this::onFinished);
    }

    private void onFinished(TestCaseFinished event) {
        if (event.getResult().getStatus() == io.cucumber.plugin.event.Status.FAILED) {
            TestCase tc = event.getTestCase();
            String loc = toLocation(tc.getUri(), tc.getLocation().getLine());
            synchronized (LOCK) {
                FAILED_LOCATIONS.add(loc);
            }
        }
    }

    private static String toLocation(URI uri, int line) {
        try {
            Path p = Paths.get(uri);
            return p.toString() + ":" + line;
        } catch (Exception e) {
            return String.valueOf(uri) + ":" + line;
        }
    }

    public static void reset() {
        synchronized (LOCK) {
            FAILED_LOCATIONS.clear();
        }
    }

    public static List<String> getFailedLocations() {
        synchronized (LOCK) {
            return new ArrayList<>(FAILED_LOCATIONS);
        }
    }
}