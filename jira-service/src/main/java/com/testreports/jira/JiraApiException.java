package com.testreports.jira;

/**
 * Exception for Jira API errors.
 */
public class JiraApiException extends Exception {

    public JiraApiException(String message) {
        super(message);
    }

    public JiraApiException(String message, Throwable cause) {
        super(message, cause);
    }
}