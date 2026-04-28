@DependencyDemo
Feature: Dependency Management Demo

  @id:Setup
  Scenario: Database setup
    Given the database is initialized
    Then setup is complete

  @id:Login @dep:Setup
  Scenario: User login
    Given a user exists
    When they log in
    Then login succeeds

  @id:Dashboard @dep:Login,Setup
  Scenario: Dashboard loads
    Given the user is logged in
    When they visit dashboard
    Then dashboard displays correctly
