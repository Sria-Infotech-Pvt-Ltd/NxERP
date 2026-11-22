# Domains and DNS for NXDESK (plan, 2026-11-22)

Based on a public DNS lookup and the read-only look at the server. Nothing was changed.

## In plain words

- A **domain name** (`helpdesk.nxsys.in`) is a name people type. **DNS** is the phone book that says which server (IP address) a name belongs to. You add or change entries in your DNS provider's website.
- Several names can point to the **same server**. The server's web program (nginx) looks at which name the visitor used and hands the request to the right app.
- A **certificate** (the padlock, https) is issued per name by Let's Encrypt, using the `certbot` program that is already installed on the server.

## Facts found

| Fact | Value |
| --- | --- |
| Where DNS for `nxsys.in` is managed | **GoDaddy** (name servers `ns39.domaincontrol.com`, `ns40.domaincontrol.com`), not Hostinger |
| Our server's address | `200.234.40.52` |
| Already pointing to our server | `helpdesk.nxsys.in`, `nxerp.nxsys.in`, `aira.nxsys.in` |
| Points to a **different** server (leave alone) | `erp.nxsys.in` (201.18.221.190) |
| The company website | `nxsys.in` and `www.nxsys.in` (leave alone) |
| Free to use (no record yet) | `nxdesk.nxsys.in`, `id.nxsys.in`, `login.nxsys.in`, `hrms.nxsys.in` |
| Naming trap | the server also runs an older, unrelated service called `nxdesk-web` (database `nxdesk_db`). It has no `nxdesk.nxsys.in` record, but the names are alike. Ask your senior developer what it is before using the name |

## The list

| Role | Public name | Today | What it is | New DNS record? |
| --- | --- | --- | --- | --- |
| **NXDESK**: front page and the one sign-in for every app | `nxdesk.nxsys.in` | free | the identity site (internal name `id`): lists the products, signs people in once | **yes, one A record** |
| **Helpdesk** | `helpdesk.nxsys.in` | live, employees use it | the Helpdesk app and all real data | no |
| **NXERP** | `nxerp.nxsys.in` | DNS and site exist, no real data | the ERP app | no |
| **AIRA HRMS** | `aira.nxsys.in` | DNS exists and an AIRA app already runs on the server (a separate codebase) | announced only in NXDESK ("Coming soon") | no. Do not touch it. Link to it later when it is ready |
| Shared database layer | none | not deployed | internal only, listens on the server itself, never on the internet | no |

## The one DNS record to add

In GoDaddy: sign in, My Products, `nxsys.in`, **DNS** (DNS Management), **Add** a record:

| Type | Name | Value | TTL |
| --- | --- | --- | --- |
| A | `nxdesk` | `200.234.40.52` | 600 seconds |

Check it from your laptop after a few minutes: `nslookup nxdesk.nxsys.in 8.8.8.8` should print `200.234.40.52`.

## What follows the DNS record (needs `sudo` on the server)

1. A web (nginx) block for `nxdesk.nxsys.in` forwarding to the identity site, and the certificate: `sudo certbot --nginx -d nxdesk.nxsys.in`.
2. The identity site itself (its own bench, database and services), per `hostinger-bare-metal-hosting.md`, step H2.
3. On the identity site, two connections (called peers) to `https://helpdesk.nxsys.in` and `https://nxerp.nxsys.in`, so its front page lists both products and sends people to them. The sign-in link between the sites is configured in the same step.

Order of work: first the code deploy in `hostinger-deploy-steps.md` (no DNS change needed), then the DNS record, then steps 1 to 3 above.

## Decisions for the owner

| Question | Suggested answer |
| --- | --- |
| Use `nxdesk.nxsys.in` as the front door, or a separate short name such as `id.nxsys.in` too? | `nxdesk.nxsys.in` only; one name is simpler |
| Keep `aira.nxsys.in` as is until the AIRA HRMS is joined to NXDESK? | yes |
| Is the existing `nxdesk-web` service on the server related to this project? | ask the senior developer before the DNS record is added |
