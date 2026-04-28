@RetryDemo @Flaky
Feature: Retry Demonstration

  @id:Stable @dep:FlakyOne
  Scenario: Always passes
    Given a stable step
    Then it should pass

  @id:FlakyOne
  Scenario: Fails first time, passes on retry
    Given a flaky step that fails once
    Then it should eventually pass
