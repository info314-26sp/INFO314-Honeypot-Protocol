
import java.net.*;
import java.io.*;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import com.google.gson.*;

public class HoneypotNode {

    private static final String NODE_ID = UUID.randomUUID().toString();
    private static PrintWriter toBrain;
    private static final Gson gson = new Gson();

    private static String brainHost = "localhost";
    private static int    brainPort = 9000;
    private static int    sshPort   = 2222;
    private static int    ftpPort   = 2121;
    private static int    httpPort  = 8080;

    // Behavioral config — modified by CONTROL_COMMAND (temporary) / CONFIG_UPDATE (persistent)
    static volatile int     responseDelayMs   = 0;
    static volatile boolean dropConnections   = false;
    static volatile int     heartbeatInterval = 30;
    static volatile int     attempts          = Integer.MAX_VALUE;
    static volatile String  errorResp         = "";
    private static NodeState defaultConfig    = new NodeState();

    // Class-level so SET_HEARTBEAT_INTERVAL can restart the scheduler
    static ScheduledExecutorService heartbeatScheduler = Executors.newScheduledThreadPool(1);
    static final AtomicInteger heartbeatSeq = new AtomicInteger(0);

    static final Map<String, Consumer<JsonObject>> commandHandlers = new HashMap<>();
    static {
        commandHandlers.put("SLOW_RESPONSE",         params -> responseDelayMs = params.get("delay_ms").getAsInt());
        commandHandlers.put("DROP_CONNECTION",        params -> dropConnections = params.get("drop").getAsBoolean());
        commandHandlers.put("SET_ATTEMPTS",           params -> attempts = params.get("attempts").getAsInt());
        commandHandlers.put("SET_ERROR_RESPONSE",     params -> errorResp = params.get("msg").getAsString());
        commandHandlers.put("SET_HEARTBEAT_INTERVAL", params -> {
            heartbeatInterval = params.get("interval_s").getAsInt();
            startHeartbeat();
        });
    }

    public static void main(String[] args) throws IOException {
        if (args.length >= 1) brainHost = args[0];
        if (args.length >= 2) brainPort = Integer.parseInt(args[1]);
        if (args.length >= 3) sshPort   = Integer.parseInt(args[2]);
        if (args.length >= 4) ftpPort   = Integer.parseInt(args[3]);
        if (args.length >= 5) httpPort  = Integer.parseInt(args[4]);

        System.out.println("Connecting to central brain at " + brainHost + ":" + brainPort);
        Socket cBrainSocket = new Socket(brainHost, brainPort);
        toBrain = new PrintWriter(cBrainSocket.getOutputStream(), true);

        authMsg();
        startHeartbeat();

        ExecutorService executor = Executors.newFixedThreadPool(4);
        executor.submit(() -> listenOnPort(sshPort,  "SSH"));
        executor.submit(() -> listenOnPort(ftpPort,  "FTP"));
        executor.submit(() -> listenOnPort(httpPort, "HTTP"));
        executor.submit(() -> receiveUpdates(cBrainSocket));
    }

    // ── Network listeners ─────────────────────────────────────────────────────

    static void listenOnPort(int port, String serviceType) {
        try (ServerSocket server = new ServerSocket(port)) {
            System.out.println("Listening on port " + port + " (" + serviceType + ")");
            while (true) {
                Socket attacker = server.accept();
                new Thread(() -> handleAttacker(attacker, serviceType)).start();
            }
        } catch (IOException e) {
            System.out.println("Failed on port " + port + ": " + e.getMessage());
        }
    }

    static void handleAttacker(Socket attacker, String serviceType) {
        String sourceIp   = attacker.getInetAddress().getHostAddress();
        int    sourcePort = attacker.getPort();
        String eventType  = serviceType.equals("HTTP") ? "HTTP_REQUEST" : "LOGIN_ATTEMPT";

        try {
            PrintWriter    out = new PrintWriter(attacker.getOutputStream(), true);
            BufferedReader in  = new BufferedReader(new InputStreamReader(attacker.getInputStream()));

            if (dropConnections) {
                attacker.close();
                return;
            }

            sendFakeBanner(out, serviceType);

            if (responseDelayMs > 0) {
                Thread.sleep(responseDelayMs);
            }

            StringBuilder capturedData = new StringBuilder();
            String line;
            int    attemptCount = 0;

            while ((line = in.readLine()) != null) {
                if (++attemptCount > attempts) {
                    out.println(errorResp);
                    break;
                }
                capturedData.append(line).append("\n");
            }

            JsonObject payload = new JsonObject();
            payload.addProperty("data", capturedData.toString().trim());
            sendEventReport(serviceType, sourceIp, sourcePort, eventType, payload);

        } catch (IOException e) {
            System.out.println("Client connection error from " + sourceIp + ": " + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            rollback();
            try { attacker.close(); } catch (IOException ignored) {}
        }
    }

    // Listens for incoming messages from the Central Brain.
    static void receiveUpdates(Socket brainSocket) {
        try {
            BufferedReader in = new BufferedReader(new InputStreamReader(brainSocket.getInputStream()));
            String line;
            while ((line = in.readLine()) != null) {
                JsonObject msg  = gson.fromJson(line, JsonObject.class);
                String     type = msg.get("type").getAsString();
                switch (type) {
                    case "PING":
                        echo(msg.get("msg_id").getAsString());
                        break;
                    case "CONTROL_COMMAND":
                        applyControlCommand(msg);
                        break;
                    case "CONFIG_UPDATE":
                        applyConfigUpdate(msg);
                        break;
                }
            }
        } catch (IOException e) {
            System.out.println("Connection to brain lost: " + e.getMessage());
        }
    }

    // ── Command application ───────────────────────────────────────────────────

    static void applyControlCommand(JsonObject msg) {
        String     msgId    = msg.get("msg_id").getAsString();
        JsonArray  commands = msg.get("cc_commands").getAsJsonArray();
        for (JsonElement el : commands) {
            JsonObject cmd     = el.getAsJsonObject();
            String     command = cmd.get("command").getAsString();
            JsonObject params  = cmd.has("parameters") ? cmd.getAsJsonObject("parameters") : new JsonObject();
            Consumer<JsonObject> handler = commandHandlers.get(command);
            if (handler != null) {
                try {
                    handler.accept(params);
                } catch (Exception e) {
                    rollback();
                    commandAck("CONTROL_COMMAND", msgId, false,
                        "Failed to apply " + command + ": " + e.getMessage());
                    return;
                }
            }
        }
        commandAck("CONTROL_COMMAND", msgId, true);
    }

    static void applyConfigUpdate(JsonObject msg) {
        String    msgId    = msg.get("msg_id").getAsString();
        JsonArray commands = msg.get("cu_commands").getAsJsonArray();
        for (JsonElement el : commands) {
            JsonObject cmd     = el.getAsJsonObject();
            String     command = cmd.get("command").getAsString();
            JsonObject params  = cmd.has("parameters") ? cmd.getAsJsonObject("parameters") : new JsonObject();
            Consumer<JsonObject> handler = commandHandlers.get(command);
            if (handler != null) {
                try {
                    handler.accept(params);
                } catch (Exception e) {
                    rollback();
                    commandAck("CONFIG_UPDATE", msgId, false,
                        "Failed to apply " + command + ": " + e.getMessage());
                    return;
                }
            }
        }
        updateConfig();
        commandAck("CONFIG_UPDATE", msgId, true);
    }

    // Resets transient CONTROL_COMMAND changes back to the current baseline.
    private static void rollback() {
        responseDelayMs   = defaultConfig.responseDelayMs;
        dropConnections   = false;
        heartbeatInterval = defaultConfig.heartbeatInterval;
        attempts          = defaultConfig.attempts;
        errorResp         = defaultConfig.errorResp;
    }

    // Makes the current settings the new baseline (called after CONFIG_UPDATE).
    private static void updateConfig() {
        defaultConfig.responseDelayMs   = responseDelayMs;
        defaultConfig.heartbeatInterval = heartbeatInterval;
        defaultConfig.attempts          = attempts;
        defaultConfig.errorResp         = errorResp;
    }

    // ── Outgoing messages to brain ────────────────────────────────────────────

    static void sendEventReport(String service, String sourceIp, int sourcePort,
                                String eventType, JsonObject payload) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type",        "EVENT_REPORT");
        msg.addProperty("msg_id",      UUID.randomUUID().toString());
        msg.addProperty("node_id",     NODE_ID);
        msg.addProperty("source_ip",   sourceIp);
        msg.addProperty("source_port", sourcePort);
        msg.addProperty("service",     service);
        msg.addProperty("event_type",  eventType);
        msg.add(        "payload",     payload);
        msg.addProperty("timestamp",   System.currentTimeMillis());
        send(gson.toJson(msg));
        System.out.println("EVENT_REPORT sent: " + eventType + " from " + sourceIp + " on " + service);
    }

    static void sendHeartbeat(int seqNum) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type",      "HEARTBEAT");
        msg.addProperty("seq_num",   seqNum);
        msg.addProperty("msg_id",    UUID.randomUUID().toString());
        msg.addProperty("node_id",   NODE_ID);
        msg.addProperty("timestamp", System.currentTimeMillis());
        send(gson.toJson(msg));
        System.out.println("HEARTBEAT #" + seqNum + " sent");
    }

    // (Re)starts the heartbeat scheduler at the current heartbeatInterval.
    private static synchronized void startHeartbeat() {
        heartbeatScheduler.shutdownNow();
        heartbeatScheduler = Executors.newScheduledThreadPool(1);
        heartbeatScheduler.scheduleAtFixedRate(
            () -> sendHeartbeat(heartbeatSeq.incrementAndGet()),
            0, heartbeatInterval, TimeUnit.SECONDS
        );
    }

    static void authMsg() {
        JsonObject auth = new JsonObject();
        auth.addProperty("type",        "AUTH");
        auth.addProperty("msg_id",      UUID.randomUUID().toString());
        auth.addProperty("node_id",     NODE_ID);
        auth.addProperty("credentials", "");
        auth.addProperty("timestamp",   System.currentTimeMillis());
        send(gson.toJson(auth));
        System.out.println("AUTH sent (node_id=" + NODE_ID + ")");
    }

    static void authInit(String nonce1) {
        JsonObject auth = new JsonObject();
        auth.addProperty("type",       "AUTH_INIT");
        auth.addProperty("node_id",    NODE_ID);
        auth.addProperty("msg_id",     UUID.randomUUID().toString());
        auth.addProperty("node_nonce", nonce1);
        auth.addProperty("timestamp",  System.currentTimeMillis());
        send(gson.toJson(auth));
    }

    static void authResp(String nonce1, String nonce2, String sourceMsgId) {
        JsonObject auth = new JsonObject();
        auth.addProperty("type",            "AUTH_RESPONSE");
        auth.addProperty("node_id",         NODE_ID);
        auth.addProperty("msg_id",          UUID.randomUUID().toString());
        auth.addProperty("reply_to_msg_id", sourceMsgId);
        auth.addProperty("node_nonce",      nonce1);
        auth.addProperty("challenge_nonce", nonce2);
        auth.addProperty("proof",           nonce2 + nonce1);
        auth.addProperty("timestamp",       System.currentTimeMillis());
        send(gson.toJson(auth));
    }

    static void commandAck(String ackFor, String cmdMsgId, boolean applied) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type",       "CMD_ACK");
        msg.addProperty("msg_id",     UUID.randomUUID().toString());
        msg.addProperty("node_id",    NODE_ID);
        msg.addProperty("ack_for",    ackFor);
        msg.addProperty("cmd_msg_id", cmdMsgId);
        msg.addProperty("applied",    applied);
        msg.addProperty("timestamp",  System.currentTimeMillis());
        send(gson.toJson(msg));
    }

    static void commandAck(String ackFor, String cmdMsgId, boolean applied, String errorMsg) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type",       "CMD_ACK");
        msg.addProperty("msg_id",     UUID.randomUUID().toString());
        msg.addProperty("node_id",    NODE_ID);
        msg.addProperty("ack_for",    ackFor);
        msg.addProperty("cmd_msg_id", cmdMsgId);
        msg.addProperty("applied",    applied);
        msg.addProperty("error_msg",  errorMsg);
        msg.addProperty("timestamp",  System.currentTimeMillis());
        send(gson.toJson(msg));
    }

    static void echo(String pingMsgId) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type",      "ECHO");
        msg.addProperty("msg_id",    UUID.randomUUID().toString());
        msg.addProperty("node_id",   NODE_ID);
        msg.addProperty("ping_id",   pingMsgId);
        msg.addProperty("timestamp", System.currentTimeMillis());
        send(gson.toJson(msg));
        System.out.println("ECHO sent in response to PING " + pingMsgId);
    }

    private static synchronized void send(String json) {
        toBrain.println(json);
    }

    // ── Fake service banners ──────────────────────────────────────────────────

    static void sendFakeBanner(PrintWriter out, String serviceType) {
        switch (serviceType) {
            case "SSH":
                out.println("SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.1");
                break;
            case "FTP":
                out.println("220 FTP server ready");
                break;
            case "HTTP":
                out.print("HTTP/1.1 200 OK\r\nServer: Apache/2.4.41\r\n\r\n");
                out.flush();
                break;
            default:
                out.println("220 Service ready");
                break;
        }
    }

    // ── NodeState snapshot ────────────────────────────────────────────────────

    static class NodeState {
        int     responseDelayMs   = 0;
        boolean dropConnections   = false;
        int     heartbeatInterval = 30;
        int     attempts          = Integer.MAX_VALUE;
        String  errorResp         = "";
    }
}
