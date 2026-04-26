package com.testreports.orchestrator;

import com.testreports.email.EmailService;
import com.testreports.email.ReportSummary;
import com.testreports.model.RunManifest;

import java.util.Objects;
import java.util.logging.Logger;

public class EmailSendStage implements PipelineStage {
    private static final Logger LOGGER = Logger.getLogger(EmailSendStage.class.getName());

    private final EmailSender sender;

    public EmailSendStage() {
        this(null);
    }

    public EmailSendStage(EmailSender sender) {
        this.sender = sender;
    }

    @Override
    public String getName() {
        return "EmailSend";
    }

    @Override
    public boolean isCritical() {
        return false;
    }

    @Override
    public void execute(RunContext ctx) {
        RunManifest manifest = Objects.requireNonNull(ctx.getManifest(), "manifest must be available before email send");
        String recipient = ctx.getConfig().get(PipelineConfig.EMAIL_RECIPIENT).orElse("");
        if (recipient.isBlank()) {
            LOGGER.info("No email recipient configured; skipping email notification");
            return;
        }
        EmailSender activeSender = sender == null ? createSender(ctx.getConfig()) : sender;
        activeSender.send(toSummary(manifest, reportUrl(ctx)), recipient);
    }

    private EmailSender createSender(PipelineConfig config) {
        String smtpHost = config.get(PipelineConfig.SMTP_HOST)
                .orElseThrow(() -> new IllegalStateException("smtp.host is required when email.recipient is set"));
        EmailService service = new EmailService(
                smtpHost,
                config.intValue(PipelineConfig.SMTP_PORT, 587),
                config.getOrDefault(PipelineConfig.SMTP_USERNAME, ""),
                config.getOrDefault(PipelineConfig.SMTP_PASSWORD, ""),
                config.getOrDefault(PipelineConfig.SMTP_FROM, "reports@example.invalid")
        );
        return service::sendReport;
    }

    private ReportSummary toSummary(RunManifest manifest, String reportUrl) {
        return new ReportSummary(
                manifest.getRunId(),
                manifest.getTimestamp(),
                manifest.getTotalScenarios(),
                manifest.getPassed(),
                manifest.getFailed(),
                manifest.getSkipped(),
                reportUrl
        );
    }

    private String reportUrl(RunContext ctx) {
        String baseUrl = ctx.getConfig().getOrDefault(PipelineConfig.REPORT_BASE_URL, "");
        if (baseUrl.isBlank()) {
            return ctx.getConfig().path(PipelineConfig.WEB_DEPLOY_DIR).resolve(ctx.getRunId()).resolve("report").toString();
        }
        return baseUrl.endsWith("/") ? baseUrl + ctx.getRunId() + "/report" : baseUrl + "/" + ctx.getRunId() + "/report";
    }

    @FunctionalInterface
    public interface EmailSender {
        void send(ReportSummary summary, String recipientEmail);
    }
}
