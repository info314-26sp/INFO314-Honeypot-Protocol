

import java.net.*;
import java.io.*;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.security.MessageDigest;
import javax.crypto.Mac; //(for HMAC)
import java.security.Signature; //(for public/private key signing)

import com.google.gson.*;

public class HoneypotNode {

    // HoneypotNode Class Attributes
    private static final String NODE_ID = UUID.randomUUID().toString();
    private static PrintWriter toBrain;
    private static final Gson gson = new Gson();
    static final Object interactionLock = new Object();
    
    
    // Attributes related COMMANDS
    static int responseDelayMs = 0;
    static boolean dropConnections = false;
    static int activePort = 80;
    static String serviceType = "SSH";
    static int attempts = Integer.MAX_VALUE;
    static String errorResp = "";
    private static NodeState defaultConfig = new NodeState(); 


    // Command Parameters
    static final Map<String, Consumer<JsonObject>> commandHandlers = new HashMap<>();
    static {
        // CONTROL_COMMAND Commands
        commandHandlers.put("SLOW_RESPONSE", params -> {
            responseDelayMs = params.get("delay_ms").getAsInt();
        });
        commandHandlers.put("DROP_CONNECTION", params -> {
            dropConnections = params.get("drop").getAsBoolean();
        });
        
        // Both COMMAND_CONTROLS or CONFIG_UPDATE Commands
        commandHandlers.put("SET_ATTEMPTS", params -> {
            attempts = params.get("attempts").getAsInt();
        });
        commandHandlers.put("SET_ERROR_RESPONSE", params -> {
            errorResp = params.get("msg").getAsString();
        });

        // CONFIG_UPDATE Commands
        // delete tbh ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        commandHandlers.put("SET_PORT", params -> {
            activePort = params.get("portNum").getAsInt();
        });
        commandHandlers.put("CHANGE_SERVICE", params -> {
            serviceType = params.get("service").getAsString();
        });
    }

    // Main method 
    public static void main(String[] args) throws IOException{
        
        Socket cBrainSocket = new Socket("localhost", 9000);
        toBrain = new PrintWriter(cBrainSocket.getOutputStream(), true);


        // authenticate
        authMsg("temp, change later");

        // start heartbeat
        AtomicInteger heartbeatSeq = new AtomicInteger(0);

        ScheduledExecutorService heartbeat = Executors.newScheduledThreadPool(1);
        heartbeat.scheduleAtFixedRate(() -> sendHeartbeat(heartbeatSeq.incrementAndGet()), 0, 30, TimeUnit.SECONDS);

        // wait and listen
        ExecutorService executor = Executors.newFixedThreadPool(4);
        executor.submit(() -> listenOnPort(22, "SSH"));
        executor.submit(() -> listenOnPort(21, "FTP"));
        executor.submit(() -> listenOnPort(80, "HTTP"));

        executor.submit(() -> recieveUpdates(cBrainSocket));


    }

    // ~~~~~~~~~~~~~~~~~~~~~~ METHODS ~~~~~~~~~~~~~~~~~~~~~~

    // ~~~~ NETWORK LISTENERS ~~~~

    // Listen for attackers on a given port
    static void listenOnPort(int port, String serviceType) {
        try (ServerSocket serverSocker = new ServerSocket(port)) {
            while (true) {
                Socket attacker = serverSocker.accept();
                synchronized (interactionLock) {
                    handleAttacker(attacker, serviceType);
                }   
            }
        } catch (IOException e) {
            System.out.println("Failed on port " + port);
        }
    }

    // Handle Interactions with the attacker
    static void handleAttacker(Socket attacker, String serviceType) {
        try {
            PrintWriter out = new PrintWriter(attacker.getOutputStream(), true);
            BufferedReader in = new BufferedReader(new InputStreamReader(attacker.getInputStream()));

            // DROP_CONNECTION Check
            if (dropConnections) {
                attacker.close();
                return;
            }

            sendFakeBanner(out, serviceType);

            // DELAY_MS Check
            if (responseDelayMs > 0) {
                Thread.sleep(responseDelayMs);
            }


            StringBuilder msgText = new StringBuilder();
            String line;
            int attemptCount = 0;

            while ((line = in.readLine()) != null) {
                attemptCount++;

                // ATTEMPTS Check
                if (attemptCount > attempts) {
                    out.println(errorResp);
                    break;
                }
                msgText.append(line);
            }

            sendEventReport(serviceType, attacker.getInetAddress().toString(), msgText.toString());

        } catch (IOException e) {
            System.out.println("400 Error: Client connection error");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }finally {
            rollback();
        }
    }

    // Listen to and recieve messages from the Central Brain, then respond accordingly.
    static void recieveUpdates(Socket brainSocket) {
        try {
            BufferedReader in = new BufferedReader(new InputStreamReader(brainSocket.getInputStream()));

            String line;
            while ((line = in.readLine()) != null) {
                JsonObject msg = gson.fromJson(line, JsonObject.class);
                String type = msg.get("type").getAsString();
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
                    case "AUTH":
                        authMsg(""); // UPDATE
                        break;
                    case "AUTH_OK":
                        break;
                    case "AUTH_CHALLENGE":
                        break;
                }
            }

        } catch (IOException e) {
            System.out.println("500 error: Connection Lost");
        }
    }

    // ~~~~ COMMAND SETTING LOGIC ~~~~

    static void applyControlCommand(JsonObject msg) {
        String msgId = msg.get("msg_id").getAsString();


        JsonArray commands = msg.get("cc_commands").getAsJsonArray();
        for (JsonElement el : commands) {
            JsonObject cmd = el.getAsJsonObject();
            String command = cmd.get("command").getAsString();

            // parameters?
            JsonObject parameters = cmd.has("parameters") 
                ? cmd.getAsJsonObject("parameters") 
                : new JsonObject(); 
            Consumer<JsonObject> handler = commandHandlers.get(command);

            // could also add a case where command DNE
            if (handler != null) {
                try{
                    handler.accept(parameters);
                } catch (Exception e) {
                    rollback();
                    commandAck("CONTROL_COMMAND", msgId, false, "Failed to apply: " + command + " Resetting to default config. Error:" + e.getMessage());                    
                    return;
                }
                
            }
        }

        commandAck("CONTROL_COMMAND", msgId, true);
    }


    static void applyConfigUpdate(JsonObject msg) {
        String msgId = msg.get("msg_id").getAsString();

        JsonArray commands = msg.get("cu_commands").getAsJsonArray();
        for (JsonElement el : commands) {
            JsonObject cmd = el.getAsJsonObject();
            String command = cmd.get("command").getAsString();

            JsonObject parameters = cmd.has("parameters") 
                ? cmd.getAsJsonObject("parameters") 
                : new JsonObject(); 

            Consumer<JsonObject> handler = commandHandlers.get(command);
            if (handler != null) {
                try {
                    handler.accept(parameters);
                } catch (Exception e) {
                    rollback();
                    commandAck("CONFIG_UPDATE", msgId, false, "Failed to apply: " + command + " Resetting to default config. Error:" + e.getMessage());                    
                    return;
                }
            }
        }
        updateConfig();
        commandAck("CONFIG_UPDATE", msgId, true);
    }

    // Rollback to default config settings
    private static void rollback() {
        responseDelayMs = defaultConfig.responseDelayMs;
        dropConnections = false;
        activePort = defaultConfig.activePort;       
        serviceType = defaultConfig.serviceType;
        attempts = defaultConfig.attempts;
        errorResp = defaultConfig.errorResp;
    }

    // Overwrites the default config settings with the current config settings, making that the new default.
    private static void updateConfig() {
        defaultConfig.responseDelayMs = responseDelayMs;
        defaultConfig.dropConnections = false;
        defaultConfig.activePort = activePort;
        defaultConfig.serviceType = serviceType;
        defaultConfig.attempts = attempts;
        defaultConfig.errorResp = errorResp;
    }



    
    // ~~~~ OUTGOING MESSAGES TO BRAIN ~~~~

    // Sends command acknowledgements; used after successful application
    static void commandAck(String recievedType, String commandId, boolean success) {
        JsonObject acky = new JsonObject();
        acky.addProperty("type", "CMD_ACK");
        acky.addProperty("msg_id", UUID.randomUUID().toString());
        acky.addProperty("node_id", NODE_ID);
        acky.addProperty("ack_for", recievedType );
        acky.addProperty("cmd_msg_id",  commandId);
        acky.addProperty("applied", success);
        acky.addProperty("timestamp", System.currentTimeMillis());
        toBrain.println(gson.toJson(acky));

    }
    
    // Sends command acknowledgements; used after command application fails
    static void commandAck(String recievedType, String commandId, boolean success, String error) {
        JsonObject acky = new JsonObject();
        acky.addProperty("type", "CMD_ACK");
        acky.addProperty("msg_id", UUID.randomUUID().toString());
        acky.addProperty("node_id", NODE_ID);
        acky.addProperty("ack_for", recievedType );
        acky.addProperty("cmd_msg_id",  commandId);
        acky.addProperty("applied", success);
        acky.addProperty("error_msg", error);
        acky.addProperty("timestamp", System.currentTimeMillis());
        toBrain.println(gson.toJson(acky));
    }




    // Event Report for when no data is attatched
    static void sendEventReport(String serviceType, String sourceIp) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type", "EVENT_REPORT");
        msg.addProperty("msg_id", UUID.randomUUID().toString());
        msg.addProperty("node_id", NODE_ID);
        msg.addProperty("service_type", serviceType);
        msg.addProperty("source_ip", sourceIp);
        msg.addProperty("timestamp", System.currentTimeMillis());
        toBrain.println(gson.toJson(msg));
    }

    // Event Report for when there's accompanying data
    static void sendEventReport(String serviceType, String sourceIp, String data) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type", "EVENT_REPORT");
        msg.addProperty("msg_id", UUID.randomUUID().toString());
        msg.addProperty("node_id", NODE_ID);
        msg.addProperty("service_type", serviceType);
        msg.addProperty("source_ip", sourceIp);
        msg.addProperty("captured_data", data);
        msg.addProperty("timestamp", System.currentTimeMillis());
        toBrain.println(gson.toJson(msg));
    }

    static void sendHeartbeat(int seqNum) {
        JsonObject beat = new JsonObject();
        beat.addProperty("type", "HEARTBEAT");
        beat.addProperty("seq_num", seqNum);
        beat.addProperty("msg_id", UUID.randomUUID().toString());
        beat.addProperty("node_id", NODE_ID);
        beat.addProperty("timestamp", System.currentTimeMillis());
        toBrain.println(gson.toJson(beat));
    }

    // MAY UPDATE LATER
    static void authMsg(String cred) {
        JsonObject auth = new JsonObject();
        auth.addProperty("type", "AUTH");
        auth.addProperty("node_id", NODE_ID);
        auth.addProperty("msg_id", UUID.randomUUID().toString());
        auth.addProperty("timestamp", System.currentTimeMillis());
        auth.addProperty("credentials", cred);
        toBrain.println(gson.toJson(auth));
    }     

    // improved auth
    static void authInit(String nonce1) {
        JsonObject auth = new JsonObject();
        auth.addProperty("type", "AUTH_INIT" );
        auth.addProperty("node_id", NODE_ID);
        auth.addProperty("msg_id", UUID.randomUUID().toString());
        auth.addProperty("node_nonce", nonce1);
        auth.addProperty("timestamp", System.currentTimeMillis());
        toBrain.println(gson.toJson(auth));
    }


    // edit this
    static void authResp(String nonce1, String nonce2, String sourceMsgId) {
        JsonObject auth = new JsonObject();
        auth.addProperty("type", "AUTH_RESPONSE");
        auth.addProperty("node_id", NODE_ID);
        auth.addProperty("msg_id", UUID.randomUUID().toString());
        auth.addProperty("reply_to_msg_id", sourceMsgId);
        auth.addProperty("node_nonce", nonce1);
        auth.addProperty("challenge_nonce", nonce2);
        auth.addProperty("proof", nonce2 + nonce1);
        auth.addProperty("timestamp", System.currentTimeMillis());
        toBrain.println(gson.toJson(auth));
    }


    static void echo(String sourceMsgId) {
        JsonObject msg = new JsonObject();
        msg.addProperty("type", "ECHO");
        msg.addProperty("msg_id", UUID.randomUUID().toString());
        msg.addProperty("reply_to_msg_id", sourceMsgId);
        msg.addProperty("node_id", NODE_ID);
        msg.addProperty("timestamp", System.currentTimeMillis());
        toBrain.println(gson.toJson(msg)); 
    }


    // ~~~~ ADVERSARY INTERACTION CHANGES ~~~~
    static void sendFakeBanner(PrintWriter out, String serviceType) {
        switch (serviceType) {
            case "SSH":
                out.println("SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.1");
                break;
            case "FTP":
                out.println("220 FTP server ready");
                break;
            case "HTTP":
                out.println("HTTP/1.1 200 OK\\r\\nServer: Apache/2.4.41\\r\\n");
                break;
            default:
                out.println("220 Service ready");
                break;

        }   
    }


    // ~~~~ NODESTATE SUBCLASS ~~~~
    // Saves the default config settings
    static class NodeState {
         int responseDelayMs;
         boolean dropConnections;
         int activePort;
         String serviceType;
         int attempts;
         String errorResp;

        NodeState() {
            this.responseDelayMs = HoneypotNode.responseDelayMs;
            this.dropConnections = HoneypotNode.dropConnections;
            this.activePort = HoneypotNode.activePort;
            this.serviceType = HoneypotNode.serviceType;
            this.attempts = HoneypotNode.attempts;
            this.errorResp = HoneypotNode.errorResp;
        }
    }

}
