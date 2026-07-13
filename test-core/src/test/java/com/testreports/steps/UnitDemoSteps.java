package com.testreports.steps;

import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class UnitDemoSteps {

    private String input;
    private String result;

    @Given("the input string {string}")
    public void the_input_string(String value) {
        input = value;
    }

    @When("it is upper-cased")
    public void it_is_upper_cased() {
        result = input.toUpperCase();
    }

    @When("it is trimmed")
    public void it_is_trimmed() {
        result = input.trim();
    }

    @When("it is reversed")
    public void it_is_reversed() {
        result = new StringBuilder(input).reverse().toString();
    }

    @Then("the unit result is {string}")
    public void the_unit_result_is(String expected) {
        assertEquals(expected, result, "Unit demo string transformation result");
    }
}
