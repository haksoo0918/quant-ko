# Security & Sensitive Data Guidelines

This document outlines mandatory security protocols to protect sensitive data and prevent destructive operations within the project.

## 1. Secrets & Credentials Protection

1. **Zero Hardcoded Secrets**: Never commit API keys, tokens, passwords, private keys, database connection strings, or cloud credentials to source control.
2. **Environment Variables**:
   - Store all runtime secrets and configuration in `.env` or local configuration files.
   - Always commit a sanitized `.env.example` documenting all expected variable names with placeholder values.
3. **Pre-Commit Verification**:
   - Verify that `.env`, `.env.local`, and credential files are included in `.gitignore`.
   - Never echo or print secret values into terminal logs, transcripts, or commit messages.

---

## 2. Destructive Operations Safety Protocol

1. **Dangerous Commands**: AI agents are strictly forbidden from executing destructive or irreversible commands without explicit, upfront user confirmation:
   - File deletion: `rm -rf`, `Remove-Item -Recurse -Force`, `shred`
   - Git resets & history mutations: `git reset --hard`, `git clean -fd`, `git push --force`, `git push <remote> +<ref>` (any forced overwrite refspec syntax)
   - Database mutations: `DROP DATABASE`, `TRUNCATE TABLE`, irreversible migration rollbacks
   - System modifications: Disk formatting, firewall changes, global package removals
2. **Zero Autonomous Recovery**:
   - In case of operational errors, unexpected failures, or exceptions, NEVER attempt autonomous recovery, rollback, or destructive mutations.
   - Immediately halt all executions, report the current state objectively, and await specific instructions from the user.
3. **Safe Alternatives**:
   - Prefer trash/recycle bin operations or non-destructive staging.
   - Double-check working directories before executing any delete command.

---

## 3. Dependency & Supply Chain Security

1. **Verified Packages**: Only install well-maintained and reputable packages from official registries (npm, PyPI, crates.io, etc.).
2. **Lockfiles**: Always commit lockfiles (`package-lock.json`, `poetry.lock`, `pnpm-lock.yaml`, `Cargo.lock`) to ensure reproducible and tamper-evident builds.
3. **Audit Checks**: Regularly run security vulnerability audits (e.g. `npm audit`, `pip-audit`) when adding dependencies.
