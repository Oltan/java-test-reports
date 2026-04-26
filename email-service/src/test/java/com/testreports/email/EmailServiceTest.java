package com.testreports.email;

import com.icegreen.greenmail.configuration.GreenMailConfiguration;
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.BodyPart;
import org.simplejavamail.api.mailer.config.TransportStrategy;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class EmailServiceTest {

    private GreenMail greenMail;
    private int smtpPort;
    private EmailService emailService;
    private static final String TEST_HOST = "localhost";
    private static final String TEST_USERNAME = "testuser";
    private static final String TEST_PASSWORD = "testpass";
    private static final String TEST_FROM = "noreply@testreports.com";
    private static final String TEST_RECIPIENT = "test@example.com";

    @BeforeEach
    void setUp() {
        ServerSetup[] serverSetups = { new ServerSetup(0, TEST_HOST, ServerSetup.PROTOCOL_SMTP) };
        greenMail = new GreenMail(serverSetups)
                .withConfiguration(new GreenMailConfiguration().withDisabledAuthentication());
        greenMail.start();
        smtpPort = greenMail.getSmtp().getPort();
        emailService = new EmailService(TEST_HOST, smtpPort, TEST_USERNAME, TEST_PASSWORD, TEST_FROM, TransportStrategy.SMTP);
    }

    @AfterEach
    void tearDown() {
        if (greenMail != null) {
            greenMail.stop();
        }
        emailService.shutdown();
    }

    @Test
    void sendReport_SendsEmailWithCorrectContent() throws Exception {
        String runId = "run-123";
        ReportSummary summary = new ReportSummary(
                runId,
                Instant.now(),
                10,
                8,
                1,
                1,
                "https://reports.example.com/run-123"
        );

        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<AssertionError> error = new AtomicReference<>();

        Thread senderThread = new Thread(() -> {
            try {
                emailService.sendReport(summary, TEST_RECIPIENT);
            } catch (Exception e) {
                error.set(new AssertionError("Send failed", e));
            }
            latch.countDown();
        });
        senderThread.start();

        assertTrue(latch.await(10, TimeUnit.SECONDS), "Email send timed out");
        if (error.get() != null) {
            throw error.get();
        }

        MimeMessage[] received = greenMail.getReceivedMessages();
        assertEquals(1, received.length, "Should receive exactly one message");

        Message msg = received[0];
        assertTrue(msg.getSubject().contains(runId), "Subject should contain runId");
        assertEquals(TEST_RECIPIENT, msg.getAllRecipients()[0].toString());

        Object content = msg.getContent();
        if (content instanceof Multipart multipart) {
            boolean hasHtml = false;
            boolean hasPlainText = false;
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart part = multipart.getBodyPart(i);
                String type = part.getContentType();
                if (type.contains("text/html")) {
                    hasHtml = true;
                    String htmlBody = (String) part.getContent();
                    assertTrue(htmlBody.contains(summary.getReportUrl()), "HTML body should contain report link");
                }
                if (type.contains("text/plain")) {
                    hasPlainText = true;
                }
            }
            assertTrue(hasHtml, "Should have text/html part");
            assertTrue(hasPlainText, "Should have text/plain part");
        } else if (content instanceof String bodyString) {
            assertTrue(bodyString.contains("text/html"), "Should have HTML content");
            assertTrue(bodyString.contains(summary.getReportUrl()), "Body should contain report link");
        }
    }
}