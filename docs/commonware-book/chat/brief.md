# Chapter Brief: commonware-chat

## 1. Module Purpose

`commonware-chat` is a case study in invitation-only conversation. The point
is not terminal UI, command-line flags, or even message passing. The point is
to show how identity, membership, and reachability compose into a room that
only invited people can enter.

The hard part of group chat is that it is really three problems at once:

- a cryptographic identity that cannot be forged,
- a shared guest list that defines who belongs,
- and a discovery layer that can find those invited peers on the network.

`commonware-chat` shows how those responsibilities fit together:

- **`commonware-cryptography::ed25519`** gives each participant a stable
  signing identity.
- **`commonware-p2p::authenticated::discovery`** turns the guest list into a
  reachable authenticated overlay.
- **`commonware-runtime`** provides the async execution model that keeps the
  room alive.
- **`commonware-utils`** supplies the small pieces that keep the example tidy:
  a canonical set of allowed keys, a mutex for shared logs, a bounded channel,
  and a few numeric helpers.
- **`commonware_macros::select!`** keeps the event loop readable when human
  input and network traffic compete for attention.

The chapter's core lesson is simple: the friend list is not decoration. It is
part of the protocol that defines the room.

---

## 2. Key Source Files

### `examples/chat/src/main.rs`
The composition root. It creates the signer, derives the authorized peer set,
configures discovery, registers the application channel, and starts the
runtime.

### `examples/chat/src/handler.rs`
The live conversation loop. It draws the terminal panes, reads keyboard input,
receives network messages, and sends chat messages to the authenticated peer
set.

### `examples/chat/src/logger.rs`
The log adapter. It converts JSON tracing output into a readable in-memory log
feed for the UI.

---

## 3. Chapter Outline

1. **Start with the real question** - a group chat is a room, not a text box.
2. **Mental model: an invitation-only room with cryptographic badges** - the
   public key is the badge, the friend list is the guest list, and the network
   only looks for invited peers.
3. **Identity and membership** - how `ed25519`, `Set<PublicKey>`, and
   `oracle.track(0, recipients)` establish who the room is for.
4. **Conversation as a separate problem** - how discovery, transport, and the
   chat channel carry the conversation once the room is defined.
5. **How the room moves** - from parsing friends to starting the runtime, from
   keypress to send, from receive to rendered message.
6. **What pressure it absorbs** - offline peers, bounded queues, partial
   connectivity, and the difference between connection and delivery.
7. **Failure modes and limits** - no store-and-forward, no membership
   coordination, no key management, and no durable history.
8. **How to read the source** - the shortest path through `main.rs`,
   `handler.rs`, and `logger.rs`.

---

## 4. System Concepts To Explain

- **Identity is not an address** - public keys name peers; bootstrap addresses
  only help find them.
- **The guest list is part of the protocol** - `oracle.track(0, recipients)` is
  the discovery boundary, not bookkeeping.
- **Discovery requires shared membership** - the room only stays coherent when
  every peer agrees on the same friend set.
- **Send results matter** - the example should surface who actually accepted a
  message and warn when the recipient set is empty.
- **The UI is an instrument panel** - logs, metrics, and messages expose the
  live state of the room.
- **Replay resistance comes from a namespace** - the application namespace is
  part of the stream identity.

---

## 5. Interactive Visualizations To Build Later

1. **Guest-list topology plate** - show the friend set as a shared graph and
   highlight how discovery only connects nodes on the same list.
2. **Identity vs address plate** - compare public key, bootstrap address, and
   authenticated peer connection so the reader sees what each one means.
3. **Message flow plate** - trace one typed message from input line to sender,
   over authenticated p2p, into the receiver, and back into the message pane.
4. **Pressure and visibility plate** - show logs, metrics, and message panes
   as three different views of the same live system.

---

## 6. Claims-To-Verify Checklist

- [ ] The chapter explains why the friend list is a protocol input, not a UI
      convenience.
- [ ] The chapter distinguishes identity, address, and authenticated
      connection clearly.
- [ ] `oracle.track(0, recipients)` is explained as the discovery boundary.
- [ ] The event loop is described as a composition of runtime, network, and UI
      concerns, not as a terminal tutorial.
- [ ] The failure modes emphasize missing delivery, not just blocked peers.
- [ ] The chapter stays conceptual and does not become a command-line manual.
