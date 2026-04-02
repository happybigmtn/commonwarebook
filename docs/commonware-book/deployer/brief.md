# Chapter Brief: commonware-deployer

## 1. Module Purpose

`commonware-deployer` answers a systems question that usually gets hand-waved:
how do we turn a declarative deployment config into a repeatable AWS topology,
and then keep that topology operable after the first successful launch?

The naive approach is handwritten cloud choreography:

- create some EC2 instances,
- copy binaries over SSH,
- fix ingress by trial and error,
- and reconstruct the state later from memory and shell history.

That produces a deployment once. It does not produce a process.

This crate treats deployment as operational compilation. The config is the
source input. The emitted cloud topology is the artifact. S3 stores reusable
pieces. `~/.commonware_deployer/{tag}` stores the build record. The command
surface exists so an operator can create, update, inspect, profile, authorize,
clean, and destroy the same deployment without guessing.

The chapter should sound like a lecture about that pipeline:

- source config goes in,
- topology and runtime services come out,
- local metadata keeps the compiler honest,
- and later commands act on the same emitted system instead of inventing a new
  one.

---

## 2. Source Files That Matter Most

### `deployer/src/main.rs`
Why it matters: the operator front door. It shows how the command surface maps
to the emitted deployment lifecycle.

### `deployer/src/aws/mod.rs`
Why it matters: the vocabulary and invariants. It defines the config types,
deployment metadata, error types, architecture detection, and command
constants.

### `deployer/src/aws/create.rs`
Why it matters: the main lowering pipeline. This is where config becomes
regions, subnets, peering links, instances, telemetry services, and SSH
configuration.

### `deployer/src/aws/s3.rs`
Why it matters: the shared artifact cache. It handles bucket naming,
pre-signed URLs, digest-based deduplication, and upload/download helpers.

### `deployer/src/aws/ec2.rs`
Why it matters: the cloud primitive layer. It wraps EC2 operations for VPCs,
subnets, security groups, routing, image lookup, and instance launch logic.

### `deployer/src/aws/services.rs`
Why it matters: the emitted runtime payload. It contains tool versions, S3 key
schemes, service templates, and generated config content for monitoring and
binary hosts.

### `deployer/src/aws/update.rs`
Why it matters: the rolling update path. It shows how the crate replaces
artifacts in place without pretending the deployment is stateless.

### `deployer/src/aws/destroy.rs`
Why it matters: the inverse pipeline. It explains how the deployer unwinds the
topology and why persisted metadata matters.

### `deployer/src/aws/profile.rs`
Why it matters: the profiling workflow. It shows how a remote instance turns
into a local CPU profile with symbolication.

### `deployer/src/aws/authorize.rs`, `list.rs`, and `utils.rs`
Why they matter: they handle operational edges like ingress authorization,
deployment discovery, retries, SSH, and SCP.

---

## 3. Chapter Outline

1. Why laptop success is not deployment success
   - a local run hides topology, access, and observability work
   - manual cloud setup drifts immediately
   - the crate takes ownership of the repeatable parts

2. Mental model: operational compilation
   - config as source code
   - topology, telemetry, and workflows as generated output
   - S3 as cache and the metadata directory as the build record

3. Core ideas
   - the config and metadata types that define the contract
   - architecture detection and region-specific planning
   - shared artifacts, pre-signed URLs, and digest deduplication
   - the emitted monitoring plane and binary plane

4. How the system moves
   - parse and validate the config
   - persist local state before remote work starts
   - derive regions, architectures, and availability-zone support
   - create VPCs, subnets, peering, and security groups
   - launch monitoring and binary instances
   - emit services, configs, and telemetry wiring
   - mark completion so later commands can target the same topology

5. What pressure it is designed to absorb
   - multi-region concurrency
   - artifact reuse across deployments
   - eventual consistency and transient SSH failure
   - repeatable update, profile, and cleanup operations

6. Failure modes and limits
   - requires enabled AWS regions and the right IAM permissions
   - depends on SSH and a reachable public IP for operator actions
   - is not a live reconciler or drift manager
   - uses a fixed monitoring region and a shared account-level cache

7. How to read the source
   - start with `main.rs`
   - then read `aws/mod.rs` for the vocabulary
   - then read `create.rs` end to end
   - then read `s3.rs`, `ec2.rs`, and `services.rs`
   - finish with `update.rs`, `destroy.rs`, `profile.rs`, and `authorize.rs`

8. Glossary and further reading
   - deployment tag
   - pre-signed URL
   - VPC peering
   - monitoring plane
   - artifact cache
   - metadata marker files

---

## 4. System Concepts To Explain

- **Deployment as compilation.** The crate lowers declarative intent into
  cloud resources, cached artifacts, and operational steps.
- **Persistence as a build record.** The local directory under
  `~/.commonware_deployer/{tag}` is what keeps later commands aligned with the
  same build.
- **Shared artifacts as cache entries.** Observability tools and static service
  files should not be re-downloaded for every deployment.
- **Operational workflows as first-class outputs.** `update`, `destroy`,
  `authorize`, `list`, `clean`, and `profile` are part of the design, not
  extras.
- **Observability is part of the emitted topology.** Prometheus, Loki,
  Pyroscope, Tempo, and Grafana are not afterthoughts.

---

## 5. Interactive Visualizations To Build Later

1. **Compilation pipeline plate** - show config flowing through validate,
   lower, link, emit, and operate stages.
2. **Topology plate** - show monitoring VPC, binary VPCs, peering, routes, and
   security groups as one graph.
3. **Artifact cache plate** - show shared tools in S3, deployment-specific
   files, and pre-signed URL flow.
4. **Update plate** - show a rolling restart with S3 download, service stop,
   service start, and health polling.
5. **Destroy plate** - show the cleanup order and why metadata allows teardown
   even when the original config is gone.

---

## 6. Claims-To-Verify Checklist

- [ ] The chapter explains deployment as operational compilation.
- [ ] The monitoring stack is described as part of the emitted topology, not an
      afterthought.
- [ ] `create`, `update`, `destroy`, `authorize`, `list`, `clean`, and
      `profile` all appear in the chapter's mental model.
- [ ] The role of `~/.commonware_deployer/{tag}` is clear.
- [ ] The chapter distinguishes shared cache data from per-deployment data.
- [ ] The reader can locate the main control flow in `create.rs`.
