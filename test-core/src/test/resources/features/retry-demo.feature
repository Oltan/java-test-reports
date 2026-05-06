@RetryDemo @Flaky
Feature: Retry Demonstration

  @smoke @id:Stable @dep:FlakyOne @DOORS-20001
  Scenario: Always passes
    Given a stable step
    Then it should pass

  @smoke @id:FlakyOne @DOORS-20002
  Scenario: Fails first time, passes on retry
    Given a flaky step that fails once
    Then it should eventually pass
