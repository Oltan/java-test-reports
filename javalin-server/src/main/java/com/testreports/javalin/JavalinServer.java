package com.testreports.javalin;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import io.javalin.Javalin;
import io.javalin.http.Context;
import io.javalin.http.staticfiles.Location;
import io.javalin.json.JavalinJackson;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.Map;
import java.util.logging.Logger;

public class JavalinServer {

    private static final Logger LOGGER = Logger.getLogger(JavalinServer.class.getName());

    private static final String JWT_SECRET = System.getProperty("jwt.secret", "dev-secret-change-me-must-be-at-least-32-chars!!");
    private static final String JWT_ALGORITHM = "HS256";
    private static final String ADMIN_USERNAME = System.getProperty("admin.username", "admin");
    private static final String ADMIN_PASSWORD = System.getProperty("admin.password", "admin123");

    private final Javalin app;
    private final ManifestService manifestService;
    private final ObjectMapper objectMapper;
    private final SecretKey signingKey;

    public JavalinServer() {
        this("../manifests");
    }

    public JavalinServer(String manifestsDir) {
        this.signingKey = Keys.hmacShaKeyFor(JWT_SECRET.getBytes(StandardCharsets.UTF_8));
        this.manifestService = new ManifestService(manifestsDir);
        this.objectMapper = new ObjectMapper();
        this.objectMapper.registerModule(new JavaTimeModule());
        this.app = createApp();
    }

    public Javalin app() {
        return app;
    }

    private Javalin createApp() {
        Javalin app = Javalin.create(config -> {
            config.staticFiles.add("../manifests", Location.EXTERNAL);
            config.jsonMapper(new JavalinJackson(objectMapper, false));
        });

        app.before("/api/v1/*", this::authenticateJwt);

        app.post("/api/v1/auth/login", this::handleLogin);

        app.get("/api/v1/runs", this::handleGetAllRuns);
        app.get("/api/v1/runs/{runId}", this::handleGetRun);
        app.get("/api/v1/runs/{runId}/failures", this::handleGetFailures);

        return app;
    }

    private void authenticateJwt(Context ctx) throws Exception {
        if (ctx.path().equals("/api/v1/auth/login")) {
            return;
        }

        String authHeader = ctx.header("Authorization");
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            ctx.status(401).json(Map.of("error", "Missing or invalid Authorization header"));
            return;
        }

        String token = authHeader.substring(7);
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(signingKey)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();

            ctx.attribute("username", claims.getSubject());
        } catch (Exception e) {
            ctx.status(401).json(Map.of("error", "Invalid or expired token"));
        }
    }

    private void handleLogin(Context ctx) throws Exception {
        Map<String, String> body = objectMapper.readValue(ctx.body(), Map.class);
        String username = body.get("username");
        String password = body.get("password");

        if (!ADMIN_USERNAME.equals(username) || !ADMIN_PASSWORD.equals(password)) {
            ctx.status(401).json(Map.of("error", "Invalid credentials"));
            return;
        }

        String token = Jwts.builder()
                .subject(username)
                .issuedAt(Date.from(Instant.now()))
                .signWith(signingKey)
                .compact();

        ctx.json(Map.of("token", token));
    }

    private void handleGetAllRuns(Context ctx) throws Exception {
        ctx.json(manifestService.getAllRuns());
    }

    private void handleGetRun(Context ctx) throws Exception {
        String runId = ctx.pathParam("runId");
        var run = manifestService.getRun(runId);
        if (run.isEmpty()) {
            ctx.status(404).json(Map.of("error", "Run '" + runId + "' not found"));
            return;
        }
        ctx.json(run.get());
    }

    private void handleGetFailures(Context ctx) throws Exception {
        String runId = ctx.pathParam("runId");
        var failures = manifestService.getFailures(runId);
        if (failures.isEmpty()) {
            ctx.status(404).json(Map.of("error", "Run '" + runId + "' not found"));
            return;
        }
        ctx.json(failures.get());
    }

    public Javalin start(int port) {
        return app.start(port);
    }

    public static void main(String[] args) {
        JavalinServer server = new JavalinServer();
        server.start(8080);
        LOGGER.info("Javalin server started on port 8080");
    }
}