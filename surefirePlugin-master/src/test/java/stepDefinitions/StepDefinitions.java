package stepDefinitions;

import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class StepDefinitions {
    private static int counter = 0;
    private String currentUser;
    private String loginResult;

    @Given("a stable step")
    public void aStableStep() {
        System.out.println("Running stable step");
    }

    @Then("this step always passes")
    public void thisStepAlwaysPasses() {
        assertTrue(true);
    }

    @Given("a flaky step")
    public void aFlakyStep() {
        counter++;
        System.out.println("Running flaky step, attempt: " + counter);
        assertEquals(0, counter % 3, "Fails unless counter divisible by 3");
    }

    @Then("this step eventually passes")
    public void thisStepEventuallyPasses() {
        assertTrue(true);
    }

    @Given("I have a username {string}")
    public void i_have_a_username(String user) {
        currentUser = user;
        System.out.println("[Step] Got username: " + user);
    }

    @When("I try to login")
    public void i_try_to_login() {
        // Dummy login logic: only alice and charlie succeed
        if ("alice".equalsIgnoreCase(currentUser) || "charlie".equalsIgnoreCase(currentUser)) {
            loginResult = "success";
        } else {
            loginResult = "failure";
        }
        System.out.println("[Step] Login attempt for " + currentUser + " -> " + loginResult);
    }

    @Then("the login result should be {string}")
    public void the_login_result_should_be(String expected) {
        System.out.println("[Step] Expecting result = " + expected + ", actual = " + loginResult);
        assertEquals(expected, loginResult, "Login result mismatch!");
    }
}
