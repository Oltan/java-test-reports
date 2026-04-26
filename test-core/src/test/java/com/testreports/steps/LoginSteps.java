package com.testreports.steps;

import io.cucumber.java.After;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;
import io.qameta.allure.Feature;
import io.qameta.allure.Story;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.By;
import org.openqa.selenium.support.ui.WebDriverWait;
import org.junit.jupiter.api.Assertions;

import java.time.Duration;

@Feature("Kullanıcı Girişi")
@Story("Login")
public class LoginSteps {

    private WebDriver driver;

    @Given("user is on the login page")
    public void user_is_on_the_login_page() {
        driver = com.testreports.config.WebDriverFactory.createDriver();
        com.testreports.allure.WebDriverHolder.setDriver(driver);
        driver.get("https://example.com");
    }

    @When("user enters valid credentials")
    public void user_enters_valid_credentials() {
    }

    @Then("user should see the page title {string}")
    public void user_should_see_the_page_title(String expectedTitle) {
        WebDriverWait wait = new WebDriverWait(driver, Duration.ofSeconds(10));
        wait.until(d -> d.getTitle().contains(expectedTitle));
        Assertions.assertTrue(driver.getTitle().contains(expectedTitle));
    }

    @Then("user should see element that doesn't exist")
    public void user_should_see_element_that_doesnt_exist() {
        WebDriverWait wait = new WebDriverWait(driver, Duration.ofSeconds(5));
        wait.until(d -> d.findElement(By.id("this-element-does-not-exist-12345")));
    }

    @After(order = 1001)
    public void cleanup() {
        if (driver != null) {
            driver.quit();
        }
    }
}
