# COCOHOSPITALS LIS — Analyzer Connector

A desktop-based laboratory analyzer integration application for communicating with medical laboratory instruments over **ASTM TCP/IP** and sending structured laboratory results to the **COCOHOSPITALS LIS**.

The connector is designed to provide reliable communication between laboratory analyzers and the hospital information system (LIS), including ASTM message handling, result parsing, logging, and API integration.

---

## Overview

The Analyzer Connector acts as a bridge between laboratory instruments and the COCOHOSPITALS LIS.

```text
Laboratory Analyzer
        │
        │ ASTM TCP/IP
        ▼
┌─────────────────────────┐
│   Analyzer Connector    │
│                         │
│  • TCP Listener         │
│  • ASTM Handler         │
│  • Message Parser       │
│  • Sample Identification│
│  • Result Extraction    │
│  • Activity Logging     │
└────────────┬────────────┘
             │
             │ HTTPS / REST API
             ▼
┌─────────────────────────┐
│   COCOHOSPITALS LIS     │
│                         │
│  Laboratory Results     │
└─────────────────────────┘
