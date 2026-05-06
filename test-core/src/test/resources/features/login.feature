@REQ-LOGIN-001
Feature: Login Feature

  @smoke @sample-fail @DOORS-30001
  Scenario: Hatalı giriş
    Given user is on the login page
    When user enters valid credentials
    Then user should see element that doesn't exist

  @smoke @DOORS-30002
  Scenario: Başarılı giriş
    Given user is on the login page
    When user enters valid credentials
    Then user should see the page title "Example Domain"
