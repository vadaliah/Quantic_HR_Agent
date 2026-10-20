# Aurora reuse findings (read-only)

**Date:** 20 October 2026  
**Status:** Discovery only. **No AWS mutations.** No snapshots, start/stop, schema, `quantic_hr` database, roles, security-group edits, or CDK deploy.  
**Intention (not yet approved):** Reuse the existing Café Fausse Aurora cluster for Quantic after the HR data model is finalized, subject to cost and connectivity validation.

This supersedes the “Quantic must have a newly provisioned cluster” assumption in `docs/AURORA_ARCHITECTURE_DECISION.md`. Local PostgreSQL remains acceptable for isolated tests. Undeployed Quantic CDK stays an optional path; do not delete it.

Legend: **observed** (API/CLI today), **inferred** (docs + observed config), **unverified** (would need start, SQL, or a mutation).

## Session evidence

- **Observed** caller: account `287238357427`, region `us-east-2`, role `AWSReservedSSO_AEA-Sandbox-PowerUser_5722ca7eda84f45e`, user `hirenvadalia`. Profile used: `AEA-Sandbox-PowerUser-287238357427`.
- Commands (all describe/list; secret **values** were not read):
  - `aws sts get-caller-identity`
  - `aws rds describe-db-clusters|describe-db-instances|describe-db-cluster-snapshots|describe-db-cluster-automated-backups|describe-events`
  - `aws cloudformation describe-stacks|list-stack-resources` for `CafeFausseApplicationStack` and `AeaSandboxStack`
  - `aws ec2 describe-vpcs|describe-subnets|describe-route-tables|describe-security-groups|describe-nat-gateways|describe-addresses|describe-vpc-endpoints|describe-instances|describe-availability-zones`
  - `aws secretsmanager list-secrets` (Name/ARN only)

---

## 1. Inventory / dependencies

### Café Fausse (reuse candidate)

| Item | Value | Kind |
|---|---|---|
| Stack | `CafeFausseApplicationStack` `CREATE_COMPLETE`, created 2026-09-02T01:28:25Z, last updated 2026-09-02T01:28:39Z | observed |
| Cluster id | `cafefausseapplicationstac-databaseaurorapostgres65-zchaodeehzxe` | observed |
| ARN | `arn:aws:rds:us-east-2:287238357427:cluster:cafefausseapplicationstac-databaseaurorapostgres65-zchaodeehzxe` | observed |
| Engine | `aurora-postgresql` **17.4**, `EngineMode=provisioned` (Serverless v2 instance class) | observed |
| Database name | `cafe_fausse_db` | observed |
| Master username | `cafe_fausse_admin` (password not read) | observed |
| Secret name | `cafe-fausse-application/database/admin` | observed |
| IAM DB auth | enabled | observed |
| Encryption | storage encrypted | observed |
| Capacity | Serverless v2 min **0.5** / max **2.0** ACU; `SecondsUntilAutoPause` **absent** | observed |
| Lifecycle | cluster and writer **stopped**; writer `db.serverless` in `us-east-2a`; `PubliclyAccessible=false` | observed |
| Port | 5432 | observed |
| Deletion protection | **false** | observed |
| Backup retention | **1 day**; window `06:19–06:49` UTC | observed |
| Parameter group | `default.aurora-postgresql17` | observed |
| VPC | `vpc-0a6e62a6eae7cb617` CIDR `10.0.0.0/16`, not default | observed |
| Subnets | `subnet-0d331fbab109578a0` `10.0.0.0/24` **use2-az1** / `us-east-2a`; `subnet-068b3bf98550a93e7` `10.0.1.0/24` **use2-az2** / `us-east-2b`; isolated, no public IP | observed |
| Routes | local `10.0.0.0/16` only; **no IGW, no NAT** | observed |
| DB SG | `sg-09f0dd96526f3085f` ingress TCP 5432 **only** from admin host SG `sg-00c1c1abbe77e4e55` | observed |
| Admin host | `i-0fa327066e84e94a5` `t4g.nano` **stopped**, `10.0.0.4` | observed |

Writer instance id: `cafefausseapplicationstac-databaseaurorapostgreswr-j3mic7quyghf`.

### AEA (do not reuse for Quantic)

Separate cluster `aeasandboxstack-databaseaurorapostgres6560ef93-56zpfc4li8qg`, database `aea`, secret `aea/sandbox/database/admin`, VPC `vpc-0a8c8b6535f37055d` (also `10.0.0.0/16`, different VPC id), same engine/capacity/stopped shape. Stack `AeaSandboxStack` `UPDATE_COMPLETE` (last updated 2026-08-18).

**Observed:** Café and AEA are two stacks, two VPCs, two clusters, two secrets. Deleting either stack would delete that stack’s Aurora, secret, VPC, and admin host.

### What cannot be deleted safely

- **Café Fausse stack/cluster/secret/VPC** if the restaurant app or a future Quantic share still needs them.
- **AEA stack/cluster** is unused by Café and unused by Quantic today; deleting it is a **separate** product decision, not required for reuse, and is **not** recommended in this step.
- **CDKToolkit** in this account/region remains the bootstrap stack.

### Drift (unchanged from Step 0)

CloudFormation still lists three Café interface endpoints (`vpce-0f9fe810eeb6a7921`, `vpce-0906b320c4e267d6a`, `vpce-089b9d994c38142bb`) as `CREATE_COMPLETE`. `describe-vpc-endpoints` for the **region** returned **zero** endpoints. **Observed** drift. Not repaired.

### Unverified (needs start + SQL; not done)

- Whether `vector` / `pgvector` is installed on `cafe_fausse_db`.
- Existing Café tables, sizes, and whether a second database on the same cluster is viable.
- Actual storage bytes vs `AllocatedStorage: 1`.

---

## 2. Costs

Prices below are **approximate us-east-2 public list** (inferred), not an invoice.

### Charged while clusters are **stopped** (unavoidable existing)

| Resource | Observed state | Approx. ongoing |
|---|---|---|
| Aurora cluster volume | 1 GB reported each, encrypted | ~$0.10/GB-month storage **per cluster** (~$0.20 for Café+AEA) |
| Automated backups | 1-day retention; one automated snapshot each (2026-10-18) | usually within free backup equal to cluster volume; extra backup GB ~$0.021/GB-month |
| Manual snapshots | **none** for these clusters | $0 today |
| NAT / EIP | **zero** in the account | $0 |
| VPC interface endpoints | **zero live** | $0 unless CFN drift is “repaired” (~$7–8/month per AZ endpoint) |
| Admin EC2 `t4g.nano` × 2 | stopped | instance hours $0; **EBS** still billed (**inferred** ~$0.5–1/month each) |
| CloudWatch | not fully inventoried | small |

Stopped Aurora is **not** free: storage + backup remain. **Observed** AWS behavior: a stopped cluster **auto-starts after seven days**. Café events:

- 2026-10-10: started *because it exceeded the maximum allowed time being stopped*
- 2026-10-18 11:02Z: stopped again

AEA auto-started 2026-10-13, stopped 2026-10-18.

**Inferred waste:** each 7-day restart at 0.5 ACU until someone stops it again is on the order of **~$1.5/day** (~$0.12/ACU-hour × 0.5 × 24). Café ran ~8 days after the Oct 10 forced start (~$10–12). This will recur around **~25 Oct 2026** unless the cluster is stopped again or auto-pause-to-0 is configured (a mutation; not done).

### Incremental Quantic cost if the Café cluster is **shared** (no second cluster)

| Item | Incremental vs today |
|---|---|
| Second Aurora cluster / NAT / EIP | **avoided** if reuse is approved |
| Extra cluster volume for HR + embeddings | **inferred** $0.10/GB-month of growth |
| ACU while Quantic is used | **inferred** 0.5 ACU floor while **available** (~$43/month if left running 24/7) |
| Auto-pause to 0 ACU | **not configured**; would cut idle ACU to ~$0 after idle timeout; still storage |
| AgentCore / Bedrock | not in Café stack; billed only if those are deployed later |
| Connectivity add-ons (NAT, many interface endpoints, extra EC2) | see §5; this is the real incremental cost risk |

**Likely waste to avoid:** deploying undeployed `QuanticHrAgentStack` (new VPC + NAT + second Aurora) **and** keeping Café Aurora. Also leaving stopped clusters to auto-start for a week.

---

## 3. Auto-pause feasibility

**Observed:** min ACU **0.5**, max **2**, no `SecondsUntilAutoPause`. That is “always at least 0.5 ACU when **available**,” plus the **stop** API (7-day limit).

**Inferred from AWS docs:** Aurora PostgreSQL **≥13.15 / 14.12 / 15.7 / 16.3** supports Serverless v2 scale-to-0. **17.4 is newer** and should qualify; **unverified in-account** because we did not call `modify-db-cluster`.

To enable later (proposal only):

```text
MinCapacity=0, MaxCapacity=2, SecondsUntilAutoPause=300..86400
```

Limitations (**inferred** from AWS auto-pause docs, not applied):

- Instances pause only with **no user connections**. Long-lived MCP/agent pools would **prevent** pause.
- Resume can take **up to ~15 seconds**; first request after idle will be slow.
- Some Aurora features are incompatible with auto-pause (cluster stays at min > 0); list not verified against this cluster.
- **Stop** and **auto-pause** are different: stop does not auto-resume on connect and auto-starts after 7 days. Auto-pause stays paused indefinitely aside from storage/backup charges and resumes on connect.
- Cluster is **stopped today**; auto-pause only applies once the cluster is **available**. Enabling it is a **modify**.

---

## 4. Snapshot / retention plan (not executed)

| Kind | Today | Notes |
|---|---|---|
| Automated | Café snapshot `rds:cafefausseapplicationstac-databaseaurorapostgres65-zchaodeehzxe-2026-10-18-06-33` | **observed**; 1-day retention; PITR window **observed** earliest 2026-10-17T06:34Z latest 2026-10-18T10:56Z (before the 11:02Z stop) |
| Manual / final | **none** | **observed** |
| Restore | `restore-db-cluster-from-snapshot` into a **new** cluster, then create instance; or PITR `restore-db-cluster-to-point-in-time` | inferred; would create billable resources |

**AWS docs (inferred):** a **manual** DB cluster snapshot requires the cluster to be **`available`**. A stopped cluster therefore likely **must be started** to take the intended “final Café” snapshot. Automated snapshots already exist from when it was running on 18 Oct.

**Snapshot storage cost (inferred):** billed for backup/snapshot GB above the free allocation equal to the cluster volume. Café volume reports 1 GB, so a same-size manual snapshot is likely **pennies/month**, not zero. Snapshots do not expire until deleted.

**Do not snapshot in this step.**

---

## 5. Connectivity strategy

Café Aurora is **private-isolated**. Postgres is not on the internet (**observed** SG: only the SSM admin host). That must stay.

### Paths

1. **Admin / laptop (existing Café pattern):** start cluster + start `t4g.nano` + SSM port-forward to 5432. Drifted SSM interface endpoints mean this path may **fail until endpoints are repaired** (**unverified** without starting the host). Repair is a mutation and would add endpoint hourly cost.
2. **AgentCore `networkMode=VPC` in the Café VPC:** ENIs in isolated subnets have **no NAT and no live endpoints**. They cannot reach Bedrock, ECR, or CloudWatch Logs. **Observed** network cannot host AgentCore without adding NAT **or** a set of interface endpoints (ECR, S3, logs, Bedrock, STS). That is **not** cheaper than one NAT in a dedicated Quantic VPC if many endpoints are required.
3. **Render BFF on the public internet:** cannot open TCP 5432 to this cluster without a public DB (**reject**) or a tunnel/proxy/NAT path.
4. **Lowest-cost alternative to a new NAT (proposal):** keep **compute local or on Render**, keep **data local** until the HR model is frozen; when AWS SQL is required, **reuse Café Aurora** via SSM (after endpoint repair) rather than creating a second cluster. For a **graded public agent**, either (a) accept one NAT in a small Quantic compute VPC **peered** to Café (peering + SG rule; peering is free, NAT is not), or (b) research **RDS Data API** (`HttpEndpointEnabled` is **false** today) as an HTTPS control-plane path — **unverified** for PostgreSQL 17.4 Serverless v2 in `us-east-2`, and enabling it would be a Café-affecting modify.

IAM auth is already on. A future Quantic DB user (`rds-db:connect`) can be added **after** schema approval without sharing `cafe_fausse_admin`. Do not reuse Café application secrets.

**Group access:** IAM Identity Center + IAM DB auth + SG allowlists. No public Postgres.

---

## 6. CDK proposal only (do not implement)

Current undeployed `QuanticHrAgentStack` would create a **new** VPC `10.20.0.0/16`, NAT, Aurora `quantic_hr`, and Hello World runtime. That **duplicates** Café Aurora and adds ~$80/month if left up. Under a reuse decision it should **not** be deployed as-is.

Proposed later shape (no code change in this step):

1. Keep `CafeFausseApplicationStack` as the **owner** of the cluster, secret, isolated VPC, and admin host.
2. Quantic CDK (if any) **omits** new Aurora, NAT, and admin host.
3. Pass Café cluster ARN, SG id, subnet ids, and secret **name** as parameters; do not `fromLookup` in a way that invites CFN to adopt Café resources.
4. The only Café-touching change, if AgentCore or another SG must connect, is an **ingress rule on `sg-09f0dd96526f3085f`**. That **does** affect Café Fausse (wider 5432 allowlist). Prefer adding it via a **reviewed Café stack change** (or a tiny dedicated SG in the Café VPC) rather than silent drift.
5. Do not import AEA resources.
6. Continue local Postgres for CI (`docs/COST_FIRST_DELIVERY_STRATEGY.md` local spine) so November 15 work does not wait on this cluster.

**Café impact if reuse proceeds:** possible SG change, possible second database/role on the same cluster, possible auto-pause modify, possible start for snapshot. Any of those need an explicit checklist tick.

---

## 7. Data modeling deferred

Not selected and **not** migrated:

- Whether Quantic is a **new database** on the Café cluster vs schemas inside `cafe_fausse_db` (strongly prefer a **separate database** later so restaurant tables stay isolated).
- HR entities (employee, manager, location, PTO, tickets) and their keys.
- RAG tables (documents, chunks, embedding width, citation ids) and `vector` extension install.
- Access controls (IAM user vs password; grants; row-level policy).
- Retention/deletion of embeddings and mock PII.
- Whether Café restaurant data is ever joined (default **no**).

---

## Proposed reuse plan (no-change)

1. Continue **local** MCP/RAG/app work. Do not deploy `QuanticHrAgentStack`.
2. Finalize HR + RAG data model **offline**.
3. User approval gate (below).
4. Then, in order: optional start + **manual snapshot** of Café cluster; optional auto-pause-to-0; create database/role **only after model freeze**; SG/IAM for the chosen compute path; never public 5432.

---

## Approval checklist (later mutations)

Tick only with a written yes. None of these were done.

- [ ] Accept Café cluster reuse vs remaining on local Postgres until demo week.
- [ ] Accept that a **manual snapshot requires starting** the cluster (ACU charges until stopped or auto-paused).
- [ ] Choose compute path: SSM-only vs NAT vs interface endpoints vs Data API research.
- [ ] Approve any **security-group** change on Café DB SG.
- [ ] Approve `MinCapacity=0` auto-pause (Café cluster modify).
- [ ] Approve creating database/schema/roles **after** the HR model is written down.
- [ ] Confirm AEA cluster is out of scope (leave stopped or discuss deletion separately).
- [ ] Confirm undeployed Quantic CDK is retained but **not** deployed with a second Aurora/NAT.

**Stop.** Awaiting data-model review and explicit AWS mutation approval.
