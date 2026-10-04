# ADR 0006: One infrastructure stack per lab

- **Status:** Accepted

## Context

The five labs use different Azure services and are useful on their own. One shared stack would force every lab's resources to exist, and cost money, to try any one of them.

## Decision

Each lab has its own Bicep file and Terraform stack, its own resource group per environment and its own state key. Common resources are shared as Terraform modules, not as shared infrastructure. The pipeline takes a `lab` input or runs all five as a matrix.

## Consequences

- A lab can be created, tested and deleted without touching the others.
- Some resources (logs, Key Vault) are repeated per lab, which costs a little more than sharing.
- Module changes affect every lab, so CI validates and tests all five stacks on every change.
