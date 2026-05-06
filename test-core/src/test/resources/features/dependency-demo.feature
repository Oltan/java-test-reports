@DependencyDemo
Feature: Dependency Management Demo

  @smoke @id:Setup
  Scenario: Database setup
    Given the database is initialized
    Then setup is complete

  @smoke @id:Login @dep:Setup
  Scenario: User login
    Given a user exists
    When they log in
    Then login succeeds

  @smoke @id:Dashboard @dep:Login,Setup
  Scenario: Dashboard loads
    Given the user is logged in
    When they visit dashboard
    Then dashboard displays correctly
