# BuddyParallel

BuddyParallel keeps the official Hardware Buddy device firmware and UI experience, but replaces the event source with a companion we control.

## Goals

- preserve the official firmware heartbeat-driven UI and approval flow
- support API-driven and hook-driven Claude workflows
- run a single Python-first companion as the source of truth
- support USB and BLE device transports without double-writing state

## Repository layout

- `firmware/` - upstream-derived device firmware and protocol reference
- `companion/` - Python companion app, ingest pipeline, transports, tray, dashboard, settings, updates
- `vscode-extension/` - local VS Code approval bridge and ambient activity monitor
- `docs/` - architecture, roadmap, and current status for handoff between agents

## Current status

BuddyParallel is well past bootstrap. The primary USB companion loop is working, the tray/dashboard/settings surfaces are real, the VS Code bridge is active, and additional notice sources now exist alongside Telegram. The main remaining work is packaging, release hygiene, and deciding which non-Telegram notice transport becomes the long-term default. See `docs/status.md` for the live summary, `docs/roadmap.md` for milestones, and `docs/release-hygiene.md` for the current packaging checklist.

## ASCII buddies

Renderable gallery: [`docs/ascii-buddies.md`](docs/ascii-buddies.md)

Current firmware roster, with one representative idle pose and a quick human-style voice note for each buddy:

<table>
  <tr>
    <td valign="top"><strong>axolotl</strong><pre>

}~(______)~{
}~( o  o )~{
  ( .--. )
  (_/  \_)
</pre><sub>"Let's keep this gentle and figure it out one blink at a time."</sub></td>
    <td valign="top"><strong>blob</strong><pre>

   .----.
  ( o  o )
  (      )
   `----`
</pre><sub>"I may look gooey, but I am emotionally available and surprisingly resilient."</sub></td>
    <td valign="top"><strong>cactus</strong><pre>

 n  ____  n
 | |o  o| |
 |_|    |_|
   |    |
</pre><sub>"I care a lot, I just come pre-equipped with boundaries."</sub></td>
  </tr>
  <tr>
    <td valign="top"><strong>capybara</strong><pre>

  n______n
 ( o    o )
 (   oo   )
  `------'
</pre><sub>"Nothing here is worth panicking over; we can float through it."</sub></td>
    <td valign="top"><strong>cat</strong><pre>

   /\_/\
  ( o   o )
  (  w   )
  (")_(")
</pre><sub>"I already knew the answer, but I will allow you to discover it."</sub></td>
    <td valign="top"><strong>chonk</strong><pre>

  /\____/\
 ( o    o )
 (   ..   )
  `------'
</pre><sub>"I believe in comfort, snacks, and shipping things that actually hold up."</sub></td>
  </tr>
  <tr>
    <td valign="top"><strong>dragon</strong><pre>

  /^\  /^\
 &lt;  o    o &gt;
 (   ww   )
  `-vvvv-'
</pre><sub>"Stand back, I can solve this elegantly or dramatically, possibly both."</sub></td>
    <td valign="top"><strong>duck</strong><pre>

    __
  &lt;(o )___
   (  ._&gt;
    `--'
</pre><sub>"I have no long-term plan, but I do have momentum."</sub></td>
    <td valign="top"><strong>ghost</strong><pre>

   .----.
  ( o    o )
  |   __   |
  ~`~``~`~
</pre><sub>"I am not haunting the project; I am just monitoring it with concern."</sub></td>
  </tr>
  <tr>
    <td valign="top"><strong>goose</strong><pre>

    (&gt;
    ||
  _(__)_
   ^^^^
</pre><sub>"This is now my incident, and I will be honking until it is fixed."</sub></td>
    <td valign="top"><strong>mushroom</strong><pre>

 .-o-OO-o-.
(__________)
   |o   o|
   |____|
</pre><sub>"Come sit down; recovery is also part of the roadmap."</sub></td>
    <td valign="top"><strong>octopus</strong><pre>

   .----.
  ( o  o )
  (______)
  /\/\/\/\
</pre><sub>"I can hold eight threads at once, but I would still prefer a checklist."</sub></td>
  </tr>
  <tr>
    <td valign="top"><strong>owl</strong><pre>

   /\  /\
  ((O)(O))
  (  &gt;&lt;  )
   `----'
</pre><sub>"The answer was always in the margins if you stayed up long enough."</sub></td>
    <td valign="top"><strong>penguin</strong><pre>
   .---.
  ( o&gt;o )
 /(     )\
  `-----`
   J   L
</pre><sub>"We do this with dignity, structure, and a very clean handoff."</sub></td>
    <td valign="top"><strong>rabbit</strong><pre>
    (\_/)
   ( o o )
  =(  v  )=
   (")_(")

</pre><sub>"I already started three versions, and one of them is definitely the winner."</sub></td>
  </tr>
  <tr>
    <td valign="top"><strong>robot</strong><pre>

   .[||].
  [ o    o ]
  [ ==== ]
  `------'
</pre><sub>"Please clarify the requirement so I can be correct at industrial scale."</sub></td>
    <td valign="top"><strong>snail</strong><pre>
  \\  /
    .--.
  _( oo )_
 (___@@___)
  ~~~~~~~~
</pre><sub>"Fast is nice, but finished and well-shaped is nicer."</sub></td>
    <td valign="top"><strong>turtle</strong><pre>

   _,--._
  ( o    o)
 /[______]\
  ``    ``
</pre><sub>"We are still moving, which means we are still winning."</sub></td>
  </tr>
</table>
