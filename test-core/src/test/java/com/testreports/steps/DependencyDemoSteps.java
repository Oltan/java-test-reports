package com.testreports.steps;

import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import static org.junit.jupiter.api.Assertions.assertTrue;

public class DependencyDemoSteps {

    private boolean dbInitialized = false;
    private boolean userExists = false;
    private boolean loggedIn = false;

    @Given("the database is initialized")
    public void the_database_is_initialized() {
        dbInitialized = true;
    }

    @Then("setup is complete")
    public void setup_is_complete() {
        assertTrue(dbInitialized, "Database should be initialized");
    }

    @Given("a user exists")
    public void a_user_exists() {
        userExists = true;
    }

    @When("they log in")
    public void they_log_in() {
        assertTrue(userExists, "User must exist before logging in");
        loggedIn = true;
    }

    @Then("login succeeds")
    public void login_succeeds() {
        assertTrue(loggedIn, "User should be logged in");
    }

    @Given("the user is logged in")
    public void the_user_is_logged_in() {
        loggedIn = true;
    }

    @When("they visit dashboard")
    public void they_visit_dashboard() {
        assertTrue(loggedIn, "User must be logged in to visit dashboard");
    }

    @Then("dashboard displays correctly")
    public void dashboard_displays_correctly() {
        assertTrue(true, "Dashboard display check passed");
    }
}
