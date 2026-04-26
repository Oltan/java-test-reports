package com.testreports.email;

import org.simplejavamail.api.email.Email;
import org.simplejavamail.api.mailer.Mailer;
import org.simplejavamail.api.mailer.config.TransportStrategy;
import org.simplejavamail.email.EmailBuilder;
import org.simplejavamail.mailer.MailerBuilder;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class EmailService {
    private final String smtpHost;
    private final int smtpPort;
    private final String username;
    private final String password;
    private final String fromAddress;
    private final TransportStrategy transportStrategy;
    private final TemplateEngine templateEngine;
    private final ScheduledExecutorService retryExecutor;

    public EmailService(String smtpHost, int smtpPort, String username, String password, String fromAddress) {
        this(smtpHost, smtpPort, username, password, fromAddress, TransportStrategy.SMTP_TLS);
    }

    public EmailService(String smtpHost, int smtpPort, String username, String password,
                       String fromAddress, TransportStrategy transportStrategy) {
        this.smtpHost = smtpHost;
        this.smtpPort = smtpPort;
        this.username = username;
        this.password = password;
        this.fromAddress = fromAddress;
        this.transportStrategy = transportStrategy;
        this.retryExecutor = Executors.newScheduledThreadPool(1);

        ClassLoaderTemplateResolver resolver = new ClassLoaderTemplateResolver();
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setCacheable(false);

        this.templateEngine = new TemplateEngine();
        this.templateEngine.setTemplateResolver(resolver);
    }

    public void sendReport(ReportSummary summary, String recipientEmail) {
        Context context = new Context();
        context.setVariable("runId", summary.getRunId());
        context.setVariable("timestamp", summary.getTimestamp().toString());
        context.setVariable("totalScenarios", summary.getTotalScenarios());
        context.setVariable("passed", summary.getPassed());
        context.setVariable("failed", summary.getFailed());
        context.setVariable("skipped", summary.getSkipped());
        context.setVariable("reportUrl", summary.getReportUrl());

        String htmlContent = templateEngine.process("report-email", context);
        String plainTextContent = buildPlainTextSummary(summary);

        Mailer mailer = MailerBuilder
                .withSMTPServer(smtpHost, smtpPort, username, password)
                .withTransportStrategy(transportStrategy)
                .withExecutorService(retryExecutor)
                .withConnectionPoolCoreSize(2)
                .withConnectionPoolMaxSize(2)
                .withConnectionPoolExpireAfterMillis(1000)
                .buildMailer();

        Email email = EmailBuilder.startingBlank()
                .from(fromAddress)
                .to(recipientEmail)
                .withSubject("Test Report: Run " + summary.getRunId())
                .withPlainText(plainTextContent)
                .withHTMLText(htmlContent)
                .buildEmail();

        boolean sent = false;
        int retries = 2;
        long backoffMs = 1000;

        for (int i = 0; i <= retries && !sent; i++) {
            try {
                mailer.sendMail(email);
                sent = true;
            } catch (Exception e) {
                if (i == retries) {
                    throw e;
                }
                try {
                    TimeUnit.MILLISECONDS.sleep(backoffMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException(ie);
                }
            }
        }
    }

    private String buildPlainTextSummary(ReportSummary summary) {
        return "Test Report Summary\n" +
                "====================\n" +
                "Run ID: " + summary.getRunId() + "\n" +
                "Timestamp: " + summary.getTimestamp() + "\n" +
                "Total Scenarios: " + summary.getTotalScenarios() + "\n" +
                "Passed: " + summary.getPassed() + "\n" +
                "Failed: " + summary.getFailed() + "\n" +
                "Skipped: " + summary.getSkipped() + "\n" +
                "Report URL: " + summary.getReportUrl();
    }

    public void shutdown() {
        retryExecutor.shutdown();
    }
}