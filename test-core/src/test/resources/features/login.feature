@DOORS-12345
@REQ-LOGIN-001
Feature: Login Feature

  @sample-fail
  Scenario: Hatalı giriş
    Given user is on the login page
    When user enters valid credentials
    Then user should see element that doesn't exist

  Scenario: Başarılı giriş
    Given user is on the login page
    When user enters valid credentials
    Then user should see the page title "Example Domain"