# Project Draft 1 - HDP Protocol Design
By Anthony Covello, Francis Dinh, Eli Gold

**Protocol List** 
*Everyone Please Select 4. Just put your name text to one to claim. Maybe start defining them below the list here or something.*

---
### Format Example
**Sent by..**
- MESSAGE_NAME (sent to whom) ~ Purpose >> Claimed By

**Honeypot Node:**
- HEARTBEAT (to Brain) ~ Let Brain know it's active >> Anthony
- EVENT_REPORT (to Brain) ~ Let Brain know about an Event >> Francis
- FAKE_BANNER (to external user) ~ Send out Honeypot Message to External User >> Anthony
- AUTH (to Brain) ~ Sent to Brain in setup to Authenticate itself as a real node >> Francis
- PING_RESPONSE (to Brain) ~ Response to Brain's PING to confirm it's alive >> Francis (Renamed to ECHO)
- COMMAND_ACK (to Brain) ~ Confirmation that a CONTROL_COMMAND or CONFIG_UPDATE has been recieved and if it's been enacted >> Anthony

**Central Brain:**
- CONTROL_COMMAND (to Honeypot) ~ Specific, in-moment instructions and adjustments sent to Honeypot as a reaction to detected attack behavior >> Anthony
- CONFIG_UPDATE (to Honeypot) ~ Lets Honeypot know its operational parameters and baseline behavior >> ANTHONY
- PING (to Honeypot) ~ Sent to Honeypot to check if its still active after the defined # of HEARTBEAT misses >> Francis
- STORE_EVENT (to Store) ~ Sends parsed and defined Event Data to Event Store for storage >> Eli
- NODE_STATUS (to Store) ~ Sends Node Status updates to Event Store for storage >> Eli

**Event Store:**
- ACK (to Central Brain) ~ Sent to Brain to acknowledge data has been recieved and stored >> Eli
- QUERY_RESPONSE (to external user) ~ Sent to external user to meet the demands of their query >> Eli

---
### **Requirements and Example:**
This protocol specification should include:

1. A list of all message types
2. A short, one sentence description of each message type
3. The structure and format for each message
4. Which components send and/or receive this message
5. Required and optional fields (if any) for each message
6. Expected response(s) (if any)
7. Any expected side effects (e.g., "saves the message to disk")
8. At least one example message for each

### *Example*

~~~~~
Message: CREATE_TASK (R1)
Description: Requests that the server record the existence of a new task. (R2)
Sender: Client → Server (R4)

Format: JSON over TCP (R3)

Fields: (R5)
- task_id (string, required)
- description (string, required)
- priority (int, optional)

Response: (R6)
- SUCCESS or ERROR

Side Effects: (R7)
- Server saves the new task to its database

Example: (R8)
{
  "type": "CREATE_TASK",
  "task_id": "task-001",
  "description": "Write the quarterly report",
  "priority": 2
}
~~~~~

### Message References

**Honeypot Nodes**

~~~~~
Message: HEARTBEAT
Description: Message sent at every 30 second interval to confirm node's operational status
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
Message: EVENT_REPORT
Description: Relays a captured attacker interaction to the Central Brain for classification
Sender: Honeypot Node → Central Brain

Format: JSON over TCP

Fields:
- msg_id (string, required)
- node_id (string, required)
- timestamp (long, required)
- source_ip (string, required)
- source_port (int, required)
- service (string, required) - simulated service that was hit (e.g. "SSH", "HTTP", "FTP")
- event_type (string, required) - type of interaction (e.g. "LOGIN_ATTEMPT", "PORT_PROBE")
- payload (object, optional) - captured interaction data, such as attempted username/password, HTTP request data, etc.

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

**Central Brain**

~~~~~
Message: PING
Description: Requests a response from honeypot nodes
Sender: Central Brain → Honeypot Node

Format: JSON over TCP

Fields:
- ping_id (int, required)
- time (time, required)

Example:
{
  "type": "PING",
  "ping_id": 50,
  "time": -27107477939000
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
      "command": "SET_PORTS",
      "parameters": {
        "port_num": 80
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