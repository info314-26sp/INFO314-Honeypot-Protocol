# Project Draft 1 - HDP Protocol Design
By Anthony Covello, Francis Dinh, Eli Gold

**Protocol List** 
*Everyone Please Select 4. Just put your name text to one to claim. Maybe start defining them below the list here or something.*

---
### Format Example
**Sent by..**
- MESSAGE_NAME (sent to whom) ~ Purpose >> Claimed By


**Honeypot Node:**
- HEARTBEAT (to Brain) ~ Let Brain know it's active >>
- EVENT_REPORT (to Brain) ~ Let Brain know about an Event >> Francis
- FAKE_BANNER (to external user) ~ Send out Honeypot Message to External User >>
- AUTH (to Brain) ~ Sent to Brain in setup to Authenticate itself as a real node >> Francis
- PING_RESPONSE (to Brain) ~ Response to Brain's PING to confirm  it's alive >> Francis (Renamed to ECHO)


**Central Brain:**
- CONTROL_COMMAND (to Honeypot) ~ Specific, in-moment instructions and adjustments sent to Honeypot as a reaction to detected attack behavior  >>
- CONFIG_UPDATE (to Honeypot) ~ Lets Honeypot know its operational parameters and baseline behavior >>
- PING (to Honeypot) ~ Sent to Honeypot to check if its still active after the defined # of HEARTBEAT misses >> Francis
- STORE_EVENT (to Store) ~ Sends parsed and defined Event Data to Event Store for storage >>
- NODE_STATUS (to Store) ~ Sends Node Status updates to Event Store for storage >>

**Event Store:**
- ACK (to Central Brain) ~ Sent to Brain to acknowledge data has been recieved and stored >>
- QUERY_RESPONSE (to external user) ~ Sent to external user to meet the demands of their query >>

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
Message: EVENT_REPORT
Description: Relays an event to the central brain server
Sender: Honeypot node -> Central Brain

Format: JSON over TCP

Fields: 
- node_id (int, required)
- event (string, required)
- time (time, required)
- 

Response: 
- Acknowledgement

Side Effects:
- Central brain checks for other events from other honeypot nodes
- Report is stored to Event Store

**Central Brain**
Message: PING
Description: Requests a response from honeypot nodes
Sender: Central Brain -> Honeypot node

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

**Event Store**