# SaaS and Cloud Licensing Guidelines

> **Status:** Sample guidance for this application, not an approved technology,
> security, or licensing standard. The organization must review it and replace
> it with approved requirements before relying on it for production decisions.

## 1. Scope and approval

These guidelines apply to hosted software, cloud infrastructure, platform
services, managed services, free trials, add-ons, and marketplace subscriptions
used for organizational work. A trial is still subject to review when it uses
corporate identities, devices, integrations, or data.

Use an approved supplier and product. Before purchase, trial, or production
use, confirm the business owner, user population, data involved, integrations,
expected usage, service region, renewal terms, and total cost. Follow the
Corporate Procurement Policy for budget, sourcing, contract, and approval
requirements.

## 2. Licensing and cost management

Select the license tier and quantity that match the documented need. Confirm
whether charges are per user, consumption-based, tiered, or subject to a
minimum commitment, overage, or true-up. Record renewal dates, notice periods,
price changes, and usage limits with an accountable owner.

Assign licenses to named, authorized users where the supplier terms require
it. Do not share accounts, exceed purchased entitlements, or use personal
subscriptions for organizational work. Review usage periodically, reclaim
unused seats, remove access when a person changes role or leaves, and verify
actual usage before renewal or expansion.

Do not treat a free tier, trial, credit, or promotional price as approval for
ongoing use or as evidence that the supplier's terms are acceptable.

## 3. Identity and access

Use organization-managed identities and single sign-on where available and
required by organizational standards. Require multi-factor authentication for
privileged access. Assign least-privilege roles, restrict administrator
accounts, and review access when users or service responsibilities change.

Manage service accounts, API keys, and integration credentials through
approved secrets-management processes. Do not place credentials in source
code, tickets, shared documents, or chat. Disable unused integrations and
revoke credentials when no longer needed.

## 4. Data protection and AI features

Classify the data that the service will receive. Do not upload confidential,
personal, regulated, or otherwise restricted data unless the service and
configuration have been approved for that data classification and the
necessary contractual and privacy safeguards are in place.

Before enabling an AI, analytics, or content-processing feature, determine
whether submitted data is retained, used for model training, shared with
subprocessors, or used to produce outputs visible to other customers. Obtain
the required security, privacy, and Legal review; disable optional reuse or
sharing features unless approved.

Confirm data location, retention, export, backup, deletion, and incident
processes with the supplier and document any material limitations.

## 5. Cloud configuration and operations

The service owner must maintain a supported configuration, limit public
exposure, enable available security logging, and assign responsibility for
monitoring alerts and supplier advisories. For critical services, document
recovery requirements, backup ownership, and a tested exit or continuity plan.

Use approved network and key-management controls for sensitive workloads.
Review changes to regions, subprocessors, integrations, or service features
that could affect data handling or risk before enabling them.

## 6. Renewal and offboarding

Review business need, seat and consumption levels, security and privacy
posture, contract terms, budget, and alternative options before renewal.
Obtain approval for any increase in scope or commitment before it takes
effect.

At offboarding, remove user and administrator access, revoke tokens and
integrations, export records that must be retained, and arrange return or
deletion of organizational data under the agreement and retention schedule.
Record completion with the service owner.