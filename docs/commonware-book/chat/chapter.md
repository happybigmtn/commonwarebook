# commonware-chat

## Invitation-Only Conversation

---

## The Problem Beneath Chat

A group chat looks like a message stream, but the hard part is membership.
If peers do not agree on who is in the room, they are not sharing one room.
The example therefore spends most of its effort on identity, discovery, and
authorized membership before it ever gets to the text box.

That is the right order. Identity says who a participant is. Membership says
who may join. Discovery says how the invited peers find one another.
Conversation is the last step, not the first. The example is really about
keeping those responsibilities separate so a private room does not collapse
into a public socket with encryption on top.

The code uses familiar primitives:

- `commonware-cryptography::ed25519` gives each peer a stable identity.
- `commonware-p2p::authenticated::discovery` turns membership into reachable
  overlay state.
- `commonware-runtime` keeps the event loop moving.
- `commonware-utils` provides the small collection helpers the example needs.
- `commonware_macros::select!` lets human input and network input run together.

The chapter keeps one question in view the whole time: what makes this room
the same room for every invited peer?

## 1. What the Example Is Actually Teaching

`commonware-chat` is not a terminal demo that happens to send bytes.
It is a lecture on how to build a private conversation without mixing up
addresses, badges, guest lists, and transport paths.

The warning is subtle but important. A network address is a route, not a
person. A socket is a path, not permission. An encrypted payload can hide the
contents of a message while still leaving the group boundary vague. If the
membership rule is not shared, the room itself is undefined.

That is why the example is intentionally invitation-only. It teaches how to
make a room that only exists for peers that were admitted, and how to keep the
transport layer from deciding who belongs.

## 2. Identity and Membership

[`examples/chat/src/main.rs`](/home/r/coding/monorepo/examples/chat/src/main.rs)
begins by parsing `--me` into an `ed25519::PrivateKey`, then deriving the
public key that names the local peer.

That choice removes ambiguity. The local participant is no longer a nickname
or a host address that can drift. It is a cryptographic identity that can be
carried through discovery, logging, and message handling without translation.

The friend list follows the same rule. The example turns `--friends` into a
canonical `Set<PublicKey>` and rejects duplicates with `TryCollect`. That is
not cleanup for its own sake. Duplicate peers mean the guest list is not a
clean statement of membership yet.

Then the example gives that set to discovery with `oracle.track(0, recipients)`.
That line is the membership boundary. It tells discovery which peers should be
treated as part of the same active room.

The requirement that every participant agree on the same friend set is not a
nice-to-have. If the sets diverge, some pairs may still connect, but the room
is no longer globally the same room. The discovery overlay can only describe a
shared membership rule if every peer is using the same rule.

## 3. Discovery and Transport Wiring

`discovery::Config::local` is where the room becomes concrete.
The example passes the local signer, the namespace
`_COMMONWARE_EXAMPLES_CHAT`, the local socket address, and the bootstrapper
list.

The namespace matters. It is the stream identity, and it prevents this chat
room from being confused with any other protocol that happens to reuse the
same transport. Changing it is not a cosmetic refactor. It changes the stream
identity.

The bootstrapper list is not the membership list. It is only the hallway into
the room. The invited peers still come from the friend set, while the
bootstrappers are just the first places discovery can look.

The network then registers the chat channel with a quota and a backlog:
`Quota::per_second(NZU32!(128))` and `MAX_MESSAGE_BACKLOG`.
That is the example telling the truth about pressure. A live conversation is
bounded. It is not an infinite pipe.

The resulting boundary is clean:

- `chat_sender` is how the UI enters the network.
- `chat_receiver` is how the UI hears from the network.

No raw sockets leak into the application layer. The room speaks through its
own channel.

## 4. The Live Loop

[`examples/chat/src/handler.rs`](/home/r/coding/monorepo/examples/chat/src/handler.rs)
is where the example stops being a setup story and becomes a live system.

`select!` balances keyboard events against network receives. That matters
because the two streams are independent. Human intent and peer traffic do not
arrive in lockstep, and neither should block the other.

When the user presses Enter, the current line is sent to `Recipients::All`.
That is not just a convenience API. It is the example saying that once a peer
is inside the room, the message is addressed to the room.

The return value from `send` is part of the lesson. If the returned set is
empty, the example warns the user. A message with no recipients is not the
same thing as a delivered message, and the UI makes that distinction visible.

Incoming messages are handled just as plainly. The receiver yields bytes, the
UI turns them into text, and the message appears in the pane. The transport
layer does not get to narrate meaning. It only carries data for the room.

Logs and metrics stay inside the interface too. `examples/chat/src/logger.rs`
feeds tracing into the terminal, and `context.encode()` makes the metrics pane
part of the explanation rather than a separate debugging tool.

## 5. What to Watch in Real Runs

The most useful chat runs are the ones that tell you something about the room.

- If `p2p_connections` is lower than `count(friends) - 1`, someone is not
  connected yet.
- If a friend is offline when you send, `authenticated::discovery` drops the
  message instead of pretending delivery happened.
- If the friend set is not synchronized, discovery may work for a subset of
  peers while the full room never forms.
- If the input pane keeps accepting text but nothing appears in the message
  pane, the problem is likely connection state, membership, or an empty
  recipient set, not the terminal.
- If the queue fills, the bounded channel makes that pressure visible instead
  of silently absorbing it.

The example is deliberately live-only. It does not store offline messages, it
does not create durable history, and it does not try to repair disagreement
about membership after the fact. Those are boundaries, not omissions.

## 6. How to Read the Source

1. Start with [`examples/chat/src/main.rs`](/home/r/coding/monorepo/examples/chat/src/main.rs).
   This is the composition root. It shows how identity, membership, and
   discovery become one room.
2. Move to [`examples/chat/src/handler.rs`](/home/r/coding/monorepo/examples/chat/src/handler.rs).
   This is the live loop. Watch how `select!` keeps human input and network
   input in the same control path.
3. Finish with [`examples/chat/src/logger.rs`](/home/r/coding/monorepo/examples/chat/src/logger.rs).
   This is observability as part of the room, not a sidecar service.
4. Only after those files should you revisit the p2p discovery docs. At that
   point discovery reads like a membership rule instead of a helper API.

Read in that order, the example stays focused on how a private conversation
is assembled from distinct responsibilities.
