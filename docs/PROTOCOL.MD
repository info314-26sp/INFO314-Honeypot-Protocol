# HDP Protocol Design
By Anthony Covello, Francis Dinh, Eli Gold

---
### Message Overviews

**Honeypot Node:**
- HEARTBEAT (to Brain) ~ Let Brain know it's active 
- EVENT_REPORT (to Brain) ~ Let Brain know about an Event
- FAKE_BANNER (to external user) ~ Send out Honeypot Message to External User 
- AUTH (to Brain) ~ Sent to Brain in setup to Authenticate itself as a real node
- ECHO (to Brain) ~ Response to Brain's PING to confirm it's alive 
- CMD_ACK (to Brain) ~ Confirmation that a CONTROL_COMMAND or CONFIG_UPDATE has been recieved and if it's been enacted 

**Central Brain:**
- CONTROL_COMMAND (to Honeypot) ~ Specific, in-moment instructions and adjustments sent to Honeypot as a reaction to detected attack behavior
- CONFIG_UPDATE (to Honeypot) ~ Lets Honeypot know its operational parameters and baseline behavior
- PING (to Honeypot) ~ Sent to Honeypot to check if its still active after the defined # of HEARTBEAT misses
- STORE_EVENT (to Store) ~ Sends parsed and defined Event Data to Event Store for storage 
- NODE_STATUS (to Store) ~ Sends Node Status updates to Event Store for storage

**Event Store:**
- ACK (to Central Brain) ~ Sent to Brain to acknowledge data has been recieved and stored
- QUERY_RESPONSE (to external user) ~ Sent to external user to meet the demands of their query 

---

### Message References

**Honeypot Nodes**

~~~~~
Message: HEARTBEAT
Description: Message sent at every x second interval (30 by default) to confirm node's operational status
Sender: Honeypot Node → Central Brain

Format: JSON over TCP

Fields:
- seq_Num (int, required)
- msg_id (string, required)
- node_id (string, required)
- timestamp (long, required)

Response:
- No response

Side Effects:
- Central Brain knows the sending Node is active, and can keep its list of active nodes updated.

Example:
{
  "type": "HEARTBEAT",
  "seq_Num": 1,
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "timestamp": 1771434120000
}
~~~~~

~~~~~
Message: FAKE_BANNER
Description: A plaintext banner sent to an external actor. Meant to simulate a real vulnerable service and encourage the external actor to engage with the node further.
Sender: Honeypot Node → External Interactor

Format: Plaintext over TCP

Fields:
- banner_text (string, required) {raw plaintext}

Response:
- No expected Message response, but any data sent back by the external interactor is logged by the Honeypot Node.

Side Effects:
- The external interactor believes thay're connected to a real service, as presented by FAKE_BANNER's message. Allows Honeypot Node to further monitor the external actor's behavior.

Example:

SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.1
~~~~~

~~~~~
Message: EVENT_REPORT
Description: Relays a captured attacker interaction to the Central Brain for classification
Sender: Honeypot Node → Central Brain

Format: JSON over TCP

Fields:
- msg_id (string, required)
- node_id (string, required)
- source_ip (string, required)
- source_port (int, required)
- service (string, required) - simulated service that was hit (e.g. "SSH", "HTTP", "FTP")
- event_type (string, required) - type of interaction (e.g. "LOGIN_ATTEMPT", "PORT_PROBE")
- payload (object, optional) - captured interaction data, such as attempted username/password, HTTP request data, etc.
- timestamp (long, required)

Response:
- No response

Side Effects:
- Central Brain runs classification rules against the event
- If severity threshold is met, Central Brain dispatches a CONTROL_COMMAND to the originating node
- Central Brain forwards classified event to Event Store via STORE_EVENT

Example:
{
  "type": "EVENT_REPORT",
  "msg_id": "a1b2c3d4-0001-4aaa-8888-000000000001",
  "node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "timestamp": 1771434120000,
  "source_ip": "10.0.0.5",
  "source_port": 51200,
  "service": "SSH",
  "event_type": "LOGIN_ATTEMPT",
  "payload": {
    "username": "root",
    "password": "admin123"
  }
}
~~~~~

~~~~~
Message: CMD_ACK
Description: Confirmation that a CONTROL_COMMAND or CONFIG_UPDATE has been recieved and if it's been successfully enacted
Sender: Honeypot Node → Central Brain

Format: JSON over TCP

Fields:
- msg_id (string, required)
- node_id (string, required)
- ack_for (string, required)
- cmd_msg_id (string, required)
- applied (boolean, required)
- error_msg (string, optional)
- timestamp (long, required)

Response:
- No response

Side Effects:
- Central Brain gets confirmation its orders were recieved and carried out successfully, or can correct the situation if not

Example:
{
  "type": "CMD_ACK",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "ack_for": "CONFIG_UPDATE",
  "cmd_msg_id": "89b5c2e4-f013-4a7d-9c81-3d6e2b8f5019",
  "applied": false,
  "error_msg": "INVALID_CONFIG",
  "timestamp": 1771434120000
}
~~~~~

~~~~~
Message: AUTH
Description: Authenticates the honeypot node to the central brain for initialization
Sender: Honeypot Node → Central Brain

Format: JSON over TCP

Fields:
- msg_id (string, required)
- node_id (string, required)
- timestamp (long, required)
- credentials (string, required) - Node's security certificate


Response:
- CONFIG_UPDATE on success
- Connection dropped on failure

Side Effects:
- Central brain recognizes node as part of the secure network
- If no response is recieved, node assumes monitoring protocols and reattempts authorization. The failure to connect will be recorded and presented to central brain upon connection. 

Example:
{
  "type": "AUTH",
  "timestamp": 1771434180000,
  "credentials": "90nWW88O0lOl1sJ8oM1jkk42FIJ8O9A9P44UlFW1ojI7712Mjn42Mfq8sP90jR199aOK1JkIPdOsifiI9j7nQQf9kf2FfkwOk7j8U2jn9O7lpQQpW2O4I0njOk4kd",
  "msg_id": "b289f0b8-ed66-4570-b249-d00be6a33cf3",
  "node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2"
}
~~~~~

~~~~~
Message: ECHO
Description: Responds to PING message from Central Brain to confirm liveness.
Sender: Honeypot Node → Central Brain

Format: JSON over TCP

Fields:
- msg_id (string, required)
- node_id (string, required)
- ping_id (string, required)
- timestamp (long, required)

Response:
- No response

Side Effects:
- Central brain marks node back online if it was previously flagged as unresponsive

Example:
{
  "type": "ECHO",
  "msg_id": "b289f0b8-ed66-4570-b249-d00be6a33cf3",
  "timestamp": 1771434180000,
  "node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "ping_id": "b5c645j24-3402-4vvh-by94-452d0l0a43l4"
}
~~~~~

**Central Brain**

~~~~~
Message: PING
Description: Sent by the Central Brain to a Honeypot Node to confirm liveness after missed heartbeats.
Sender: Central Brain → Honeypot Node

Format: JSON over TCP

Fields:
- msg_id (string, required)
- target_node_id (string, required)
- timestamp (long, required)

Response:
- ECHO

Side Effects:
- If no ECHO is received within the timeout window, the Central Brain marks the node as offline and sends a NODE_STATUS to the Event Store

Example:
{
  "type": "PING",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "target_node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "timestamp": 1771434180000
}
~~~~~

~~~~~
Message: CONTROL_COMMAND
Description: Specific, in-moment instructions and adjustments sent to a Honeypot Node as a reaction to detected attack behavior. Issued command changes are expected to expire after the Honeypot Node's current connection is dropped.
Sender: Central Brain → Honeypot Node

Format: JSON over TCP

Fields:
- msg_id (string, required)
- rec_node_id (string, required)
- cc_commands (array of objects, required)
  - command (string, required)
  - parameters (object, optional)
- timestamp (long, required)

Response:
- CMD_ACK

Side Effects:
- The specified Honeypot Node attempts to apply the received commands for the duration of the current connection, resetting to current baseline behavior after disconnection. It responds with a CMD_ACK indicating if the application was a success or failure

Example:
{
  "type": "CONTROL_COMMAND",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "rec_node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "cc_commands": [
    {
      "command": "SLOW_RESPONSE",
      "parameters": {
        "delay_ms": 5000
      }
    }
  ],
  "timestamp": 1771434120000
}
~~~~~

~~~~~
Message: CONFIG_UPDATE
Description: Sends a command to a specific Honeypot Node to update its operational parameters and baseline behavior, overwriting previous behavior.
Sender: Central Brain → Honeypot Node

Format: JSON over TCP

Fields:
- msg_id (string, required)
- rec_node_id (string, required)
- cu_commands (array of objects, required)
  - command (string, required)
  - parameters (object, optional)
- timestamp (long, required)

Response:
- CMD_ACK

Side Effects:
- The specified Honeypot Node attempts to apply the received config update by overwriting it's previous behavior. It responds with a CMD_ACK indicating success or failure

Example:
{
  "type": "CONFIG_UPDATE",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "rec_node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "cu_commands": [
    {
      "command": "SET_HEARTBEAT_INTERVAL",
      "parameters": {
        "heartbeatInterval": 30
      }
    }
  ],
  "timestamp": 1771434120000
}
~~~~~

~~~~~
Message: STORE_EVENT
Description: Sent by the Central Brain to the Event Store to persist a classified attack event.
Sender: Central Brain → Event Store

Format: JSON over TCP

Fields:
- msg_id (string, required)
- event_id (string, required) — unique identifier for this event record
- node_id (string, required) — originating honeypot node
- source_ip (string, required)
- source_port (int, required)
- service (string, required) — e.g. "SSH", "FTP", "HTTP"
- event_type (string, required) — e.g. "LOGIN_ATTEMPT", "PORT_PROBE", "HTTP_REQUEST"
- classification (string, required) — e.g. "BRUTE_FORCE", "PORT_SCAN", "SQL_INJECTION"
- severity (int, required) — score from 1 to 10
- payload (object, optional) — captured interaction data
- timestamp (long, required)

Response:
- ACK

Side Effects:
- Event Store checks for a duplicate event_id before writing to ensure idempotent storage
- Event Store writes the record to its database

Example:
{
  "type": "STORE_EVENT",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "event_id": "evt-00192",
  "node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "source_ip": "10.0.0.5",
  "source_port": 51200,
  "service": "SSH",
  "event_type": "LOGIN_ATTEMPT",
  "classification": "BRUTE_FORCE",
  "severity": 8,
  "payload": {
    "username": "root",
    "password": "admin123"
  },
  "timestamp": 1771434120000
}
~~~~~

~~~~~
Message: NODE_STATUS
Description: Sent by the Central Brain to the Event Store to record a change in a Honeypot Node's operational status.
Sender: Central Brain → Event Store

Format: JSON over TCP

Fields:
- msg_id (string, required)
- node_id (string, required) — the node whose status has changed
- status (string, required) — "ONLINE" or "OFFLINE"
- reason (string, optional) — e.g. "missed_heartbeats", "node_recovered"
- last_seen (long, optional) — timestamp of last received HEARTBEAT, present when status is "OFFLINE"
- timestamp (long, required)

Response:
- ACK

Side Effects:
- Event Store persists the status record to its database

Example:
{
  "type": "NODE_STATUS",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "node_id": "b3c89a24-1102-4bbf-bc9e-634d0b1a03d2",
  "status": "OFFLINE",
  "reason": "missed_heartbeats",
  "last_seen": 1771434090000,
  "timestamp": 1771434180000
}
~~~~~

**Event Store**

~~~~~
Message: ACK
Description: Sent by the Event Store to confirm that a message has been received and successfully persisted.
Sender: Event Store → Central Brain

Format: JSON over TCP

Fields:
- msg_id (string, required)
- ack_for_msg_id (string, required) — msg_id of the message being acknowledged
- success (boolean, required)
- error_msg (string, optional) — present only if success is false
- timestamp (long, required)

Response:
- None

Side Effects:
- If success is false, Central Brain retries the original message up to 3 times before logging a storage failure alert

Example:
{
  "type": "ACK",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "ack_for_msg_id": "a1b2c3d4-0007-4aaa-8888-000000000007",
  "success": true,
  "timestamp": 1771434120500
}
~~~~~

~~~~~
Message: QUERY_RESPONSE
Description: Sent by the Event Store to deliver requested records to an analyst.
Sender: Event Store → Analyst

Format: JSON over TCP

Fields:
- msg_id (string, required)
- query_msg_id (string, required) — msg_id of the originating query
- result_count (int, required)
- results (array of objects, required) — matching event or node status records
- timestamp (long, required)

Response:
- None

Side Effects:
- None

Example:
{
  "type": "QUERY_RESPONSE",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "query_msg_id": "a1b2c3d4-0011-4aaa-8888-000000000011",
  "result_count": 2,
  "results": [
    {
      "event_id": "evt-00192",
      "classification": "BRUTE_FORCE",
      "severity": 8,
      "source_ip": "10.0.0.5",
      "timestamp": 1771434120000
    },
    {
      "event_id": "evt-00193",
      "classification": "PORT_SCAN",
      "severity": 6,
      "source_ip": "10.0.0.5",
      "timestamp": 1771434135000
    }
  ],
  "timestamp": 1771434200000
}
~~~~~

**Analyst Commands**

~~~~~
Message: QUERY

Description: This is the message format that should be sent by an analyst to the Event Store to request records matching specific criteria.
Sender: Analyst → Event Store

Format: JSON over TCP

Fields:
- msg_id (string, required)
- search (object, required) — key-value pairs to filter records by e.g. source_ip, classification, severity

Response:
- QUERY_RESPONSE

Side Effects:
- The analyst recieves back the records they requested.

Example:
{
  "type": "QUERY",
  "msg_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "search": {
    "source_ip": "10.0.0.5"
  }
}
~~~~~

