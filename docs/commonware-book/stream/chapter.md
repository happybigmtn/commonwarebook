# commonware-stream

## Turning a Noisy Pipe into a Private Conversation

---

## The Setup

Look, when you connect two computers together over a network, what you really have is just a pipe. You pour bytes in one end, and they slop out the other end. That’s it. It’s a miracle it works at all, but it doesn't give you any of the things you actually *want*. It doesn't tell you who is on the other end, it doesn't tell you if someone is listening, and it definitely doesn't tell you where one message stops and the next one begins. 

`commonware-stream` is the machinery that fixes this. It takes that raw, dumb byte pipe and builds a trusted, private conversation on top of it. It figures out who is talking, locks down the connection so nobody else can mess with it, wraps every message in a neat little package so you know exactly how big it is, and seals the whole thing up with cryptography.

If you just take some bytes and run them through an encryption function, you’re going to have a bad time. You’ll get messed up boundaries, people playing back your old messages, and total confusion about who is saying what. A secure transport isn't just "encrypting the bytes." It's about proving that *these* bytes belong to *this* conversation, exactly in *this* order.

### How to Read This

If you want to look at the code—and you should!—start by looking at the big picture in `stream/src/encrypted.rs`. Then, see how we remember the history of the conversation in `cryptography/src/handshake.rs`. After that, check out how we chop the stream into pieces in `stream/src/utils/codec.rs`.

### The Basic Rules of the Game
- The underlying pipe just moves bytes. It doesn't know what a "message" is.
- The two computers already know what application they're trying to talk to (the "namespace").
- We assume their clocks are running at roughly the same time.
- You can always hang up the phone before the conversation really starts.

---

## Background: Why a Pipe is Not a Conversation

Imagine you're standing at the end of a long, dark tube, and someone is shouting letters of the alphabet at you. That's a byte stream. There are no pauses, no punctuation, no "Hello, it's me, Alice." 

If you want to have a secure conversation, you need a few tools:
- **A byte stream** is the tube itself. A continuous, dumb flow.
- **A frame** is like putting a message in an envelope. It says, "This is exactly 50 bytes long."
- **A handshake** is how you figure out who is on the other end of the tube before you start saying anything important.
- **A transcript** is your memory of the handshake. "First he said this, then I said that."
- **A cipher** is the secret code you use to lock the envelopes.

You might think, "Why not just encrypt everything and be done with it?" Well, if you do that:
- The guy on the receiving end still doesn't know where one encrypted blob ends and the next begins!
- An attacker could record your encrypted bytes and play them back to you tomorrow, and your computer would think they were perfectly valid.
- You might accidentally use the same secret code for sending *and* receiving, which is a catastrophic cryptographic mistake.

So, we have to do a little more work. We have to frame the messages. We have to shake hands. We have to bind our secret keys to the *exact history* of how we met. That's what `commonware-stream` does.

---

## 1. What Problem Are We Actually Solving?

We want to make the transport layer disappear. We want you to be able to write an application where you just say "Send this message to Bob," and the system handles the rest. 

The crate takes your raw pipe and slaps a state machine on top of it. It doesn't ask the underlying pipe to be secure or even to understand messages. It takes total responsibility for turning the motion of bytes into the meaning of a conversation. Once the handshake is done, you stop worrying about bytes and start thinking in terms of secure, bounded messages.

---

## 2. The Mental Model: The Envelope Machine

Think of `commonware-stream` like an incredibly pedantic machine sitting at the end of your tube. 

Before it lets any real data through, it insists on a strict ritual. The Handshake. Both sides have to introduce themselves, sign their names, and agree on exactly what just happened (the transcript). They mix all this together to create a unique secret that belongs *only* to this specific moment in time.

Once the machine is satisfied, it switches modes. Now, it takes every piece of data you want to send, stamps the exact length on the front (the frame), seals it with an unforgeable tag, and encrypts it using a code that is *only* used for sending in your direction. The receiver's machine does the exact opposite. It never guesses. If a message is too long, or the tag is wrong, or the count is out of order, the machine doesn't try to fix it. It just destroys the connection. 

Secure transport is not a feature you add on; it's a series of proofs that have to be satisfied before a message is even allowed to exist.

---

## 3. The Core Ideas

Let's break down the magic tricks happening here.

### The Handshake is Where Trust is Born
If you look in `cryptography/src/handshake.rs`, you'll see three messages: `Syn`, `SynAck`, and `Ack`. 
- The dialer says "Hello, here's my temporary key." (`Syn`)
- The listener says "I hear you, here's mine, and here's proof I know the secret." (`SynAck`)
- The dialer says "Got it, I know the secret too." (`Ack`)

But they aren't just swapping keys. They are building a *transcript*. This transcript includes the time, who they think they are talking to, the keys, everything. This is the memory of the session.

### The Transcript is the Difference Between a Key and a Conversation
Why do we care about the transcript? Because a shared secret just means two people know a number. A *transcript-bound* secret means we know exactly *how* we agreed on that number. If someone tries to take a secret from today and use it in a conversation tomorrow, the machine will notice the history doesn't match, and it will reject it. The secret is locked inside a specific history.

### Framing Turns Soup Back Into Blocks
Over in `stream/src/utils/codec.rs`, we do the framing. Before we send an encrypted payload, we stick a small number on the front (a "varint") that says exactly how many bytes are coming. 

Why? Because if you don't bound the message, the receiver might just keep reading bytes forever until they run out of memory! Framing isn't just bookkeeping; it's a critical defense mechanism. The boundary is explicitly stated, and if it's too big, we drop it immediately.

### Two Directions, Two Ciphers
We use a different cipher for sending than we do for receiving. 
This is beautiful because it means we don't have to send a "nonce" (a number used once) over the wire with every message. We just use a counter! Message 1, Message 2, Message 3... As long as both sides keep track of the counter, they stay perfectly in sync. By giving each direction its own cipher and its own counter, we completely avoid the risk of accidentally using the same nonce twice.

### The Configuration is the Promise
The `Config` struct isn't just a list of settings. It's the rules of engagement.
- `namespace`: Stops someone from taking a message from your chat app and playing it back to your banking app.
- `max_message_size`: Stops someone from sending a 10-gigabyte message and blowing up your RAM.
- `handshake_timeout`: Says "If you don't finish shaking hands in 1 second, I'm hanging up."

---

## 4. The Machine in Motion

Let's look at the actual state machine in `stream/src/encrypted.rs`. The rule is simple: you don't get to send application data until all the proofs are done.

### The Four Steps on the Wire
Even though it's a "three-message" handshake, there are actually four things sent over the wire:
1. The dialer sends their static public key (so the listener knows who is calling).
2. The dialer sends the `Syn` message.
3. The listener sends the `SynAck`.
4. The dialer sends the `Ack`.

Why send the public key first? So the listener can run a `bouncer` function! Before doing any heavy cryptographic math, the listener can say, "Wait, I don't like this guy," and just hang up. It's cheap and efficient.

### The Listener's Clever Trick
Here's a neat detail: The listener actually figures out the shared secret and sets up the ciphers *before* it gets the final `Ack` from the dialer. But it doesn't give those ciphers to the application yet! It holds them in a `ListenState`, waiting for that final confirmation. Only when the dialer proves they also know the secret does the listener finally say, "Okay, we are `Established`."

---

## 5. Under the Hood of the Handshake

The real magic of the handshake is how the transcript works. 

### Committing to the Truth
When the dialer sends `Syn`, they are effectively saying: "At exactly 12:00 PM, I, Alice, wanted to talk to Bob, using this temporary key, for the purpose of playing Chess." They sign this statement.

When the listener (Bob) gets this, he checks the signature. Then he adds his own information: "At 12:01 PM, I, Bob, replied with my temporary key." Bob signs the whole thing.

Then they use X25519 (a type of Diffie-Hellman math) to combine their temporary keys into a shared secret. But they don't stop there! They shove that shared secret *into the transcript*. 

### The Confirmations
The `confirmation` values in the `SynAck` and `Ack` messages are basically a summary of this massive transcript. When Bob sends his confirmation to Alice, he's proving, "I saw the exact same sequence of events you did, and I got the exact same math result."

### Splitting the Stream
Once they agree, they use that final transcript to generate *two* different encryption keys using ChaCha20-Poly1305. One key for Alice-to-Bob, and one for Bob-to-Alice. 

If the handshake fails at any point, the code just spits out `HandshakeFailed`. We don't tell the attacker *why* it failed. We just slam the door.

---

## 6. The Art of the Frame

Once the handshake is done, we have to actually send data. The cipher path relies completely on the framing path being incredibly strict.

### The Wire Format
Every single message looks like this:
`[Length Prefix] [Encrypted Payload] [Authentication Tag]`

The length prefix tells you how many bytes are in the payload plus the tag. Notice that the length prefix itself is *not* encrypted. It's out there in the open. 

### The Fast Path for Sending
When you want to send a message, `Sender::send` doesn't mess around. It asks the memory pool for a single, contiguous chunk of memory big enough for the prefix, the payload, and the tag. It writes the prefix, copies your data in, encrypts the data *in place* right there in memory, sticks the tag on the end, and fires it down the pipe. One allocation. Boom.

### The Defensive Receiver
Receiving is trickier because bytes might trickle in slowly. `recv_length` tries a fast path first: it peeks at the bytes that have already arrived to see if the whole length prefix is there. If it is, great! 

But if it's not, it falls back to reading the pipe *one byte at a time*. This sounds slow, but the length prefix is tiny (a varint). By reading byte-by-byte, we absolutely guarantee that we never read past the end of the length prefix if it happens to be malformed.

If the length prefix says the message is larger than `max_message_size`, we drop the connection immediately. We check the size *before* we allocate memory.

### Decryption is Terminal
When we receive a frame, we copy it into a buffer and tell the cipher to decrypt it. The cipher increments its internal counter (the nonce) and does the math. 

If the math fails—if the tag is wrong, or the data was corrupted—the cipher returns an error. But here is the critical part: *the counter already incremented*. You can't rewind it. If a message is bad, that session is dead. Period. We don't try to guess what went wrong. We just kill the conversation.

---

## 7. Ciphers and Counters

We use ChaCha20-Poly1305. Each direction has a 32-byte key and a 96-bit counter.

The counter starts at zero and goes up by one for every message. 96 bits means you can send a billion messages a second for trillions of years without overflowing. 

Because we use this counter as the nonce, we get **ordered acceptance**. If Bob sends messages 1, 2, and 3, Alice's receiver expects exactly those nonces in that order. If the network duplicates message 1, Alice will reject it because she's already moved her counter to 2. If the network drops message 2, Alice will reject message 3 because she's expecting nonce 2, not 3.

We don't try to fix the network. We just guarantee that if a message is handed to the application, it arrived in the exact correct order. 

---

## 8. What We Prove, and What We Leak

You have to be honest about what your cryptography actually does.

### What We Guarantee
- **Authentication:** We know who is talking because of the signatures.
- **Forward Secrecy:** If someone steals your static key tomorrow, they can't decrypt the conversation you had today (thanks to the temporary X25519 keys).
- **Transcript Binding:** You can't take a secret from one session and use it in another.
- **Ordered Acceptance:** Messages arrive exactly as sent, or the connection dies.
- **Size Bounds:** We never allocate massive buffers for malicious giant messages.

### What an Attacker Can Still See (Leaks)
We protect the *content*, but we leak a lot of *metadata*:
- An observer can see the dialer's public key right at the start.
- They know you are shaking hands.
- They can see exactly how big every message is (we don't pad the messages to hide their size).
- They can see the timing of when you talk and when you are silent.
- They know who is talking to whom.

This crate isn't Tor. It's not trying to hide the fact that you are communicating. It is simply a rock-solid, ordered, private channel between two known peers.

---

## 9. Reading the Code

Here's how I'd approach the code if I were you:

1. Look at `stream/src/encrypted.rs`. Read `dial` and `listen`. You'll see the exact sequence of events: send public key, start handshake, send Syn, read SynAck, end handshake. It's the story of how the session is born.
2. Read `Sender` and `Receiver` in the same file to see the fast, in-place encryption loop.
3. Jump into `cryptography/src/handshake.rs`. Look at `dial_start` and `listen_start`. See how `transcript.commit()` is called over and over? That's the history being written down.
4. Finally, check out `stream/src/utils/codec.rs` to see the dirty work of varint encoding and the byte-by-byte defensive reading.

---

## 10. The Vocabulary

- **Transcript** - The permanent, unforgeable history of how the connection was established.
- **Frame** - A message neatly packaged with its exact length on the front.
- **Nonce counter** - A simple index (1, 2, 3...) that we use as the unique input for the encryption cipher, guaranteeing order.
- **Confirmation tag** - The final proof sent during the handshake that says, "I did the math on our transcript, and here is the result."
- **Bouncer** - The bouncer at the door of the listener. It gets to look at the dialer's ID and say "No thanks" before any expensive math happens.

Now go read the source! It's much simpler than you think once you see the pattern.
