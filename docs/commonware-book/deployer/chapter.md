# commonware-deployer

## Operational Compilation for Repeatable Cloud Topology

---

## The Problem with Guessing

You know, when people first start putting software on the internet, they usually just open up a terminal and start typing commands. They click around in a web console, maybe run an SSH command, copy a file over. And it works! It's like building a little house out of playing cards. It stands up. 

But then a week later, they want to do it again. Or worse, something breaks, and they have to fix it. Suddenly, they realize they don't actually know *what* they did. Was it this security group or that one? Did I open port 9090? What region was that machine in again? It turns into a game of memory, and human memory is a terrible place to store your infrastructure.

Some people realize this and say, "Ah! I will write a script!" So they write a bash script. But scripts are sneaky. They assume things. They assume a file is already there, or that a network is already configured. They have hidden state.

The real problem here is that deploying a distributed system is not about just running "some instances." It's about lowering a description of your intent into actual, physical (well, virtual) relationships. It's a compiler problem!

Let's get the vocabulary straight, just so we are talking about the same things:
- **Topology:** This is just a fancy word for the map of your machines, networks, and who is allowed to talk to whom.
- **Control plane:** The part of the system that watches and manages the rest of the system.
- **Data plane:** The part of the system actually doing the real work you care about.
- **Immutable artifact:** A file—like a binary or config—identified by what's *inside* it (its hash), not by some path on a hard drive that might change.
- **Observability:** Figuring out what on earth your program is doing once it's actually running in the wild.

What `commonware-deployer` does is take away the guessing. It trades the quick-and-dirty convenience of clicking around for something much more powerful: repeatability. It takes your configuration—your *intent*—and compiles it into a cloud topology.

---

## 1. The Compiler Mental Model

I want you to read this crate like it's a lecture on compilers. 

In a normal compiler, you take C code, the compiler checks if it makes sense, and then it emits machine code. 

Here, the "source code" is a YAML configuration file. `commonware-deployer` parses it, checks that you aren't doing something silly (like naming an instance "monitoring" when that's reserved), and then lowers it into AWS regions, Virtual Private Clouds (VPCs), subnets, security groups, and instances. The "machine code" it emits is the actual working system, plus the operational commands needed to keep it running.

You see, a deployment isn't just the binaries running on a server. It's the monitoring stack, the S3 artifact cache, the SSH keys, the local metadata record... all of it. If you can't observe it, update it, and cleanly destroy it, you haven't really deployed it. You've just thrown it over the fence.

---

## 2. The Core Invariants (And The Code That Enforces Them)

If you look inside `deployer/src/aws/mod.rs`, you'll see the Rust data structures that keep this whole system honest. You have `Config` for your overall intent, `MonitoringConfig` for the observability plane, and `InstanceConfig` for the actual nodes doing the work. They use the `serde` crate to deserialize exactly what you wrote in your YAML file into strongly-typed Rust structs. But the code is just the implementation. The *ideas* are what matter. Here are the core invariants:

### One tag rules them all
Every deployment is keyed by a single `tag` (like a UUID). This tag is stamped onto the local metadata, the S3 artifact cache, and the AWS resource tags. Why? Because when you type `destroy`, the system needs to know exactly what to tear down without accidentally deleting your other projects. 

### The Control Plane lives in one place
All the monitoring—Prometheus, Grafana, Loki, Tempo, Pyroscope—lives on a single instance in `us-east-1`. This is your anchor. It gives you one single place to gather logs, metrics, and profiles from all your binary instances spread across the world. It's not just another replica; it's the control plane.

### Topology enforces trust
We don't just throw everything into one big network and hope for the best. The deployer creates separate security groups for the monitoring instance and the binary instances. It uses VPC peering to connect the monitoring VPC to the binary VPCs. The monitoring instance is allowed to reach in and scrape metrics (port `9090` for your binary, `9100` for system metrics), but operator access and telemetry traffic remain strictly shaped.

### Content-addressed caching
This is a beautiful trick. Instead of uploading the same Prometheus binary or your custom binary to every single instance over SSH, the deployer hashes the files. It uploads them once to a shared S3 bucket (`commonware-deployer-cache`). Then, it just hands the instances a pre-signed URL. "Here, go download this exact hash." It turns the deployment into a distributed build system. It saves bandwidth and makes everything incredibly fast.

---

## 3. How the Machine Works (The Passes)

Let's look at what happens when you run `aws create`. It moves exactly like a sequence of compiler passes:

### Pass 1: Parse and Validate
First, it reads your YAML. Are there duplicate names? Did you request regions that aren't enabled? It checks this upfront. A good compiler refuses to compile an invalid program.

### Pass 2: Write the Record Early
Before it even touches AWS, it generates an SSH key pair and writes the metadata to your local drive (`~/.commonware_deployer/{tag}/metadata.yaml`). This is crucial! If the internet cuts out halfway through creating the servers, you have a local record of what was *supposed* to happen. That means `aws destroy --tag` can still go in and clean up the mess. 

### Pass 3: Lowering to AWS Topology
Now it starts building the graph. Region by region, concurrently. It builds a VPC, finds the right availability zones, sets up subnets, internet gateways, and route tables. It creates the security groups. Then it wires up the VPC peering so the `us-east-1` monitoring node can talk privately to your nodes in Tokyo or London.

### Pass 4: Launch and Wire the Runtime
The topology is there, but it's empty. Now it launches the EC2 instances. Once they are reachable via SSH, it installs the services. The monitoring node gets the full observability stack. The binary nodes get your program, plus Promtail (for logs), Node Exporter (for system metrics), and maybe the Pyroscope agent (for continuous profiling).

### Pass 5: Seal the Build
Finally, it writes a simple `created` file locally. This is the line between "I am trying to build this" and "This is a working, operational deployment." 

Other commands rely on this seal. `update` won't run if it's not created. `destroy` won't run twice. 

---

## 4. Profiling: Seeing the Invisible

One of the most fascinating parts of this deployer is how it handles profiling. When your program is running, you want to know where it's spending its time. The deployer gives you two ways to look under the hood:

1. **Continuous Profiling:** If you set `profiling: true` in your config, it runs Pyroscope on the instances. It continuously gathers CPU profiles and sends them to the monitoring instance. You just open Grafana and look. But to do this, you have to deploy your binary with debug symbols and frame pointers built in.
2. **On-Demand Profiling (`aws profile`):** Suppose you didn't want to deploy a massive binary with debug symbols. You deployed a stripped binary. If something gets slow, you can run `aws profile --config ...`. The deployer SSHes into the specific instance, downloads a tool called `samply`, records a 30-second CPU profile, and pulls it back to your laptop. It then automatically opens the Firefox Profiler, matching the profile against your *local* unstripped binary to resolve the symbols! It's an incredibly elegant way to get deep visibility without paying the cost of symbols in production.

---

## 5. What it is NOT

I want to be very clear about its limits. `commonware-deployer` is not magic. It doesn't eliminate operational risk; it just reduces the number of places where humans have to make things up on the spot.

It is not an always-on reconciler like Kubernetes. If you go into the AWS console and manually delete a security group, the deployer won't automatically fix it. It is an explicit, command-driven tool. 

It is designed to absorb the pressure of fan-out (deploying to many regions at once via concurrency), deduplication (S3 caching), and repeatability (local metadata). 

---

## 6. Reading the Source

If you want to understand this for yourself, don't just take my word for it. Open the code!

- Start in `deployer/src/main.rs`. That's the front door. You'll see the commands: `create`, `update`, `destroy`, `clean`, `list`, `profile`.
- Look at `deployer/src/aws/mod.rs` to see the vocabulary—the `Config` and `Metadata` structures.
- Then, read `deployer/src/aws/create.rs`. That is the lowering pipeline, the main compilation pass.
- After that, poke around `deployer/src/aws/ec2.rs`, `deployer/src/aws/s3.rs`, and `deployer/src/aws/services.rs`. Those are the backend details—how it actually talks to AWS to build the topology and cache the artifacts.

Remember, a deployment is not just a machine running somewhere. It is a set of relationships—networks, trust boundaries, cached artifacts, and telemetry—that must be emitted, observed, and eventually unwound in a predictable way. `commonware-deployer` is just the compiler that keeps those relationships honest.