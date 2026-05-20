# Honeypot Detection Protocol

## Abstract
This network protocol allows for decoy network nodes to detect and record potential cyberattacks.

---

## Introduction
Cyberattacks are a growing problem for institutions that manage sensitive data, and the tools used to defend against them have not always kept pace. Platforms that millions of people rely on have been breached in recent years, and in many cases the attack went undetected until significant damage was done. Simply watching network logs is no longer enough. Administrators need systems that actively draw out attackers and gather intelligence on them in real time. Our project builds exactly that: a distributed honeypot system that uses decoy network nodes to simulate vulnerable services, lure in suspicious actors, and capture their behavior for analysis. 

---

## Architecture

The system is composed of three independently running components:

| Component | Role |
|---|---|
| **Honeypot Node** | Simulates vulnerable services (SSH, FTP, HTTP) to attract and observe attackers |
| **Central Brain** | Classifies attack behavior, coordinates node responses, and routes events to storage |
| **Event Store** | Persists classified events and node status data, exposes a query interface for analysts |


![Architecture Diagram](images/systemArchOverview.png)


---

## Protocol

All components communicate exclusively over TCP using HDP, a custom JSON-based messaging protocol. The protocol is designed for internal use only and is never exposed to the network being monitored.

See the full message specification in [`PROTOCOL.md`](./PROTOCOL.md).

---


## Further Reading
[Protocol Specification](./PROTOCOL.md)  
[Project Proposal](./PROPOSAL.md)

---

## Status of This Memo  
---

## Copyright Notice
---


## Tech Stack

![Java](https://img.shields.io/badge/Java-ED8B00?style=flat&logo=openjdk&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)

---

## Team

- Anthony Covello
- Francis Dinh
- Eli Gold