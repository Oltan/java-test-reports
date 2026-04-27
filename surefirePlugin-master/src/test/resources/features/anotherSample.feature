@İmamBayıldı
Feature: Flaky Demo

  Scenario: Always passes
    Given a stable step
    Then this step always passes

  Scenario: Sometimes fails but retries
    Given a flaky step
    Then this step eventually passes

  Scenario: Always passes running again
    Given a stable step
    Then this step always passes
