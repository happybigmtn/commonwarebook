# commonware-chat

## Invitation-Only Conversation

---

## What is a Chat Room, Really?

You know, when most people think about a group chat, they imagine a window with text bubbling up. They think the hard part is moving the bytes from point A to point B. But that's not the hard part at all! Moving bytes is easy. The *real* trick, the profoundly difficult thing to get right, is figuring out who is actually in the room!

Think about it. If you and I don't agree on who is allowed in the room, are we even in the same room? We're not! So this example, `commonware-chat`, spends almost all of its energy on three things before it ever lets you type a single word:

1. **Identity:** Who are you?
2. **Membership:** Who is allowed in the room?
3. **Discovery:** How do the people allowed in the room actually find each other?

Conversation is just the easy part at the very end. The whole point of this example is to show you how to keep these ideas strictly separate. Otherwise, your private, secure room just collapses into a public walkie-talkie channel with some encryption slapped on top.

We use some beautiful, simple tools to do this:
- `commonware-cryptography::ed25519` gives everyone a mathematical, unforgeable identity.
- `commonware-p2p::authenticated::discovery` turns our "guest list" into a living, breathing network overlay.
- `commonware-runtime` keeps the engine ticking.
- `commonware-utils` gives us some handy data structures.
- `commonware_macros::select!` lets us listen to human typing and network traffic at the exact same time.

Keep this one question in your mind as we go through this: *What makes this room exactly the same room for every person invited to it?*

## 1. The Lesson Hidden in the Example

I want to be clear: `commonware-chat` is not just a terminal demo that squirts bytes across the internet. It's a lecture. It’s teaching you how to build a private conversation without jumbling up network addresses, identities, and the guest list.

This is a subtle thing, but it's tremendously important: A network address is just a path—it's a route, not a person! A network socket is a pipe, not a permission slip. Even if you encrypt the data, if you don't all share the exact same rule for who belongs in the group, the boundary of your room is totally undefined. 

That's why this chat is strictly invitation-only. It shows you how to build a room that *only exists* for the people who were invited, and how to stop the network transport layer from making any decisions about who belongs.

## 2. Identity and the Guest List

Let's look at the code. If you open up [`examples/chat/src/main.rs`](/home/r/coding/monorepo/examples/chat/src/main.rs), you'll see we start by parsing a `--me` argument. We turn this into an `ed25519::PrivateKey`, and from that, we derive a public key. That public key is *you*.

This is brilliant because it removes all the fuzziness! You aren't a nickname. You aren't an IP address that might change tomorrow when you take your laptop to a coffee shop. You are a cryptographic identity. You carry that identity everywhere—through discovery, logging, and sending messages—and it never has to be translated.

The list of friends follows the exact same logic. You pass in a `--friends` list, and the code turns it into a mathematical set: `Set<PublicKey>`. It even rejects duplicates using `TryCollect`. Now, you might think, "Oh, it's just cleaning up user input." No! It's much deeper than that. Duplicate peers would mean our guest list isn't a precise, mathematically clean statement of membership.

Then we hand this pristine set of friends to the discovery system:
```rust
oracle.track(0, recipients).await;
```
*That line right there is the boundary of the room.* It tells the discovery system exactly who we consider part of our active group.

And here is the kicker: every single participant *must* agree on this exact same set of friends. It’s not a suggestion. If the sets are different, sure, a few pairs of people might connect, but the room itself is no longer globally the same room. The network overlay can only build a shared space if everyone is playing by the exact same membership rule.

## 3. Wiring the Network: Discovery and Transport

Next, we look at where the room gets physical. It’s in `discovery::Config::local`. We pass in our local signer, a specific namespace `_COMMONWARE_EXAMPLES_CHAT`, our local socket address, and a list of "bootstrappers."

Notice the namespace! It's essentially the identity of the stream. It stops this chat room from getting accidentally mixed up with some other protocol that happens to be running on the same network. Changing that string isn't just renaming a variable; it fundamentally changes what stream you are talking to.

And what about the bootstrappers? They are *not* the membership list. Think of bootstrappers as the front door or the hallway leading to the room. The people allowed inside are still defined solely by your friend set. The bootstrappers are just the first places your computer checks to find where the party is happening.

Then, the network registers our chat channel with some strict rules:
```rust
let (chat_sender, chat_receiver) = network.register(
    handler::CHANNEL,
    Quota::per_second(NZU32!(128)),
    MAX_MESSAGE_BACKLOG,
);
```
I love this part. It’s telling the truth about reality. A live conversation is bounded; it's not an infinite, magical pipe that can absorb data forever. We limit it!

Look at the clean boundary we get out of this:
- `chat_sender` is the only way your user interface talks to the network.
- `chat_receiver` is the only way your user interface hears from the network.

There are no raw, messy sockets bleeding into your application logic. The room only speaks through its dedicated channel.

## 4. The Live Loop

Now we move to [`examples/chat/src/handler.rs`](/home/r/coding/monorepo/examples/chat/src/handler.rs). This is where the setup ends and the engine starts running.

We use the `select!` macro. Why? Because we have to balance the human typing on the keyboard with the messages arriving from the network. These two things are completely independent. A human doesn't wait for a packet to arrive before pressing a key, and network packets don't politely wait for you to finish typing. They happen concurrently, and neither one should block the other!

When you hit 'Enter', your text gets sent to `Recipients::All`. This isn't just a convenient helper function. It's making a profound statement: once someone is verified and inside the room, any message you send is addressed to the room as a whole.

And watch what happens with the return value of `send`. If it returns an empty set, it means nobody got it, and we warn the user! Sending a message into the void is *not* the same thing as a delivered message. The UI tells you the truth about the physics of the network.

Incoming messages are handled with the same beautiful simplicity. The receiver gives us bytes, we turn them into text, and we print them on the screen. Notice what *isn't* happening: the transport layer isn't interpreting the meaning of the data. It just carries the mail.

Even our logs and metrics are brought inside this interface. [`examples/chat/src/logger.rs`](/home/r/coding/monorepo/examples/chat/src/logger.rs) pipes our tracing data straight into the terminal. And `context.encode()` grabs the metrics so we can display them right there in the UI. Observability isn't some bolted-on extra; it's part of the explanation of the system itself.

## 5. What to Look For When You Run It

The best way to understand this is to run it and watch what it tells you about the room.

- Check the metrics panel! If `p2p_connections` is less than `count(friends) - 1` (since you don't connect to yourself), somebody hasn't made it to the party yet.
- If a friend is offline when you hit Enter, the `authenticated::discovery` system simply drops the message. It doesn't lie to you and pretend it was delivered.
- If your friend lists aren't perfectly synchronized across everyone, you'll see a fractured room. Some people will connect, but the whole group will never fully form.
- If you can type in the box, but nothing shows up in the message pane, it's not a broken terminal. You likely have a connection issue, a mismatched guest list, or an empty recipient set.
- If the system gets overwhelmed, that bounded channel we talked about will push back, making the pressure visible instead of silently eating up all your memory.

This example is ruthlessly, intentionally live-only. We don't save offline messages. We don't store a durable chat history. We don't try to play mediator and fix disagreements about who is in the group after the fact. Those aren't missing features; they are strict boundaries that keep the model pure.

## 6. How to Study the Code

If you want to really get this, here is how you should read the source code:

1. Start in [`examples/chat/src/main.rs`](/home/r/coding/monorepo/examples/chat/src/main.rs). This is where everything is glued together. Watch how identity, the guest list, and discovery merge to form a single room.
2. Next, read [`examples/chat/src/handler.rs`](/home/r/coding/monorepo/examples/chat/src/handler.rs). Watch the live engine. See how `select!` elegantly juggles the unpredictable human and the unpredictable network.
3. Then check out [`examples/chat/src/logger.rs`](/home/r/coding/monorepo/examples/chat/src/logger.rs) to see how we make the system's inner thoughts visible.
4. *Only after you understand those three* should you go read the p2p discovery documentation. If you do it in this order, you'll see discovery not as a confusing network API, but as a mathematically pure membership rule.

Read it this way, and you'll see exactly how a private, secure conversation is built from the ground up!