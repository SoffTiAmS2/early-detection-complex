"""Catalog of supported honeypot profiles, services and UI settings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SERVICE_CATALOG: dict[str, dict[str, Any]] = {
    "ssh": {
        "title": "SSH",
        "port": 2222,
        "protocol": "ssh",
        "banner": "SSH-2.0-OpenSSH_8.4",
        "response": "Permission denied, please try again.\r\n",
    },
    "telnet": {
        "title": "Telnet",
        "port": 2323,
        "protocol": "telnet",
        "banner": "Debian GNU/Linux 13\r\nlogin: ",
        "response": "Password: ",
    },
    "http": {
        "title": "HTTP",
        "port": 8081,
        "protocol": "http",
        "banner": "HTTP/1.1 200 OK\r\nServer: nginx/1.22.1\r\nContent-Type: text/plain\r\n\r\nservice online\r\n",
        "response": "",
    },
    "https": {
        "title": "HTTPS",
        "port": 8443,
        "protocol": "https",
        "banner": "HTTP/1.1 200 OK\r\nServer: nginx/1.22.1\r\nContent-Type: text/plain\r\n\r\nsecure service online\r\n",
        "response": "",
    },
    "ftp": {
        "title": "FTP",
        "port": 2121,
        "protocol": "ftp",
        "banner": "220 fileserver FTP service ready\r\n",
        "response": "530 Login incorrect.\r\n",
    },
    "smtp": {
        "title": "SMTP",
        "port": 2525,
        "protocol": "smtp",
        "banner": "220 mail-gw ESMTP Postfix\r\n",
        "response": "250 OK\r\n",
    },
    "mysql": {
        "title": "MySQL",
        "port": 33060,
        "protocol": "mysql",
        "banner": "5.7.31-log MySQL Community Server\r\n",
        "response": "",
    },
    "mssql": {
        "title": "MSSQL",
        "port": 1433,
        "protocol": "mssql",
        "banner": "",
        "response": "",
    },
    "modbus": {
        "title": "Modbus",
        "port": 1502,
        "protocol": "modbus",
        "banner": "",
        "response": "",
    },
    "s7": {
        "title": "Siemens S7",
        "port": 102,
        "protocol": "s7",
        "banner": "",
        "response": "",
    },
    "snmp": {
        "title": "SNMP",
        "port": 161,
        "protocol": "snmp",
        "banner": "",
        "response": "",
    },
    "sip": {
        "title": "SIP",
        "port": 5060,
        "protocol": "sip",
        "banner": "SIP/2.0 401 Unauthorized\r\n",
        "response": "",
    },
    "vnc": {
        "title": "VNC",
        "port": 5900,
        "protocol": "vnc",
        "banner": "RFB 003.008\n",
        "response": "",
    },
    "redis": {
        "title": "Redis",
        "port": 6379,
        "protocol": "redis",
        "banner": "-NOAUTH Authentication required.\r\n",
        "response": "-NOAUTH Authentication required.\r\n",
    },
    "printer": {
        "title": "Printer",
        "port": 9100,
        "protocol": "printer",
        "banner": "HP JetDirect ready\r\n",
        "response": "",
    },
    "pop3": {
        "title": "POP3",
        "port": 110,
        "protocol": "pop3",
        "banner": "+OK POP3 server ready\r\n",
        "response": "-ERR authentication failed\r\n",
    },
    "imap": {
        "title": "IMAP",
        "port": 143,
        "protocol": "imap",
        "banner": "* OK IMAP4rev1 Service Ready\r\n",
        "response": "NO authentication failed\r\n",
    },
    "postgresql": {
        "title": "PostgreSQL",
        "port": 5432,
        "protocol": "postgresql",
        "banner": "",
        "response": "",
    },
    "socks5": {
        "title": "SOCKS5",
        "port": 1080,
        "protocol": "socks5",
        "banner": "",
        "response": "",
    },
    "smb": {
        "title": "SMB",
        "port": 445,
        "protocol": "smb",
        "banner": "",
        "response": "",
    },
}


HONEYPOT_CATALOG: dict[str, dict[str, Any]] = {
    "opencanary": {
        "title": "OpenCanary",
        "role": "dmz",
        "description": "Low-interaction canary daemon with many fake network services.",
        "default_services": ["ssh", "http", "ftp", "smtp"],
        "services": ["ssh", "telnet", "ftp", "http", "https", "mysql", "mssql", "smtp", "snmp", "sip", "vnc", "redis"],
        "settings": [
            {"key": "node_id", "title": "Node ID", "type": "text", "default": "opencanary-node"},
            {"key": "listen_addr", "title": "Listen address", "type": "text", "default": "0.0.0.0"},
            {"key": "honeycred_user", "title": "Honeycred user", "type": "text", "default": "admin"},
            {"key": "honeycred_password", "title": "Honeycred password", "type": "text", "default": "password"},
            {"key": "http_skin", "title": "HTTP skin", "type": "select", "default": "basic", "options": ["basic", "nas-login", "jenkins", "wordpress"]},
        ],
    },
    "cowrie": {
        "title": "Cowrie",
        "role": "office",
        "description": "SSH/Telnet honeypot focused on brute force, shell interaction and downloaded artifacts.",
        "default_services": ["ssh", "telnet"],
        "services": ["ssh", "telnet"],
        "settings": [
            {"key": "hostname", "title": "Fake hostname", "type": "text", "default": "srv01"},
            {"key": "kernel_version", "title": "Kernel version", "type": "text", "default": "5.10.0-23-amd64"},
            {"key": "ssh_version", "title": "SSH version", "type": "text", "default": "SSH-2.0-OpenSSH_8.4"},
            {"key": "backend", "title": "Backend", "type": "select", "default": "shell", "options": ["shell", "proxy", "backend_pool", "llm"]},
            {"key": "auth_class", "title": "Auth policy", "type": "select", "default": "deny", "options": ["deny", "random", "allow_known"]},
            {"key": "download_limit_mb", "title": "Download limit MB", "type": "number", "default": 10},
            {"key": "sftp_enabled", "title": "SFTP enabled", "type": "boolean", "default": True},
        ],
    },
    "heralding": {
        "title": "Heralding",
        "role": "office",
        "description": "Credential-catching honeypot for common login protocols.",
        "default_services": ["ssh", "telnet", "ftp", "smtp", "http"],
        "services": ["ftp", "telnet", "ssh", "http", "https", "pop3", "imap", "smtp", "vnc", "postgresql", "socks5"],
        "settings": [
            {"key": "listen_addr", "title": "Listen address", "type": "text", "default": "0.0.0.0"},
            {"key": "ssh_version", "title": "SSH version", "type": "text", "default": "SSH-2.0-OpenSSH_7.6"},
            {"key": "capture_passwords", "title": "Capture auth attempts", "type": "boolean", "default": True},
            {"key": "json_sessions", "title": "JSON session log", "type": "boolean", "default": True},
        ],
    },
    "conpot": {
        "title": "Conpot",
        "role": "ot-mining",
        "description": "ICS/OT honeypot with protocol templates for industrial environments.",
        "default_services": ["http", "modbus"],
        "services": ["http", "modbus", "s7", "snmp"],
        "settings": [
            {"key": "template", "title": "Template", "type": "select", "default": "default", "options": ["default", "iec104", "ipmi", "kamstrup_382", "guardian_ast"]},
            {"key": "device_name", "title": "Device name", "type": "text", "default": "S7-200"},
            {"key": "vendor", "title": "Vendor", "type": "text", "default": "Siemens"},
            {"key": "strict_mode", "title": "Strict protocol mode", "type": "boolean", "default": False},
        ],
    },
    "dionaea": {
        "title": "Dionaea",
        "role": "dmz",
        "description": "Malware-focused honeypot with protocol modules and artifact capture.",
        "default_services": ["http", "ftp", "mysql", "smb"],
        "services": ["http", "https", "ftp", "mysql", "mssql", "smb", "sip"],
        "settings": [
            {"key": "download_dir", "title": "Download directory", "type": "text", "default": "/data/downloads"},
            {"key": "capture_binaries", "title": "Capture binaries", "type": "boolean", "default": True},
            {"key": "listen_addr", "title": "Listen address", "type": "text", "default": "0.0.0.0"},
            {"key": "tls_enabled", "title": "TLS modules enabled", "type": "boolean", "default": False},
            {"key": "nfq_enabled", "title": "NFQ dynamic service mode", "type": "boolean", "default": False},
        ],
    },
    "honeytrap": {
        "title": "Honeytrap",
        "role": "custom",
        "description": "Generic low-interaction service trap used for custom decoy surfaces.",
        "default_services": ["ssh", "http", "ftp", "printer"],
        "services": ["ssh", "http", "ftp", "printer", "redis"],
        "settings": [
            {"key": "banner_profile", "title": "Banner profile", "type": "select", "default": "linux", "options": ["linux", "printer", "web", "custom"]},
            {"key": "connection_timeout_sec", "title": "Connection timeout sec", "type": "number", "default": 2},
            {"key": "capture_payloads", "title": "Capture payload previews", "type": "boolean", "default": True},
        ],
    },
}


def default_settings(honeypot_type: str) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for field in HONEYPOT_CATALOG[honeypot_type]["settings"]:
        settings[field["key"]] = deepcopy(field.get("default"))
    return settings


def default_honeypot(honeypot_type: str) -> dict[str, Any]:
    item = HONEYPOT_CATALOG[honeypot_type]
    return {
        "type": honeypot_type,
        "enabled": True,
        "services": list(item["default_services"]),
        "settings": default_settings(honeypot_type),
    }


def legacy_honeypot(profile: str, services: list[str] | None = None) -> dict[str, Any]:
    honeypot_type = profile if profile in HONEYPOT_CATALOG else "opencanary"
    honeypot = default_honeypot(honeypot_type)
    if services:
        allowed = set(HONEYPOT_CATALOG[honeypot_type]["services"])
        honeypot["services"] = [service for service in services if service in allowed]
    return honeypot


def catalog_payload() -> dict[str, Any]:
    return {
        "honeypots": HONEYPOT_CATALOG,
        "services": {
            key: {"title": value["title"], "port": value["port"], "protocol": value["protocol"]}
            for key, value in SERVICE_CATALOG.items()
        },
    }
