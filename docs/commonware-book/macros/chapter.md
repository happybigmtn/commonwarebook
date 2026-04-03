# commonware-macros: The Language of the System

## The Problem With Boilerplate

You know, when you look at a lot of protocol code, you start noticing something funny. It keeps saying the same things over and over again!

- "Wait for whichever future is ready first."
- "Keep looping until the system tells us to shut down."
- "Hide this feature if we're not at the right stability level."
- "Run this test, but make sure it captures all our logs."

Now, the easy thing to do—the naive thing—is just to copy and paste those little rituals everywhere. It's just a little boilerplate, right? What's the harm?

Well, here's the problem: if you do that enough times, the system starts speaking in dialects. One loop prioritizes shutdown differently than another. One test names its groups one way, another does it backwards. Before you know it, the code still *compiles*, but the shared meaning has completely splintered. You have to relearn how a simple loop works every time you open a new file!

That's what `commonware-macros` is all about. It's not about being clever with syntax or showing off what procedural macros can do. It's about taking these repeated, fundamental protocol shapes and turning them into a shared language. It's a way to keep the grammar of our system from drifting apart.

---

## How to Think About Macros

I like to think of this crate as a tiny, highly-specialized compiler front-end. 

Instead of writing all the tedious, repetitive plumbing yourself, you write the *intent* using syntax that feels natural. The macro takes that syntax, breaks it down, and stamps out the exact, explicit Rust code that bakes in our system's rules. It’s not "doing work" in the background—it’s just translating a small protocol grammar into explicit, predictable code.

There are three main ways this translation happens:
1. **Control flow:** `select!` and `select_loop!` handle waiting and prioritization.
2. **Visibility:** The stability macros (`#[stability]`, `stability_scope!`) control what code is visible at compile-time.
3. **Tests:** The test macros make sure all our tests run with the same logging and naming rules.

Let's look at how these pieces actually work under the hood.

---

## 1. Controlling the Flow: `select!` and `select_loop!`

### Making Priority Visible with `select!`

In a protocol, you spend a lot of time waiting. A message comes in, a timer goes off, a connection drops. The real question isn't "how do I wait?" The real question is, "If two things happen at the exact same time, which one wins?"

`select!` answers this by generating a biased `tokio::select!` block. 

```rust
commonware_macros::select! {
    _ = &mut shutdown => { ... } // This will ALWAYS be checked first!
    msg = rx.recv() => { ... }
}
```

What does "biased" mean? It simply means the order in which you write the code *is* the priority! An earlier branch isn't just earlier on the page; it's earlier in the scheduling policy. If shutdown should win before anything else, you put it at the top. The macro makes that choice visible and undeniable, rather than hiding it in some helper function.

### The Actor Lifecycle: `select_loop!`

Now, `select_loop!` is where things get really interesting. It takes that simple idea of prioritization and builds an entire lifecycle around it.

Instead of hand-rolling a `loop`, setting up a shutdown future, and writing a `select!` every single time, you write this little mini-language:

```rust
commonware_macros::select_loop! {
    context,
    on_start => { 
        // We prepare our state here
        let start_time = std::time::Instant::now(); 
    },
    on_stopped => { 
        // What to do when the music stops
        println!("Shutting down...");
        drop(shutdown);
    },
    Some(msg) = rx.recv() else break => {
        // Handle the message
    },
    on_end => {
        // This runs after a successful iteration
        println!("That loop took {:?}", start_time.elapsed());
    },
}
```

The macro takes this and expands it into something beautiful and explicit. It creates a `let mut shutdown = context.stopped();` binding right up front. Then it starts a `loop`. It runs your `on_start` code, drops into a biased `select!` (where `shutdown` is always checked first), and finishes with `on_end`. 

Notice that `else break`? The macro is smart! If you give it a pattern that might fail (like `Some(msg)` when a channel closes and returns `None`), it *forces* you to say what happens if it fails. It uses Rust's `let else` syntax to safely unwrap the value or execute your fallback, preventing confusing runtime bugs.

It's not magic. It's just generating the exact, robust actor lifecycle you *should* be writing, every single time.

---

## 2. The Stability Fences

When you are building a big system, you don't want every piece of code available to everyone all at once. You have things that are experimental (ALPHA), things getting solid (BETA), and things that are rock solid (EPSILON).

You might see an annotation like this:

```rust
#[stability(BETA)]
pub struct StableApi {}
```

What is this actually doing? Well, the macro looks at `BETA` (which is level 1) and generates a ladder of `#[cfg]` attributes. It basically says, "Include this code *unless* the compiler is told we are building for GAMMA, DELTA, or EPSILON." 

It builds an *exclusion ladder*.

Even better, we have `stability_scope!`. Instead of making every single item in a file its own little snowflake with a dozen `#[cfg]` tags, you wrap the whole block! 

```rust
stability_scope!(BETA {
    pub mod stable_module;
    pub use crate::stable_module::Item;
});
```

The macro simply runs through and stamps the exact same visibility rule onto every item inside the block. It keeps the policy local and easy to read, but makes sure the items don't accidentally drift apart in how they are compiled.

---

## 3. Standardizing the Tests

Finally, let's talk about testing. If you don't have consistent observability in your tests, debugging becomes a scavenger hunt in the dark!

The test macros act like little shims that wrap your test functions:

- `#[test_async]` strips the `async` keyword and wraps your code in `futures::executor::block_on`. Simple, clean, and keeps async tests looking like normal tests.
- `#[test_traced("INFO")]` sets up a tracing subscriber with the exact log level you want, just for that test's scope.
- `#[test_group("my_group")]` is my favorite because it's so strict. It takes your test name, say `test_behavior`, validates "my_group" against a configuration file (`nextest.toml`), and literally renames the function to `test_behavior_my_group_`. It turns a convention into a *build-time contract*. If you typo the group name, it doesn't compile!

---

## The Takeaway

When you are reading or writing code in Commonware, remember what these macros are here for. They absorb the pressure of boilerplate drift. They give us a shared vocabulary for cancellation, priority, stability, and testing.

They don't magically make the logic of your protocol correct. But by stripping away the noise and the repetitive ceremonies, they make it much, much easier for you to see the logic that *actually* matters.
