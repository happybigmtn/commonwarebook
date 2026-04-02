# commonware-deployer

## Operational Compilation for Repeatable Cloud Topology

---

## Background

Deployment is really a compiler problem in disguise. The input is not a person
clicking through a console. The input is intent: which binaries to run, in what
regions, with what network boundaries, and with what monitoring. The output is
a concrete system made of cloud resources, startup scripts, cached artifacts,
and records that make later operations safe.

The broad vocabulary is worth making explicit:

- **Topology** is the graph of machines, networks, and trust boundaries.
- **Control plane** is the part that manages the system.
- **Data plane** is the part that does the work.
- **Immutable artifact** means a binary or config blob identified by content,
  not by a mutable local path.
- **Drift** is the gap between the intended system and the actual system over
  time.
- **Observability** is the ability to see what the system is doing after it is
  launched.

The naive way to deploy software is with ad hoc shell commands and console
clicks. That may work once, but it does not scale to repeated launches,
recoveries, or clean teardowns. The next naive step is to wrap the same manual
steps in a script. That is better, but scripts still tend to accumulate hidden
state and unspoken assumptions about what already exists.

The real tradeoff is between flexibility and repeatability. A more explicit
deployment pipeline asks for more structure up front: names, regions, recorded
metadata, and content-addressed artifacts. In return, it gives you something
much more valuable than convenience. It gives you a deployment that can be
reconstructed, inspected, updated, and destroyed without guessing which parts
were created the last time.

That is why the chapter should be read as operational compilation rather than
machine provisioning. The goal is not to launch "some instances." The goal is
to lower one description of a system into the actual relationships that make
that system operate.

---

## 1. What Problem Does This Solve?

On a laptop, deployment looks simpler than it is because the laptop has
already collapsed the hard parts. It gives you one machine, one network, one
user, one clock, and one place to inspect. AWS does the opposite. It makes the
hard parts visible.

The same binary now depends on region availability, instance architecture,
subnet layout, private reachability, operator ingress, telemetry placement, and
a cleanup path that can still find what was created after the fact. If you do
that by hand, you do not have a deployment system. You have a memory exercise
with cloud APIs.

`commonware-deployer` exists to make that work repeatable. It takes a
declarative config and lowers it into a cloud topology plus the operational
commands that keep that topology useful. The crate owns the parts that are
usually improvised:

- topology creation,
- artifact distribution,
- telemetry wiring,
- update and cleanup mechanics,
- and the local record that makes later commands safe.

That is the real problem here. Not "how do I launch an EC2 instance?" The
deeper question is:

> How do I compile a config into a deployment I can stand up again, update,
> observe, and destroy without guessing?

---

## 2. Mental Model

Read the crate like a lecture on operational compilation.

The YAML config is the source language. The crate parses it, checks that it is
coherent, lowers it into regions, networks, security groups, artifacts, and
monitoring endpoints, and then emits the commands that operate on that emitted
system. The compiler analogy matters because the input is intent, not a human
runbook, and the output is a repeatable topology rather than a pile of one-off
instances.

Two stored pieces of state keep the contract grounded: S3 caches deployment
artifacts, and `~/.commonware_deployer/{tag}` records enough information to
make later commands safe. The monitoring stack is part of the runtime, not an
afterthought, because the deployment is only useful if it can be observed and
managed after creation.

---

## 3. The Core Ideas

The public vocabulary in `deployer/src/aws/mod.rs` exists to keep the emitted
topology honest. `Config` carries deployment intent, `MonitoringConfig` defines
the observability plane, `InstanceConfig` describes each binary host,
`PortConfig` describes ingress, `Metadata` records what was created, and
`Architecture` keeps AMI selection and tool downloads aligned with the instance
type.

The real invariants are simpler to state:

### One tag names one build

Every deployment is keyed by a `tag`, and that tag threads through the local
metadata directory, the S3 artifact namespace, and the AWS resource tags that
let `destroy` find the right objects later.

### One region anchors the control plane

Monitoring lives in `us-east-1`. That gives the deployment one place to gather
logs, metrics, traces, and profiles from every binary region, and it makes the
monitoring VPC the control plane rather than another replica.

### Topology carries trust boundaries

The crate keeps the monitoring security group separate from the binary security
groups so operator access and telemetry traffic remain distinct. The deployment
is not just running. It is shaped.

### Artifacts are content-addressed

The crate hashes binaries and config files, stores each unique object once in
S3, and hands instances pre-signed URLs for the exact content they need. That
turns deployment into a small build system with an artifact cache.

### Operational commands are part of the output

`create`, `update`, `destroy`, `profile`, `authorize`, `list`, and `clean`
all operate on the same recorded state. That is why the command set belongs in
the chapter: the topology is only useful if it can be observed, updated, and
removed after the initial build.

---

## 4. How The System Moves

The main pipeline is `aws create`, and it reads like a sequence of compiler
passes.

### 4.1 Parse and validate

`create` loads the YAML config, checks for duplicate instance names, rejects an
instance named `monitoring`, and verifies that every required region is
enabled. It also checks that the deployment directory does not already exist.

That is the front end doing its job. The crate refuses to build an invalid
program.

### 4.2 Write the record early

The crate then generates an SSH key pair and writes deployment metadata before
it touches remote resources. That order is deliberate. If the rest of the
pipeline fails, the local record is already there, which means `destroy --tag`
can still find the deployment and clean it up.

This is the deployment equivalent of writing an object file before linking.

### 4.3 Choose architecture and toolchain

The crate detects the architecture for each instance type, then chooses the
right AMIs and tool downloads. That keeps ARM64 and x86_64 deployments on the
same code path without pretending they are interchangeable.

It also prepares the shared tools used by the monitoring stack: Prometheus,
Grafana, Loki, Pyroscope, Tempo, Node Exporter, and the small set of system
packages those tools need on Ubuntu 24.04.

### 4.4 Lower the config into AWS topology

The resource graph is built region by region:

- a VPC per region,
- one subnet per available zone that can support the requested instance types,
- an internet gateway and route table,
- security groups for monitoring and binary nodes,
- and VPC peering between the monitoring region and each binary region.

That is the emitted topology. The deployment is no longer a file. It is a
graph of networks and trust boundaries.

### 4.5 Launch the runtime

After the topology exists, the crate launches the monitoring instance and the
binary instances. It waits for them to become reachable, then installs and
starts the services over SSH.

The monitoring node gets the full observability stack. The binary nodes get the
binary itself, Promtail, Node Exporter, and optional Pyroscope agent plumbing.
The crate then adds the monitoring IP to the binary security groups so
Prometheus can scrape metrics without opening the cluster to everyone.

### 4.6 Emit the generated files

The crate generates the deployment-specific files that glue the system
together:

- `hosts.yaml` for the private and public mapping,
- Prometheus scrape config,
- per-instance Promtail config,
- per-instance Pyroscope agent scripts,
- Grafana datasources and dashboard plumbing,
- and the systemd service content needed to boot the services consistently.

The files are not the end goal. They are the emitted instructions that let the
remote machines converge on the intended shape.

### 4.7 Seal the build

Finally, the crate writes a `created` marker in the deployment directory. That
marker is the line between "attempted" and "operational."

The rest of the command set depends on that line:

- `update` refuses to run if the deployment was never completed,
- `destroy` refuses to run twice,
- `profile` requires a live deployment and a known host,
- and `list` uses the stored metadata to show what is still active.

---

## 5. What Pressure It Is Designed To Absorb

The first pressure is fan-out. One deployment may span many regions and many
instances. The crate uses concurrency where it is safe: creating resources,
uploading artifacts, and configuring hosts happen in parallel when they do not
depend on each other. The `--concurrency` flag exists because SSH and remote
setup have practical limits, not because the topology is conceptually
sequential.

The second pressure is deduplication. The same binary or config can appear on
multiple instances. The S3 layer hashes content and uploads unique values once.
That saves bandwidth, reduces cache churn, and makes updates cheaper.

The third pressure is eventual consistency and retries. The deployer talks to
AWS, S3, SSH, and SCP. All of those can fail in ways that are temporary. The
helper layer retries downloads and SSH actions, polls for service state, and
gives the deployment time to settle before it moves on.

The fourth pressure is repeatability. The local metadata directory keeps enough
state to make later commands deterministic. The deployment is not rediscovered
by guesswork. It is read from the record the compiler wrote earlier.

The fifth pressure is observability. The deployment is not considered finished
until it includes a telemetry pipeline. Metrics, logs, traces, and profiles are
part of the outcome. That is why the crate treats Prometheus, Loki, Tempo,
Pyroscope, and Grafana as core runtime pieces rather than optional extras.

---

## 6. Failure Modes and Limits

`commonware-deployer` does not remove operational risk. It reduces the places
where humans have to improvise.

It still depends on:

- AWS credentials with the right permissions,
- enabled regions,
- reachable Ubuntu AMIs,
- a public IP that can be authorized into the security groups,
- SSH and SCP access to the instances,
- and local binaries that are suitable for deployment or symbolication.

It also has hard limits:

- it is AWS-specific,
- it is EC2/VPC-specific,
- the monitoring region is fixed,
- the shared S3 cache is account-wide by design,
- and the crate is not a background reconciler that constantly repairs drift.

That last point matters. The deployer is not an always-on controller. It is an
explicit operator tool. If the topology changes outside the tool, the tool does
not pretend nothing happened.

The destroy path is similarly honest. It tries to clean up in dependency order
and uses persisted metadata when the original config is unavailable, but it is
still bounded by AWS state and by the resources that actually exist.

So the right mental model is not magic infrastructure. It is a compiler with
careful teardown and enough memory to keep its own promises.

---

## 7. How to Read the Source

Start with `deployer/src/main.rs` to see the operator contract, then read
`deployer/src/aws/mod.rs` for the deployment vocabulary and
`deployer/src/aws/create.rs` for the lowering pipeline. After that, read
`deployer/src/aws/s3.rs`, `deployer/src/aws/ec2.rs`, and
`deployer/src/aws/services.rs` as the back end that turns intent into cached
artifacts, resources, and runtime services. Finish with the operational
commands so the create/update/destroy cycle stays tied to the recorded state
rather than to memory.

---

## 8. Glossary and Further Reading

- **Deployment tag**: the unique name that ties together local state, S3
  artifacts, and AWS resource tags.
- **Pre-signed URL**: a temporary link that lets a remote instance download an
  object from S3 without sharing credentials.
- **VPC peering**: the private connection between the monitoring VPC and each
  binary VPC.
- **Monitoring plane**: the long-lived instance that runs Prometheus, Loki,
  Tempo, Pyroscope, and Grafana.
- **Artifact cache**: the shared S3 bucket that stores reusable tools and
  deployment-specific generated files.
- **Metadata marker files**: `created` and `destroyed`, which record the
  lifecycle state of a deployment.

The deeper lesson of the crate is simple. A deployment is not a machine. It is
a set of relationships that must be emitted, observed, and later unwound in a
predictable order. `commonware-deployer` is the code that keeps those
relationships honest.
