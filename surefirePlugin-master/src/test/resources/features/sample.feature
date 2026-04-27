@Deneme
Feature: Retry showcase with durable state


  Scenario: Background_Pre condition scenario execution
    Given I ping the health endpoint
    Then I get status "OK"

  @id:CleanCase
  @dep:Login
  Scenario: Health endpoint returns OK
    Given I ping the health endpoint
    Then I get status "OK"

  @id:OneTimeFlake
  Scenario: Background job eventually succeeds
    Given a background job starts
    Then it completes after one retry

  @id:Login
  @dep:OneTimeFlake
  Scenario Outline: Login with different users
    Given I have a username "<user>"
    When I try to login
    Then the login result should be "<expected>"

    Examples:
      | user    | expected |
      | alice   | success  |
      | charlie | failure  |
      | bob     | failure  |




