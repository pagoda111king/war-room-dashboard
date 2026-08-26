# Security Policy

War Room Dashboard is local-first software. By default it runs on your machine and stores data in a local SQLite database.

## Supported Versions

The `main` branch is the supported development version.

## Reporting a Vulnerability

Please report security concerns through GitHub Issues unless the report contains sensitive private data. If it does, contact the maintainer through the GitHub profile.

## Important Local-First Notes

- Do not expose the server to the public internet without adding authentication, HTTPS, backups, and write permission controls.
- Do not commit `app/项目台.db` or any real personal database.
- Do not store secrets in the SQLite database unless you understand the risk.
- The optional `OPENMAIC_URL` hook should point to a trusted local service.

## Current Security Boundary

This project is built for trusted local use and private LAN demos. It is not yet a hardened multi-user web app.
