@DependencyDemo
Feature: Dependency Management Demo

  @smoke @id:Setup @DOORS-10001
  Scenario: Database setup
    Given the database is initialized
    Then setup is complete

  @smoke @id:Login @dep:Setup @DOORS-10002
  Scenario: User login
    Given a user exists
    When they log in
    Then login succeeds

  @smoke @id:Dashboard @dep:Login,Setup @DOORS-10003
  Scenario: Dashboard loads
    Given the user is logged in
    When they visit dashboard
    Then dashboard displays correctly
