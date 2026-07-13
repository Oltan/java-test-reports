@UnitDemo
Feature: String utilities unit checks

  Browser gerektirmeyen saf birim-seviyesi Gherkin senaryolari.
  Ikinci senaryo triage/Jira akisini gostermek icin bilerek fail eder
  (login.feature'daki @sample-fail ile ayni amac, ancak tarayicisiz).

  @smoke @DOORS-40001
  Scenario: Uppercase conversion works
    Given the input string "merhaba"
    When it is upper-cased
    Then the unit result is "MERHABA"

  @smoke @sample-fail @DOORS-40002
  Scenario: Trim collapses inner whitespace (intentional failure)
    Given the input string "  a b  "
    When it is trimmed
    Then the unit result is "ab"

  @smoke @sample-fail @DOORS-40003
  Scenario: Reverse is idempotent (intentional failure)
    Given the input string "abc"
    When it is reversed
    Then the unit result is "abc"
